"""Tests for the MR per-client wireless DATA-LOG producers (#323 + #622).

These producers emit OTLP data-log records (via ``DataLogEmitter``) and create NO
Prometheus series. The tests assert:
- both events off (or emitter absent) => no API call, no records (zero cost);
- packet-loss records carry the right bounded attributes; PII is gated;
- NetworkFilter is enforced on the org-wide response;
- the experimental signal-quality fan-out emits per-client records;
- the producer creates NO new Prometheus series;
- the fetcher normalizes the SDK exhausted-retry error shape.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter  # noqa: PLC2701
from prometheus_client import CollectorRegistry
from prometheus_client.core import REGISTRY

from meraki_dashboard_exporter.collectors.devices.mr.client_logs import (
    MRClientLogsCollector,
    _PacketLossByClientRow,  # noqa: PLC2701
)
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.error_handling import DataValidationError
from meraki_dashboard_exporter.core.otel_data_logs import DataLogEmitter, DataLogEvent

PACKET_LOSS = DataLogEvent.WIRELESS_CLIENT_PACKET_LOSS.value
SIGNAL_QUALITY = DataLogEvent.WIRELESS_CLIENT_SIGNAL_QUALITY.value


def _make_emitter(exporter: InMemoryLogRecordExporter, **logs: object) -> DataLogEmitter:
    """Build a DataLogEmitter with an isolated registry + in-memory exporter."""
    otel: dict[str, object] = {"logs": logs} if logs else {}
    settings = Settings(meraki={"api_key": "a" * 40}, otel=otel)
    return DataLogEmitter(settings, registry=CollectorRegistry(), exporter=exporter)


def _pl_row(
    client_id: str,
    network_id: str,
    *,
    mac: str = "aa:bb:cc:dd:ee:ff",
    name: str = "Net",
) -> dict[str, Any]:
    """Build one getOrganizationWirelessDevicesPacketLossByClient row."""
    return {
        "client": {"id": client_id, "mac": mac},
        "network": {"id": network_id, "name": name},
        "downstream": {"total": 1000, "lost": 10, "lossPercentage": 1.0},
        "upstream": {"total": 500, "lost": 5, "lossPercentage": 2.0},
    }


def _sq_history() -> list[dict[str, Any]]:
    """Two signal-quality buckets; newest (by endTs) is snr=35/rssi=-55."""
    return [
        {
            "startTs": "2026-01-01T00:00:00Z",
            "endTs": "2026-01-01T01:00:00Z",
            "snr": 30,
            "rssi": -60,
        },
        {
            "startTs": "2026-01-01T01:00:00Z",
            "endTs": "2026-01-01T02:00:00Z",
            "snr": 35,
            "rssi": -55,
        },
    ]


class _FakeParent:
    """Minimal DeviceCollector stand-in for the log producer."""

    def __init__(
        self,
        emitter: DataLogEmitter | None,
        *,
        allowed_network_ids: set[str] | None = None,
    ) -> None:
        self.api = MagicMock()
        self.api.wireless = MagicMock()
        self.settings = MagicMock()
        self.settings.api.concurrency_limit = 5
        self.data_log_emitter = emitter
        # _create_gauge must NEVER be called by a log producer.
        self._create_gauge = MagicMock()
        if allowed_network_ids is None:
            self.inventory = None
        else:
            self.inventory = MagicMock()
            self.inventory.get_allowed_network_ids = AsyncMock(return_value=allowed_network_ids)


def _registry_metric_names() -> set[str]:
    return {family.name for family in REGISTRY.collect()}


class TestPacketLossProducer:
    """WIRELESS_CLIENT_PACKET_LOSS (#323) — the clean bulk primary."""

    async def test_emits_one_record_per_client_row(self) -> None:
        """Emits one record per client row."""
        exp = InMemoryLogRecordExporter()
        emitter = _make_emitter(exp, enabled=True, endpoint="http://otel:4317")
        parent = _FakeParent(emitter)
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock(
            return_value=[_pl_row("c1", "N_1"), _pl_row("c2", "N_1")]
        )
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        await collector.collect_client_logs("org1", "Org One")

        records = exp.get_finished_logs()
        assert len(records) == 2
        rec = records[0].log_record
        assert rec.event_name == PACKET_LOSS
        a = rec.attributes
        assert a["org.id"] == "org1"
        assert a["network.id"] == "N_1"
        assert a["network.name"] == "Net"
        assert a["client.id"] == "c1"
        assert a["downstream.total_packets"] == 1000
        assert a["downstream.lost_packets"] == 10
        assert a["downstream.loss_percent"] == 1.0
        assert a["upstream.total_packets"] == 500
        assert a["upstream.loss_percent"] == 2.0
        # total = (10+5)/(1000+500)*100 = 1.0
        assert a["total.loss_percent"] == pytest.approx(1.0)
        assert a["data.window_seconds"] == 300

    async def test_pii_dropped_by_default(self) -> None:
        """Pii dropped by default."""
        exp = InMemoryLogRecordExporter()
        emitter = _make_emitter(exp, enabled=True, endpoint="http://otel:4317")
        parent = _FakeParent(emitter)
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock(
            return_value=[_pl_row("c1", "N_1")]
        )
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        await collector.collect_client_logs("org1", "Org One")

        a = exp.get_finished_logs()[0].log_record.attributes
        assert "client.mac" not in a

    async def test_pii_included_when_opted_in(self) -> None:
        """Pii included when opted in."""
        exp = InMemoryLogRecordExporter()
        emitter = _make_emitter(
            exp, enabled=True, endpoint="http://otel:4317", include_identifiers=True
        )
        parent = _FakeParent(emitter)
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock(
            return_value=[_pl_row("c1", "N_1", mac="11:22:33:44:55:66")]
        )
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        await collector.collect_client_logs("org1", "Org One")

        a = exp.get_finished_logs()[0].log_record.attributes
        assert a["client.mac"] == "11:22:33:44:55:66"

    async def test_network_filter_enforced(self) -> None:
        """Network filter enforced."""
        exp = InMemoryLogRecordExporter()
        emitter = _make_emitter(exp, enabled=True, endpoint="http://otel:4317")
        parent = _FakeParent(emitter, allowed_network_ids={"N_1"})
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock(
            return_value=[_pl_row("c1", "N_1"), _pl_row("c2", "N_denied")]
        )
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        await collector.collect_client_logs("org1", "Org One")

        records = exp.get_finished_logs()
        assert len(records) == 1
        assert records[0].log_record.attributes["client.id"] == "c1"


class TestGatingZeroCost:
    """Disabled events / absent emitter => no API call, no records."""

    async def test_no_emitter_is_noop(self) -> None:
        """No emitter is noop."""
        parent = _FakeParent(None)
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock()
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        await collector.collect_client_logs("org1", "Org One")

        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient.assert_not_called()

    async def test_both_events_disabled_skips_fetch(self) -> None:
        """Both events disabled skips fetch."""
        exp = InMemoryLogRecordExporter()
        # enabled=False => is_event_enabled False for both events.
        emitter = _make_emitter(exp, enabled=False)
        parent = _FakeParent(emitter)
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock()
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        await collector.collect_client_logs("org1", "Org One")

        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient.assert_not_called()
        assert len(exp.get_finished_logs()) == 0

    async def test_signal_quality_only_does_not_emit_packet_loss(self) -> None:
        """Signal quality only does not emit packet loss."""
        exp = InMemoryLogRecordExporter()
        emitter = _make_emitter(
            exp, enabled=True, endpoint="http://otel:4317", events=[SIGNAL_QUALITY]
        )
        parent = _FakeParent(emitter)
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock(
            return_value=[_pl_row("c1", "N_1")]
        )
        parent.api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=_sq_history()
        )
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        await collector.collect_client_logs("org1", "Org One")

        events = {r.log_record.event_name for r in exp.get_finished_logs()}
        assert events == {SIGNAL_QUALITY}


class TestSignalQualityProducer:
    """WIRELESS_CLIENT_SIGNAL_QUALITY (#622) — experimental per-client fan-out."""

    async def test_emits_newest_bucket_per_client(self) -> None:
        """Emits newest bucket per client."""
        exp = InMemoryLogRecordExporter()
        emitter = _make_emitter(
            exp, enabled=True, endpoint="http://otel:4317", events=[SIGNAL_QUALITY]
        )
        parent = _FakeParent(emitter)
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock(
            return_value=[_pl_row("c1", "N_1")]
        )
        parent.api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=_sq_history()
        )
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        await collector.collect_client_logs("org1", "Org One")

        records = exp.get_finished_logs()
        assert len(records) == 1
        a = records[0].log_record.attributes
        assert records[0].log_record.event_name == SIGNAL_QUALITY
        assert a["org.id"] == "org1"
        assert a["network.id"] == "N_1"
        assert a["client.id"] == "c1"
        assert a["signal.rssi_dbm"] == -55.0
        assert a["signal.snr_db"] == 35.0
        assert a["data.window_seconds"] == 3600
        # The per-client fan-out filtered by clientId.
        _, kwargs = parent.api.wireless.getNetworkWirelessSignalQualityHistory.call_args
        assert kwargs["clientId"] == "c1"

    async def test_both_events_emit_both_record_types(self) -> None:
        """Both events emit both record types."""
        exp = InMemoryLogRecordExporter()
        emitter = _make_emitter(exp, enabled=True, endpoint="http://otel:4317")
        parent = _FakeParent(emitter)
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock(
            return_value=[_pl_row("c1", "N_1")]
        )
        parent.api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=_sq_history()
        )
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        await collector.collect_client_logs("org1", "Org One")

        events = sorted(r.log_record.event_name for r in exp.get_finished_logs())
        assert events == sorted([PACKET_LOSS, SIGNAL_QUALITY])

    async def test_all_null_history_emits_nothing(self) -> None:
        """All null history emits nothing."""
        exp = InMemoryLogRecordExporter()
        emitter = _make_emitter(
            exp, enabled=True, endpoint="http://otel:4317", events=[SIGNAL_QUALITY]
        )
        parent = _FakeParent(emitter)
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock(
            return_value=[_pl_row("c1", "N_1")]
        )
        parent.api.wireless.getNetworkWirelessSignalQualityHistory = MagicMock(
            return_value=[{"startTs": "t", "endTs": "t", "snr": None, "rssi": None}]
        )
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        await collector.collect_client_logs("org1", "Org One")

        assert len(exp.get_finished_logs()) == 0


class TestNoPrometheusSeries:
    """The producer must never create a Prometheus series."""

    async def test_producer_creates_no_series(self) -> None:
        """Producer creates no series."""
        exp = InMemoryLogRecordExporter()
        emitter = _make_emitter(exp, enabled=True, endpoint="http://otel:4317")
        parent = _FakeParent(emitter)
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock(
            return_value=[_pl_row("c1", "N_1"), _pl_row("c2", "N_1")]
        )
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        before = _registry_metric_names()
        await collector.collect_client_logs("org1", "Org One")
        after = _registry_metric_names()

        assert after == before
        # And the metric-creation seam was never touched.
        parent._create_gauge.assert_not_called()


class TestFetcherErrorShape:
    """validate_response_format normalizes the SDK exhausted-retry error shape."""

    async def test_error_shaped_response_raises(self) -> None:
        """Error shaped response raises."""
        exp = InMemoryLogRecordExporter()
        emitter = _make_emitter(exp, enabled=True, endpoint="http://otel:4317")
        parent = _FakeParent(emitter)
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock(
            return_value={"errors": ["Bad request: invalid organization"]}
        )
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        with pytest.raises(DataValidationError):
            await collector._fetch_packet_loss_by_client("org1")

    async def test_error_shaped_response_swallowed_by_collect(self) -> None:
        """Error shaped response swallowed by collect."""
        # The outer @with_error_handling(continue_on_error=True) means a bad
        # response never aborts the collection cycle and emits nothing.
        exp = InMemoryLogRecordExporter()
        emitter = _make_emitter(exp, enabled=True, endpoint="http://otel:4317")
        parent = _FakeParent(emitter)
        parent.api.wireless.getOrganizationWirelessDevicesPacketLossByClient = MagicMock(
            return_value={"errors": ["Bad request: invalid organization"]}
        )
        collector = MRClientLogsCollector(parent)  # type: ignore[arg-type]

        await collector.collect_client_logs("org1", "Org One")  # must not raise
        assert len(exp.get_finished_logs()) == 0


class TestModel:
    """Lenient parsing of the byClient row model."""

    def test_extra_fields_allowed(self) -> None:
        """Extra fields allowed."""
        row = _PacketLossByClientRow.model_validate({
            "client": {"id": "c1", "mac": "aa:bb", "extra": 1},
            "network": {"id": "N_1", "name": "Net"},
            "downstream": {"total": 10, "lost": 1, "lossPercentage": 10.0},
            "upstream": {"total": 5, "lost": 0, "lossPercentage": 0.0},
            "unknownTopLevel": "ignored",
        })
        assert row.client is not None and row.client.id == "c1"
        assert row.downstream is not None and row.downstream.total == 10
