"""SNMP collector for Meraki Cloud Controller metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.logging import get_logger
from ...core.logging_helpers import LogContext
from ...core.metrics import LabelName
from .base import BaseSNMPCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Cloud Controller specific OIDs
CLOUD_CONTROLLER_OIDS = {
    "device_status": "1.3.6.1.4.1.29671.1.1.4.1.3",  # devStatus
    "device_client_count": "1.3.6.1.4.1.29671.1.1.4.1.5",  # devClientCount
    "device_last_contact": "1.3.6.1.4.1.29671.1.1.4.1.4",  # devContactedAt
    "interface_sent_pkts": "1.3.6.1.4.1.29671.1.1.5.1.4",  # devInterfaceSentPkts
    "interface_recv_pkts": "1.3.6.1.4.1.29671.1.1.5.1.5",  # devInterfaceRecvPkts
    "interface_sent_bytes": "1.3.6.1.4.1.29671.1.1.5.1.6",  # devInterfaceSentBytes
    "interface_recv_bytes": "1.3.6.1.4.1.29671.1.1.5.1.7",  # devInterfaceRecvBytes
}


class CloudControllerSNMPCollector(BaseSNMPCollector):
    """Collector for Meraki Cloud Controller SNMP metrics."""

    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics for cloud controller SNMP."""
        # Device status metric
        self.device_status_metric = self.parent._create_gauge(
            "meraki_snmp_organization_device_status",
            "Device online/offline status from cloud SNMP (1=online, 0=offline)",
            [
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.MAC.value,
                LabelName.NAME.value,
            ],
        )

        # Device client count
        self.client_count_metric = self.parent._create_gauge(
            "meraki_snmp_organization_device_client_count",
            "Number of clients connected to device from cloud SNMP",
            [
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.MAC.value,
                LabelName.NAME.value,
            ],
        )

        # Interface packet counters
        self.interface_packets_sent = self.parent._create_counter(
            "meraki_snmp_organization_interface_packets_sent_total",
            "Total packets sent on interface from cloud SNMP",
            [
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.MAC.value,
                LabelName.NAME.value,
                LabelName.PORT_NAME.value,
            ],
        )

        self.interface_packets_received = self.parent._create_counter(
            "meraki_snmp_organization_interface_packets_received_total",
            "Total packets received on interface from cloud SNMP",
            [
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.MAC.value,
                LabelName.NAME.value,
                LabelName.PORT_NAME.value,
            ],
        )

        # Interface byte counters
        self.interface_bytes_sent = self.parent._create_counter(
            "meraki_snmp_organization_interface_bytes_sent_total",
            "Total bytes sent on interface from cloud SNMP",
            [
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.MAC.value,
                LabelName.NAME.value,
                LabelName.PORT_NAME.value,
            ],
        )

        self.interface_bytes_received = self.parent._create_counter(
            "meraki_snmp_organization_interface_bytes_received_total",
            "Total bytes received on interface from cloud SNMP",
            [
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.MAC.value,
                LabelName.NAME.value,
                LabelName.PORT_NAME.value,
            ],
        )

        # SNMP connectivity metric
        self.snmp_up_metric = self.parent._create_gauge(
            "meraki_snmp_organization_up",
            "Whether cloud controller SNMP is responding (1=up, 0=down)",
            [LabelName.ORG_ID.value, LabelName.ORG_NAME.value],
        )

    async def collect_snmp_metrics(self, target: dict[str, Any]) -> None:
        """Collect SNMP metrics from cloud controller.

        Parameters
        ----------
        target : dict[str, Any]
            Cloud controller SNMP target information.

        """
        org_id = target["org_id"]
        org_name = target["org_name"]
        devices = target.get("devices", [])

        # Test SNMP connectivity with a simple query
        result = await self.snmp_get(target, CLOUD_CONTROLLER_OIDS["device_status"])

        if result is None:
            # SNMP is down
            self.snmp_up_metric.labels(**{
                LabelName.ORG_ID.value: org_id,
                LabelName.ORG_NAME.value: org_name,
            }).set(0)
            with LogContext(org_id=org_id, org_name=org_name):
                logger.warning("Cloud controller SNMP is down")
            return

        # SNMP is up
        self.snmp_up_metric.labels(**{
            LabelName.ORG_ID.value: org_id,
            LabelName.ORG_NAME.value: org_name,
        }).set(1)

        # Collect device-specific metrics
        for device in devices:
            await self._collect_device_metrics(target, device, org_id, org_name)

    async def _collect_device_metrics(
        self,
        target: dict[str, Any],
        device: dict[str, Any],
        org_id: str,
        org_name: str,
    ) -> None:
        """Collect metrics for a specific device.

        Parameters
        ----------
        target : dict[str, Any]
            SNMP target configuration.
        device : dict[str, Any]
            Device information.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        device_mac = device["mac"]
        device_name = device.get("name", device_mac)
        device_index = device.get("index")  # Device index in SNMP tables

        if not device_index:
            with LogContext(
                device_name=device_name,
                device_mac=device_mac,
                org_id=org_id,
            ):
                logger.debug("No SNMP index for device, skipping")
            return

        # Build OIDs with device index
        status_oid = f"{CLOUD_CONTROLLER_OIDS['device_status']}.{device_index}"
        client_count_oid = f"{CLOUD_CONTROLLER_OIDS['device_client_count']}.{device_index}"

        # Get device status and client count
        results = await self.snmp_get(target, status_oid, client_count_oid)

        if results:
            for oid, value in results:
                if oid.startswith(CLOUD_CONTROLLER_OIDS["device_status"]):
                    # Device status (0=offline, 1=online)
                    status = 1 if value == 1 else 0
                    self.device_status_metric.labels(**{
                        LabelName.ORG_ID.value: org_id,
                        LabelName.ORG_NAME.value: org_name,
                        LabelName.MAC.value: device_mac,
                        LabelName.NAME.value: device_name,
                    }).set(status)

                elif oid.startswith(CLOUD_CONTROLLER_OIDS["device_client_count"]):
                    # Client count
                    self.client_count_metric.labels(**{
                        LabelName.ORG_ID.value: org_id,
                        LabelName.ORG_NAME.value: org_name,
                        LabelName.MAC.value: device_mac,
                        LabelName.NAME.value: device_name,
                    }).set(value or 0)

        # Collect interface metrics if available
        await self._collect_interface_metrics(target, device, org_id, org_name, device_index)

    async def _collect_interface_metrics(
        self,
        target: dict[str, Any],
        device: dict[str, Any],
        org_id: str,
        org_name: str,
        device_index: int,
    ) -> None:
        """Collect interface metrics for a device.

        Parameters
        ----------
        target : dict[str, Any]
            SNMP target configuration.
        device : dict[str, Any]
            Device information.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_index : int
            Device SNMP index.

        """
        device_mac = device["mac"]
        device_name = device.get("name", device_mac)

        # Interface metrics are in a sub-table, need to walk them
        # For now, we'll just query the primary interface (index 1)
        interface_index = 1
        interface_name = "primary"

        # Build OIDs for interface metrics
        oids = [
            f"{CLOUD_CONTROLLER_OIDS['interface_sent_pkts']}.{device_index}.{interface_index}",
            f"{CLOUD_CONTROLLER_OIDS['interface_recv_pkts']}.{device_index}.{interface_index}",
            f"{CLOUD_CONTROLLER_OIDS['interface_sent_bytes']}.{device_index}.{interface_index}",
            f"{CLOUD_CONTROLLER_OIDS['interface_recv_bytes']}.{device_index}.{interface_index}",
        ]

        results = await self.snmp_get(target, *oids)

        if results:
            labels = {
                LabelName.ORG_ID.value: org_id,
                LabelName.ORG_NAME.value: org_name,
                LabelName.MAC.value: device_mac,
                LabelName.NAME.value: device_name,
                LabelName.PORT_NAME.value: interface_name,
            }

            for oid, value in results:
                if value is None:
                    continue

                if oid.startswith(CLOUD_CONTROLLER_OIDS["interface_sent_pkts"]):
                    self.interface_packets_sent.labels(**labels)._value.set(value)
                elif oid.startswith(CLOUD_CONTROLLER_OIDS["interface_recv_pkts"]):
                    self.interface_packets_received.labels(**labels)._value.set(value)
                elif oid.startswith(CLOUD_CONTROLLER_OIDS["interface_sent_bytes"]):
                    self.interface_bytes_sent.labels(**labels)._value.set(value)
                elif oid.startswith(CLOUD_CONTROLLER_OIDS["interface_recv_bytes"]):
                    self.interface_bytes_received.labels(**labels)._value.set(value)
