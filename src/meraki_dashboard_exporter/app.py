"""FastAPI application for the Meraki Dashboard Exporter."""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

from .api.client import AsyncMerakiClient
from .collectors.manager import CollectorManager
from .core.config import Settings
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
        self.settings = settings or Settings()
        setup_logging(self.settings)

        self.client = AsyncMerakiClient(self.settings)
        self.collector_manager = CollectorManager(
            client=self.client,
            settings=self.settings,
        )

        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._shutdown_event = asyncio.Event()
        self._force_shutdown = False
        self._shutdown_count = 0

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals.

        Parameters
        ----------
        signum : int
            Signal number.
        frame : Any
            Current stack frame.

        """
        self._shutdown_count += 1

        if self._shutdown_count == 1:
            logger.info("Received shutdown signal, starting graceful shutdown...")
            self._shutdown_event.set()
        elif self._shutdown_count == 2:
            logger.warning("Received second shutdown signal, forcing shutdown...")
            self._force_shutdown = True
            # Force exit after a short delay if tasks don't complete
            asyncio.create_task(self._force_exit())
        else:
            logger.error("Multiple shutdown signals received, terminating immediately!")
            os._exit(1)

    async def _force_exit(self) -> None:
        """Force exit after a delay if graceful shutdown fails."""
        await asyncio.sleep(2)
        if self._force_shutdown:
            logger.error("Forced shutdown after timeout")
            os._exit(1)

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
        # Set up signal handlers
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._handle_signal)

        logger.info(
            "Starting Meraki Dashboard Exporter",
            host=self.settings.host,
            port=self.settings.port,
            org_id=self.settings.org_id,
        )

        # Start background collection task
        collection_task = asyncio.create_task(self._collection_loop())
        self._background_tasks.add(collection_task)
        collection_task.add_done_callback(self._background_tasks.discard)

        try:
            yield
        finally:
            logger.info("Shutting down Meraki Dashboard Exporter")
            self._shutdown_event.set()

            # Cancel all background tasks
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()

            # Wait for tasks to complete with a timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._background_tasks, return_exceptions=True),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("Some tasks did not complete within timeout")

            # Cleanup
            await self.client.close()

    async def _collection_loop(self) -> None:
        """Background task for periodic metric collection."""
        consecutive_failures = 0
        max_consecutive_failures = 10

        while not self._shutdown_event.is_set():
            try:
                logger.info("Starting metric collection")
                await self.collector_manager.collect_all()
                logger.info("Metric collection completed")
                # Reset failure counter on success
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                logger.exception(
                    "Error during metric collection",
                    consecutive_failures=consecutive_failures,
                    max_consecutive_failures=max_consecutive_failures,
                )

                # Only exit if we have too many consecutive failures (indicating a systemic issue)
                if consecutive_failures >= max_consecutive_failures:
                    logger.critical(
                        "Too many consecutive collection failures, exiting",
                        consecutive_failures=consecutive_failures,
                    )
                    self._shutdown_event.set()
                    raise

            # Wait for next collection or shutdown
            # Check for shutdown every second for responsiveness
            remaining_time = self.settings.scrape_interval
            while remaining_time > 0 and not self._shutdown_event.is_set():
                wait_time = min(1.0, remaining_time)
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=wait_time,
                    )
                    break  # Shutdown event was set
                except asyncio.TimeoutError:
                    remaining_time -= wait_time
                    continue

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
            version="0.1.0",
            lifespan=self.lifespan,
        )

        @app.get("/")
        async def root() -> dict[str, str]:
            """Root endpoint."""
            return {
                "name": "Meraki Dashboard Exporter",
                "version": "0.1.0",
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


def create_app() -> FastAPI:
    """Create the FastAPI application with default settings.

    Returns
    -------
    FastAPI
        The configured FastAPI application.

    """
    exporter = ExporterApp()
    return exporter.create_app()
