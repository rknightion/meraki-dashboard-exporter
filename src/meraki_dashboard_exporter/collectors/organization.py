"""Organization-level metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..core.api_helpers import create_api_helper
from ..core.collector import MetricCollector
from ..core.constants import OrgMetricName, UpdateTier
from ..core.error_handling import ErrorCategory, with_error_handling
from ..core.logging import get_logger
from ..core.metrics import LabelName
from ..core.registry import register_collector
from .organization_collectors import APIUsageCollector, ClientOverviewCollector, LicenseCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings

logger = get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)
class OrganizationCollector(MetricCollector):
    """Collector for organization-level metrics."""

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
    ) -> None:
        """Initialize organization collector with sub-collectors."""
        super().__init__(api, settings, registry)

        # Create API helper
        self.api_helper = create_api_helper(self)

        # Initialize sub-collectors
        self.api_usage_collector = APIUsageCollector(self)
        self.license_collector = LicenseCollector(self)
        self.client_overview_collector = ClientOverviewCollector(self)

    def _initialize_metrics(self) -> None:
        """Initialize organization metrics."""
        # Organization info
        self._org_info = self._create_info(
            OrgMetricName.ORG_INFO,
            "Organization information",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        # API metrics
        self._api_requests_total = self._create_gauge(
            OrgMetricName.ORG_API_REQUESTS_TOTAL,
            "Total API requests made by the organization",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._api_rate_limit = self._create_gauge(
            OrgMetricName.ORG_API_REQUESTS_RATE_LIMIT,
            "API rate limit for the organization",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        # Network metrics
        self._networks_total = self._create_gauge(
            OrgMetricName.ORG_NETWORKS_TOTAL,
            "Total number of networks in the organization",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        # Device metrics
        self._devices_total = self._create_gauge(
            OrgMetricName.ORG_DEVICES_TOTAL,
            "Total number of devices in the organization",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME, LabelName.DEVICE_TYPE],
        )

        self._devices_by_model_total = self._create_gauge(
            OrgMetricName.ORG_DEVICES_BY_MODEL_TOTAL,
            "Total number of devices by specific model",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME, LabelName.MODEL],
        )

        # Device availability metrics (from new API)
        self._devices_availability_total = self._create_gauge(
            OrgMetricName.ORG_DEVICES_AVAILABILITY_TOTAL,
            "Total number of devices by availability status and product type",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME, LabelName.STATUS, LabelName.PRODUCT_TYPE],
        )

        # License metrics
        self._licenses_total = self._create_gauge(
            OrgMetricName.ORG_LICENSES_TOTAL,
            "Total number of licenses",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME, LabelName.LICENSE_TYPE, LabelName.STATUS],
        )

        self._licenses_expiring = self._create_gauge(
            OrgMetricName.ORG_LICENSES_EXPIRING,
            "Number of licenses expiring within 30 days",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME, LabelName.LICENSE_TYPE],
        )

        # Client metrics
        self._clients_total = self._create_gauge(
            OrgMetricName.ORG_CLIENTS_TOTAL,
            "Total number of active clients in the organization (5-minute window from last complete interval)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        # Usage metrics (in KB for the 5-minute window)
        self._usage_total_kb = self._create_gauge(
            OrgMetricName.ORG_USAGE_TOTAL_KB,
            "Total data usage in KB for the 5-minute window (last complete 5-min interval, e.g., 11:04 call returns 10:55-11:00)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._usage_downstream_kb = self._create_gauge(
            OrgMetricName.ORG_USAGE_DOWNSTREAM_KB,
            "Downstream data usage in KB for the 5-minute window (last complete 5-min interval)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._usage_upstream_kb = self._create_gauge(
            OrgMetricName.ORG_USAGE_UPSTREAM_KB,
            "Upstream data usage in KB for the 5-minute window (last complete 5-min interval)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

    async def _collect_impl(self) -> None:
        """Collect organization metrics."""
        try:
            # Get organizations
            organizations = await self._fetch_organizations()
            if not organizations:
                logger.warning("No organizations found to collect metrics from")
                return

            # Collect metrics for each organization
            tasks = [self._collect_org_metrics(org) for org in organizations]
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception:
            logger.exception("Failed to collect organization metrics")

    async def _fetch_organizations(self) -> list[dict[str, Any]] | None:
        """Fetch organizations using API helper.

        Returns
        -------
        list[dict[str, Any]] | None
            List of organizations or None on error.

        """
        return await self.api_helper.get_organizations()

    @with_error_handling(
        operation="Collect organization metrics",
        continue_on_error=True,
    )
    async def _collect_org_metrics(self, org: dict[str, Any]) -> None:
        """Collect metrics for a specific organization.

        Parameters
        ----------
        org : dict[str, Any]
            Organization data.

        """
        org_id = org["id"]
        org_name = org["name"]

        try:
            # Set organization info
            if self._org_info:
                self._org_info.labels(
                    org_id=org_id,
                    org_name=org_name,
                ).info({
                    "url": org.get("url", ""),
                    "api_enabled": str(org.get("api", {}).get("enabled", False)),
                })
            else:
                logger.error("_org_info metric not initialized")

            # Collect various metrics sequentially with logging
            # Skip API metrics for now - it's often problematic
            # logger.info("Collecting API metrics", org_id=org_id)
            # await self._collect_api_metrics(org_id, org_name)

            logger.debug("Collecting network metrics", org_id=org_id)
            await self._collect_network_metrics(org_id, org_name)

            logger.debug("Collecting device metrics", org_id=org_id)
            await self._collect_device_metrics(org_id, org_name)

            logger.debug("Collecting device counts by model", org_id=org_id)
            await self._collect_device_counts_by_model(org_id, org_name)

            logger.debug("Collecting device availability metrics", org_id=org_id)
            await self._collect_device_availability_metrics(org_id, org_name)

            logger.debug("Collecting license metrics", org_id=org_id)
            await self._collect_license_metrics(org_id, org_name)

            logger.debug("Collecting client overview metrics", org_id=org_id)
            await self._collect_client_overview(org_id, org_name)

        except Exception:
            logger.exception(
                "Failed to collect metrics for organization",
                org_id=org_id,
                org_name=org_name,
            )

    async def _collect_api_metrics(self, org_id: str, org_name: str) -> None:
        """Collect API usage metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        await self.api_usage_collector.collect(org_id, org_name)

    @with_error_handling(
        operation="Collect network metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_network_metrics(self, org_id: str, org_name: str) -> None:
        """Collect network metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            logger.debug("Fetching networks", org_id=org_id)
            networks = await self.api_helper.get_organization_networks(org_id)

            # Count total networks
            total_networks = len(networks)
            if self._networks_total:
                self._networks_total.labels(
                    org_id=org_id,
                    org_name=org_name,
                ).set(total_networks)
                logger.debug(
                    "Successfully collected network metrics",
                    org_id=org_id,
                    total_networks=total_networks,
                )
            else:
                logger.error("_networks_total metric not initialized")

        except Exception:
            logger.exception(
                "Failed to collect network metrics",
                org_id=org_id,
                org_name=org_name,
            )

    @with_error_handling(
        operation="Collect device metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_device_metrics(self, org_id: str, org_name: str) -> None:
        """Collect device metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            logger.debug("Fetching devices", org_id=org_id)
            devices = await self.api_helper.get_organization_devices(org_id)

            # Count devices by type
            device_counts: dict[str, int] = {}
            for device in devices:
                model = device.get("model", "")
                # Extract device type from model (e.g., "MS" from "MS210-8")
                device_type = model[:2] if len(model) >= 2 else "Unknown"
                device_counts[device_type] = device_counts.get(device_type, 0) + 1

            # Set metrics for each device type
            if self._devices_total:
                for device_type, count in device_counts.items():
                    self._devices_total.labels(
                        org_id=org_id,
                        org_name=org_name,
                        device_type=device_type,
                    ).set(count)
                    logger.debug(
                        "Set device count",
                        org_id=org_id,
                        device_type=device_type,
                        count=count,
                    )
            else:
                logger.error("_devices_total metric not initialized")

        except Exception:
            logger.exception(
                "Failed to collect device metrics",
                org_id=org_id,
                org_name=org_name,
            )

    async def _collect_device_counts_by_model(self, org_id: str, org_name: str) -> None:
        """Collect device counts by specific model.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            logger.debug("Fetching device counts by model", org_id=org_id)
            self._track_api_call("getOrganizationDevicesOverviewByModel")
            overview = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevicesOverviewByModel,
                org_id,
            )

            # Response can be either the direct object or wrapped in {"items": []}
            if isinstance(overview, dict) and "items" in overview:
                items = overview["items"]
            elif isinstance(overview, dict) and "counts" in overview:
                # Direct response format
                counts = overview.get("counts", [])
            else:
                logger.warning(
                    "Unexpected response format for device overview by model",
                    org_id=org_id,
                    response_type=type(overview).__name__,
                )
                return

            # Process counts
            if "counts" in locals():
                if self._devices_by_model_total:
                    for model_data in counts:
                        model = model_data.get("model", "Unknown")
                        count = model_data.get("total", 0)
                        self._devices_by_model_total.labels(
                            org_id=org_id,
                            org_name=org_name,
                            model=model,
                        ).set(count)
                        logger.debug(
                            "Set device count by model",
                            org_id=org_id,
                            model=model,
                            count=count,
                        )
                else:
                    logger.error("_devices_by_model_total metric not initialized")

        except Exception:
            logger.exception(
                "Failed to collect device counts by model",
                org_id=org_id,
                org_name=org_name,
            )

    async def _collect_license_metrics(self, org_id: str, org_name: str) -> None:
        """Collect license metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        await self.license_collector.collect(org_id, org_name)

    async def _collect_device_availability_metrics(self, org_id: str, org_name: str) -> None:
        """Collect device availability metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            logger.debug("Fetching device availabilities", org_id=org_id)
            self._track_api_call("getOrganizationDevicesAvailabilities")
            availabilities = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevicesAvailabilities,
                org_id,
                total_pages="all",
            )

            # Group by status and product type
            availability_counts: dict[tuple[str, str], int] = {}
            for device in availabilities:
                status = device.get("status", "unknown")
                product_type = device.get("productType", "unknown")
                key = (status, product_type)
                availability_counts[key] = availability_counts.get(key, 0) + 1

            # Set metrics for each combination
            if self._devices_availability_total:
                for (status, product_type), count in availability_counts.items():
                    self._devices_availability_total.labels(
                        org_id=org_id,
                        org_name=org_name,
                        status=status,
                        product_type=product_type,
                    ).set(count)
                    logger.debug(
                        "Set device availability count",
                        org_id=org_id,
                        status=status,
                        product_type=product_type,
                        count=count,
                    )
            else:
                logger.error("_devices_availability_total metric not initialized")

        except Exception:
            logger.exception(
                "Failed to collect device availability metrics",
                org_id=org_id,
                org_name=org_name,
            )

    async def _collect_client_overview(self, org_id: str, org_name: str) -> None:
        """Collect client overview metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        await self.client_overview_collector.collect(org_id, org_name)
