"""FastAPI application for the Meraki Dashboard Exporter."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Response
from fastapi import Request as FastAPIRequest
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from starlette.requests import Request

from .__version__ import __version__
from .api.client import AsyncMerakiClient
from .collectors.manager import CollectorManager
from .core.cardinality import CardinalityMonitor, setup_cardinality_endpoint
from .core.config import Settings
from .core.config_logger import log_startup_summary
from .core.constants import UpdateTier
from .core.discovery import DiscoveryService
from .core.logging import get_logger, setup_logging
from .core.metric_expiration import MetricExpirationManager
from .core.metrics_filter import FilteredRegistry, MetricsFilter
from .core.otel_logging import OTELLoggingConfig
from .core.otel_metrics import PrometheusToOTelBridge
from .core.otel_tracing import TracingConfig
from .core.webhook_handler import WebhookHandler

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


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

        self.client = AsyncMerakiClient(self.settings)

        # Initialize metric expiration manager (Phase 3.2)
        self.expiration_manager = MetricExpirationManager(settings=self.settings)

        self.collector_manager = CollectorManager(
            client=self.client,
            settings=self.settings,
            expiration_manager=self.expiration_manager,
        )

        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._shutdown_event = asyncio.Event()
        self._tier_tasks: dict[str, asyncio.Task[Any]] = {}
        self._start_time = time.time()
        self._discovery_summary: dict[str, Any] | None = None
        self._startup_summary_logged = False
        self._first_collection_complete = False

        # Setup Jinja2 templates
        template_dir = Path(__file__).parent / "templates"
        self.templates = Jinja2Templates(directory=str(template_dir))

        # Setup OTEL bridge if enabled and metrics are configured for OTEL export
        self.otel_bridge: PrometheusToOTelBridge | None = None
        otel_settings = self.settings.otel
        if otel_settings.enabled and otel_settings.endpoint:
            # Check if any metrics are configured for OTEL export
            should_export_to_otel = (
                otel_settings.export_meraki_metrics_to_otel
                or otel_settings.export_exporter_metrics_to_otel
            )

            if should_export_to_otel:
                # Get allowlist and blocklist based on configuration
                allowlist = MetricsFilter.get_otel_allowlist(otel_settings)
                blocklist = MetricsFilter.get_otel_blocklist(otel_settings)

                self.otel_bridge = PrometheusToOTelBridge(
                    registry=REGISTRY,
                    endpoint=otel_settings.endpoint,
                    service_name=otel_settings.service_name,
                    export_interval_seconds=otel_settings.export_interval,
                    resource_attributes=otel_settings.resource_attributes,
                    metric_allowlist=allowlist,
                    metric_blocklist=blocklist,
                )
                logger.info(
                    "OTEL metrics bridge configured",
                    allowlist=allowlist,
                    blocklist=blocklist,
                )
            else:
                logger.info(
                    "OTEL enabled but no metrics configured for export",
                    tracing_enabled=otel_settings.tracing_enabled,
                )

        # Setup cardinality monitor
        self.cardinality_monitor = CardinalityMonitor(
            registry=REGISTRY,
            warning_threshold=1000,
            critical_threshold=10000,
        )

        # Setup webhook handler
        self.webhook_handler: WebhookHandler | None = None
        if self.settings.webhooks.enabled:
            self.webhook_handler = WebhookHandler(self.settings)
            logger.info(
                "Webhook receiver enabled",
                require_secret=self.settings.webhooks.require_secret,
            )

    def _handle_shutdown(self) -> None:
        """Handle shutdown request."""
        logger.info("Shutdown requested, stopping collection...")
        self._shutdown_event.set()

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
        logger.info(
            "Starting Meraki Dashboard Exporter",
            host=self.settings.server.host,
            port=self.settings.server.port,
            org_id=self.settings.meraki.org_id,
        )

        # Run discovery to log environment information once at startup
        discovery = DiscoveryService(self.client.api, self.settings)
        try:
            self._discovery_summary = await discovery.run_discovery()
        except Exception:
            logger.exception("Discovery failed, continuing with normal operation")
            self._discovery_summary = {"errors": ["discovery_failed"]}

        # Start OTEL bridge if enabled
        if self.otel_bridge:
            await self.otel_bridge.start()
            logger.info(
                "Started OpenTelemetry metric export",
                endpoint=self.settings.otel.endpoint,
                interval=self.settings.otel.export_interval,
            )

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

            # Stop OTEL bridge if running
            if self.otel_bridge:
                await self.otel_bridge.stop()
                logger.info("Stopped OpenTelemetry metric export")

            # Stop metric expiration manager (Phase 3.2)
            await self.expiration_manager.stop()
            logger.info("Stopped metric expiration manager")

            # Cleanup
            await self.client.close()

            # Shutdown tracing
            self.tracing.shutdown()

            # Shutdown OTEL logging
            if self.settings.otel.enabled:
                self.otel_logging.shutdown()

            logger.info("Shutdown complete")

    async def _startup_collections(self) -> None:
        """Start tiered collection loops immediately."""
        try:
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

            # Wait for first collection cycle to complete (no-op if already done)
            asyncio.create_task(self._wait_for_first_collection())

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
        consecutive_failures = 0
        max_consecutive_failures = 10
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
                    # Reset failure counter on success
                    consecutive_failures = 0
                except asyncio.CancelledError:
                    logger.info("Collection loop cancelled", tier=tier)
                    raise
                except Exception:
                    consecutive_failures += 1
                    logger.exception(
                        "Error during metric collection",
                        tier=tier,
                        consecutive_failures=consecutive_failures,
                        max_consecutive_failures=max_consecutive_failures,
                    )

                    # Only exit if we have too many consecutive failures
                    if consecutive_failures >= max_consecutive_failures:
                        logger.critical(
                            "Too many consecutive collection failures, exiting",
                            tier=tier,
                            consecutive_failures=consecutive_failures,
                        )
                        self._shutdown_event.set()
                        raise

                # Wait for next collection
                logger.debug(
                    "Waiting for next collection",
                    tier=tier,
                    wait_seconds=interval,
                )

                # Wait in small increments for responsiveness
                remaining_time = float(interval)
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
            log_startup_summary(self.settings, self._discovery_summary)
            self._startup_summary_logged = True
        except Exception:
            logger.exception("Failed to log startup summary")

    async def _cardinality_monitor_loop(self) -> None:
        """Background task for periodic cardinality monitoring."""
        # Check cardinality every 5 minutes
        check_interval = 300  # 5 minutes

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
                    # Run cardinality analysis
                    self.cardinality_monitor.analyze_cardinality()
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
                            "tier": tier.value.upper(),
                            "failure_streak": health.get("failure_streak", 0),
                            "success_rate": f"{success_rate:.1f}",
                            "last_success": last_success_str,
                            "total_runs": total_runs,
                        })

            # Get skipped collectors
            skipped_collectors = exporter.collector_manager.skipped_collectors

            # Get organization count (if available)
            org_count = 1 if exporter.settings.meraki.org_id else "All"

            # Get real-time metrics stats
            metrics_stats = exporter._get_metrics_stats()

            context = {
                "request": request,
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
            }

            return app.state.templates.TemplateResponse("index.html", context)  # type: ignore[no-any-return]

        @app.get("/health")
        async def health() -> dict[str, str]:
            """Health check endpoint."""
            return {"status": "healthy"}

        @app.get("/metrics", response_class=Response)
        async def metrics() -> Response:
            """Prometheus metrics endpoint with filtering based on configuration."""
            exporter = app.state.exporter

            # Use filtered registry to respect export configuration
            filtered_registry = FilteredRegistry(REGISTRY, exporter.settings.otel)
            # FilteredRegistry implements collect() interface required by generate_latest
            data = generate_latest(filtered_registry)  # type: ignore[arg-type]

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
                "request": request,
                "version": __version__,
                "clients_by_network": clients_by_network,
                "total_clients": stats["total_clients"],
                "online_clients": stats["online_clients"],
                "offline_clients": stats["offline_clients"],
                "network_count": stats["total_networks"],
                "cache_ttl": exporter.settings.clients.cache_ttl,
                "dns_server": exporter.settings.clients.dns_server or "System Default",
                "dns_cache_stats": dns_cache_stats,
            }

            return app.state.templates.TemplateResponse("clients.html", context)  # type: ignore[no-any-return]

        @app.post("/api/clients/clear-dns-cache")
        async def clear_dns_cache() -> dict[str, str]:
            """Clear the DNS cache."""
            # Get exporter instance from app state
            exporter = app.state.exporter

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
                exporter.webhook_handler.validation_failures.labels(
                    validation_error="invalid_content_type"
                ).inc()
                raise HTTPException(
                    status_code=400,
                    detail="Content-Type must be application/json",
                )

            # Check payload size
            content_length = request.headers.get("content-length")
            if content_length:
                size = int(content_length)
                max_size = exporter.settings.webhooks.max_payload_size
                if size > max_size:
                    logger.warning(
                        "Webhook payload too large",
                        size=size,
                        max_size=max_size,
                    )
                    exporter.webhook_handler.validation_failures.labels(
                        validation_error="payload_too_large"
                    ).inc()
                    raise HTTPException(
                        status_code=413,
                        detail=f"Payload too large (max: {max_size} bytes)",
                    )

            # Parse JSON body
            try:
                payload_data = await request.json()
            except Exception as e:
                logger.error("Failed to parse webhook JSON", error=str(e))
                exporter.webhook_handler.validation_failures.labels(
                    validation_error="invalid_json"
                ).inc()
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
