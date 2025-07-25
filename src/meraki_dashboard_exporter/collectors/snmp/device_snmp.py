"""SNMP collectors for individual Meraki devices (MR, MS)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.logging import get_logger
from ...core.logging_helpers import LogContext
from ...core.metrics import LabelName
from .base import BaseSNMPCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Standard MIB-2 OIDs
MIB2_OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
}


class MRDeviceSNMPCollector(BaseSNMPCollector):
    """SNMP collector for Meraki MR (wireless) devices."""

    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics for MR SNMP."""
        # SNMP connectivity metric
        self.snmp_up_metric = self.parent._create_gauge(
            "meraki_snmp_mr_up",
            "Whether MR device SNMP is responding (1=up, 0=down)",
            [
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.NETWORK_ID.value,
                LabelName.NETWORK_NAME.value,
                LabelName.SERIAL.value,
                LabelName.NAME.value,
                LabelName.MAC.value,
            ],
        )

        # System uptime in seconds
        self.uptime_metric = self.parent._create_gauge(
            "meraki_snmp_mr_uptime_seconds",
            "Device uptime in seconds from SNMP",
            [
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.NETWORK_ID.value,
                LabelName.NETWORK_NAME.value,
                LabelName.SERIAL.value,
                LabelName.NAME.value,
                LabelName.MAC.value,
            ],
        )

    async def collect_snmp_metrics(self, target: dict[str, Any]) -> None:
        """Collect SNMP metrics from MR device.

        Parameters
        ----------
        target : dict[str, Any]
            MR device SNMP target information.

        """
        # Extract device metadata
        device_info = target["device_info"]
        labels = {
            LabelName.ORG_ID.value: device_info["org_id"],
            LabelName.ORG_NAME.value: device_info["org_name"],
            LabelName.NETWORK_ID.value: device_info["network_id"],
            LabelName.NETWORK_NAME.value: device_info["network_name"],
            LabelName.SERIAL.value: device_info["serial"],
            LabelName.NAME.value: device_info["name"],
            LabelName.MAC.value: device_info["mac"],
        }

        # Test SNMP connectivity with basic queries
        result = await self.snmp_get(
            target,
            MIB2_OIDS["sysDescr"],
            MIB2_OIDS["sysUpTime"],
            MIB2_OIDS["sysName"],
        )

        if result is None:
            # SNMP is down
            self.snmp_up_metric.labels(**labels).set(0)
            with LogContext(
                device_name=device_info["name"],
                device_serial=device_info["serial"],
                network_id=device_info["network_id"],
            ):
                logger.debug("MR device SNMP is down")
            return

        # SNMP is up
        self.snmp_up_metric.labels(**labels).set(1)

        # Process results
        for oid, value in result:
            if oid == MIB2_OIDS["sysUpTime"] and value is not None:
                # sysUpTime is already in seconds (converted by base class)
                self.uptime_metric.labels(**labels).set(value)


class MSDeviceSNMPCollector(BaseSNMPCollector):
    """SNMP collector for Meraki MS (switch) devices."""

    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics for MS SNMP."""
        # SNMP connectivity metric
        self.snmp_up_metric = self.parent._create_gauge(
            "meraki_snmp_ms_up",
            "Whether MS device SNMP is responding (1=up, 0=down)",
            [
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.NETWORK_ID.value,
                LabelName.NETWORK_NAME.value,
                LabelName.SERIAL.value,
                LabelName.NAME.value,
                LabelName.MAC.value,
            ],
        )

        # System uptime in seconds
        self.uptime_metric = self.parent._create_gauge(
            "meraki_snmp_ms_uptime_seconds",
            "Device uptime in seconds from SNMP",
            [
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.NETWORK_ID.value,
                LabelName.NETWORK_NAME.value,
                LabelName.SERIAL.value,
                LabelName.NAME.value,
                LabelName.MAC.value,
            ],
        )

        # MAC address table size
        self.mac_table_size_metric = self.parent._create_gauge(
            "meraki_snmp_ms_mac_table_size",
            "Number of MAC addresses in forwarding table",
            [
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.NETWORK_ID.value,
                LabelName.NETWORK_NAME.value,
                LabelName.SERIAL.value,
                LabelName.NAME.value,
                LabelName.MAC.value,
            ],
        )

    async def collect_snmp_metrics(self, target: dict[str, Any]) -> None:
        """Collect SNMP metrics from MS device.

        Parameters
        ----------
        target : dict[str, Any]
            MS device SNMP target information.

        """
        # Extract device metadata
        device_info = target["device_info"]
        labels = {
            LabelName.ORG_ID.value: device_info["org_id"],
            LabelName.ORG_NAME.value: device_info["org_name"],
            LabelName.NETWORK_ID.value: device_info["network_id"],
            LabelName.NETWORK_NAME.value: device_info["network_name"],
            LabelName.SERIAL.value: device_info["serial"],
            LabelName.NAME.value: device_info["name"],
            LabelName.MAC.value: device_info["mac"],
        }

        # Test SNMP connectivity with basic queries
        result = await self.snmp_get(
            target,
            MIB2_OIDS["sysDescr"],
            MIB2_OIDS["sysUpTime"],
            MIB2_OIDS["sysName"],
        )

        if result is None:
            # SNMP is down
            self.snmp_up_metric.labels(**labels).set(0)
            with LogContext(
                device_name=device_info["name"],
                device_serial=device_info["serial"],
                network_id=device_info["network_id"],
            ):
                logger.debug("MS device SNMP is down")
            return

        # SNMP is up
        self.snmp_up_metric.labels(**labels).set(1)

        # Process results
        for oid, value in result:
            if oid == MIB2_OIDS["sysUpTime"] and value is not None:
                # sysUpTime is already in seconds (converted by base class)
                self.uptime_metric.labels(**labels).set(value)

        # Collect MAC address table size (example of MS-specific metric)
        await self._collect_mac_table_size(target, labels)

    async def _collect_mac_table_size(self, target: dict[str, Any], labels: dict[str, str]) -> None:
        """Collect MAC address table size.

        Parameters
        ----------
        target : dict[str, Any]
            SNMP target configuration.
        labels : dict[str, str]
            Metric labels.

        """
        # Use BRIDGE-MIB to get MAC table entries
        # This is a simplified example - real implementation would walk the table
        mac_table_oid = "1.3.6.1.2.1.17.4.3.1.1"  # dot1dTpFdbAddress

        # For now, we'll do a bulk operation to get a sample
        result = await self.snmp_bulk(target, mac_table_oid)

        if result:
            # Count unique MAC addresses
            mac_count = len([r for r in result if r[0].startswith(mac_table_oid)])
            self.mac_table_size_metric.labels(**labels).set(mac_count)
