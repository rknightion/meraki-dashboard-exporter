"""MR wireless radio and SSID metrics collector.

This module handles wireless-specific metrics for MR devices:
- Radio status and configuration (broadcasting, channel, power)
- SSID status and usage statistics

Pattern established in Phase 3.1 following Phase 3.2 metric expiration integration.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

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


class MRWirelessCollector:
    """Collector for MR wireless radio and SSID metrics."""

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MR wireless collector.

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
        """Initialize wireless-related metrics (radio and SSID)."""
        # MR SSID/Radio status metrics
        self._mr_radio_broadcasting = self.parent._create_gauge(
            MRMetricName.MR_RADIO_BROADCASTING,
            "Access point radio broadcasting status (1 = broadcasting, 0 = not broadcasting)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.BAND,
                LabelName.RADIO_INDEX,
            ],
        )

        self._mr_radio_channel = self.parent._create_gauge(
            MRMetricName.MR_RADIO_CHANNEL,
            "Access point radio channel number",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.BAND,
                LabelName.RADIO_INDEX,
            ],
        )

        self._mr_radio_channel_width = self.parent._create_gauge(
            MRMetricName.MR_RADIO_CHANNEL_WIDTH_MHZ,
            "Access point radio channel width in MHz",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.BAND,
                LabelName.RADIO_INDEX,
            ],
        )

        self._mr_radio_power = self.parent._create_gauge(
            MRMetricName.MR_RADIO_POWER_DBM,
            "Access point radio transmit power in dBm",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.BAND,
                LabelName.RADIO_INDEX,
            ],
        )

        # SSID usage metrics (now with network labels)
        self._ssid_usage_total_mb = self.parent._create_gauge(
            MRMetricName.MR_SSID_USAGE_TOTAL_MB,
            "Total data usage in MB by SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SSID,
            ],
        )

        self._ssid_usage_downstream_mb = self.parent._create_gauge(
            MRMetricName.MR_SSID_USAGE_DOWNSTREAM_MB,
            "Downstream data usage in MB by SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SSID,
            ],
        )

        self._ssid_usage_upstream_mb = self.parent._create_gauge(
            MRMetricName.MR_SSID_USAGE_UPSTREAM_MB,
            "Upstream data usage in MB by SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SSID,
            ],
        )

        self._ssid_usage_percentage = self.parent._create_gauge(
            MRMetricName.MR_SSID_USAGE_PERCENTAGE,
            "Percentage of total organization data usage by SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SSID,
            ],
        )

        self._ssid_client_count = self.parent._create_gauge(
            MRMetricName.MR_SSID_CLIENT_COUNT,
            "Number of clients connected to SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SSID,
            ],
        )

    @log_api_call("getOrganizationWirelessSsidsStatusesByDevice")
    @with_error_handling(
        operation="Collect SSID status",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_ssid_status(self, org_id: str, org_name: str) -> None:
        """Collect SSID status metrics (org-level).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            with LogContext(org_id=org_id):
                ssid_statuses = await asyncio.to_thread(
                    self.api.wireless.getOrganizationWirelessSsidsStatusesByDevice,
                    org_id,
                )
                ssid_statuses = validate_response_format(
                    ssid_statuses,
                    expected_type=list,
                    operation="getOrganizationWirelessSsidsStatusesByDevice",
                )

            # Process SSID status for each device
            for device_status in ssid_statuses:
                serial = device_status.get("serial", "")
                network = device_status.get("network", {})
                network_id = network.get("id", "")
                network_name = network.get("name", network_id)

                # Get basic device info
                basic_info = device_status.get("basicServiceSets", [])

                for bss in basic_info:
                    band = bss.get("band")
                    radio_index = bss.get("index")
                    broadcasting = bss.get("broadcasting")
                    channel = bss.get("channel")
                    channel_width = bss.get("channelWidth")
                    power = bss.get("power")

                    # Create device info dict
                    device_info = {
                        "serial": serial,
                        "networkId": network_id,
                        "networkName": network_name,
                        "orgId": org_id,
                        "orgName": org_name,
                    }

                    # Create labels with band and radio index
                    radio_labels = create_device_labels(
                        device_info,
                        org_id=org_id,
                        org_name=org_name,
                        band=band,
                        radio_index=str(radio_index) if radio_index is not None else "0",
                    )

                    # Set radio metrics - using P3.2 pattern
                    if broadcasting is not None:
                        self.parent._set_metric(
                            self._mr_radio_broadcasting,
                            radio_labels,
                            1 if broadcasting else 0,
                        )

                    if channel is not None:
                        self.parent._set_metric(
                            self._mr_radio_channel,
                            radio_labels,
                            channel,
                        )

                    if channel_width is not None:
                        self.parent._set_metric(
                            self._mr_radio_channel_width,
                            radio_labels,
                            channel_width,
                        )

                    if power is not None:
                        self.parent._set_metric(
                            self._mr_radio_power,
                            radio_labels,
                            power,
                        )

        except Exception:
            logger.exception(
                "Failed to collect SSID status",
                org_id=org_id,
            )

    async def _build_ssid_to_network_mapping(self, org_id: str) -> dict[str, list[dict[str, str]]]:
        """Build mapping of SSID names to networks.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        dict[str, list[dict[str, str]]]
            Mapping of SSID names to list of networks with that SSID.

        """
        ssid_to_networks: dict[str, list[dict[str, str]]] = {}

        try:
            with LogContext(org_id=org_id):
                networks = await asyncio.to_thread(
                    self.api.organizations.getOrganizationNetworks,
                    org_id,
                )

            # Filter for wireless networks
            wireless_networks = [n for n in networks if "wireless" in n.get("productTypes", [])]

            # Get SSIDs for each network
            for network in wireless_networks:
                network_id = network.get("id", "")
                network_name = network.get("name", network_id)

                try:
                    with LogContext(network_id=network_id):
                        ssids = await asyncio.to_thread(
                            self.api.wireless.getNetworkWirelessSsids,
                            network_id,
                        )

                    for ssid in ssids:
                        ssid_name = ssid.get("name", "")
                        if ssid_name:
                            if ssid_name not in ssid_to_networks:
                                ssid_to_networks[ssid_name] = []
                            ssid_to_networks[ssid_name].append({
                                "id": network_id,
                                "name": network_name,
                            })

                except Exception:
                    logger.exception(
                        "Failed to get SSIDs for network",
                        network_id=network_id,
                    )
                    continue

            return ssid_to_networks

        except Exception:
            logger.exception(
                "Failed to build SSID to network mapping",
                org_id=org_id,
            )
            return {}

    @log_api_call("getOrganizationWirelessSsidUsage")
    @with_error_handling(
        operation="Collect SSID usage",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_ssid_usage(self, org_id: str, org_name: str) -> None:
        """Collect SSID usage metrics (org-level).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            with LogContext(org_id=org_id):
                ssid_usage = await asyncio.to_thread(
                    self.api.wireless.getOrganizationWirelessSsidUsage,
                    org_id,
                    timespan=86400,  # 24 hours
                )
                ssid_usage = validate_response_format(
                    ssid_usage,
                    expected_type=list,
                    operation="getOrganizationWirelessSsidUsage",
                )

            # Build SSID to network mapping for better labeling
            ssid_to_networks = await self._build_ssid_to_network_mapping(org_id)

            # Process SSID usage data
            for ssid_data in ssid_usage:
                ssid_name = ssid_data.get("ssidName", "")
                if not ssid_name:
                    continue

                # Get usage metrics
                usage = ssid_data.get("usage", {})
                total_mb = usage.get("total", 0) / (1024 * 1024)  # Convert bytes to MB
                downstream_mb = usage.get("downstream", 0) / (1024 * 1024)
                upstream_mb = usage.get("upstream", 0) / (1024 * 1024)

                # Calculate percentage of total org usage
                org_total = sum(s.get("usage", {}).get("total", 0) for s in ssid_usage)
                usage_percentage = (usage.get("total", 0) / org_total * 100) if org_total > 0 else 0

                # Client count
                client_count = ssid_data.get("clients", 0)

                # Get networks for this SSID
                networks = ssid_to_networks.get(ssid_name, [])

                if networks:
                    # Set metrics for each network with this SSID
                    for network in networks:
                        network_id = network.get("id", "")
                        network_name = network.get("name", network_id)

                        # Create labels
                        ssid_labels = {
                            "org_id": org_id,
                            "org_name": org_name,
                            "network_id": network_id,
                            "network_name": network_name,
                            "ssid": ssid_name,
                        }

                        # Set SSID usage metrics - using P3.2 pattern
                        self.parent._set_metric(
                            self._ssid_usage_total_mb,
                            ssid_labels,
                            total_mb,
                        )

                        self.parent._set_metric(
                            self._ssid_usage_downstream_mb,
                            ssid_labels,
                            downstream_mb,
                        )

                        self.parent._set_metric(
                            self._ssid_usage_upstream_mb,
                            ssid_labels,
                            upstream_mb,
                        )

                        self.parent._set_metric(
                            self._ssid_usage_percentage,
                            ssid_labels,
                            usage_percentage,
                        )

                        self.parent._set_metric(
                            self._ssid_client_count,
                            ssid_labels,
                            client_count,
                        )
                else:
                    # No network mapping found, use generic labels
                    logger.debug(
                        "No network mapping found for SSID",
                        ssid=ssid_name,
                        org_id=org_id,
                    )

                    # Set metrics with empty network info
                    ssid_labels = {
                        "org_id": org_id,
                        "org_name": org_name,
                        "network_id": "",
                        "network_name": "",
                        "ssid": ssid_name,
                    }

                    self.parent._set_metric(
                        self._ssid_usage_total_mb,
                        ssid_labels,
                        total_mb,
                    )

                    self.parent._set_metric(
                        self._ssid_usage_downstream_mb,
                        ssid_labels,
                        downstream_mb,
                    )

                    self.parent._set_metric(
                        self._ssid_usage_upstream_mb,
                        ssid_labels,
                        upstream_mb,
                    )

                    self.parent._set_metric(
                        self._ssid_usage_percentage,
                        ssid_labels,
                        usage_percentage,
                    )

                    self.parent._set_metric(
                        self._ssid_client_count,
                        ssid_labels,
                        client_count,
                    )

        except Exception:
            logger.exception(
                "Failed to collect SSID usage",
                org_id=org_id,
            )
