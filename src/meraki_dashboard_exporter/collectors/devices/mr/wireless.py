"""MR wireless radio and SSID metrics collector.

This module handles wireless-specific metrics for MR devices:
- Radio status and configuration (broadcasting, channel, power)
- SSID status and usage statistics

Pattern established in Phase 3.1 following Phase 3.2 metric expiration integration.
"""

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
from ....core.scheduler import EndpointGroupName

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
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
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
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
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
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
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
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.BAND,
                LabelName.RADIO_INDEX,
            ],
        )

        # SSID usage metrics. getOrganizationSummaryTopSsidsByUsage reports one
        # org-wide row per SSID name, so these are labelled at org+SSID level only
        # (no network labels — replicating the org total per network inflated sums).
        self._ssid_usage_total_mb = self.parent._create_gauge(
            MRMetricName.MR_SSID_USAGE_TOTAL_BYTES,
            "Total data usage in bytes by SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.SSID,
            ],
        )

        self._ssid_usage_downstream_mb = self.parent._create_gauge(
            MRMetricName.MR_SSID_USAGE_DOWNSTREAM_BYTES,
            "Downstream data usage in bytes by SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.SSID,
            ],
        )

        self._ssid_usage_upstream_mb = self.parent._create_gauge(
            MRMetricName.MR_SSID_USAGE_UPSTREAM_BYTES,
            "Upstream data usage in bytes by SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.SSID,
            ],
        )

        self._ssid_usage_percentage = self.parent._create_gauge(
            MRMetricName.MR_SSID_USAGE_PERCENT,
            "Percentage of total organization data usage by SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.SSID,
            ],
        )

        self._ssid_client_count = self.parent._create_gauge(
            MRMetricName.MR_SSID_CLIENT_COUNT,
            "Number of clients connected to SSID over the last day",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.SSID,
            ],
        )

    @log_api_call("getOrganizationWirelessSsidsStatusesByDevice")
    @with_error_handling(
        operation="Collect SSID status",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_ssid_status(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]]
    ) -> None:
        """Collect SSID status metrics (org-level).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]]
            Device lookup table for device info.

        """
        # Scheduler gate: skip the org-wide fetch when not due (#617).
        if not self.parent._should_run_group(EndpointGroupName.MR_SSID_STATUS):
            return
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.MR_SSID_STATUS)

        try:
            with LogContext(org_id=org_id):
                ssid_statuses = await asyncio.to_thread(
                    self.api.wireless.getOrganizationWirelessSsidsStatusesByDevice,
                    org_id,
                    perPage=500,
                    total_pages="all",
                )
                ssid_statuses = validate_response_format(
                    ssid_statuses,
                    expected_type=list,
                    operation="getOrganizationWirelessSsidsStatusesByDevice",
                )

            # Fetch succeeded — record the run so the gate can stretch (#617).
            self.parent._mark_group_ran(EndpointGroupName.MR_SSID_STATUS)

            # Resolve allowed network IDs for filter enforcement on org-wide responses.
            allowed_network_ids = (
                await self.parent.inventory.get_allowed_network_ids(org_id)
                if self.parent.inventory is not None
                else None
            )
            skipped = 0

            # Process SSID status for each device
            for device_status in ssid_statuses:
                serial = device_status.get("serial", "")
                network = device_status.get("network", {})
                network_id = network.get("id", "")
                network_name = network.get("name", network_id)

                if allowed_network_ids is not None and network_id not in allowed_network_ids:
                    skipped += 1
                    continue

                # Get basic device info
                basic_info = device_status.get("basicServiceSets", [])

                for bss in basic_info:
                    radio = bss.get("radio", {})
                    band = radio.get("band")
                    radio_index = radio.get("index")
                    broadcasting = radio.get("isBroadcasting")
                    channel = radio.get("channel")
                    channel_width = radio.get("channelWidth")
                    power = radio.get("power")

                    # Enrich device info from lookup (provides name, model, device_type)
                    device_info = device_lookup.get(serial, {"serial": serial})
                    device_info["serial"] = serial
                    device_info["networkId"] = network_id
                    device_info["networkName"] = network_name
                    device_info["name"] = device_info.get("name") or device_status.get(
                        "name", serial
                    )
                    device_info["orgId"] = org_id
                    device_info["orgName"] = org_name

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
                            ttl_seconds=ttl,
                        )

                    if channel is not None:
                        self.parent._set_metric(
                            self._mr_radio_channel,
                            radio_labels,
                            channel,
                            ttl_seconds=ttl,
                        )

                    if channel_width is not None:
                        self.parent._set_metric(
                            self._mr_radio_channel_width,
                            radio_labels,
                            channel_width,
                            ttl_seconds=ttl,
                        )

                    if power is not None:
                        self.parent._set_metric(
                            self._mr_radio_power,
                            radio_labels,
                            power,
                            ttl_seconds=ttl,
                        )

            if skipped:
                logger.debug(
                    "MR SSID status: skipped rows outside network filter",
                    org_id=org_id,
                    skipped_count=skipped,
                )

        except Exception:
            logger.exception(
                "Failed to collect SSID status",
                org_id=org_id,
            )

    @log_api_call("getOrganizationSummaryTopSsidsByUsage")
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
        # Scheduler gate: skip the org-wide summary fetch when not due (#617).
        if not self.parent._should_run_group(EndpointGroupName.MR_SSID_USAGE):
            return
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.MR_SSID_USAGE)

        try:
            with LogContext(org_id=org_id):
                # quantity=50 is the endpoint maximum (default is only top 10),
                # so orgs with up to 50 SSIDs get stable per-SSID series.
                ssid_usage = await asyncio.to_thread(
                    self.api.organizations.getOrganizationSummaryTopSsidsByUsage,
                    org_id,
                    quantity=50,
                )
                ssid_usage = validate_response_format(
                    ssid_usage,
                    expected_type=list,
                    operation="getOrganizationSummaryTopSsidsByUsage",
                )

            # Fetch succeeded — record the run so the gate can stretch (#617).
            self.parent._mark_group_ran(EndpointGroupName.MR_SSID_USAGE)

            # Process SSID usage data. Each row is an org-wide total for one SSID
            # name, so we emit exactly one org-level series per SSID (no per-network
            # replication, which previously inflated sum-by-org totals N-fold).
            for ssid_data in ssid_usage:
                ssid_name = ssid_data.get("name", "") or ssid_data.get("ssidName", "")
                if not ssid_name:
                    continue

                # Get usage metrics. API values are MB (decimal); convert to
                # bytes at the emit site (×1,000,000) per issue #531 APIDEV-03.
                usage = ssid_data.get("usage", {})
                total_bytes = usage.get("total", 0) * 1_000_000
                downstream_bytes = usage.get("downstream", 0) * 1_000_000
                upstream_bytes = usage.get("upstream", 0) * 1_000_000
                usage_percentage = usage.get("percentage", 0)

                # Client count
                clients = ssid_data.get("clients", {})
                client_count = clients.get("counts", {}).get("total", clients.get("total", 0))

                ssid_labels = {
                    "org_id": org_id,
                    "ssid": ssid_name,
                }

                # Set SSID usage metrics - using P3.2 pattern
                self.parent._set_metric(
                    self._ssid_usage_total_mb,
                    ssid_labels,
                    total_bytes,
                    ttl_seconds=ttl,
                )

                self.parent._set_metric(
                    self._ssid_usage_downstream_mb,
                    ssid_labels,
                    downstream_bytes,
                    ttl_seconds=ttl,
                )

                self.parent._set_metric(
                    self._ssid_usage_upstream_mb,
                    ssid_labels,
                    upstream_bytes,
                    ttl_seconds=ttl,
                )

                self.parent._set_metric(
                    self._ssid_usage_percentage,
                    ssid_labels,
                    usage_percentage,
                    ttl_seconds=ttl,
                )

                self.parent._set_metric(
                    self._ssid_client_count,
                    ssid_labels,
                    client_count,
                    ttl_seconds=ttl,
                )

        except Exception:
            logger.exception(
                "Failed to collect SSID usage",
                org_id=org_id,
            )
