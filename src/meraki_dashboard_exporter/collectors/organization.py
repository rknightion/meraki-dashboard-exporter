"""Organization-level metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..core.api_helpers import create_api_helper
from ..core.collector import MetricCollector
from ..core.constants import OrgMetricName, UpdateTier
from ..core.error_handling import ErrorCategory, with_error_handling
from ..core.label_helpers import create_org_labels
from ..core.logging import get_logger
from ..core.logging_decorators import log_api_call, log_batch_operation
from ..core.logging_helpers import LogContext, log_metric_collection_summary
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
            "Total API requests made by the organization in the last hour",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._api_requests_by_status = self._create_gauge(
            OrgMetricName.ORG_API_REQUESTS_BY_STATUS,
            "API requests by HTTP status code in the last hour",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME, LabelName.STATUS_CODE],
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
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.STATUS,
                LabelName.PRODUCT_TYPE,
            ],
        )

        # License metrics
        self._licenses_total = self._create_gauge(
            OrgMetricName.ORG_LICENSES_TOTAL,
            "Total number of licenses",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.LICENSE_TYPE,
                LabelName.STATUS,
            ],
        )

        self._licenses_expiring = self._create_gauge(
            OrgMetricName.ORG_LICENSES_EXPIRING,
            "Number of licenses expiring within 30 days",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME, LabelName.LICENSE_TYPE],
        )

        # Client metrics
        self._clients_total = self._create_gauge(
            OrgMetricName.ORG_CLIENTS_TOTAL,
            "Total number of active clients in the organization (1-hour window)",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        # Usage metrics (in KB for the 1-hour window)
        self._usage_total_kb = self._create_gauge(
            OrgMetricName.ORG_USAGE_TOTAL_KB,
            "Total data usage in KB for the 1-hour window",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._usage_downstream_kb = self._create_gauge(
            OrgMetricName.ORG_USAGE_DOWNSTREAM_KB,
            "Downstream data usage in KB for the 1-hour window",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._usage_upstream_kb = self._create_gauge(
            OrgMetricName.ORG_USAGE_UPSTREAM_KB,
            "Upstream data usage in KB for the 1-hour window",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        # Packet capture metrics
        self._packetcaptures_total = self._create_gauge(
            OrgMetricName.ORG_PACKETCAPTURES_TOTAL,
            "Total number of packet captures in the organization",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        self._packetcaptures_remaining = self._create_gauge(
            OrgMetricName.ORG_PACKETCAPTURES_REMAINING,
            "Number of remaining packet captures to process",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME],
        )

        # Application usage metrics
        self._application_usage_total_mb = self._create_gauge(
            OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_MB,
            "Total application usage in MB by category",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME, LabelName.CATEGORY],
        )

        self._application_usage_downstream_mb = self._create_gauge(
            OrgMetricName.ORG_APPLICATION_USAGE_DOWNSTREAM_MB,
            "Downstream application usage in MB by category",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME, LabelName.CATEGORY],
        )

        self._application_usage_upstream_mb = self._create_gauge(
            OrgMetricName.ORG_APPLICATION_USAGE_UPSTREAM_MB,
            "Upstream application usage in MB by category",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME, LabelName.CATEGORY],
        )

        self._application_usage_percentage = self._create_gauge(
            OrgMetricName.ORG_APPLICATION_USAGE_PERCENTAGE,
            "Application usage percentage by category",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME, LabelName.CATEGORY],
        )

    async def _collect_impl(self) -> None:
        """Collect organization metrics."""
        start_time = asyncio.get_event_loop().time()
        metrics_collected = 0
        organizations_processed = 0
        api_calls_made = 0

        try:
            # Get organizations
            organizations = await self._fetch_organizations()
            if not organizations:
                logger.warning("No organizations found to collect metrics from")
                return
            api_calls_made += 1

            # Collect metrics for each organization
            tasks = [self._collect_org_metrics(org) for org in organizations]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successful collections
            for result in results:
                if not isinstance(result, Exception):
                    organizations_processed += 1
                    # Each org makes multiple API calls
                    api_calls_made += 7  # Approximate

            # Log collection summary
            log_metric_collection_summary(
                "OrganizationCollector",
                metrics_collected=metrics_collected,
                duration_seconds=asyncio.get_event_loop().time() - start_time,
                organizations_processed=organizations_processed,
                api_calls_made=api_calls_made,
            )

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

    @log_batch_operation("collect org metrics", batch_size=1)
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
            with LogContext(org_id=org_id, org_name=org_name):
                # Create org labels using helper
                org_labels = create_org_labels(org)

                # Set organization info
                if self._org_info:
                    self._org_info.labels(**org_labels).info({
                        "url": org.get("url", ""),
                        "api_enabled": str(org.get("api", {}).get("enabled", False)),
                    })
                else:
                    logger.error("_org_info metric not initialized")

                # Collect various metrics sequentially
                # Skip API metrics for now - it's often problematic
                # await self._collect_api_metrics(org_id, org_name)

                await self._collect_network_metrics(org_id, org_name)
                await self._collect_device_metrics(org_id, org_name)
                await self._collect_device_counts_by_model(org_id, org_name)
                await self._collect_device_availability_metrics(org_id, org_name)
                await self._collect_license_metrics(org_id, org_name)
                await self._collect_client_overview(org_id, org_name)
                await self._collect_packet_capture_metrics(org_id, org_name)
                await self._collect_application_usage_metrics(org_id, org_name)

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
            networks = await self.api_helper.get_organization_networks(org_id)
            if not networks:
                logger.warning("No networks found or error fetching networks", org_id=org_id)
                return

            # Count total networks
            total_networks = len(networks)
            # Create org labels using helper
            org_data = {"id": org_id, "name": org_name}
            org_labels = create_org_labels(org_data)

            if self._networks_total:
                self._networks_total.labels(**org_labels).set(total_networks)
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
            devices = await self.api_helper.get_organization_devices(org_id)
            if not devices:
                return

            # Count devices by type
            device_counts: dict[str, int] = {}
            for device in devices:
                model = device.get("model", "")
                # Extract device type from model (e.g., "MS" from "MS210-8")
                device_type = model[:2] if len(model) >= 2 else "Unknown"
                device_counts[device_type] = device_counts.get(device_type, 0) + 1

            # Set metrics for each device type
            # Create org labels using helper
            org_data = {"id": org_id, "name": org_name}

            if self._devices_total:
                for device_type, count in device_counts.items():
                    labels = create_org_labels(
                        org_data,
                        device_type=device_type,
                    )
                    self._devices_total.labels(**labels).set(count)
            else:
                logger.error("_devices_total metric not initialized")

        except Exception:
            logger.exception(
                "Failed to collect device metrics",
                org_id=org_id,
                org_name=org_name,
            )

    @log_api_call("getOrganizationDevicesOverviewByModel")
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
            with LogContext(org_id=org_id, org_name=org_name):
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
                # Create org labels using helper
                org_data = {"id": org_id, "name": org_name}

                if self._devices_by_model_total:
                    for model_data in counts:
                        model = model_data.get("model", "Unknown")
                        count = model_data.get("total", 0)
                        labels = create_org_labels(
                            org_data,
                            model=model,
                        )
                        self._devices_by_model_total.labels(**labels).set(count)
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

    @log_api_call("getOrganizationDevicesAvailabilities")
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
            with LogContext(org_id=org_id, org_name=org_name):
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
            # Create org labels using helper
            org_data = {"id": org_id, "name": org_name}

            if self._devices_availability_total:
                for (status, product_type), count in availability_counts.items():
                    labels = create_org_labels(
                        org_data,
                        status=status,
                        product_type=product_type,
                    )
                    self._devices_availability_total.labels(**labels).set(count)
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

    @log_api_call("getOrganizationDevicesPacketCaptureCaptures")
    @with_error_handling(
        operation="Collect packet capture metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_packet_capture_metrics(self, org_id: str, org_name: str) -> None:
        """Collect packet capture metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            with LogContext(org_id=org_id, org_name=org_name):
                # Use perPage=3 to minimize data transfer while still getting the meta counts
                response = await asyncio.to_thread(
                    self.api.organizations.getOrganizationDevicesPacketCaptureCaptures,
                    org_id,
                    perPage=3,
                )

            # Extract meta counts
            if isinstance(response, dict) and "meta" in response and "counts" in response["meta"]:
                counts = response["meta"]["counts"].get("items", {})
                total = counts.get("total", 0)
                remaining = counts.get("remaining", 0)

                # Set metrics
                # Create org labels using helper
                org_data = {"id": org_id, "name": org_name}
                org_labels = create_org_labels(org_data)

                if self._packetcaptures_total:
                    self._packetcaptures_total.labels(**org_labels).set(total)
                else:
                    logger.error("_packetcaptures_total metric not initialized")

                if self._packetcaptures_remaining:
                    self._packetcaptures_remaining.labels(**org_labels).set(remaining)
                else:
                    logger.error("_packetcaptures_remaining metric not initialized")

                logger.debug(
                    "Collected packet capture metrics",
                    org_id=org_id,
                    total=total,
                    remaining=remaining,
                )
            else:
                logger.warning(
                    "Unexpected response format for packet captures",
                    org_id=org_id,
                    response_type=type(response).__name__,
                )

        except Exception:
            logger.exception(
                "Failed to collect packet capture metrics",
                org_id=org_id,
                org_name=org_name,
            )

    def _sanitize_category_name(self, category: str) -> str:
        """Sanitize category name for use as a Prometheus label.

        Parameters
        ----------
        category : str
            Raw category name from API.

        Returns
        -------
        str
            Sanitized category name.

        """
        if not category:
            return "unknown"

        # Convert to lowercase and replace problematic characters
        sanitized = category.lower()
        sanitized = sanitized.replace(" & ", "_and_")
        sanitized = sanitized.replace("&", "_and_")
        sanitized = sanitized.replace(" - ", "_")
        sanitized = sanitized.replace("-", "_")
        sanitized = sanitized.replace(" ", "_")
        sanitized = sanitized.replace("/", "_")
        sanitized = sanitized.replace("\\", "_")
        sanitized = sanitized.replace(".", "")
        sanitized = sanitized.replace(",", "")
        sanitized = sanitized.replace(":", "")
        sanitized = sanitized.replace(";", "")
        sanitized = sanitized.replace("(", "")
        sanitized = sanitized.replace(")", "")
        sanitized = sanitized.replace("'", "")
        sanitized = sanitized.replace('"', "")

        # Remove any remaining non-alphanumeric characters except underscore
        result = ""
        for char in sanitized:
            if char.isalnum() or char == "_":
                result += char

        # Remove multiple underscores
        while "__" in result:
            result = result.replace("__", "_")

        # Strip leading/trailing underscores
        result = result.strip("_")

        return result if result else "unknown"

    @log_api_call("getOrganizationSummaryTopApplicationsCategoriesByUsage")
    @with_error_handling(
        operation="Collect application usage metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_application_usage_metrics(self, org_id: str, org_name: str) -> None:
        """Collect application usage metrics by category.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            with LogContext(org_id=org_id, org_name=org_name):
                # Call API with quantity=1000 and no timespan
                response = await asyncio.to_thread(
                    self.api.organizations.getOrganizationSummaryTopApplicationsCategoriesByUsage,
                    org_id,
                    quantity=1000,
                )

            # Process each category
            for category_data in response:
                category = category_data.get("category", "Unknown")
                sanitized_category = self._sanitize_category_name(category)

                # Convert MB to MB (values are already in MB based on the example)
                total_mb = category_data.get("total", 0)
                downstream_mb = category_data.get("downstream", 0)
                upstream_mb = category_data.get("upstream", 0)
                percentage = category_data.get("percentage", 0)

                # Set metrics
                # Create org labels using helper
                org_data = {"id": org_id, "name": org_name}
                labels = create_org_labels(
                    org_data,
                    category=sanitized_category,
                )

                if self._application_usage_total_mb:
                    self._application_usage_total_mb.labels(**labels).set(total_mb)

                if self._application_usage_downstream_mb:
                    self._application_usage_downstream_mb.labels(**labels).set(downstream_mb)

                if self._application_usage_upstream_mb:
                    self._application_usage_upstream_mb.labels(**labels).set(upstream_mb)

                if self._application_usage_percentage:
                    self._application_usage_percentage.labels(**labels).set(percentage)

            logger.debug(
                "Collected application usage metrics",
                org_id=org_id,
                categories_count=len(response),
            )

        except Exception:
            logger.exception(
                "Failed to collect application usage metrics",
                org_id=org_id,
                org_name=org_name,
            )
