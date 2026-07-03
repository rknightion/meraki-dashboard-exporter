"""Collector manager for coordinating metric collection."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from prometheus_client import Counter, Gauge

from ..core.async_utils import ManagedTaskGroup
from ..core.constants import UpdateTier
from ..core.constants.metrics_constants import CollectorMetricName
from ..core.logging import get_logger
from ..core.metrics import LabelName
from ..core.org_health import OrgHealthTracker
from ..core.otel_tracing import trace_method
from ..core.rate_limiter import OrgRateLimiter
from ..core.registry import get_registered_collectors
from ..core.scheduler import EndpointScheduler
from ..services.inventory import OrganizationInventory

if TYPE_CHECKING:
    from ..api.client import AsyncMerakiClient
    from ..core.collector import MetricCollector
    from ..core.config import Settings
    from ..core.metric_expiration import MetricExpirationManager
    from ..core.otel_data_logs import DataLogEmitter
    from ..core.scheduler import OrgShape

logger = get_logger(__name__)

# Upper bound on a collector's smoothing start-offset as a fraction of its tier
# interval (F-018). The tier's effective cadence is ~max(offset_i + duration_i),
# so an offset approaching the full interval would stretch the whole tier's
# period past its configured interval. Capping the max offset at half the
# interval guarantees smoothing offsets alone can never push cadence beyond the
# interval - only a collector that itself runs >50% of the interval can, which
# is a utilization problem surfaced separately by the utilization metric.
_SMOOTHING_MAX_INTERVAL_FRACTION = 0.5

# Collectors that consult the shared OrgHealthTracker to skip per-org collection
# for organizations currently in exponential backoff (F-169). Three of them also
# *record* their per-org verdict into the tracker, each under its own failure
# domain (#547): OrganizationCollector (SOURCE_ORGANIZATION), DeviceCollector
# (SOURCE_DEVICE), and NetworkHealthCollector (SOURCE_NETWORK_HEALTH) -- so a
# persistent failure in any one domain engages backoff even when the org
# collector is healthy or disabled. ClientsCollector, AlertsCollector, and
# MTSensorAlertsCollector remain gating consumers only (read should_collect,
# never mutate the tracker).
_ORG_HEALTH_TRACKER_COLLECTORS = frozenset({
    "OrganizationCollector",
    "DeviceCollector",
    "NetworkHealthCollector",
    "ClientsCollector",
    "AlertsCollector",
    "MTSensorAlertsCollector",
})


class CollectorManager:
    """Manages and coordinates metric collectors with tiered update intervals.

    Parameters
    ----------
    client : AsyncMerakiClient
        Meraki API client.
    settings : Settings
        Application settings.
    expiration_manager : MetricExpirationManager | None
        Manager for tracking and expiring stale metrics.

    """

    def __init__(
        self,
        client: AsyncMerakiClient,
        settings: Settings,
        expiration_manager: MetricExpirationManager | None = None,
        data_log_emitter: DataLogEmitter | None = None,
    ) -> None:
        """Initialize the collector manager with client and settings."""
        self.client = client
        self.settings = settings
        self.expiration_manager = expiration_manager
        self.data_log_emitter = data_log_emitter
        self.rate_limiter = OrgRateLimiter(settings)

        # Adaptive budget-aware endpoint scheduler (#617). Constructed right after
        # the rate limiter so it can read the AIMD-effective budget from the same
        # limiter, and injected into every collector below. Groups are registered
        # after collectors are instantiated (see _register_endpoint_groups).
        self.scheduler = EndpointScheduler(settings, self.rate_limiter)

        self.collectors: dict[UpdateTier, list[MetricCollector]] = {
            UpdateTier.FAST: [],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }

        # Initialize shared inventory service for caching org/network/device data.
        # Pass a NetworkFilter so excluded networks are dropped at the read path.
        from ..core.network_filter import NetworkFilter

        self.inventory = OrganizationInventory(
            api=self.client.api,
            settings=self.settings,
            rate_limiter=self.rate_limiter,
            network_filter=NetworkFilter(self.settings.network_filter),
        )

        # Per-organization health tracking for graceful degradation
        self.org_health_tracker = OrgHealthTracker()

        # Track collector health state
        self.collector_health: dict[str, dict[str, Any]] = {}

        # Track skipped/disabled collectors for visibility
        self.skipped_collectors: list[dict[str, str]] = []

        # Track collector offsets for diagnostics
        self.collector_offsets: dict[tuple[str, str], float] = {}
        self._collector_index: dict[str, MetricCollector] = {}
        self._collector_tiers: dict[str, UpdateTier] = {}
        self._collector_locks: dict[str, asyncio.Lock] = {}

        # Track whether each tier has completed its first collection cycle
        self._tier_initial_complete: dict[str, bool] = {
            "fast": False,
            "medium": False,
            "slow": False,
        }

        self._initialize_metrics()
        self._initialize_collectors()
        self._register_endpoint_groups()
        self._validate_collector_configuration()

    def _initialize_metrics(self) -> None:
        """Initialize collector infrastructure metrics."""
        # Gauge for tracking active parallel collections
        self._parallel_collections_active = Gauge(
            CollectorMetricName.PARALLEL_COLLECTIONS_ACTIVE.value,
            "Number of parallel organization collections currently active",
            labelnames=[
                LabelName.COLLECTOR.value,
                LabelName.TIER.value,
            ],
        )

        # Counter for collection errors by collector and phase
        self._collection_errors = Counter(
            CollectorMetricName.COLLECTION_ERRORS_TOTAL.value,
            "Total number of collection errors by collector and phase",
            labelnames=[
                LabelName.COLLECTOR.value,
                LabelName.TIER.value,
                LabelName.ERROR_TYPE.value,
            ],
        )

        # NB: no "collector_success_age_seconds" gauge here (F-039). It was set only
        # in post-run bookkeeping, so it froze at its last value when a collector
        # stopped running — defeating staleness detection. Use the query-time
        # expression `time() - meraki_exporter_collector_success_timestamp_seconds`
        # (owned by MetricCollector) for a freeze-proof staleness signal instead.

        # Gauge for collector failure streak
        self._collector_failure_streak = Gauge(
            CollectorMetricName.COLLECTOR_FAILURE_STREAK.value,
            "Consecutive failures for each collector since last success",
            labelnames=[
                LabelName.COLLECTOR.value,
                LabelName.TIER.value,
            ],
        )

        # Gauge for collection utilization ratio (actual_duration / tier_interval)
        self._collection_utilization = Gauge(
            CollectorMetricName.EXPORTER_COLLECTION_UTILIZATION_RATIO.value,
            "Fraction of the tier interval consumed by actual collection (0=instant, 1=full interval)",
            labelnames=[
                LabelName.COLLECTOR.value,
                LabelName.TIER.value,
            ],
        )

    def _get_tier_interval(self, tier: UpdateTier) -> int:
        if tier == UpdateTier.FAST:
            return self.settings.update_intervals.fast
        if tier == UpdateTier.MEDIUM:
            return self.settings.update_intervals.medium
        return self.settings.update_intervals.slow

    def _get_tier_concurrency(self, tier: UpdateTier) -> int:
        """Get the concurrency limit for a specific update tier.

        Parameters
        ----------
        tier : UpdateTier
            The update tier.

        Returns
        -------
        int
            The maximum concurrent tasks allowed for this tier.

        """
        if tier == UpdateTier.FAST:
            return self.settings.api.concurrency_limit_fast
        elif tier == UpdateTier.MEDIUM:
            return self.settings.api.concurrency_limit_medium
        elif tier == UpdateTier.SLOW:
            return self.settings.api.concurrency_limit_slow
        return self.settings.api.concurrency_limit  # fallback

    def _get_smoothing_window(self, tier: UpdateTier) -> float:
        if not self.settings.api.smoothing_enabled:
            return 0.0
        interval = self._get_tier_interval(tier)
        window = max(0.0, float(interval) * self.settings.api.smoothing_window_ratio)
        # Cap 1 (F-018): keep the max offset within a bounded fraction of the tier
        # interval so smoothing offsets can never stretch the tier cadence past
        # its configured interval.
        window = min(window, float(interval) * _SMOOTHING_MAX_INTERVAL_FRACTION)
        # Cap 2: keep the offset within the per-collector timeout budget.
        timeout_budget = float(self.settings.collectors.collector_timeout) - 10.0
        if timeout_budget > 0:
            window = min(window, timeout_budget)
        return max(0.0, window)

    def _get_collector_offset(self, collector_name: str, tier: UpdateTier) -> float:
        import hashlib

        window = self._get_smoothing_window(tier)
        if window <= 0:
            return 0.0
        key = f"{collector_name}:{tier.value}"
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        raw = int.from_bytes(digest[:4], "big")
        ratio = raw / 0xFFFFFFFF
        return ratio * window

    def _initialize_collectors(self) -> None:
        """Initialize all enabled collectors."""
        # Import all collectors to trigger registration
        # This ensures the @register_collector decorators are executed
        from . import (  # noqa: F401
            alerts,
            clients,
            config,
            device,
            insight,
            mt_alerts,
            mt_sensor,
            network_health,
            organization,
        )

        # Get all registered collectors
        registered_collectors = get_registered_collectors()

        # Get active collector names for filtering
        active_collector_names = self.settings.collectors.active_collectors

        # Initialize collectors for each tier
        for tier, collector_classes in registered_collectors.items():
            for collector_class in collector_classes:
                collector_name = collector_class.__name__
                collector_short_name = collector_name.replace("Collector", "").lower()

                # Check if collector is in active list
                if collector_short_name not in active_collector_names:
                    logger.info(
                        "Skipping collector (not in active list)",
                        collector=collector_name,
                        tier=tier.value,
                    )
                    # Track skipped collectors
                    self.skipped_collectors.append({
                        "name": collector_name,
                        "tier": tier.value,
                        "reason": "not in active_collectors list",
                    })
                    continue

                try:
                    # Create instance of the collector with inventory service and expiration manager
                    # Pass the shared org_health_tracker to every collector that gates
                    # per-org collection on it for graceful degradation (F-169).
                    extra_kwargs: dict[str, Any] = {}
                    if collector_name in _ORG_HEALTH_TRACKER_COLLECTORS:
                        extra_kwargs["org_health_tracker"] = self.org_health_tracker
                    collector_instance = collector_class(
                        api=self.client.api,
                        settings=self.settings,
                        inventory=self.inventory,
                        expiration_manager=self.expiration_manager,
                        rate_limiter=self.rate_limiter,
                        scheduler=self.scheduler,
                        data_log_emitter=self.data_log_emitter,
                        **extra_kwargs,
                    )
                    self.collectors[tier].append(collector_instance)
                    self._register_collector_metadata(collector_instance, tier)

                    # Initialize health tracking for this collector
                    self.collector_health[collector_name] = {
                        "last_success_time": None,
                        "failure_streak": 0,
                        "total_runs": 0,
                        "total_successes": 0,
                        "total_failures": 0,
                    }

                    logger.info(
                        "Initialized collector with inventory cache",
                        collector=collector_name,
                        tier=tier.value,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to initialize collector",
                        collector=collector_name,
                        tier=tier.value,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    # Track as skipped due to initialization failure
                    self.skipped_collectors.append({
                        "name": collector_name,
                        "tier": tier.value,
                        "reason": f"initialization failed: {type(e).__name__}",
                    })
                    # Continue with other collectors even if one fails to initialize

    def _register_endpoint_groups(self) -> None:
        """Register every collector's endpoint groups with the scheduler (#617).

        Funnels ``get_endpoint_groups()`` from all instantiated collectors (across
        every tier) into ``scheduler.register_groups``. Groups are empty until the
        fetch-site gating lands (Wave 2), so this is a no-op at that point and
        ``resolve()`` degrades to leaving intervals at their tier heartbeats.
        """
        self.scheduler.register_groups(
            group
            for tier_collectors in self.collectors.values()
            for collector in tier_collectors
            for group in collector.get_endpoint_groups()
        )

    @staticmethod
    def _normalize_collector_name(name: str) -> str:
        return "".join(char for char in name.lower() if char.isalnum())

    def _register_collector_metadata(
        self,
        collector: MetricCollector,
        tier: UpdateTier,
    ) -> None:
        collector_name = collector.__class__.__name__
        short_name = collector_name.replace("Collector", "")
        for key in {collector_name, short_name}:
            normalized = self._normalize_collector_name(key)
            self._collector_index[normalized] = collector
        self._collector_tiers[collector_name] = tier
        if collector_name not in self._collector_locks:
            self._collector_locks[collector_name] = asyncio.Lock()

    def get_collector_by_name(self, name: str) -> tuple[MetricCollector, UpdateTier] | None:
        """Look up a collector and its tier by name."""
        normalized = self._normalize_collector_name(name)
        collector = self._collector_index.get(normalized)
        if collector is None:
            return None
        collector_name = collector.__class__.__name__
        tier = self._collector_tiers.get(collector_name, collector.update_tier)
        return collector, tier

    def is_collector_running(self, collector_name: str) -> bool:
        """Check whether the named collector is currently running."""
        lock = self._collector_locks.get(collector_name)
        if lock is None:
            return False
        return lock.locked()

    async def run_collector_once(self, collector: MetricCollector, tier: UpdateTier) -> None:
        """Run a single collector once with the configured timeout."""
        timeout = self.settings.collectors.collector_timeout
        await self._run_collector_with_timeout(collector, tier, timeout)

    def _validate_collector_configuration(self) -> None:
        """Validate collector configuration and warn about invalid names.

        Checks if any collector names in active_collectors don't match
        any registered collectors, which could indicate typos or removed collectors.
        """
        # Get all known collector names (short form)
        all_known_collectors = set()
        for tier_collectors in self.collectors.values():
            for collector in tier_collectors:
                collector_short_name = collector.__class__.__name__.replace("Collector", "").lower()
                all_known_collectors.add(collector_short_name)

        # Also add skipped collectors to known list
        for skipped in self.skipped_collectors:
            collector_short_name = skipped["name"].replace("Collector", "").lower()
            all_known_collectors.add(collector_short_name)

        # Check for unknown collector names in configuration
        configured_collectors = self.settings.collectors.active_collectors
        unknown_collectors = configured_collectors - all_known_collectors

        if unknown_collectors:
            logger.warning(
                "Unknown collector names in configuration",
                unknown_collectors=sorted(unknown_collectors),
                known_collectors=sorted(all_known_collectors),
                message="Check for typos in MERAKI_EXPORTER_COLLECTORS__ENABLED_COLLECTORS",
            )

        # Log summary of collector configuration
        active_count = sum(len(tier_collectors) for tier_collectors in self.collectors.values())
        logger.info(
            "Collector configuration summary",
            active_collectors=active_count,
            skipped_collectors=len(self.skipped_collectors),
            configured_names=sorted(configured_collectors),
        )

    @property
    def is_ready(self) -> bool:
        """Whether FAST+MEDIUM tiers completed their first collection.

        AND at least one Meraki API request has returned HTTP 200 (#509
        hardening). SLOW tier is excluded (readiness probes must not block
        up to 900s).
        """
        return (
            self._tier_initial_complete["fast"]
            and self._tier_initial_complete["medium"]
            and self._has_api_success()
        )

    def _has_api_success(self) -> bool:
        """Whether at least one Meraki API request returned HTTP 200 (#509)."""
        count = self.client.get_successful_api_requests()
        return isinstance(count, int) and count > 0

    def get_readiness_status(self) -> dict[str, Any]:
        """Return readiness status for each tier and overall readiness.

        Returns
        -------
        dict[str, Any]
            Dictionary with "ready" bool, "api_success" bool, and "collectors"
            dict per tier.

        """
        return {
            "ready": self.is_ready,
            "api_success": self._has_api_success(),
            "collectors": {
                "fast": self._tier_initial_complete["fast"],
                "medium": self._tier_initial_complete["medium"],
                "slow": self._tier_initial_complete["slow"],
            },
        }

    def get_last_success_time(self) -> float | None:
        """Return the most recent successful-collection timestamp across all collectors.

        Returns
        -------
        float | None
            The newest ``last_success_time`` (unix seconds) among all tracked
            collectors, or ``None`` if no collector has ever succeeded. Used by
            the liveness dead-man switch (F-043).

        """
        times = [
            health["last_success_time"]
            for health in self.collector_health.values()
            if health.get("last_success_time")
        ]
        return max(times) if times else None

    def has_attempted_collection(self) -> bool:
        """Whether any collector has attempted at least one run.

        Returns
        -------
        bool
            True once any collector's ``total_runs`` is greater than zero. Used
            to keep the liveness probe green during startup/discovery before any
            collection has been attempted (F-043).

        """
        return any(health.get("total_runs", 0) > 0 for health in self.collector_health.values())

    async def collect_initial(self) -> None:
        """Run initial collection from all tiers sequentially to avoid API overload."""
        # Warm the cache before the first collection cycle so collectors get cache hits
        try:
            logger.info("Warming inventory cache before initial collection")
            await self.inventory.warm_cache()
            logger.info("Inventory cache warming complete")
        except Exception:
            logger.exception("Inventory cache warming failed, continuing with cold cache")

        # Resolve adaptive endpoint-group intervals from the (now warm) inventory
        # cache and emit the startup demand-vs-budget summary (#617). Safe to run
        # even on a cold cache — get_org_shape reads cached counts and the solver
        # degrades to floors/heartbeats. The first tier cycles below then run with
        # every gate open (never-ran => due), preserving today's warm startup.
        await self._resolve_and_log_schedule()

        # Validate the network filter resolves to at least one network somewhere.
        if self.settings.network_filter.is_active:
            await self._validate_network_filter()

        # Collect tier by tier to reduce API load during startup
        for tier in [UpdateTier.FAST, UpdateTier.MEDIUM, UpdateTier.SLOW]:
            try:
                await self.collect_tier(tier)
                # Small delay between tiers to avoid connection pool exhaustion
                await asyncio.sleep(1)
            except Exception:
                logger.exception(
                    "Failed to collect tier during initial collection",
                    tier=tier,
                )
                # Continue with next tier even if this one fails

    async def _resolve_and_log_schedule(self) -> None:
        """Compute the org shape and resolve endpoint-group intervals (#617).

        Reads the warmed inventory cache to build the single-org shape (#585),
        runs the scheduler's pure-CPU solve, and emits the one-line startup
        demand-vs-budget summary (plus an over-budget WARNING naming the
        priority-3/4 collectors to disable). Any failure is logged and swallowed
        so startup proceeds with intervals left at their tier heartbeats.
        """
        org_id = self.settings.meraki.org_id
        if org_id is None:
            # Single-org id is resolved at startup (#585) before collect_initial;
            # if it is somehow still unset, skip resolving rather than guess.
            logger.warning(
                "Skipping scheduler resolve: org_id is not set",
            )
            return
        try:
            shape = await self.inventory.get_org_shape(org_id)
            self.scheduler.resolve(shape)
        except Exception:
            logger.exception("Scheduler resolve failed during initial collection")
            return
        self._log_schedule_summary(shape)

    def _log_schedule_summary(self, shape: OrgShape) -> None:
        """Emit the one-line startup demand-vs-budget summary + over-budget warning."""
        diagnostics = self.scheduler.diagnostics()
        stretched = [
            f"{group['name']} {group['interval_seconds']:.0f}s ({group['stretch_factor']:.2f}x)"
            for group in diagnostics.get("groups", [])
            if (group.get("stretch_factor") or 1.0) > 1.0
        ]
        logger.info(
            "Scheduler solved endpoint-group intervals",
            org_shape_wireless_networks=shape.wireless_network_count,
            org_shape_devices=shape.device_count,
            estimated_demand_rps=round(diagnostics.get("total_demand_rps", 0.0), 2),
            budget_rps=round(diagnostics.get("budget_rps", 0.0), 2),
            shared_fraction=self.settings.api.rate_limit_shared_fraction,
            target_utilization=diagnostics.get("target_utilization"),
            over_budget=diagnostics.get("over_budget", False),
            stretched=stretched,
        )
        if diagnostics.get("over_budget"):
            shed = self._priority_shed_collectors()
            logger.warning(
                "Estimated API demand exceeds budget even at interval caps; disable "
                "low-priority (priority 3/4) collectors to fit within the API budget",
                estimated_demand_rps=round(diagnostics.get("total_demand_rps", 0.0), 2),
                budget_rps=round(diagnostics.get("budget_rps", 0.0), 2),
                target_utilization=diagnostics.get("target_utilization"),
                collectors_to_disable=shed,
                env_hint=(
                    "MERAKI_EXPORTER_COLLECTORS__DISABLE_COLLECTORS=" + ",".join(shed)
                    if shed
                    else None
                ),
            )

    def _priority_shed_collectors(self) -> list[str]:
        """Short names of collectors owning any gated priority-3/4 endpoint group.

        These are the collectors an operator should disable (via
        ``MERAKI_EXPORTER_COLLECTORS__DISABLE_COLLECTORS``) when the estimated
        demand cannot be squeezed under the budget by stretching alone.
        """
        names: set[str] = set()
        for tier_collectors in self.collectors.values():
            for collector in tier_collectors:
                if any(
                    group.priority >= 3 and group.gated for group in collector.get_endpoint_groups()
                ):
                    short = collector.__class__.__name__.replace("Collector", "").lower()
                    names.add(short)
        return sorted(names)

    async def _validate_network_filter(self) -> None:
        """Verify the configured network filter resolves to at least one network.

        Logs an ERROR per organisation that resolves to zero networks (visible
        in default log filters), and raises :class:`RuntimeError` only if the
        filter resolves to zero across **all** configured organisations —
        multi-org operators may legitimately have empty intersections for some
        orgs while the deployment still has work to do elsewhere.
        """
        organizations = await self.inventory.get_organizations()
        total_resolved = 0
        for org in organizations:
            org_id = org.get("id", "")
            if not org_id:
                continue
            full = await self.inventory.get_networks(org_id, unfiltered=True)
            resolved = await self.inventory.get_networks(org_id)
            total_resolved += len(resolved)
            if not resolved:
                logger.error(
                    "Network filter resolved to zero networks for organization",
                    org_id=org_id,
                    org_name=org.get("name"),
                    total_networks_in_org=len(full),
                    configured_filter=self.settings.network_filter.model_dump(),
                )

        if total_resolved == 0:
            raise RuntimeError(
                "Configured network filter resolved to zero networks across "
                "all organizations after warm-up. Check filter configuration: "
                f"{self.settings.network_filter.model_dump()}"
            )
        logger.info("Network filter active", resolved_total=total_resolved)

    @trace_method("collect.tier")
    async def collect_tier(self, tier: UpdateTier) -> None:
        """Run all collectors for a specific tier in parallel with bounded concurrency.

        Uses ManagedTaskGroup to run multiple collectors concurrently while
        respecting the configured concurrency limit. This provides significant
        performance improvements for multi-organization deployments.

        Parameters
        ----------
        tier : UpdateTier
            The update tier to collect.

        """
        # Add tier to current span context for visibility
        current_span = trace.get_current_span()
        if current_span.is_recording():
            current_span.set_attribute("tier", tier.value)

        tier_collectors = self.collectors.get(tier, [])
        if not tier_collectors:
            logger.debug(
                "No collectors for tier",
                tier=tier,
            )
            # No collectors to run — mark tier as complete immediately
            tier_key = tier.value
            if not self._tier_initial_complete.get(tier_key, False):
                self._tier_initial_complete[tier_key] = True
            return

        tier_concurrency = self._get_tier_concurrency(tier)
        logger.info(
            "Starting parallel collection for tier",
            tier=tier,
            collector_count=len(tier_collectors),
            concurrency_limit=tier_concurrency,
        )

        # Use collector_timeout from settings (default: 240s)
        timeout = self.settings.collectors.collector_timeout

        smoothing_window = self._get_smoothing_window(tier)

        # Skip the deterministic smoothing offset on the tier's FIRST collection
        # cycle (#591). The offset delays each collector up to 0.5x the tier
        # interval, which on every startup/rolling restart adds that latency to
        # /ready (FAST+MEDIUM gated). Applying smoothing only once the tier has
        # completed its initial cycle keeps steady-state cadence smoothing
        # unchanged while making readiness fast after a restart.
        apply_smoothing = self._tier_initial_complete.get(tier.value, False)

        # Run collectors in parallel with bounded concurrency
        async with ManagedTaskGroup(
            name=f"tier_{tier.value}",
            max_concurrency=tier_concurrency,
        ) as group:
            for collector in tier_collectors:
                collector_name = collector.__class__.__name__
                offset = (
                    self._get_collector_offset(collector_name, tier) if apply_smoothing else 0.0
                )
                self.collector_offsets[(collector_name, tier.value)] = offset
                await group.create_task(
                    self._run_collector_with_delay(
                        collector, tier, timeout, offset, smoothing_window
                    ),
                    name=collector_name,
                )

        logger.info(
            "Completed collection for tier",
            tier=tier,
            collector_count=len(tier_collectors),
        )

        # Mark this tier's first collection complete only once at least one
        # collector in the tier has actually SUCCEEDED (F-105). Marking it
        # complete after a cycle where every collector failed (e.g. a bad or
        # revoked API key) would flip /ready to 200 while the exporter has no
        # real data, defeating the readiness gate the Helm chart documents.
        tier_key = tier.value
        if not self._tier_initial_complete.get(tier_key, False):
            tier_had_success = any(
                self.collector_health.get(c.__class__.__name__, {}).get("total_successes", 0) > 0
                for c in tier_collectors
            )
            if tier_had_success:
                self._tier_initial_complete[tier_key] = True
                logger.info(
                    "Tier initial collection complete",
                    tier=tier_key,
                    is_ready=self.is_ready,
                )
            else:
                logger.warning(
                    "Tier collection cycle completed but no collector succeeded; "
                    "readiness withheld",
                    tier=tier_key,
                )

    async def _run_collector_with_delay(
        self,
        collector: MetricCollector,
        tier: UpdateTier,
        timeout: int,
        offset_seconds: float,
        window_seconds: float,
    ) -> None:
        if offset_seconds > 0:
            logger.debug(
                "Delaying collector start for smoothing",
                collector=collector.__class__.__name__,
                tier=tier.value,
                offset_seconds=round(offset_seconds, 2),
                window_seconds=round(window_seconds, 2),
            )
            await asyncio.sleep(offset_seconds)
        await self._run_collector_with_timeout(collector, tier, timeout)

    async def _run_collector_with_timeout(
        self,
        collector: MetricCollector,
        tier: UpdateTier,
        timeout: int,
    ) -> None:
        """Run a single collector with timeout and error handling.

        Tracks active collections, errors, and health status via metrics.

        Parameters
        ----------
        collector : MetricCollector
            The collector to run.
        tier : UpdateTier
            The update tier.
        timeout : int
            Timeout in seconds.

        """
        collector_name = collector.__class__.__name__
        collector_lock = self._collector_locks.get(collector_name)
        if collector_lock is None:
            collector_lock = asyncio.Lock()
            self._collector_locks[collector_name] = collector_lock

        if collector_lock.locked():
            logger.warning(
                "Collector already running, skipping",
                collector=collector_name,
                tier=tier.value,
            )
            return

        async with collector_lock:
            logger.debug(
                "Starting collector",
                collector=collector_name,
                tier=tier,
            )

            # Track active collection
            self._parallel_collections_active.labels(
                collector=collector_name,
                tier=tier.value,
            ).inc()

            # Track run
            if collector_name in self.collector_health:
                self.collector_health[collector_name]["total_runs"] += 1

            success = False
            start_time = time.time()
            try:
                async with asyncio.timeout(timeout):
                    await collector.collect()
                logger.debug(
                    "Collector completed successfully",
                    collector=collector_name,
                    tier=tier,
                )
                success = True
            except TimeoutError:
                logger.error(
                    "Collector timeout",
                    collector=collector_name,
                    tier=tier,
                    timeout_seconds=timeout,
                )
                # Track timeout error
                self._collection_errors.labels(
                    collector=collector_name,
                    tier=tier.value,
                    error_type="TimeoutError",
                ).inc()
                # Error logged, but don't raise to allow other collectors to continue
            except asyncio.CancelledError:
                logger.info(
                    "Collector task cancelled",
                    collector=collector_name,
                    tier=tier.value,
                )
                raise
            except Exception as e:
                logger.error(
                    "Collector failed",
                    collector=collector_name,
                    tier=tier,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Track collection error
                self._collection_errors.labels(
                    collector=collector_name,
                    tier=tier.value,
                    error_type=type(e).__name__,
                ).inc()
                # Error logged, but don't raise to allow other collectors to continue
            finally:
                # Calculate and record collection utilization ratio
                actual_duration = time.time() - start_time
                tier_interval = self._get_tier_interval(tier)
                utilization = actual_duration / tier_interval
                self._collection_utilization.labels(
                    collector=collector_name,
                    tier=tier.value,
                ).set(utilization)
                if utilization > 0.8:
                    logger.warning(
                        "Collector utilization high - may not keep up",
                        collector=collector_name,
                        tier=tier.value,
                        utilization=round(utilization, 2),
                        duration=round(actual_duration, 1),
                        interval=tier_interval,
                    )

                # Update health tracking
                if collector_name in self.collector_health:
                    if success:
                        self.collector_health[collector_name]["last_success_time"] = time.time()
                        self.collector_health[collector_name]["failure_streak"] = 0
                        self.collector_health[collector_name]["total_successes"] += 1
                    else:
                        self.collector_health[collector_name]["failure_streak"] += 1
                        self.collector_health[collector_name]["total_failures"] += 1

                    # No success-age gauge emission (F-039): staleness is derived at
                    # query time from meraki_exporter_collector_success_timestamp_seconds.
                    self._collector_failure_streak.labels(
                        collector=collector_name,
                        tier=tier.value,
                    ).set(self.collector_health[collector_name]["failure_streak"])

                # Decrement active collection counter
                self._parallel_collections_active.labels(
                    collector=collector_name,
                    tier=tier.value,
                ).dec()

    def get_tier_interval(self, tier: UpdateTier) -> int:
        """Get the update interval for a tier.

        Parameters
        ----------
        tier : UpdateTier
            The update tier.

        Returns
        -------
        int
            The interval in seconds.

        """
        if tier == UpdateTier.FAST:
            return self.settings.update_intervals.fast
        elif tier == UpdateTier.MEDIUM:
            return self.settings.update_intervals.medium
        else:  # SLOW
            return self.settings.update_intervals.slow

    def get_scheduling_diagnostics(self) -> dict[str, Any]:
        """Return scheduling diagnostics for UI/logging."""
        tier_info: dict[str, dict[str, Any]] = {}
        timeout_seconds = self.settings.collectors.collector_timeout
        smoothing_cap = max(0.0, float(timeout_seconds) - 10.0)
        for tier in UpdateTier:
            interval = self.get_tier_interval(tier)
            jitter_window = min(10.0, interval * 0.1)
            smoothing_window = self._get_smoothing_window(tier)
            tier_info[tier.value] = {
                "interval": interval,
                "jitter_window": round(jitter_window, 2),
                "smoothing_window": round(smoothing_window, 2),
            }

        collector_offsets: list[dict[str, Any]] = []
        for tier, collectors in self.collectors.items():
            for collector in collectors:
                collector_name = collector.__class__.__name__
                offset = self._get_collector_offset(collector_name, tier)
                collector_offsets.append({
                    "collector": collector_name,
                    "tier": tier.value,
                    "offset_seconds": round(offset, 2),
                })

        return {
            "tiers": tier_info,
            "collector_offsets": sorted(
                collector_offsets,
                key=lambda item: (item["tier"], item["offset_seconds"]),
            ),
            "smoothing": {
                "enabled": self.settings.api.smoothing_enabled,
                "window_ratio": self.settings.api.smoothing_window_ratio,
                "min_batch_delay": self.settings.api.smoothing_min_batch_delay,
                "max_batch_delay": self.settings.api.smoothing_max_batch_delay,
                "window_cap_seconds": round(smoothing_cap, 2),
            },
            "collector_timeout_seconds": timeout_seconds,
            "rate_limiter": {
                "enabled": self.settings.api.rate_limit_enabled,
                "rps": self.settings.api.rate_limit_requests_per_second,
                "burst": self.settings.api.rate_limit_burst,
                "share_fraction": self.settings.api.rate_limit_shared_fraction,
            },
            # The legacy per-setting "endpoint_intervals" block is retired into the
            # scheduler diagnostics (#617): the same operator pins now surface as
            # per-group solved intervals under scheduler["groups"].
            "scheduler": self.scheduler.diagnostics(),
        }

    def register_collector(self, collector: MetricCollector) -> None:
        """Register an additional collector.

        Parameters
        ----------
        collector : MetricCollector
            The collector to register.

        """
        tier = collector.update_tier
        self.collectors[tier].append(collector)
        self._register_collector_metadata(collector, tier)
        logger.info(
            "Registered collector",
            collector=collector.__class__.__name__,
            tier=tier,
        )
