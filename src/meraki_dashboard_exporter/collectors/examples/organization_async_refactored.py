"""Example refactored organization collector using async patterns.

This shows how organization.py could be refactored to use standardized async utilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.async_utils import ManagedTaskGroup, safe_gather, with_timeout
from ...core.collector import MetricCollector
from ...core.constants import OrgMetricName, UpdateTier
from ...core.error_handling import with_error_handling
from ...core.logging import get_logger
from ...core.registry import register_collector
from ..organization_collectors import (
    APIUsageCollector,
    ClientOverviewCollector,
    LicenseCollector,
)

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ...core.config import Settings

logger = get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)
class OrganizationCollectorAsync(MetricCollector):
    """Refactored organization collector using async patterns."""

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
    ) -> None:
        """Initialize the organization collector."""
        super().__init__(api, settings, registry)

        # Initialize sub-collectors
        self.api_usage_collector = APIUsageCollector(self)
        self.license_collector = LicenseCollector(self)
        self.client_overview_collector = ClientOverviewCollector(self)

    def _initialize_metrics(self) -> None:
        """Initialize organization metrics."""
        # Organization info metric
        self._org_info = self._create_info(
            OrgMetricName.ORG_INFO,
            "Organization information",
            labelnames=["org_id", "org_name"],
        )

        # Network count
        self._org_networks_total = self._create_gauge(
            OrgMetricName.ORG_NETWORKS_TOTAL,
            "Total number of networks in the organization",
            labelnames=["org_id", "org_name"],
        )

        # Device count
        self._org_devices_total = self._create_gauge(
            OrgMetricName.ORG_DEVICES_TOTAL,
            "Total number of devices in the organization",
            labelnames=["org_id", "org_name"],
        )

    @with_error_handling(
        operation="Collect organization metrics",
        continue_on_error=True,
    )
    async def _collect_impl(self) -> None:
        """Collect metrics using async patterns."""
        # Fetch organizations with timeout
        organizations = await with_timeout(
            self._fetch_organizations(),
            timeout=30.0,
            operation="fetch organizations",
            default=[],
        )

        if not organizations:
            logger.warning("No organizations found to collect metrics for")
            return

        # Use ManagedTaskGroup for structured concurrency
        async with ManagedTaskGroup("organization_collection") as task_group:
            for org in organizations:
                # Create a task for each organization
                await task_group.create_task(
                    self._collect_org_metrics_async(org),
                    name=f"org_{org['id']}",
                )

            # All tasks are automatically awaited and cleaned up

    async def _collect_org_metrics_async(self, org: dict[str, Any]) -> None:
        """Collect metrics for a single organization using async patterns."""
        org_id = org["id"]
        org_name = org["name"]

        try:
            # Set organization info
            self._org_info.labels(
                org_id=org_id,
                org_name=org_name,
            ).info({
                "url": org.get("url", ""),
                "api_enabled": str(org.get("api", {}).get("enabled", False)),
            })

            # Use safe_gather for concurrent metric collection
            # This ensures all metrics are attempted even if some fail
            metric_tasks = [
                self._collect_network_metrics(org_id, org_name),
                self._collect_device_metrics(org_id, org_name),
                self._collect_device_counts_by_model(org_id, org_name),
                self._collect_device_availability_metrics(org_id, org_name),
            ]

            # Collect basic metrics concurrently
            basic_results = await safe_gather(
                *metric_tasks,
                description=f"basic metrics for org {org_id}",
                log_errors=True,
            )

            # Use ManagedTaskGroup for sub-collector tasks
            async with ManagedTaskGroup(f"org_{org_id}_subcollectors") as sub_group:
                # License metrics might take longer
                await sub_group.create_task(
                    with_timeout(
                        self._collect_license_metrics(org_id, org_name),
                        timeout=60.0,
                        operation=f"license metrics for {org_id}",
                    ),
                    name="license_metrics",
                )

                # Client overview with shorter timeout
                await sub_group.create_task(
                    with_timeout(
                        self._collect_client_overview(org_id, org_name),
                        timeout=30.0,
                        operation=f"client overview for {org_id}",
                    ),
                    name="client_overview",
                )

                # API usage (if enabled)
                if self.settings.collectors.active_collectors.get("api_usage", False):
                    await sub_group.create_task(
                        with_timeout(
                            self.api_usage_collector.collect(org_id, org_name),
                            timeout=30.0,
                            operation=f"API usage for {org_id}",
                        ),
                        name="api_usage",
                    )

        except Exception:
            logger.exception(
                "Failed to collect metrics for organization",
                org_id=org_id,
                org_name=org_name,
            )

    async def _fetch_organizations(self) -> list[dict[str, Any]]:
        """Fetch organizations."""
        # Implementation would use api_helper
        pass

    async def _collect_network_metrics(self, org_id: str, org_name: str) -> None:
        """Collect network count metrics."""
        # Implementation
        pass

    async def _collect_device_metrics(self, org_id: str, org_name: str) -> None:
        """Collect device count metrics."""
        # Implementation
        pass

    async def _collect_device_counts_by_model(self, org_id: str, org_name: str) -> None:
        """Collect device counts by model."""
        # Implementation
        pass

    async def _collect_device_availability_metrics(self, org_id: str, org_name: str) -> None:
        """Collect device availability metrics."""
        # Implementation
        pass

    async def _collect_license_metrics(self, org_id: str, org_name: str) -> None:
        """Collect license metrics via sub-collector."""
        await self.license_collector.collect(org_id, org_name)

    async def _collect_client_overview(self, org_id: str, org_name: str) -> None:
        """Collect client overview via sub-collector."""
        await self.client_overview_collector.collect(org_id, org_name)


# Benefits of this refactoring:
# 1. Structured concurrency with ManagedTaskGroup ensures proper cleanup
# 2. Timeouts prevent any single operation from blocking too long
# 3. safe_gather ensures all metrics are attempted even if some fail
# 4. Sub-collectors can run concurrently with proper isolation
# 5. Clear async patterns that can be replicated in other collectors
