"""Collector manager for coordinating metric collection."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from prometheus_client import Counter, Gauge, Histogram

from ..core.async_utils import ManagedTaskGroup
from ..core.constants import UpdateTier
from ..core.constants.metrics_constants import CollectorMetricName
from ..core.logging import get_logger
from ..core.metrics import LabelName
from ..core.registry import get_registered_collectors
from ..services.inventory import OrganizationInventory

if TYPE_CHECKING:
    from ..api.client import AsyncMerakiClient
    from ..core.collector import MetricCollector
    from ..core.config import Settings
    from ..core.metric_expiration import MetricExpirationManager

logger = get_logger(__name__)


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
    ) -> None:
        """Initialize the collector manager with client and settings."""
        self.client = client
        self.settings = settings
        self.expiration_manager = expiration_manager
        self.collectors: dict[UpdateTier, list[MetricCollector]] = {
            UpdateTier.FAST: [],
            UpdateTier.MEDIUM: [],
            UpdateTier.SLOW: [],
        }

        # Initialize shared inventory service for caching org/network/device data
        self.inventory = OrganizationInventory(
            api=self.client.api,
            settings=self.settings,
        )

        # Track collector health state
        self.collector_health: dict[str, dict[str, Any]] = {}

        # Track skipped/disabled collectors for visibility
        self.skipped_collectors: list[dict[str, str]] = []

        self._initialize_metrics()
        self._initialize_collectors()
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

        # Histogram for organization collection wait time
        self._org_collection_wait_time = Histogram(
            CollectorMetricName.ORG_COLLECTION_WAIT_TIME_SECONDS.value,
            "Time an organization spends waiting for semaphore slot before collection starts",
            labelnames=[
                LabelName.COLLECTOR.value,
                LabelName.ORG_ID.value,
            ],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
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

        # Gauge for collector health - last successful collection age in seconds
        self._collector_last_success_age = Gauge(
            "meraki_exporter_collector_success_age_seconds",
            "Seconds since the last successful collection for each collector",
            labelnames=[
                LabelName.COLLECTOR.value,
                LabelName.TIER.value,
            ],
        )

        # Gauge for collector failure streak
        self._collector_failure_streak = Gauge(
            "meraki_exporter_collector_failure_streak",
            "Consecutive failures for each collector since last success",
            labelnames=[
                LabelName.COLLECTOR.value,
                LabelName.TIER.value,
            ],
        )

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
                    collector_instance = collector_class(
                        api=self.client.api,
                        settings=self.settings,
                        inventory=self.inventory,
                        expiration_manager=self.expiration_manager,
                    )
                    self.collectors[tier].append(collector_instance)

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

    async def collect_initial(self) -> None:
        """Run initial collection from all tiers sequentially to avoid API overload."""
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
        tier_collectors = self.collectors.get(tier, [])
        if not tier_collectors:
            logger.debug(
                "No collectors for tier",
                tier=tier,
            )
            return

        logger.info(
            "Starting parallel collection for tier",
            tier=tier,
            collector_count=len(tier_collectors),
            concurrency_limit=self.settings.api.concurrency_limit,
        )

        # Use collector_timeout from settings (default: 120s)
        timeout = self.settings.collectors.collector_timeout

        # Run collectors in parallel with bounded concurrency
        async with ManagedTaskGroup(
            name=f"tier_{tier.value}",
            max_concurrency=self.settings.api.concurrency_limit,
        ) as group:
            for collector in tier_collectors:
                await group.create_task(
                    self._run_collector_with_timeout(collector, tier, timeout),
                    name=collector.__class__.__name__,
                )

        logger.info(
            "Completed collection for tier",
            tier=tier,
            collector_count=len(tier_collectors),
        )

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
        try:
            await asyncio.wait_for(collector.collect(), timeout=timeout)
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
            # Update health tracking
            if collector_name in self.collector_health:
                if success:
                    self.collector_health[collector_name]["last_success_time"] = time.time()
                    self.collector_health[collector_name]["failure_streak"] = 0
                    self.collector_health[collector_name]["total_successes"] += 1
                else:
                    self.collector_health[collector_name]["failure_streak"] += 1
                    self.collector_health[collector_name]["total_failures"] += 1

                # Update health metrics
                last_success = self.collector_health[collector_name]["last_success_time"]
                if last_success is not None:
                    age = time.time() - last_success
                    self._collector_last_success_age.labels(
                        collector=collector_name,
                        tier=tier.value,
                    ).set(age)

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
