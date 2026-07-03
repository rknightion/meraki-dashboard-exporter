"""Tests for the WebhookLogsCollector (#300)."""

from __future__ import annotations

import pytest

from meraki_dashboard_exporter.collectors.organization_collectors.webhooks import (
    WebhookLogsCollector,
)


class _MockParent:
    def __init__(self, api) -> None:
        self.api = api
        self.settings = None
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

    def _collector(self, mock_api_builder) -> WebhookLogsCollector:
        parent = _MockParent(mock_api_builder.build())
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
