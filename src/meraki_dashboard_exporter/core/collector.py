"""Base collector interface and registry."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Info
from prometheus_client.core import REGISTRY

from ..core.constants import UpdateTier
from ..core.logging import get_logger

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from .config import Settings

logger = get_logger(__name__)


class MetricCollector(ABC):
    """Abstract base class for metric collectors.

    Parameters
    ----------
    api : DashboardAPI
        Meraki Dashboard API client.
    settings : Settings
        Application settings.
    registry : CollectorRegistry | None
        Prometheus collector registry, defaults to the global registry.

    """

    # Default update tier - subclasses should override this
    update_tier: UpdateTier = UpdateTier.MEDIUM

    # Class-level performance metrics shared by all collectors
    _collector_duration: Histogram | None = None
    _collector_errors: Counter | None = None
    _collector_last_success: Gauge | None = None
    _collector_api_calls: Counter | None = None

    # Flag to ensure we initialize only once
    _metrics_initialized: bool = False

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
    ) -> None:
        """Initialize the metric collector with API client and settings."""
        self.api = api
        self.settings = settings
        self.registry = registry or REGISTRY
        self._metrics: dict[str, Any] = {}

        # Initialize performance metrics only once
        if not MetricCollector._metrics_initialized:
            MetricCollector._initialize_performance_metrics()
            MetricCollector._metrics_initialized = True

        self._initialize_metrics()

    @abstractmethod
    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics."""
        ...

    @abstractmethod
    async def _collect_impl(self) -> None:
        """Implement metric collection from the Meraki API.

        Subclasses should implement this method instead of collect().
        """
        ...

    async def collect(self) -> None:
        """Collect metrics from the Meraki API with performance tracking."""
        collector_name = self.__class__.__name__
        start_time = time.time()

        try:
            await self._collect_impl()

            # Record success
            duration = time.time() - start_time

            # Always try to record metrics (they should be initialized)
            if MetricCollector._collector_duration is not None:
                MetricCollector._collector_duration.labels(
                    collector=collector_name,
                    tier=self.update_tier.value,
                ).observe(duration)
            else:
                logger.warning("Collector duration metric not initialized")

            if MetricCollector._collector_last_success is not None:
                MetricCollector._collector_last_success.labels(
                    collector=collector_name,
                    tier=self.update_tier.value,
                ).set(time.time())
            else:
                logger.warning("Collector last success metric not initialized")

            logger.debug(
                "Collector completed successfully",
                collector=collector_name,
                tier=self.update_tier.value,
                duration=f"{duration:.2f}s",
            )

        except Exception as e:
            # Record error
            duration = time.time() - start_time

            # Always try to record metrics (they should be initialized)
            if MetricCollector._collector_errors is not None:
                MetricCollector._collector_errors.labels(
                    collector=collector_name,
                    tier=self.update_tier.value,
                    error_type=type(e).__name__,
                ).inc()
            else:
                logger.warning("Collector errors metric not initialized")

            logger.error(
                "Collector failed",
                collector=collector_name,
                tier=self.update_tier.value,
                duration=f"{duration:.2f}s",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def _create_gauge(
        self,
        name: str,
        documentation: str,
        labelnames: list[str] | None = None,
    ) -> Gauge:
        """Create and register a Gauge metric.

        Parameters
        ----------
        name : str
            Metric name.
        documentation : str
            Metric description.
        labelnames : list[str] | None
            Label names for the metric.

        Returns
        -------
        Gauge
            The created gauge metric.

        """
        gauge = Gauge(
            name,
            documentation,
            labelnames=labelnames or [],
            registry=self.registry,
        )
        self._metrics[name] = gauge
        return gauge

    def _create_counter(
        self,
        name: str,
        documentation: str,
        labelnames: list[str] | None = None,
    ) -> Counter:
        """Create and register a Counter metric.

        Parameters
        ----------
        name : str
            Metric name.
        documentation : str
            Metric description.
        labelnames : list[str] | None
            Label names for the metric.

        Returns
        -------
        Counter
            The created counter metric.

        """
        counter = Counter(
            name,
            documentation,
            labelnames=labelnames or [],
            registry=self.registry,
        )
        self._metrics[name] = counter
        return counter

    def _create_histogram(
        self,
        name: str,
        documentation: str,
        labelnames: list[str] | None = None,
        buckets: list[float] | None = None,
    ) -> Histogram:
        """Create and register a Histogram metric.

        Parameters
        ----------
        name : str
            Metric name.
        documentation : str
            Metric description.
        labelnames : list[str] | None
            Label names for the metric.
        buckets : list[float] | None
            Bucket boundaries for the histogram.

        Returns
        -------
        Histogram
            The created histogram metric.

        """
        histogram = Histogram(
            name,
            documentation,
            labelnames=labelnames or [],
            buckets=buckets or Histogram.DEFAULT_BUCKETS,
            registry=self.registry,
        )
        self._metrics[name] = histogram
        return histogram

    def _create_info(
        self,
        name: str,
        documentation: str,
        labelnames: list[str] | None = None,
    ) -> Info:
        """Create and register an Info metric.

        Parameters
        ----------
        name : str
            Metric name.
        documentation : str
            Metric description.
        labelnames : list[str] | None
            Label names for the metric.

        Returns
        -------
        Info
            The created info metric.

        """
        info = Info(
            name,
            documentation,
            labelnames=labelnames or [],
            registry=self.registry,
        )
        self._metrics[name] = info
        return info

    def _track_api_call(self, endpoint: str) -> None:
        """Track an API call for performance metrics.

        Parameters
        ----------
        endpoint : str
            The API endpoint being called.

        """
        # Always try to track (metrics should be initialized)
        if MetricCollector._collector_api_calls is not None:
            MetricCollector._collector_api_calls.labels(
                collector=self.__class__.__name__,
                tier=self.update_tier.value,
                endpoint=endpoint,
            ).inc()
        else:
            logger.warning("Collector API calls metric not initialized", endpoint=endpoint)

    @classmethod
    def _initialize_performance_metrics(cls) -> None:
        """Initialize collector performance metrics."""
        if cls._metrics_initialized:
            logger.debug("Performance metrics already initialized")
            return

        try:
            # Create metrics and assign to class attributes
            duration_metric = Histogram(
                "meraki_collector_duration_seconds",
                "Time spent collecting metrics",
                labelnames=["collector", "tier"],
                buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
                registry=REGISTRY,
            )
            cls._collector_duration = duration_metric

            errors_metric = Counter(
                "meraki_collector_errors_total",
                "Total number of collector errors",
                labelnames=["collector", "tier", "error_type"],
                registry=REGISTRY,
            )
            cls._collector_errors = errors_metric

            success_metric = Gauge(
                "meraki_collector_last_success_timestamp_seconds",
                "Unix timestamp of last successful collection",
                labelnames=["collector", "tier"],
                registry=REGISTRY,
            )
            cls._collector_last_success = success_metric

            api_calls_metric = Counter(
                "meraki_collector_api_calls_total",
                "Total number of API calls made by collectors",
                labelnames=["collector", "tier", "endpoint"],
                registry=REGISTRY,
            )
            cls._collector_api_calls = api_calls_metric

            logger.info("Successfully initialized collector performance metrics")

            # Initialize gauge values for common collectors
            # Note: We don't initialize counters as that creates _created timestamps
            for collector_name in [
                "OrganizationCollector",
                "DeviceCollector",
                "NetworkHealthCollector",
                "SensorCollector",
            ]:
                for tier in ["fast", "medium"]:
                    # Initialize gauge with 0
                    cls._collector_last_success.labels(
                        collector=collector_name,
                        tier=tier,
                    ).set(0)

            cls._metrics_initialized = True

        except ValueError as e:
            # Metrics already registered, retrieve them from registry
            if "Duplicated timeseries" in str(e) or "already registered" in str(e):
                logger.info("Performance metrics already registered, retrieving from registry")
                # Metrics are already registered, which is fine
                cls._metrics_initialized = True
            else:
                logger.error(f"Failed to initialize performance metrics: {e}")
                raise


class CollectorProtocol(Protocol):
    """Protocol for metric collectors."""

    async def collect(self) -> None:
        """Collect metrics from the Meraki API."""
        ...
