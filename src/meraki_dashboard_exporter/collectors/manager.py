"""Collector manager for coordinating metric collection."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from prometheus_client import Counter, Gauge

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
    """Manages and coordinates metric collectors on per-collector, group-clocked loops.

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

        # Flat list of all instantiated top-level collectors. Each runs its own
        # endpoint-group-clocked loop (#631); there is no tier grouping.
        self.collectors: list[MetricCollector] = []

        # Bound concurrent collector runs across all the per-collector loops.
        self._collector_semaphore = asyncio.Semaphore(
            self.settings.collectors.max_concurrent_collectors
        )

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

        self._collector_index: dict[str, MetricCollector] = {}
        self._collector_locks: dict[str, asyncio.Lock] = {}

        # Names of collectors that have completed at least one SUCCESSFUL run.
        # Drives readiness (every collector owning an enabled priority-<=3 group
        # must appear here) — the de-tiered replacement for tier-complete flags.
        self._collector_succeeded: set[str] = set()

        self._initialize_metrics()
        self._initialize_collectors()
        self._register_endpoint_groups()
        self._install_ttl_resolver()
        self._validate_collector_configuration()

    def _initialize_metrics(self) -> None:
        """Initialize collector infrastructure metrics."""
        # Gauge for tracking active parallel collections
        self._parallel_collections_active = Gauge(
            CollectorMetricName.PARALLEL_COLLECTIONS_ACTIVE.value,
            "Number of parallel organization collections currently active",
            labelnames=[
                LabelName.COLLECTOR.value,
            ],
        )

        # Counter for collection errors by collector and phase
        self._collection_errors = Counter(
            CollectorMetricName.COLLECTION_ERRORS_TOTAL.value,
            "Total number of collection errors by collector and phase",
            labelnames=[
                LabelName.COLLECTOR.value,
                LabelName.ERROR_TYPE.value,
            ],
        )

        # Per-collector effective cadence (min solved interval of its enabled
        # gated groups) — the de-tiered replacement for the per-tier interval;
        # staleness alerts read `time() - success_timestamp > 3 x cadence` (#631).
        self._collector_cadence = Gauge(
            CollectorMetricName.COLLECTOR_CADENCE_SECONDS.value,
            "Effective cadence of a collector (smallest solved interval of its "
            "enabled endpoint groups)",
            labelnames=[
                LabelName.COLLECTOR.value,
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
            ],
        )

        # Gauge for collection utilization ratio (actual_duration / collector cadence)
        self._collection_utilization = Gauge(
            CollectorMetricName.EXPORTER_COLLECTION_UTILIZATION_RATIO.value,
            "Fraction of the collector's cadence consumed by actual collection "
            "(0=instant, 1=full cadence)",
            labelnames=[
                LabelName.COLLECTOR.value,
            ],
        )

    def _install_ttl_resolver(self) -> None:
        """Wire the expiration manager's fallback-TTL resolver to collector cadence.

        Series without an explicit ``ttl_seconds`` fall back to the owning
        collector's current cadence × ``metric_ttl_multiplier`` (#631), evaluated
        lazily at cleanup so it tracks the solver's live intervals.
        """
        if self.expiration_manager is None:
            return
        multiplier = float(self.settings.monitoring.metric_ttl_multiplier)

        def _resolver(collector_name: str) -> float | None:
            collector = self.get_collector_by_class_name(collector_name)
            if collector is None:
                return None
            return collector.collector_cadence_seconds() * multiplier

        self.expiration_manager.set_ttl_resolver(_resolver)

    def _emit_cadence_gauges(self) -> None:
        """Publish each collector's effective cadence gauge (post-resolve)."""
        for collector in self.collectors:
            self._collector_cadence.labels(
                collector=collector.__class__.__name__,
            ).set(collector.collector_cadence_seconds())

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

        # Get all registered collectors (flat list, no tiers)
        registered_collectors = get_registered_collectors()

        # Get active collector names for filtering
        active_collector_names = self.settings.collectors.active_collectors

        for collector_class in registered_collectors:
            collector_name = collector_class.__name__
            collector_short_name = collector_name.replace("Collector", "").lower()

            # Check if collector is in active list
            if collector_short_name not in active_collector_names:
                logger.info(
                    "Skipping collector (not in active list)",
                    collector=collector_name,
                )
                # Track skipped collectors
                self.skipped_collectors.append({
                    "name": collector_name,
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
                self.collectors.append(collector_instance)
                self._register_collector_metadata(collector_instance)

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
                )
            except Exception as e:
                logger.error(
                    "Failed to initialize collector",
                    collector=collector_name,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Track as skipped due to initialization failure
                self.skipped_collectors.append({
                    "name": collector_name,
                    "reason": f"initialization failed: {type(e).__name__}",
                })
                # Continue with other collectors even if one fails to initialize

    def _register_endpoint_groups(self) -> None:
        """Register every collector's endpoint groups with the scheduler (#617)."""
        self.scheduler.register_groups(
            group for collector in self.collectors for group in collector.get_endpoint_groups()
        )

    @staticmethod
    def _normalize_collector_name(name: str) -> str:
        return "".join(char for char in name.lower() if char.isalnum())

    def _register_collector_metadata(
        self,
        collector: MetricCollector,
    ) -> None:
        collector_name = collector.__class__.__name__
        short_name = collector_name.replace("Collector", "")
        for key in {collector_name, short_name}:
            normalized = self._normalize_collector_name(key)
            self._collector_index[normalized] = collector
        if collector_name not in self._collector_locks:
            self._collector_locks[collector_name] = asyncio.Lock()

    def get_collector_by_name(self, name: str) -> MetricCollector | None:
        """Look up a collector by (normalized) name."""
        normalized = self._normalize_collector_name(name)
        return self._collector_index.get(normalized)

    def get_collector_by_class_name(self, name: str) -> MetricCollector | None:
        """Return the instantiated collector whose class name is ``name`` (#614).

        Returns ``None`` when no enabled collector has that class name — e.g. the
        collector was disabled via ``active_collectors`` — so callers degrade
        gracefully.

        Parameters
        ----------
        name : str
            Exact collector class name (e.g. ``"DeviceCollector"``).

        Returns
        -------
        MetricCollector | None
            The matching collector instance, or ``None`` if absent/disabled.

        """
        for collector in self.collectors:
            if collector.__class__.__name__ == name:
                return collector
        return None

    def is_collector_running(self, collector_name: str) -> bool:
        """Check whether the named collector is currently running."""
        lock = self._collector_locks.get(collector_name)
        if lock is None:
            return False
        return lock.locked()

    async def run_collector_once(self, collector: MetricCollector, *, force: bool = False) -> None:
        """Run a single collector once with the configured timeout.

        When ``force`` is True every endpoint group is fetched regardless of its
        gate (used by the manual-trigger endpoint so a trigger actually refetches
        rather than silently no-opping in-window groups, #631).
        """
        timeout = self.settings.collectors.collector_timeout
        await self._run_collector_with_timeout(collector, timeout, force=force)

    def _validate_collector_configuration(self) -> None:
        """Validate collector configuration and warn about invalid names.

        Checks if any collector names in active_collectors don't match
        any registered collectors, which could indicate typos or removed collectors.
        """
        # Get all known collector names (short form)
        all_known_collectors = set()
        for collector in self.collectors:
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
        active_count = len(self.collectors)
        logger.info(
            "Collector configuration summary",
            active_collectors=active_count,
            skipped_collectors=len(self.skipped_collectors),
            configured_names=sorted(configured_collectors),
        )

    def _readiness_collectors(self) -> list[MetricCollector]:
        """Collectors that gate readiness: those owning an enabled priority-<=3 group.

        Config-style collectors (all priority-4 groups, e.g. ConfigCollector) are
        excluded — exactly as the SLOW tier used to be — so readiness probes are
        never blocked waiting on slow config data (#631, preserving F-105).
        """
        result: list[MetricCollector] = []
        for collector in self.collectors:
            if any(
                group.priority <= 3 and group.gated and self.scheduler.is_enabled(group.name)
                for group in collector.get_endpoint_groups()
            ):
                result.append(collector)
        return result

    @property
    def is_ready(self) -> bool:
        """Whether every readiness-gating collector has succeeded at least once.

        AND at least one Meraki API request has returned HTTP 200 (#509
        hardening). A collector cycle that produced no success withholds
        readiness (F-105).
        """
        gating = self._readiness_collectors()
        all_succeeded = all(c.__class__.__name__ in self._collector_succeeded for c in gating)
        return bool(gating) and all_succeeded and self._has_api_success()

    def _has_api_success(self) -> bool:
        """Whether at least one Meraki API request returned HTTP 200 (#509)."""
        count = self.client.get_successful_api_requests()
        return isinstance(count, int) and count > 0

    def get_readiness_status(self) -> dict[str, Any]:
        """Return overall readiness plus per-collector first-success state.

        Returns
        -------
        dict[str, Any]
            Dictionary with "ready" bool, "api_success" bool, and "collectors"
            mapping each readiness-gating collector name to whether it has
            succeeded at least once.

        """
        return {
            "ready": self.is_ready,
            "api_success": self._has_api_success(),
            "collectors": {
                collector.__class__.__name__: (
                    collector.__class__.__name__ in self._collector_succeeded
                )
                for collector in self._readiness_collectors()
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

    def _ordered_collectors(self) -> list[MetricCollector]:
        """Collectors ordered by best (lowest) group priority, then class name.

        Priority-1 (up-ness/alerts) collectors run first so the freshest signals
        land earliest; a collector with no groups sorts last. Deterministic.
        """

        def sort_key(collector: MetricCollector) -> tuple[int, str]:
            groups = collector.get_endpoint_groups()
            best = min((g.priority for g in groups), default=99)
            return (best, collector.__class__.__name__)

        return sorted(self.collectors, key=sort_key)

    async def collect_initial(self) -> None:
        """Run one initial collection of every collector, sequentially.

        Ordered by best group priority (up-ness first) then name, to bound
        startup API load while landing the freshest signals earliest. Every gate
        is open on a cold start (never-attempted groups are due), so this
        refetches everything once.
        """
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

        # Collect one collector at a time (priority order) to bound startup load.
        for collector in self._ordered_collectors():
            try:
                await self.run_collector_once(collector)
                # Small delay between collectors to avoid connection pool exhaustion
                await asyncio.sleep(1)
            except Exception:
                logger.exception(
                    "Failed to collect during initial collection",
                    collector=collector.__class__.__name__,
                )
                # Continue with the next collector even if this one fails

        # Publish the per-collector cadence gauges now that a schedule exists.
        self._emit_cadence_gauges()

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
        self._emit_cadence_gauges()
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
        for collector in self.collectors:
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

    @staticmethod
    def _mark_span_error(exc: BaseException) -> None:
        """Mark the current (``collect.collector``) span ERROR and record ``exc``.

        Used by the swallow-and-continue error paths so the root span reflects a
        real collector failure (#647) even though the exception is not re-raised.

        Parameters
        ----------
        exc : BaseException
            The exception (or ``TimeoutError``) that the collector run raised.

        """
        span = trace.get_current_span()
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
        span.record_exception(exc)

    @trace_method("collect.collector")
    async def _run_collector_with_timeout(
        self,
        collector: MetricCollector,
        timeout: int,
        *,
        force: bool = False,
    ) -> None:
        """Run a single collector once with timeout, concurrency bound, and health tracking.

        Bounded by the global ``max_concurrent_collectors`` semaphore so the many
        per-collector loops never overwhelm the API together. When ``force`` is
        True the collector fetches every group regardless of its gate (manual
        trigger). Tracks active collections, errors, cadence-utilization, and
        health; records first-success for readiness.

        Parameters
        ----------
        collector : MetricCollector
            The collector to run.
        timeout : int
            Timeout in seconds.
        force : bool
            Force every endpoint group to fetch this run (bypass gates).

        """
        collector_name = collector.__class__.__name__
        # #646: label the shared "collect.collector" root span so it is
        # identifiable (and groupable) without descending into the child
        # collect.<Collector> span -- all collectors share this literal name.
        trace.get_current_span().set_attribute("collector.name", collector_name)
        collector_lock = self._collector_locks.get(collector_name)
        if collector_lock is None:
            collector_lock = asyncio.Lock()
            self._collector_locks[collector_name] = collector_lock

        if collector_lock.locked():
            logger.warning(
                "Collector already running, skipping",
                collector=collector_name,
            )
            return

        async with self._collector_semaphore, collector_lock:
            logger.debug("Starting collector", collector=collector_name)

            # Track active collection
            self._parallel_collections_active.labels(
                collector=collector_name,
            ).inc()

            # Track run
            if collector_name in self.collector_health:
                self.collector_health[collector_name]["total_runs"] += 1

            success = False
            start_time = time.time()
            if force:
                collector._force_run = True
            try:
                async with asyncio.timeout(timeout):
                    await collector.collect()
                logger.debug("Collector completed successfully", collector=collector_name)
                success = True
            except TimeoutError as e:
                logger.error(
                    "Collector timeout",
                    collector=collector_name,
                    timeout_seconds=timeout,
                )
                self._collection_errors.labels(
                    collector=collector_name,
                    error_type="TimeoutError",
                ).inc()
                # #647: reflect the failure on the collect.collector root span so
                # root-level error panels/rates fire. We swallow (don't re-raise)
                # so other collectors continue, but the span must not read OK.
                self._mark_span_error(e)
                # Error logged, but don't raise to allow other collectors to continue
            except asyncio.CancelledError:
                logger.info("Collector task cancelled", collector=collector_name)
                raise
            except Exception as e:
                logger.error(
                    "Collector failed",
                    collector=collector_name,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                self._collection_errors.labels(
                    collector=collector_name,
                    error_type=type(e).__name__,
                ).inc()
                # #647: mark the root span ERROR even though we swallow the
                # exception to let other collectors continue.
                self._mark_span_error(e)
                # Error logged, but don't raise to allow other collectors to continue
            finally:
                if force:
                    collector._force_run = False
                # Record utilization as a fraction of the collector's cadence.
                actual_duration = time.time() - start_time
                cadence = max(1.0, collector.collector_cadence_seconds())
                utilization = actual_duration / cadence
                self._collection_utilization.labels(
                    collector=collector_name,
                ).set(utilization)
                if utilization > 0.8:
                    logger.warning(
                        "Collector utilization high - may not keep up",
                        collector=collector_name,
                        utilization=round(utilization, 2),
                        duration=round(actual_duration, 1),
                        cadence=round(cadence, 1),
                    )

                # Update health tracking
                if collector_name in self.collector_health:
                    if success:
                        self.collector_health[collector_name]["last_success_time"] = time.time()
                        self.collector_health[collector_name]["failure_streak"] = 0
                        self.collector_health[collector_name]["total_successes"] += 1
                        # Record first-success for readiness (#631).
                        self._collector_succeeded.add(collector_name)
                    else:
                        self.collector_health[collector_name]["failure_streak"] += 1
                        self.collector_health[collector_name]["total_failures"] += 1

                    # No success-age gauge emission (F-039): staleness is derived at
                    # query time from meraki_exporter_collector_success_timestamp_seconds.
                    self._collector_failure_streak.labels(
                        collector=collector_name,
                    ).set(self.collector_health[collector_name]["failure_streak"])

                # Decrement active collection counter
                self._parallel_collections_active.labels(
                    collector=collector_name,
                ).dec()

    def get_scheduling_diagnostics(self) -> dict[str, Any]:
        """Return scheduling diagnostics for UI/logging.

        Per-tier info is gone (#631): scheduling is now per endpoint group
        (solved intervals + next-due under ``scheduler``) with a per-collector
        cadence + phase-offset summary.
        """
        timeout_seconds = self.settings.collectors.collector_timeout
        smoothing_cap = max(0.0, float(timeout_seconds) - 10.0)

        collectors: list[dict[str, Any]] = []
        for collector in self.collectors:
            collector_name = collector.__class__.__name__
            collectors.append({
                "collector": collector_name,
                "cadence_seconds": round(collector.collector_cadence_seconds(), 2),
                "phase_offset_seconds": round(collector.phase_offset_seconds(), 2),
            })

        return {
            "collectors": sorted(collectors, key=lambda item: item["collector"]),
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
            # Operator pins surface as per-group solved intervals under scheduler["groups"].
            "scheduler": self.scheduler.diagnostics(),
        }

    def register_collector(self, collector: MetricCollector) -> None:
        """Register an additional collector.

        Parameters
        ----------
        collector : MetricCollector
            The collector to register.

        """
        self.collectors.append(collector)
        self._register_collector_metadata(collector)
        logger.info(
            "Registered collector",
            collector=collector.__class__.__name__,
        )
