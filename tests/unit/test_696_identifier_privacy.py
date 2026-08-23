"""Privacy contracts for #696 data-log identifier handling."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter  # noqa: PLC2701
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.collectors.devices.mr.client_logs import (
    MRClientLogsCollector,
    _PacketLossByClientRow,  # noqa: PLC2701
)
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.otel_data_logs import DataLogEmitter, DataLogEvent


def _emitter(exporter: InMemoryLogRecordExporter) -> DataLogEmitter:
    """Build an enabled default-privacy emitter with an in-memory exporter."""
    settings = Settings.model_validate({
        "meraki": {"api_key": "a" * 40},
        "otel": {"logs": {"enabled": True, "endpoint": "http://otel:4317"}},
    })
    return DataLogEmitter(
        settings,
        registry=CollectorRegistry(),
        exporter=exporter,  # type: ignore[arg-type]
    )


def test_696_missing_client_id_keeps_packet_loss_without_exposing_mac() -> None:
    """A MAC-only packet-loss row remains useful but contains no identifier."""
    exporter = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
    emitter = _emitter(exporter)
    parent = MagicMock()
    collector = MRClientLogsCollector(parent)
    mac = "aa:bb:cc:dd:ee:ff"
    row = _PacketLossByClientRow.model_validate({
        "client": {"mac": mac},
        "network": {"id": "N_1", "name": "Net"},
        "downstream": {"total": 1000, "lost": 10, "lossPercentage": 1.0},
        "upstream": {"total": 500, "lost": 5, "lossPercentage": 2.0},
    })

    collector._emit_packet_loss(emitter, "org1", "Org One", [row])

    records = exporter.get_finished_logs()
    assert len(records) == 1
    record = records[0].log_record
    attributes: dict[str, Any] = dict(record.attributes or {})
    assert "client.id" not in attributes
    assert mac not in attributes.values()
    assert mac not in str(record.body)


def test_696_default_privacy_scrubs_separated_mac_addresses_from_bodies() -> None:
    """Separated MAC text is redacted while ordinary body content is preserved."""
    exporter = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
    emitter = _emitter(exporter)
    body = "client aa:bb:cc:dd:ee:ff on AP 11-22-33-44-55-66: store 112233445566"

    emitter.emit(DataLogEvent.WIRELESS_CLIENT_PACKET_LOSS, {"org.id": "org1"}, body=body)

    exported_body = str(exporter.get_finished_logs()[0].log_record.body)
    assert "aa:bb:cc:dd:ee:ff" not in exported_body
    assert "11-22-33-44-55-66" not in exported_body
    assert exported_body.endswith(": store 112233445566")


def test_696_default_privacy_scrubs_mac_values_and_cisco_dotted_form() -> None:
    """A separated MAC cannot escape through an identifier or dotted body text."""
    exporter = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
    emitter = _emitter(exporter)

    emitter.emit(
        DataLogEvent.WIRELESS_CLIENT_PACKET_LOSS,
        {"org.id": "org1", "client.id": "aa:bb:cc:dd:ee:ff"},
        body="clients aabb.ccdd.eeff and 112233445566 packet loss stable",
    )

    record = exporter.get_finished_logs()[0].log_record
    attributes: dict[str, Any] = dict(record.attributes or {})
    assert attributes["client.id"] == "[redacted-mac]"
    assert "aabb.ccdd.eeff" not in str(record.body)
    assert "112233445566" in str(record.body)


def test_696_default_privacy_redacts_bare_mac_in_mac_attribute_key() -> None:
    """A delimiter-free MAC is redacted when its attribute key identifies it as a MAC."""
    exporter = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
    emitter = _emitter(exporter)

    emitter.emit(
        DataLogEvent.WIRELESS_CLIENT_PACKET_LOSS,
        {
            "device.mac": "112233445566",
            "network.name": "store-112233445566",
        },
    )

    attributes = dict(exporter.get_finished_logs()[0].log_record.attributes or {})
    assert attributes["device.mac"] == "[redacted-mac]"
    assert attributes["network.name"] == "store-112233445566"
