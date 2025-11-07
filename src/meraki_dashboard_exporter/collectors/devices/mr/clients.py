"""MR wireless client connection metrics collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ....core.constants import MRMetricName
from ....core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ....core.label_helpers import create_device_labels
from ....core.logging import get_logger
from ....core.logging_decorators import log_api_call
from ....core.logging_helpers import LogContext
from ....core.metrics import LabelName

if TYPE_CHECKING:
    from ...device import DeviceCollector

logger = get_logger(__name__)


class MRClientsCollector:
    """Collector for MR wireless client connection metrics."""

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MR clients collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance that owns the metrics.

        """
        self.parent = parent
        self.api = parent.api
        self.settings = parent.settings
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize client-related metrics."""
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

    @log_api_call("getDeviceWirelessStatus")
    @with_error_handling(
        operation="Collect MR client metrics",
        continue_on_error=True,
    )
    async def collect(self, device: dict[str, Any]) -> None:
        """Collect per-device wireless client metrics.

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

            # Client count - using P3.2 pattern for expiration tracking
            if "clientCount" in status:
                self.parent._set_metric(
                    self._ap_clients,
                    device_labels,
                    status["clientCount"],
                )

            # Get connection stats (30 minute window)
            await self._collect_connection_stats(device)

        except Exception:
            logger.exception(
                "Failed to collect wireless client metrics",
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
                # Set all stats to 0 when no data - using P3.2 pattern
                for stat_type in ("assoc", "auth", "dhcp", "dns", "success"):
                    labels = create_device_labels(
                        device, org_id=org_id, org_name=org_name, stat_type=stat_type
                    )
                    self.parent._set_metric(
                        self._ap_connection_stats,
                        labels,
                        0,
                    )
                return

            stats = connection_stats.get("connectionStats", {})

            # Set metrics for each connection stat type - using P3.2 pattern
            for stat_type, value in stats.items():
                if stat_type in {"assoc", "auth", "dhcp", "dns", "success"}:
                    labels = create_device_labels(
                        device, org_id=org_id, org_name=org_name, stat_type=stat_type
                    )
                    self.parent._set_metric(
                        self._ap_connection_stats,
                        labels,
                        value,
                    )

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
        """Collect wireless client counts for MR devices (org-level).

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

                # Set metric - using P3.2 pattern for expiration tracking
                self.parent._set_metric(
                    self._ap_clients,
                    labels,
                    online_clients,
                )

        except Exception:
            logger.exception(
                "Failed to collect wireless client counts",
                org_id=org_id,
            )
