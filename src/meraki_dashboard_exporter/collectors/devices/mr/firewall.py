"""MR SSID firewall rule count and LAN-access metrics collector (#290)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ....core.async_utils import ManagedTaskGroup
from ....core.constants import MRMetricName
from ....core.domain_models import (
    WirelessSsid,
    WirelessSsidFirewallL3Rules,
    WirelessSsidFirewallL7Rules,
)
from ....core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ....core.logging import get_logger
from ....core.logging_decorators import log_api_call
from ....core.logging_helpers import LogContext
from ....core.metrics import LabelName
from ....core.scheduler import EndpointGroupName

if TYPE_CHECKING:
    from ...device import DeviceCollector

logger = get_logger(__name__)

# Meraki always appends a synthetic trailing rule to the L3 rule list that
# cannot be removed by the admin; exclude it from the user-defined count,
# mirroring mx_firewall.py's default-rule exclusion for MX appliances.
_DEFAULT_RULE_COMMENT = "Default rule"


class MRFirewallCollector:
    """Collector for per-SSID L3/L7 firewall rule counts and LAN-access policy.

    Enumerates the SSIDs configured on each wireless network
    (``getNetworkWirelessSsids``) and, for every *enabled* SSID only (bounding
    call volume to at most 15 SSIDs/network), fetches the L3 and L7 firewall
    rule sets. Disabled SSIDs are skipped entirely — this is mandatory, not an
    optimization, because call volume here is networks x enabled-SSIDs x 2.
    """

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MR firewall collector.

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
        """Initialize SSID firewall-related metrics."""
        self._ssid_firewall_rules = self.parent._create_gauge(
            MRMetricName.MR_SSID_FIREWALL_RULES,
            "Number of user-defined SSID firewall rules by type (excludes the implicit default rule)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SSID,
                LabelName.RULE_TYPE,
            ],
        )

        self._ssid_allow_lan_access = self.parent._create_gauge(
            MRMetricName.MR_SSID_ALLOW_LAN_ACCESS,
            "Whether wireless clients on this SSID may access the LAN (1 = allowed, 0 = blocked)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SSID,
            ],
        )

    @log_api_call("getNetworkWirelessSsidFirewallL3FirewallRules")
    @with_error_handling(
        operation="Collect MR SSID firewall rules",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_ssid_firewall(
        self,
        org_id: str,
        org_name: str,
        networks: list[dict[str, Any]],
    ) -> None:
        """Collect per-SSID firewall rule counts for all wireless networks.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        networks : list[dict[str, Any]]
            Networks in the organization (already NetworkFilter-filtered via
            ``OrganizationInventory.get_networks``); filtered here to wireless
            networks only.

        """
        # Scheduler gate: skip the whole per-network fan-out when not due (#617).
        if not self.parent._should_run_group(EndpointGroupName.MR_SSID_FIREWALL):
            return

        wireless_networks = [n for n in networks if "wireless" in n.get("productTypes", [])]

        async with ManagedTaskGroup(
            name="mr_ssid_firewall_networks",
            max_concurrency=self.settings.api.concurrency_limit,
        ) as group:
            for network in wireless_networks:
                network_id = network.get("id", "")
                network_name = network.get("name", network_id)
                if not network_id:
                    continue
                await group.create_task(
                    self.collect_for_network(org_id, org_name, network_id, network_name),
                    name=f"ssid_firewall_{network_id}",
                )

        # Mark ran after the per-network fan-out completes (#617), mirroring
        # ms_stack.py's collect_for_org gate-once/mark-once pattern.
        self.parent._mark_group_ran(EndpointGroupName.MR_SSID_FIREWALL)

    @log_api_call("getNetworkWirelessSsids")
    @with_error_handling(
        operation="Collect MR SSID firewall rules for network",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_for_network(
        self,
        org_id: str,
        org_name: str,
        network_id: str,
        network_name: str,
    ) -> None:
        """Collect firewall rule counts for every enabled SSID on one network.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        network_id : str
            Network ID for the wireless network.
        network_name : str
            Human-readable network name (unused in labels; ID-only, #534).

        """
        # Per-network fetch inside the collect_ssid_firewall fan-out; the group
        # gate lives on collect_ssid_firewall (once per cycle).
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.MR_SSID_FIREWALL)

        with LogContext(org_id=org_id, network_id=network_id):
            raw_ssids = await asyncio.to_thread(
                self.api.wireless.getNetworkWirelessSsids,
                network_id,
            )
        ssids_data = validate_response_format(
            raw_ssids,
            expected_type=list,
            operation="getNetworkWirelessSsids",
        )

        # Only fetch firewall rules for *enabled* SSIDs (mandatory, not an
        # optimization): call volume here is networks x enabled-SSIDs x 2, so
        # skipping disabled SSIDs (up to 15/network) keeps this bounded.
        enabled_ssids = [
            WirelessSsid.model_validate(raw_ssid)
            for raw_ssid in ssids_data
            if raw_ssid.get("enabled")
        ]

        for ssid in enabled_ssids:
            if ssid.number is None:
                continue

            ssid_name = ssid.name or str(ssid.number)
            base_labels = {
                LabelName.ORG_ID.value: org_id,
                LabelName.NETWORK_ID.value: network_id,
                LabelName.SSID.value: ssid_name,
            }

            try:
                await self._collect_ssid_rules(network_id, str(ssid.number), base_labels, ttl)
            except Exception:
                logger.exception(
                    "Failed to collect SSID firewall rules",
                    org_id=org_id,
                    network_id=network_id,
                    ssid_number=ssid.number,
                )

    async def _collect_ssid_rules(
        self,
        network_id: str,
        ssid_number: str,
        base_labels: dict[str, str],
        ttl: float | None,
    ) -> None:
        """Fetch and emit L3+L7 firewall rule counts for a single SSID.

        Parameters
        ----------
        network_id : str
            Network ID for the wireless network.
        ssid_number : str
            SSID number (0-14) as required by the firewall-rules endpoints.
        base_labels : dict[str, str]
            Shared org/network/ssid labels for every emitted series.
        ttl : float | None
            Fully-resolved per-series TTL for the MR_SSID_FIREWALL group.

        """
        l3_raw = await asyncio.to_thread(
            self.api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules,
            network_id,
            ssid_number,
        )
        l3_data = validate_response_format(
            l3_raw,
            expected_type=dict,
            operation="getNetworkWirelessSsidFirewallL3FirewallRules",
        )
        l3 = WirelessSsidFirewallL3Rules.model_validate(l3_data)

        # The trailing rule is always the built-in default rule; exclude it
        # from the user-defined count (mirrors mx_firewall.py).
        user_l3_rules = [r for r in l3.rules if (r.comment or "") != _DEFAULT_RULE_COMMENT]

        self.parent._set_metric(
            self._ssid_firewall_rules,
            {**base_labels, LabelName.RULE_TYPE.value: "L3"},
            float(len(user_l3_rules)),
            ttl_seconds=ttl,
        )

        if l3.allowLanAccess is not None:
            self.parent._set_metric(
                self._ssid_allow_lan_access,
                base_labels,
                1.0 if l3.allowLanAccess else 0.0,
                ttl_seconds=ttl,
            )

        l7_raw = await asyncio.to_thread(
            self.api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules,
            network_id,
            ssid_number,
        )
        l7_data = validate_response_format(
            l7_raw,
            expected_type=dict,
            operation="getNetworkWirelessSsidFirewallL7FirewallRules",
        )
        l7 = WirelessSsidFirewallL7Rules.model_validate(l7_data)

        self.parent._set_metric(
            self._ssid_firewall_rules,
            {**base_labels, LabelName.RULE_TYPE.value: "L7"},
            float(len(l7.rules)),
            ttl_seconds=ttl,
        )
