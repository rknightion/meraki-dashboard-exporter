"""Tests for OpenTelemetry tracing configuration.

Tests verify that tracing can be independently enabled/disabled
from OTEL metrics export.
"""

# ruff: noqa: S101

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

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
        settings.otel.tracing_enabled = True
        settings.otel.endpoint = None
        settings.otel.service_name = "test-service"
        settings.otel.resource_attributes = {}
        return settings

    def test_tracing_disabled_when_otel_not_enabled(self, mock_settings: MagicMock) -> None:
        """Test tracing is not set up when OTEL is disabled."""
        mock_settings.otel.enabled = False
        mock_settings.otel.tracing_enabled = True
        mock_settings.otel.endpoint = "http://otel:4317"

        config = TracingConfig(mock_settings)

        with patch.object(config, "_create_sampler") as mock_sampler:
            config.setup_tracing()
            mock_sampler.assert_not_called()

        assert not config._initialized

    def test_tracing_disabled_when_tracing_enabled_false(self, mock_settings: MagicMock) -> None:
        """Test tracing is not set up when tracing_enabled is False."""
        mock_settings.otel.enabled = True
        mock_settings.otel.tracing_enabled = False
        mock_settings.otel.endpoint = "http://otel:4317"

        config = TracingConfig(mock_settings)

        with patch.object(config, "_create_sampler") as mock_sampler:
            config.setup_tracing()
            mock_sampler.assert_not_called()

        assert not config._initialized

    def test_tracing_disabled_when_no_endpoint(self, mock_settings: MagicMock) -> None:
        """Test tracing is not set up when no endpoint is configured."""
        mock_settings.otel.enabled = True
        mock_settings.otel.tracing_enabled = True
        mock_settings.otel.endpoint = None

        config = TracingConfig(mock_settings)

        with patch.object(config, "_create_sampler") as mock_sampler:
            config.setup_tracing()
            mock_sampler.assert_not_called()

        assert not config._initialized

    def test_tracing_enabled_with_all_conditions_met(self, mock_settings: MagicMock) -> None:
        """Test tracing is set up when all conditions are met."""
        mock_settings.otel.enabled = True
        mock_settings.otel.tracing_enabled = True
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


class TestTracingConfigIndependentOfMetrics:
    """Test that tracing can be configured independently of metrics."""

    @pytest.fixture
    def make_settings(self, monkeypatch) -> callable:
        """Factory to create settings with various OTEL configurations."""

        def _make_settings(
            otel_enabled: bool = True,
            endpoint: str = "http://otel:4317",
            tracing_enabled: bool = True,
            export_meraki_to_otel: bool = False,
            export_exporter_to_otel: bool = False,
        ) -> Settings:
            monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
            if otel_enabled:
                monkeypatch.setenv("MERAKI_EXPORTER_OTEL__ENABLED", "true")
                monkeypatch.setenv("MERAKI_EXPORTER_OTEL__ENDPOINT", endpoint)
            else:
                monkeypatch.setenv("MERAKI_EXPORTER_OTEL__ENABLED", "false")

            monkeypatch.setenv(
                "MERAKI_EXPORTER_OTEL__TRACING_ENABLED", str(tracing_enabled).lower()
            )
            monkeypatch.setenv(
                "MERAKI_EXPORTER_OTEL__EXPORT_MERAKI_METRICS_TO_OTEL",
                str(export_meraki_to_otel).lower(),
            )
            monkeypatch.setenv(
                "MERAKI_EXPORTER_OTEL__EXPORT_EXPORTER_METRICS_TO_OTEL",
                str(export_exporter_to_otel).lower(),
            )

            return Settings()

        return _make_settings

    def test_tracing_only_mode(self, make_settings) -> None:
        """Test tracing can be enabled without OTEL metrics export."""
        settings = make_settings(
            otel_enabled=True,
            tracing_enabled=True,
            export_meraki_to_otel=False,
            export_exporter_to_otel=False,
        )

        assert settings.otel.enabled is True
        assert settings.otel.tracing_enabled is True
        assert settings.otel.export_meraki_metrics_to_otel is False
        assert settings.otel.export_exporter_metrics_to_otel is False

    def test_metrics_only_mode(self, make_settings) -> None:
        """Test OTEL metrics can be enabled without tracing."""
        settings = make_settings(
            otel_enabled=True,
            tracing_enabled=False,
            export_meraki_to_otel=True,
            export_exporter_to_otel=True,
        )

        assert settings.otel.enabled is True
        assert settings.otel.tracing_enabled is False
        assert settings.otel.export_meraki_metrics_to_otel is True
        assert settings.otel.export_exporter_metrics_to_otel is True

    def test_both_tracing_and_metrics(self, make_settings) -> None:
        """Test both tracing and OTEL metrics can be enabled."""
        settings = make_settings(
            otel_enabled=True,
            tracing_enabled=True,
            export_meraki_to_otel=True,
            export_exporter_to_otel=True,
        )

        assert settings.otel.enabled is True
        assert settings.otel.tracing_enabled is True
        assert settings.otel.export_meraki_metrics_to_otel is True
        assert settings.otel.export_exporter_metrics_to_otel is True


class TestTracingConfigReinitialization:
    """Test TracingConfig handles reinitialization correctly."""

    def test_setup_tracing_only_runs_once(self) -> None:
        """Test that setup_tracing is idempotent."""
        mock_settings = MagicMock(spec=Settings)
        mock_settings.otel = MagicMock()
        mock_settings.otel.enabled = True
        mock_settings.otel.tracing_enabled = True
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
