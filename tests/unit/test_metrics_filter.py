"""Tests for metrics filtering and OTEL export routing.

This module tests all runtime modes for metrics export:
- Mode 1 (Default): Prometheus for all metrics
- Mode 2: Prometheus for Meraki metrics only
- Mode 3: OTEL only for all metrics
- Mode 4: OTEL for internal metrics + Prometheus for Meraki
- Dual export: Metrics to both Prometheus and OTEL
- Tracing control: Independent enable/disable
"""

# ruff: noqa: S101

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry, Counter, Gauge

from meraki_dashboard_exporter.core.config_models import OTelSettings
from meraki_dashboard_exporter.core.metrics_filter import FilteredRegistry, MetricsFilter


class TestMetricsFilterClassification:
    """Test metric classification by prefix."""

    def test_is_exporter_metric_with_exporter_prefix(self) -> None:
        """Test that meraki_exporter_* metrics are identified as exporter metrics."""
        assert MetricsFilter.is_exporter_metric("meraki_exporter_api_duration_seconds")
        assert MetricsFilter.is_exporter_metric("meraki_exporter_collector_errors_total")
        assert MetricsFilter.is_exporter_metric("meraki_exporter_cache_hits_total")

    def test_is_exporter_metric_with_meraki_prefix(self) -> None:
        """Test that meraki_* (non-exporter) metrics are NOT exporter metrics."""
        assert not MetricsFilter.is_exporter_metric("meraki_device_up")
        assert not MetricsFilter.is_exporter_metric("meraki_network_clients_total")
        assert not MetricsFilter.is_exporter_metric("meraki_switch_port_status")

    def test_is_exporter_metric_with_other_prefix(self) -> None:
        """Test that non-meraki metrics are NOT exporter metrics."""
        assert not MetricsFilter.is_exporter_metric("python_gc_objects_collected_total")
        assert not MetricsFilter.is_exporter_metric("process_cpu_seconds_total")

    def test_is_meraki_metric_with_meraki_prefix(self) -> None:
        """Test that meraki_* (non-exporter) metrics are Meraki metrics."""
        assert MetricsFilter.is_meraki_metric("meraki_device_up")
        assert MetricsFilter.is_meraki_metric("meraki_network_clients_total")
        assert MetricsFilter.is_meraki_metric("meraki_switch_port_status")

    def test_is_meraki_metric_excludes_exporter(self) -> None:
        """Test that meraki_exporter_* metrics are NOT Meraki metrics."""
        assert not MetricsFilter.is_meraki_metric("meraki_exporter_api_duration_seconds")
        assert not MetricsFilter.is_meraki_metric("meraki_exporter_collector_errors_total")

    def test_is_meraki_metric_with_other_prefix(self) -> None:
        """Test that non-meraki metrics are NOT Meraki metrics."""
        assert not MetricsFilter.is_meraki_metric("python_gc_objects_collected_total")
        assert not MetricsFilter.is_meraki_metric("process_cpu_seconds_total")


class TestMode1DefaultPrometheusAll:
    """Test Mode 1: Prometheus for all metrics (default configuration)."""

    @pytest.fixture
    def settings(self) -> OTelSettings:
        """Create default settings (Mode 1)."""
        return OTelSettings(
            enabled=False,
            export_meraki_metrics_to_prometheus=True,
            export_exporter_metrics_to_prometheus=True,
            export_meraki_metrics_to_otel=False,
            export_exporter_metrics_to_otel=False,
        )

    def test_meraki_metrics_exported_to_prometheus(self, settings: OTelSettings) -> None:
        """Test Meraki network metrics are exported to Prometheus."""
        assert MetricsFilter.should_export_to_prometheus("meraki_device_up", settings)
        assert MetricsFilter.should_export_to_prometheus("meraki_network_clients_total", settings)

    def test_exporter_metrics_exported_to_prometheus(self, settings: OTelSettings) -> None:
        """Test exporter internal metrics are exported to Prometheus."""
        assert MetricsFilter.should_export_to_prometheus(
            "meraki_exporter_api_duration_seconds", settings
        )
        assert MetricsFilter.should_export_to_prometheus(
            "meraki_exporter_collector_errors_total", settings
        )

    def test_python_metrics_exported_to_prometheus(self, settings: OTelSettings) -> None:
        """Test Python runtime metrics are always exported to Prometheus."""
        assert MetricsFilter.should_export_to_prometheus(
            "python_gc_objects_collected_total", settings
        )
        assert MetricsFilter.should_export_to_prometheus("process_cpu_seconds_total", settings)

    def test_no_metrics_exported_to_otel(self, settings: OTelSettings) -> None:
        """Test no metrics are exported to OTEL in default mode."""
        assert not MetricsFilter.should_export_to_otel("meraki_device_up", settings)
        assert not MetricsFilter.should_export_to_otel(
            "meraki_exporter_api_duration_seconds", settings
        )

    def test_otel_allowlist_is_none(self, settings: OTelSettings) -> None:
        """Test OTEL allowlist is None when nothing exported to OTEL."""
        assert MetricsFilter.get_otel_allowlist(settings) is None

    def test_otel_blocklist_is_none(self, settings: OTelSettings) -> None:
        """Test OTEL blocklist is None when nothing exported to OTEL."""
        assert MetricsFilter.get_otel_blocklist(settings) is None


class TestMode2PrometheusMerakiOnly:
    """Test Mode 2: Prometheus for Meraki metrics only (hide exporter internals)."""

    @pytest.fixture
    def settings(self) -> OTelSettings:
        """Create Mode 2 settings."""
        return OTelSettings(
            enabled=False,
            export_meraki_metrics_to_prometheus=True,
            export_exporter_metrics_to_prometheus=False,
            export_meraki_metrics_to_otel=False,
            export_exporter_metrics_to_otel=False,
        )

    def test_meraki_metrics_exported_to_prometheus(self, settings: OTelSettings) -> None:
        """Test Meraki network metrics are exported to Prometheus."""
        assert MetricsFilter.should_export_to_prometheus("meraki_device_up", settings)
        assert MetricsFilter.should_export_to_prometheus("meraki_network_clients_total", settings)

    def test_exporter_metrics_not_exported_to_prometheus(self, settings: OTelSettings) -> None:
        """Test exporter internal metrics are NOT exported to Prometheus."""
        assert not MetricsFilter.should_export_to_prometheus(
            "meraki_exporter_api_duration_seconds", settings
        )
        assert not MetricsFilter.should_export_to_prometheus(
            "meraki_exporter_collector_errors_total", settings
        )

    def test_python_metrics_still_exported(self, settings: OTelSettings) -> None:
        """Test Python runtime metrics are still exported to Prometheus."""
        assert MetricsFilter.should_export_to_prometheus(
            "python_gc_objects_collected_total", settings
        )


class TestMode3OtelOnlyAll:
    """Test Mode 3: OTEL only for all metrics."""

    @pytest.fixture
    def settings(self) -> OTelSettings:
        """Create Mode 3 settings."""
        return OTelSettings(
            enabled=True,
            endpoint="http://otel-collector:4317",
            export_meraki_metrics_to_prometheus=False,
            export_exporter_metrics_to_prometheus=False,
            export_meraki_metrics_to_otel=True,
            export_exporter_metrics_to_otel=True,
        )

    def test_meraki_metrics_not_exported_to_prometheus(self, settings: OTelSettings) -> None:
        """Test Meraki network metrics are NOT exported to Prometheus."""
        assert not MetricsFilter.should_export_to_prometheus("meraki_device_up", settings)
        assert not MetricsFilter.should_export_to_prometheus(
            "meraki_network_clients_total", settings
        )

    def test_exporter_metrics_not_exported_to_prometheus(self, settings: OTelSettings) -> None:
        """Test exporter internal metrics are NOT exported to Prometheus."""
        assert not MetricsFilter.should_export_to_prometheus(
            "meraki_exporter_api_duration_seconds", settings
        )

    def test_python_metrics_still_exported_to_prometheus(self, settings: OTelSettings) -> None:
        """Test Python runtime metrics are ALWAYS exported to Prometheus."""
        assert MetricsFilter.should_export_to_prometheus(
            "python_gc_objects_collected_total", settings
        )

    def test_meraki_metrics_exported_to_otel(self, settings: OTelSettings) -> None:
        """Test Meraki network metrics are exported to OTEL."""
        assert MetricsFilter.should_export_to_otel("meraki_device_up", settings)
        assert MetricsFilter.should_export_to_otel("meraki_network_clients_total", settings)

    def test_exporter_metrics_exported_to_otel(self, settings: OTelSettings) -> None:
        """Test exporter internal metrics are exported to OTEL."""
        assert MetricsFilter.should_export_to_otel("meraki_exporter_api_duration_seconds", settings)

    def test_python_metrics_not_exported_to_otel(self, settings: OTelSettings) -> None:
        """Test Python runtime metrics are NOT exported to OTEL."""
        assert not MetricsFilter.should_export_to_otel(
            "python_gc_objects_collected_total", settings
        )

    def test_otel_allowlist_includes_both_prefixes(self, settings: OTelSettings) -> None:
        """Test OTEL allowlist includes both meraki_ and meraki_exporter_ prefixes."""
        allowlist = MetricsFilter.get_otel_allowlist(settings)
        assert allowlist is not None
        assert "meraki_" in allowlist
        assert "meraki_exporter_" in allowlist

    def test_otel_blocklist_is_none(self, settings: OTelSettings) -> None:
        """Test OTEL blocklist is None when both metric types are exported."""
        assert MetricsFilter.get_otel_blocklist(settings) is None


class TestMode4OtelInternalPrometheusmeraki:
    """Test Mode 4: OTEL for internal metrics + Prometheus for Meraki."""

    @pytest.fixture
    def settings(self) -> OTelSettings:
        """Create Mode 4 settings."""
        return OTelSettings(
            enabled=True,
            endpoint="http://otel-collector:4317",
            export_meraki_metrics_to_prometheus=True,
            export_exporter_metrics_to_prometheus=False,
            export_meraki_metrics_to_otel=False,
            export_exporter_metrics_to_otel=True,
        )

    def test_meraki_metrics_exported_to_prometheus(self, settings: OTelSettings) -> None:
        """Test Meraki network metrics are exported to Prometheus."""
        assert MetricsFilter.should_export_to_prometheus("meraki_device_up", settings)

    def test_exporter_metrics_not_exported_to_prometheus(self, settings: OTelSettings) -> None:
        """Test exporter internal metrics are NOT exported to Prometheus."""
        assert not MetricsFilter.should_export_to_prometheus(
            "meraki_exporter_api_duration_seconds", settings
        )

    def test_meraki_metrics_not_exported_to_otel(self, settings: OTelSettings) -> None:
        """Test Meraki network metrics are NOT exported to OTEL."""
        assert not MetricsFilter.should_export_to_otel("meraki_device_up", settings)

    def test_exporter_metrics_exported_to_otel(self, settings: OTelSettings) -> None:
        """Test exporter internal metrics are exported to OTEL."""
        assert MetricsFilter.should_export_to_otel("meraki_exporter_api_duration_seconds", settings)

    def test_otel_allowlist_includes_exporter_only(self, settings: OTelSettings) -> None:
        """Test OTEL allowlist includes only exporter prefix."""
        allowlist = MetricsFilter.get_otel_allowlist(settings)
        assert allowlist is not None
        assert "meraki_exporter_" in allowlist
        # Should still include meraki_ prefix since it's a substring
        # The blocklist handles the exclusion of non-exporter meraki metrics


class TestDualExport:
    """Test dual export: metrics to both Prometheus and OTEL."""

    @pytest.fixture
    def settings(self) -> OTelSettings:
        """Create dual export settings."""
        return OTelSettings(
            enabled=True,
            endpoint="http://otel-collector:4317",
            export_meraki_metrics_to_prometheus=True,
            export_meraki_metrics_to_otel=True,
            export_exporter_metrics_to_prometheus=True,
            export_exporter_metrics_to_otel=True,
        )

    def test_meraki_metrics_exported_to_both(self, settings: OTelSettings) -> None:
        """Test Meraki metrics are exported to both Prometheus and OTEL."""
        assert MetricsFilter.should_export_to_prometheus("meraki_device_up", settings)
        assert MetricsFilter.should_export_to_otel("meraki_device_up", settings)

    def test_exporter_metrics_exported_to_both(self, settings: OTelSettings) -> None:
        """Test exporter metrics are exported to both Prometheus and OTEL."""
        assert MetricsFilter.should_export_to_prometheus(
            "meraki_exporter_api_duration_seconds", settings
        )
        assert MetricsFilter.should_export_to_otel("meraki_exporter_api_duration_seconds", settings)


class TestTracingControl:
    """Test tracing enable/disable independent of metrics."""

    def test_tracing_enabled_by_default(self) -> None:
        """Test tracing is enabled by default when OTEL is enabled."""
        settings = OTelSettings(
            enabled=True,
            endpoint="http://otel-collector:4317",
        )
        assert settings.tracing_enabled is True

    def test_tracing_can_be_disabled(self) -> None:
        """Test tracing can be disabled while OTEL metrics are enabled."""
        settings = OTelSettings(
            enabled=True,
            endpoint="http://otel-collector:4317",
            tracing_enabled=False,
            export_meraki_metrics_to_otel=True,
        )
        assert settings.tracing_enabled is False
        assert settings.export_meraki_metrics_to_otel is True

    def test_tracing_only_mode(self) -> None:
        """Test tracing only mode (metrics via Prometheus, traces via OTEL)."""
        settings = OTelSettings(
            enabled=True,
            endpoint="http://otel-collector:4317",
            tracing_enabled=True,
            export_meraki_metrics_to_prometheus=True,
            export_exporter_metrics_to_prometheus=True,
            export_meraki_metrics_to_otel=False,
            export_exporter_metrics_to_otel=False,
        )
        assert settings.tracing_enabled is True
        assert MetricsFilter.should_export_to_prometheus("meraki_device_up", settings)
        assert not MetricsFilter.should_export_to_otel("meraki_device_up", settings)


class TestOtelAllowlistBlocklist:
    """Test OTEL allowlist and blocklist generation."""

    def test_allowlist_meraki_only(self) -> None:
        """Test allowlist with only Meraki metrics to OTEL."""
        settings = OTelSettings(
            enabled=True,
            endpoint="http://otel-collector:4317",
            export_meraki_metrics_to_otel=True,
            export_exporter_metrics_to_otel=False,
        )
        allowlist = MetricsFilter.get_otel_allowlist(settings)
        assert allowlist is not None
        assert "meraki_" in allowlist

    def test_allowlist_exporter_only(self) -> None:
        """Test allowlist with only exporter metrics to OTEL."""
        settings = OTelSettings(
            enabled=True,
            endpoint="http://otel-collector:4317",
            export_meraki_metrics_to_otel=False,
            export_exporter_metrics_to_otel=True,
        )
        allowlist = MetricsFilter.get_otel_allowlist(settings)
        assert allowlist is not None
        assert "meraki_exporter_" in allowlist

    def test_blocklist_when_meraki_not_exporter(self) -> None:
        """Test blocklist excludes exporter when only meraki metrics exported."""
        settings = OTelSettings(
            enabled=True,
            endpoint="http://otel-collector:4317",
            export_meraki_metrics_to_otel=True,
            export_exporter_metrics_to_otel=False,
        )
        blocklist = MetricsFilter.get_otel_blocklist(settings)
        assert blocklist is not None
        assert "meraki_exporter_" in blocklist


class TestFilteredRegistry:
    """Test FilteredRegistry with real Prometheus metrics."""

    @pytest.fixture
    def registry(self) -> CollectorRegistry:
        """Create a fresh registry with test metrics."""
        registry = CollectorRegistry()

        # Create Meraki network metrics
        Gauge(
            "meraki_device_up",
            "Device up status",
            labelnames=["serial"],
            registry=registry,
        ).labels(serial="Q2XX-1234").set(1)

        # Create exporter internal metrics
        Counter(
            "meraki_exporter_api_requests_total",
            "Total API requests",
            labelnames=["endpoint"],
            registry=registry,
        ).labels(endpoint="getDevices").inc()

        return registry

    def test_mode1_returns_all_metrics(self, registry: CollectorRegistry) -> None:
        """Test Mode 1 returns all metrics."""
        settings = OTelSettings(
            enabled=False,
            export_meraki_metrics_to_prometheus=True,
            export_exporter_metrics_to_prometheus=True,
        )
        filtered = FilteredRegistry(registry, settings)
        metrics = list(filtered.collect())

        metric_names = [m.name for m in metrics]
        assert "meraki_device_up" in metric_names
        assert "meraki_exporter_api_requests" in metric_names

    def test_mode2_excludes_exporter_metrics(self, registry: CollectorRegistry) -> None:
        """Test Mode 2 excludes exporter metrics."""
        settings = OTelSettings(
            enabled=False,
            export_meraki_metrics_to_prometheus=True,
            export_exporter_metrics_to_prometheus=False,
        )
        filtered = FilteredRegistry(registry, settings)
        metrics = list(filtered.collect())

        metric_names = [m.name for m in metrics]
        assert "meraki_device_up" in metric_names
        assert "meraki_exporter_api_requests" not in metric_names

    def test_mode3_excludes_meraki_metrics(self, registry: CollectorRegistry) -> None:
        """Test Mode 3 excludes Meraki network metrics from Prometheus."""
        settings = OTelSettings(
            enabled=True,
            endpoint="http://otel-collector:4317",
            export_meraki_metrics_to_prometheus=False,
            export_exporter_metrics_to_prometheus=False,
        )
        filtered = FilteredRegistry(registry, settings)
        metrics = list(filtered.collect())

        metric_names = [m.name for m in metrics]
        assert "meraki_device_up" not in metric_names
        assert "meraki_exporter_api_requests" not in metric_names


class TestOtelSettingsValidation:
    """Test OTelSettings validation rules."""

    def test_otel_enabled_requires_endpoint(self) -> None:
        """Test that enabling OTEL requires an endpoint."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            OTelSettings(enabled=True)

        assert "OTEL endpoint must be provided" in str(exc_info.value)

    def test_otel_disabled_does_not_require_endpoint(self) -> None:
        """Test that disabled OTEL does not require an endpoint."""
        settings = OTelSettings(enabled=False)
        assert settings.endpoint is None

    def test_default_export_settings(self) -> None:
        """Test default export settings are correct."""
        settings = OTelSettings(enabled=False)

        # By default, all metrics go to Prometheus
        assert settings.export_meraki_metrics_to_prometheus is True
        assert settings.export_exporter_metrics_to_prometheus is True

        # By default, no metrics go to OTEL
        assert settings.export_meraki_metrics_to_otel is False
        assert settings.export_exporter_metrics_to_otel is False

        # By default, tracing is enabled (if OTEL is enabled)
        assert settings.tracing_enabled is True

    def test_all_settings_can_be_configured(self) -> None:
        """Test all export settings can be independently configured."""
        settings = OTelSettings(
            enabled=True,
            endpoint="http://otel-collector:4317",
            export_meraki_metrics_to_prometheus=False,
            export_exporter_metrics_to_prometheus=True,
            export_meraki_metrics_to_otel=True,
            export_exporter_metrics_to_otel=False,
            tracing_enabled=False,
        )

        assert settings.export_meraki_metrics_to_prometheus is False
        assert settings.export_exporter_metrics_to_prometheus is True
        assert settings.export_meraki_metrics_to_otel is True
        assert settings.export_exporter_metrics_to_otel is False
        assert settings.tracing_enabled is False


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_metric_name(self) -> None:
        """Test handling of empty metric name."""
        assert not MetricsFilter.is_exporter_metric("")
        assert not MetricsFilter.is_meraki_metric("")

    def test_partial_prefix_match(self) -> None:
        """Test that partial prefix matches don't cause false positives."""
        # "meraki" without underscore should not match
        assert not MetricsFilter.is_meraki_metric("meraki")
        assert not MetricsFilter.is_exporter_metric("meraki_exporter")

    def test_case_sensitivity(self) -> None:
        """Test that prefix matching is case-sensitive."""
        assert not MetricsFilter.is_meraki_metric("MERAKI_device_up")
        assert not MetricsFilter.is_exporter_metric("MERAKI_EXPORTER_api_calls")

    def test_metrics_with_similar_prefixes(self) -> None:
        """Test metrics with similar but different prefixes."""
        # These should be classified as Meraki metrics (they start with meraki_)
        assert MetricsFilter.is_meraki_metric("meraki_device_status")
        assert MetricsFilter.is_meraki_metric("meraki_network_health")

        # Make sure exporter prefix is properly distinguished from regular meraki
        assert MetricsFilter.is_exporter_metric("meraki_exporter_test")
        assert not MetricsFilter.is_meraki_metric("meraki_exporter_test")

        # Non-meraki metrics should not match either
        assert not MetricsFilter.is_meraki_metric("prometheus_http_requests")
        assert not MetricsFilter.is_exporter_metric("prometheus_http_requests")
