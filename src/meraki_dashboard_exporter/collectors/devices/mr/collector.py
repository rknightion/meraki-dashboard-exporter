"""MR collector coordinator that delegates to specialized sub-collectors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ....core.logging import get_logger
from ....core.otel_tracing import trace_method
from ...devices.base import BaseDeviceCollector
from .clients import MRClientsCollector
from .performance import MRPerformanceCollector
from .wireless import MRWirelessCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ...device import DeviceCollector

logger = get_logger(__name__)


class MRCollector(BaseDeviceCollector):
    """Coordinator for Meraki MR (Wireless AP) device collectors.

    This coordinator delegates to specialized sub-collectors:
    - MRClientsCollector: Client connection and authentication metrics
    - MRPerformanceCollector: Ethernet status, packet loss, CPU metrics
    - MRWirelessCollector: SSID status, radio configuration, usage metrics

    Pattern established in Phase 3.1 following Phase 3.2 metric expiration integration.
    """

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MR collector coordinator.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance.

        """
        super().__init__(parent)

        # Initialize sub-collectors
        self.clients = MRClientsCollector(parent)
        self.performance = MRPerformanceCollector(parent)
        self.wireless = MRWirelessCollector(parent)

        # For backward compatibility, expose metrics from sub-collectors
        # This allows existing code like `mr_collector._ap_clients` to continue working

        # Client metrics
        self._ap_clients = self.clients._ap_clients
        self._ap_connection_stats = self.clients._ap_connection_stats

        # Performance metrics - Power/Ethernet
        self._mr_power_info = self.performance._mr_power_info
        self._mr_power_ac_connected = self.performance._mr_power_ac_connected
        self._mr_power_poe_connected = self.performance._mr_power_poe_connected
        self._mr_port_poe_info = self.performance._mr_port_poe_info
        self._mr_port_link_negotiation_info = self.performance._mr_port_link_negotiation_info
        self._mr_port_link_negotiation_speed = self.performance._mr_port_link_negotiation_speed
        self._mr_aggregation_enabled = self.performance._mr_aggregation_enabled
        self._mr_aggregation_speed = self.performance._mr_aggregation_speed

        # Performance metrics - Packet Loss (device-level)
        self._mr_packets_downstream_total = self.performance._mr_packets_downstream_total
        self._mr_packets_downstream_lost = self.performance._mr_packets_downstream_lost
        self._mr_packet_loss_downstream_percent = (
            self.performance._mr_packet_loss_downstream_percent
        )
        self._mr_packets_upstream_total = self.performance._mr_packets_upstream_total
        self._mr_packets_upstream_lost = self.performance._mr_packets_upstream_lost
        self._mr_packet_loss_upstream_percent = self.performance._mr_packet_loss_upstream_percent
        self._mr_packets_total = self.performance._mr_packets_total
        self._mr_packets_lost_total = self.performance._mr_packets_lost_total
        self._mr_packet_loss_total_percent = self.performance._mr_packet_loss_total_percent

        # Performance metrics - Packet Loss (network-level)
        self._mr_network_packets_downstream_total = (
            self.performance._mr_network_packets_downstream_total
        )
        self._mr_network_packets_downstream_lost = (
            self.performance._mr_network_packets_downstream_lost
        )
        self._mr_network_packet_loss_downstream_percent = (
            self.performance._mr_network_packet_loss_downstream_percent
        )
        self._mr_network_packets_upstream_total = (
            self.performance._mr_network_packets_upstream_total
        )
        self._mr_network_packets_upstream_lost = self.performance._mr_network_packets_upstream_lost
        self._mr_network_packet_loss_upstream_percent = (
            self.performance._mr_network_packet_loss_upstream_percent
        )
        self._mr_network_packets_total = self.performance._mr_network_packets_total
        self._mr_network_packets_lost_total = self.performance._mr_network_packets_lost_total
        self._mr_network_packet_loss_total_percent = (
            self.performance._mr_network_packet_loss_total_percent
        )

        # Performance metrics - CPU
        self._mr_cpu_load_5min = self.performance._mr_cpu_load_5min

        # Wireless metrics - Radio
        self._mr_radio_broadcasting = self.wireless._mr_radio_broadcasting
        self._mr_radio_channel = self.wireless._mr_radio_channel
        self._mr_radio_channel_width = self.wireless._mr_radio_channel_width
        self._mr_radio_power = self.wireless._mr_radio_power

        # Wireless metrics - SSID Usage
        self._ssid_usage_total_mb = self.wireless._ssid_usage_total_mb
        self._ssid_usage_downstream_mb = self.wireless._ssid_usage_downstream_mb
        self._ssid_usage_upstream_mb = self.wireless._ssid_usage_upstream_mb
        self._ssid_usage_percentage = self.wireless._ssid_usage_percentage
        self._ssid_client_count = self.wireless._ssid_client_count
        self._packet_value_cache = self.performance._packet_value_cache

    def update_api(self, api: DashboardAPI) -> None:
        """Propagate API updates to sub-collectors."""
        self.api = api
        self.clients.api = api
        self.performance.api = api
        self.wireless.api = api

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect per-device wireless AP metrics.

        Delegates to clients sub-collector. Performance and wireless metrics
        are collected at org-level via separate methods.

        Parameters
        ----------
        device : dict[str, Any]
            Wireless device data.

        """
        # Delegate to clients sub-collector for per-device metrics
        await self.clients.collect(device)

        # Note: Performance metrics (ethernet, packet loss, CPU) and wireless
        # metrics (SSID status, radio config) are collected at org-level via
        # separate delegation methods called from the parent DeviceCollector

    @trace_method("collect.mr_wireless_clients")
    async def collect_wireless_clients(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect wireless client counts for MR devices (org-level).

        Delegates to clients sub-collector.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table for device info.

        """
        await self.clients.collect_wireless_clients(org_id, org_name, device_lookup)

    @trace_method("collect.mr_ethernet_status")
    async def collect_ethernet_status(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect ethernet status for MR devices (org-level).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table for device info.

        """
        await self.performance.collect_ethernet_status(org_id, org_name, device_lookup)

    @trace_method("collect.mr_packet_loss")
    async def collect_packet_loss(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect packet loss metrics for MR devices (org-level).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table for device info.

        """
        await self.performance.collect_packet_loss(org_id, org_name, device_lookup)

    @trace_method("collect.mr_cpu_load")
    async def collect_cpu_load(
        self, org_id: str, org_name: str, devices: list[dict[str, Any]]
    ) -> None:
        """Collect CPU load metrics for MR devices (org-level).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        devices : list[dict[str, Any]]
            List of device data.

        """
        await self.performance.collect_cpu_load(org_id, org_name, devices)

    @trace_method("collect.mr_ssid_status")
    async def collect_ssid_status(self, org_id: str, org_name: str) -> None:
        """Collect SSID status metrics (org-level).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        await self.wireless.collect_ssid_status(org_id, org_name)

    @trace_method("collect.mr_ssid_usage")
    async def collect_ssid_usage(self, org_id: str, org_name: str) -> None:
        """Collect SSID usage metrics (org-level).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        await self.wireless.collect_ssid_usage(org_id, org_name)

    @trace_method("collect.mr_connection_stats")
    async def collect_connection_stats(
        self,
        org_id: str,
        org_name: str,
        networks: list[dict[str, Any]],
        device_lookup: dict[str, dict[str, Any]],
    ) -> None:
        """Collect wireless connection statistics for MR devices (network-level).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        networks : list[dict[str, Any]]
            List of wireless networks in the organization.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table for device info.

        """
        await self.clients.collect_connection_stats(org_id, org_name, networks, device_lookup)
