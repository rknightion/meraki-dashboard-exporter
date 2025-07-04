"""Base collector interface and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Info
from prometheus_client.core import REGISTRY

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

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self.api = api
        self.settings = settings
        self.registry = registry or REGISTRY
        self._metrics: dict[str, Any] = {}
        self._initialize_metrics()

    @abstractmethod
    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics."""
        ...

    @abstractmethod
    async def collect(self) -> None:
        """Collect metrics from the Meraki API."""
        ...

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


class CollectorProtocol(Protocol):
    """Protocol for metric collectors."""

    async def collect(self) -> None:
        """Collect metrics from the Meraki API."""
        ...
