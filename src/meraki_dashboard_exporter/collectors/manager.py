"""Collector manager for coordinating metric collection."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..core.logging import get_logger

if TYPE_CHECKING:
    from ..api.client import AsyncMerakiClient
    from ..core.collector import MetricCollector
    from ..core.config import Settings

logger = get_logger(__name__)


class CollectorManager:
    """Manages and coordinates metric collectors.

    Parameters
    ----------
    client : AsyncMerakiClient
        Meraki API client.
    settings : Settings
        Application settings.

    """

    def __init__(self, client: AsyncMerakiClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.collectors: list[MetricCollector] = []
        self._initialize_collectors()

    def _initialize_collectors(self) -> None:
        """Initialize all enabled collectors."""
        # Import here to avoid circular imports
        from .device import DeviceCollector
        from .organization import OrganizationCollector

        # Always collect organization metrics
        self.collectors.append(
            OrganizationCollector(
                api=self.client.api,
                settings=self.settings,
            )
        )
        logger.info("Initialized organization collector")

        # Initialize device collector if any device types are specified
        if self.settings.device_types:
            self.collectors.append(
                DeviceCollector(
                    api=self.client.api,
                    settings=self.settings,
                )
            )
            logger.info(
                "Initialized device collector",
                device_types=self.settings.device_types,
            )

    async def collect_all(self) -> None:
        """Run all collectors concurrently."""
        if not self.collectors:
            logger.warning("No collectors initialized")
            return

        # Run all collectors concurrently
        tasks = [collector.collect() for collector in self.collectors]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log any errors
        for collector, result in zip(self.collectors, results, strict=False):
            if isinstance(result, Exception):
                logger.error(
                    "Collector failed",
                    collector=collector.__class__.__name__,
                    error=str(result),
                )

    def register_collector(self, collector: MetricCollector) -> None:
        """Register an additional collector.

        Parameters
        ----------
        collector : MetricCollector
            The collector to register.

        """
        self.collectors.append(collector)
        logger.info(
            "Registered collector",
            collector=collector.__class__.__name__,
        )
