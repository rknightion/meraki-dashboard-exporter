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

# Cloud Controller specific OIDs from MERAKI-CLOUD-CONTROLLER-MIB
# Base OID: enterprises.meraki.cloudController.organization = 1.3.6.1.4.1.29671.1.1
CLOUD_CONTROLLER_BASE = "1.3.6.1.4.1.29671.1.1"

# Table OIDs
CLOUD_CONTROLLER_TABLES = {
    "devTable": f"{CLOUD_CONTROLLER_BASE}.4",  # Device table
    "devInterfaceTable": f"{CLOUD_CONTROLLER_BASE}.5",  # Interface table
}

# Entry OIDs (these are the base OIDs for table entries)
CLOUD_CONTROLLER_OIDS = {
    # Device table entries (indexed by MAC address)
    "device_status": f"{CLOUD_CONTROLLER_BASE}.4.1.3",  # devStatus
    "device_client_count": f"{CLOUD_CONTROLLER_BASE}.4.1.5",  # devClientCount
    "device_name": f"{CLOUD_CONTROLLER_BASE}.4.1.2",  # devName
    "device_serial": f"{CLOUD_CONTROLLER_BASE}.4.1.8",  # devSerial
    # Interface table entries (indexed by MAC address + interface index)
    "interface_name": f"{CLOUD_CONTROLLER_BASE}.5.1.3",  # devInterfaceName
    "interface_sent_pkts": f"{CLOUD_CONTROLLER_BASE}.5.1.4",  # devInterfaceSentPkts
    "interface_recv_pkts": f"{CLOUD_CONTROLLER_BASE}.5.1.5",  # devInterfaceRecvPkts
    "interface_sent_bytes": f"{CLOUD_CONTROLLER_BASE}.5.1.6",  # devInterfaceSentBytes
    "interface_recv_bytes": f"{CLOUD_CONTROLLER_BASE}.5.1.7",  # devInterfaceRecvBytes
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
                LabelName.NETWORK_ID.value,
                LabelName.NETWORK_NAME.value,
                LabelName.SERIAL.value,
                LabelName.NAME.value,
                LabelName.MAC.value,
            ],
        )

        # Device client count
        self.client_count_metric = self.parent._create_gauge(
            "meraki_snmp_organization_device_client_count",
            "Number of clients connected to device from cloud SNMP",
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

        # Interface packet counters
        self.interface_packets_sent = self.parent._create_counter(
            "meraki_snmp_organization_interface_packets_sent_total",
            "Total packets sent on interface from cloud SNMP",
            [
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.NETWORK_ID.value,
                LabelName.NETWORK_NAME.value,
                LabelName.SERIAL.value,
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
                LabelName.NETWORK_ID.value,
                LabelName.NETWORK_NAME.value,
                LabelName.SERIAL.value,
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
                LabelName.NETWORK_ID.value,
                LabelName.NETWORK_NAME.value,
                LabelName.SERIAL.value,
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
                LabelName.NETWORK_ID.value,
                LabelName.NETWORK_NAME.value,
                LabelName.SERIAL.value,
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

        # Walk the device status table to discover devices
        device_status_results = await self.snmp_bulk(target, CLOUD_CONTROLLER_OIDS["device_status"])

        # If v3 failed and we have a v2c fallback, try that
        if device_status_results is None and "v2c_fallback" in target:
            with LogContext(org_id=org_id, org_name=org_name):
                logger.info("SNMPv3 connection failed, falling back to v2c")

            # Mark v3 as failed for this org to avoid retrying in this session
            if hasattr(self.parent, "_failed_org_v3"):
                self.parent._failed_org_v3.add(org_id)

            # Update target with v2c settings
            fallback = target["v2c_fallback"]
            target["version"] = fallback["version"]
            target["community"] = fallback["community"]

            # Remove v3-specific settings
            for key in ["username", "auth_key", "priv_key", "auth_protocol", "priv_protocol"]:
                target.pop(key, None)

            # Retry with v2c
            device_status_results = await self.snmp_bulk(
                target, CLOUD_CONTROLLER_OIDS["device_status"]
            )

            # If v2c works, cache it as the working version
            if device_status_results and hasattr(self.parent, "_org_snmp_versions"):
                self.parent._org_snmp_versions[org_id] = "v2c"

        if device_status_results is None:
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

        with LogContext(
            org_id=org_id,
            org_name=org_name,
            snmp_version=target.get("version", "unknown"),
            device_count=len(device_status_results),
        ):
            logger.debug("Cloud controller SNMP connection established")

        # Process device status results
        await self._process_device_table(target, device_status_results, org_id, org_name)

        # Walk client count table
        client_count_results = await self.snmp_bulk(
            target, CLOUD_CONTROLLER_OIDS["device_client_count"]
        )
        if client_count_results:
            await self._process_client_counts(client_count_results, org_id, org_name, target)

        # Walk interface tables
        await self._collect_interface_metrics(target, org_id, org_name)

    def _parse_mac_from_oid(self, oid: str, base_oid: str) -> str | None:
        """Parse MAC address from SNMP OID.

        The MAC address is encoded as 6 octets after the base OID.
        Example: 1.3.6.1.4.1.29671.1.1.4.1.3.0.24.10.1.2.3
        would be MAC 00:18:0a:01:02:03

        Parameters
        ----------
        oid : str
            Full OID string
        base_oid : str
            Base OID to strip from the beginning

        Returns
        -------
        str | None
            MAC address in colon notation or None if parsing fails

        """
        try:
            # Remove the base OID and the leading dot
            suffix = oid.replace(base_oid + ".", "")
            # Split by dots to get the octets
            parts = suffix.split(".")

            if len(parts) >= 6:
                # First 6 parts are the MAC address octets
                mac_octets = parts[:6]
                # Convert to hex and format as MAC
                mac = ":".join(f"{int(octet):02x}" for octet in mac_octets)
                return mac
        except (ValueError, IndexError) as e:
            with LogContext(
                oid=oid,
                base_oid=base_oid,
                error=str(e),
                collector=self.__class__.__name__,
            ):
                logger.debug("Failed to parse MAC from OID")
        return None

    async def _process_device_table(
        self,
        target: dict[str, Any],
        results: list[tuple[str, Any]],
        org_id: str,
        org_name: str,
    ) -> None:
        """Process device status table results.

        Parameters
        ----------
        target : dict[str, Any]
            SNMP target configuration.
        results : list[tuple[str, Any]]
            SNMP walk results for device status
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        # Get device map from target for enrichment
        device_map = target.get("device_map", {})

        # Also get device names and serials from SNMP if available
        name_results = await self.snmp_bulk(target, CLOUD_CONTROLLER_OIDS["device_name"])
        serial_results = await self.snmp_bulk(target, CLOUD_CONTROLLER_OIDS["device_serial"])

        name_map = {}
        if name_results:
            for oid, value in name_results:
                if value:
                    mac = self._parse_mac_from_oid(oid, CLOUD_CONTROLLER_OIDS["device_name"])
                    if mac:
                        name_map[mac] = value

        serial_map = {}
        if serial_results:
            for oid, value in serial_results:
                if value:
                    mac = self._parse_mac_from_oid(oid, CLOUD_CONTROLLER_OIDS["device_serial"])
                    if mac:
                        serial_map[mac] = value

        # Process status results
        for oid, value in results:
            if value is None:
                continue

            # Parse MAC address from OID
            mac = self._parse_mac_from_oid(oid, CLOUD_CONTROLLER_OIDS["device_status"])
            if not mac:
                continue

            # Normalize MAC for lookup (lowercase, no colons)
            normalized_mac = mac.lower().replace(":", "")

            # Skip unknown devices (not in device_map)
            if normalized_mac not in device_map:
                with LogContext(
                    device_mac=mac,
                    collector=self.__class__.__name__,
                ):
                    logger.debug("Skipping unknown device from SNMP results")
                continue

            # Get device info from map
            device_info = device_map[normalized_mac]
            device = device_info["device"]
            network = device_info["network"]

            # Get device name from SNMP or API
            device_name = name_map.get(mac) or device.get("name", device["serial"])

            # Get serial from SNMP or API
            serial = serial_map.get(mac) or device.get("serial", "")

            # Device status (0=offline, 1=online)
            try:
                status = 1 if value == 1 else 0
                self.device_status_metric.labels(**{
                    LabelName.ORG_ID.value: org_id,
                    LabelName.ORG_NAME.value: org_name,
                    LabelName.NETWORK_ID.value: network.get("id", ""),
                    LabelName.NETWORK_NAME.value: network.get("name", ""),
                    LabelName.SERIAL.value: serial,
                    LabelName.NAME.value: device_name,
                    LabelName.MAC.value: mac,
                }).set(status)

                with LogContext(
                    device_mac=mac,
                    device_name=device_name,
                    serial=serial,
                    network_name=network.get("name", ""),
                    status="online" if status == 1 else "offline",
                    collector=self.__class__.__name__,
                ):
                    logger.debug("Set device status metric")

            except (ValueError, TypeError) as e:
                with LogContext(
                    device_mac=mac,
                    value=value,
                    error=str(e),
                    collector=self.__class__.__name__,
                ):
                    logger.warning("Failed to set device status metric")

    async def _process_client_counts(
        self,
        results: list[tuple[str, Any]],
        org_id: str,
        org_name: str,
        target: dict[str, Any],
    ) -> None:
        """Process client count results.

        Parameters
        ----------
        results : list[tuple[str, Any]]
            SNMP walk results for client counts
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        target : dict[str, Any]
            SNMP target with device_map.

        """
        # Get device map from target for enrichment
        device_map = target.get("device_map", {})

        for oid, value in results:
            if value is None:
                continue

            # Parse MAC address from OID
            mac = self._parse_mac_from_oid(oid, CLOUD_CONTROLLER_OIDS["device_client_count"])
            if not mac:
                continue

            # Normalize MAC for lookup (lowercase, no colons)
            normalized_mac = mac.lower().replace(":", "")

            # Skip unknown devices (not in device_map)
            if normalized_mac not in device_map:
                with LogContext(
                    device_mac=mac,
                    collector=self.__class__.__name__,
                ):
                    logger.debug("Skipping client count for unknown device")
                continue

            # Get device info from map
            device_info = device_map[normalized_mac]
            device = device_info["device"]
            network = device_info["network"]

            # Check if value is numeric
            try:
                # Ensure value is a number
                client_count = int(value)

                self.client_count_metric.labels(**{
                    LabelName.ORG_ID.value: org_id,
                    LabelName.ORG_NAME.value: org_name,
                    LabelName.NETWORK_ID.value: network.get("id", ""),
                    LabelName.NETWORK_NAME.value: network.get("name", ""),
                    LabelName.SERIAL.value: device.get("serial", ""),
                    LabelName.NAME.value: device.get("name", device["serial"]),
                    LabelName.MAC.value: mac,
                }).set(client_count)

                with LogContext(
                    device_mac=mac,
                    device_name=device.get("name", device["serial"]),
                    serial=device.get("serial", ""),
                    network_name=network.get("name", ""),
                    client_count=client_count,
                    collector=self.__class__.__name__,
                ):
                    logger.debug("Set client count metric")

            except (ValueError, TypeError) as e:
                with LogContext(
                    device_mac=mac,
                    value=value,
                    value_type=type(value).__name__,
                    error=str(e),
                    collector=self.__class__.__name__,
                ):
                    logger.warning("Failed to set client count metric - invalid value type")

    async def _collect_interface_metrics(
        self,
        target: dict[str, Any],
        org_id: str,
        org_name: str,
    ) -> None:
        """Collect interface metrics from all devices.

        Parameters
        ----------
        target : dict[str, Any]
            SNMP target configuration.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        # Get device map from target for enrichment
        device_map = target.get("device_map", {})

        # Walk interface name table first to get interface names
        name_results = await self.snmp_bulk(target, CLOUD_CONTROLLER_OIDS["interface_name"])
        interface_names = {}
        if name_results:
            for oid, value in name_results:
                if value:
                    # Parse MAC and interface index from OID
                    mac, if_idx = self._parse_interface_oid(
                        oid, CLOUD_CONTROLLER_OIDS["interface_name"]
                    )
                    if mac and if_idx:
                        interface_names[(mac, if_idx)] = value

        # Walk each interface metric table
        for metric_name, metric_oid in [
            ("sent_pkts", CLOUD_CONTROLLER_OIDS["interface_sent_pkts"]),
            ("recv_pkts", CLOUD_CONTROLLER_OIDS["interface_recv_pkts"]),
            ("sent_bytes", CLOUD_CONTROLLER_OIDS["interface_sent_bytes"]),
            ("recv_bytes", CLOUD_CONTROLLER_OIDS["interface_recv_bytes"]),
        ]:
            results = await self.snmp_bulk(target, metric_oid)
            if not results:
                continue

            for oid, value in results:
                if value is None:
                    continue

                # Parse MAC and interface index from OID
                mac, if_idx = self._parse_interface_oid(oid, metric_oid)
                if not mac or not if_idx:
                    continue

                # Normalize MAC for lookup (lowercase, no colons)
                normalized_mac = mac.lower().replace(":", "")

                # Skip unknown devices (not in device_map)
                if normalized_mac not in device_map:
                    with LogContext(
                        device_mac=mac,
                        interface_idx=if_idx,
                        collector=self.__class__.__name__,
                    ):
                        logger.debug("Skipping interface metric for unknown device")
                    continue

                # Get device info from map
                device_info = device_map[normalized_mac]
                device = device_info["device"]
                network = device_info["network"]

                # Get interface name or use index
                if_name = interface_names.get((mac, if_idx), f"interface{if_idx}")

                labels = {
                    LabelName.ORG_ID.value: org_id,
                    LabelName.ORG_NAME.value: org_name,
                    LabelName.NETWORK_ID.value: network.get("id", ""),
                    LabelName.NETWORK_NAME.value: network.get("name", ""),
                    LabelName.SERIAL.value: device.get("serial", ""),
                    LabelName.MAC.value: mac,
                    LabelName.NAME.value: device.get("name", device["serial"]),
                    LabelName.PORT_NAME.value: if_name,
                }

                try:
                    if metric_name == "sent_pkts":
                        self.interface_packets_sent.labels(**labels)._value.set(value)
                    elif metric_name == "recv_pkts":
                        self.interface_packets_received.labels(**labels)._value.set(value)
                    elif metric_name == "sent_bytes":
                        self.interface_bytes_sent.labels(**labels)._value.set(value)
                    elif metric_name == "recv_bytes":
                        self.interface_bytes_received.labels(**labels)._value.set(value)

                    with LogContext(
                        device_mac=mac,
                        device_name=device.get("name", device["serial"]),
                        serial=device.get("serial", ""),
                        network_name=network.get("name", ""),
                        interface=if_name,
                        metric=metric_name,
                        value=value,
                        collector=self.__class__.__name__,
                    ):
                        logger.debug("Set interface metric")

                except (ValueError, TypeError) as e:
                    with LogContext(
                        device_mac=mac,
                        interface=if_name,
                        metric=metric_name,
                        value=value,
                        error=str(e),
                        collector=self.__class__.__name__,
                    ):
                        logger.warning("Failed to set interface metric")

    def _parse_interface_oid(self, oid: str, base_oid: str) -> tuple[str | None, int | None]:
        """Parse MAC address and interface index from interface table OID.

        The interface table is indexed by MAC address (6 octets) followed by interface index.
        Example: 1.3.6.1.4.1.29671.1.1.5.1.4.0.24.10.1.2.3.1
        would be MAC 00:18:0a:01:02:03 interface 1

        Parameters
        ----------
        oid : str
            Full OID string
        base_oid : str
            Base OID to strip from the beginning

        Returns
        -------
        tuple[str | None, int | None]
            (MAC address in colon notation, interface index) or (None, None) if parsing fails

        """
        try:
            # Remove the base OID and the leading dot
            suffix = oid.replace(base_oid + ".", "")
            # Split by dots to get the octets
            parts = suffix.split(".")

            if len(parts) >= 7:  # 6 MAC octets + 1 interface index
                # First 6 parts are the MAC address octets
                mac_octets = parts[:6]
                # Convert to hex and format as MAC
                mac = ":".join(f"{int(octet):02x}" for octet in mac_octets)
                # Last part is the interface index
                if_idx = int(parts[6])
                return mac, if_idx
        except (ValueError, IndexError) as e:
            with LogContext(
                oid=oid,
                base_oid=base_oid,
                error=str(e),
                collector=self.__class__.__name__,
            ):
                logger.debug("Failed to parse interface OID")
        return None, None
