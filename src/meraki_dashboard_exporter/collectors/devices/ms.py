"""Meraki MS (Switch) metrics collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants import MSMetricName
from ...core.error_handling import validate_response_format, with_error_handling
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.metrics import LabelName
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class MSCollector(BaseDeviceCollector):
    """Collector for Meraki MS (Switch) devices."""

    def _initialize_metrics(self) -> None:
        """Initialize MS-specific metrics."""
        # Switch port metrics
        self._switch_port_status = self.parent._create_gauge(
            MSMetricName.MS_PORT_STATUS,
            "Switch port status (1 = connected, 0 = disconnected)",
            labelnames=[
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.PORT_ID,
                LabelName.PORT_NAME,
                LabelName.LINK_SPEED,
                LabelName.DUPLEX,
            ],
        )

        self._switch_port_traffic = self.parent._create_gauge(
            MSMetricName.MS_PORT_TRAFFIC_BYTES,
            "Switch port traffic rate in bytes per second (averaged over 1 hour)",
            labelnames=[
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.PORT_ID,
                LabelName.PORT_NAME,
                LabelName.DIRECTION,
            ],
        )

        self._switch_port_usage = self.parent._create_gauge(
            MSMetricName.MS_PORT_USAGE_BYTES,
            "Switch port data usage in bytes over the last 1 hour",
            labelnames=[
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.PORT_ID,
                LabelName.PORT_NAME,
                LabelName.DIRECTION,
            ],
        )

        self._switch_port_client_count = self.parent._create_gauge(
            MSMetricName.MS_PORT_CLIENT_COUNT,
            "Number of clients connected to switch port",
            labelnames=[
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.PORT_ID,
                LabelName.PORT_NAME,
            ],
        )

        # Switch power metrics
        self._switch_power = self.parent._create_gauge(
            MSMetricName.MS_POWER_USAGE_WATTS,
            "Switch power usage in watts",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.MODEL],
        )

        # POE metrics
        self._switch_poe_port_power = self.parent._create_gauge(
            MSMetricName.MS_POE_PORT_POWER_WATTS,
            "Per-port POE power consumption in watt-hours (Wh) over the last 1 hour",
            labelnames=[
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.PORT_ID,
                LabelName.PORT_NAME,
            ],
        )

        self._switch_poe_total_power = self.parent._create_gauge(
            MSMetricName.MS_POE_TOTAL_POWER_WATTS,
            "Total POE power consumption for switch in watt-hours (Wh)",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.MODEL, LabelName.NETWORK_ID],
        )

        self._switch_poe_budget = self.parent._create_gauge(
            MSMetricName.MS_POE_BUDGET_WATTS,
            "Total POE power budget for switch in watts",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.MODEL, LabelName.NETWORK_ID],
        )

        self._switch_poe_network_total = self.parent._create_gauge(
            MSMetricName.MS_POE_NETWORK_TOTAL_WATTS,
            "Total POE power consumption for all switches in network in watt-hours (Wh)",
            labelnames=[LabelName.NETWORK_ID, LabelName.NETWORK_NAME],
        )

        # STP metrics
        self._switch_stp_priority = self.parent._create_gauge(
            MSMetricName.MS_STP_PRIORITY,
            "Switch STP (Spanning Tree Protocol) priority",
            labelnames=[LabelName.SERIAL, LabelName.NAME, LabelName.NETWORK_ID],
        )
        
        # Packet count metrics (5-minute window)
        packet_labels = [
            LabelName.SERIAL.value,
            LabelName.NAME.value,
            LabelName.NETWORK_ID.value,
            LabelName.NETWORK_NAME.value,
            LabelName.PORT_ID.value,
            LabelName.PORT_NAME.value,
            LabelName.DIRECTION.value,
        ]
        
        self._switch_port_packets_total = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_TOTAL,
            "Total packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )
        
        self._switch_port_packets_broadcast = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_BROADCAST,
            "Broadcast packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )
        
        self._switch_port_packets_multicast = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_MULTICAST,
            "Multicast packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )
        
        self._switch_port_packets_crcerrors = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_CRCERRORS,
            "CRC align error packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )
        
        self._switch_port_packets_fragments = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_FRAGMENTS,
            "Fragment packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )
        
        self._switch_port_packets_collisions = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_COLLISIONS,
            "Collision packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )
        
        self._switch_port_packets_topologychanges = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_TOPOLOGYCHANGES,
            "Topology change packets on switch port (5-minute window)",
            labelnames=packet_labels,
        )
        
        # Packet rate metrics (packets per second)
        self._switch_port_packets_rate_total = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_TOTAL,
            "Total packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )
        
        self._switch_port_packets_rate_broadcast = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_BROADCAST,
            "Broadcast packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )
        
        self._switch_port_packets_rate_multicast = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_MULTICAST,
            "Multicast packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )
        
        self._switch_port_packets_rate_crcerrors = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_CRCERRORS,
            "CRC align error packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )
        
        self._switch_port_packets_rate_fragments = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_FRAGMENTS,
            "Fragment packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )
        
        self._switch_port_packets_rate_collisions = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_COLLISIONS,
            "Collision packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )
        
        self._switch_port_packets_rate_topologychanges = self.parent._create_gauge(
            MSMetricName.MS_PORT_PACKETS_RATE_TOPOLOGYCHANGES,
            "Topology change packet rate on switch port (packets per second, 5-minute average)",
            labelnames=packet_labels,
        )

    @log_api_call("getDeviceSwitchPortsStatuses")
    @with_error_handling(
        operation="Collect MS device metrics",
        continue_on_error=True,
    )
    async def collect(self, device: dict[str, Any]) -> None:
        """Collect switch-specific metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Switch device data.

        """
        serial = device["serial"]
        name = device.get("name", serial)
        model = device.get("model", "")
        network_id = device.get("networkId", "")
        network_name = device.get("networkName", network_id)  # Get network name if available

        try:
            # Get port statuses with 1-hour timespan
            with LogContext(serial=serial, name=name):
                port_statuses = await asyncio.to_thread(
                    self.api.switch.getDeviceSwitchPortsStatuses,
                    serial,
                    timespan=3600,  # 1 hour timespan for better accuracy
                )
                port_statuses = validate_response_format(
                    port_statuses, expected_type=list, operation="getDeviceSwitchPortsStatuses"
                )

            for port in port_statuses:
                port_id = str(port.get("portId", ""))
                port_name = port.get("name", f"Port {port_id}")

                # Port status with speed and duplex
                is_connected = 1 if port.get("status") == "Connected" else 0
                speed = port.get("speed", "")  # e.g., "1 Gbps", "100 Mbps"
                duplex = port.get("duplex", "")  # e.g., "full", "half"
                
                self._switch_port_status.labels(
                    serial=serial,
                    name=name,
                    network_id=network_id,
                    network_name=network_name,
                    port_id=port_id,
                    port_name=port_name,
                    link_speed=speed,
                    duplex=duplex,
                ).set(is_connected)

                # Traffic counters (rate in bytes per second)
                if "trafficInKbps" in port:
                    traffic_counters = port["trafficInKbps"]

                    if "recv" in traffic_counters:
                        self._switch_port_traffic.labels(
                            serial=serial,
                            name=name,
                            network_id=network_id,
                            network_name=network_name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="rx",
                        ).set(traffic_counters["recv"] * 1000 / 8)  # Convert kbps to bytes/sec

                    if "sent" in traffic_counters:
                        self._switch_port_traffic.labels(
                            serial=serial,
                            name=name,
                            network_id=network_id,
                            network_name=network_name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="tx",
                        ).set(traffic_counters["sent"] * 1000 / 8)  # Convert kbps to bytes/sec

                # Usage counters (total bytes over timespan)
                if "usageInKb" in port:
                    usage_counters = port["usageInKb"]

                    if "recv" in usage_counters:
                        self._switch_port_usage.labels(
                            serial=serial,
                            name=name,
                            network_id=network_id,
                            network_name=network_name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="rx",
                        ).set(usage_counters["recv"] * 1024)  # Convert KB to bytes

                    if "sent" in usage_counters:
                        self._switch_port_usage.labels(
                            serial=serial,
                            name=name,
                            network_id=network_id,
                            network_name=network_name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="tx",
                        ).set(usage_counters["sent"] * 1024)  # Convert KB to bytes

                    if "total" in usage_counters:
                        self._switch_port_usage.labels(
                            serial=serial,
                            name=name,
                            network_id=network_id,
                            network_name=network_name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="total",
                        ).set(usage_counters["total"] * 1024)  # Convert KB to bytes

                # Client count
                client_count = port.get("clientCount", 0)
                self._switch_port_client_count.labels(
                    serial=serial,
                    name=name,
                    network_id=network_id,
                    network_name=network_name,
                    port_id=port_id,
                    port_name=port_name,
                ).set(client_count)

            # Extract POE data from port statuses (POE data is included in port status)
            total_poe_consumption = 0

            for port in port_statuses:
                port_id = str(port.get("portId", ""))
                port_name = port.get("name", f"Port {port_id}")

                # Check if port has POE data
                poe_info = port.get("poe", {})
                if poe_info.get("isAllocated", False):
                    # Port is drawing POE power
                    power_used = port.get("powerUsageInWh", 0)

                    self._switch_poe_port_power.labels(
                        serial=serial,
                        name=name,
                        network_id=network_id,
                        network_name=network_name,
                        port_id=port_id,
                        port_name=port_name,
                    ).set(power_used)

                    total_poe_consumption += power_used
                else:
                    # Port is not drawing POE power
                    self._switch_poe_port_power.labels(
                        serial=serial,
                        name=name,
                        network_id=network_id,
                        network_name=network_name,
                        port_id=port_id,
                        port_name=port_name,
                    ).set(0)

            # Set switch-level POE total
            self._switch_poe_total_power.labels(
                serial=serial,
                name=name,
                model=model,
                network_id=network_id,
            ).set(total_poe_consumption)

            # Set total switch power usage (POE consumption is the main power draw)
            # This is an approximation - actual switch base power consumption varies by model
            self._switch_power.labels(
                serial=serial,
                name=name,
                model=model,
            ).set(total_poe_consumption)

            # Note: POE budget is not available via API, would need a lookup table by model
            
            # Collect packet statistics
            await self._collect_packet_statistics(device)

        except Exception:
            logger.exception(
                "Failed to collect switch metrics",
                serial=serial,
            )

    @log_api_call("getOrganizationNetworks")
    @with_error_handling(
        operation="Collect STP priorities",
        continue_on_error=True,
    )
    async def collect_stp_priorities(
        self, org_id: str, device_lookup: dict[str, dict[str, Any]] | None = None
    ) -> None:
        """Collect STP priorities for all switches in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        device_lookup : dict[str, dict[str, Any]] | None
            Device lookup table. If not provided, uses parent's _device_lookup.

        """
        from ...core.domain_models import STPConfiguration

        try:
            # First, fetch all networks in the organization
            with LogContext(org_id=org_id):
                networks = await asyncio.to_thread(
                    self.api.organizations.getOrganizationNetworks,
                    org_id,
                    total_pages="all",
                )

            # Filter to only networks with switches
            switch_networks = [
                n for n in networks if "switch" in n.get("productTypes", [])
            ]

            logger.debug(
                "Found switch networks for STP collection",
                org_id=org_id,
                total_networks=len(networks),
                switch_networks=len(switch_networks),
            )

            # Use provided device lookup or parent's
            devices = device_lookup or getattr(self.parent, "_device_lookup", {})

            # Collect STP data for each network
            for network in switch_networks:
                network_id = network["id"]
                
                try:
                    # Fetch STP configuration for the network
                    with LogContext(network_id=network_id):
                        stp_data = await asyncio.to_thread(
                            self.api.switch.getNetworkSwitchStp,
                            network_id,
                        )

                    # Parse the STP configuration
                    stp_config = STPConfiguration.model_validate(stp_data)

                    # Set metrics for each switch in the network
                    switch_priorities = stp_config.switch_priorities
                    for switch_serial, priority in switch_priorities.items():
                        # Get switch details from device lookup
                        device_info = devices.get(switch_serial, {})
                        switch_name = device_info.get("name", switch_serial)

                        self._switch_stp_priority.labels(
                            serial=switch_serial,
                            name=switch_name,
                            network_id=network_id,
                        ).set(priority)

                        logger.debug(
                            "Set STP priority",
                            serial=switch_serial,
                            name=switch_name,
                            network_id=network_id,
                            priority=priority,
                        )

                except Exception:
                    logger.exception(
                        "Failed to collect STP data for network",
                        network_id=network_id,
                    )

        except Exception:
            logger.exception(
                "Failed to collect STP priorities",
                org_id=org_id,
            )
    
    @log_api_call("getDeviceSwitchPortsStatusesPackets")
    @with_error_handling(
        operation="Collect MS packet statistics",
        continue_on_error=True,
    )
    async def _collect_packet_statistics(self, device: dict[str, Any]) -> None:
        """Collect packet statistics for a switch.
        
        Parameters
        ----------
        device : dict[str, Any]
            Switch device data.
            
        """
        serial = device["serial"]
        name = device.get("name", serial)
        network_id = device.get("networkId", "")
        network_name = device.get("networkName", network_id)
        
        try:
            # Get packet statistics with 5-minute timespan
            with LogContext(serial=serial, name=name):
                packet_stats = await asyncio.to_thread(
                    self.api.switch.getDeviceSwitchPortsStatusesPackets,
                    serial,
                    timespan=300,  # 5-minute window
                )
                packet_stats = validate_response_format(
                    packet_stats, expected_type=list, operation="getDeviceSwitchPortsStatusesPackets"
                )
            
            # Mapping of API descriptions to metric types
            metric_map = {
                "Total": (self._switch_port_packets_total, self._switch_port_packets_rate_total),
                "Broadcast": (self._switch_port_packets_broadcast, self._switch_port_packets_rate_broadcast),
                "Multicast": (self._switch_port_packets_multicast, self._switch_port_packets_rate_multicast),
                "CRC align errors": (self._switch_port_packets_crcerrors, self._switch_port_packets_rate_crcerrors),
                "Fragments": (self._switch_port_packets_fragments, self._switch_port_packets_rate_fragments),
                "Collisions": (self._switch_port_packets_collisions, self._switch_port_packets_rate_collisions),
                "Topology changes": (self._switch_port_packets_topologychanges, self._switch_port_packets_rate_topologychanges),
            }
            
            for port_data in packet_stats:
                port_id = str(port_data.get("portId", ""))
                # Use the port name from the port status call if available
                port_name = f"Port {port_id}"
                
                packets = port_data.get("packets", [])
                
                for packet_type in packets:
                    desc = packet_type.get("desc", "")
                    
                    if desc in metric_map:
                        count_metric, rate_metric = metric_map[desc]
                        
                        # Total counts
                        total = packet_type.get("total", 0)
                        sent = packet_type.get("sent", 0)
                        recv = packet_type.get("recv", 0)
                        
                        # Set count metrics
                        count_metric.labels(
                            serial=serial,
                            name=name,
                            network_id=network_id,
                            network_name=network_name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="total",
                        ).set(total)
                        
                        count_metric.labels(
                            serial=serial,
                            name=name,
                            network_id=network_id,
                            network_name=network_name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="sent",
                        ).set(sent)
                        
                        count_metric.labels(
                            serial=serial,
                            name=name,
                            network_id=network_id,
                            network_name=network_name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="recv",
                        ).set(recv)
                        
                        # Rate per second
                        rate_data = packet_type.get("ratePerSec", {})
                        rate_total = rate_data.get("total", 0)
                        rate_sent = rate_data.get("sent", 0)
                        rate_recv = rate_data.get("recv", 0)
                        
                        # Set rate metrics
                        rate_metric.labels(
                            serial=serial,
                            name=name,
                            network_id=network_id,
                            network_name=network_name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="total",
                        ).set(rate_total)
                        
                        rate_metric.labels(
                            serial=serial,
                            name=name,
                            network_id=network_id,
                            network_name=network_name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="sent",
                        ).set(rate_sent)
                        
                        rate_metric.labels(
                            serial=serial,
                            name=name,
                            network_id=network_id,
                            network_name=network_name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="recv",
                        ).set(rate_recv)
            
            logger.debug(
                "Collected packet statistics",
                serial=serial,
                name=name,
                port_count=len(packet_stats),
            )
            
        except Exception:
            logger.exception(
                "Failed to collect packet statistics",
                serial=serial,
            )
