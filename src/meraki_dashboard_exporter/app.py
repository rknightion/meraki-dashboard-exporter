"""FastAPI application for the Meraki Dashboard Exporter."""

from __future__ import annotations

import asyncio
import hmac
import json
import random
import time
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psutil  # type: ignore[import-untyped]
from fastapi import FastAPI, HTTPException, Response
from fastapi import Request as FastAPIRequest
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Gauge, generate_latest
from pydantic import BaseModel
from starlette.requests import Request

from .__version__ import __version__
from .api.client import AsyncMerakiClient
from .collectors.manager import CollectorManager
from .core.build_info import register_build_info
from .core.cardinality import CardinalityMonitor, setup_cardinality_endpoint
from .core.config import Settings
from .core.config_logger import log_startup_summary
from .core.constants import UpdateTier
from .core.constants.metrics_constants import CollectorMetricName
from .core.discovery import DiscoveryService, resolve_org_id
from .core.logging import get_logger, setup_logging
from .core.metric_expiration import MetricExpirationManager
from .core.otel_data_logs import DataLogEmitter
from .core.otel_logging import OTELLoggingConfig
from .core.otel_tracing import TracingConfig
from .core.webhook_handler import WebhookHandler, enforce_webhook_security
from .services.status import StatusService, build_effective_config

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# #277: cadence for the lightweight exporter process self-resource sampler
# (see ExporterApp._resource_metrics_loop). Deliberately NOT a full collector
# tier - just a cheap psutil read on a fixed interval.
RESOURCE_METRICS_INTERVAL_SECONDS = 30.0


# SECURITY (SEC-01 / #558): sensitive GET UIs that leak PII (client MAC/IP/
# hostname), full topology, or metric label surface. When
# ``server.api_token`` is set these require a bearer token; when
# ``server.ui_enabled`` is false the human UI surface is suppressed entirely.
# ``/metrics`` is deliberately NOT gated - Prometheus must scrape it - and
# ``/health`` / ``/ready`` stay open for orchestrator probes.
SENSITIVE_UI_PREFIXES: tuple[str, ...] = (
    "/clients",
    "/status",
    "/config",
    "/cardinality",
    "/api/metrics/cardinality",
)


def _is_sensitive_ui_path(path: str) -> bool:
    """Return True if ``path`` is a sensitive GET UI/endpoint (see #558)."""
    return any(path == p or path.startswith(p + "/") for p in SENSITIVE_UI_PREFIXES)


def ui_guard_decision(
    *,
    method: str,
    path: str,
    ui_enabled: bool,
    api_token: str | None,
    auth_header: str,
) -> tuple[int, str] | None:
    """Decide whether a request to a sensitive GET UI should be short-circuited.

    Pure function (no I/O) so the gating policy is unit-testable without the
    config flags being wired yet (#558).

    Parameters
    ----------
    method : str
        HTTP method.
    path : str
        Request path (no query string).
    ui_enabled : bool
        Effective ``server.ui_enabled`` - when False the human UI is suppressed.
    api_token : str | None
        Effective ``server.api_token`` secret value, or None when unset.
    auth_header : str
        The raw ``Authorization`` header value.

    Returns
    -------
    tuple[int, str] | None
        ``(status_code, detail)`` to short-circuit the request, or ``None`` to
        allow it through.

    """
    if method != "GET":
        return None
    is_index = path == "/"
    is_sensitive = _is_sensitive_ui_path(path)
    if not (is_index or is_sensitive):
        return None
    if not ui_enabled:
        return (404, "Web UI is disabled")
    # Token gate applies only to the sensitive PII/detail endpoints, not the
    # index landing page.
    if is_sensitive and api_token is not None:
        scheme, _, provided = auth_header.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(provided, api_token):
            return (401, "Invalid or missing API token")
    return None


class CollectorTriggerRequest(BaseModel):
    """Request model for triggering a collector on-demand."""

    collector: str


class ExporterApp:
    """Main application class for the Meraki Dashboard Exporter.

    Parameters
    ----------
    settings : Settings | None
        Application settings, will load from environment if not provided.

    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the exporter application with settings."""
        self.settings = settings or Settings()
        setup_logging(self.settings)

        # Initialize tracing before anything else
        self.tracing = TracingConfig(self.settings)
        self.tracing.setup_tracing()

        # Initialize OTEL logging if enabled
        self.otel_logging = OTELLoggingConfig(self.settings)
        if self.settings.otel.enabled:
            self.otel_logging.setup_otel_logging()

        # Initialize the OTLP data-log emitter (#622): a dedicated log channel for
        # high-cardinality per-entity product data. Independent of tracing; hard
        # off by default. Constructing it while disabled is a cheap no-op.
        self.data_log_emitter = DataLogEmitter(self.settings)

        self.client = AsyncMerakiClient(self.settings)

        # #544: small dedicated pool for synchronous registry-iteration work
        # (/metrics generate_latest, _get_metrics_stats, cardinality analysis).
        # The SDK's own bounded executor (client.executor) becomes the loop's
        # DEFAULT executor in lifespan, so this separate pool guarantees scrapes
        # never queue behind blocked SDK threads during a 429 storm (RES-04).
        self._serving_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="registry-serve",
        )

        # Register the static build-info gauge (MET-10): constant value 1 with
        # version/commit labels identifying the running build.
        register_build_info()

        # Exporter process self-resource gauges (#277): unlabeled process-level
        # singletons, sampled periodically by _resource_metrics_loop (a
        # lightweight lifespan background task, not a full collector tier).
        # psutil.Process() is created once here; cpu_percent() is primed (its
        # first call always returns 0.0) at the top of the loop itself.
        self._resource_process = psutil.Process()
        self._resource_metrics_interval_seconds = RESOURCE_METRICS_INTERVAL_SECONDS
        self._resource_memory_gauge = Gauge(
            CollectorMetricName.EXPORTER_MEMORY_USAGE_BYTES.value,
            "Resident memory (RSS) used by the exporter process itself, in bytes (#277).",
        )
        self._resource_cpu_gauge = Gauge(
            CollectorMetricName.EXPORTER_CPU_USAGE_PERCENT.value,
            "CPU utilization percent of the exporter process itself, sampled periodically (#277).",
        )

        # Initialize metric expiration manager (Phase 3.2)
        self.expiration_manager = MetricExpirationManager(settings=self.settings)

        self.collector_manager = CollectorManager(
            client=self.client,
            settings=self.settings,
            expiration_manager=self.expiration_manager,
            data_log_emitter=self.data_log_emitter,
        )

        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._shutdown_event = asyncio.Event()
        self._tier_tasks: dict[str, asyncio.Task[Any]] = {}
        self._start_time = time.time()
        self._discovery_summary: dict[str, Any] | None = None

        # Setup webhook handler. SECURITY (SEC-03 / #561): refuse the insecure
        # combination (enabled + require_secret=false) at startup unless the
        # operator explicitly opted in via webhooks.allow_insecure.
        enforce_webhook_security(
            enabled=self.settings.webhooks.enabled,
            require_secret=self.settings.webhooks.require_secret,
            # TODO(CFG-BIG): webhooks.allow_insecure lands with the config sweep;
            # getattr keeps the secure default (False) until then.
            allow_insecure=getattr(self.settings.webhooks, "allow_insecure", False),
        )
        self.webhook_handler: WebhookHandler | None = None
        if self.settings.webhooks.enabled:
            self.webhook_handler = WebhookHandler(self.settings)
            logger.info(
                "Webhook receiver enabled",
                require_secret=self.settings.webhooks.require_secret,
            )

        # Initialize status service for /status endpoint
        self.status_service = StatusService(
            collector_manager=self.collector_manager,
            expiration_manager=self.expiration_manager,
            client=self.client,
            settings=self.settings,
            start_time=self._start_time,
            webhook_handler=self.webhook_handler,
        )

        self._startup_summary_logged = False
        self._first_collection_complete = False

        # Setup Jinja2 templates
        template_dir = Path(__file__).parent / "templates"
        self.templates = Jinja2Templates(directory=str(template_dir))

        # Setup cardinality monitor
        self.cardinality_monitor = CardinalityMonitor(
            registry=REGISTRY,
            warning_threshold=1000,
            critical_threshold=10000,
            settings=self.settings,
        )

    def _handle_shutdown(self) -> None:
        """Handle shutdown request."""
        logger.info("Shutdown requested, stopping collection...")
        self._shutdown_event.set()

    def _fastest_enabled_tier_interval_seconds(self) -> float:
        """Return the update interval of the fastest tier with an enabled collector.

        Checks tiers in FAST, MEDIUM, SLOW order and returns the interval of the
        first one that has at least one instantiated collector (see
        ``CollectorManager.collectors``). Falls back to the SLOW interval if,
        pathologically, no tier has any collectors (e.g. before startup wires
        collectors, or every collector disabled).

        This is deliberately a single, isolated helper (rather than inlining the
        loop into ``_liveness_threshold_seconds``). It anticipated the #617
        adaptive scheduler swapping in a "fastest computed group cadence" - but
        under the frozen gate model that swap is a no-op: endpoint groups never
        run faster than their owning tier's heartbeat, and a fully-gated
        collector run still completes a successful heartbeat cycle, so the
        collector success cadence (what liveness watches) remains exactly the
        tier interval. The tier derivation below therefore already IS the
        computed fastest cadence, in both ``adaptive`` and ``fixed`` scheduler
        modes; the threshold stays correct without reading the scheduler.
        ``EndpointScheduler.fastest_effective_interval_seconds()`` exists for
        diagnostics only, not for this liveness threshold (#596/#617).
        """
        manager = self.collector_manager
        for tier in (UpdateTier.FAST, UpdateTier.MEDIUM, UpdateTier.SLOW):
            if manager.collectors.get(tier):
                return float(manager.get_tier_interval(tier))
        return float(manager.get_tier_interval(UpdateTier.SLOW))

    def _liveness_threshold_seconds(self) -> float:
        """Return the dead-man staleness threshold in seconds (F-043).

        Uses ``monitoring.liveness_max_stale_seconds`` when set (>0), otherwise
        auto-derives the threshold as three times the **fastest enabled tier's**
        interval (RES-08) - so a stalled fast loop trips liveness promptly while
        slower tiers don't cause false positives. This keeps the wedge-to-restart
        window close to the metric TTL (``metric_ttl_multiplier`` x interval)
        instead of the much longer fixed SLOW-tier-derived window used previously.
        """
        configured = self.settings.monitoring.liveness_max_stale_seconds
        if configured > 0:
            return float(configured)
        return self._fastest_enabled_tier_interval_seconds() * 3.0

    def _liveness_check(self) -> tuple[bool, str]:
        """Evaluate the dead-man liveness switch (F-043).

        Returns
        -------
        tuple[bool, str]
            ``(is_wedged, reason)``. The exporter is considered wedged only once
            it has attempted collection and no collector has succeeded within the
            staleness threshold - a fully failing exporter therefore flips
            /health to 503 so Kubernetes/Docker restart it. Stays healthy during
            startup/discovery before any collection has been attempted.

        """
        manager = self.collector_manager
        if not manager.has_attempted_collection():
            return False, "starting up"

        threshold = self._liveness_threshold_seconds()
        now = time.time()
        last_success = manager.get_last_success_time()

        if last_success is None:
            stale_for = now - self._start_time
            if stale_for > threshold:
                return True, (
                    f"no collector has succeeded in {int(stale_for)}s (threshold {int(threshold)}s)"
                )
            return False, "no successful collection yet"

        stale_for = now - last_success
        if stale_for > threshold:
            return True, (
                f"last successful collection was {int(stale_for)}s ago "
                f"(threshold {int(threshold)}s)"
            )
        return False, "healthy"

    def _check_api_token(self, request: FastAPIRequest) -> None:
        """Enforce the optional bearer-token guard on state-changing endpoints (F-167).

        When ``server.api_token`` is unset (default) the control endpoints stay
        open - the exporter is assumed bound to a trusted interface, and the web
        UI trigger / DNS-clear buttons call them unauthenticated. When a token is
        configured, requests must present ``Authorization: Bearer <token>`` or
        this raises ``HTTPException(401)``.
        """
        configured = self.settings.server.api_token
        if configured is None:
            return
        expected = configured.get_secret_value()
        header = request.headers.get("authorization", "")
        scheme, _, provided = header.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="Invalid or missing API token")

    def _format_uptime(self) -> str:
        """Format uptime in a human-readable format."""
        uptime_seconds = int(time.time() - self._start_time)
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60

        if days > 0:
            return f"{days}d {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    def _get_metrics_stats(self) -> dict[str, int]:
        """Calculate total metrics and timeseries from the Prometheus registry.

        Returns
        -------
        dict[str, int]
            Dictionary containing:
            - metric_count: Total number of unique metrics
            - timeseries_count: Total number of unique time series

        """
        from prometheus_client import REGISTRY

        metric_count = 0
        timeseries_count = 0

        for metric_family in REGISTRY.collect():
            # Skip internal cardinality metrics to avoid counting monitoring of monitoring
            if metric_family.name.startswith("meraki_exporter_cardinality_"):
                continue

            metric_count += 1

            # Count all samples (time series) for this metric
            for _sample in metric_family.samples:
                timeseries_count += 1

        return {
            "metric_count": metric_count,
            "timeseries_count": timeseries_count,
        }

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        """Manage application lifecycle.

        Parameters
        ----------
        app : FastAPI
            The FastAPI application instance.

        Yields
        ------
        None
            Yields control during application runtime.

        """
        # #544: make the client's dedicated, sized SDK pool the event loop's
        # default executor. Every SDK call site already uses asyncio.to_thread
        # (which targets the default executor), so this single line routes all
        # blocking SDK work onto the bounded "meraki-sdk" pool without touching
        # the call sites; registry-serving work runs on self._serving_executor.
        asyncio.get_running_loop().set_default_executor(self.client.executor)

        # Enforce the single-organization contract (#585) BEFORE anything reads
        # org_id (inventory warm, discovery, collectors). When org_id is unset
        # and the key sees exactly one org it is auto-selected and written back
        # onto settings; a multi-org key with no org_id raises OrgResolutionError
        # here, which propagates out of lifespan startup and aborts the process
        # before it serves any request (fail fast). A configured org_id is used
        # as-is with no extra API call, so this never adds crash-loop risk to a
        # correctly-pinned single-org instance.
        await resolve_org_id(self.client.api, self.settings)

        logger.info(
            "Starting Meraki Dashboard Exporter",
            host=self.settings.server.host,
            port=self.settings.server.port,
            org_id=self.settings.meraki.org_id,
        )

        # NB: discovery is deliberately NOT awaited here (F-104). Running its
        # serial API calls before `yield` would keep uvicorn from binding, so a
        # slow/rate-limited discovery could trip the liveness probe and
        # crash-loop the pod during startup. It now runs inside the background
        # `_startup_collections` task, which already tolerates failure.

        # Start metric expiration manager (Phase 3.2)
        await self.expiration_manager.start()
        logger.info(
            "Started metric expiration manager",
            ttl_multiplier=self.settings.monitoring.metric_ttl_multiplier,
        )

        # Start background task for initial collection and tiered loops
        startup_task = asyncio.create_task(self._startup_collections())
        self._background_tasks.add(startup_task)
        startup_task.add_done_callback(self._background_tasks.discard)

        # Start periodic cardinality analysis
        cardinality_task = asyncio.create_task(self._cardinality_monitor_loop())
        self._background_tasks.add(cardinality_task)
        cardinality_task.add_done_callback(self._background_tasks.discard)

        # Start periodic exporter process self-resource sampling (#277)
        resource_metrics_task = asyncio.create_task(self._resource_metrics_loop())
        self._background_tasks.add(resource_metrics_task)
        resource_metrics_task.add_done_callback(self._background_tasks.discard)

        try:
            yield
        finally:
            logger.info("Shutting down Meraki Dashboard Exporter")
            # Signal shutdown to stop collection loop
            self._shutdown_event.set()

            # Give tasks a moment to finish their current work
            await asyncio.sleep(0.5)

            # Cancel all background tasks
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()

            # Wait for tasks to complete with a timeout
            if self._background_tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*self._background_tasks, return_exceptions=True), timeout=3.0
                    )
                except TimeoutError:
                    logger.warning("Some tasks did not complete within timeout")

            # Stop metric expiration manager (Phase 3.2)
            await self.expiration_manager.stop()
            logger.info("Stopped metric expiration manager")

            # Cleanup (client.close also shuts down the dedicated SDK executor)
            await self.client.close()
            self._serving_executor.shutdown(wait=False, cancel_futures=True)

            # Shutdown tracing
            self.tracing.shutdown()

            # Shutdown OTEL logging
            if self.settings.otel.enabled:
                self.otel_logging.shutdown()

            # Flush + shutdown the data-log emitter (#622); no-op when disabled.
            self.data_log_emitter.shutdown()

            logger.info("Shutdown complete")

    async def _startup_collections(self) -> None:
        """Start tiered collection loops immediately."""
        try:
            # Run discovery off the lifespan critical path (F-104) so /health is
            # serveable within seconds of process start. It tolerates failure.
            discovery = DiscoveryService(self.client.api, self.settings)
            try:
                self._discovery_summary = await discovery.run_discovery()
            except Exception:
                logger.exception("Discovery failed, continuing with normal operation")
                self._discovery_summary = {"errors": ["discovery_failed"]}

            # Run a sequential first collection to avoid startup bursts
            initial_collection_completed = False
            try:
                logger.info("Starting initial sequential collection")
                await self.collector_manager.collect_initial()
                self._first_collection_complete = True
                initial_collection_completed = True
                self.cardinality_monitor.mark_first_run_complete()
                logger.info("Initial collection completed")
            except Exception:
                logger.exception("Initial collection failed, continuing with tiered loops")

            # Emit one-time startup summary after discovery + initial collection
            self._log_startup_summary()

            # Start tiered collection tasks with an initial delay
            for tier in UpdateTier:
                interval = self.collector_manager.get_tier_interval(tier)
                jitter_window = min(10.0, interval * 0.1)
                jitter = random.uniform(0.0, jitter_window)
                initial_delay = (interval + jitter) if initial_collection_completed else jitter
                logger.debug(
                    "Creating tiered collection task",
                    tier=tier,
                    interval=interval,
                    initial_delay_seconds=round(initial_delay, 2),
                )
                task = asyncio.create_task(
                    self._tiered_collection_loop(tier, initial_delay=initial_delay)
                )
                self._tier_tasks[tier] = task
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

            logger.info(
                "Started all tiered collection loops",
                task_count=len(self._tier_tasks),
                tiers=list(self._tier_tasks.keys()),
            )

            # Start the adaptive scheduler resolve loop (#617). Same background-
            # task bookkeeping/shutdown pattern as the tier loops above: it
            # recomputes endpoint-group intervals from the org shape on the
            # inventory-TTL cadence and early-re-solves on AIMD budget moves.
            resolve_task = asyncio.create_task(self._scheduler_resolve_loop())
            self._background_tasks.add(resolve_task)
            resolve_task.add_done_callback(self._background_tasks.discard)

            # Wait for first collection cycle to complete (no-op if already done).
            # Track the task so lifespan shutdown cancels it instead of leaking it
            # (F-044) - mirrors the tier-loop / cardinality-loop bookkeeping.
            wait_task = asyncio.create_task(self._wait_for_first_collection())
            self._background_tasks.add(wait_task)
            wait_task.add_done_callback(self._background_tasks.discard)

        except Exception:
            logger.exception("Failed during startup collections")
            # Don't crash the server if initial collection fails

    async def _tiered_collection_loop(
        self,
        tier: UpdateTier,
        initial_delay: float = 0.0,
    ) -> None:
        """Background task for periodic metric collection for a specific tier.

        Parameters
        ----------
        tier : UpdateTier
            The update tier to run collection for.
        initial_delay : float
            Initial delay in seconds before the first collection run.

        """
        interval = self.collector_manager.get_tier_interval(tier)

        logger.debug(
            "Starting tiered collection loop",
            tier=tier,
            interval=interval,
        )

        try:
            if initial_delay > 0:
                logger.debug(
                    "Delaying initial collection",
                    tier=tier,
                    delay_seconds=round(initial_delay, 2),
                )
                remaining_delay = float(initial_delay)
                while remaining_delay > 0 and not self._shutdown_event.is_set():
                    wait_time = min(1.0, remaining_delay)
                    await asyncio.sleep(wait_time)
                    remaining_delay -= wait_time

            while not self._shutdown_event.is_set():
                # Run collection
                try:
                    cycle_start = time.monotonic()
                    logger.debug(
                        "Starting metric collection",
                        tier=tier,
                        interval=interval,
                    )
                    await self.collector_manager.collect_tier(tier)
                    logger.debug(
                        "Metric collection completed",
                        tier=tier,
                        next_run_in=interval,
                    )
                except asyncio.CancelledError:
                    logger.info("Collection loop cancelled", tier=tier)
                    raise
                except Exception:
                    # collect_tier (via CollectorManager) already swallows per-org/per-collector
                    # failures at its own boundary so sibling tiers keep running; honest health
                    # signals are surfaced via /ready (503) + failure_streak (see #509). A
                    # collect_tier exception reaching here is unexpected, so log it and keep the
                    # loop alive rather than pretend to guard against a failure count that never
                    # actually accumulates.
                    logger.exception(
                        "Error during metric collection",
                        tier=tier,
                    )

                # Wait for next collection
                elapsed = time.monotonic() - cycle_start
                wait_seconds = max(0.0, float(interval) - elapsed)
                logger.debug(
                    "Waiting for next collection",
                    tier=tier,
                    wait_seconds=round(wait_seconds, 2),
                    elapsed_seconds=round(elapsed, 2),
                )

                # Wait in small increments for responsiveness
                remaining_time = wait_seconds
                while remaining_time > 0 and not self._shutdown_event.is_set():
                    wait_time = min(1.0, remaining_time)
                    await asyncio.sleep(wait_time)
                    remaining_time -= wait_time

        except asyncio.CancelledError:
            logger.info("Collection task cancelled, exiting cleanly", tier=tier)
            raise

    async def _wait_for_first_collection(self) -> None:
        """Wait for all collectors to complete their first run."""
        if self._first_collection_complete:
            return
        # Wait for the slowest tier (SLOW) to complete once
        slow_interval = self.collector_manager.get_tier_interval(UpdateTier.SLOW)
        await asyncio.sleep(slow_interval + 5)  # Add 5 seconds buffer
        self.cardinality_monitor.mark_first_run_complete()
        self._first_collection_complete = True
        logger.info("First collection cycle complete, cardinality analysis enabled")

    def _log_startup_summary(self) -> None:
        """Log a one-time startup summary with config + discovery details."""
        if self._startup_summary_logged:
            return
        try:
            scheduling = self.collector_manager.get_scheduling_diagnostics()
            log_startup_summary(self.settings, self._discovery_summary, scheduling)
            self._startup_summary_logged = True
        except Exception:
            logger.exception("Failed to log startup summary")

    async def _cardinality_monitor_loop(self) -> None:
        """Background task for periodic cardinality monitoring."""
        # Cadence is operator-tunable via cardinality.monitor_interval_seconds (#554)
        check_interval = self.cardinality_monitor.analysis_interval_seconds

        # Wait 30 seconds after each collection cycle to ensure metrics are updated
        post_collection_delay = 30  # seconds

        logger.info(
            "Starting cardinality monitoring loop",
            check_interval=check_interval,
            post_collection_delay=post_collection_delay,
        )

        try:
            # Initial delay to let collectors run
            medium_interval = self.collector_manager.get_tier_interval(UpdateTier.MEDIUM)
            await asyncio.sleep(medium_interval + post_collection_delay)

            while not self._shutdown_event.is_set():
                try:
                    # Run cardinality analysis off the event loop - it iterates
                    # the whole registry synchronously (F-026) - on the serving
                    # pool, isolated from blocked SDK threads (#544).
                    await asyncio.get_running_loop().run_in_executor(
                        self._serving_executor, self.cardinality_monitor.analyze_cardinality
                    )
                except Exception:
                    logger.exception("Error during cardinality analysis")

                # Wait for next check
                remaining_time = float(check_interval)
                while remaining_time > 0 and not self._shutdown_event.is_set():
                    wait_time = min(1.0, remaining_time)
                    await asyncio.sleep(wait_time)
                    remaining_time -= wait_time

        except asyncio.CancelledError:
            logger.info("Cardinality monitoring task cancelled")
            raise

    async def _scheduler_resolve_loop(self) -> None:
        """Background task recomputing the adaptive scheduler's intervals (#617).

        Two cadences share one loop, checked on a fixed 60s tick:

        * **Every 60s** - ``scheduler.needs_resolve()``: an early re-solve when
          the AIMD-effective budget has moved past its hysteresis band (a 429
          burst halved it, or clean-minute recovery lifted it), so the solver
          reacts to throttling faster than the scheduled cadence.
        * **Every ``settings.scheduler.resolve_interval_seconds``** (default
          900, matching the inventory TTL): a scheduled re-solve from a fresh
          ``OrgShape`` - the "on inventory refresh" hook.

        Both paths call ``inventory.get_org_shape(org_id)`` (cached reads - zero
        extra API calls in the steady state) then the synchronous, pure-CPU
        ``scheduler.resolve(shape)``. Exceptions are swallowed and logged so a
        transient inventory/solve failure never kills the loop; shutdown is
        honoured with the same 1s-increment interruptible wait as the tier
        loops, and cancellation exits cleanly.

        The initial resolve already ran inside ``collect_initial`` (the manager
        lane), so this loop deliberately does not re-solve on entry - the first
        60s tick only re-solves if AIMD already moved the budget.
        """
        scheduler = self.collector_manager.scheduler
        inventory = self.collector_manager.inventory
        org_id = self.settings.meraki.org_id
        if org_id is None:
            logger.warning("Scheduler resolve loop: no org_id resolved; not starting")
            return

        resolve_interval = float(self.settings.scheduler.resolve_interval_seconds)
        check_interval = 60.0

        async def _do_resolve() -> None:
            shape = await inventory.get_org_shape(org_id)
            scheduler.resolve(shape)

        logger.debug(
            "Starting scheduler resolve loop",
            resolve_interval_seconds=resolve_interval,
            check_interval_seconds=check_interval,
        )

        seconds_since_resolve = 0.0
        try:
            while not self._shutdown_event.is_set():
                try:
                    if seconds_since_resolve >= resolve_interval:
                        await _do_resolve()
                        seconds_since_resolve = 0.0
                    elif scheduler.needs_resolve():
                        logger.info("Scheduler re-solving early on AIMD budget change")
                        await _do_resolve()
                        seconds_since_resolve = 0.0
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Scheduler resolve loop iteration failed")

                # Interruptible wait in 1s increments (mirrors the tier loops).
                remaining_time = check_interval
                while remaining_time > 0 and not self._shutdown_event.is_set():
                    wait_time = min(1.0, remaining_time)
                    await asyncio.sleep(wait_time)
                    remaining_time -= wait_time
                seconds_since_resolve += check_interval

        except asyncio.CancelledError:
            logger.info("Scheduler resolve loop cancelled")
            raise

    def _sample_resource_metrics(self) -> None:
        """Sample the exporter's own RSS + CPU usage and update the gauges (#277).

        Cheap, synchronous psutil reads (no I/O, no event-loop blocking risk) -
        errors (e.g. the process handle becoming invalid) are logged and
        swallowed so a transient psutil failure never takes down the sampling
        loop or the exporter itself.
        """
        try:
            memory_bytes = self._resource_process.memory_info().rss
            cpu_percent = self._resource_process.cpu_percent()
        except Exception:
            logger.exception("Failed to sample exporter process resource metrics")
            return
        self._resource_memory_gauge.set(memory_bytes)
        self._resource_cpu_gauge.set(cpu_percent)

    async def _resource_metrics_loop(self) -> None:
        """Background task periodically sampling exporter process resources (#277).

        Deliberately not a full collector tier - just a fixed-cadence psutil
        sample (RSS + CPU percent) feeding two unlabeled singleton gauges.
        ``psutil.Process.cpu_percent()``'s first call always returns 0.0 (no
        prior sample to diff against), so it is primed here - once, before the
        loop's first real reading - regardless of whether shutdown is already
        signalled.
        """
        try:
            self._resource_process.cpu_percent()  # prime; see docstring
        except Exception:
            logger.exception("Failed to prime exporter resource metrics sampler")

        try:
            while not self._shutdown_event.is_set():
                self._sample_resource_metrics()

                remaining_time = float(self._resource_metrics_interval_seconds)
                while remaining_time > 0 and not self._shutdown_event.is_set():
                    wait_time = min(1.0, remaining_time)
                    await asyncio.sleep(wait_time)
                    remaining_time -= wait_time
        except asyncio.CancelledError:
            logger.info("Resource metrics sampling task cancelled")
            raise

    def create_app(self) -> FastAPI:
        """Create the FastAPI application.

        Returns
        -------
        FastAPI
            The configured FastAPI application.

        """
        app = FastAPI(
            title="Meraki Dashboard Exporter",
            description="Prometheus exporter for Cisco Meraki Dashboard metrics",
            version=__version__,
            lifespan=self.lifespan,
        )

        # Instrument FastAPI with tracing
        self.tracing.instrument_fastapi(app)

        # Store reference to templates in app state
        app.state.templates = self.templates
        app.state.exporter = self

        @app.middleware("http")
        async def _ui_exposure_guard(
            request: Request,
            call_next: Any,
        ) -> Response:
            """Gate sensitive GET UIs by ui_enabled + optional bearer token (#558).

            Default posture is unchanged (open) unless the operator sets
            ``server.api_token`` (token-gate) or ``server.ui_enabled=false``
            (suppress the human UI). ``/metrics`` and the probes stay open.
            """
            api_token_setting = self.settings.server.api_token
            decision = ui_guard_decision(
                method=request.method,
                path=request.url.path,
                # TODO(CFG-BIG): server.ui_enabled lands with the config sweep;
                # getattr keeps the default (True = UI enabled) until then.
                ui_enabled=getattr(self.settings.server, "ui_enabled", True),
                api_token=(
                    api_token_setting.get_secret_value() if api_token_setting is not None else None
                ),
                auth_header=request.headers.get("authorization", ""),
            )
            if decision is not None:
                status_code, detail = decision
                return JSONResponse(status_code=status_code, content={"detail": detail})
            return await call_next(request)  # type: ignore[no-any-return]

        @app.get("/", response_class=HTMLResponse)
        async def root(request: Request) -> HTMLResponse:
            """Root endpoint with HTML landing page."""
            # Get exporter instance from app state
            exporter = app.state.exporter

            # Get collector information with health status
            collectors = []
            for tier, collector_list in exporter.collector_manager.collectors.items():
                for collector in collector_list:
                    # Only show active collectors
                    if collector.is_active:
                        collector_name = collector.__class__.__name__
                        health = exporter.collector_manager.collector_health.get(collector_name, {})

                        # Calculate success rate
                        total_runs = health.get("total_runs", 0)
                        total_successes = health.get("total_successes", 0)
                        success_rate = (
                            (total_successes / total_runs * 100) if total_runs > 0 else 0.0
                        )

                        # Calculate last success age
                        last_success_time = health.get("last_success_time")
                        if last_success_time:
                            last_success_age = int(time.time() - last_success_time)
                            if last_success_age < 60:
                                last_success_str = f"{last_success_age}s ago"
                            elif last_success_age < 3600:
                                last_success_str = f"{last_success_age // 60}m ago"
                            else:
                                last_success_str = f"{last_success_age // 3600}h ago"
                        else:
                            last_success_str = "Never"

                        collectors.append({
                            "name": collector_name.replace("Collector", ""),
                            "key": collector_name,
                            "tier": tier.value.upper(),
                            "failure_streak": health.get("failure_streak", 0),
                            "success_rate": f"{success_rate:.1f}",
                            "last_success": last_success_str,
                            "total_runs": total_runs,
                            "is_running": exporter.collector_manager.is_collector_running(
                                collector_name
                            ),
                        })

            # Get skipped collectors
            skipped_collectors = exporter.collector_manager.skipped_collectors

            # Get organization count (if available)
            org_count = 1 if exporter.settings.meraki.org_id else "All"

            # Get real-time metrics stats. This iterates the whole registry
            # synchronously, so offload it to the serving pool (F-026/#544).
            metrics_stats = await asyncio.get_running_loop().run_in_executor(
                exporter._serving_executor, exporter._get_metrics_stats
            )
            scheduling = exporter.collector_manager.get_scheduling_diagnostics()

            context = {
                "version": __version__,
                "uptime": exporter._format_uptime(),
                "collector_count": len(collectors),
                "org_count": org_count,
                "metric_count": metrics_stats["metric_count"],
                "timeseries_count": metrics_stats["timeseries_count"],
                "collectors": collectors,
                "skipped_collectors": skipped_collectors,
                "fast_interval": exporter.settings.update_intervals.fast,
                "medium_interval": exporter.settings.update_intervals.medium,
                "slow_interval": exporter.settings.update_intervals.slow,
                "org_id": exporter.settings.meraki.org_id,
                "scheduling": scheduling,
            }

            return app.state.templates.TemplateResponse(request, "index.html", context=context)  # type: ignore[no-any-return]

        @app.get("/health")
        async def health() -> JSONResponse:
            """Liveness endpoint with a dead-man switch (F-043).

            Returns 200 while the exporter is starting up or collecting
            successfully, and 503 once it is wedged - no collector has succeeded
            within the liveness staleness threshold - so Kubernetes/Docker
            restart the pod instead of leaving it serving stale/empty metrics.
            """
            exporter = app.state.exporter
            wedged, reason = exporter._liveness_check()
            if wedged:
                logger.error("Liveness dead-man switch tripped", reason=reason)
                return JSONResponse(
                    status_code=503,
                    content={"status": "unhealthy", "reason": reason},
                )
            return JSONResponse(status_code=200, content={"status": "healthy"})

        @app.get("/ready")
        async def readiness() -> JSONResponse:
            """Readiness probe - returns 200 when initial collection is complete.

            Returns 503 until both FAST and MEDIUM collection tiers have completed
            their first cycle. SLOW tier is excluded to avoid blocking Kubernetes
            readiness probes for up to 900s.
            """
            exporter = app.state.exporter
            manager = exporter.collector_manager
            status = manager.get_readiness_status()

            if status["ready"]:
                return JSONResponse(status_code=200, content=status)
            return JSONResponse(status_code=503, content=status)

        @app.get("/metrics", response_class=Response)
        async def metrics() -> Response:
            """Prometheus metrics endpoint."""
            # Offload the synchronous registry serialization to the dedicated
            # serving pool so a large registry does not block the event loop
            # (F-026) and scrapes never queue behind blocked SDK threads (#544:
            # the default executor is the bounded meraki-sdk pool).
            # prometheus_client's registry is thread-safe.
            exporter = app.state.exporter
            data = await asyncio.get_running_loop().run_in_executor(
                exporter._serving_executor, generate_latest, REGISTRY
            )

            return Response(
                content=data,
                media_type=CONTENT_TYPE_LATEST,
            )

        # Setup cardinality monitoring endpoint
        setup_cardinality_endpoint(app, self.cardinality_monitor)

        @app.get("/clients", response_class=HTMLResponse)
        async def clients(request: Request) -> HTMLResponse:
            """Client data visualization endpoint."""
            # Get exporter instance from app state
            exporter = app.state.exporter

            # Check if client collection is enabled
            if not exporter.settings.clients.enabled:
                return HTMLResponse(
                    content="<h1>Client data collection is disabled</h1>"
                    "<p>Set MERAKI_EXPORTER_CLIENTS__ENABLED=true to enable.</p>",
                    status_code=404,
                )

            # Get client store and DNS resolver from collector
            client_store = None
            dns_resolver = None
            for collector in exporter.collector_manager.collectors[UpdateTier.MEDIUM]:
                if collector.__class__.__name__ == "ClientsCollector" and collector.is_active:
                    client_store = getattr(collector, "client_store", None)
                    dns_resolver = getattr(collector, "dns_resolver", None)
                    break

            if not client_store:
                return HTMLResponse(
                    content="<h1>Client collector not found</h1>",
                    status_code=500,
                )

            # Get all clients
            all_clients = client_store.get_all_clients()

            # Sort by network and then by description/hostname
            all_clients.sort(key=lambda c: (c.networkName or "", c.display_name))

            # Group by network
            clients_by_network: dict[str, list[Any]] = {}
            for client in all_clients:
                network_key = f"{client.networkName or 'Unknown'} ({client.networkId or 'Unknown'})"
                if network_key not in clients_by_network:
                    clients_by_network[network_key] = []
                clients_by_network[network_key].append(client)

            # Get statistics
            stats = client_store.get_statistics()

            # Get DNS cache statistics
            dns_cache_stats = dns_resolver.get_cache_stats() if dns_resolver else {}

            context = {
                "version": __version__,
                "clients_by_network": clients_by_network,
                "total_clients": stats["total_clients"],
                "online_clients": stats["online_clients"],
                "offline_clients": stats["offline_clients"],
                "network_count": stats["total_networks"],
                "cache_ttl": exporter.settings.clients.cache_ttl,
                "dns_cache_stats": dns_cache_stats,
            }

            return app.state.templates.TemplateResponse(request, "clients.html", context=context)  # type: ignore[no-any-return]

        @app.get("/status", response_class=HTMLResponse)
        async def status(request: Request, format: str | None = None) -> Response:  # noqa: A002
            """Exporter self-health status dashboard."""
            exporter = app.state.exporter
            snapshot = exporter.status_service.get_snapshot()

            if format == "json":
                return JSONResponse(content=snapshot.to_dict())

            return app.state.templates.TemplateResponse(  # type: ignore[no-any-return]
                request,
                "status.html",
                context=snapshot.to_dict(),
            )

        @app.get("/config")
        async def config_view() -> JSONResponse:
            """Redacted effective-configuration view (#312).

            Returns the resolved settings as JSON with all secrets masked (see
            ``build_effective_config``). Gated as a sensitive GET by the
            ui-exposure middleware (ui_enabled + optional bearer token).
            """
            exporter = app.state.exporter
            return JSONResponse(content=build_effective_config(exporter.settings))

        @app.post("/api/clients/clear-dns-cache")
        async def clear_dns_cache(request: FastAPIRequest) -> dict[str, str]:
            """Clear the DNS cache."""
            # Get exporter instance from app state
            exporter = app.state.exporter

            # Optional bearer-token guard (F-167)
            exporter._check_api_token(request)

            # Check if client collection is enabled
            if not exporter.settings.clients.enabled:
                return {"status": "error", "message": "Client collection is disabled"}

            # Get DNS resolver from collector
            dns_resolver = None
            for collector in exporter.collector_manager.collectors[UpdateTier.MEDIUM]:
                if collector.__class__.__name__ == "ClientsCollector" and collector.is_active:
                    dns_resolver = getattr(collector, "dns_resolver", None)
                    break

            if not dns_resolver:
                return {"status": "error", "message": "DNS resolver not found"}

            # Clear the cache
            dns_resolver.clear_cache()
            return {"status": "success", "message": "DNS cache cleared"}

        @app.post("/api/collectors/trigger")
        async def trigger_collector(
            request: FastAPIRequest,
            payload: CollectorTriggerRequest,
        ) -> dict[str, str]:
            """Trigger a collector run on-demand."""
            exporter = app.state.exporter

            # Optional bearer-token guard (F-167)
            exporter._check_api_token(request)

            result = exporter.collector_manager.get_collector_by_name(payload.collector)
            if result is None:
                return {
                    "status": "error",
                    "message": f"Collector '{payload.collector}' not found",
                }

            collector, tier = result
            collector_name = collector.__class__.__name__
            if not collector.is_active:
                return {
                    "status": "error",
                    "message": f"Collector '{collector_name}' is disabled",
                }

            if exporter.collector_manager.is_collector_running(collector_name):
                return {
                    "status": "running",
                    "message": f"Collector '{collector_name}' is already running",
                }

            task = asyncio.create_task(
                exporter.collector_manager.run_collector_once(collector, tier),
                name=f"manual_{collector_name}",
            )
            exporter._background_tasks.add(task)
            task.add_done_callback(exporter._background_tasks.discard)

            return {
                "status": "started",
                "message": f"Collector '{collector_name}' triggered",
            }

        @app.post("/api/webhooks/meraki")
        async def webhook_receiver(request: FastAPIRequest) -> dict[str, str]:
            """Meraki webhook receiver endpoint.

            This endpoint receives and processes webhook events from Meraki Dashboard.
            Events are validated and tracked via Prometheus metrics.

            Parameters
            ----------
            request : FastAPIRequest
                The incoming webhook request.

            Returns
            -------
            dict[str, str]
                Status response.

            Raises
            ------
            HTTPException
                If webhooks are disabled, validation fails, or processing errors occur.

            """
            # Get exporter instance from app state
            exporter = app.state.exporter

            # Check if webhooks are enabled
            if not exporter.settings.webhooks.enabled or not exporter.webhook_handler:
                raise HTTPException(
                    status_code=404,
                    detail="Webhook receiver is not enabled",
                )

            # Validate content type
            content_type = request.headers.get("content-type", "")
            if "application/json" not in content_type:
                logger.warning(
                    "Invalid content type for webhook",
                    content_type=content_type,
                )
                exporter.webhook_handler.record_validation_failure("invalid_content_type")
                raise HTTPException(
                    status_code=400,
                    detail="Content-Type must be application/json",
                )

            # Read the body while enforcing a hard byte cap regardless of the
            # Content-Length header (F-103). A chunked / Content-Length-absent
            # request must not be able to buffer an unbounded body before the
            # shared secret is validated, so we stream and abort the moment the
            # accumulated size exceeds the configured maximum. The early
            # Content-Length short-circuit below is a cheap fast-reject; the
            # streaming counter is the authoritative guard.
            max_size = exporter.settings.webhooks.max_payload_size

            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    declared_size = int(content_length)
                except ValueError:
                    declared_size = 0
                if declared_size > max_size:
                    logger.warning(
                        "Webhook payload too large",
                        size=declared_size,
                        max_size=max_size,
                    )
                    exporter.webhook_handler.record_validation_failure("payload_too_large")
                    raise HTTPException(
                        status_code=413,
                        detail=f"Payload too large (max: {max_size} bytes)",
                    )

            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > max_size:
                    logger.warning(
                        "Webhook payload too large",
                        size=len(body),
                        max_size=max_size,
                    )
                    exporter.webhook_handler.record_validation_failure("payload_too_large")
                    raise HTTPException(
                        status_code=413,
                        detail=f"Payload too large (max: {max_size} bytes)",
                    )

            # Parse JSON body from the (size-capped) buffer.
            try:
                payload_data = json.loads(bytes(body))
            except Exception as e:
                logger.error("Failed to parse webhook JSON", error=str(e))
                exporter.webhook_handler.record_validation_failure("invalid_json")
                raise HTTPException(
                    status_code=400,
                    detail="Invalid JSON payload",
                ) from e

            # Process webhook
            payload = exporter.webhook_handler.process_webhook(payload_data)

            if payload is None:
                # Processing failed (validation or secret mismatch)
                raise HTTPException(
                    status_code=401,
                    detail="Webhook validation failed",
                )

            # Return success
            return {"status": "success", "message": "Webhook processed"}

        return app


# Global app instance to prevent multiple initializations
_app_instance: FastAPI | None = None


def create_app() -> FastAPI:
    """Create the FastAPI application with default settings.

    Returns
    -------
    FastAPI
        The configured FastAPI application.

    """
    global _app_instance
    if _app_instance is None:
        exporter = ExporterApp()
        _app_instance = exporter.create_app()
    assert _app_instance is not None  # Type checker hint
    return _app_instance
