"""Metric expiration and lifecycle management.

Prevents memory leaks by expiring stale metrics from devices/networks that
are no longer present or reporting. Implements TTL-based cleanup with
configurable grace periods.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any, NamedTuple

import structlog
from prometheus_client import Counter, Gauge

from .cardinality import CardinalityConfig
from .constants import UpdateTier
from .constants.metrics_constants import CollectorMetricName
from .metrics import LabelName

if TYPE_CHECKING:
    from .config import Settings

logger = structlog.get_logger(__name__)


class _TrackedSeries(NamedTuple):
    """Per-series tracking record stored in ``_metric_timestamps``.

    ``ttl_seconds`` (when not ``None``) is a fully-resolved TTL that overrides
    the tier-derived TTL — set by scheduler-gated fetch sites so a series polled
    slower than ``tier_interval × multiplier`` does not flap (#617 §1f / #541).
    """

    ts: float
    tier: UpdateTier | None
    ttl_seconds: float | None


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

        # Track last update time, tier, and optional per-series TTL per metric
        # Key: (collector_name, metric_name, frozen_labels)
        # Value: _TrackedSeries(ts, tier, ttl_seconds)
        self._metric_timestamps: dict[tuple[str, str, str], _TrackedSeries] = {}

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
            CollectorMetricName.EXPIRED_METRICS_TOTAL.value,
            "Total number of metrics expired due to TTL",
            labelnames=[LabelName.COLLECTOR.value, LabelName.TIER.value],
        )

        self._tracked_metrics = Gauge(
            CollectorMetricName.EXPIRATION_TRACKED_METRICS.value,
            "Number of metrics currently tracked for expiration",
            labelnames=[LabelName.COLLECTOR.value],
        )

        self._cardinality_limit_reached_total = Counter(
            CollectorMetricName.EXPORTER_CARDINALITY_LIMIT_REACHED_TOTAL.value,
            "Number of times a metric family exceeded its cardinality budget "
            "(cardinality.max_series_per_family). With action=warn (default) series "
            "are kept; with action=drop the oldest series in the family are shed.",
            labelnames=[LabelName.METRIC.value],
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
        ttl_seconds: float | None = None,
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
        ttl_seconds : float | None
            Fully-resolved per-series TTL in seconds. When provided it overrides
            the tier-derived TTL for this series (#617 §1f) — used by
            scheduler-gated fetch sites so a series polled slower than
            ``tier_interval × multiplier`` does not flap. When ``None`` the
            tier-derived TTL applies (zero behaviour change).

        """
        # Create a frozen representation of labels for dict key
        frozen_labels = self._freeze_labels(label_values)
        key = (collector_name, metric_name, frozen_labels)

        # Update timestamp, tier, and per-series TTL
        current_time = time.time()
        if key not in self._metric_timestamps:
            self._metric_counts[collector_name] += 1

        self._metric_timestamps[key] = _TrackedSeries(current_time, tier, ttl_seconds)

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
        for key, entry in self._metric_timestamps.items():
            collector_name, metric_name, _ = key
            tier = entry.tier
            age = current_time - entry.ts

            # A per-series ttl_seconds (scheduler-gated sites) wins over the
            # tier-derived TTL; else fall back to tier TTL (or MEDIUM default).
            if entry.ttl_seconds is not None:
                ttl = entry.ttl_seconds
            elif tier is not None:
                ttl = self._get_ttl_for_tier(tier)
            else:
                ttl = default_ttl
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

        # Enforce per-family cardinality budgets (#540). Budgets are keyed by
        # metric family (metric name), NOT by collector — the old shared
        # per-collector bucket lumped every device sub-collector into one
        # "DeviceCollector" budget and deleted live series at scale.
        self._enforce_cardinality_budgets()

    def _enforce_cardinality_budgets(self) -> None:
        """Enforce ``cardinality.max_series_per_family`` across all tracked families.

        Groups the tracked series once (a single O(n) pass) and applies the
        configured budget/action to every metric family. With the default
        ``action="warn"`` an over-budget family only alarms (counter + log);
        live series are never removed. ``action="drop"`` restores the legacy
        shedding behaviour, scoped to the offending family.
        """
        config = CardinalityConfig.from_settings(self.settings)

        families: defaultdict[str, list[tuple[tuple[str, str, str], float]]] = defaultdict(list)
        for key, entry in self._metric_timestamps.items():
            families[key[1]].append((key, entry.ts))

        for metric_name, entries in families.items():
            if len(entries) <= config.max_series_per_family:
                continue
            self._alarm_and_maybe_shed(
                metric_name, entries, config.max_series_per_family, config.action
            )

    def check_family_cardinality(
        self, metric_name: str, max_series: int, action: str = "warn"
    ) -> int:
        """Check one metric family against a cardinality budget.

        Parameters
        ----------
        metric_name : str
            Metric family (full wire name) to check.
        max_series : int
            Maximum number of tracked series allowed for this family.
        action : str
            ``"warn"`` (alarm only, keep all series — the default) or
            ``"drop"`` (shed the oldest series down to the budget).

        Returns
        -------
        int
            Number of series shed (always 0 with ``action="warn"``).

        """
        entries = [
            (key, entry.ts)
            for key, entry in self._metric_timestamps.items()
            if key[1] == metric_name
        ]
        if len(entries) <= max_series:
            return 0
        return self._alarm_and_maybe_shed(metric_name, entries, max_series, action)

    def _alarm_and_maybe_shed(
        self,
        metric_name: str,
        entries: list[tuple[tuple[str, str, str], float]],
        max_series: int,
        action: str,
    ) -> int:
        """Alarm for an over-budget family; shed oldest series only when dropping.

        Parameters
        ----------
        metric_name : str
            The over-budget metric family.
        entries : list[tuple[tuple[str, str, str], float]]
            The family's tracked ``(key, timestamp)`` entries.
        max_series : int
            The configured budget the family exceeded.
        action : str
            ``"warn"`` or ``"drop"``.

        Returns
        -------
        int
            Number of series shed (0 in warn mode).

        """
        self._cardinality_limit_reached_total.labels(metric=metric_name).inc()

        if action != "drop":
            logger.warning(
                "Metric family exceeds cardinality budget; keeping all series (action=warn)",
                metric=metric_name,
                series=len(entries),
                budget=max_series,
            )
            return 0

        # Legacy behaviour: sort by timestamp ascending (oldest first) and shed excess.
        entries.sort(key=lambda x: x[1])
        to_shed = len(entries) - max_series
        for key, _ts in entries[:to_shed]:
            self._remove_series(key)
            del self._metric_timestamps[key]
            self._metric_counts[key[0]] -= 1

        logger.warning(
            "Cardinality budget exceeded, shed oldest series (action=drop)",
            metric=metric_name,
            shed_count=to_shed,
            budget=max_series,
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
