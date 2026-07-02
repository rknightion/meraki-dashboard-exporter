"""MX VPN/WAN health collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants.metrics_constants import MXMetricName
from ...core.domain_models import ApplianceVpnStats
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName, create_labels
from ..subcollector_mixin import SubCollectorMixin

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ...core.config import Settings

logger = get_logger(__name__)


class MXVpnCollector(SubCollectorMixin):
    """Collector for MX VPN/WAN health metrics.

    Collects site-to-site VPN peer reachability status at the organization level
    using the getOrganizationApplianceVpnStatuses endpoint. Per-peer performance
    data (usage volume, average latency) is collected separately by
    :meth:`collect_vpn_stats` from the getOrganizationApplianceVpnStats endpoint —
    the statuses endpoint's ``merakiVpnPeers``/``thirdPartyVpnPeers`` items carry
    no latency/jitter/loss fields to parse.
    """

    def __init__(self, parent: Any) -> None:
        """Initialize MX VPN collector.

        Parameters
        ----------
        parent : Any
            Parent collector instance (MXCollector or DeviceCollector) that
            exposes ``_create_gauge``, ``_set_metric``, ``api``, and ``settings``.

        """
        self.parent = parent
        self.api: DashboardAPI = parent.api
        self.settings: Settings = parent.settings
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize VPN-related Prometheus gauge metrics."""
        self._vpn_peer_status = self.parent._create_gauge(
            MXMetricName.MX_VPN_PEER_STATUS,
            "VPN peer reachability status (1=reachable, 0=unreachable)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.PEER_NETWORK_ID,
                LabelName.PEER_TYPE,
            ],
        )
        self._vpn_peers_total = self.parent._create_gauge(
            MXMetricName.MX_VPN_PEERS,
            "Number of VPN peers configured for a network",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        # Historical VPN usage/latency stats (getOrganizationApplianceVpnStats),
        # aggregated per (network, peer network) pair to keep cardinality bounded.
        vpn_stats_labelnames = [
            LabelName.ORG_ID,
            LabelName.ORG_NAME,
            LabelName.NETWORK_ID,
            LabelName.NETWORK_NAME,
            LabelName.PEER_NETWORK_ID,
        ]
        self._vpn_usage_sent_bytes = self.parent._create_gauge(
            MXMetricName.MX_VPN_USAGE_SENT_BYTES,
            "VPN usage sent in bytes over the last 5 minutes, per peer network",
            labelnames=vpn_stats_labelnames,
        )
        self._vpn_usage_recv_bytes = self.parent._create_gauge(
            MXMetricName.MX_VPN_USAGE_RECV_BYTES,
            "VPN usage received in bytes over the last 5 minutes, per peer network",
            labelnames=vpn_stats_labelnames,
        )
        self._vpn_stats_avg_latency_seconds = self.parent._create_gauge(
            MXMetricName.MX_VPN_STATS_AVG_LATENCY_SECONDS,
            "Average VPN latency in seconds to a peer network (5-min avg), averaged across all "
            "sender/receiver uplink combinations",
            labelnames=vpn_stats_labelnames,
        )

    @log_api_call("getOrganizationApplianceVpnStatuses")
    @with_error_handling(
        operation="Collect VPN health metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect(self, org_id: str, org_name: str) -> None:
        """Collect VPN peer status metrics for an organization.

        Fetches the VPN peer status for every network in the organization and
        records per-peer reachability and the total peer count per network.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        vpn_statuses = await asyncio.to_thread(
            self.api.appliance.getOrganizationApplianceVpnStatuses,
            org_id,
            total_pages="all",
        )

        vpn_statuses = validate_response_format(
            vpn_statuses,
            expected_type=list,
            operation="getOrganizationApplianceVpnStatuses",
        )

        # Resolve allowed network IDs for filter enforcement on org-wide responses.
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )
        skipped = 0

        for status in vpn_statuses:
            network_id = status.get("networkId", "")
            network_name = status.get("networkName", network_id)

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            # Combine Meraki and third-party VPN peers
            meraki_peers: list[dict[str, Any]] = status.get("merakiVpnPeers", [])
            third_party_peers: list[dict[str, Any]] = status.get("thirdPartyVpnPeers", [])
            all_peers = meraki_peers + third_party_peers

            # Total peer count for this network
            self.parent._set_metric(
                self._vpn_peers_total,
                {
                    LabelName.ORG_ID: org_id,
                    LabelName.ORG_NAME: org_name,
                    LabelName.NETWORK_ID: network_id,
                    LabelName.NETWORK_NAME: network_name,
                },
                float(len(all_peers)),
            )

            for peer in all_peers:
                # Determine peer identifier and type
                if "networkId" in peer:
                    peer_network_id = peer["networkId"]
                    peer_type = "meraki"
                else:
                    # Third-party peers are identified by their public IP
                    peer_network_id = peer.get("publicIp", "unknown")
                    peer_type = "third_party"

                reachability = peer.get("reachability", "")
                peer_labels = {
                    LabelName.ORG_ID: org_id,
                    LabelName.ORG_NAME: org_name,
                    LabelName.NETWORK_ID: network_id,
                    LabelName.NETWORK_NAME: network_name,
                    LabelName.PEER_NETWORK_ID: peer_network_id,
                    LabelName.PEER_TYPE: peer_type,
                }

                self.parent._set_metric(
                    self._vpn_peer_status,
                    peer_labels,
                    1.0 if reachability == "reachable" else 0.0,
                )

        logger.debug(
            "Collected VPN statuses",
            org_id=org_id,
            network_count=len(vpn_statuses),
            skipped_count=skipped,
        )

    @log_api_call("getOrganizationApplianceVpnStats")
    @with_error_handling(
        operation="Collect VPN usage and latency stats",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_vpn_stats(self, org_id: str, org_name: str) -> None:
        """Collect historical VPN usage and latency stats for an organization.

        Complements :meth:`collect`'s point-in-time VPN peer status with historical
        per-peer-network usage volume (sent/received kilobytes) and average latency
        using the getOrganizationApplianceVpnStats endpoint. To keep cardinality
        bounded, data is aggregated to one series per (network, peer network) pair —
        the sender/receiver uplink cross-product within ``latencySummaries`` is never
        used as a label; instead the average latency across all uplink combinations
        is emitted.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        resp = await asyncio.to_thread(
            self.api.appliance.getOrganizationApplianceVpnStats,
            org_id,
            total_pages="all",
            timespan=300,
        )

        rows = validate_response_format(
            resp,
            expected_type=list,
            operation="getOrganizationApplianceVpnStats",
        )

        # Resolve allowed network IDs for filter enforcement on org-wide responses.
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )
        skipped = 0
        emitted = 0

        for raw_row in rows:
            row = ApplianceVpnStats.model_validate(raw_row)
            network_id = row.networkId
            network_name = row.networkName if row.networkName is not None else network_id

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            for peer in row.merakiVpnPeers:
                peer_id = peer.networkId

                labels = create_labels(
                    org_id=org_id,
                    org_name=org_name,
                    network_id=network_id,
                    network_name=network_name,
                    peer_network_id=peer_id,
                )

                usage = peer.usageSummary

                sent = usage.sentInKilobytes if usage is not None else None
                if sent is not None:
                    self.parent._set_metric(
                        self._vpn_usage_sent_bytes,
                        labels,
                        float(sent) * 1000,
                        MXMetricName.MX_VPN_USAGE_SENT_BYTES.value,
                    )
                    emitted += 1

                received = usage.receivedInKilobytes if usage is not None else None
                if received is not None:
                    self.parent._set_metric(
                        self._vpn_usage_recv_bytes,
                        labels,
                        float(received) * 1000,
                        MXMetricName.MX_VPN_USAGE_RECV_BYTES.value,
                    )
                    emitted += 1

                latency_values = [
                    float(summary.avgLatencyMs)
                    for summary in peer.latencySummaries
                    if summary.avgLatencyMs is not None
                ]
                if latency_values:
                    self.parent._set_metric(
                        self._vpn_stats_avg_latency_seconds,
                        labels,
                        (sum(latency_values) / len(latency_values)) / 1000,
                        MXMetricName.MX_VPN_STATS_AVG_LATENCY_SECONDS.value,
                    )
                    emitted += 1

        logger.debug(
            "Collected MX VPN usage/latency stats",
            org_id=org_id,
            network_count=len(rows),
            skipped_count=skipped,
            emitted_count=emitted,
        )
