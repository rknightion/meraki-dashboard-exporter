"""Collector manager for coordinating metric collection."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..core.constants import UpdateTier
from ..core.logging import get_logger
from ..core.registry import get_registered_collectors

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
            UpdateTier.SLOW: [],
        }
        self._initialize_collectors()

    def _initialize_collectors(self) -> None:
        """Initialize all enabled collectors."""
        # Import all collectors to trigger registration
        # This ensures the @register_collector decorators are executed
        from . import (  # noqa: F401
            alerts,
            clients,
            config,
            device,
            mt_sensor,
            network_health,
            organization,
            snmp,
        )

        # Get all registered collectors
        registered_collectors = get_registered_collectors()

        # Initialize collectors for each tier
        for tier, collector_classes in registered_collectors.items():
            for collector_class in collector_classes:
                try:
                    # Create instance of the collector
                    collector_instance = collector_class(
                        api=self.client.api,
                        settings=self.settings,
                    )
                    self.collectors[tier].append(collector_instance)
                    logger.info(
                        "Initialized collector",
                        collector=collector_class.__name__,
                        tier=tier.value,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to initialize collector",
                        collector=collector_class.__name__,
                        tier=tier.value,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    # Continue with other collectors even if one fails to initialize

    async def collect_initial(self) -> None:
        """Run initial collection from all tiers sequentially to avoid API overload."""
        # Collect tier by tier to reduce API load during startup
        for tier in [UpdateTier.SLOW, UpdateTier.MEDIUM, UpdateTier.FAST]:
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
        elif tier == UpdateTier.MEDIUM:
            timeout = 120  # 2 minutes for medium tier
        else:  # SLOW
            timeout = 180  # 3 minutes for slow tier

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
            return self.settings.update_intervals.fast
        elif tier == UpdateTier.MEDIUM:
            return self.settings.update_intervals.medium
        else:  # SLOW
            return self.settings.update_intervals.slow

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
