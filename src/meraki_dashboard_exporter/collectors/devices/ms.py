"""Meraki MS (Switch) metrics collector."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from ...core.constants import MSMetricName
from ...core.error_handling import validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels, create_port_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.metrics import LabelName
from ...core.otel_tracing import trace_method
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class MSCollector(BaseDeviceCollector):
    """Collector for Meraki MS (Switch) devices."""

    def __init__(self, parent: Any) -> None:
        """Initialize the MS collector.

        Parameters
        ----------
        parent : Any
            Parent collector providing shared metrics and helpers.

        """
        super().__init__(parent)
        self._last_port_usage: dict[str, float] = {}
        self._last_packet_stats: dict[str, float] = {}
        self._org_port_status_supported: bool | None = None

    def _initialize_metrics(self) -> None:
        """Initialize MS-specific metrics."""
        # Switch port metrics
        self._switch_port_status = self.parent._create_gauge(
            MSMetricName.MS_PORT_STATUS,
            "Switch port status (1 = connected, 0 = disconnected)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
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
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
                LabelName.PORT_NAME,
                LabelName.DIRECTION,
            ],
        )

        self._switch_port_usage = self.parent._create_gauge(
            MSMetricName.MS_PORT_USAGE_BYTES,
            "Switch port data usage in bytes over the last 1 hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
                LabelName.PORT_NAME,
                LabelName.DIRECTION,
            ],
        )

        self._switch_port_client_count = self.parent._create_gauge(
            MSMetricName.MS_PORT_CLIENT_COUNT,
            "Number of clients connected to switch port",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
                LabelName.PORT_NAME,
            ],
        )

        # Switch power metrics
        self._switch_power = self.parent._create_gauge(
            MSMetricName.MS_POWER_USAGE_WATTS,
            "Switch power usage in watts",
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

        # POE metrics
        self._switch_poe_port_power = self.parent._create_gauge(
            MSMetricName.MS_POE_PORT_POWER_WATTS,
            "Per-port POE power consumption in watt-hours (Wh) over the last 1 hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PORT_ID,
                LabelName.PORT_NAME,
            ],
        )

        self._switch_poe_total_power = self.parent._create_gauge(
            MSMetricName.MS_POE_TOTAL_POWER_WATTS,
            "Total POE power consumption for switch in watt-hours (Wh)",
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

        self._switch_poe_budget = self.parent._create_gauge(
            MSMetricName.MS_POE_BUDGET_WATTS,
            "Total POE power budget for switch in watts",
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

        self._switch_poe_network_total = self.parent._create_gauge(
            MSMetricName.MS_POE_NETWORK_TOTAL_WATTS,
            "Total POE power consumption for all switches in network in watt-hours (Wh)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        # STP metrics
        self._switch_stp_priority = self.parent._create_gauge(
            MSMetricName.MS_STP_PRIORITY,
            "Switch STP (Spanning Tree Protocol) priority",
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

        # Packet count metrics (5-minute window)
        packet_labels = [
            LabelName.ORG_ID.value,
            LabelName.ORG_NAME.value,
            LabelName.NETWORK_ID.value,
            LabelName.NETWORK_NAME.value,
            LabelName.SERIAL.value,
            LabelName.NAME.value,
            LabelName.MODEL.value,
            LabelName.DEVICE_TYPE.value,
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

    def _should_collect_port_usage(self, serial: str) -> bool:
        interval = self.settings.api.ms_port_usage_interval
        if interval <= 0:
            return True
        last = self._last_port_usage.get(serial, 0.0)
        return (time.time() - last) >= interval

    def _mark_port_usage_collected(self, serial: str) -> None:
        self._last_port_usage[serial] = time.time()

    def _should_collect_packet_stats(self, serial: str) -> bool:
        interval = self.settings.api.ms_packet_stats_interval
        if interval <= 0:
            return True
        last = self._last_packet_stats.get(serial, 0.0)
        return (time.time() - last) >= interval

    def _mark_packet_stats_collected(self, serial: str) -> None:
        self._last_packet_stats[serial] = time.time()

    @log_api_call("getOrganizationSwitchPortsStatusesBySwitch")
    @with_error_handling(
        operation="Collect MS switch port statuses (org)",
        continue_on_error=True,
    )
    async def collect_port_statuses_by_switch(
        self,
        org_id: str,
        org_name: str,
        devices: list[dict[str, Any]],
    ) -> bool:
        """Collect port status metrics using the org-level switch endpoint."""
        if self._org_port_status_supported is None:
            self._org_port_status_supported = hasattr(
                self.api.switch,
                "getOrganizationSwitchPortsStatusesBySwitch",
            )
            if not self._org_port_status_supported:
                logger.warning(
                    "Org-level switch port status endpoint not available in SDK; "
                    "falling back to per-device collection",
                    org_id=org_id,
                )

        if not self._org_port_status_supported:
            return False

        device_lookup = {device.get("serial"): device for device in devices}
        serials = [device.get("serial") for device in devices if device.get("serial")]
        if not serials:
            return True

        with LogContext(org_id=org_id):
            response = await asyncio.to_thread(
                self.api.switch.getOrganizationSwitchPortsStatusesBySwitch,
                org_id,
                serials=serials,
                perPage=20,
                total_pages="all",
            )
            switches = validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationSwitchPortsStatusesBySwitch",
            )

        for switch in switches:
            serial = switch.get("serial")
            if not serial:
                continue

            device_info = device_lookup.get(serial, {})
            network = switch.get("network", {}) or {}
            network_id = network.get("id", device_info.get("networkId", ""))
            network_name = network.get("name", device_info.get("networkName", network_id))

            device_data = {
                "serial": serial,
                "name": switch.get("name", device_info.get("name", serial)),
                "model": switch.get("model", device_info.get("model", "")),
                "networkId": network_id,
                "networkName": network_name,
                "orgId": org_id,
                "orgName": org_name,
            }

            for port in switch.get("ports", []) or []:
                speed = port.get("speed", "")
                duplex = port.get("duplex", "")
                port_labels = create_port_labels(
                    device_data,
                    port,
                    org_id=org_id,
                    org_name=org_name,
                    link_speed=speed,
                    duplex=duplex,
                )

                is_connected = 1 if port.get("status") == "Connected" else 0
                self._switch_port_status.labels(**port_labels).set(is_connected)

        return True

    @trace_method("process.device")
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
        # Extract org info from device data
        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)

        # Create standard device labels
        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)
        try:
            # Get port statuses with 1-hour timespan
            with LogContext(serial=device_labels["serial"], name=device_labels["name"]):
                port_statuses = await asyncio.to_thread(
                    self.api.switch.getDeviceSwitchPortsStatuses,
                    device_labels["serial"],
                    timespan=3600,  # 1 hour timespan for better accuracy
                )
                port_statuses = validate_response_format(
                    port_statuses, expected_type=list, operation="getDeviceSwitchPortsStatuses"
                )

            for port in port_statuses:
                # Create port labels with additional attributes
                speed = port.get("speed", "")  # e.g., "1 Gbps", "100 Mbps"
                duplex = port.get("duplex", "")  # e.g., "full", "half"
                port_labels = create_port_labels(
                    device, port, org_id=org_id, org_name=org_name, link_speed=speed, duplex=duplex
                )

                # Port status with speed and duplex
                is_connected = 1 if port.get("status") == "Connected" else 0
                self._switch_port_status.labels(**port_labels).set(is_connected)

                # Traffic counters (rate in bytes per second)
                if "trafficInKbps" in port:
                    traffic_counters = port["trafficInKbps"]

                    if "recv" in traffic_counters:
                        rx_labels = create_port_labels(
                            device, port, org_id=org_id, org_name=org_name, direction="rx"
                        )
                        self._switch_port_traffic.labels(**rx_labels).set(
                            traffic_counters["recv"] * 1000 / 8  # Convert kbps to bytes/sec
                        )

                    if "sent" in traffic_counters:
                        tx_labels = create_port_labels(
                            device, port, org_id=org_id, org_name=org_name, direction="tx"
                        )
                        self._switch_port_traffic.labels(**tx_labels).set(
                            traffic_counters["sent"] * 1000 / 8  # Convert kbps to bytes/sec
                        )

                # Usage counters (total bytes over timespan)
                if "usageInKb" in port:
                    usage_counters = port["usageInKb"]

                    if "recv" in usage_counters:
                        rx_labels = create_port_labels(
                            device, port, org_id=org_id, org_name=org_name, direction="rx"
                        )
                        self._switch_port_usage.labels(**rx_labels).set(
                            usage_counters["recv"] * 1024  # Convert KB to bytes
                        )

                    if "sent" in usage_counters:
                        tx_labels = create_port_labels(
                            device, port, org_id=org_id, org_name=org_name, direction="tx"
                        )
                        self._switch_port_usage.labels(**tx_labels).set(
                            usage_counters["sent"] * 1024  # Convert KB to bytes
                        )

                    if "total" in usage_counters:
                        total_labels = create_port_labels(
                            device, port, org_id=org_id, org_name=org_name, direction="total"
                        )
                        self._switch_port_usage.labels(**total_labels).set(
                            usage_counters["total"] * 1024  # Convert KB to bytes
                        )

                # Client count
                client_count = port.get("clientCount", 0)
                # Use base port labels without direction for client count
                port_labels_no_extra = create_port_labels(
                    device, port, org_id=org_id, org_name=org_name
                )
                self._switch_port_client_count.labels(**port_labels_no_extra).set(client_count)

            # Extract POE data from port statuses (POE data is included in port status)
            total_poe_consumption = 0

            for port in port_statuses:
                # Create port labels for POE metrics
                port_labels = create_port_labels(device, port, org_id=org_id, org_name=org_name)

                # Check if port has POE data
                poe_info = port.get("poe", {})
                if poe_info.get("isAllocated", False):
                    # Port is drawing POE power
                    power_used = port.get("powerUsageInWh", 0)
                    self._switch_poe_port_power.labels(**port_labels).set(power_used)
                    total_poe_consumption += power_used
                else:
                    # Port is not drawing POE power
                    self._switch_poe_port_power.labels(**port_labels).set(0)

            # Set switch-level POE total
            self._switch_poe_total_power.labels(**device_labels).set(total_poe_consumption)

            # Set total switch power usage (POE consumption is the main power draw)
            # This is an approximation - actual switch base power consumption varies by model
            self._switch_power.labels(**device_labels).set(total_poe_consumption)

            # Note: POE budget is not available via API, would need a lookup table by model

            # Collect packet statistics
            await self._collect_packet_statistics(device)
            self._mark_port_usage_collected(device_labels["serial"])

        except Exception:
            logger.exception(
                "Failed to collect switch metrics",
                serial=device_labels["serial"],
            )

    @log_api_call("getDeviceSwitchPortsStatuses")
    @with_error_handling(
        operation="Collect MS port usage metrics",
        continue_on_error=True,
    )
    async def collect_device_port_usage_metrics(self, device: dict[str, Any]) -> None:
        """Collect per-port usage and POE metrics for a switch."""
        serial = device.get("serial")
        if not serial:
            return

        if not self._should_collect_port_usage(serial):
            logger.debug(
                "Skipping switch port usage collection",
                serial=serial,
                interval_seconds=self.settings.api.ms_port_usage_interval,
            )
            return

        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)
        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)

        with LogContext(serial=device_labels["serial"], name=device_labels["name"]):
            port_statuses = await asyncio.to_thread(
                self.api.switch.getDeviceSwitchPortsStatuses,
                device_labels["serial"],
                timespan=3600,
            )
            port_statuses = validate_response_format(
                port_statuses, expected_type=list, operation="getDeviceSwitchPortsStatuses"
            )

        for port in port_statuses:
            # Traffic counters (rate in bytes per second)
            if "trafficInKbps" in port:
                traffic_counters = port["trafficInKbps"]

                if "recv" in traffic_counters:
                    rx_labels = create_port_labels(
                        device, port, org_id=org_id, org_name=org_name, direction="rx"
                    )
                    self._switch_port_traffic.labels(**rx_labels).set(
                        traffic_counters["recv"] * 1000 / 8
                    )

                if "sent" in traffic_counters:
                    tx_labels = create_port_labels(
                        device, port, org_id=org_id, org_name=org_name, direction="tx"
                    )
                    self._switch_port_traffic.labels(**tx_labels).set(
                        traffic_counters["sent"] * 1000 / 8
                    )

            # Usage counters (total bytes over timespan)
            if "usageInKb" in port:
                usage_counters = port["usageInKb"]

                if "recv" in usage_counters:
                    rx_labels = create_port_labels(
                        device, port, org_id=org_id, org_name=org_name, direction="rx"
                    )
                    self._switch_port_usage.labels(**rx_labels).set(usage_counters["recv"] * 1024)

                if "sent" in usage_counters:
                    tx_labels = create_port_labels(
                        device, port, org_id=org_id, org_name=org_name, direction="tx"
                    )
                    self._switch_port_usage.labels(**tx_labels).set(usage_counters["sent"] * 1024)

                if "total" in usage_counters:
                    total_labels = create_port_labels(
                        device, port, org_id=org_id, org_name=org_name, direction="total"
                    )
                    self._switch_port_usage.labels(**total_labels).set(
                        usage_counters["total"] * 1024
                    )

            # Client count
            client_count = port.get("clientCount", 0)
            port_labels_no_extra = create_port_labels(
                device, port, org_id=org_id, org_name=org_name
            )
            self._switch_port_client_count.labels(**port_labels_no_extra).set(client_count)

        # Extract POE data from port statuses (POE data is included in port status)
        total_poe_consumption = 0

        for port in port_statuses:
            port_labels = create_port_labels(device, port, org_id=org_id, org_name=org_name)
            poe_info = port.get("poe", {})
            if poe_info.get("isAllocated", False):
                power_used = port.get("powerUsageInWh", 0)
                self._switch_poe_port_power.labels(**port_labels).set(power_used)
                total_poe_consumption += power_used
            else:
                self._switch_poe_port_power.labels(**port_labels).set(0)

        self._switch_poe_total_power.labels(**device_labels).set(total_poe_consumption)
        self._switch_power.labels(**device_labels).set(total_poe_consumption)
        self._mark_port_usage_collected(serial)

    @log_api_call("getOrganizationNetworks")
    @with_error_handling(
        operation="Collect STP priorities",
        continue_on_error=True,
    )
    async def collect_stp_priorities(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]] | None = None
    ) -> None:
        """Collect STP priorities for all switches in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
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
            switch_networks = [n for n in networks if "switch" in n.get("productTypes", [])]

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
                    network_name = network.get("name", network_id)

                    for switch_serial, priority in switch_priorities.items():
                        # Get switch details from device lookup
                        device_info = devices.get(switch_serial, {"serial": switch_serial})
                        device_info["networkId"] = network_id
                        device_info["networkName"] = network_name
                        device_info["orgId"] = org_id
                        device_info["orgName"] = org_name

                        # Create standard device labels
                        labels = create_device_labels(device_info, org_id=org_id, org_name=org_name)

                        self._switch_stp_priority.labels(**labels).set(priority)

                        logger.debug(
                            "Set STP priority",
                            serial=switch_serial,
                            name=labels["name"],
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
        # Extract org info from device data
        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)

        # Create standard device labels
        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)
        serial = device_labels.get("serial")
        if serial and not self._should_collect_packet_stats(serial):
            logger.debug(
                "Skipping packet statistics collection",
                serial=serial,
                interval_seconds=self.settings.api.ms_packet_stats_interval,
            )
            return

        try:
            # Get packet statistics with 5-minute timespan
            with LogContext(serial=device_labels["serial"], name=device_labels["name"]):
                packet_stats = await asyncio.to_thread(
                    self.api.switch.getDeviceSwitchPortsStatusesPackets,
                    device_labels["serial"],
                    timespan=300,  # 5-minute window
                )
                packet_stats = validate_response_format(
                    packet_stats,
                    expected_type=list,
                    operation="getDeviceSwitchPortsStatusesPackets",
                )

            # Mapping of API descriptions to metric types
            metric_map = {
                "Total": (self._switch_port_packets_total, self._switch_port_packets_rate_total),
                "Broadcast": (
                    self._switch_port_packets_broadcast,
                    self._switch_port_packets_rate_broadcast,
                ),
                "Multicast": (
                    self._switch_port_packets_multicast,
                    self._switch_port_packets_rate_multicast,
                ),
                "CRC align errors": (
                    self._switch_port_packets_crcerrors,
                    self._switch_port_packets_rate_crcerrors,
                ),
                "Fragments": (
                    self._switch_port_packets_fragments,
                    self._switch_port_packets_rate_fragments,
                ),
                "Collisions": (
                    self._switch_port_packets_collisions,
                    self._switch_port_packets_rate_collisions,
                ),
                "Topology changes": (
                    self._switch_port_packets_topologychanges,
                    self._switch_port_packets_rate_topologychanges,
                ),
            }

            for port_data in packet_stats:
                packets = port_data.get("packets", [])

                for packet_type in packets:
                    desc = packet_type.get("desc", "")

                    if desc in metric_map:
                        count_metric, rate_metric = metric_map[desc]

                        # Total counts
                        total = packet_type.get("total", 0)
                        sent = packet_type.get("sent", 0)
                        recv = packet_type.get("recv", 0)

                        # Create port labels for each direction
                        total_labels = create_port_labels(
                            device, port_data, org_id=org_id, org_name=org_name, direction="total"
                        )
                        sent_labels = create_port_labels(
                            device, port_data, org_id=org_id, org_name=org_name, direction="sent"
                        )
                        recv_labels = create_port_labels(
                            device, port_data, org_id=org_id, org_name=org_name, direction="recv"
                        )

                        # Set count metrics
                        count_metric.labels(**total_labels).set(total)
                        count_metric.labels(**sent_labels).set(sent)
                        count_metric.labels(**recv_labels).set(recv)

                        # Rate per second
                        rate_data = packet_type.get("ratePerSec", {})
                        rate_total = rate_data.get("total", 0)
                        rate_sent = rate_data.get("sent", 0)
                        rate_recv = rate_data.get("recv", 0)

                        # Set rate metrics
                        rate_metric.labels(**total_labels).set(rate_total)
                        rate_metric.labels(**sent_labels).set(rate_sent)
                        rate_metric.labels(**recv_labels).set(rate_recv)

            logger.debug(
                "Collected packet statistics",
                serial=device_labels["serial"],
                name=device_labels["name"],
                port_count=len(packet_stats),
            )
            if serial:
                self._mark_packet_stats_collected(serial)

        except Exception:
            logger.exception(
                "Failed to collect packet statistics",
                serial=device_labels["serial"],
            )
