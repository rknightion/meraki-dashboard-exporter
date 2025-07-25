"""SNMP collectors for individual Meraki devices (MR, MS)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.constants import UpdateTier
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

# BRIDGE-MIB OIDs
BRIDGE_MIB_OIDS = {
    # NOTE: Meraki devices don't implement STP portion of BRIDGE-MIB (1.3.6.1.2.1.17.2.*)
    # "dot1dStpTopChanges": "1.3.6.1.2.1.17.2.2.0",  # Not available on MS/MR
    "dot1dBaseBridgeAddress": "1.3.6.1.2.1.17.1.1.0",  # Bridge MAC address
    "dot1dBaseNumPorts": "1.3.6.1.2.1.17.1.2.0",  # Number of ports
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
                collector=self.__class__.__name__,
                tier=getattr(self, "update_tier", UpdateTier.FAST).value,
                device_type="MR",
            ):
                logger.debug("MR device SNMP is down")
            return

        # SNMP is up
        self.snmp_up_metric.labels(**labels).set(1)

        # Collect uptime using centralized method
        await self._collect_single_metric(
            target=target,
            metric_name="meraki_snmp_mr_uptime_seconds",
            oid=MIB2_OIDS["sysUpTime"],
            labels=labels,
            metric_obj=self.uptime_metric,
        )


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

        # Bridge information
        self.bridge_num_ports_metric = self.parent._create_gauge(
            "meraki_snmp_ms_bridge_num_ports",
            "Number of bridge ports from SNMP",
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
                collector=self.__class__.__name__,
                tier=getattr(self, "update_tier", UpdateTier.FAST).value,
                device_type="MS",
            ):
                logger.debug("MS device SNMP is down")
            return

        # SNMP is up
        self.snmp_up_metric.labels(**labels).set(1)

        # Process results for uptime
        for oid, value in result:
            if oid == MIB2_OIDS["sysUpTime"] and value is not None:
                # sysUpTime is already in seconds (converted by base class)
                self.uptime_metric.labels(**labels).set(value)

        # Collect uptime using centralized method
        await self._collect_single_metric(
            target=target,
            metric_name="meraki_snmp_ms_uptime_seconds",
            oid=MIB2_OIDS["sysUpTime"],
            labels=labels,
            metric_obj=self.uptime_metric,
        )

        # Collect bridge port count using centralized method
        await self._collect_single_metric(
            target=target,
            metric_name="meraki_snmp_ms_bridge_num_ports",
            oid=BRIDGE_MIB_OIDS["dot1dBaseNumPorts"],
            labels=labels,
            metric_obj=self.bridge_num_ports_metric,
        )

        # Collect MAC address table size
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
        mac_table_oid = "1.3.6.1.2.1.17.4.3.1.1"  # dot1dTpFdbAddress
        metric_name = "meraki_snmp_ms_mac_table_size"

        # Custom processing function to count MAC entries
        async def count_mac_entries() -> int:
            with LogContext(
                device_name=labels.get(LabelName.NAME.value, "unknown"),
                device_serial=labels.get(LabelName.SERIAL.value, "unknown"),
                metric_name=metric_name,
                oid=mac_table_oid,
                collector=self.__class__.__name__,
            ):
                logger.debug("Walking MAC address table")

            result = await self.snmp_bulk(target, mac_table_oid)
            if result:
                # Count unique MAC addresses
                mac_count = len([r for r in result if r[0].startswith(mac_table_oid)])
                return mac_count
            return 0

        # Use centralized method with custom processing
        mac_count = await count_mac_entries()
        if mac_count is not None:
            try:
                self.mac_table_size_metric.labels(**labels).set(mac_count)
                with LogContext(
                    device_name=labels.get(LabelName.NAME.value, "unknown"),
                    metric_name=metric_name,
                    value=mac_count,
                    collector=self.__class__.__name__,
                ):
                    logger.debug("Successfully set MAC table size metric")
            except (ValueError, TypeError) as e:
                with LogContext(
                    device_name=labels.get(LabelName.NAME.value, "unknown"),
                    metric_name=metric_name,
                    error=str(e),
                    collector=self.__class__.__name__,
                ):
                    logger.warning("Failed to set MAC table size metric")
