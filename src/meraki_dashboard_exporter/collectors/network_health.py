"""Medium-tier network health metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..core.collector import MetricCollector
from ..core.constants import MetricName, UpdateTier
from ..core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class NetworkHealthCollector(MetricCollector):
    """Collector for medium-moving network health metrics."""

    # Network health data updates at medium frequency
    update_tier: UpdateTier = UpdateTier.MEDIUM

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
        network_id = network["id"]
        network_name = network.get("name", network_id)

        try:
            # Get channel utilization
            logger.debug(
                "Fetching channel utilization",
                network_id=network_id,
                network_name=network_name,
            )

            # Get AP names for lookup
            logger.debug("Fetching network devices for RF health", network_id=network_id)
            self._track_api_call("getNetworkDevices")
            devices = await asyncio.to_thread(
                self.api.networks.getNetworkDevices,
                network_id,
            )
            logger.debug("Successfully fetched devices", network_id=network_id, count=len(devices))
            device_names = {
                d["serial"]: d.get("name", d["serial"])
                for d in devices
                if d.get("model", "").startswith("MR")
            }

            logger.debug("Fetching channel utilization data", network_id=network_id)
            self._track_api_call("getNetworkNetworkHealthChannelUtilization")
            channel_util = await asyncio.to_thread(
                self.api.networks.getNetworkNetworkHealthChannelUtilization,
                network_id,
                total_pages="all",
            )
            logger.debug(
                "Successfully fetched channel utilization",
                network_id=network_id,
                ap_count=len(channel_util) if channel_util else 0,
            )

            if channel_util:
                # Track network-wide averages
                network_2_4ghz_total = {"total": 0, "wifi": 0, "non_wifi": 0, "count": 0}
                network_5ghz_total = {"total": 0, "wifi": 0, "non_wifi": 0, "count": 0}

                for ap_data in channel_util:
                    serial = ap_data.get("serial", "")
                    model = ap_data.get("model", "")
                    name = device_names.get(serial, serial)

                    # Process 2.4GHz (wifi0)
                    if "wifi0" in ap_data and ap_data["wifi0"]:
                        latest_2_4 = ap_data["wifi0"][0]  # Get most recent data
                        total_util = latest_2_4.get("utilization", 0)
                        wifi_util = latest_2_4.get("wifi", 0)
                        non_wifi_util = latest_2_4.get("nonWifi", 0)

                        # Set per-AP metrics for total utilization
                        self._set_metric_value(
                            "_ap_utilization_2_4ghz",
                            {
                                "network_id": network_id,
                                "network_name": network_name,
                                "serial": serial,
                                "name": name,
                                "model": model,
                                "type": "total",
                            },
                            total_util,
                        )

                        # Set per-AP metrics for WiFi utilization
                        self._set_metric_value(
                            "_ap_utilization_2_4ghz",
                            {
                                "network_id": network_id,
                                "network_name": network_name,
                                "serial": serial,
                                "name": name,
                                "model": model,
                                "type": "wifi",
                            },
                            wifi_util,
                        )

                        # Set per-AP metrics for non-WiFi utilization
                        self._set_metric_value(
                            "_ap_utilization_2_4ghz",
                            {
                                "network_id": network_id,
                                "network_name": network_name,
                                "serial": serial,
                                "name": name,
                                "model": model,
                                "type": "non_wifi",
                            },
                            non_wifi_util,
                        )

                        # Update network totals
                        network_2_4ghz_total["total"] += total_util
                        network_2_4ghz_total["wifi"] += wifi_util
                        network_2_4ghz_total["non_wifi"] += non_wifi_util
                        network_2_4ghz_total["count"] += 1

                    # Process 5GHz (wifi1)
                    if "wifi1" in ap_data and ap_data["wifi1"]:
                        latest_5 = ap_data["wifi1"][0]  # Get most recent data
                        total_util = latest_5.get("utilization", 0)
                        wifi_util = latest_5.get("wifi", 0)
                        non_wifi_util = latest_5.get("nonWifi", 0)

                        # Set per-AP metrics for total utilization
                        self._set_metric_value(
                            "_ap_utilization_5ghz",
                            {
                                "network_id": network_id,
                                "network_name": network_name,
                                "serial": serial,
                                "name": name,
                                "model": model,
                                "type": "total",
                            },
                            total_util,
                        )

                        # Set per-AP metrics for WiFi utilization
                        self._set_metric_value(
                            "_ap_utilization_5ghz",
                            {
                                "network_id": network_id,
                                "network_name": network_name,
                                "serial": serial,
                                "name": name,
                                "model": model,
                                "type": "wifi",
                            },
                            wifi_util,
                        )

                        # Set per-AP metrics for non-WiFi utilization
                        self._set_metric_value(
                            "_ap_utilization_5ghz",
                            {
                                "network_id": network_id,
                                "network_name": network_name,
                                "serial": serial,
                                "name": name,
                                "model": model,
                                "type": "non_wifi",
                            },
                            non_wifi_util,
                        )

                        # Update network totals
                        network_5ghz_total["total"] += total_util
                        network_5ghz_total["wifi"] += wifi_util
                        network_5ghz_total["non_wifi"] += non_wifi_util
                        network_5ghz_total["count"] += 1

                # Calculate and set network-wide averages
                if network_2_4ghz_total["count"] > 0:
                    avg_total_2_4 = network_2_4ghz_total["total"] / network_2_4ghz_total["count"]
                    avg_wifi_2_4 = network_2_4ghz_total["wifi"] / network_2_4ghz_total["count"]
                    avg_non_wifi_2_4 = (
                        network_2_4ghz_total["non_wifi"] / network_2_4ghz_total["count"]
                    )

                    self._set_metric_value(
                        "_network_utilization_2_4ghz",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "type": "total",
                        },
                        avg_total_2_4,
                    )

                    self._set_metric_value(
                        "_network_utilization_2_4ghz",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "type": "wifi",
                        },
                        avg_wifi_2_4,
                    )

                    self._set_metric_value(
                        "_network_utilization_2_4ghz",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "type": "non_wifi",
                        },
                        avg_non_wifi_2_4,
                    )

                if network_5ghz_total["count"] > 0:
                    avg_total_5 = network_5ghz_total["total"] / network_5ghz_total["count"]
                    avg_wifi_5 = network_5ghz_total["wifi"] / network_5ghz_total["count"]
                    avg_non_wifi_5 = network_5ghz_total["non_wifi"] / network_5ghz_total["count"]

                    self._set_metric_value(
                        "_network_utilization_5ghz",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "type": "total",
                        },
                        avg_total_5,
                    )

                    self._set_metric_value(
                        "_network_utilization_5ghz",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "type": "wifi",
                        },
                        avg_wifi_5,
                    )

                    self._set_metric_value(
                        "_network_utilization_5ghz",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "type": "non_wifi",
                        },
                        avg_non_wifi_5,
                    )

                logger.debug(
                    "Successfully collected RF health metrics",
                    network_id=network_id,
                    network_name=network_name,
                    ap_2_4ghz_count=network_2_4ghz_total["count"],
                    ap_5ghz_count=network_5ghz_total["count"],
                )

        except Exception as e:
            # Log at debug level if it's just not available (400/404 errors)
            error_str = str(e)
            if "400" in error_str or "404" in error_str or "Bad Request" in error_str:
                logger.debug(
                    "Channel utilization not available",
                    network_id=network_id,
                    network_name=network_name,
                    error=error_str,
                )
            else:
                logger.exception(
                    "Failed to collect RF health metrics",
                    network_id=network_id,
                    network_name=network_name,
                )

    async def _collect_network_connection_stats(self, network: dict[str, Any]) -> None:
        """Collect network-wide wireless connection statistics.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        network_id = network["id"]
        network_name = network.get("name", network_id)

        try:
            logger.debug(
                "Fetching network connection stats",
                network_id=network_id,
                network_name=network_name,
            )

            # Track API call
            self._track_api_call("getNetworkWirelessConnectionStats")

            # Use 30 minute (1800 second) timespan as minimum
            connection_stats = await asyncio.to_thread(
                self.api.wireless.getNetworkWirelessConnectionStats,
                network_id,
                timespan=1800,  # 30 minutes
            )

            # Handle empty response (no data in timespan)
            if not connection_stats:
                logger.debug(
                    "No connection stats data available",
                    network_id=network_id,
                    timespan="30m",
                )
                # Set all stats to 0 when no data
                for stat_type in ("assoc", "auth", "dhcp", "dns", "success"):
                    self._set_metric_value(
                        "_network_connection_stats",
                        {
                            "network_id": network_id,
                            "network_name": network_name,
                            "stat_type": stat_type,
                        },
                        0,
                    )
                return

            # Set metrics for each connection stat type
            for stat_type in ("assoc", "auth", "dhcp", "dns", "success"):
                value = connection_stats.get(stat_type, 0)
                self._set_metric_value(
                    "_network_connection_stats",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                        "stat_type": stat_type,
                    },
                    value,
                )

            logger.debug(
                "Successfully collected network connection stats",
                network_id=network_id,
                stats=connection_stats,
            )

        except Exception as e:
            # Log at debug level if it's just not available (400/404 errors)
            error_str = str(e)
            if "400" in error_str or "404" in error_str or "Bad Request" in error_str:
                logger.debug(
                    "Network connection stats not available",
                    network_id=network_id,
                    network_name=network_name,
                    error=error_str,
                )
            else:
                logger.exception(
                    "Failed to collect network connection stats",
                    network_id=network_id,
                    network_name=network_name,
                )

    async def _collect_network_data_rates(self, network: dict[str, Any]) -> None:
        """Collect network-wide wireless data rate metrics.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        network_id = network["id"]
        network_name = network.get("name", network_id)

        try:
            logger.debug(
                "Fetching network data rates",
                network_id=network_id,
                network_name=network_name,
            )

            # Track API call
            self._track_api_call("getNetworkWirelessDataRateHistory")

            # Use 300 second (5 minute) resolution with recent timespan
            # Using timespan of 300 seconds to get the most recent 5-minute data block
            data_rate_history = await asyncio.to_thread(
                self.api.wireless.getNetworkWirelessDataRateHistory,
                network_id,
                timespan=300,
                resolution=300,
            )

            # Handle empty response
            if not data_rate_history:
                logger.debug(
                    "No data rate history available",
                    network_id=network_id,
                )
                return

            # Get the most recent data point
            if isinstance(data_rate_history, list) and len(data_rate_history) > 0:
                # Sort by endTs to ensure we get the most recent
                sorted_data = sorted(
                    data_rate_history, key=lambda x: x.get("endTs", ""), reverse=True
                )
                latest_data = sorted_data[0]

                # Extract download and upload rates
                download_kbps = latest_data.get("downloadKbps", 0)
                upload_kbps = latest_data.get("uploadKbps", 0)

                # Set the metrics
                self._set_metric_value(
                    "_network_wireless_download_kbps",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    download_kbps,
                )

                self._set_metric_value(
                    "_network_wireless_upload_kbps",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upload_kbps,
                )

                logger.debug(
                    "Successfully collected network data rates",
                    network_id=network_id,
                    download_kbps=download_kbps,
                    upload_kbps=upload_kbps,
                )

        except Exception as e:
            # Log at debug level if it's just not available (400/404 errors)
            error_str = str(e)
            if "400" in error_str or "404" in error_str or "Bad Request" in error_str:
                logger.debug(
                    "Network data rates not available",
                    network_id=network_id,
                    network_name=network_name,
                    error=error_str,
                )
            else:
                logger.exception(
                    "Failed to collect network data rates",
                    network_id=network_id,
                    network_name=network_name,
                )

    async def _collect_network_bluetooth_clients(self, network: dict[str, Any]) -> None:
        """Collect Bluetooth clients detected by MR devices in a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        network_id = network["id"]
        network_name = network.get("name", network_id)

        try:
            logger.debug(
                "Fetching Bluetooth clients",
                network_id=network_id,
                network_name=network_name,
            )

            # Track API call
            self._track_api_call("getNetworkBluetoothClients")

            # Get Bluetooth clients for the last 5 minutes with page size 1000
            bluetooth_clients = await asyncio.to_thread(
                self.api.networks.getNetworkBluetoothClients,
                network_id,
                timespan=300,  # 5 minutes
                perPage=1000,
                total_pages="all",
            )

            # Count the total number of Bluetooth clients
            client_count = len(bluetooth_clients) if bluetooth_clients else 0

            # Set the metric
            self._set_metric_value(
                "_network_bluetooth_clients_total",
                {
                    "network_id": network_id,
                    "network_name": network_name,
                },
                client_count,
            )

            logger.debug(
                "Successfully collected Bluetooth clients",
                network_id=network_id,
                network_name=network_name,
                client_count=client_count,
            )

        except Exception as e:
            # Log at debug level if it's just not available (400/404 errors)
            error_str = str(e)
            if "400" in error_str or "404" in error_str or "Bad Request" in error_str:
                logger.debug(
                    "Bluetooth clients API not available",
                    network_id=network_id,
                    network_name=network_name,
                    error=error_str,
                )
                # Set metric to 0 when API is not available
                self._set_metric_value(
                    "_network_bluetooth_clients_total",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    0,
                )
            else:
                logger.exception(
                    "Failed to collect Bluetooth clients",
                    network_id=network_id,
                    network_name=network_name,
                )
