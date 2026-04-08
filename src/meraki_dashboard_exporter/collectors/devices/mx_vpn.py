"""MX VPN/WAN health collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants.metrics_constants import MXMetricName
from ...core.error_handling import ErrorCategory, with_error_handling
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName
from ..subcollector_mixin import SubCollectorMixin

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ...core.config import Settings

logger = get_logger(__name__)


class MXVpnCollector(SubCollectorMixin):
    """Collector for MX VPN/WAN health metrics.

    Collects site-to-site VPN peer status and per-peer performance data
    (latency, jitter, packet loss) at the organization level using the
    getOrganizationApplianceVpnStatuses endpoint.
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
        self._vpn_latency_ms = self.parent._create_gauge(
            MXMetricName.MX_VPN_LATENCY_MS,
            "VPN peer round-trip latency in milliseconds",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.PEER_NETWORK_ID,
                LabelName.PEER_TYPE,
            ],
        )
        self._vpn_jitter_ms = self.parent._create_gauge(
            MXMetricName.MX_VPN_JITTER_MS,
            "VPN peer jitter in milliseconds",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.PEER_NETWORK_ID,
                LabelName.PEER_TYPE,
            ],
        )
        self._vpn_packet_loss_ratio = self.parent._create_gauge(
            MXMetricName.MX_VPN_PACKET_LOSS_RATIO,
            "VPN peer packet loss ratio (0.0–1.0)",
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
            MXMetricName.MX_VPN_PEERS_TOTAL,
            "Total number of VPN peers configured for a network",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

    @log_api_call("getOrganizationApplianceVpnStatuses")
    @with_error_handling(
        operation="Collect VPN health metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect(self, org_id: str, org_name: str) -> None:
        """Collect VPN status and performance metrics for an organization.

        Fetches the VPN peer status for every network in the organization and
        records per-peer reachability, latency, jitter, and packet-loss data.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        self._track_api_call("getOrganizationApplianceVpnStatuses")
        vpn_statuses = await asyncio.to_thread(
            self.api.appliance.getOrganizationApplianceVpnStatuses,
            org_id,
            total_pages="all",
        )

        if not isinstance(vpn_statuses, list):
            logger.warning(
                "Unexpected VPN statuses response format",
                org_id=org_id,
                response_type=type(vpn_statuses).__name__,
            )
            return

        for status in vpn_statuses:
            network_id = status.get("networkId", "")
            network_name = status.get("networkName", network_id)

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

                # Performance statistics are nested under usageSummary or directly on the peer
                # depending on the API version; check both locations.
                stats: dict[str, Any] = peer.get("usageSummary", peer)

                latency = stats.get("latencyMs") or stats.get("avgLatencyMs")
                if latency is not None:
                    self.parent._set_metric(
                        self._vpn_latency_ms,
                        peer_labels,
                        float(latency),
                    )

                jitter = stats.get("jitterMs") or stats.get("avgJitterMs")
                if jitter is not None:
                    self.parent._set_metric(
                        self._vpn_jitter_ms,
                        peer_labels,
                        float(jitter),
                    )

                loss = stats.get("lossPercent") or stats.get("avgLossPercent")
                if loss is not None:
                    # Convert from percentage (0–100) to ratio (0.0–1.0)
                    self.parent._set_metric(
                        self._vpn_packet_loss_ratio,
                        peer_labels,
                        float(loss) / 100.0,
                    )

        logger.debug(
            "Collected VPN statuses",
            org_id=org_id,
            network_count=len(vpn_statuses),
        )
