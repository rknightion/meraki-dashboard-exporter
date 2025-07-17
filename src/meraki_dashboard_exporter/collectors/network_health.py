"""Medium-tier network health metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..core.collector import MetricCollector
from ..core.constants import NetworkHealthMetricName, NetworkMetricName, ProductType, UpdateTier
from ..core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ..core.logging import get_logger
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

logger = get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)
class NetworkHealthCollector(MetricCollector):
    """Collector for medium-moving network health metrics."""

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
    ) -> None:
        """Initialize network health collector with sub-collectors."""
        super().__init__(api, settings, registry)

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
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME, LabelName.SERIAL, LabelName.NAME, LabelName.MODEL, LabelName.TYPE],
        )

        self._ap_utilization_5ghz = self._create_gauge(
            NetworkHealthMetricName.AP_CHANNEL_UTILIZATION_5GHZ_PERCENT,
            "5GHz channel utilization percentage per AP",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME, LabelName.SERIAL, LabelName.NAME, LabelName.MODEL, LabelName.TYPE],
        )

        # Network-wide average utilization
        self._network_utilization_2_4ghz = self._create_gauge(
            NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_2_4GHZ_PERCENT,
            "Network-wide average 2.4GHz channel utilization percentage",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME, LabelName.TYPE],
        )

        self._network_utilization_5ghz = self._create_gauge(
            NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_5GHZ_PERCENT,
            "Network-wide average 5GHz channel utilization percentage",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME, LabelName.TYPE],
        )

        # Network-wide wireless connection statistics
        self._network_connection_stats = self._create_gauge(
            NetworkMetricName.NETWORK_WIRELESS_CONNECTION_STATS,
            "Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME, LabelName.STAT_TYPE],
        )

        # Network-wide wireless data rate metrics
        self._network_wireless_download_kbps = self._create_gauge(
            NetworkHealthMetricName.NETWORK_WIRELESS_DOWNLOAD_KBPS,
            "Network-wide wireless download bandwidth in kilobits per second",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._network_wireless_upload_kbps = self._create_gauge(
            NetworkHealthMetricName.NETWORK_WIRELESS_UPLOAD_KBPS,
            "Network-wide wireless upload bandwidth in kilobits per second",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        # Bluetooth clients detected by MR devices
        self._network_bluetooth_clients_total = self._create_gauge(
            NetworkHealthMetricName.NETWORK_BLUETOOTH_CLIENTS_TOTAL,
            "Total number of Bluetooth clients detected by MR devices in the last 5 minutes",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

    async def _collect_impl(self) -> None:
        """Collect network health metrics."""
        try:
            # Get organizations with error handling
            organizations = await self._fetch_organizations()
            if not organizations:
                logger.warning("No organizations found for network health collection")
                return

            # Collect network health for each organization
            org_ids = [org["id"] for org in organizations]
            for org_id in org_ids:
                await self._collect_org_network_health(org_id)

        except Exception:
            logger.exception("Failed to collect network health metrics")

    @with_error_handling(
        operation="Fetch organizations",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_organizations(self) -> list[dict[str, Any]] | None:
        """Fetch organizations for network health collection.

        Returns
        -------
        list[dict[str, Any]] | None
            List of organizations or None on error.

        """
        if self.settings.org_id:
            return [{"id": self.settings.org_id}]
        else:
            logger.debug("Fetching all organizations for network health")
            self._track_api_call("getOrganizations")
            orgs = await asyncio.to_thread(self.api.organizations.getOrganizations)
            orgs = validate_response_format(
                orgs,
                expected_type=list,
                operation="getOrganizations"
            )
            logger.debug("Successfully fetched organizations", count=len(orgs))
            return orgs

    @with_error_handling(
        operation="Collect organization network health",
        continue_on_error=True,
    )
    async def _collect_org_network_health(self, org_id: str) -> None:
        """Collect network health metrics for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        """
        try:
            # Get all networks
            logger.debug("Fetching networks for health collection", org_id=org_id)
            self._track_api_call("getOrganizationNetworks")
            networks = await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )
            networks = validate_response_format(
                networks,
                expected_type=list,
                operation="getOrganizationNetworks"
            )
            logger.debug("Successfully fetched networks", org_id=org_id, count=len(networks))

            # Collect health metrics for each network in batches
            # to avoid overwhelming the API connection pool
            batch_size = 10
            for i in range(0, len(networks), batch_size):
                batch = networks[i : i + batch_size]
                tasks = []

                # Use list comprehension for better performance
                tasks = [
                    self._collect_network_rf_health(network)
                    for network in batch
                    if ProductType.WIRELESS in network.get("productTypes", [])
                ]

                # Also collect connection stats for wireless networks
                connection_tasks = [
                    self._collect_network_connection_stats(network)
                    for network in batch
                    if ProductType.WIRELESS in network.get("productTypes", [])
                ]

                # Also collect data rate metrics for wireless networks
                data_rate_tasks = [
                    self._collect_network_data_rates(network)
                    for network in batch
                    if ProductType.WIRELESS in network.get("productTypes", [])
                ]

                # Also collect Bluetooth clients for wireless networks
                bluetooth_tasks = [
                    self._collect_network_bluetooth_clients(network)
                    for network in batch
                    if ProductType.WIRELESS in network.get("productTypes", [])
                ]

                all_tasks = tasks + connection_tasks + data_rate_tasks + bluetooth_tasks
                if all_tasks:
                    await asyncio.gather(*all_tasks, return_exceptions=True)

        except Exception:
            logger.exception(
                "Failed to collect network health for organization",
                org_id=org_id,
            )

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
