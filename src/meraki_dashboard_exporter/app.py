"""FastAPI application for the Meraki Dashboard Exporter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

from .__version__ import __version__
from .api.client import AsyncMerakiClient
from .collectors.manager import CollectorManager
from .core.config import Settings
from .core.constants import UpdateTier
from .core.discovery import DiscoveryService
from .core.logging import get_logger, setup_logging

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

        self.client = AsyncMerakiClient(self.settings)
        self.collector_manager = CollectorManager(
            client=self.client,
            settings=self.settings,
        )

        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._shutdown_event = asyncio.Event()
        self._tier_tasks: dict[str, asyncio.Task[Any]] = {}

    def _handle_shutdown(self) -> None:
        """Handle shutdown request."""
        logger.info("Shutdown requested, stopping collection...")
        self._shutdown_event.set()

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
            host=self.settings.host,
            port=self.settings.port,
            org_id=self.settings.org_id,
        )

        # Run discovery to log environment information once at startup
        discovery = DiscoveryService(self.client.api, self.settings)
        try:
            await discovery.run_discovery()
        except Exception:
            logger.exception("Discovery failed, continuing with normal operation")

        # Start background task for initial collection and tiered loops
        startup_task = asyncio.create_task(self._startup_collections())
        self._background_tasks.add(startup_task)
        startup_task.add_done_callback(self._background_tasks.discard)

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

            # Cleanup
            await self.client.close()
            logger.info("Shutdown complete")

    async def _startup_collections(self) -> None:
        """Start tiered collection loops immediately."""
        try:
            # Start tiered collection tasks immediately
            # Each will do its first collection right away
            for tier in UpdateTier:
                interval = self.collector_manager.get_tier_interval(tier)
                logger.debug(
                    "Creating tiered collection task",
                    tier=tier,
                    interval=interval,
                )
                # Start with immediate collection (no initial wait)
                task = asyncio.create_task(self._tiered_collection_loop(tier))
                self._tier_tasks[tier] = task
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

            logger.info(
                "Started all tiered collection loops",
                task_count=len(self._tier_tasks),
                tiers=list(self._tier_tasks.keys()),
            )

        except Exception:
            logger.exception("Failed during startup collections")
            # Don't crash the server if initial collection fails

    async def _tiered_collection_loop(self, tier: UpdateTier) -> None:
        """Background task for periodic metric collection for a specific tier.

        Parameters
        ----------
        tier : UpdateTier
            The update tier to run collection for.

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

        @app.get("/")
        async def root() -> dict[str, str]:
            """Root endpoint."""
            return {
                "name": "Meraki Dashboard Exporter",
                "version": __version__,
                "metrics_path": "/metrics",
            }

        @app.get("/health")
        async def health() -> dict[str, str]:
            """Health check endpoint."""
            return {"status": "healthy"}

        @app.get("/metrics", response_class=Response)
        async def metrics() -> Response:
            """Prometheus metrics endpoint."""
            data = generate_latest(REGISTRY)
            return Response(
                content=data,
                media_type=CONTENT_TYPE_LATEST,
            )

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
