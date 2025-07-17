"""Medium-tier network health metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..core.collector import MetricCollector
from ..core.constants import MetricName, UpdateTier
from ..core.logging import get_logger
from .network_health_collectors.bluetooth import BluetoothCollector
from .network_health_collectors.connection_stats import ConnectionStatsCollector
from .network_health_collectors.data_rates import DataRatesCollector
from .network_health_collectors.rf_health import RFHealthCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings

logger = get_logger(__name__)


class NetworkHealthCollector(MetricCollector):
    """Collector for medium-moving network health metrics."""

    # Network health data updates at medium frequency
    update_tier: UpdateTier = UpdateTier.MEDIUM

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

    def _set_metric_value(
        self, metric_name: str, labels: dict[str, str], value: float | None
    ) -> None:
        """Safely set a metric value with validation.

        Parameters
        ----------
        metric_name : str
            Name of the metric attribute.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float | None
            Value to set. If None, the metric will not be updated.

        """
        # Skip if value is None - this happens when API returns null values
        if value is None:
            logger.debug(
                "Skipping metric update due to None value",
                metric_name=metric_name,
                labels=labels,
            )
            return

        metric = getattr(self, metric_name, None)
        if metric is None:
            logger.debug(
                "Metric not found",
                metric_name=metric_name,
            )
            return

        try:
            metric.labels(**labels).set(value)
            logger.debug(
                "Set metric value",
                metric_name=metric_name,
                labels=labels,
                value=value,
            )
        except Exception:
            logger.exception(
                "Failed to set metric value",
                metric_name=metric_name,
                labels=labels,
                value=value,
            )

    def _initialize_metrics(self) -> None:
        """Initialize network health metrics."""
        # RF channel utilization metrics per AP
        self._ap_utilization_2_4ghz = self._create_gauge(
            "meraki_ap_channel_utilization_2_4ghz_percent",
            "2.4GHz channel utilization percentage per AP",
            labelnames=["network_id", "network_name", "serial", "name", "model", "type"],
        )

        self._ap_utilization_5ghz = self._create_gauge(
            "meraki_ap_channel_utilization_5ghz_percent",
            "5GHz channel utilization percentage per AP",
            labelnames=["network_id", "network_name", "serial", "name", "model", "type"],
        )

        # Network-wide average utilization
        self._network_utilization_2_4ghz = self._create_gauge(
            "meraki_network_channel_utilization_2_4ghz_percent",
            "Network-wide average 2.4GHz channel utilization percentage",
            labelnames=["network_id", "network_name", "type"],
        )

        self._network_utilization_5ghz = self._create_gauge(
            "meraki_network_channel_utilization_5ghz_percent",
            "Network-wide average 5GHz channel utilization percentage",
            labelnames=["network_id", "network_name", "type"],
        )

        # Network-wide wireless connection statistics
        self._network_connection_stats = self._create_gauge(
            MetricName.NETWORK_WIRELESS_CONNECTION_STATS,
            "Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)",
            labelnames=["network_id", "network_name", "stat_type"],
        )

        # Network-wide wireless data rate metrics
        self._network_wireless_download_kbps = self._create_gauge(
            "meraki_network_wireless_download_kbps",
            "Network-wide wireless download bandwidth in kilobits per second",
            labelnames=["network_id", "network_name"],
        )

        self._network_wireless_upload_kbps = self._create_gauge(
            "meraki_network_wireless_upload_kbps",
            "Network-wide wireless upload bandwidth in kilobits per second",
            labelnames=["network_id", "network_name"],
        )

        # Bluetooth clients detected by MR devices
        self._network_bluetooth_clients_total = self._create_gauge(
            "meraki_network_bluetooth_clients_total",
            "Total number of Bluetooth clients detected by MR devices in the last 5 minutes",
            labelnames=["network_id", "network_name"],
        )

    async def _collect_impl(self) -> None:
        """Collect network health metrics."""
        try:
            # Get organizations
            if self.settings.org_id:
                org_ids = [self.settings.org_id]
            else:
                logger.debug("Fetching all organizations for network health")
                self._track_api_call("getOrganizations")
                orgs = await asyncio.to_thread(self.api.organizations.getOrganizations)
                org_ids = [org["id"] for org in orgs]
                logger.debug("Successfully fetched organizations", count=len(org_ids))

            # Collect network health for each organization
            for org_id in org_ids:
                await self._collect_org_network_health(org_id)

        except Exception:
            logger.exception("Failed to collect network health metrics")

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
                    if "wireless" in network.get("productTypes", [])
                ]

                # Also collect connection stats for wireless networks
                connection_tasks = [
                    self._collect_network_connection_stats(network)
                    for network in batch
                    if "wireless" in network.get("productTypes", [])
                ]

                # Also collect data rate metrics for wireless networks
                data_rate_tasks = [
                    self._collect_network_data_rates(network)
                    for network in batch
                    if "wireless" in network.get("productTypes", [])
                ]

                # Also collect Bluetooth clients for wireless networks
                bluetooth_tasks = [
                    self._collect_network_bluetooth_clients(network)
                    for network in batch
                    if "wireless" in network.get("productTypes", [])
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
