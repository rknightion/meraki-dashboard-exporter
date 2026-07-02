"""Tests for OpenTelemetry tracing configuration."""

# ruff: noqa: S101

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from meraki_dashboard_exporter.__version__ import get_version
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.otel_tracing import TracingConfig


class TestTracingConfigSetup:
    """Test TracingConfig setup behavior with various settings."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings with configurable OTEL options."""
        settings = MagicMock(spec=Settings)
        settings.otel = MagicMock()
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
