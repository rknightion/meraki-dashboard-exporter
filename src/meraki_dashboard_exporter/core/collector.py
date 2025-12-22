"""Base collector interface and registry."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Info
from prometheus_client.core import REGISTRY

from ..core.constants import UpdateTier
from ..core.error_handling import ErrorCategory
from ..core.exemplars import add_exemplar
from ..core.logging import get_logger

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ..services.inventory import OrganizationInventory
    from .config import Settings
    from .metric_expiration import MetricExpirationManager

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

    # Whether this collector is actively collecting metrics
    # Subclasses can override this based on their configuration
    @property
    def is_active(self) -> bool:
        """Check if this collector is actively collecting metrics.

        Returns
        -------
        bool
            True if the collector is active, False otherwise.

        """
        return True

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
        inventory: OrganizationInventory | None = None,
        expiration_manager: MetricExpirationManager | None = None,
    ) -> None:
        """Initialize the metric collector with API client and settings.

        Parameters
        ----------
        api : DashboardAPI
            Meraki Dashboard API client.
        settings : Settings
            Application settings.
        registry : CollectorRegistry | None
            Prometheus collector registry, defaults to the global registry.
        inventory : OrganizationInventory | None
            Shared inventory cache for org/network/device data. If not provided,
            collectors will fetch data directly from the API without caching.
        expiration_manager : MetricExpirationManager | None
            Manager for tracking and expiring stale metrics. If provided,
            the _set_metric() helper will automatically track metric updates.

        """
        self.api = api
        self.settings = settings
        self.registry = registry or REGISTRY
        self.inventory = inventory
        self.expiration_manager = expiration_manager
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
                # Record the metric value
                MetricCollector._collector_duration.labels(
                    collector=collector_name,
                    tier=self.update_tier.value,
                ).observe(duration)

                # Also try to add exemplar to link metric to trace
                # Note: This is a no-op if no trace is active
                add_exemplar(
                    MetricCollector._collector_duration,
                    value=duration,
                    labels={
                        "collector": collector_name,
                        "tier": self.update_tier.value,
                    },
                )
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
                # Record the error
                MetricCollector._collector_errors.labels(
                    collector=collector_name,
                    tier=self.update_tier.value,
                    error_type=type(e).__name__,
                ).inc()

                # Also try to add exemplar to link error metric to trace
                # Note: This is a no-op if no trace is active
                add_exemplar(
                    MetricCollector._collector_errors,
                    value=1,
                    labels={
                        "collector": collector_name,
                        "tier": self.update_tier.value,
                        "error_type": type(e).__name__,
                    },
                )
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
        # Log the API call at DEBUG level
        logger.debug(
            "API call tracked",
            collector=self.__class__.__name__,
            tier=self.update_tier.value,
            endpoint=endpoint,
        )

        # Always try to track (metrics should be initialized)
        if MetricCollector._collector_api_calls is not None:
            # Record the API call
            MetricCollector._collector_api_calls.labels(
                collector=self.__class__.__name__,
                tier=self.update_tier.value,
                endpoint=endpoint,
            ).inc()

            # Also try to add exemplar to link API call metric to trace
            # Note: This is a no-op if no trace is active
            add_exemplar(
                MetricCollector._collector_api_calls,
                value=1,
                labels={
                    "collector": self.__class__.__name__,
                    "tier": self.update_tier.value,
                    "endpoint": endpoint,
                },
            )
        else:
            logger.warning("Collector API calls metric not initialized", endpoint=endpoint)

    def _track_error(self, category: ErrorCategory) -> None:
        """Track an error for monitoring.

        Parameters
        ----------
        category : ErrorCategory
            The category of error that occurred.

        """
        if MetricCollector._collector_errors is not None:
            # Record the error
            MetricCollector._collector_errors.labels(
                collector=self.__class__.__name__,
                tier=self.update_tier.value,
                error_type=category.value,
            ).inc()

            # Also try to add exemplar to link error metric to trace
            # Note: This is a no-op if no trace is active
            add_exemplar(
                MetricCollector._collector_errors,
                value=1,
                labels={
                    "collector": self.__class__.__name__,
                    "tier": self.update_tier.value,
                    "error_type": category.value,
                },
            )

    def _track_retry(self, operation: str, reason: str) -> None:
        """Track a retry attempt for metrics.

        Parameters
        ----------
        operation : str
            The operation being retried.
        reason : str
            The reason for the retry (e.g., 'http_200_rate_limit').

        """
        # Use the existing API retry counter from the API client
        try:
            from ..api.client import AsyncMerakiClient

            if AsyncMerakiClient._api_retry_attempts is not None:
                AsyncMerakiClient._api_retry_attempts.labels(
                    endpoint=operation,
                    retry_reason=reason,
                ).inc()
        except ImportError, AttributeError:
            # Silently fail if client not available - metrics are optional
            pass

    def _set_metric_value(
        self, metric_name: str, labels: dict[str, str], value: float | None
    ) -> None:
        """Safely set a metric value with validation.

        This is a legacy helper method that accepts metric names as strings.
        It now uses `_set_metric()` internally for automatic expiration tracking.

        Parameters
        ----------
        metric_name : str
            Name of the metric attribute.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float | None
            Value to set. If None, the metric will not be updated.

        """
        # Skip if value is None - this happens when API returns null values
        if value is None:
            logger.debug(
                "Skipping metric update due to None value",
                metric_name=metric_name,
                labels=labels,
            )
            return

        metric = getattr(self, metric_name, None)
        if metric is None:
            logger.debug(
                "Metric not available",
                metric_name=metric_name,
            )
            return

        # Use _set_metric() for automatic expiration tracking (Phase 3.2.3)
        # Only works with Gauge metrics (Counter doesn't have .set() method)
        if isinstance(metric, Gauge):
            # Extract full metric name from metric object
            full_metric_name = getattr(metric, "_name", None)
            if full_metric_name:
                # Use new helper with expiration tracking
                self._set_metric(metric, labels, value, full_metric_name)
            else:
                # Fallback to direct set if we can't get metric name
                try:
                    metric.labels(**labels).set(value)
                    logger.debug(
                        "Set metric value (no expiration tracking - no name)",
                        metric_name=metric_name,
                        labels=labels,
                        value=value,
                    )
                except Exception:
                    logger.exception(
                        "Failed to set metric value",
                        metric_name=metric_name,
                        labels=labels,
                        value=value,
                    )
        else:
            # Non-Gauge metric (e.g., Counter) - use direct set without expiration
            try:
                metric.labels(**labels).set(value)
                logger.debug(
                    "Set metric value (no expiration tracking - not a Gauge)",
                    metric_name=metric_name,
                    labels=labels,
                    value=value,
                )
            except Exception:
                logger.exception(
                    "Failed to set metric value",
                    metric_name=metric_name,
                    labels=labels,
                    value=value,
                )

    def _set_metric(
        self,
        metric: Gauge,
        labels: dict[str, str],
        value: float,
        metric_name: str | None = None,
    ) -> None:
        """Set a metric value with automatic expiration tracking (Phase 3.2).

        This helper automatically tracks metric updates with the expiration manager
        when available. Use this instead of calling metric.labels().set() directly
        to enable automatic metric lifecycle management.

        Parameters
        ----------
        metric : Gauge
            The Gauge metric object to update.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float
            Value to set.
        metric_name : str | None
            Full metric name (e.g., "meraki_device_up"). If not provided,
            will attempt to extract from metric object.

        Examples
        --------
        >>> self._set_metric(
        ...     self.device_up,
        ...     {"org_id": "123", "serial": "ABC"},
        ...     1.0,
        ...     "meraki_device_up"
        ... )

        """
        try:
            # Set the metric value
            metric.labels(**labels).set(value)

            # Track for expiration if manager is available
            if self.expiration_manager:
                # Get metric name if not provided
                if metric_name is None:
                    metric_name = getattr(metric, "_name", "unknown")

                # Track the update
                self.expiration_manager.track_metric_update(
                    collector_name=self.__class__.__name__,
                    metric_name=metric_name,
                    label_values=labels,
                )

        except Exception:
            logger.exception(
                "Failed to set metric with tracking",
                metric_name=metric_name or "unknown",
                labels=labels,
                value=value,
            )

    @classmethod
    def _initialize_performance_metrics(cls) -> None:
        """Initialize collector performance metrics."""
        if cls._metrics_initialized:
            logger.debug("Performance metrics already initialized")
            return

        try:
            # Create metrics and assign to class attributes
            duration_metric = Histogram(
                "meraki_exporter_collector_duration_seconds",
                "Time spent collecting metrics",
                labelnames=["collector", "tier"],
                buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
                registry=REGISTRY,
            )
            cls._collector_duration = duration_metric

            errors_metric = Counter(
                "meraki_exporter_collector_errors_total",
                "Total number of collector errors",
                labelnames=["collector", "tier", "error_type"],
                registry=REGISTRY,
            )
            cls._collector_errors = errors_metric

            success_metric = Gauge(
                "meraki_exporter_collector_success_timestamp_seconds",
                "Unix timestamp of last successful collection",
                labelnames=["collector", "tier"],
                registry=REGISTRY,
            )
            cls._collector_last_success = success_metric

            api_calls_metric = Counter(
                "meraki_exporter_collector_api_calls_total",
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
                "MTSensorCollector",
                "AlertsCollector",
                "ConfigCollector",
            ]:
                for tier in ["fast", "medium", "slow"]:
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
