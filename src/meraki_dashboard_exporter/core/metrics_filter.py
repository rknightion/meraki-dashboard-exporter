"""Metrics filtering utilities for Prometheus and OTEL export routing.

This module provides utilities for filtering metrics based on their prefix
and configuration settings. It allows routing different metric types to
different export destinations (Prometheus, OpenTelemetry, or both).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from prometheus_client.core import Metric

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry

    from .config_models import OTelSettings


class MetricsFilter:
    """Utility for filtering metrics based on prefix and configuration.

    Metrics are classified into two categories based on their prefix:
    - Exporter metrics: `meraki_exporter_*` - internal metrics about exporter performance
    - Meraki metrics: `meraki_*` (excluding exporter) - Meraki network data metrics

    Examples
    --------
    >>> from meraki_dashboard_exporter.core.metrics_filter import MetricsFilter
    >>> MetricsFilter.is_exporter_metric("meraki_exporter_api_duration_seconds")
    True
    >>> MetricsFilter.is_meraki_metric("meraki_device_up")
    True
    >>> MetricsFilter.is_exporter_metric("meraki_device_up")
    False

    """

    EXPORTER_PREFIX = "meraki_exporter_"
    MERAKI_PREFIX = "meraki_"

    @staticmethod
    def is_exporter_metric(name: str) -> bool:
        """Check if metric is an internal exporter metric.

        Parameters
        ----------
        name : str
            The metric name to check.

        Returns
        -------
        bool
            True if the metric starts with 'meraki_exporter_'.

        """
        return name.startswith(MetricsFilter.EXPORTER_PREFIX)

    @staticmethod
    def is_meraki_metric(name: str) -> bool:
        """Check if metric is a Meraki network metric.

        Parameters
        ----------
        name : str
            The metric name to check.

        Returns
        -------
        bool
            True if the metric starts with 'meraki_' but not 'meraki_exporter_'.

        """
        return name.startswith(MetricsFilter.MERAKI_PREFIX) and not name.startswith(
            MetricsFilter.EXPORTER_PREFIX
        )

    @staticmethod
    def should_export_to_prometheus(name: str, settings: OTelSettings) -> bool:
        """Determine if metric should be exported to Prometheus.

        Parameters
        ----------
        name : str
            The metric name to check.
        settings : OTelSettings
            The OTEL settings containing export configuration.

        Returns
        -------
        bool
            True if the metric should be included in the Prometheus /metrics endpoint.

        """
        if MetricsFilter.is_exporter_metric(name):
            return settings.export_exporter_metrics_to_prometheus
        elif MetricsFilter.is_meraki_metric(name):
            return settings.export_meraki_metrics_to_prometheus
        # Non-meraki metrics (e.g., python_* from prometheus_client) always exported
        return True

    @staticmethod
    def should_export_to_otel(name: str, settings: OTelSettings) -> bool:
        """Determine if metric should be exported to OpenTelemetry.

        Parameters
        ----------
        name : str
            The metric name to check.
        settings : OTelSettings
            The OTEL settings containing export configuration.

        Returns
        -------
        bool
            True if the metric should be exported to OpenTelemetry collector.

        """
        if MetricsFilter.is_exporter_metric(name):
            return settings.export_exporter_metrics_to_otel
        elif MetricsFilter.is_meraki_metric(name):
            return settings.export_meraki_metrics_to_otel
        # Non-meraki metrics not exported to OTEL by default
        return False

    @staticmethod
    def get_otel_allowlist(settings: OTelSettings) -> list[str] | None:
        """Get the metric allowlist for OTEL export based on settings.

        Parameters
        ----------
        settings : OTelSettings
            The OTEL settings containing export configuration.

        Returns
        -------
        list[str] | None
            List of metric prefixes to allow, or None if no filtering needed.

        """
        allowlist: list[str] = []

        if settings.export_meraki_metrics_to_otel:
            allowlist.append(MetricsFilter.MERAKI_PREFIX)
        if settings.export_exporter_metrics_to_otel:
            allowlist.append(MetricsFilter.EXPORTER_PREFIX)

        return allowlist if allowlist else None

    @staticmethod
    def get_otel_blocklist(settings: OTelSettings) -> list[str] | None:
        """Get the metric blocklist for OTEL export based on settings.

        Parameters
        ----------
        settings : OTelSettings
            The OTEL settings containing export configuration.

        Returns
        -------
        list[str] | None
            List of metric prefixes to block, or None if no blocking needed.

        """
        blocklist: list[str] = []

        # If exporting meraki but not exporter metrics, block exporter prefix
        if settings.export_meraki_metrics_to_otel and not settings.export_exporter_metrics_to_otel:
            blocklist.append(MetricsFilter.EXPORTER_PREFIX)

        return blocklist if blocklist else None


class FilteredRegistry:
    """A registry wrapper that filters metrics based on OTelSettings.

    This class wraps a Prometheus CollectorRegistry and filters the metrics
    returned by collect() based on the export configuration in OTelSettings.

    Parameters
    ----------
    base_registry : CollectorRegistry
        The underlying Prometheus registry to wrap.
    settings : OTelSettings
        The OTEL settings containing export configuration.

    Examples
    --------
    >>> from prometheus_client import REGISTRY
    >>> from meraki_dashboard_exporter.core.config_models import OTelSettings
    >>> settings = OTelSettings(export_exporter_metrics_to_prometheus=False)
    >>> filtered = FilteredRegistry(REGISTRY, settings)
    >>> for metric_family in filtered.collect():
    ...     # Only returns metrics that should be exported to Prometheus
    ...     pass

    """

    def __init__(self, base_registry: CollectorRegistry, settings: OTelSettings) -> None:
        """Initialize the filtered registry."""
        self._base_registry = base_registry
        self._settings = settings

    def collect(self) -> Iterator[Metric]:
        """Collect and filter metrics based on configuration.

        Yields
        ------
        Metric
            Metric families that should be exported to Prometheus.

        """
        for metric_family in self._base_registry.collect():
            if MetricsFilter.should_export_to_prometheus(metric_family.name, self._settings):
                yield metric_family
