"""Tests for OpenTelemetry tracing configuration."""

# ruff: noqa: S101

from __future__ import annotations

from unittest.mock import MagicMock, patch

import grpc
import pytest

from meraki_dashboard_exporter.__version__ import get_version
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.otel_tracing import TracingConfig, build_otlp_credentials


class TestTracingConfigSetup:
    """Test TracingConfig setup behavior with various settings."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings with configurable OTEL options."""
        settings = MagicMock(spec=Settings)
        settings.otel = MagicMock()
        settings.otel.ca_cert_path = None
        settings.otel.client_cert_path = None
        settings.otel.client_key_path = None
        settings.otel.enabled = False
        settings.otel.endpoint = None
        settings.otel.service_name = "test-service"
        settings.otel.resource_attributes = {}
        return settings

    def test_tracing_disabled_when_otel_not_enabled(self, mock_settings: MagicMock) -> None:
        """Test tracing is not set up when OTEL is disabled."""
        mock_settings.otel.enabled = False
        mock_settings.otel.endpoint = "http://otel:4317"

        config = TracingConfig(mock_settings)

        with patch.object(config, "_create_sampler") as mock_sampler:
            config.setup_tracing()
            mock_sampler.assert_not_called()

        assert not config._initialized

    def test_tracing_disabled_when_no_endpoint(self, mock_settings: MagicMock) -> None:
        """Test tracing is not set up when no endpoint is configured."""
        mock_settings.otel.enabled = True
        mock_settings.otel.endpoint = None

        config = TracingConfig(mock_settings)

        with patch.object(config, "_create_sampler") as mock_sampler:
            config.setup_tracing()
            mock_sampler.assert_not_called()

        assert not config._initialized

    def test_tracing_enabled_with_all_conditions_met(self, mock_settings: MagicMock) -> None:
        """Test tracing is set up when all conditions are met."""
        mock_settings.otel.enabled = True
        mock_settings.otel.endpoint = "http://otel:4317"

        config = TracingConfig(mock_settings)

        # Patch the dependencies to avoid actual OTEL setup
        with (
            patch("meraki_dashboard_exporter.core.otel_tracing.Resource.create"),
            patch("meraki_dashboard_exporter.core.otel_tracing.TracerProvider"),
            patch("meraki_dashboard_exporter.core.otel_tracing.OTLPSpanExporter"),
            patch("meraki_dashboard_exporter.core.otel_tracing.BatchSpanProcessor"),
            patch("meraki_dashboard_exporter.core.otel_tracing.trace.set_tracer_provider"),
            patch("meraki_dashboard_exporter.core.otel_tracing.set_global_textmap"),
        ):
            config.setup_tracing()

        assert config._initialized


class TestTracingConfigResourceVersion:
    """Test the OTel Resource is tagged with the real package version."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings with OTEL enabled and an endpoint configured."""
        settings = MagicMock(spec=Settings)
        settings.otel = MagicMock()
        settings.otel.ca_cert_path = None
        settings.otel.client_cert_path = None
        settings.otel.client_key_path = None
        settings.otel.enabled = True
        settings.otel.endpoint = "http://otel:4317"
        settings.otel.service_name = "test-service"
        settings.otel.resource_attributes = {}
        return settings

    def test_resource_service_version_matches_package_version(
        self, mock_settings: MagicMock
    ) -> None:
        """The Resource's service.version must be the real, dynamic package version."""
        config = TracingConfig(mock_settings)

        with (
            patch("meraki_dashboard_exporter.core.otel_tracing.Resource.create") as mock_resource,
            patch("meraki_dashboard_exporter.core.otel_tracing.TracerProvider"),
            patch("meraki_dashboard_exporter.core.otel_tracing.OTLPSpanExporter"),
            patch("meraki_dashboard_exporter.core.otel_tracing.BatchSpanProcessor"),
            patch("meraki_dashboard_exporter.core.otel_tracing.trace.set_tracer_provider"),
            patch("meraki_dashboard_exporter.core.otel_tracing.set_global_textmap"),
        ):
            config.setup_tracing()

        resource_attrs = mock_resource.call_args[0][0]
        assert resource_attrs["service.version"] == get_version()
        assert resource_attrs["service.version"] != "0.8.0"


class TestTracingConfigSettings:
    """Test tracing configuration via environment settings."""

    @pytest.fixture
    def make_settings(self, monkeypatch) -> callable:
        """Factory to create settings with various OTEL configurations."""

        def _make_settings(
            otel_enabled: bool = True,
            endpoint: str = "http://otel:4317",
        ) -> Settings:
            monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
            if otel_enabled:
                monkeypatch.setenv("MERAKI_EXPORTER_OTEL__ENABLED", "true")
                monkeypatch.setenv("MERAKI_EXPORTER_OTEL__ENDPOINT", endpoint)
            else:
                monkeypatch.setenv("MERAKI_EXPORTER_OTEL__ENABLED", "false")

            return Settings()

        return _make_settings

    def test_tracing_only_mode(self, make_settings) -> None:
        """Test tracing can be enabled when OTEL is enabled."""
        settings = make_settings(
            otel_enabled=True,
        )

        assert settings.otel.enabled is True

    def test_sampling_rate_honored_from_env(self, monkeypatch) -> None:
        """A sampling rate set via env/.env is read from settings (F-106)."""
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON

        monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
        monkeypatch.setenv("MERAKI_EXPORTER_OTEL__SAMPLING_RATE", "1.0")
        settings = Settings()

        assert settings.otel.sampling_rate == 1.0

        config = TracingConfig(settings)
        assert config._get_sampling_rate() == 1.0
        assert config._create_sampler() is ALWAYS_ON


class TestTracingConfigSampling:
    """F-106: sampling rate sourced from settings, with a guarded parse."""

    def _settings(self, sampling_rate) -> MagicMock:
        settings = MagicMock(spec=Settings)
        settings.otel = MagicMock()
        settings.otel.ca_cert_path = None
        settings.otel.client_cert_path = None
        settings.otel.client_key_path = None
        settings.otel.sampling_rate = sampling_rate
        return settings

    def test_zero_rate_disables_sampling(self) -> None:
        """A 0.0 sampling rate maps to ALWAYS_OFF."""
        from opentelemetry.sdk.trace.sampling import ALWAYS_OFF

        config = TracingConfig(self._settings(0.0))
        assert config._create_sampler() is ALWAYS_OFF

    def test_full_rate_samples_all(self) -> None:
        """A 1.0 sampling rate maps to ALWAYS_ON."""
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON

        config = TracingConfig(self._settings(1.0))
        assert config._create_sampler() is ALWAYS_ON

    def test_partial_rate_uses_ratio_sampler(self) -> None:
        """A fractional sampling rate maps to a ParentBased ratio sampler."""
        from opentelemetry.sdk.trace.sampling import ParentBased

        config = TracingConfig(self._settings(0.5))
        assert isinstance(config._create_sampler(), ParentBased)

    def test_malformed_rate_does_not_abort(self) -> None:
        """A non-numeric sampling rate falls back to the default without raising (F-106)."""
        from opentelemetry.sdk.trace.sampling import ParentBased

        config = TracingConfig(self._settings("not-a-float"))

        # Guarded: does not raise, falls back to the 0.1 default.
        assert config._get_sampling_rate() == config._DEFAULT_SAMPLING_RATE
        assert isinstance(config._create_sampler(), ParentBased)


class TestTracingConfigExporterTLS:
    """F-110: the OTLP exporter's insecure flag is driven by settings."""

    def _settings(self, insecure: bool) -> MagicMock:
        settings = MagicMock(spec=Settings)
        settings.otel = MagicMock()
        settings.otel.ca_cert_path = None
        settings.otel.client_cert_path = None
        settings.otel.client_key_path = None
        settings.otel.enabled = True
        settings.otel.endpoint = "http://otel:4317"
        settings.otel.service_name = "test-service"
        settings.otel.resource_attributes = {}
        settings.otel.insecure = insecure
        return settings

    def _run_setup(self, settings: MagicMock) -> MagicMock:
        config = TracingConfig(settings)
        with (
            patch("meraki_dashboard_exporter.core.otel_tracing.Resource.create"),
            patch("meraki_dashboard_exporter.core.otel_tracing.TracerProvider"),
            patch("meraki_dashboard_exporter.core.otel_tracing.OTLPSpanExporter") as mock_exporter,
            patch("meraki_dashboard_exporter.core.otel_tracing.BatchSpanProcessor"),
            patch("meraki_dashboard_exporter.core.otel_tracing.trace.set_tracer_provider"),
            patch("meraki_dashboard_exporter.core.otel_tracing.set_global_textmap"),
        ):
            config.setup_tracing()
        return mock_exporter

    def test_insecure_true_flows_to_exporter(self) -> None:
        """insecure=True (default) yields a non-TLS exporter channel."""
        mock_exporter = self._run_setup(self._settings(insecure=True))
        assert mock_exporter.call_args.kwargs["insecure"] is True

    def test_insecure_false_flows_to_exporter(self) -> None:
        """insecure=False yields a TLS/system-trust exporter channel."""
        mock_exporter = self._run_setup(self._settings(insecure=False))
        assert mock_exporter.call_args.kwargs["insecure"] is False


class TestTracingConfigReinitialization:
    """Test TracingConfig handles reinitialization correctly."""

    def test_setup_tracing_only_runs_once(self) -> None:
        """Test that setup_tracing is idempotent."""
        mock_settings = MagicMock(spec=Settings)
        mock_settings.otel = MagicMock()
        mock_settings.otel.ca_cert_path = None
        mock_settings.otel.client_cert_path = None
        mock_settings.otel.client_key_path = None
        mock_settings.otel.enabled = True
        mock_settings.otel.endpoint = "http://otel:4317"
        mock_settings.otel.service_name = "test-service"
        mock_settings.otel.resource_attributes = {}

        config = TracingConfig(mock_settings)

        # First setup
        with (
            patch("meraki_dashboard_exporter.core.otel_tracing.Resource.create") as mock_resource,
            patch("meraki_dashboard_exporter.core.otel_tracing.TracerProvider"),
            patch("meraki_dashboard_exporter.core.otel_tracing.OTLPSpanExporter"),
            patch("meraki_dashboard_exporter.core.otel_tracing.BatchSpanProcessor"),
            patch("meraki_dashboard_exporter.core.otel_tracing.trace.set_tracer_provider"),
            patch("meraki_dashboard_exporter.core.otel_tracing.set_global_textmap"),
        ):
            config.setup_tracing()
            first_call_count = mock_resource.call_count

            # Second setup should be skipped
            config.setup_tracing()
            assert mock_resource.call_count == first_call_count


class TestBuildOtlpCredentials:
    """#314: ``build_otlp_credentials`` is a pure helper shared by all OTLP channels."""

    def test_no_paths_returns_none(self) -> None:
        """No cert paths configured -> None (system trust store / plaintext preserved)."""
        assert build_otlp_credentials(None, None, None) is None

    def test_ca_only_builds_credentials(self, tmp_path, monkeypatch) -> None:
        """A CA-only path builds credentials with just root_certificates set."""
        ca_path = tmp_path / "ca.pem"
        ca_path.write_bytes(b"CA-PEM-BYTES")

        captured: dict[str, object] = {}

        def fake_ssl_channel_credentials(
            root_certificates=None, private_key=None, certificate_chain=None
        ):
            captured["root_certificates"] = root_certificates
            captured["private_key"] = private_key
            captured["certificate_chain"] = certificate_chain
            return "FAKE_CREDENTIALS"

        monkeypatch.setattr(
            "meraki_dashboard_exporter.core.otel_tracing.grpc.ssl_channel_credentials",
            fake_ssl_channel_credentials,
        )

        result = build_otlp_credentials(str(ca_path), None, None)

        assert result == "FAKE_CREDENTIALS"
        assert captured["root_certificates"] == b"CA-PEM-BYTES"
        assert captured["private_key"] is None
        assert captured["certificate_chain"] is None

    def test_ca_and_client_cert_and_key_builds_full_mtls_credentials(
        self, tmp_path, monkeypatch
    ) -> None:
        """CA + client cert + client key builds full mTLS credentials."""
        ca_path = tmp_path / "ca.pem"
        ca_path.write_bytes(b"CA-BYTES")
        cert_path = tmp_path / "client.crt"
        cert_path.write_bytes(b"CERT-BYTES")
        key_path = tmp_path / "client.key"
        key_path.write_bytes(b"KEY-BYTES")

        captured: dict[str, object] = {}

        def fake_ssl_channel_credentials(
            root_certificates=None, private_key=None, certificate_chain=None
        ):
            captured["root_certificates"] = root_certificates
            captured["private_key"] = private_key
            captured["certificate_chain"] = certificate_chain
            return "FAKE_MTLS_CREDENTIALS"

        monkeypatch.setattr(
            "meraki_dashboard_exporter.core.otel_tracing.grpc.ssl_channel_credentials",
            fake_ssl_channel_credentials,
        )

        result = build_otlp_credentials(str(ca_path), str(cert_path), str(key_path))

        assert result == "FAKE_MTLS_CREDENTIALS"
        assert captured["root_certificates"] == b"CA-BYTES"
        assert captured["private_key"] == b"KEY-BYTES"
        assert captured["certificate_chain"] == b"CERT-BYTES"

    def test_missing_file_raises(self, tmp_path) -> None:
        """A configured path that doesn't exist raises rather than silently no-op'ing."""
        missing = tmp_path / "does-not-exist.pem"

        with pytest.raises(OSError):
            build_otlp_credentials(str(missing), None, None)

    def test_client_cert_without_key_still_reads_only_configured_paths(
        self, tmp_path, monkeypatch
    ) -> None:
        """Only client_cert_path set (no key) -> certificate_chain set, others None.

        (XOR validation of cert/key pairing is Lane A's config-model concern;
        this helper is a pure file-reading function and does not enforce it.)
        """
        cert_path = tmp_path / "client.crt"
        cert_path.write_bytes(b"CERT-ONLY-BYTES")

        captured: dict[str, object] = {}

        def fake_ssl_channel_credentials(
            root_certificates=None, private_key=None, certificate_chain=None
        ):
            captured["root_certificates"] = root_certificates
            captured["private_key"] = private_key
            captured["certificate_chain"] = certificate_chain
            return "FAKE_CREDENTIALS"

        monkeypatch.setattr(
            "meraki_dashboard_exporter.core.otel_tracing.grpc.ssl_channel_credentials",
            fake_ssl_channel_credentials,
        )

        result = build_otlp_credentials(None, str(cert_path), None)

        assert result == "FAKE_CREDENTIALS"
        assert captured["root_certificates"] is None
        assert captured["private_key"] is None
        assert captured["certificate_chain"] == b"CERT-ONLY-BYTES"


class TestTracingConfigExporterCredentials:
    """#314: the span exporter receives ``credentials=`` built from settings cert paths."""

    def _settings(
        self,
        ca_cert_path: str | None = None,
        client_cert_path: str | None = None,
        client_key_path: str | None = None,
    ) -> MagicMock:
        settings = MagicMock(spec=Settings)
        settings.otel = MagicMock()
        settings.otel.enabled = True
        settings.otel.endpoint = "http://otel:4317"
        settings.otel.service_name = "test-service"
        settings.otel.resource_attributes = {}
        settings.otel.insecure = False
        settings.otel.ca_cert_path = ca_cert_path
        settings.otel.client_cert_path = client_cert_path
        settings.otel.client_key_path = client_key_path
        return settings

    def test_no_cert_paths_passes_none_credentials(self) -> None:
        """No cert paths configured -> exporter receives credentials=None (preserves today's behaviour)."""
        settings = self._settings()
        config = TracingConfig(settings)
        with (
            patch("meraki_dashboard_exporter.core.otel_tracing.Resource.create"),
            patch("meraki_dashboard_exporter.core.otel_tracing.TracerProvider"),
            patch("meraki_dashboard_exporter.core.otel_tracing.OTLPSpanExporter") as mock_exporter,
            patch("meraki_dashboard_exporter.core.otel_tracing.BatchSpanProcessor"),
            patch("meraki_dashboard_exporter.core.otel_tracing.trace.set_tracer_provider"),
            patch("meraki_dashboard_exporter.core.otel_tracing.set_global_textmap"),
        ):
            config.setup_tracing()

        assert mock_exporter.call_args.kwargs["credentials"] is None

    def test_cert_paths_set_passes_built_credentials(self, tmp_path) -> None:
        """Cert paths configured -> exporter receives the built ChannelCredentials object."""
        ca_path = tmp_path / "ca.pem"
        ca_path.write_bytes(b"CA-BYTES")
        settings = self._settings(ca_cert_path=str(ca_path))
        config = TracingConfig(settings)

        with (
            patch("meraki_dashboard_exporter.core.otel_tracing.Resource.create"),
            patch("meraki_dashboard_exporter.core.otel_tracing.TracerProvider"),
            patch("meraki_dashboard_exporter.core.otel_tracing.OTLPSpanExporter") as mock_exporter,
            patch("meraki_dashboard_exporter.core.otel_tracing.BatchSpanProcessor"),
            patch("meraki_dashboard_exporter.core.otel_tracing.trace.set_tracer_provider"),
            patch("meraki_dashboard_exporter.core.otel_tracing.set_global_textmap"),
        ):
            config.setup_tracing()

        credentials = mock_exporter.call_args.kwargs["credentials"]
        assert credentials is not None
        assert isinstance(credentials, grpc.ChannelCredentials)
