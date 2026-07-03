"""MX VPN/WAN health collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.async_utils import ManagedTaskGroup
from ...core.constants.device_constants import ProductType
from ...core.constants.metrics_constants import MXMetricName
from ...core.domain_models import ApplianceVpnSiteToSite, ApplianceVpnStats
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName, create_labels
from ...core.scheduler import EndpointGroupName
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
                LabelName.NETWORK_ID,
                LabelName.PEER_NETWORK_ID,
                LabelName.PEER_TYPE,
            ],
        )
        self._vpn_peers_total = self.parent._create_gauge(
            MXMetricName.MX_VPN_PEERS,
            "Number of VPN peers configured for a network",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
            ],
        )

        # Historical VPN usage/latency stats (getOrganizationApplianceVpnStats),
        # aggregated per (network, peer network) pair to keep cardinality bounded.
        vpn_stats_labelnames = [
            LabelName.ORG_ID,
            LabelName.NETWORK_ID,
            LabelName.PEER_NETWORK_ID,
        ]
        self._vpn_usage_sent_bytes = self.parent._create_gauge(
            MXMetricName.MX_VPN_USAGE_SENT_BYTES,
            "VPN usage sent in bytes over the last 15 minutes, per peer network",
            labelnames=vpn_stats_labelnames,
        )
        self._vpn_usage_recv_bytes = self.parent._create_gauge(
            MXMetricName.MX_VPN_USAGE_RECV_BYTES,
            "VPN usage received in bytes over the last 15 minutes, per peer network",
            labelnames=vpn_stats_labelnames,
        )
        self._vpn_stats_avg_latency_seconds = self.parent._create_gauge(
            MXMetricName.MX_VPN_STATS_AVG_LATENCY_SECONDS,
            "Average VPN latency in seconds to a peer network (15-min avg), averaged across all "
            "sender/receiver uplink combinations",
            labelnames=vpn_stats_labelnames,
        )

        # Phase 4 (#287): site-to-site VPN topology config drift.
        self._vpn_site_to_site_mode = self.parent._create_gauge(
            MXMetricName.MX_VPN_SITE_TO_SITE_MODE,
            "Site-to-site VPN mode one-hot indicator (1=active mode for this network)",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID, LabelName.MODE],
        )
        self._vpn_hubs = self.parent._create_gauge(
            MXMetricName.MX_VPN_HUBS,
            "Number of configured VPN hubs for a network (spoke mode)",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID],
        )
        self._vpn_subnets_advertised = self.parent._create_gauge(
            MXMetricName.MX_VPN_SUBNETS_ADVERTISED,
            "Number of local subnets advertised to the site-to-site VPN",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID],
        )

    @log_api_call("getOrganizationApplianceVpnStatuses")
    @with_error_handling(
        operation="Collect VPN health metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect(self, org_id: str, org_name: str, *, due: bool = True) -> None:
        """Collect VPN peer status metrics for an organization.

        Fetches the VPN peer status for every network in the organization and
        records per-peer reachability and the total peer count per network.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        due : bool
            Whether the ``MX_VPN`` group is due this cycle. Computed once by the
            coordinator (``DeviceCollector``) and threaded into both this call
            and :meth:`collect_vpn_stats` — the gate must not be re-evaluated
            here because ``_should_run_group`` mutates the scheduler attempt
            clock, which would suppress the second call mid-cycle (#631).

        """
        # mx_vpn gate (#617): the mx_vpn group covers BOTH this VpnStatuses call
        # and collect_vpn_stats' VpnStats call (cost 2/cycle). Both consult the
        # same ``due`` flag; the run-marker is set only by collect_vpn_stats (the
        # second call each cycle per DeviceCollector._collect_mx_specific_metrics)
        # so marking here would not throttle the pair out mid-cycle.
        if due:
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
            ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MX_VPN)

            for status in vpn_statuses:
                network_id = status.get("networkId", "")

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
                        LabelName.NETWORK_ID: network_id,
                    },
                    float(len(all_peers)),
                    ttl_seconds=ttl_seconds,
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
                        LabelName.NETWORK_ID: network_id,
                        LabelName.PEER_NETWORK_ID: peer_network_id,
                        LabelName.PEER_TYPE: peer_type,
                    }

                    self.parent._set_metric(
                        self._vpn_peer_status,
                        peer_labels,
                        1.0 if reachability == "reachable" else 0.0,
                        ttl_seconds=ttl_seconds,
                    )

            logger.debug(
                "Collected VPN statuses",
                org_id=org_id,
                network_count=len(vpn_statuses),
                skipped_count=skipped,
            )

        # Phase 4 (#287): site-to-site VPN topology, on its own mx_vpn_config
        # cadence (independently gated -- must not be entangled with mx_vpn's
        # cadence above).
        await self.collect_site_to_site_topology(org_id, org_name)

    @log_api_call("getNetworkApplianceVpnSiteToSiteVpn")
    @with_error_handling(
        operation="Collect MX site-to-site VPN topology",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_site_to_site_topology(self, org_id: str, org_name: str) -> None:
        """Collect site-to-site VPN topology config drift for every appliance network (#287).

        Fetches ``getNetworkApplianceVpnSiteToSiteVpn`` per appliance network
        (mode/hubs/advertised-subnets). ``mode: "none"`` is a normal, expected
        response (VPN not configured for that network) and is still emitted as
        a one-hot series, not skipped.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        if not self.parent._should_run_group(EndpointGroupName.MX_VPN_CONFIG):
            return

        if self.parent.inventory is None:
            return

        networks = await self.parent.inventory.get_networks(org_id)
        appliance_networks = [
            n for n in networks if ProductType.APPLIANCE in n.get("productTypes", [])
        ]

        async with ManagedTaskGroup(
            name="mx_vpn_site_to_site_networks",
            max_concurrency=self.settings.api.concurrency_limit,
        ) as group:
            for network in appliance_networks:
                network_id = network.get("id", "")
                if not network_id:
                    continue
                await group.create_task(
                    self._collect_site_to_site_for_network(org_id, network_id),
                    name=f"vpn_site_to_site_{network_id}",
                )

        # Mark ran after the per-network fan-out completes (#617), mirroring
        # MRFirewallCollector.collect_ssid_firewall's gate-once/mark-once pattern.
        self.parent._mark_group_ran(EndpointGroupName.MX_VPN_CONFIG)

        logger.debug(
            "Collected VPN site-to-site topology",
            org_id=org_id,
            network_count=len(appliance_networks),
        )

    @log_api_call("getNetworkApplianceVpnSiteToSiteVpn")
    @with_error_handling(
        operation="Collect MX site-to-site VPN topology for network",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_site_to_site_for_network(self, org_id: str, network_id: str) -> None:
        """Collect site-to-site VPN topology for a single appliance network.

        Parameters
        ----------
        org_id : str
            Organization ID.
        network_id : str
            Network ID for the appliance network.

        """
        response = await asyncio.to_thread(
            self.api.appliance.getNetworkApplianceVpnSiteToSiteVpn,
            network_id,
        )
        data = validate_response_format(
            response,
            expected_type=dict,
            operation="getNetworkApplianceVpnSiteToSiteVpn",
        )
        topology = ApplianceVpnSiteToSite.model_validate(data)

        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MX_VPN_CONFIG)
        base_labels = {
            LabelName.ORG_ID: org_id,
            LabelName.NETWORK_ID: network_id,
        }

        self.parent._set_metric(
            self._vpn_site_to_site_mode,
            {**base_labels, LabelName.MODE: topology.mode},
            1.0,
            ttl_seconds=ttl_seconds,
        )
        self.parent._set_metric(
            self._vpn_hubs,
            base_labels,
            float(len(topology.hubs)),
            ttl_seconds=ttl_seconds,
        )
        self.parent._set_metric(
            self._vpn_subnets_advertised,
            base_labels,
            float(sum(1 for s in topology.subnets if s.useVpn)),
            ttl_seconds=ttl_seconds,
        )

    @log_api_call("getOrganizationApplianceVpnStats")
    @with_error_handling(
        operation="Collect VPN usage and latency stats",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_vpn_stats(self, org_id: str, org_name: str, *, due: bool = True) -> None:
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
        due : bool
            Whether the ``MX_VPN`` group is due this cycle, computed once by the
            coordinator and threaded in (do not re-call ``_should_run_group`` —
            it mutates the scheduler attempt clock).

        """
        # timespan (issue #527): the OpenAPI spec's default for this endpoint is 1 day
        # (86400s), which is far larger than the 300s (5-min) this collector originally
        # requested — evidence/api-conformance.md (APIDEV-06) flagged 300s as liable to
        # return sparse/empty usageSummary/latencySummaries depending on how often Meraki
        # actually rolls up VPN stats internally. No live capture of this endpoint's
        # response exists in evidence/ to confirm/deny sparsity at 300s, so a live check
        # is still recommended. Absent that, 900s (15 minutes) is chosen as the safe
        # documented default: it comfortably covers this collector's own MEDIUM-tier
        # (300s) scrape interval with 3x headroom, matching the widening the issue
        # itself suggests (600 or 900), while staying far short of the spec's 1-day
        # default so the data stays reasonably fresh.
        #
        # mx_vpn gate (#617): second of the two mx_vpn-group calls per cycle (see
        # collect()). Uses the ``due`` flag threaded from the coordinator (do not
        # re-call _should_run_group — it mutates the attempt clock) and sets the
        # run-marker here, after this call succeeds, so the VpnStatuses/VpnStats
        # pair runs together once per solved interval.
        if not due:
            return

        resp = await asyncio.to_thread(
            self.api.appliance.getOrganizationApplianceVpnStats,
            org_id,
            total_pages="all",
            timespan=900,
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
        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MX_VPN)

        for raw_row in rows:
            row = ApplianceVpnStats.model_validate(raw_row)
            network_id = row.networkId

            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            for peer in row.merakiVpnPeers:
                peer_id = peer.networkId

                labels = create_labels(
                    org_id=org_id,
                    network_id=network_id,
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
                        ttl_seconds=ttl_seconds,
                    )
                    emitted += 1

                received = usage.receivedInKilobytes if usage is not None else None
                if received is not None:
                    self.parent._set_metric(
                        self._vpn_usage_recv_bytes,
                        labels,
                        float(received) * 1000,
                        MXMetricName.MX_VPN_USAGE_RECV_BYTES.value,
                        ttl_seconds=ttl_seconds,
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
                        ttl_seconds=ttl_seconds,
                    )
                    emitted += 1

        # Mark after a successful org-wide fetch (failures retry next cycle). This
        # is the second mx_vpn-group call each cycle, so marking here throttles the
        # VpnStatuses/VpnStats pair together on the next cycle.
        self.parent._mark_group_ran(EndpointGroupName.MX_VPN)

        logger.debug(
            "Collected MX VPN usage/latency stats",
            org_id=org_id,
            network_count=len(rows),
            skipped_count=skipped,
            emitted_count=emitted,
        )
