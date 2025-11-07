"""MR wireless performance metrics collector (ethernet, packet loss, CPU).

This module handles performance-related metrics for MR devices:
- Ethernet status and power metrics
- Packet loss statistics
- CPU load metrics

Pattern established in Phase 3.1 following Phase 3.2 metric expiration integration.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from ....core.constants import MRMetricName
from ....core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ....core.label_helpers import create_device_labels, create_network_labels
from ....core.logging import get_logger
from ....core.logging_decorators import log_api_call
from ....core.logging_helpers import LogContext
from ....core.metrics import LabelName

if TYPE_CHECKING:
    from ...device import DeviceCollector

logger = get_logger(__name__)


class MRPerformanceCollector:
    """Collector for MR wireless performance metrics."""

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MR performance collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance that owns the metrics.

        """
        self.parent = parent
        self.api = parent.api
        self.settings = parent.settings
        # Cache for packet metric values (for retention logic)
        self._packet_value_cache: dict[str, float] = {}
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize performance-related metrics (ethernet/power, packet loss, CPU)."""
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
            "Total packet loss percentage for access point (5-minute window)",
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

        # Network-level packet loss metrics (aggregated, 5-minute window)
        self._mr_network_packets_downstream_total = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKETS_DOWNSTREAM_TOTAL,
            "Total downstream packets for network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packets_downstream_lost = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKETS_DOWNSTREAM_LOST,
            "Downstream packets lost for network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packet_loss_downstream_percent = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKET_LOSS_DOWNSTREAM_PERCENT,
            "Downstream packet loss percentage for network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packets_upstream_total = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKETS_UPSTREAM_TOTAL,
            "Total upstream packets for network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packets_upstream_lost = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKETS_UPSTREAM_LOST,
            "Upstream packets lost for network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packet_loss_upstream_percent = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKET_LOSS_UPSTREAM_PERCENT,
            "Upstream packet loss percentage for network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packets_total = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKETS_TOTAL,
            "Total packets (upstream + downstream) for network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packets_lost_total = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKETS_LOST_TOTAL,
            "Total packets lost (upstream + downstream) for network (5-minute window)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        self._mr_network_packet_loss_total_percent = self.parent._create_gauge(
            MRMetricName.MR_NETWORK_PACKET_LOSS_TOTAL_PERCENT,
            "Total packet loss percentage for network (5-minute window)",
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
            "Access point CPU load percentage (5-minute average)",
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
                device_info["networkName"] = network_info.get(
                    "name", device_info.get("networkId", "")
                )
                device_info["name"] = device_info.get("name") or device_status.get("name", serial)
                device_info["orgId"] = org_id
                device_info["orgName"] = org_name

                # Create standard device labels
                device_labels = create_device_labels(device_info, org_id=org_id, org_name=org_name)

                # Power mode information - using P3.2 pattern
                power_mode = device_status.get("power", {}).get("mode")
                if power_mode:
                    power_labels = create_device_labels(
                        device_info, org_id=org_id, org_name=org_name, mode=power_mode
                    )
                    self.parent._set_metric(
                        self._mr_power_info,
                        power_labels,
                        1,
                    )

                # AC power status - using P3.2 pattern
                ac_info = device_status.get("power", {}).get("ac", {})
                ac_connected = ac_info.get("isConnected", False)
                self.parent._set_metric(
                    self._mr_power_ac_connected,
                    device_labels,
                    1 if ac_connected else 0,
                )

                # PoE power status - using P3.2 pattern
                poe_info = device_status.get("power", {}).get("poe", {})
                poe_connected = poe_info.get("isConnected", False)
                self.parent._set_metric(
                    self._mr_power_poe_connected,
                    device_labels,
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
                    if poe_standard:
                        poe_labels = create_device_labels(
                            device_info,
                            org_id=org_id,
                            org_name=org_name,
                            port_name=port_name,
                            standard=poe_standard,
                        )
                        self.parent._set_metric(
                            self._mr_port_poe_info,
                            poe_labels,
                            1,
                        )

                    # Link negotiation information
                    link_negotiation = port.get("linkNegotiation", {})
                    duplex = link_negotiation.get("duplex")
                    if duplex:
                        link_labels = create_device_labels(
                            device_info,
                            org_id=org_id,
                            org_name=org_name,
                            port_name=port_name,
                            duplex=duplex,
                        )
                        self.parent._set_metric(
                            self._mr_port_link_negotiation_info,
                            link_labels,
                            1,
                        )

                    speed = link_negotiation.get("speed")
                    if speed:
                        speed_labels = create_device_labels(
                            device_info,
                            org_id=org_id,
                            org_name=org_name,
                            port_name=port_name,
                        )
                        self.parent._set_metric(
                            self._mr_port_link_negotiation_speed,
                            speed_labels,
                            speed,
                        )

                    # Track aggregation
                    if port.get("aggregation", {}).get("enabled"):
                        aggregation_enabled = True
                    if speed:
                        total_speed += speed

                # Aggregation metrics - using P3.2 pattern
                self.parent._set_metric(
                    self._mr_aggregation_enabled,
                    device_labels,
                    1 if aggregation_enabled else 0,
                )

                if aggregation_enabled and total_speed > 0:
                    self.parent._set_metric(
                        self._mr_aggregation_speed,
                        device_labels,
                        total_speed,
                    )

        except Exception:
            logger.exception(
                "Failed to collect ethernet status",
                org_id=org_id,
            )

    @log_api_call("getOrganizationWirelessDevicesPacketLossByClient")
    @with_error_handling(
        operation="Collect MR packet loss",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_packet_loss(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect packet loss metrics for MR devices.

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
            # Fetch network-level packet loss data
            network_packet_loss = await self._fetch_network_packet_loss(org_id)

            if not network_packet_loss:
                logger.debug(
                    "No network packet loss data available",
                    org_id=org_id,
                )
                return

            # Process network-level packet loss
            for network_data in network_packet_loss:
                network_id = network_data.get("networkId", "")
                network_name = network_data.get("networkName", network_id)

                # Create network labels
                network_labels = create_network_labels(
                    network={"id": network_id, "name": network_name},
                    org_id=org_id,
                    org_name=org_name,
                )

                # Downstream metrics
                downstream = network_data.get("downstream", {})
                downstream_total = downstream.get("total")
                downstream_lost = downstream.get("lost")
                downstream_loss_percent = downstream.get("lossPercentage")

                self._set_packet_metric_value(
                    "_mr_network_packets_downstream_total", network_labels, downstream_total
                )
                self._set_packet_metric_value(
                    "_mr_network_packets_downstream_lost", network_labels, downstream_lost
                )
                self._set_packet_metric_value(
                    "_mr_network_packet_loss_downstream_percent",
                    network_labels,
                    downstream_loss_percent,
                )

                # Upstream metrics
                upstream = network_data.get("upstream", {})
                upstream_total = upstream.get("total")
                upstream_lost = upstream.get("lost")
                upstream_loss_percent = upstream.get("lossPercentage")

                self._set_packet_metric_value(
                    "_mr_network_packets_upstream_total", network_labels, upstream_total
                )
                self._set_packet_metric_value(
                    "_mr_network_packets_upstream_lost", network_labels, upstream_lost
                )
                self._set_packet_metric_value(
                    "_mr_network_packet_loss_upstream_percent",
                    network_labels,
                    upstream_loss_percent,
                )

                # Combined metrics
                if downstream_total is not None and upstream_total is not None:
                    total_packets = downstream_total + upstream_total
                    total_lost = (downstream_lost or 0) + (upstream_lost or 0)

                    self._set_packet_metric_value(
                        "_mr_network_packets_total", network_labels, total_packets
                    )
                    self._set_packet_metric_value(
                        "_mr_network_packets_lost_total", network_labels, total_lost
                    )

                    if total_packets > 0:
                        total_loss_percent = (total_lost / total_packets) * 100
                        self._set_packet_metric_value(
                            "_mr_network_packet_loss_total_percent",
                            network_labels,
                            total_loss_percent,
                        )

                # Process device-level packet loss
                for device_data in network_data.get("devices", []):
                    serial = device_data.get("serial", "")
                    device_info = device_lookup.get(serial, {"serial": serial})
                    device_info["networkId"] = network_id
                    device_info["networkName"] = network_name
                    device_info["orgId"] = org_id
                    device_info["orgName"] = org_name

                    device_labels = create_device_labels(
                        device_info, org_id=org_id, org_name=org_name
                    )

                    # Device downstream metrics
                    dev_downstream = device_data.get("downstream", {})
                    dev_downstream_total = dev_downstream.get("total")
                    dev_downstream_lost = dev_downstream.get("lost")
                    dev_downstream_loss_percent = dev_downstream.get("lossPercentage")

                    self._set_packet_metric_value(
                        "_mr_packets_downstream_total", device_labels, dev_downstream_total
                    )
                    self._set_packet_metric_value(
                        "_mr_packets_downstream_lost", device_labels, dev_downstream_lost
                    )
                    self._set_packet_metric_value(
                        "_mr_packet_loss_downstream_percent",
                        device_labels,
                        dev_downstream_loss_percent,
                    )

                    # Device upstream metrics
                    dev_upstream = device_data.get("upstream", {})
                    dev_upstream_total = dev_upstream.get("total")
                    dev_upstream_lost = dev_upstream.get("lost")
                    dev_upstream_loss_percent = dev_upstream.get("lossPercentage")

                    self._set_packet_metric_value(
                        "_mr_packets_upstream_total", device_labels, dev_upstream_total
                    )
                    self._set_packet_metric_value(
                        "_mr_packets_upstream_lost", device_labels, dev_upstream_lost
                    )
                    self._set_packet_metric_value(
                        "_mr_packet_loss_upstream_percent", device_labels, dev_upstream_loss_percent
                    )

                    # Device combined metrics
                    if dev_downstream_total is not None and dev_upstream_total is not None:
                        dev_total_packets = dev_downstream_total + dev_upstream_total
                        dev_total_lost = (dev_downstream_lost or 0) + (dev_upstream_lost or 0)

                        self._set_packet_metric_value(
                            "_mr_packets_total", device_labels, dev_total_packets
                        )
                        self._set_packet_metric_value(
                            "_mr_packets_lost_total", device_labels, dev_total_lost
                        )

                        if dev_total_packets > 0:
                            dev_total_loss_percent = (dev_total_lost / dev_total_packets) * 100
                            self._set_packet_metric_value(
                                "_mr_packet_loss_total_percent",
                                device_labels,
                                dev_total_loss_percent,
                            )

        except Exception:
            logger.exception(
                "Failed to collect packet loss metrics",
                org_id=org_id,
            )

    async def _fetch_network_packet_loss(self, org_id: str) -> Any:
        """Fetch network packet loss data.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        Any
            Packet loss data or None if unavailable.

        """
        try:
            with LogContext(org_id=org_id):
                packet_loss = await asyncio.to_thread(
                    self.api.wireless.getOrganizationWirelessDevicesPacketLossByNetwork,
                    org_id,
                    total_pages="all",
                    timespan=300,  # 5 minutes
                )
                packet_loss = validate_response_format(
                    packet_loss,
                    expected_type=list,
                    operation="getOrganizationWirelessDevicesPacketLossByNetwork",
                )
                return packet_loss
        except Exception:
            logger.exception(
                "Failed to fetch network packet loss",
                org_id=org_id,
            )
            return None

    @log_api_call("getOrganizationWirelessDevicesSystemCpuLoadHistory")
    @with_error_handling(
        operation="Collect MR CPU load",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
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
            List of device data.

        """
        try:
            # Filter for MR devices
            mr_devices = [d for d in devices if d.get("model", "").startswith("MR")]

            if not mr_devices:
                logger.debug("No MR devices found for CPU load collection", org_id=org_id)
                return

            # Process in batches
            batch_size = self.settings.api.batch_size

            # Process devices in batches (API requires batch processing)
            for i in range(0, len(mr_devices), batch_size):
                batch = mr_devices[i : i + batch_size]
                try:
                    await self._process_cpu_load_batch(org_id, org_name, batch)
                except Exception:
                    logger.exception(
                        "Failed to process CPU load batch",
                        org_id=org_id,
                        batch_start=i,
                        batch_size=len(batch),
                    )

                # Delay between batches (except for last)
                if i + batch_size < len(mr_devices):
                    await asyncio.sleep(0.5)

            logger.debug(
                "Completed MR CPU load collection",
                org_id=org_id,
                device_count=len(mr_devices),
            )

        except Exception:
            logger.exception(
                "Failed to collect MR CPU load",
                org_id=org_id,
            )

    async def _process_cpu_load_batch(
        self, org_id: str, org_name: str, devices: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Process a batch of devices for CPU load metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        devices : list[dict[str, Any]]
            Batch of devices to process.

        Returns
        -------
        list[dict[str, Any]]
            List of device results.

        """
        serials = [d.get("serial") for d in devices if d.get("serial")]

        if not serials:
            return []

        try:
            with LogContext(org_id=org_id):
                cpu_data_raw = await asyncio.to_thread(
                    self.api.wireless.getOrganizationWirelessDevicesSystemCpuLoadHistory,
                    org_id,
                    serials=serials,
                    timespan=300,  # 5 minutes
                )
                cpu_data = cast(
                    list[dict[str, Any]],
                    validate_response_format(
                        cpu_data_raw,
                        expected_type=list,
                        operation="getOrganizationWirelessDevicesSystemCpuLoadHistory",
                    ),
                )

            # Process CPU data for each device
            for item in cpu_data:
                serial = item.get("serial")
                if not serial:
                    continue

                # Find device info
                device = next((d for d in devices if d.get("serial") == serial), None)
                if not device:
                    continue

                # Extract CPU data
                cpu_value = self._extract_cpu_data(item)
                if cpu_value is None:
                    continue

                # Process device CPU data
                self._process_device_cpu_data(device, cpu_value, org_id, org_name)

            return cpu_data

        except Exception:
            logger.exception(
                "Failed to process CPU load batch",
                org_id=org_id,
                serial_count=len(serials),
            )
            return []

    def _extract_cpu_data(
        self,
        item: dict[str, Any],
    ) -> float | None:
        """Extract CPU load value from API response.

        Parameters
        ----------
        item : dict[str, Any]
            CPU data item from API.

        Returns
        -------
        float | None
            CPU load percentage or None if unavailable.

        """
        # Get the most recent CPU reading
        history = item.get("history", [])
        if not history:
            return None

        # Use the last (most recent) reading
        latest = history[-1]
        cpu_load = latest.get("load")

        # Return as float or None
        if cpu_load is not None:
            return float(cpu_load)
        return None

    def _process_device_cpu_data(
        self,
        device: dict[str, Any],
        cpu_load: float,
        org_id: str,
        org_name: str,
    ) -> None:
        """Process and set CPU load metric for a device.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.
        cpu_load : float
            CPU load percentage.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)

        # Set CPU load metric - using P3.2 pattern
        self.parent._set_metric(
            self._mr_cpu_load_5min,
            device_labels,
            cpu_load,
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

        # Use parent's _set_metric with P3.2 pattern for expiration tracking
        metric = getattr(self, metric_name, None)
        if metric and value is not None:
            self.parent._set_metric(metric, labels, value)
