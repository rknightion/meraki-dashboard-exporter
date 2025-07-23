"""Meraki MR (Wireless AP) metrics collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from ...core.constants import MRMetricName
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels, create_network_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.metrics import LabelName
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    from ..device import DeviceCollector

logger = get_logger(__name__)


class MRCollector(BaseDeviceCollector):
    """Collector for Meraki MR (Wireless AP) devices."""

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MR collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance.

        """
        super().__init__(parent)
        # Create a cache for last known packet values (for retention logic)
        self._packet_value_cache: dict[str, float] = {}
        # Initialize MR-specific metrics
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize MR-specific metrics."""
        # Wireless AP metrics
        self._ap_clients = self.parent._create_gauge(
            MRMetricName.MR_CLIENTS_CONNECTED,
            "Number of clients connected to access point",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._ap_connection_stats = self.parent._create_gauge(
            MRMetricName.MR_CONNECTION_STATS,
            "Wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.STAT_TYPE,
            ],
        )

        # MR ethernet status metrics
        self._mr_power_info = self.parent._create_gauge(
            MRMetricName.MR_POWER_INFO,
            "Access point power information",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.MODE,
            ],
        )

        self._mr_power_ac_connected = self.parent._create_gauge(
            MRMetricName.MR_POWER_AC_CONNECTED,
            "Access point AC power connection status (1 = connected, 0 = not connected)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._mr_power_poe_connected = self.parent._create_gauge(
            MRMetricName.MR_POWER_POE_CONNECTED,
            "Access point PoE power connection status (1 = connected, 0 = not connected)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._mr_port_poe_info = self.parent._create_gauge(
            MRMetricName.MR_PORT_POE_INFO,
            "Access point port PoE information",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_NAME,
                LabelName.STANDARD,
            ],
        )

        self._mr_port_link_negotiation_info = self.parent._create_gauge(
            MRMetricName.MR_PORT_LINK_NEGOTIATION_INFO,
            "Access point port link negotiation information",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_NAME,
                LabelName.DUPLEX,
            ],
        )

        self._mr_port_link_negotiation_speed = self.parent._create_gauge(
            MRMetricName.MR_PORT_LINK_NEGOTIATION_SPEED_MBPS,
            "Access point port link negotiation speed in Mbps",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_NAME,
            ],
        )

        self._mr_aggregation_enabled = self.parent._create_gauge(
            MRMetricName.MR_AGGREGATION_ENABLED,
            "Access point port aggregation enabled status (1 = enabled, 0 = disabled)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._mr_aggregation_speed = self.parent._create_gauge(
            MRMetricName.MR_AGGREGATION_SPEED_MBPS,
            "Access point total aggregated port speed in Mbps",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        # MR packet loss metrics (per device, 5-minute window)
        self._mr_packets_downstream_total = self.parent._create_gauge(
            MRMetricName.MR_PACKETS_DOWNSTREAM_TOTAL,
            "Total downstream packets transmitted by access point (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._mr_packets_downstream_lost = self.parent._create_gauge(
            MRMetricName.MR_PACKETS_DOWNSTREAM_LOST,
            "Downstream packets lost by access point (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._mr_packet_loss_downstream_percent = self.parent._create_gauge(
            MRMetricName.MR_PACKET_LOSS_DOWNSTREAM_PERCENT,
            "Downstream packet loss percentage for access point (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._mr_packets_upstream_total = self.parent._create_gauge(
            MRMetricName.MR_PACKETS_UPSTREAM_TOTAL,
            "Total upstream packets received by access point (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._mr_packets_upstream_lost = self.parent._create_gauge(
            MRMetricName.MR_PACKETS_UPSTREAM_LOST,
            "Upstream packets lost by access point (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._mr_packet_loss_upstream_percent = self.parent._create_gauge(
            MRMetricName.MR_PACKET_LOSS_UPSTREAM_PERCENT,
            "Upstream packet loss percentage for access point (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        # Combined packet metrics (calculated)
        self._mr_packets_total = self.parent._create_gauge(
            MRMetricName.MR_PACKETS_TOTAL,
            "Total packets (upstream + downstream) for access point (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._mr_packets_lost_total = self.parent._create_gauge(
            MRMetricName.MR_PACKETS_LOST_TOTAL,
            "Total packets lost (upstream + downstream) for access point (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._mr_packet_loss_total_percent = self.parent._create_gauge(
            MRMetricName.MR_PACKET_LOSS_TOTAL_PERCENT,
            "Total packet loss percentage (upstream + downstream) for access point (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        # Network-wide MR packet loss metrics (5-minute window)
        self._mr_network_packets_downstream_total = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKETS_DOWNSTREAM_TOTAL,
            "Total downstream packets for all access points in network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packets_downstream_lost = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKETS_DOWNSTREAM_LOST,
            "Downstream packets lost for all access points in network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packet_loss_downstream_percent = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKET_LOSS_DOWNSTREAM_PERCENT,
            "Downstream packet loss percentage for all access points in network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packets_upstream_total = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKETS_UPSTREAM_TOTAL,
            "Total upstream packets for all access points in network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packets_upstream_lost = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKETS_UPSTREAM_LOST,
            "Upstream packets lost for all access points in network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packet_loss_upstream_percent = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKET_LOSS_UPSTREAM_PERCENT,
            "Upstream packet loss percentage for all access points in network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        # Combined network-wide packet metrics (calculated)
        self._mr_network_packets_total = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKETS_TOTAL,
            "Total packets (upstream + downstream) for all access points in network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packets_lost_total = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKETS_LOST_TOTAL,
            "Total packets lost (upstream + downstream) for all access points in network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packet_loss_total_percent = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKET_LOSS_TOTAL_PERCENT,
            "Total packet loss percentage (upstream + downstream) for all access points in network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        # MR CPU metrics
        self._mr_cpu_load_5min = self.parent._create_gauge(
            MRMetricName.MR_CPU_LOAD_5MIN,
            "Access point CPU load average over 5 minutes (normalized to 0-100 per core)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        # MR SSID/Radio status metrics
        self._mr_radio_broadcasting = self.parent._create_gauge(
            MRMetricName.MR_RADIO_BROADCASTING,
            "Access point radio broadcasting status (1 = broadcasting, 0 = not broadcasting)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.BAND,
                LabelName.RADIO_INDEX,
            ],
        )

        self._mr_radio_channel = self.parent._create_gauge(
            MRMetricName.MR_RADIO_CHANNEL,
            "Access point radio channel number",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.BAND,
                LabelName.RADIO_INDEX,
            ],
        )

        self._mr_radio_channel_width = self.parent._create_gauge(
            MRMetricName.MR_RADIO_CHANNEL_WIDTH_MHZ,
            "Access point radio channel width in MHz",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.BAND,
                LabelName.RADIO_INDEX,
            ],
        )

        self._mr_radio_power = self.parent._create_gauge(
            MRMetricName.MR_RADIO_POWER_DBM,
            "Access point radio transmit power in dBm",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.BAND,
                LabelName.RADIO_INDEX,
            ],
        )

        # SSID usage metrics (now with network labels)
        self._ssid_usage_total_mb = self.parent._create_gauge(
            MRMetricName.MR_SSID_USAGE_TOTAL_MB,
            "Total data usage in MB by SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SSID,
            ],
        )

        self._ssid_usage_downstream_mb = self.parent._create_gauge(
            MRMetricName.MR_SSID_USAGE_DOWNSTREAM_MB,
            "Downstream data usage in MB by SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SSID,
            ],
        )

        self._ssid_usage_upstream_mb = self.parent._create_gauge(
            MRMetricName.MR_SSID_USAGE_UPSTREAM_MB,
            "Upstream data usage in MB by SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SSID,
            ],
        )

        self._ssid_usage_percentage = self.parent._create_gauge(
            MRMetricName.MR_SSID_USAGE_PERCENTAGE,
            "Percentage of total organization data usage by SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SSID,
            ],
        )

        self._ssid_client_count = self.parent._create_gauge(
            MRMetricName.MR_SSID_CLIENT_COUNT,
            "Number of clients connected to SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SSID,
            ],
        )

    @log_api_call("getDeviceWirelessStatus")
    @with_error_handling(
        operation="Collect MR device metrics",
        continue_on_error=True,
    )
    async def collect(self, device: dict[str, Any]) -> None:
        """Collect wireless AP metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Wireless device data.

        """
        # Extract org info from device data
        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)

        # Create standard device labels
        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)

        try:
            # Get wireless status with timeout
            with LogContext(serial=device_labels["serial"], name=device_labels["name"]):
                status = await asyncio.to_thread(
                    self.api.wireless.getDeviceWirelessStatus,
                    device_labels["serial"],
                )
                status = validate_response_format(
                    status, expected_type=dict, operation="getDeviceWirelessStatus"
                )

            # Client count
            if "clientCount" in status:
                self._ap_clients.labels(**device_labels).set(status["clientCount"])

            # Get connection stats (30 minute window)
            await self._collect_connection_stats(device)

        except Exception:
            logger.exception(
                "Failed to collect wireless metrics",
                serial=device_labels["serial"],
            )

    @log_api_call("getDeviceWirelessConnectionStats")
    @with_error_handling(
        operation="Collect MR connection stats",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_connection_stats(self, device: dict[str, Any]) -> None:
        """Collect wireless connection statistics for the device.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        # Extract org info from device data
        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)

        # Create standard device labels
        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)

        try:
            # Use 30 minute (1800 second) timespan as minimum
            with LogContext(serial=device_labels["serial"], name=device_labels["name"]):
                connection_stats = await asyncio.to_thread(
                    self.api.wireless.getDeviceWirelessConnectionStats,
                    device_labels["serial"],
                    timespan=1800,  # 30 minutes
                )

            # Handle empty response (no data in timespan)
            if not connection_stats or "connectionStats" not in connection_stats:
                logger.debug(
                    "No connection stats data available",
                    serial=device_labels["serial"],
                    timespan="30m",
                )
                # Set all stats to 0 when no data
                for stat_type in ("assoc", "auth", "dhcp", "dns", "success"):
                    # Create labels with stat_type
                    labels = create_device_labels(
                        device, org_id=org_id, org_name=org_name, stat_type=stat_type
                    )
                    self._ap_connection_stats.labels(**labels).set(0)
                return

            stats = connection_stats.get("connectionStats", {})

            # Set metrics for each connection stat type
            for stat_type, value in stats.items():
                if stat_type in {"assoc", "auth", "dhcp", "dns", "success"}:
                    # Create labels with stat_type
                    labels = create_device_labels(
                        device, org_id=org_id, org_name=org_name, stat_type=stat_type
                    )
                    self._ap_connection_stats.labels(**labels).set(value)

        except Exception:
            logger.exception(
                "Failed to collect connection stats",
                serial=device_labels["serial"],
            )

    @log_api_call("getOrganizationWirelessClientsOverviewByDevice")
    @with_error_handling(
        operation="Collect MR wireless clients",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_wireless_clients(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect wireless client counts for MR devices.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table for device info.

        """
        try:
            with LogContext(org_id=org_id):
                client_overview = await asyncio.to_thread(
                    self.api.wireless.getOrganizationWirelessClientsOverviewByDevice,
                    org_id,
                    total_pages="all",
                )
                client_overview = validate_response_format(
                    client_overview,
                    expected_type=list,
                    operation="getOrganizationWirelessClientsOverviewByDevice",
                )

            # Handle different API response formats
            if isinstance(client_overview, dict) and "items" in client_overview:
                client_data = client_overview["items"]
            elif isinstance(client_overview, list):
                client_data = client_overview
            else:
                logger.warning(
                    "Unexpected client overview format",
                    org_id=org_id,
                    response_type=type(client_overview).__name__,
                )
                client_data = []

            # Process each device's client data
            for device_data in client_data:
                serial = device_data.get("serial", "")
                network = device_data.get("network", {})
                network_id = network.get("id", "")
                network_name = network.get("name", network_id)

                # Get online client count
                counts = device_data.get("counts", {})
                by_status = counts.get("byStatus", {})
                online_clients = by_status.get("online", 0)

                # Look up device info from our cache
                device_info = device_lookup.get(serial, {"serial": serial})
                device_info["networkId"] = network_id
                device_info["networkName"] = network_name
                device_info["orgId"] = org_id
                device_info["orgName"] = org_name

                # Create standard device labels
                labels = create_device_labels(device_info, org_id=org_id, org_name=org_name)

                self._ap_clients.labels(**labels).set(online_clients)

        except Exception:
            logger.exception(
                "Failed to collect wireless client counts",
                org_id=org_id,
            )

    @log_api_call("getOrganizationWirelessDevicesEthernetStatuses")
    @with_error_handling(
        operation="Collect MR ethernet status",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_ethernet_status(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect ethernet status for MR devices.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table for device info.

        """
        try:
            with LogContext(org_id=org_id):
                ethernet_statuses = await asyncio.to_thread(
                    self.api.wireless.getOrganizationWirelessDevicesEthernetStatuses,
                    org_id,
                )

            # Handle different API response formats
            if isinstance(ethernet_statuses, dict) and "items" in ethernet_statuses:
                ethernet_data = ethernet_statuses["items"]
            elif isinstance(ethernet_statuses, list):
                ethernet_data = ethernet_statuses
            else:
                logger.warning(
                    "Unexpected ethernet status format",
                    org_id=org_id,
                    response_type=type(ethernet_statuses).__name__,
                )
                ethernet_data = []

            logger.debug(
                "Successfully fetched MR ethernet status",
                org_id=org_id,
                device_count=len(ethernet_data) if ethernet_data else 0,
            )

            # Process each device's ethernet status
            for device_status in ethernet_data:
                serial = device_status.get("serial", "")
                device_info = device_lookup.get(serial, {"serial": serial})

                # Get device data from API response and merge with lookup
                network_info = device_status.get("network", {})
                device_info["networkId"] = network_info.get("id", "")
                device_info["networkName"] = network_info.get("name", device_info["networkId"])
                device_info["name"] = device_info.get("name") or device_status.get("name", serial)
                device_info["orgId"] = org_id
                device_info["orgName"] = org_name

                # Create standard device labels
                device_labels = create_device_labels(device_info, org_id=org_id, org_name=org_name)

                # Power mode information
                power_mode = device_status.get("power", {}).get("mode")
                if power_mode:
                    # Create labels with mode
                    power_labels = create_device_labels(
                        device_info, org_id=org_id, org_name=org_name, mode=power_mode
                    )
                    self._mr_power_info.labels(**power_labels).set(1)

                # AC power status
                ac_info = device_status.get("power", {}).get("ac", {})
                ac_connected = ac_info.get("isConnected", False)
                self._mr_power_ac_connected.labels(**device_labels).set(1 if ac_connected else 0)

                # PoE power status
                poe_info = device_status.get("power", {}).get("poe", {})
                poe_connected = poe_info.get("isConnected", False)
                self._mr_power_poe_connected.labels(**device_labels).set(1 if poe_connected else 0)

                # Process port information
                ports = device_status.get("ports", [])
                aggregation_enabled = False
                total_speed = 0

                for port in ports:
                    port_name = port.get("name", "")

                    # PoE information
                    poe_standard = port.get("poe", {}).get("standard")
                    if poe_standard:
                        # Create port labels with standard
                        poe_labels = create_device_labels(
                            device_info,
                            org_id=org_id,
                            org_name=org_name,
                            port_name=port_name,
                            standard=poe_standard,
                        )
                        self._mr_port_poe_info.labels(**poe_labels).set(1)

                    # Link negotiation information
                    link_negotiation = port.get("linkNegotiation", {})
                    duplex = link_negotiation.get("duplex")
                    speed = link_negotiation.get("speed")

                    if duplex:
                        # Create port labels with duplex
                        duplex_labels = create_device_labels(
                            device_info,
                            org_id=org_id,
                            org_name=org_name,
                            port_name=port_name,
                            duplex=duplex,
                        )
                        self._mr_port_link_negotiation_info.labels(**duplex_labels).set(1)

                    # Set speed metric
                    speed_labels = create_device_labels(
                        device_info, org_id=org_id, org_name=org_name, port_name=port_name
                    )
                    self._mr_port_link_negotiation_speed.labels(**speed_labels).set(
                        speed if speed is not None else 0
                    )

                    # Check for aggregation - Note: ports don't have isAggregated field
                    # but we can get aggregation info from the device level
                    if speed is not None:
                        total_speed += speed

                # Get aggregation info from device level (not per-port)
                aggregation_info = device_status.get("aggregation", {})
                aggregation_enabled = aggregation_info.get("enabled", False)
                # Use aggregation speed from device level if available, otherwise use total from ports
                agg_speed = aggregation_info.get("speed", total_speed)

                self._mr_aggregation_enabled.labels(**device_labels).set(
                    1 if aggregation_enabled else 0
                )
                self._mr_aggregation_speed.labels(**device_labels).set(agg_speed)

        except Exception:
            logger.exception(
                "Failed to collect MR ethernet status",
                org_id=org_id,
            )

    @log_api_call("getOrganizationWirelessDevicesEthernetStatuses")
    async def _fetch_ethernet_statuses(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch ethernet statuses for MR devices.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            Ethernet status data.

        """
        return await asyncio.to_thread(
            self.api.wireless.getOrganizationWirelessDevicesEthernetStatuses,
            org_id,
        )

    @log_api_call("getOrganizationWirelessDevicesPacketLossByDevice")
    async def collect_packet_loss(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect packet loss metrics for MR devices and networks.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table for device info.

        """
        try:
            # Use 10-minute timespan (600 seconds)
            with LogContext(org_id=org_id):
                packet_loss_data = await asyncio.to_thread(
                    self.api.wireless.getOrganizationWirelessDevicesPacketLossByDevice,
                    org_id,
                    timespan=600,  # 10 minutes
                    perPage=1000,
                    total_pages="all",
                )

            # Handle different API response formats
            if isinstance(packet_loss_data, dict) and "items" in packet_loss_data:
                devices_data = packet_loss_data["items"]
            elif isinstance(packet_loss_data, list):
                devices_data = packet_loss_data
            else:
                logger.warning(
                    "Unexpected packet loss data format",
                    org_id=org_id,
                    response_type=type(packet_loss_data).__name__,
                )
                devices_data = []

            # Process each device's packet loss data
            for device_data in devices_data:
                # Extract device info from nested "device" object
                device_info_api = device_data.get("device", {})
                serial = device_info_api.get("serial", "")

                # Get device info from lookup and merge with API data
                device_info = device_lookup.get(serial, {"serial": serial})
                device_info["name"] = device_info_api.get("name") or device_info.get("name", serial)

                # Extract network info
                network_info = device_data.get("network", {})
                device_info["networkId"] = network_info.get("id", "")
                device_info["networkName"] = network_info.get("name", device_info["networkId"])
                device_info["orgId"] = org_id
                device_info["orgName"] = org_name

                # Create standard device labels
                device_labels = create_device_labels(device_info, org_id=org_id, org_name=org_name)

                # Get packet loss data directly from top level (not nested under "packetLoss")
                # Downstream metrics
                downstream = device_data.get("downstream", {})
                downstream_total = downstream.get("total", 0)
                downstream_lost = downstream.get("lost", 0)
                downstream_percent = downstream.get("lossPercentage", 0)

                self._set_packet_metric_value(
                    "_mr_packets_downstream_total",
                    device_labels,
                    downstream_total,
                )

                self._set_packet_metric_value(
                    "_mr_packets_downstream_lost",
                    device_labels,
                    downstream_lost,
                )

                self._set_packet_metric_value(
                    "_mr_packet_loss_downstream_percent",
                    device_labels,
                    downstream_percent,
                )

                # Upstream metrics
                upstream = device_data.get("upstream", {})
                upstream_total = upstream.get("total", 0)
                upstream_lost = upstream.get("lost", 0)
                upstream_percent = upstream.get("lossPercentage", 0)

                self._set_packet_metric_value(
                    "_mr_packets_upstream_total",
                    device_labels,
                    upstream_total,
                )

                self._set_packet_metric_value(
                    "_mr_packets_upstream_lost",
                    device_labels,
                    upstream_lost,
                )

                self._set_packet_metric_value(
                    "_mr_packet_loss_upstream_percent",
                    device_labels,
                    upstream_percent,
                )

                # Combined metrics
                total_packets = downstream_total + upstream_total
                total_lost = downstream_lost + upstream_lost
                total_percent = (total_lost / total_packets * 100) if total_packets > 0 else 0

                self._set_packet_metric_value(
                    "_mr_packets_total",
                    device_labels,
                    total_packets,
                )

                self._set_packet_metric_value(
                    "_mr_packets_lost_total",
                    device_labels,
                    total_lost,
                )

                self._set_packet_metric_value(
                    "_mr_packet_loss_total_percent",
                    device_labels,
                    total_percent,
                )

            # Now collect network-wide packet loss metrics
            network_packet_loss = await self._fetch_network_packet_loss(org_id)

            # Handle different API response formats
            if isinstance(network_packet_loss, dict) and "items" in network_packet_loss:
                networks_data = network_packet_loss["items"]
            elif isinstance(network_packet_loss, list):
                networks_data = network_packet_loss
            else:
                logger.warning(
                    "Unexpected network packet loss format",
                    org_id=org_id,
                    response_type=type(network_packet_loss).__name__,
                )
                networks_data = []

            logger.debug(
                "Successfully fetched network packet loss metrics",
                org_id=org_id,
                network_count=len(networks_data) if networks_data else 0,
            )

            # Process each network's aggregated packet loss
            for network_data in networks_data:
                network_info = network_data.get("network", {})

                # Create network labels with org info
                network_labels = create_network_labels(
                    network_info, org_id=org_id, org_name=org_name
                )

                # Get packet loss data directly from top level (no "packetLoss" wrapper)
                # Downstream metrics
                downstream = network_data.get("downstream", {})
                downstream_total = downstream.get("total", 0)
                downstream_lost = downstream.get("lost", 0)
                downstream_percent = downstream.get("lossPercentage", 0)

                self._set_packet_metric_value(
                    "_mr_network_packets_downstream_total",
                    network_labels,
                    downstream_total,
                )

                self._set_packet_metric_value(
                    "_mr_network_packets_downstream_lost",
                    network_labels,
                    downstream_lost,
                )

                self._set_packet_metric_value(
                    "_mr_network_packet_loss_downstream_percent",
                    network_labels,
                    downstream_percent,
                )

                # Upstream metrics
                upstream = network_data.get("upstream", {})
                upstream_total = upstream.get("total", 0)
                upstream_lost = upstream.get("lost", 0)
                upstream_percent = upstream.get("lossPercentage", 0)

                self._set_packet_metric_value(
                    "_mr_network_packets_upstream_total",
                    network_labels,
                    upstream_total,
                )

                self._set_packet_metric_value(
                    "_mr_network_packets_upstream_lost",
                    network_labels,
                    upstream_lost,
                )

                self._set_packet_metric_value(
                    "_mr_network_packet_loss_upstream_percent",
                    network_labels,
                    upstream_percent,
                )

                # Combined metrics
                total_packets = downstream_total + upstream_total
                total_lost = downstream_lost + upstream_lost
                total_percent = (total_lost / total_packets * 100) if total_packets > 0 else 0

                self._set_packet_metric_value(
                    "_mr_network_packets_total",
                    network_labels,
                    total_packets,
                )

                self._set_packet_metric_value(
                    "_mr_network_packets_lost_total",
                    network_labels,
                    total_lost,
                )

                self._set_packet_metric_value(
                    "_mr_network_packet_loss_total_percent",
                    network_labels,
                    total_percent,
                )

        except Exception:
            logger.exception(
                "Failed to collect MR packet loss metrics",
                org_id=org_id,
            )

    async def collect_cpu_load(
        self, org_id: str, org_name: str, devices: list[dict[str, Any]]
    ) -> None:
        """Collect CPU load metrics for MR devices.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        devices : list[dict[str, Any]]
            List of all devices in the organization.

        """
        try:
            # Filter MR devices
            mr_devices = [d for d in devices if d.get("model", "").startswith("MR")]
            if not mr_devices:
                logger.debug("No MR devices found for CPU load collection", org_id=org_id)
                return

            logger.debug(
                "Fetching CPU load for MR devices",
                org_id=org_id,
                device_count=len(mr_devices),
            )

            # Process MR devices in batches of 100
            batch_size = 100
            for i in range(0, len(mr_devices), batch_size):
                batch = mr_devices[i : i + batch_size]
                await self._process_cpu_load_batch(org_id, org_name, batch, i // batch_size)

        except Exception:
            logger.exception(
                "Failed to collect MR CPU load metrics",
                org_id=org_id,
            )

    async def _process_cpu_load_batch(
        self, org_id: str, org_name: str, batch: list[dict[str, Any]], batch_index: int
    ) -> None:
        """Process a batch of devices for CPU load collection.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        batch : list[dict[str, Any]]
            Batch of devices to process.
        batch_index : int
            Index of the current batch.

        """
        try:
            serials = [d["serial"] for d in batch]

            # Get CPU load history for batch (5 minute intervals)
            self._track_api_call("getOrganizationWirelessDevicesSystemCpuLoadHistory")
            cpu_history = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessDevicesSystemCpuLoadHistory,
                org_id,
                serials=serials,
                timespan=300,  # 5 minutes
                resolution=300,  # 5 minute resolution
            )

            # Handle different API response formats
            cpu_data = self._extract_cpu_data(cpu_history, org_id, batch_index)
            if not cpu_data:
                return

            logger.debug(
                "Successfully fetched CPU history",
                org_id=org_id,
                batch_index=batch_index,
                device_count=len(cpu_data),
            )

            # Process CPU data for each device
            for device_cpu in cpu_data:
                self._process_device_cpu_data(device_cpu, batch, org_id, org_name)

        except Exception:
            logger.exception(
                "Failed to collect CPU load for batch",
                org_id=org_id,
                batch_index=batch_index,
                batch_size=len(batch),
            )

    def _extract_cpu_data(
        self, cpu_history: Any, org_id: str, batch_index: int
    ) -> list[dict[str, Any]]:
        """Extract CPU data from API response.

        Parameters
        ----------
        cpu_history : Any
            Raw API response.
        org_id : str
            Organization ID.
        batch_index : int
            Index of the current batch.

        Returns
        -------
        list[dict[str, Any]]
            Extracted CPU data.

        """
        if isinstance(cpu_history, dict) and "items" in cpu_history:
            return cast(list[dict[str, Any]], cpu_history["items"])
        elif isinstance(cpu_history, list):
            return cast(list[dict[str, Any]], cpu_history)
        else:
            logger.warning(
                "Unexpected CPU history format",
                org_id=org_id,
                batch_index=batch_index,
                response_type=type(cpu_history).__name__,
            )
            return []

    def _process_device_cpu_data(
        self, device_cpu: dict[str, Any], batch: list[dict[str, Any]], org_id: str, org_name: str
    ) -> None:
        """Process CPU data for a single device.

        Parameters
        ----------
        device_cpu : dict[str, Any]
            CPU data for a device.
        batch : list[dict[str, Any]]
            Batch of devices for lookup.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        serial = device_cpu.get("serial", "")
        device_info = next((d for d in batch if d["serial"] == serial), {"serial": serial})

        # Get the network info from API response and merge with device
        network_info = device_cpu.get("network", {})
        device_info["networkId"] = network_info.get("id", device_info.get("networkId", ""))
        device_info["networkName"] = network_info.get("name", device_info["networkId"])
        device_info["orgId"] = org_id
        device_info["orgName"] = org_name

        # Create standard device labels
        device_labels = create_device_labels(device_info, org_id=org_id, org_name=org_name)

        # Get the most recent CPU load data - API returns "series" not "usageHistory"
        series_data = device_cpu.get("series", [])
        if not series_data:
            return

        # Sort by timestamp to get most recent
        series_data.sort(key=lambda x: x.get("ts", ""), reverse=True)
        latest_reading = series_data[0]

        # Get 5-minute load average - API returns "cpuLoad5" not "avg5Minutes"
        # The API returns values in hundredths of percent (22880 = 228.80%)
        # We need to divide by 100 to get the actual percentage
        cpu_load_raw = latest_reading.get("cpuLoad5")
        if cpu_load_raw is None:
            return

        # Convert from hundredths of percent to percentage
        avg_5min = cpu_load_raw / 100.0

        self._mr_cpu_load_5min.labels(**device_labels).set(avg_5min)

    @log_api_call("getOrganizationWirelessSsidsStatusesByDevice")
    async def collect_ssid_status(self, org_id: str, org_name: str) -> None:
        """Collect SSID and radio status for MR devices.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            with LogContext(org_id=org_id):
                ssid_statuses = await asyncio.to_thread(
                    self.api.wireless.getOrganizationWirelessSsidsStatusesByDevice,
                    org_id,
                    perPage=500,  # API limit is 3-500
                    total_pages="all",
                )

            # Handle different API response formats
            if isinstance(ssid_statuses, dict) and "items" in ssid_statuses:
                devices_data = ssid_statuses["items"]
            elif isinstance(ssid_statuses, list):
                devices_data = ssid_statuses
            else:
                logger.warning(
                    "Unexpected SSID status format",
                    org_id=org_id,
                    response_type=type(ssid_statuses).__name__,
                )
                devices_data = []

            # Process each device's SSID and radio status
            for device_data in devices_data:
                # Create device info dict from API data
                device_info = {
                    "serial": device_data.get("serial", ""),
                    "name": device_data.get("name", device_data.get("serial", "")),
                    "model": "MR",  # SSID status is only for MR devices
                    "orgId": org_id,
                    "orgName": org_name,
                }

                # Extract network info
                network = device_data.get("network", {})
                device_info["networkId"] = network.get("id", "")
                device_info["networkName"] = network.get("name", device_info["networkId"])

                # Create standard device labels
                device_labels = create_device_labels(device_info, org_id=org_id, org_name=org_name)

                # Process radio status
                basic_service_sets = device_data.get("basicServiceSets", [])

                # Group radios by band and index
                radio_info = {}
                for bss in basic_service_sets:
                    radio = bss.get("radio", {})
                    band = radio.get("band", "")
                    # Convert string index to integer - API returns index as string
                    index_str = radio.get("index", "0")
                    try:
                        index = int(index_str) if index_str is not None else 0
                    except (ValueError, TypeError):
                        index = 0

                    if band and index is not None:
                        key = (band, index)
                        if key not in radio_info:
                            radio_info[key] = radio

                # Set metrics for each radio
                for (band, index), radio in radio_info.items():
                    # Create radio labels
                    radio_labels = create_device_labels(
                        device_info,
                        org_id=org_id,
                        org_name=org_name,
                        band=band,
                        radio_index=str(index),
                    )

                    # Broadcasting status
                    is_broadcasting = radio.get("isBroadcasting", False)
                    self._mr_radio_broadcasting.labels(**radio_labels).set(
                        1 if is_broadcasting else 0
                    )

                    # Channel
                    channel = radio.get("channel")
                    if channel is not None:
                        self._mr_radio_channel.labels(**radio_labels).set(channel)

                    # Channel width
                    channel_width = radio.get("channelWidth")
                    if channel_width is not None:
                        self._mr_radio_channel_width.labels(**radio_labels).set(channel_width)

                    # Transmit power
                    power = radio.get("power")
                    if power is not None:
                        self._mr_radio_power.labels(**radio_labels).set(power)

                    logger.debug(
                        "Set radio metrics",
                        serial=device_labels["serial"],
                        band=band,
                        index=index,
                        broadcasting=is_broadcasting,
                        channel=channel,
                        channel_width=channel_width,
                        power=power,
                    )

        except Exception:
            logger.exception(
                "Failed to collect MR SSID status",
                org_id=org_id,
            )

    @log_api_call("getOrganizationWirelessDevicesPacketLossByNetwork")
    async def _fetch_network_packet_loss(self, org_id: str) -> Any:
        """Fetch network-wide packet loss metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        Any
            Network packet loss data.

        """
        with LogContext(org_id=org_id):
            return await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessDevicesPacketLossByNetwork,
                org_id,
                timespan=300,  # 5 minutes
                perPage=1000,
                total_pages="all",
            )

    def _set_packet_metric_value(
        self, metric_name: str, labels: dict[str, str], value: float | None
    ) -> None:
        """Set packet metric value with retention logic for total packet counters.

        For packet loss metrics, 0 is a valid value. For total packet counters,
        we retain the last known value if the API returns None or 0.

        This caching strategy is necessary because the Meraki API sometimes returns
        0 or null for total packet counters when there's no recent activity, but
        Prometheus rate() calculations need monotonically increasing counters.

        Parameters
        ----------
        metric_name : str
            Name of the metric attribute.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float | None
            Value to set. May be None if API returned null.

        Examples
        --------
        >>> # Total packets - will use cache if API returns 0
        >>> collector._set_packet_metric_value(
        ...     "_mr_packets_total",
        ...     {"serial": "Q2KD-XXXX", "name": "Office AP"},
        ...     0  # Will use cached value instead
        ... )

        >>> # Packet loss percentage - 0 is valid
        >>> collector._set_packet_metric_value(
        ...     "_mr_packet_loss_percent",
        ...     {"serial": "Q2KD-XXXX", "name": "Office AP"},
        ...     0  # Will set to 0 (no caching)
        ... )

        Notes
        -----
        The cache is maintained for the lifetime of the collector instance.
        Cache keys include all label values to ensure uniqueness per device/network.
        Only metrics with "total" in the name (excluding "percent") use caching.

        """
        # Create a cache key from metric name and sorted labels
        cache_key = f"{metric_name}:{':'.join(f'{k}={v}' for k, v in sorted(labels.items()))}"

        # Determine if this is a "total" metric that should retain values
        is_total_metric = "total" in metric_name and "percent" not in metric_name

        # For total metrics, use cached value if current value is None or 0
        if is_total_metric:
            if value is None or value == 0:
                # Use cached value if available
                if cache_key in self._packet_value_cache:
                    value = self._packet_value_cache[cache_key]
                    logger.debug(
                        "Using cached packet value",
                        metric_name=metric_name,
                        cached_value=value,
                        cache_key=cache_key,
                    )
            else:
                # Update cache with new non-zero value
                self._packet_value_cache[cache_key] = value

        # Direct metric setting
        metric = getattr(self, metric_name, None)
        if metric and value is not None:
            try:
                metric.labels(**labels).set(value)
            except Exception:
                logger.exception(
                    "Failed to set packet metric value",
                    metric_name=metric_name,
                    labels=labels,
                    value=value,
                )

    async def _build_ssid_to_network_mapping(self, org_id: str) -> dict[str, list[dict[str, str]]]:
        """Build a mapping of SSID names to their networks.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        dict[str, list[dict[str, str]]]
            Mapping of SSID name to list of networks (can be in multiple networks).

        """
        ssid_to_networks: dict[str, list[dict[str, str]]] = {}

        try:
            # Get all networks for the organization
            networks = await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )

            # For each network, get its SSIDs
            for network in networks:
                network_id = network.get("id")
                network_name = network.get("name", network_id)

                # Only process networks with wireless
                if "wireless" in network.get("productTypes", []):
                    try:
                        # Get SSIDs for this network
                        ssids = await asyncio.to_thread(
                            self.api.wireless.getNetworkWirelessSsids,
                            network_id,
                        )

                        # Map each enabled SSID to this network
                        for ssid in ssids:
                            if ssid.get("enabled", False):
                                ssid_name = ssid.get("name")
                                if ssid_name:
                                    if ssid_name not in ssid_to_networks:
                                        ssid_to_networks[ssid_name] = []
                                    ssid_to_networks[ssid_name].append({
                                        "network_id": network_id,
                                        "network_name": network_name,
                                    })
                    except Exception as e:
                        # Skip networks where we can't get SSID info
                        logger.debug(
                            "Failed to get SSIDs for network",
                            network_id=network_id,
                            error=str(e),
                        )
                        continue

        except Exception:
            logger.exception(
                "Failed to build SSID to network mapping",
                org_id=org_id,
            )

        return ssid_to_networks

    @log_api_call("getOrganizationSummaryTopSsidsByUsage")
    @with_error_handling(
        operation="Collect SSID usage metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_ssid_usage(self, org_id: str, org_name: str) -> None:
        """Collect SSID usage metrics for the organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            # First build SSID to network mapping
            ssid_to_networks = await self._build_ssid_to_network_mapping(org_id)

            with LogContext(org_id=org_id, org_name=org_name):
                # Get top SSIDs by usage with default 1 day timespan
                ssid_usage = await asyncio.to_thread(
                    self.api.organizations.getOrganizationSummaryTopSsidsByUsage,
                    org_id,
                    # No timespan parameter - use default 1 day
                )

            # Process each SSID's usage data
            for ssid_data in ssid_usage:
                ssid_name = ssid_data.get("name", "Unknown")
                usage = ssid_data.get("usage", {})
                clients = ssid_data.get("clients", {})

                # Usage metrics (already in MB)
                total_mb = usage.get("total", 0)
                downstream_mb = usage.get("downstream", 0)
                upstream_mb = usage.get("upstream", 0)
                percentage = usage.get("percentage", 0)

                # Client count
                client_count = clients.get("counts", {}).get("total", 0)

                # Look up networks for this SSID
                networks_for_ssid = ssid_to_networks.get(ssid_name, [])

                if len(networks_for_ssid) == 0:
                    # SSID not found in mapping (maybe disabled or mapping failed)
                    network_id = "unknown"
                    network_name = "unknown"
                elif len(networks_for_ssid) == 1:
                    # SSID exists in only one network
                    network_id = networks_for_ssid[0]["network_id"]
                    network_name = networks_for_ssid[0]["network_name"]
                else:
                    # SSID exists in multiple networks - usage is aggregated
                    network_id = "multiple"
                    network_name = f"multiple_({len(networks_for_ssid)}_networks)"

                # Set metrics with network labels
                self._ssid_usage_total_mb.labels(
                    org_id=org_id,
                    org_name=org_name,
                    network_id=network_id,
                    network_name=network_name,
                    ssid=ssid_name,
                ).set(total_mb)

                self._ssid_usage_downstream_mb.labels(
                    org_id=org_id,
                    org_name=org_name,
                    network_id=network_id,
                    network_name=network_name,
                    ssid=ssid_name,
                ).set(downstream_mb)

                self._ssid_usage_upstream_mb.labels(
                    org_id=org_id,
                    org_name=org_name,
                    network_id=network_id,
                    network_name=network_name,
                    ssid=ssid_name,
                ).set(upstream_mb)

                self._ssid_usage_percentage.labels(
                    org_id=org_id,
                    org_name=org_name,
                    network_id=network_id,
                    network_name=network_name,
                    ssid=ssid_name,
                ).set(percentage)

                self._ssid_client_count.labels(
                    org_id=org_id,
                    org_name=org_name,
                    network_id=network_id,
                    network_name=network_name,
                    ssid=ssid_name,
                ).set(client_count)

            logger.debug(
                "Collected SSID usage metrics",
                org_id=org_id,
                ssid_count=len(ssid_usage),
                mapped_ssids=len(ssid_to_networks),
            )

        except Exception:
            logger.exception(
                "Failed to collect SSID usage metrics",
                org_id=org_id,
            )
