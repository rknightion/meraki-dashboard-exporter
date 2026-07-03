"""Unit tests for the OTLP data-log emitter (#622).

Uses the in-memory log-record exporter as a deterministic test seam; asserts the
emitter emits the right records when enabled, no-ops when disabled or
allowlisted-out, gates PII, tags the shared resource, and moves its
self-observability counters.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter  # noqa: PLC2701
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.__version__ import get_version
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.otel_data_logs import (
    BUILT_IN_EVENTS,
    PII_ATTRIBUTE_KEYS,
    DataLogEmitter,
    DataLogEvent,
)

PACKET_LOSS = DataLogEvent.WIRELESS_CLIENT_PACKET_LOSS.value


def _make_settings(**logs: object) -> Settings:
    """Build Settings with the given otel.logs sub-block (api key stubbed)."""
    otel: dict[str, object] = {}
    if logs:
        otel["logs"] = logs
    return Settings(meraki={"api_key": "a" * 40}, otel=otel)


def _make_emitter(
    exporter: InMemoryLogRecordExporter | None = None,
    registry: CollectorRegistry | None = None,
    **logs: object,
) -> tuple[DataLogEmitter, InMemoryLogRecordExporter, CollectorRegistry]:
    exp = exporter or InMemoryLogRecordExporter()
    reg = registry or CollectorRegistry()
    emitter = DataLogEmitter(_make_settings(**logs), registry=reg, exporter=exp)
    return emitter, exp, reg


class TestDataLogEmitterEnabled:
    """Emission behaviour when logs are enabled."""

    def test_emit_produces_record_with_event_name_and_attributes(self) -> None:
        """Emit produces record with event name and attributes."""
        emitter, exp, _ = _make_emitter(enabled=True, endpoint="http://otel:4317")
        emitter.emit(
            PACKET_LOSS,
            {"org.id": "123", "client.id": "c1", "downstream.loss_percent": 1.5},
            body="pkt loss summary",
        )

        records = exp.get_finished_logs()
        assert len(records) == 1
        rec = records[0].log_record
        assert rec.event_name == PACKET_LOSS
        assert rec.attributes["event.name"] == PACKET_LOSS
        assert rec.attributes["org.id"] == "123"
        assert rec.attributes["client.id"] == "c1"
        assert rec.attributes["downstream.loss_percent"] == 1.5
        assert rec.body == "pkt loss summary"

    def test_resource_attributes_present(self) -> None:
        """Resource attributes present."""
        emitter, exp, _ = _make_emitter(enabled=True, endpoint="http://otel:4317")
        emitter.emit(PACKET_LOSS, {"org.id": "1"})

        rec = exp.get_finished_logs()[0]
        res = rec.resource.attributes
        assert res["service.name"] == "meraki-dashboard-exporter"
        assert res["service.version"] == get_version()
        assert "service.instance.id" in res
        assert "deployment.environment" in res

    def test_enabled_property_true(self) -> None:
        """Enabled property true."""
        emitter, _, _ = _make_emitter(enabled=True, endpoint="http://otel:4317")
        assert emitter.enabled is True
        assert emitter.is_event_enabled(PACKET_LOSS) is True


class TestDataLogEmitterDisabled:
    """No-op behaviour when disabled (the hard default)."""

    def test_disabled_by_default(self) -> None:
        """Disabled by default."""
        emitter, exp, _ = _make_emitter()  # no logs block => default off
        assert emitter.enabled is False
        assert emitter.is_event_enabled(PACKET_LOSS) is False
        emitter.emit(PACKET_LOSS, {"org.id": "1"})
        assert len(exp.get_finished_logs()) == 0

    def test_explicit_disabled_noop(self) -> None:
        """Explicit disabled noop."""
        emitter, exp, _ = _make_emitter(enabled=False)
        emitter.emit(PACKET_LOSS, {"org.id": "1"})
        assert len(exp.get_finished_logs()) == 0

    def test_disabled_emitter_registers_no_counters(self) -> None:
        """Disabled emitter registers no counters."""
        _, _, reg = _make_emitter(enabled=False)
        assert (
            reg.get_sample_value(
                "meraki_exporter_data_log_records_emitted_total", {"event": PACKET_LOSS}
            )
            is None
        )


class TestDataLogEmitterAllowlist:
    """Per-data-class event allowlist filtering."""

    def test_event_not_in_allowlist_is_skipped(self) -> None:
        """Event not in allowlist is skipped."""
        emitter, exp, _ = _make_emitter(
            enabled=True, endpoint="http://otel:4317", events=["some.other.event"]
        )
        assert emitter.is_event_enabled(PACKET_LOSS) is False
        emitter.emit(PACKET_LOSS, {"org.id": "1"})
        assert len(exp.get_finished_logs()) == 0

    def test_event_in_allowlist_is_emitted(self) -> None:
        """Event in allowlist is emitted."""
        emitter, exp, _ = _make_emitter(
            enabled=True, endpoint="http://otel:4317", events=[PACKET_LOSS]
        )
        assert emitter.is_event_enabled(PACKET_LOSS) is True
        emitter.emit(PACKET_LOSS, {"org.id": "1"})
        assert len(exp.get_finished_logs()) == 1

    def test_none_allowlist_enables_all_built_ins(self) -> None:
        """None allowlist enables all built ins."""
        emitter, _, _ = _make_emitter(enabled=True, endpoint="http://otel:4317")
        for event in BUILT_IN_EVENTS:
            assert emitter.is_event_enabled(event) is True


class TestDataLogEmitterIdentifierGating:
    """PII / include_identifiers gating."""

    def test_pii_dropped_by_default(self) -> None:
        """Pii dropped by default."""
        emitter, exp, _ = _make_emitter(enabled=True, endpoint="http://otel:4317")
        assert emitter.include_identifiers is False
        emitter.emit(
            PACKET_LOSS,
            {
                "client.id": "c1",
                "client.mac": "aa:bb:cc:dd:ee:ff",
                "client.hostname": "laptop",
                "client.description": "Bob's laptop",
            },
        )
        attrs = exp.get_finished_logs()[0].log_record.attributes
        assert attrs["client.id"] == "c1"
        for pii_key in PII_ATTRIBUTE_KEYS:
            assert pii_key not in attrs

    def test_pii_included_when_opted_in(self) -> None:
        """Pii included when opted in."""
        emitter, exp, _ = _make_emitter(
            enabled=True, endpoint="http://otel:4317", include_identifiers=True
        )
        assert emitter.include_identifiers is True
        emitter.emit(
            PACKET_LOSS,
            {"client.id": "c1", "client.mac": "aa:bb:cc:dd:ee:ff"},
        )
        attrs = exp.get_finished_logs()[0].log_record.attributes
        assert attrs["client.mac"] == "aa:bb:cc:dd:ee:ff"


class TestDataLogEmitterCounters:
    """Self-observability counters."""

    def test_emitted_counter_increments(self) -> None:
        """Emitted counter increments."""
        emitter, _, reg = _make_emitter(enabled=True, endpoint="http://otel:4317")
        emitter.emit(PACKET_LOSS, {"org.id": "1"})
        emitter.emit(PACKET_LOSS, {"org.id": "2"})
        assert (
            reg.get_sample_value(
                "meraki_exporter_data_log_records_emitted_total", {"event": PACKET_LOSS}
            )
            == 2.0
        )

    def test_dropped_counter_increments_on_pipeline_error(self) -> None:
        """Dropped counter increments on pipeline error."""
        emitter, _, reg = _make_emitter(enabled=True, endpoint="http://otel:4317")

        # Swap the underlying logger for one whose emit() raises, to exercise the
        # best-effort drop path (enabled/is_event_enabled stay True: _logger is set).
        class _Boom:
            def emit(self, **_: object) -> None:
                raise RuntimeError("pipeline down")

        emitter._logger = _Boom()  # type: ignore[assignment]
        assert emitter.is_event_enabled(PACKET_LOSS) is True
        emitter.emit(PACKET_LOSS, {"org.id": "1"})
        assert (
            reg.get_sample_value(
                "meraki_exporter_data_log_records_dropped_total", {"event": PACKET_LOSS}
            )
            == 1.0
        )
        assert (
            reg.get_sample_value(
                "meraki_exporter_data_log_records_emitted_total", {"event": PACKET_LOSS}
            )
            is None
        )


class TestDataLogEmitterStats:
    """stats() surfaces data-log flow for /status (#639)."""

    def test_disabled_stats_report_zero(self) -> None:
        """A disabled emitter reports enabled=False and zero totals (not absent)."""
        emitter, _, _ = _make_emitter(enabled=False)
        stats = emitter.stats()
        assert stats["enabled"] is False
        assert stats["total_emitted"] == 0
        assert stats["total_dropped"] == 0
        assert stats["emitted_by_event"] == {}

    def test_stats_track_emitted_and_dropped(self) -> None:
        """stats() reflects cumulative emitted/dropped totals per event."""
        emitter, _, _ = _make_emitter(enabled=True, endpoint="http://otel:4317")
        emitter.emit(PACKET_LOSS, {"org.id": "1"})
        emitter.emit(PACKET_LOSS, {"org.id": "2"})

        class _Boom:
            def emit(self, **_: object) -> None:
                raise RuntimeError("pipeline down")

        emitter._logger = _Boom()  # type: ignore[assignment]
        emitter.emit(PACKET_LOSS, {"org.id": "3"})  # dropped

        stats = emitter.stats()
        assert stats["enabled"] is True
        assert stats["total_emitted"] == 2
        assert stats["total_dropped"] == 1
        assert stats["emitted_by_event"][PACKET_LOSS] == 2
        assert stats["dropped_by_event"][PACKET_LOSS] == 1


class TestDataLogEmitterShutdown:
    """Shutdown is safe in every state."""

    def test_shutdown_when_disabled_is_safe(self) -> None:
        """Shutdown when disabled is safe."""
        emitter, _, _ = _make_emitter(enabled=False)
        emitter.shutdown()  # must not raise

    def test_shutdown_flushes_when_enabled(self) -> None:
        """Shutdown flushes when enabled."""
        emitter, _, _ = _make_emitter(enabled=True, endpoint="http://otel:4317")
        emitter.emit(PACKET_LOSS, {"org.id": "1"})
        emitter.shutdown()  # must not raise


class TestDataLogEmitterInheritance:
    """Endpoint / insecure inheritance from the tracing block."""

    def test_endpoint_inherited_from_tracing(self) -> None:
        """Endpoint inherited from tracing."""
        settings = Settings(
            meraki={"api_key": "a" * 40},
            otel={"endpoint": "http://shared:4317", "logs": {"enabled": True}},
        )
        assert settings.otel.logs_endpoint == "http://shared:4317"

    def test_insecure_inherited_from_tracing(self) -> None:
        """Insecure inherited from tracing."""
        settings = Settings(
            meraki={"api_key": "a" * 40},
            otel={
                "endpoint": "http://shared:4317",
                "insecure": False,
                "logs": {"enabled": True},
            },
        )
        assert settings.otel.logs_insecure is False

    def test_insecure_own_value_overrides(self) -> None:
        """Insecure own value overrides."""
        settings = Settings(
            meraki={"api_key": "a" * 40},
            otel={
                "endpoint": "http://shared:4317",
                "insecure": False,
                "logs": {"enabled": True, "insecure": True},
            },
        )
        assert settings.otel.logs_insecure is True


class TestOTelLogsSettingsValidation:
    """Config validator for otel.logs."""

    def test_enabled_requires_resolvable_endpoint(self) -> None:
        """Enabled requires resolvable endpoint."""
        with pytest.raises(ValueError, match="data-log endpoint"):
            Settings(meraki={"api_key": "a" * 40}, otel={"logs": {"enabled": True}})

    def test_enabled_with_own_endpoint_ok(self) -> None:
        """Enabled with own endpoint ok."""
        settings = Settings(
            meraki={"api_key": "a" * 40},
            otel={"logs": {"enabled": True, "endpoint": "http://own:4317"}},
        )
        assert settings.otel.logs.enabled is True
        assert settings.otel.logs_endpoint == "http://own:4317"

    def test_logs_independent_of_tracing(self) -> None:
        """Logs independent of tracing."""
        # logs enabled, tracing disabled -> valid, and tracing endpoint not required
        settings = Settings(
            meraki={"api_key": "a" * 40},
            otel={"logs": {"enabled": True, "endpoint": "http://own:4317"}},
        )
        assert settings.otel.enabled is False
        assert settings.otel.logs.enabled is True

    def test_defaults_off(self) -> None:
        """Defaults off."""
        settings = Settings(meraki={"api_key": "a" * 40})
        assert settings.otel.logs.enabled is False
        assert settings.otel.logs.include_identifiers is False
        assert settings.otel.logs.events is None
        assert settings.otel.logs.endpoint is None


class TestDataLogEmitterExporterCredentials:
    """#314: the real OTLPLogExporter receives ``credentials=`` from cert paths.

    Uses MagicMock settings (not real ``Settings()``) so this test does not
    depend on Lane A's cert fields having landed on ``OTelSettings`` yet; only
    the attribute *access* is exercised, matching how ``_setup_provider`` reads
    ``settings.otel.ca_cert_path`` etc.
    """

    def _settings(
        self,
        ca_cert_path: str | None = None,
        client_cert_path: str | None = None,
        client_key_path: str | None = None,
    ) -> MagicMock:
        settings = MagicMock(spec=Settings)
        settings.otel = MagicMock()
        settings.otel.logs = MagicMock()
        settings.otel.logs.enabled = True
        settings.otel.logs.include_identifiers = False
        settings.otel.logs.events = None
        settings.otel.logs_endpoint = "http://otel:4317"
        settings.otel.logs_insecure = False
        settings.otel.ca_cert_path = ca_cert_path
        settings.otel.client_cert_path = client_cert_path
        settings.otel.client_key_path = client_key_path
        return settings

    def test_no_cert_paths_passes_none_credentials(self) -> None:
        """No cert paths configured -> exporter receives credentials=None."""
        settings = self._settings()
        with (
            patch(
                "opentelemetry.exporter.otlp.proto.grpc._log_exporter.OTLPLogExporter"
            ) as mock_exporter,
            patch("meraki_dashboard_exporter.core.otel_data_logs.BatchLogRecordProcessor"),
        ):
            DataLogEmitter(settings)

        assert mock_exporter.call_args.kwargs["credentials"] is None

    def test_cert_paths_set_passes_built_credentials(self, tmp_path) -> None:
        """Cert paths configured -> exporter receives the built ChannelCredentials object."""
        import grpc

        ca_path = tmp_path / "ca.pem"
        ca_path.write_bytes(b"CA-BYTES")
        settings = self._settings(ca_cert_path=str(ca_path))

        with (
            patch(
                "opentelemetry.exporter.otlp.proto.grpc._log_exporter.OTLPLogExporter"
            ) as mock_exporter,
            patch("meraki_dashboard_exporter.core.otel_data_logs.BatchLogRecordProcessor"),
        ):
            DataLogEmitter(settings)

        credentials = mock_exporter.call_args.kwargs["credentials"]
        assert credentials is not None
        assert isinstance(credentials, grpc.ChannelCredentials)
