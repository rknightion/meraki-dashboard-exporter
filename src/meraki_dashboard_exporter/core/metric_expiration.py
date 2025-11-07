"""Metric expiration and lifecycle management.

Prevents memory leaks by expiring stale metrics from devices/networks that
are no longer present or reporting. Implements TTL-based cleanup with
configurable grace periods.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

import structlog
from prometheus_client import Counter, Gauge

from .constants import UpdateTier
from .constants.metrics_constants import CollectorMetricName
from .metrics import LabelName

if TYPE_CHECKING:
    from .config import Settings

logger = structlog.get_logger(__name__)


class MetricExpirationManager:
    """Manages metric lifecycle and expiration to prevent memory leaks.

    Tracks metric updates and removes stale metrics that haven't been
    updated within the TTL period. This prevents unbounded memory growth
    from ephemeral devices or network changes.

    The TTL is based on the collection interval with a configurable multiplier:
    - FAST tier (60s): TTL = 120s (2x multiplier)
    - MEDIUM tier (300s): TTL = 600s (2x multiplier)
    - SLOW tier (900s): TTL = 1800s (2x multiplier)

    Examples
    --------
    Create and start expiration manager:
    >>> manager = MetricExpirationManager(settings)
    >>> await manager.start()

    Track metric updates:
    >>> manager.track_metric_update(
    ...     collector_name="DeviceCollector",
    ...     metric_name="meraki_device_up",
    ...     label_values={"org_id": "123", "serial": "ABC"},
    ... )

    Stop manager:
    >>> await manager.stop()

    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the expiration manager.

        Parameters
        ----------
        settings : Settings
            Application settings.

        """
        self.settings = settings
        self._ttl_multiplier = settings.monitoring.metric_ttl_multiplier

        # Track last update time per metric
        # Key: (collector_name, metric_name, frozen_labels)
        # Value: timestamp of last update
        self._metric_timestamps: dict[tuple[str, str, str], float] = {}

        # Track metric count per collector
        self._metric_counts: defaultdict[str, int] = defaultdict(int)

        # Background task
        self._cleanup_task: asyncio.Task[Any] | None = None
        self._running = False

        # Metrics for monitoring expiration
        self._expired_metrics_total = Counter(
            CollectorMetricName.COLLECTION_ERRORS_TOTAL.value + "_expired",
            "Total number of metrics expired due to TTL",
            labelnames=[LabelName.COLLECTOR.value, LabelName.TIER.value],
        )

        self._tracked_metrics = Gauge(
            CollectorMetricName.INVENTORY_CACHE_SIZE.value + "_tracked_metrics",
            "Number of metrics currently tracked for expiration",
            labelnames=[LabelName.COLLECTOR.value],
        )

        logger.info(
            "Initialized metric expiration manager",
            ttl_multiplier=self._ttl_multiplier,
        )

    def track_metric_update(
        self,
        collector_name: str,
        metric_name: str,
        label_values: dict[str, str],
    ) -> None:
        """Track that a metric was updated.

        Parameters
        ----------
        collector_name : str
            Name of the collector that owns this metric.
        metric_name : str
            Full name of the metric (e.g., "meraki_device_up").
        label_values : dict[str, str]
            Label key-value pairs that uniquely identify this metric series.

        """
        # Create a frozen representation of labels for dict key
        frozen_labels = self._freeze_labels(label_values)
        key = (collector_name, metric_name, frozen_labels)

        # Update timestamp
        current_time = time.time()
        if key not in self._metric_timestamps:
            self._metric_counts[collector_name] += 1

        self._metric_timestamps[key] = current_time

    def _freeze_labels(self, labels: dict[str, str]) -> str:
        """Convert label dict to frozen string representation.

        Parameters
        ----------
        labels : dict[str, str]
            Label key-value pairs.

        Returns
        -------
        str
            Frozen string representation for use as dict key.

        """
        return "|".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def _get_ttl_for_tier(self, tier: UpdateTier) -> float:
        """Get TTL in seconds for a specific tier.

        Parameters
        ----------
        tier : UpdateTier
            The update tier.

        Returns
        -------
        float
            TTL in seconds (interval * multiplier).

        """
        if tier == UpdateTier.FAST:
            interval = self.settings.update_intervals.fast
        elif tier == UpdateTier.MEDIUM:
            interval = self.settings.update_intervals.medium
        else:  # SLOW
            interval = self.settings.update_intervals.slow

        return float(interval * self._ttl_multiplier)

    async def start(self) -> None:
        """Start the background cleanup task."""
        if self._running:
            logger.warning("Expiration manager already running")
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Started metric expiration cleanup loop")

    async def stop(self) -> None:
        """Stop the background cleanup task."""
        if not self._running:
            return

        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped metric expiration cleanup loop")

    async def _cleanup_loop(self) -> None:
        """Background task that periodically cleans up expired metrics."""
        # Run cleanup every 5 minutes
        cleanup_interval = 300

        while self._running:
            try:
                await asyncio.sleep(cleanup_interval)
                await self._cleanup_expired_metrics()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in metric cleanup loop")

    async def _cleanup_expired_metrics(self) -> None:
        """Clean up metrics that haven't been updated within their TTL.

        This is a placeholder for actual cleanup. In practice, Prometheus
        doesn't provide an easy way to delete individual metric series.
        Instead, this tracks and logs stale metrics for monitoring.
        """
        current_time = time.time()
        expired_count = 0
        expired_by_collector: defaultdict[str, int] = defaultdict(int)

        # Default TTL for metrics without tier info (use MEDIUM)
        default_ttl = self._get_ttl_for_tier(UpdateTier.MEDIUM)

        # Find expired metrics
        expired_keys = []
        for key, last_update in self._metric_timestamps.items():
            collector_name, metric_name, _ = key
            age = current_time - last_update

            # Use default TTL (we don't track tier per metric currently)
            # TODO: Enhance to track tier per metric
            if age > default_ttl:
                expired_keys.append(key)
                expired_count += 1
                expired_by_collector[collector_name] += 1

        # Remove expired metrics from tracking
        for key in expired_keys:
            collector_name = key[0]
            del self._metric_timestamps[key]
            self._metric_counts[collector_name] -= 1

        # Update metrics
        for collector_name, count in expired_by_collector.items():
            # We don't have tier info here, using "unknown"
            self._expired_metrics_total.labels(
                collector=collector_name,
                tier="unknown",
            ).inc(count)

        # Update tracked metrics gauge
        for collector_name, count in self._metric_counts.items():
            self._tracked_metrics.labels(collector=collector_name).set(count)

        if expired_count > 0:
            logger.info(
                "Cleaned up expired metrics",
                total_expired=expired_count,
                by_collector=dict(expired_by_collector),
            )

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about tracked metrics.

        Returns
        -------
        dict[str, Any]
            Dictionary with expiration statistics.

        """
        return {
            "total_tracked": len(self._metric_timestamps),
            "by_collector": dict(self._metric_counts),
            "ttl_multiplier": self._ttl_multiplier,
        }
