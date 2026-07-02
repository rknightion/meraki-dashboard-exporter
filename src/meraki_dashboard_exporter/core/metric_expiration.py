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

        # Track last update time and tier per metric
        # Key: (collector_name, metric_name, frozen_labels)
        # Value: (timestamp of last update, tier or None)
        self._metric_timestamps: dict[tuple[str, str, str], tuple[float, UpdateTier | None]] = {}

        # Track the actual Gauge object and its label values per metric series so
        # expired/shed entries can be removed from the Prometheus registry (not just
        # from tracking bookkeeping).
        # Key: (collector_name, metric_name, frozen_labels)
        # Value: (Gauge object, ordered label values dict)
        self._metric_series: dict[tuple[str, str, str], tuple[Gauge, dict[str, str]]] = {}

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

        self._cardinality_limit_reached = Gauge(
            CollectorMetricName.EXPORTER_CARDINALITY_LIMIT_REACHED.value,
            "1 if cardinality shedding is active for this collector, 0 otherwise",
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
        tier: UpdateTier | None = None,
        metric: Gauge | None = None,
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
        tier : UpdateTier | None
            The update tier for this metric, used to calculate the TTL.
            If None, the default TTL (MEDIUM) is used.
        metric : Gauge | None
            The Gauge object owning this series. When provided, the actual
            Prometheus series is removed (via ``Gauge.remove``) once the entry
            expires or is shed for cardinality. When ``None``, only tracking
            bookkeeping is kept (backward compatible).

        """
        # Create a frozen representation of labels for dict key
        frozen_labels = self._freeze_labels(label_values)
        key = (collector_name, metric_name, frozen_labels)

        # Update timestamp and tier
        current_time = time.time()
        if key not in self._metric_timestamps:
            self._metric_counts[collector_name] += 1

        self._metric_timestamps[key] = (current_time, tier)

        # Remember the actual series so it can be removed from the registry on expiry.
        if metric is not None:
            self._metric_series[key] = (metric, dict(label_values))

    def _remove_series(self, key: tuple[str, str, str]) -> None:
        """Remove the actual Prometheus series for an expired/shed tracking key.

        Looks up the Gauge object recorded via ``track_metric_update`` and calls
        ``Gauge.remove`` with the label values in the gauge's declared order. Safe
        to call for keys with no recorded series (no-op) or series already removed
        elsewhere (swallows ``KeyError``/``ValueError``).

        Parameters
        ----------
        key : tuple[str, str, str]
            The (collector_name, metric_name, frozen_labels) tracking key.

        """
        series = self._metric_series.pop(key, None)
        if series is None:
            return

        metric, label_values = series
        try:
            labelnames = list(getattr(metric, "_labelnames", ()) or ())
            ordered = [label_values[name] for name in labelnames]
            metric.remove(*ordered)
        except KeyError, ValueError:
            # Series already removed, or labels no longer match the gauge — nothing to do.
            pass

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

        For every tracked series past its TTL this removes the actual Prometheus
        series (via ``Gauge.remove``) when the owning Gauge object was recorded at
        ``track_metric_update`` time, then drops the tracking bookkeeping. Series
        tracked without a Gauge reference are only untracked (bookkeeping only).
        """
        current_time = time.time()
        expired_count = 0
        expired_by_collector: defaultdict[str, int] = defaultdict(int)

        # Default TTL for metrics without tier info (use MEDIUM)
        default_ttl = self._get_ttl_for_tier(UpdateTier.MEDIUM)

        # Find expired metrics
        expired_keys = []
        expired_by_collector_tier: defaultdict[tuple[str, str], int] = defaultdict(int)
        for key, (last_update, tier) in self._metric_timestamps.items():
            collector_name, metric_name, _ = key
            age = current_time - last_update

            ttl = self._get_ttl_for_tier(tier) if tier is not None else default_ttl
            if age > ttl:
                expired_keys.append(key)
                expired_count += 1
                expired_by_collector[collector_name] += 1
                tier_label = tier.value if tier is not None else "unknown"
                expired_by_collector_tier[(collector_name, tier_label)] += 1

        # Remove expired metrics from the registry and from tracking
        for key in expired_keys:
            collector_name = key[0]
            self._remove_series(key)
            del self._metric_timestamps[key]
            self._metric_counts[collector_name] -= 1

        # Update metrics
        for (collector_name, tier_label), count in expired_by_collector_tier.items():
            self._expired_metrics_total.labels(
                collector=collector_name,
                tier=tier_label,
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

        # Enforce cardinality limits per collector
        max_cardinality = self.settings.monitoring.max_cardinality_per_collector
        collectors = set(self._metric_counts.keys())
        for collector_name in collectors:
            self.check_cardinality(collector_name, max_cardinality)

    def check_cardinality(self, collector_name: str, max_cardinality: int) -> int:
        """Check and enforce cardinality limit for a collector.

        If the collector exceeds max_cardinality, drop the oldest (least-recently-updated)
        label sets until the count is within the limit.

        Parameters
        ----------
        collector_name : str
            Name of the collector to check.
        max_cardinality : int
            Maximum number of tracked label sets allowed for this collector.

        Returns
        -------
        int
            Number of label sets shed (0 if within limits).

        """
        collector_metrics = [
            (key, ts)
            for key, (ts, _tier) in self._metric_timestamps.items()
            if key[0] == collector_name
        ]

        if len(collector_metrics) <= max_cardinality:
            self._cardinality_limit_reached.labels(collector=collector_name).set(0)
            return 0

        # Sort by timestamp ascending (oldest first) and shed excess
        collector_metrics.sort(key=lambda x: x[1])
        to_shed = len(collector_metrics) - max_cardinality

        for key, _ts in collector_metrics[:to_shed]:
            self._remove_series(key)
            del self._metric_timestamps[key]
            self._metric_counts[collector_name] -= 1

        self._cardinality_limit_reached.labels(collector=collector_name).set(1)

        logger.warning(
            "Cardinality limit reached, shed label sets",
            collector=collector_name,
            shed_count=to_shed,
            remaining=max_cardinality,
        )
        return to_shed

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
