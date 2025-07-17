"""Meraki MR (Wireless AP) metrics collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants import MetricName
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.logging import get_logger
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
            MetricName.MR_CLIENTS_CONNECTED,
            "Number of clients connected to access point",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.MODEL, LabelName.NETWORK_ID],
        )

        self._ap_connection_stats = self.parent._create_gauge(
            MetricName.MR_CONNECTION_STATS,
            "Wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.MODEL, LabelName.NETWORK_ID, LabelName.STAT_TYPE],
        )

        # MR ethernet status metrics
        self._mr_power_info = self.parent._create_gauge(
            MetricName.MR_POWER_INFO,
            "Access point power information",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.MODE],
        )

        self._mr_power_ac_connected = self.parent._create_gauge(
            MetricName.MR_POWER_AC_CONNECTED,
            "Access point AC power connection status (1 = connected, 0 = not connected)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID],
        )

        self._mr_power_poe_connected = self.parent._create_gauge(
            MetricName.MR_POWER_POE_CONNECTED,
            "Access point PoE power connection status (1 = connected, 0 = not connected)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID],
        )

        self._mr_port_poe_info = self.parent._create_gauge(
            MetricName.MR_PORT_POE_INFO,
            "Access point port PoE information",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.PORT_NAME, LabelName.STANDARD],
        )

        self._mr_port_link_negotiation_info = self.parent._create_gauge(
            MetricName.MR_PORT_LINK_NEGOTIATION_INFO,
            "Access point port link negotiation information",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.PORT_NAME, LabelName.DUPLEX],
        )

        self._mr_port_link_negotiation_speed = self.parent._create_gauge(
            MetricName.MR_PORT_LINK_NEGOTIATION_SPEED_MBPS,
            "Access point port link negotiation speed in Mbps",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.PORT_NAME],
        )

        self._mr_aggregation_enabled = self.parent._create_gauge(
            MetricName.MR_AGGREGATION_ENABLED,
            "Access point port aggregation enabled status (1 = enabled, 0 = disabled)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID],
        )

        self._mr_aggregation_speed = self.parent._create_gauge(
            MetricName.MR_AGGREGATION_SPEED_MBPS,
            "Access point total aggregated port speed in Mbps",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID],
        )

        # MR packet loss metrics (per device, 5-minute window)
        self._mr_packets_downstream_total = self.parent._create_gauge(
            MetricName.MR_PACKETS_DOWNSTREAM_TOTAL,
            "Total downstream packets transmitted by access point (5-minute window)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_packets_downstream_lost = self.parent._create_gauge(
            MetricName.MR_PACKETS_DOWNSTREAM_LOST,
            "Downstream packets lost by access point (5-minute window)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_packet_loss_downstream_percent = self.parent._create_gauge(
            MetricName.MR_PACKET_LOSS_DOWNSTREAM_PERCENT,
            "Downstream packet loss percentage for access point (5-minute window)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_packets_upstream_total = self.parent._create_gauge(
            MetricName.MR_PACKETS_UPSTREAM_TOTAL,
            "Total upstream packets received by access point (5-minute window)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_packets_upstream_lost = self.parent._create_gauge(
            MetricName.MR_PACKETS_UPSTREAM_LOST,
            "Upstream packets lost by access point (5-minute window)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_packet_loss_upstream_percent = self.parent._create_gauge(
            MetricName.MR_PACKET_LOSS_UPSTREAM_PERCENT,
            "Upstream packet loss percentage for access point (5-minute window)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        # Combined packet metrics (calculated)
        self._mr_packets_total = self.parent._create_gauge(
            MetricName.MR_PACKETS_TOTAL,
            "Total packets (upstream + downstream) for access point (5-minute window)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_packets_lost_total = self.parent._create_gauge(
            MetricName.MR_PACKETS_LOST_TOTAL,
            "Total packets lost (upstream + downstream) for access point (5-minute window)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_packet_loss_total_percent = self.parent._create_gauge(
            MetricName.MR_PACKET_LOSS_TOTAL_PERCENT,
            "Total packet loss percentage (upstream + downstream) for access point (5-minute window)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        # Network-wide MR packet loss metrics (5-minute window)
        self._mr_network_packets_downstream_total = self.parent._create_gauge(
            MetricName.MR_NETWORK_PACKETS_DOWNSTREAM_TOTAL,
            "Total downstream packets for all access points in network (5-minute window)",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_network_packets_downstream_lost = self.parent._create_gauge(
            MetricName.MR_NETWORK_PACKETS_DOWNSTREAM_LOST,
            "Downstream packets lost for all access points in network (5-minute window)",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_network_packet_loss_downstream_percent = self.parent._create_gauge(
            MetricName.MR_NETWORK_PACKET_LOSS_DOWNSTREAM_PERCENT,
            "Downstream packet loss percentage for all access points in network (5-minute window)",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_network_packets_upstream_total = self.parent._create_gauge(
            MetricName.MR_NETWORK_PACKETS_UPSTREAM_TOTAL,
            "Total upstream packets for all access points in network (5-minute window)",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_network_packets_upstream_lost = self.parent._create_gauge(
            MetricName.MR_NETWORK_PACKETS_UPSTREAM_LOST,
            "Upstream packets lost for all access points in network (5-minute window)",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_network_packet_loss_upstream_percent = self.parent._create_gauge(
            MetricName.MR_NETWORK_PACKET_LOSS_UPSTREAM_PERCENT,
            "Upstream packet loss percentage for all access points in network (5-minute window)",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        # Combined network-wide packet metrics (calculated)
        self._mr_network_packets_total = self.parent._create_gauge(
            MetricName.MR_NETWORK_PACKETS_TOTAL,
            "Total packets (upstream + downstream) for all access points in network (5-minute window)",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_network_packets_lost_total = self.parent._create_gauge(
            MetricName.MR_NETWORK_PACKETS_LOST_TOTAL,
            "Total packets lost (upstream + downstream) for all access points in network (5-minute window)",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        self._mr_network_packet_loss_total_percent = self.parent._create_gauge(
            MetricName.MR_NETWORK_PACKET_LOSS_TOTAL_PERCENT,
            "Total packet loss percentage (upstream + downstream) for all access points in network (5-minute window)",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        # MR CPU metrics
        self._mr_cpu_load_5min = self.parent._create_gauge(
            MetricName.MR_CPU_LOAD_5MIN,
            "Access point CPU load average over 5 minutes (normalized to 0-100 per core)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.MODEL, LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        # MR SSID/Radio status metrics
        self._mr_radio_broadcasting = self.parent._create_gauge(
            MetricName.MR_RADIO_BROADCASTING,
            "Access point radio broadcasting status (1 = broadcasting, 0 = not broadcasting)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME, LabelName.BAND, LabelName.RADIO_INDEX],
        )

        self._mr_radio_channel = self.parent._create_gauge(
            MetricName.MR_RADIO_CHANNEL,
            "Access point radio channel number",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME, LabelName.BAND, LabelName.RADIO_INDEX],
        )

        self._mr_radio_channel_width = self.parent._create_gauge(
            MetricName.MR_RADIO_CHANNEL_WIDTH_MHZ,
            "Access point radio channel width in MHz",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME, LabelName.BAND, LabelName.RADIO_INDEX],
        )

        self._mr_radio_power = self.parent._create_gauge(
            MetricName.MR_RADIO_POWER_DBM,
            "Access point radio transmit power in dBm",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID, LabelName.NETWORK_NAME, LabelName.BAND, LabelName.RADIO_INDEX],
        )

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
        serial = device["serial"]
        name = device.get("name", serial)
        model = device.get("model", "Unknown")
        network_id = device.get("networkId", "")

        try:
            # Get wireless status with timeout
            logger.debug(
                "Fetching wireless status",
                serial=serial,
                name=name,
            )
            self._track_api_call("getDeviceWirelessStatus")

            status = await asyncio.to_thread(
                self.api.wireless.getDeviceWirelessStatus,
                serial,
            )
            status = validate_response_format(
                status,
                expected_type=dict,
                operation="getDeviceWirelessStatus"
            )

            logger.debug(
                "Successfully fetched wireless status",
                serial=serial,
            )

            # Client count
            if "clientCount" in status:
                self._ap_clients.labels(
                    serial=serial,
                    name=name,
                    model=model,
                    network_id=network_id,
                ).set(status["clientCount"])

            # Get connection stats (30 minute window)
            await self._collect_connection_stats(serial, name, model, network_id)

        except Exception:
            logger.exception(
                "Failed to collect wireless metrics",
                serial=serial,
            )

    @with_error_handling(
        operation="Collect MR connection stats",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_connection_stats(
        self, serial: str, name: str, model: str, network_id: str
    ) -> None:
        """Collect wireless connection statistics for the device.

        Parameters
        ----------
        serial : str
            Device serial number.
        name : str
            Device name.
        model : str
            Device model.
        network_id : str
            Network ID.

        """
        try:
            logger.debug(
                "Fetching connection stats",
                serial=serial,
                name=name,
            )

            # Track API call
            self._track_api_call("getDeviceWirelessConnectionStats")

            # Use 30 minute (1800 second) timespan as minimum
            connection_stats = await asyncio.to_thread(
                self.api.wireless.getDeviceWirelessConnectionStats,
                serial,
                timespan=1800,  # 30 minutes
            )

            # Handle empty response (no data in timespan)
            if not connection_stats or "connectionStats" not in connection_stats:
                logger.debug(
                    "No connection stats data available",
                    serial=serial,
                    timespan="30m",
                )
                # Set all stats to 0 when no data
                for stat_type in ("assoc", "auth", "dhcp", "dns", "success"):
                    self._ap_connection_stats.labels(
                        serial=serial,
                        name=name,
                        model=model,
                        network_id=network_id,
                        stat_type=stat_type,
                    ).set(0)
                return

            stats = connection_stats.get("connectionStats", {})

            # Set metrics for each connection stat type
            for stat_type, value in stats.items():
                if stat_type in {"assoc", "auth", "dhcp", "dns", "success"}:
                    self._ap_connection_stats.labels(
                        serial=serial,
                        name=name,
                        model=model,
                        network_id=network_id,
                        stat_type=stat_type,
                    ).set(value)

            logger.debug(
                "Successfully collected connection stats",
                serial=serial,
                stats=stats,
            )

        except Exception:
            logger.exception(
                "Failed to collect connection stats",
                serial=serial,
            )

    @with_error_handling(
        operation="Collect MR wireless clients",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_wireless_clients(self, org_id: str, device_lookup: dict[str, dict[str, Any]]) -> None:
        """Collect wireless client counts for MR devices.

        Parameters
        ----------
        org_id : str
            Organization ID.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table for device info.

        """
        try:
            logger.debug("Fetching wireless client counts", org_id=org_id)
            self._track_api_call("getOrganizationWirelessClientsOverviewByDevice")

            client_overview = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessClientsOverviewByDevice,
                org_id,
                total_pages="all",
            )
            client_overview = validate_response_format(
                client_overview,
                expected_type=list,
                operation="getOrganizationWirelessClientsOverviewByDevice"
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

            logger.debug(
                "Successfully fetched wireless client counts",
                org_id=org_id,
                device_count=len(client_data) if client_data else 0,
            )

            # Process each device's client data
            for device_data in client_data:
                serial = device_data.get("serial", "")
                network_id = device_data.get("network", {}).get("id", "")

                # Get online client count
                counts = device_data.get("counts", {})
                by_status = counts.get("byStatus", {})
                online_clients = by_status.get("online", 0)

                # Look up device info from our cache
                device_info = device_lookup.get(serial, {})
                device_name = device_info.get("name", serial)
                device_model = device_info.get("model", "MR")

                self._ap_clients.labels(
                    serial=serial,
                    name=device_name,
                    model=device_model,
                    network_id=network_id,
                ).set(online_clients)

        except Exception:
            logger.exception(
                "Failed to collect wireless client counts",
                org_id=org_id,
            )

    @with_error_handling(
        operation="Collect MR ethernet status",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_ethernet_status(self, org_id: str, device_lookup: dict[str, dict[str, Any]]) -> None:
        """Collect ethernet status for MR devices.

        Parameters
        ----------
        org_id : str
            Organization ID.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table for device info.

        """
        try:
            logger.debug("Fetching MR ethernet status", org_id=org_id)
            self._track_api_call("getOrganizationWirelessDevicesEthernetStatuses")

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
                device_info = device_lookup.get(serial, {})
                device_name = device_info.get("name", serial)
                network_id = device_info.get("networkId", "")

                # Power mode information
                power_mode = device_status.get("power", {}).get("mode")
                if power_mode:
                    if hasattr(self.parent, "_set_metric_value"):
                        self.parent._set_metric_value(
                            "_mr_power_info",
                            {
                                "serial": serial,
                                "name": device_name,
                                "network_id": network_id,
                                "mode": power_mode,
                            },
                            1,
                        )

                # AC power status
                ac_info = device_status.get("power", {}).get("ac", {})
                ac_connected = ac_info.get("isConnected", False)
                if hasattr(self.parent, "_set_metric_value"):
                    self.parent._set_metric_value(
                        "_mr_power_ac_connected",
                        {
                            "serial": serial,
                            "name": device_name,
                            "network_id": network_id,
                        },
                        1 if ac_connected else 0,
                    )

                # PoE power status
                poe_info = device_status.get("power", {}).get("poe", {})
                poe_connected = poe_info.get("isConnected", False)
                if hasattr(self.parent, "_set_metric_value"):
                    self.parent._set_metric_value(
                        "_mr_power_poe_connected",
                        {
                            "serial": serial,
                            "name": device_name,
                            "network_id": network_id,
                        },
                        1 if poe_connected else 0,
                    )

                # Process port information
                ports = device_status.get("ports", [])
                aggregation_enabled = False
                total_speed = 0

                for port in ports:
                    port_name = port.get("name", "")

                    # PoE information
                    poe_standard = port.get("poe", {}).get("standard")
                    if poe_standard and hasattr(self.parent, "_set_metric_value"):
                        self.parent._set_metric_value(
                            "_mr_port_poe_info",
                            {
                                "serial": serial,
                                "name": device_name,
                                "network_id": network_id,
                                "port_name": port_name,
                                "standard": poe_standard,
                            },
                            1,
                        )

                    # Link negotiation information
                    link_negotiation = port.get("linkNegotiation", {})
                    duplex = link_negotiation.get("duplex")
                    speed = link_negotiation.get("speed")

                    if duplex and hasattr(self.parent, "_set_metric_value"):
                        self.parent._set_metric_value(
                            "_mr_port_link_negotiation_info",
                            {
                                "serial": serial,
                                "name": device_name,
                                "network_id": network_id,
                                "port_name": port_name,
                                "duplex": duplex,
                            },
                            1,
                        )

                    # Set speed metric
                    if hasattr(self.parent, "_set_metric_value"):
                        self.parent._set_metric_value(
                            "_mr_port_link_negotiation_speed",
                            {
                                "serial": serial,
                                "name": device_name,
                                "network_id": network_id,
                                "port_name": port_name,
                            },
                            speed if speed is not None else 0,
                        )

                    # Check for aggregation
                    if port.get("isAggregated", False):
                        aggregation_enabled = True
                        if speed is not None:
                            total_speed += speed

                if hasattr(self.parent, "_set_metric_value"):
                    self.parent._set_metric_value(
                        "_mr_aggregation_enabled",
                        {
                            "serial": serial,
                            "name": device_name,
                            "network_id": network_id,
                        },
                        1 if aggregation_enabled else 0,
                    )

                    self.parent._set_metric_value(
                        "_mr_aggregation_speed",
                        {
                            "serial": serial,
                            "name": device_name,
                            "network_id": network_id,
                        },
                        total_speed,
                    )

        except Exception:
            logger.exception(
                "Failed to collect MR ethernet status",
                org_id=org_id,
            )

    async def collect_packet_loss(self, org_id: str, device_lookup: dict[str, dict[str, Any]]) -> None:
        """Collect packet loss metrics for MR devices and networks.

        Parameters
        ----------
        org_id : str
            Organization ID.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table for device info.

        """
        try:
            logger.debug("Fetching MR packet loss metrics", org_id=org_id)
            self._track_api_call("getOrganizationWirelessDevicesPacketLossByDevice")

            # Use 5-minute timespan (300 seconds)
            packet_loss_data = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessDevicesPacketLossByDevice,
                org_id,
                timespan=300,  # 5 minutes
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

            logger.debug(
                "Successfully fetched MR packet loss metrics",
                org_id=org_id,
                device_count=len(devices_data) if devices_data else 0,
            )

            # Process each device's packet loss data
            for device_data in devices_data:
                serial = device_data.get("serial", "")
                device_info = device_lookup.get(serial, {})
                device_name = device_info.get("name", serial)
                network_id = device_data.get("network", {}).get("id", "")
                network_name = device_data.get("network", {}).get("name", "")

                # Get packet loss data
                packet_loss = device_data.get("packetLoss", {})

                # Downstream metrics
                downstream = packet_loss.get("downstream", {})
                downstream_total = downstream.get("total", 0)
                downstream_lost = downstream.get("lost", 0)
                downstream_percent = downstream.get("lossPercentage", 0)

                self._set_packet_metric_value(
                    "_mr_packets_downstream_total",
                    {
                        "serial": serial,
                        "name": device_name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    downstream_total,
                )

                self._set_packet_metric_value(
                    "_mr_packets_downstream_lost",
                    {
                        "serial": serial,
                        "name": device_name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    downstream_lost,
                )

                self._set_packet_metric_value(
                    "_mr_packet_loss_downstream_percent",
                    {
                        "serial": serial,
                        "name": device_name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    downstream_percent,
                )

                # Upstream metrics
                upstream = packet_loss.get("upstream", {})
                upstream_total = upstream.get("total", 0)
                upstream_lost = upstream.get("lost", 0)
                upstream_percent = upstream.get("lossPercentage", 0)

                self._set_packet_metric_value(
                    "_mr_packets_upstream_total",
                    {
                        "serial": serial,
                        "name": device_name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upstream_total,
                )

                self._set_packet_metric_value(
                    "_mr_packets_upstream_lost",
                    {
                        "serial": serial,
                        "name": device_name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upstream_lost,
                )

                self._set_packet_metric_value(
                    "_mr_packet_loss_upstream_percent",
                    {
                        "serial": serial,
                        "name": device_name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upstream_percent,
                )

                # Combined metrics
                total_packets = downstream_total + upstream_total
                total_lost = downstream_lost + upstream_lost
                total_percent = (total_lost / total_packets * 100) if total_packets > 0 else 0

                self._set_packet_metric_value(
                    "_mr_packets_total",
                    {
                        "serial": serial,
                        "name": device_name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_packets,
                )

                self._set_packet_metric_value(
                    "_mr_packets_lost_total",
                    {
                        "serial": serial,
                        "name": device_name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_lost,
                )

                self._set_packet_metric_value(
                    "_mr_packet_loss_total_percent",
                    {
                        "serial": serial,
                        "name": device_name,
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_percent,
                )

            # Now collect network-wide packet loss metrics
            logger.debug("Fetching network-wide packet loss metrics", org_id=org_id)
            self._track_api_call("getOrganizationWirelessDevicesPacketLossByNetwork")

            network_packet_loss = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessDevicesPacketLossByNetwork,
                org_id,
                timespan=300,  # 5 minutes
                perPage=1000,
                total_pages="all",
            )

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
                network_id = network_data.get("network", {}).get("id", "")
                network_name = network_data.get("network", {}).get("name", "")

                # Get packet loss data
                packet_loss = network_data.get("packetLoss", {})

                # Downstream metrics
                downstream = packet_loss.get("downstream", {})
                downstream_total = downstream.get("total", 0)
                downstream_lost = downstream.get("lost", 0)
                downstream_percent = downstream.get("lossPercentage", 0)

                self._set_packet_metric_value(
                    "_mr_network_packets_downstream_total",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    downstream_total,
                )

                self._set_packet_metric_value(
                    "_mr_network_packets_downstream_lost",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    downstream_lost,
                )

                self._set_packet_metric_value(
                    "_mr_network_packet_loss_downstream_percent",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    downstream_percent,
                )

                # Upstream metrics
                upstream = packet_loss.get("upstream", {})
                upstream_total = upstream.get("total", 0)
                upstream_lost = upstream.get("lost", 0)
                upstream_percent = upstream.get("lossPercentage", 0)

                self._set_packet_metric_value(
                    "_mr_network_packets_upstream_total",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upstream_total,
                )

                self._set_packet_metric_value(
                    "_mr_network_packets_upstream_lost",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upstream_lost,
                )

                self._set_packet_metric_value(
                    "_mr_network_packet_loss_upstream_percent",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    upstream_percent,
                )

                # Combined metrics
                total_packets = downstream_total + upstream_total
                total_lost = downstream_lost + upstream_lost
                total_percent = (total_lost / total_packets * 100) if total_packets > 0 else 0

                self._set_packet_metric_value(
                    "_mr_network_packets_total",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_packets,
                )

                self._set_packet_metric_value(
                    "_mr_network_packets_lost_total",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_lost,
                )

                self._set_packet_metric_value(
                    "_mr_network_packet_loss_total_percent",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    total_percent,
                )

        except Exception:
            logger.exception(
                "Failed to collect MR packet loss metrics",
                org_id=org_id,
            )

    async def collect_cpu_load(self, org_id: str, devices: list[dict[str, Any]]) -> None:
        """Collect CPU load metrics for MR devices.

        Parameters
        ----------
        org_id : str
            Organization ID.
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
                serials = [d["serial"] for d in batch]

                try:
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
                    if isinstance(cpu_history, dict) and "items" in cpu_history:
                        cpu_data = cpu_history["items"]
                    elif isinstance(cpu_history, list):
                        cpu_data = cpu_history
                    else:
                        logger.warning(
                            "Unexpected CPU history format",
                            org_id=org_id,
                            batch_index=i // batch_size,
                            response_type=type(cpu_history).__name__,
                        )
                        continue

                    logger.debug(
                        "Successfully fetched CPU history",
                        org_id=org_id,
                        batch_index=i // batch_size,
                        device_count=len(cpu_data) if cpu_data else 0,
                    )

                    # Process CPU data for each device
                    for device_cpu in cpu_data:
                        serial = device_cpu.get("serial", "")
                        device_info = next((d for d in batch if d["serial"] == serial), {})
                        device_name = device_info.get("name", serial)
                        device_model = device_info.get("model", "MR")
                        network_id = device_info.get("networkId", "")

                        # Get the network name
                        networks = device_cpu.get("network", {})
                        network_name = networks.get("name", "")

                        # Get the most recent CPU load data
                        usage_history = device_cpu.get("usageHistory", [])
                        if usage_history:
                            # Sort by timestamp to get most recent
                            usage_history.sort(key=lambda x: x.get("ts", ""), reverse=True)
                            latest_usage = usage_history[0]

                            # Get 5-minute load average
                            # The API returns it as a percentage (0-100 per core)
                            avg_5min = latest_usage.get("avg5Minutes")
                            if avg_5min is not None:
                                if hasattr(self.parent, "_set_metric_value"):
                                    self.parent._set_metric_value(
                                        "_mr_cpu_load_5min",
                                        {
                                            "serial": serial,
                                            "name": device_name,
                                            "model": device_model,
                                            "network_id": network_id,
                                            "network_name": network_name,
                                        },
                                        avg_5min,
                                    )
                                    logger.debug(
                                        "Set CPU load metric",
                                        serial=serial,
                                        name=device_name,
                                        cpu_5min=avg_5min,
                                    )

                except Exception:
                    logger.exception(
                        "Failed to collect CPU load for batch",
                        org_id=org_id,
                        batch_index=i // batch_size,
                        batch_size=len(batch),
                    )

        except Exception:
            logger.exception(
                "Failed to collect MR CPU load metrics",
                org_id=org_id,
            )

    async def collect_ssid_status(self, org_id: str) -> None:
        """Collect SSID and radio status for MR devices.

        Parameters
        ----------
        org_id : str
            Organization ID.

        """
        try:
            logger.debug("Fetching MR SSID status", org_id=org_id)
            self._track_api_call("getOrganizationWirelessSsidsStatusesByDevice")

            ssid_statuses = await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessSsidsStatusesByDevice,
                org_id,
                perPage=1000,
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

            logger.debug(
                "Successfully fetched MR SSID status",
                org_id=org_id,
                device_count=len(devices_data) if devices_data else 0,
            )

            # Process each device's SSID and radio status
            for device_data in devices_data:
                serial = device_data.get("serial", "")
                name = device_data.get("name", serial)
                network = device_data.get("network", {})
                network_id = network.get("id", "")
                network_name = network.get("name", "")

                # Process radio status
                basic_service_sets = device_data.get("basicServiceSets", [])
                
                # Group radios by band and index
                radio_info = {}
                for bss in basic_service_sets:
                    radio = bss.get("radio", {})
                    band = radio.get("band", "")
                    index = radio.get("index", 0)
                    
                    if band and index is not None:
                        key = (band, index)
                        if key not in radio_info:
                            radio_info[key] = radio

                # Set metrics for each radio
                for (band, index), radio in radio_info.items():
                    # Broadcasting status
                    is_broadcasting = radio.get("isBroadcasting", False)
                    if hasattr(self.parent, "_set_metric_value"):
                        self.parent._set_metric_value(
                            "_mr_radio_broadcasting",
                            {
                                "serial": serial,
                                "name": name,
                                "network_id": network_id,
                                "network_name": network_name,
                                "band": band,
                                "radio_index": str(index),
                            },
                            1 if is_broadcasting else 0,
                        )

                    # Channel
                    channel = radio.get("channel")
                    if channel is not None and hasattr(self.parent, "_set_metric_value"):
                        self.parent._set_metric_value(
                            "_mr_radio_channel",
                            {
                                "serial": serial,
                                "name": name,
                                "network_id": network_id,
                                "network_name": network_name,
                                "band": band,
                                "radio_index": str(index),
                            },
                            channel,
                        )

                    # Channel width
                    channel_width = radio.get("channelWidth")
                    if channel_width is not None and hasattr(self.parent, "_set_metric_value"):
                        self.parent._set_metric_value(
                            "_mr_radio_channel_width",
                            {
                                "serial": serial,
                                "name": name,
                                "network_id": network_id,
                                "network_name": network_name,
                                "band": band,
                                "radio_index": str(index),
                            },
                            channel_width,
                        )

                    # Transmit power
                    power = radio.get("power")
                    if power is not None and hasattr(self.parent, "_set_metric_value"):
                        self.parent._set_metric_value(
                            "_mr_radio_power",
                            {
                                "serial": serial,
                                "name": name,
                                "network_id": network_id,
                                "network_name": network_name,
                                "band": band,
                                "radio_index": str(index),
                            },
                            power,
                        )

                    logger.debug(
                        "Set radio metrics",
                        serial=serial,
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

    def _set_packet_metric_value(
        self, metric_name: str, labels: dict[str, str], value: float | None
    ) -> None:
        """Set packet metric value with retention logic for total packet counters.

        For packet loss metrics, 0 is a valid value. For total packet counters,
        we retain the last known value if the API returns None or 0.

        Parameters
        ----------
        metric_name : str
            Name of the metric attribute.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float | None
            Value to set. May be None if API returned null.

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

        # Use parent's _set_metric_value if available
        if hasattr(self.parent, "_set_metric_value"):
            self.parent._set_metric_value(metric_name, labels, value)
        else:
            # Direct metric setting as fallback
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
