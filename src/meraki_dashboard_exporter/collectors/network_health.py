"""Medium-tier network health metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from ..core.async_utils import ManagedTaskGroup
from ..core.batch_processing import process_in_batches_with_errors
from ..core.collector import MetricCollector
from ..core.constants import NetworkHealthMetricName, NetworkMetricName, ProductType, UpdateTier
from ..core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ..core.logging import get_logger
from ..core.logging_decorators import log_api_call, log_batch_operation
from ..core.logging_helpers import LogContext, log_metric_collection_summary
from ..core.metrics import LabelName
from ..core.registry import register_collector
from .network_health_collectors.bluetooth import BluetoothCollector
from .network_health_collectors.connection_stats import ConnectionStatsCollector
from .network_health_collectors.data_rates import DataRatesCollector
from .network_health_collectors.rf_health import RFHealthCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings
    from ..core.metric_expiration import MetricExpirationManager
    from ..services.inventory import OrganizationInventory

logger = get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)
class NetworkHealthCollector(MetricCollector):
    """Collector for medium-moving network health metrics."""

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
        inventory: OrganizationInventory | None = None,
        expiration_manager: MetricExpirationManager | None = None,
    ) -> None:
        """Initialize network health collector with sub-collectors."""
        super().__init__(api, settings, registry, inventory, expiration_manager)

        # Initialize sub-collectors
        self.rf_health_collector = RFHealthCollector(self)
        self.connection_stats_collector = ConnectionStatsCollector(self)
        self.data_rates_collector = DataRatesCollector(self)
        self.bluetooth_collector = BluetoothCollector(self)

    def _initialize_metrics(self) -> None:
        """Initialize network health metrics."""
        # RF channel utilization metrics per AP
        self._ap_utilization_2_4ghz = self._create_gauge(
            NetworkHealthMetricName.AP_CHANNEL_UTILIZATION_2_4GHZ_PERCENT,
            "2.4GHz channel utilization percentage per AP",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.UTILIZATION_TYPE,
            ],
        )

        self._ap_utilization_5ghz = self._create_gauge(
            NetworkHealthMetricName.AP_CHANNEL_UTILIZATION_5GHZ_PERCENT,
            "5GHz channel utilization percentage per AP",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.UTILIZATION_TYPE,
            ],
        )

        # Network-wide average utilization
        self._network_utilization_2_4ghz = self._create_gauge(
            NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_2_4GHZ_PERCENT,
            "Network-wide average 2.4GHz channel utilization percentage",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.UTILIZATION_TYPE,
            ],
        )

        self._network_utilization_5ghz = self._create_gauge(
            NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_5GHZ_PERCENT,
            "Network-wide average 5GHz channel utilization percentage",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.UTILIZATION_TYPE,
            ],
        )

        # Network-wide wireless connection statistics
        self._network_connection_stats = self._create_gauge(
            NetworkMetricName.NETWORK_WIRELESS_CONNECTION_STATS,
            "Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.STAT_TYPE,
            ],
        )

        # Network-wide wireless data rate metrics
        self._network_wireless_download_kbps = self._create_gauge(
            NetworkHealthMetricName.NETWORK_WIRELESS_DOWNLOAD_KBPS,
            "Network-wide wireless download bandwidth in kilobits per second",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._network_wireless_upload_kbps = self._create_gauge(
            NetworkHealthMetricName.NETWORK_WIRELESS_UPLOAD_KBPS,
            "Network-wide wireless upload bandwidth in kilobits per second",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        # Bluetooth clients detected by MR devices
        self._network_bluetooth_clients_total = self._create_gauge(
            NetworkHealthMetricName.NETWORK_BLUETOOTH_CLIENTS_TOTAL,
            "Total number of Bluetooth clients detected by MR devices in the last 5 minutes",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

    async def _collect_impl(self) -> None:
        """Collect network health metrics with parallel organization processing.

        Organizations are processed in parallel with bounded concurrency
        to significantly improve performance for multi-org deployments.
        """
        start_time = asyncio.get_event_loop().time()
        metrics_collected = 0
        organizations_processed = 0
        api_calls_made = 0

        try:
            # Get organizations with error handling
            organizations = await self._fetch_organizations()
            if not organizations:
                logger.warning("No organizations found for network health collection")
                return
            api_calls_made += 1

            logger.info(
                "Starting parallel organization processing",
                org_count=len(organizations),
                concurrency_limit=self.settings.api.concurrency_limit,
            )

            # Process organizations in parallel with bounded concurrency
            async with ManagedTaskGroup(
                name="network_health_collector_orgs",
                max_concurrency=self.settings.api.concurrency_limit,
            ) as group:
                for org in organizations:
                    org_id = org["id"]
                    org_name = org.get("name", org_id)
                    await group.create_task(
                        self._collect_org_network_health(org_id, org_name),
                        name=f"org_{org_id}",
                    )
                    organizations_processed += 1

            # Approximate API calls (actual count may vary)
            api_calls_made += organizations_processed * 5

            # Log collection summary
            log_metric_collection_summary(
                "NetworkHealthCollector",
                metrics_collected=metrics_collected,
                duration_seconds=asyncio.get_event_loop().time() - start_time,
                organizations_processed=organizations_processed,
                api_calls_made=api_calls_made,
            )

        except Exception:
            logger.exception("Failed to collect network health metrics")

    @with_error_handling(
        operation="Fetch organizations",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_organizations(self) -> list[dict[str, Any]] | None:
        """Fetch organizations for network health collection using inventory cache.

        Returns
        -------
        list[dict[str, Any]] | None
            List of organizations or None on error.

        Raises
        ------
        RuntimeError
            If inventory service is not configured.

        """
        if not self.inventory:
            raise RuntimeError(
                "Inventory service not configured for NetworkHealthCollector. "
                "This is a programming error - collectors must be initialized with inventory service."
            )

        self._track_api_call("getOrganizations")
        return await self.inventory.get_organizations()

    @log_batch_operation("collect network health", batch_size=None)
    @with_error_handling(
        operation="Collect organization network health",
        continue_on_error=True,
    )
    async def _collect_org_network_health(self, org_id: str, org_name: str | None = None) -> None:
        """Collect network health metrics for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str | None
            Organization name.

        """
        try:
            # Get all networks
            networks = await self._fetch_networks_for_health(org_id)

            # Add org info to each network
            for network in networks:
                network["orgId"] = org_id
                network["orgName"] = org_name or org_id

            wireless_networks = [
                network
                for network in networks
                if ProductType.WIRELESS in network.get("productTypes", [])
            ]
            if not wireless_networks:
                return

            await process_in_batches_with_errors(
                wireless_networks,
                self._collect_network_health_bundle,
                batch_size=self.settings.api.network_batch_size,
                delay_between_batches=self.settings.api.batch_delay,
                item_description="network health",
                error_context_func=lambda network: {
                    "org_id": org_id,
                    "org_name": org_name or org_id,
                    "network_id": network.get("id"),
                    "network_name": network.get("name"),
                },
            )

        except Exception:
            logger.exception(
                "Failed to collect network health for organization",
                org_id=org_id,
            )

    async def _collect_network_health_bundle(self, network: dict[str, Any]) -> None:
        """Collect all network health sub-metrics for a single network."""
        await self._collect_network_rf_health(network)
        await self._collect_network_connection_stats(network)
        await self._collect_network_data_rates(network)
        await self._collect_network_bluetooth_clients(network)

    @log_api_call("getOrganizationNetworks")
    async def _fetch_networks_for_health(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch networks for health collection.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of networks.

        """
        with LogContext(org_id=org_id):
            networks = await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )
            networks = validate_response_format(
                networks, expected_type=list, operation="getOrganizationNetworks"
            )
            return cast(list[dict[str, Any]], networks)

    async def _collect_network_rf_health(self, network: dict[str, Any]) -> None:
        """Collect RF health metrics for a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        await self.rf_health_collector.collect(network)

    async def _collect_network_connection_stats(self, network: dict[str, Any]) -> None:
        """Collect network-wide wireless connection statistics.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        await self.connection_stats_collector.collect(network)

    async def _collect_network_data_rates(self, network: dict[str, Any]) -> None:
        """Collect network-wide wireless data rate metrics.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        await self.data_rates_collector.collect(network)

    async def _collect_network_bluetooth_clients(self, network: dict[str, Any]) -> None:
        """Collect Bluetooth clients detected by MR devices in a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        await self.bluetooth_collector.collect(network)
