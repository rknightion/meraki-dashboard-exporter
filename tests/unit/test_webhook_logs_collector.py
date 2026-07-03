"""Tests for the WebhookLogsCollector (#300, #622)."""

from __future__ import annotations

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter  # noqa: PLC2701
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.collectors.organization_collectors.webhooks import (
    WebhookLogsCollector,
)
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.otel_data_logs import DataLogEmitter, DataLogEvent


def _make_emitter(
    *, enabled: bool = True, events: list[str] | None = None
) -> tuple[DataLogEmitter, InMemoryLogRecordExporter]:
    """Build a real DataLogEmitter wired to an in-memory exporter (test seam)."""
    exp = InMemoryLogRecordExporter()
    otel: dict[str, object] = {"logs": {"enabled": enabled, "endpoint": "http://otel:4317"}}
    if events is not None:
        otel["logs"]["events"] = events  # type: ignore[index]
    settings = Settings(meraki={"api_key": "a" * 40}, otel=otel)
    emitter = DataLogEmitter(settings, registry=CollectorRegistry(), exporter=exp)
    return emitter, exp


class _MockParent:
    def __init__(self, api, *, data_log_emitter=None) -> None:
        self.api = api
        self.settings = None
        self.data_log_emitter = data_log_emitter
        self._metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    def _should_run_group(self, group: object) -> bool:
        return True

    def _mark_group_ran(self, group: object) -> None:
        pass

    def _group_ttl_seconds(self, group: object) -> float | None:
        return None

    def _track_api_call(self, method_name: str) -> None:
        pass

    def _set_metric_value(
        self,
        metric_name: str,
        labels: dict[str, str],
        value: float | None,
        ttl_seconds: float | None = None,
    ) -> None:
        if value is not None:
            key = (metric_name, tuple(sorted(labels.items())))
            self._metrics[key] = value


class TestWebhookLogsCollector:
    """Test WebhookLogsCollector functionality."""

    @pytest.fixture
    def mock_api_builder(self):
        """Create a mock API builder."""
        from tests.helpers.mock_api import MockAPIBuilder

        return MockAPIBuilder()

    def _collector(self, mock_api_builder, *, data_log_emitter=None) -> WebhookLogsCollector:
        parent = _MockParent(mock_api_builder.build(), data_log_emitter=data_log_emitter)
        return WebhookLogsCollector(parent=parent)  # type: ignore[arg-type]

    async def test_counts_by_status_code(self, mock_api_builder):
        """Delivery attempts are counted per HTTP response status code."""
        org_id = "org1"
        logs = [
            {"responseCode": 200, "url": "https://a.example/hook"},
            {"responseCode": 200, "url": "https://a.example/hook"},
            {"responseCode": 500, "url": "https://a.example/hook"},
            {"responseCode": 404, "url": "https://b.example/hook"},
        ]
        api = mock_api_builder.with_custom_response("getOrganizationWebhooksLogs", logs).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        result = await collector.collect(org_id, "Org One")
        assert result is True

        m = collector.parent._metrics
        assert (
            m[("_org_webhook_deliveries_count", (("org_id", org_id), ("status_code", "200")))] == 2
        )
        assert (
            m[("_org_webhook_deliveries_count", (("org_id", org_id), ("status_code", "500")))] == 1
        )
        assert (
            m[("_org_webhook_deliveries_count", (("org_id", org_id), ("status_code", "404")))] == 1
        )

        # timespan + total_pages passed correctly.
        call = api.organizations.getOrganizationWebhooksLogs.call_args
        assert call[1]["timespan"] == 3600
        assert call[1]["total_pages"] == "all"

    async def test_missing_response_code_maps_to_zero(self, mock_api_builder):
        """An attempt with no response (connection failure) counts under '0'."""
        org_id = "org2"
        logs = [{"responseCode": None}, {"url": "https://x"}]
        api = mock_api_builder.with_custom_response("getOrganizationWebhooksLogs", logs).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        await collector.collect(org_id, "Org Two")
        m = collector.parent._metrics
        assert m[("_org_webhook_deliveries_count", (("org_id", org_id), ("status_code", "0")))] == 2

    async def test_stale_codes_zeroed_across_cycles(self, mock_api_builder):
        """A status code present last cycle but absent this cycle reports 0."""
        org_id = "org3"

        api1 = mock_api_builder.with_custom_response(
            "getOrganizationWebhooksLogs", [{"responseCode": 500}]
        ).build()
        collector = self._collector(mock_api_builder)
        collector.api = api1
        await collector.collect(org_id, "Org Three")

        m = collector.parent._metrics
        assert (
            m[("_org_webhook_deliveries_count", (("org_id", org_id), ("status_code", "500")))] == 1
        )

        # Second cycle: only 200s now; the 500 series must drop to 0.
        api2 = mock_api_builder.with_custom_response(
            "getOrganizationWebhooksLogs", [{"responseCode": 200}]
        ).build()
        collector.api = api2
        await collector.collect(org_id, "Org Three")

        assert (
            m[("_org_webhook_deliveries_count", (("org_id", org_id), ("status_code", "500")))] == 0
        )
        assert (
            m[("_org_webhook_deliveries_count", (("org_id", org_id), ("status_code", "200")))] == 1
        )

    async def test_empty_log_is_not_an_error(self, mock_api_builder):
        """No webhook receivers configured -> empty list, success, no series."""
        api = mock_api_builder.with_custom_response("getOrganizationWebhooksLogs", []).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        result = await collector.collect("org4", "Org Four")
        assert result is True
        assert len(collector.parent._metrics) == 0

    async def test_collect_handles_404(self, mock_api_builder):
        """A 404 is a benign skip (returns True)."""
        api = mock_api_builder.with_error(
            "getOrganizationWebhooksLogs", Exception("404 Not Found")
        ).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        result = await collector.collect("org5", "Org Five")
        assert result is True


class TestWebhookLogsCollectorDataLogEmission:
    """Per-delivery OTel data-log emission (#622), reusing the aggregate fetch."""

    @pytest.fixture
    def mock_api_builder(self):
        """Create a mock API builder."""
        from tests.helpers.mock_api import MockAPIBuilder

        return MockAPIBuilder()

    def _collector(self, mock_api_builder, *, data_log_emitter=None) -> WebhookLogsCollector:
        parent = _MockParent(mock_api_builder.build(), data_log_emitter=data_log_emitter)
        return WebhookLogsCollector(parent=parent)  # type: ignore[arg-type]

    async def test_emits_one_record_per_delivery_when_enabled(self, mock_api_builder):
        """One ORG_WEBHOOK_DELIVERY record is emitted per fetched row."""
        emitter, exp = _make_emitter(events=[DataLogEvent.ORG_WEBHOOK_DELIVERY.value])
        org_id = "org1"
        logs = [
            {
                "networkId": "N_1",
                "url": "https://a.example/hook?token=secret",
                "alertType": "Nightly report",
                "responseCode": 200,
            },
            {
                "networkId": "N_2",
                "url": "https://b.example/hook",
                "responseCode": 500,
            },
        ]
        api = mock_api_builder.with_custom_response("getOrganizationWebhooksLogs", logs).build()
        collector = self._collector(mock_api_builder, data_log_emitter=emitter)
        collector.api = api

        result = await collector.collect(org_id, "Org One")
        assert result is True

        records = exp.get_finished_logs()
        assert len(records) == 2

        by_status = {r.log_record.attributes["status_code"]: r.log_record for r in records}

        rec_200 = by_status["200"]
        assert rec_200.event_name == DataLogEvent.ORG_WEBHOOK_DELIVERY.value
        assert rec_200.attributes["org.id"] == org_id
        assert rec_200.attributes["network.id"] == "N_1"
        assert rec_200.attributes["webhook.alert_type"] == "Nightly report"
        assert rec_200.attributes["url.host"] == "a.example"
        assert rec_200.attributes["data.window_seconds"] == 3600
        # No full URL / query string / token ever emitted.
        assert "url" not in rec_200.attributes
        assert not any("secret" in str(v) for v in rec_200.attributes.values())

        rec_500 = by_status["500"]
        assert rec_500.attributes["network.id"] == "N_2"
        assert "webhook.alert_type" not in rec_500.attributes

        # The aggregate metric still fires independently of the log emission.
        m = collector.parent._metrics
        assert (
            m[("_org_webhook_deliveries_count", (("org_id", org_id), ("status_code", "200")))] == 1
        )
        assert (
            m[("_org_webhook_deliveries_count", (("org_id", org_id), ("status_code", "500")))] == 1
        )

    async def test_no_emission_when_emitter_is_none(self, mock_api_builder):
        """No emitter (default / logs disabled) -> no attempt to emit, no error."""
        logs = [{"networkId": "N_1", "url": "https://a.example/hook", "responseCode": 200}]
        api = mock_api_builder.with_custom_response("getOrganizationWebhooksLogs", logs).build()
        collector = self._collector(mock_api_builder, data_log_emitter=None)
        collector.api = api

        result = await collector.collect("org1", "Org One")
        assert result is True
        # Aggregate metric unaffected by the absence of a data-log emitter.
        assert (
            collector.parent._metrics[
                ("_org_webhook_deliveries_count", (("org_id", "org1"), ("status_code", "200")))
            ]
            == 1
        )

    async def test_no_emission_when_event_not_allowlisted(self, mock_api_builder):
        """Emitter present but ORG_WEBHOOK_DELIVERY not allowlisted -> no records."""
        emitter, exp = _make_emitter(events=["some.other.event"])
        logs = [{"networkId": "N_1", "url": "https://a.example/hook", "responseCode": 200}]
        api = mock_api_builder.with_custom_response("getOrganizationWebhooksLogs", logs).build()
        collector = self._collector(mock_api_builder, data_log_emitter=emitter)
        collector.api = api

        result = await collector.collect("org1", "Org One")
        assert result is True
        assert len(exp.get_finished_logs()) == 0

    async def test_no_emission_when_logs_disabled(self, mock_api_builder):
        """Emitter constructed but disabled -> no records, no exception."""
        emitter, exp = _make_emitter(enabled=False)
        logs = [{"networkId": "N_1", "url": "https://a.example/hook", "responseCode": 200}]
        api = mock_api_builder.with_custom_response("getOrganizationWebhooksLogs", logs).build()
        collector = self._collector(mock_api_builder, data_log_emitter=emitter)
        collector.api = api

        result = await collector.collect("org1", "Org One")
        assert result is True
        assert len(exp.get_finished_logs()) == 0

    async def test_empty_logs_emit_nothing(self, mock_api_builder):
        """Empty delivery log -> no records emitted (nothing to emit)."""
        emitter, exp = _make_emitter(events=[DataLogEvent.ORG_WEBHOOK_DELIVERY.value])
        api = mock_api_builder.with_custom_response("getOrganizationWebhooksLogs", []).build()
        collector = self._collector(mock_api_builder, data_log_emitter=emitter)
        collector.api = api

        result = await collector.collect("org1", "Org One")
        assert result is True
        assert len(exp.get_finished_logs()) == 0

    async def test_no_response_code_maps_to_zero_in_log_too(self, mock_api_builder):
        """A row with no responseCode gets status_code '0' in the log record too."""
        emitter, exp = _make_emitter(events=[DataLogEvent.ORG_WEBHOOK_DELIVERY.value])
        logs = [{"networkId": "N_1", "responseCode": None}]
        api = mock_api_builder.with_custom_response("getOrganizationWebhooksLogs", logs).build()
        collector = self._collector(mock_api_builder, data_log_emitter=emitter)
        collector.api = api

        await collector.collect("org1", "Org One")
        records = exp.get_finished_logs()
        assert len(records) == 1
        assert records[0].log_record.attributes["status_code"] == "0"

    async def test_producer_creates_no_new_prometheus_series(self, mock_api_builder):
        """The log-emission code path adds no new Prometheus series of its own.

        The emitter's own self-observability counters live on the emitter's
        private registry (asserted separately in test_otel_data_logs.py); this
        test asserts the *producer* (webhooks.py) itself only ever touches the
        one pre-existing aggregate-metric attribute, regardless of whether the
        data-log emitter is enabled.
        """
        emitter, _exp = _make_emitter(events=[DataLogEvent.ORG_WEBHOOK_DELIVERY.value])
        logs = [
            {"networkId": "N_1", "url": "https://a.example/hook", "responseCode": 200},
            {"networkId": "N_2", "url": "https://b.example/hook", "responseCode": 500},
        ]
        api = mock_api_builder.with_custom_response("getOrganizationWebhooksLogs", logs).build()
        collector = self._collector(mock_api_builder, data_log_emitter=emitter)
        collector.api = api

        await collector.collect("org1", "Org One")

        metric_names = {key[0] for key in collector.parent._metrics}
        assert metric_names == {"_org_webhook_deliveries_count"}
