"""Collector manager for coordinating metric collection."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..core.constants import UpdateTier
from ..core.logging import get_logger

if TYPE_CHECKING:
    from ..api.client import AsyncMerakiClient
    from ..core.collector import MetricCollector
    from ..core.config import Settings

logger = get_logger(__name__)


class CollectorManager:
    """Manages and coordinates metric collectors with tiered update intervals.

    Parameters
    ----------
    client : AsyncMerakiClient
        Meraki API client.
    settings : Settings
        Application settings.

    """

    def __init__(self, client: AsyncMerakiClient, settings: Settings) -> None:
        """Initialize the collector manager with client and settings."""
        self.client = client
        self.settings = settings
        self.collectors: dict[UpdateTier, list[MetricCollector]] = {
            UpdateTier.FAST: [],
            UpdateTier.MEDIUM: [],
        }
        self._initialize_collectors()

    def _initialize_collectors(self) -> None:
        """Initialize all enabled collectors."""
        # Import here to avoid circular imports
        from .alerts import AlertsCollector
        from .device import DeviceCollector
        from .network_health import NetworkHealthCollector
        from .organization import OrganizationCollector
        from .sensor import SensorCollector

        # MEDIUM tier collectors
        # Always collect organization metrics
        org_collector = OrganizationCollector(
            api=self.client.api,
            settings=self.settings,
        )
        self.collectors[UpdateTier.MEDIUM].append(org_collector)
        logger.info("Initialized organization collector (MEDIUM tier)")

        # Initialize device collector if any device types are specified
        if self.settings.device_types:
            device_collector = DeviceCollector(
                api=self.client.api,
                settings=self.settings,
            )
            self.collectors[UpdateTier.MEDIUM].append(device_collector)
            logger.info(
                "Initialized device collector (MEDIUM tier)",
                device_types=self.settings.device_types,
            )

        # MEDIUM tier collectors
        # Network health collector
        network_health_collector = NetworkHealthCollector(
            api=self.client.api,
            settings=self.settings,
        )
        self.collectors[UpdateTier.MEDIUM].append(network_health_collector)
        logger.info("Initialized network health collector (MEDIUM tier)")

        # Alerts collector
        alerts_collector = AlertsCollector(
            api=self.client.api,
            settings=self.settings,
        )
        self.collectors[UpdateTier.MEDIUM].append(alerts_collector)
        logger.info("Initialized alerts collector (MEDIUM tier)")

        # FAST tier collectors
        # Sensor collector if MT devices are enabled
        if "MT" in self.settings.device_types:
            sensor_collector = SensorCollector(
                api=self.client.api,
                settings=self.settings,
            )
            self.collectors[UpdateTier.FAST].append(sensor_collector)
            logger.info("Initialized sensor collector (FAST tier)")

    async def collect_initial(self) -> None:
        """Run initial collection from all tiers sequentially to avoid API overload."""
        # Collect tier by tier to reduce API load during startup
        for tier in [UpdateTier.MEDIUM, UpdateTier.FAST]:
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

    async def collect_tier(self, tier: UpdateTier) -> None:
        """Run all collectors for a specific tier.

        Parameters
        ----------
        tier : UpdateTier
            The update tier to collect.

        """
        tier_collectors = self.collectors.get(tier, [])
        if not tier_collectors:
            logger.debug(
                "No collectors for tier",
                tier=tier,
            )
            return

        logger.debug(
            "Starting collection for tier",
            tier=tier,
            collector_count=len(tier_collectors),
        )

        # Run collectors individually with proper error handling and timeout
        # Set timeout based on tier
        if tier == UpdateTier.FAST:
            timeout = 60  # 1 minute for fast tier
        else:  # MEDIUM
            timeout = 120  # 2 minutes for medium tier

        for collector in tier_collectors:
            collector_name = collector.__class__.__name__
            logger.debug(
                "Starting collector",
                collector=collector_name,
                tier=tier,
            )

            try:
                await asyncio.wait_for(collector.collect(), timeout=timeout)
                logger.debug(
                    "Collector completed successfully",
                    collector=collector_name,
                    tier=tier,
                )
            except TimeoutError:
                logger.error(
                    "Collector timeout",
                    collector=collector_name,
                    tier=tier,
                    timeout_seconds=timeout,
                )
                # Continue with next collector even if this one times out
            except Exception as e:
                logger.error(
                    "Collector failed",
                    collector=collector_name,
                    tier=tier,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Continue with next collector even if this one fails

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
            return self.settings.fast_update_interval
        else:  # MEDIUM
            return self.settings.medium_update_interval

    def register_collector(self, collector: MetricCollector) -> None:
        """Register an additional collector.

        Parameters
        ----------
        collector : MetricCollector
            The collector to register.

        """
        tier = collector.update_tier
        self.collectors[tier].append(collector)
        logger.info(
            "Registered collector",
            collector=collector.__class__.__name__,
            tier=tier,
        )
