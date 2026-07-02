"""Tests for MX VPN/WAN health collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mx_vpn import MXVpnCollector
from meraki_dashboard_exporter.core.constants.metrics_constants import MXMetricName

if TYPE_CHECKING:
    pass


def _make_gauge(name: str, description: str, labelnames: list[str]) -> Gauge:
    """Create a real Prometheus Gauge using the enum value as the metric name."""
    return Gauge(name.value if hasattr(name, "value") else name, description, labelnames)


class TestMXVpnCollector:
    """Test MX VPN health collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock Meraki DashboardAPI client."""
        api = MagicMock()
        api.appliance = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent collector (MXCollector) instance."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.rate_limiter = None
        # No inventory means no NetworkFilter — collector emits all rows.
        parent.inventory = None
        # _create_gauge returns a real Gauge so metric initialisation works
        parent._create_gauge = MagicMock(side_effect=_make_gauge)
        return parent

    @pytest.fixture
    def vpn_collector(self, mock_parent: MagicMock) -> MXVpnCollector:
        """Create an MXVpnCollector instance backed by mock parent."""
        return MXVpnCollector(mock_parent)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def test_initialisation_creates_all_metrics(
        self,
        vpn_collector: MXVpnCollector,
        mock_parent: MagicMock,
    ) -> None:
        """All five VPN gauge metrics must be created during __init__.

        Note: getOrganizationApplianceVpnStatuses' merakiVpnPeers/thirdPartyVpnPeers
        items carry no latency/jitter/loss fields (per the vendored OpenAPI spec), so
        no gauges are created for those — per-peer performance data instead comes
        from collect_vpn_stats (MX_VPN_USAGE_SENT_BYTES/RECV_BYTES/STATS_AVG_LATENCY_SECONDS).
        """
        assert mock_parent._create_gauge.call_count == 5

        created_names = {call.args[0] for call in mock_parent._create_gauge.call_args_list}
        assert MXMetricName.MX_VPN_PEER_STATUS in created_names
        assert MXMetricName.MX_VPN_PEERS in created_names
        assert MXMetricName.MX_VPN_USAGE_SENT_BYTES in created_names
        assert MXMetricName.MX_VPN_USAGE_RECV_BYTES in created_names
        assert MXMetricName.MX_VPN_STATS_AVG_LATENCY_SECONDS in created_names

    def test_initialisation_stores_parent_api_settings(
        self,
        vpn_collector: MXVpnCollector,
        mock_parent: MagicMock,
        mock_api: MagicMock,
    ) -> None:
        """Collector should hold references to parent, api, and settings."""
        assert vpn_collector.parent is mock_parent
        assert vpn_collector.api is mock_api
        assert vpn_collector.settings is mock_parent.settings

    # ------------------------------------------------------------------
    # Empty / no-op paths
    # ------------------------------------------------------------------

    async def test_collect_empty_response(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An empty list response should not call _set_metric."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(return_value=[])

        await vpn_collector.collect("org1", "Test Org")

        mock_parent._set_metric.assert_not_called()

    async def test_collect_invalid_response_type(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A non-list response should be handled gracefully without raising."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(return_value=None)

        await vpn_collector.collect("org1", "Test Org")

        mock_parent._set_metric.assert_not_called()

    async def test_collect_api_error(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An API exception must not propagate – @with_error_handling absorbs it."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(
            side_effect=Exception("network timeout")
        )

        # Should not raise
        await vpn_collector.collect("org1", "Test Org")

        mock_parent._set_metric.assert_not_called()

    async def test_collect_network_with_no_peers(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A network with no VPN peers should still set peers_total = 0."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "Branch",
                    "merakiVpnPeers": [],
                    "thirdPartyVpnPeers": [],
                }
            ]
        )

        await vpn_collector.collect("org1", "Test Org")

        # Only the peers_total call should be made
        assert mock_parent._set_metric.call_count == 1
        metric, labels, value = mock_parent._set_metric.call_args[0]
        assert metric is vpn_collector._vpn_peers_total
        assert value == 0.0

    # ------------------------------------------------------------------
    # Peer status – reachability mapping
    # ------------------------------------------------------------------

    async def test_reachable_peer_sets_status_1(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A peer with reachability='reachable' must set peer_status = 1."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [
                        {"networkId": "N_2", "reachability": "reachable"},
                    ],
                    "thirdPartyVpnPeers": [],
                }
            ]
        )

        await vpn_collector.collect("org1", "Test Org")

        # Find the _vpn_peer_status call
        status_call = next(
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is vpn_collector._vpn_peer_status
        )
        _, labels, value = status_call[0]
        assert value == 1.0
        assert labels["network_id"] == "N_1"
        assert labels["peer_network_id"] == "N_2"
        assert labels["peer_type"] == "meraki"

    async def test_unreachable_peer_sets_status_0(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A peer with reachability != 'reachable' must set peer_status = 0."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [
                        {"networkId": "N_2", "reachability": "unreachable"},
                    ],
                    "thirdPartyVpnPeers": [],
                }
            ]
        )

        await vpn_collector.collect("org1", "Test Org")

        status_call = next(
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is vpn_collector._vpn_peer_status
        )
        _, labels, value = status_call[0]
        assert value == 0.0

    async def test_missing_reachability_defaults_to_unreachable(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A peer with no reachability field must default to status = 0."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [{"networkId": "N_2"}],
                    "thirdPartyVpnPeers": [],
                }
            ]
        )

        await vpn_collector.collect("org1", "Test Org")

        status_call = next(
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is vpn_collector._vpn_peer_status
        )
        _, _, value = status_call[0]
        assert value == 0.0

    # ------------------------------------------------------------------
    # Peer type classification
    # ------------------------------------------------------------------

    async def test_third_party_peer_type_label(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Third-party peers must have peer_type='third_party' and use publicIp as identifier."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [],
                    "thirdPartyVpnPeers": [
                        {"publicIp": "203.0.113.10", "reachability": "reachable"},
                    ],
                }
            ]
        )

        await vpn_collector.collect("org1", "Test Org")

        status_call = next(
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is vpn_collector._vpn_peer_status
        )
        _, labels, _ = status_call[0]
        assert labels["peer_type"] == "third_party"
        assert labels["peer_network_id"] == "203.0.113.10"

    async def test_third_party_peer_no_public_ip_falls_back_to_unknown(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A third-party peer without publicIp must use 'unknown' as the identifier."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [],
                    "thirdPartyVpnPeers": [
                        {"reachability": "reachable"},
                    ],
                }
            ]
        )

        await vpn_collector.collect("org1", "Test Org")

        status_call = next(
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is vpn_collector._vpn_peer_status
        )
        _, labels, _ = status_call[0]
        assert labels["peer_network_id"] == "unknown"

    # ------------------------------------------------------------------
    # Peers total count
    # ------------------------------------------------------------------

    async def test_peers_total_counts_both_peer_types(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """peers_total must sum Meraki and third-party peers."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [
                        {"networkId": "N_2", "reachability": "reachable"},
                        {"networkId": "N_3", "reachability": "unreachable"},
                    ],
                    "thirdPartyVpnPeers": [
                        {"publicIp": "203.0.113.1", "reachability": "reachable"},
                    ],
                }
            ]
        )

        await vpn_collector.collect("org1", "Test Org")

        total_call = next(
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is vpn_collector._vpn_peers_total
        )
        _, labels, value = total_call[0]
        assert value == 3.0
        assert labels["network_id"] == "N_1"
        assert labels["org_id"] == "org1"

    async def test_peers_total_per_network(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """peers_total must be set separately for each network."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [{"networkId": "N_2", "reachability": "reachable"}],
                    "thirdPartyVpnPeers": [],
                },
                {
                    "networkId": "N_2",
                    "networkName": "Branch",
                    "merakiVpnPeers": [],
                    "thirdPartyVpnPeers": [],
                },
            ]
        )

        await vpn_collector.collect("org1", "Test Org")

        total_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is vpn_collector._vpn_peers_total
        ]
        assert len(total_calls) == 2

        totals_by_network = {c[0][1]["network_id"]: c[0][2] for c in total_calls}
        assert totals_by_network["N_1"] == 1.0
        assert totals_by_network["N_2"] == 0.0

    # ------------------------------------------------------------------
    # Performance data is NOT parsed from getOrganizationApplianceVpnStatuses
    # ------------------------------------------------------------------

    async def test_status_response_extra_fields_are_ignored(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Verify performance fields are never parsed from the statuses response.

        Per the vendored OpenAPI spec, merakiVpnPeers items only ever carry
        networkId/networkName/reachability/priority (thirdPartyVpnPeers only
        name/publicIp/reachability) — no latency/jitter/loss fields exist on this
        endpoint's response. Only peer_status and peers_total should be emitted,
        even if extra unexpected fields are present on a peer.
        """
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [
                        {"networkId": "N_2", "reachability": "reachable", "priority": 1},
                    ],
                    "thirdPartyVpnPeers": [],
                }
            ]
        )

        await vpn_collector.collect("org1", "Test Org")

        set_metrics = {c[0][0] for c in mock_parent._set_metric.call_args_list}
        assert set_metrics == {vpn_collector._vpn_peer_status, vpn_collector._vpn_peers_total}

    # ------------------------------------------------------------------
    # Label correctness
    # ------------------------------------------------------------------

    async def test_org_labels_propagated_to_all_metrics(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """org_id (ID-only, issue #534) must appear in every metric call."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [{"networkId": "N_2", "reachability": "reachable"}],
                    "thirdPartyVpnPeers": [],
                }
            ]
        )

        await vpn_collector.collect("org-abc", "My Org")

        for call in mock_parent._set_metric.call_args_list:
            _, labels, _ = call[0]
            assert labels["org_id"] == "org-abc"
            assert "org_name" not in labels
            assert "network_name" not in labels

    async def test_collect_vpn_statuses_respects_network_filter(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """VPN metrics for excluded networks must be skipped."""
        mock_api.appliance.getOrganizationApplianceVpnStatuses = MagicMock(
            return_value=[
                {
                    "networkId": "N_INCLUDED",
                    "networkName": "Prod",
                    "merakiVpnPeers": [{"networkId": "N_PEER", "reachability": "reachable"}],
                    "thirdPartyVpnPeers": [],
                },
                {
                    "networkId": "N_EXCLUDED",
                    "networkName": "Lab",
                    "merakiVpnPeers": [{"networkId": "N_PEER", "reachability": "reachable"}],
                    "thirdPartyVpnPeers": [],
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await vpn_collector.collect("org-abc", "My Org")

        # No metric for N_EXCLUDED should be emitted.
        for call in mock_parent._set_metric.call_args_list:
            _, labels, _ = call[0]
            assert labels.get("network_id") != "N_EXCLUDED"
        assert any(
            call[0][1].get("network_id") == "N_INCLUDED"
            for call in mock_parent._set_metric.call_args_list
        )


class TestMXVpnStatsCollector:
    """Test MXVpnCollector.collect_vpn_stats (historical usage/latency)."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock Meraki DashboardAPI client."""
        api = MagicMock()
        api.appliance = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent collector (MXCollector) instance."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.rate_limiter = None
        # No inventory means no NetworkFilter — collector emits all rows.
        parent.inventory = None
        # _create_gauge returns a real Gauge so metric initialisation works
        parent._create_gauge = MagicMock(side_effect=_make_gauge)
        return parent

    @pytest.fixture
    def vpn_collector(self, mock_parent: MagicMock) -> MXVpnCollector:
        """Create an MXVpnCollector instance backed by mock parent."""
        return MXVpnCollector(mock_parent)

    async def test_empty_response(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An empty list response should not call _set_metric."""
        mock_api.appliance.getOrganizationApplianceVpnStats = MagicMock(return_value=[])

        await vpn_collector.collect_vpn_stats("org1", "Test Org")

        mock_parent._set_metric.assert_not_called()

    def test_vpn_usage_help_states_window(self, vpn_collector: MXVpnCollector) -> None:
        """MET-09: VPN usage HELP must state the 5-minute data window.

        collect_vpn_stats pins timespan=300 on getOrganizationApplianceVpnStats,
        so the sent/recv usage HELP text (previously just "over the collection
        window") must say 5 minutes explicitly. mx_vpn_stats_avg_latency_seconds
        already states "(5-min avg)" and is intentionally left unchanged.
        """
        sent_doc = vpn_collector._vpn_usage_sent_bytes._documentation.lower()
        recv_doc = vpn_collector._vpn_usage_recv_bytes._documentation.lower()
        assert "5-min" in sent_doc or "5 min" in sent_doc
        assert "5-min" in recv_doc or "5 min" in recv_doc

    async def test_invalid_response_type(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A non-list response should be handled gracefully without raising."""
        mock_api.appliance.getOrganizationApplianceVpnStats = MagicMock(return_value=None)

        await vpn_collector.collect_vpn_stats("org1", "Test Org")

        mock_parent._set_metric.assert_not_called()

    async def test_api_error_absorbed(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An API exception must not propagate – @with_error_handling absorbs it."""
        mock_api.appliance.getOrganizationApplianceVpnStats = MagicMock(
            side_effect=Exception("network timeout")
        )

        await vpn_collector.collect_vpn_stats("org1", "Test Org")

        mock_parent._set_metric.assert_not_called()

    async def test_usage_sent_and_received_emitted(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Usage sent/received bytes (converted from kilobytes ×1000) must be emitted per peer pair."""
        mock_api.appliance.getOrganizationApplianceVpnStats = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [
                        {
                            "networkId": "N_2",
                            "networkName": "Branch",
                            "usageSummary": {
                                "sentInKilobytes": 123.4,
                                "receivedInKilobytes": 567.8,
                            },
                            "latencySummaries": [],
                        }
                    ],
                }
            ]
        )

        await vpn_collector.collect_vpn_stats("org1", "Test Org")

        calls_by_metric = {c[0][0]: c[0] for c in mock_parent._set_metric.call_args_list}

        sent_call = calls_by_metric[vpn_collector._vpn_usage_sent_bytes]
        assert sent_call[2] == pytest.approx(123400.0)
        assert sent_call[1] == {
            "org_id": "org1",
            "network_id": "N_1",
            "peer_network_id": "N_2",
        }

        recv_call = calls_by_metric[vpn_collector._vpn_usage_recv_bytes]
        assert recv_call[2] == pytest.approx(567800.0)

        # No latency samples -> latency metric must not be emitted.
        assert vpn_collector._vpn_stats_avg_latency_seconds not in calls_by_metric

    async def test_latency_averaged_across_summaries(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """avgLatencyMs across multiple latencySummaries entries must be averaged."""
        mock_api.appliance.getOrganizationApplianceVpnStats = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [
                        {
                            "networkId": "N_2",
                            "networkName": "Branch",
                            "usageSummary": None,
                            "latencySummaries": [
                                {
                                    "senderUplink": "wan1",
                                    "receiverUplink": "wan1",
                                    "avgLatencyMs": 10.0,
                                },
                                {
                                    "senderUplink": "wan1",
                                    "receiverUplink": "wan2",
                                    "avgLatencyMs": 20.0,
                                },
                                {
                                    "senderUplink": "wan2",
                                    "receiverUplink": "wan1",
                                    "avgLatencyMs": None,
                                },
                            ],
                        }
                    ],
                }
            ]
        )

        await vpn_collector.collect_vpn_stats("org1", "Test Org")

        latency_call = next(
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is vpn_collector._vpn_stats_avg_latency_seconds
        )
        labels, value = latency_call[0][1], latency_call[0][2]
        # Mean of 10.0 and 20.0 ms (the None entry is ignored) = 15.0 ms = 0.015 s
        assert value == pytest.approx(0.015)
        assert labels["peer_network_id"] == "N_2"
        # Only ONE latency metric emitted per peer pair — no sender x receiver cross product.
        latency_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is vpn_collector._vpn_stats_avg_latency_seconds
        ]
        assert len(latency_calls) == 1

    async def test_null_usage_summary_handled(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A peer with usageSummary=None must not raise and must not emit usage metrics."""
        mock_api.appliance.getOrganizationApplianceVpnStats = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [
                        {
                            "networkId": "N_2",
                            "networkName": "Branch",
                            "usageSummary": None,
                            "latencySummaries": [],
                        }
                    ],
                }
            ]
        )

        await vpn_collector.collect_vpn_stats("org1", "Test Org")

        mock_parent._set_metric.assert_not_called()

    async def test_multiple_peers_emit_separate_series(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Multiple peers under one network must each get their own labelled series."""
        mock_api.appliance.getOrganizationApplianceVpnStats = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "networkName": "HQ",
                    "merakiVpnPeers": [
                        {
                            "networkId": "N_2",
                            "networkName": "Branch1",
                            "usageSummary": {
                                "sentInKilobytes": 10.0,
                                "receivedInKilobytes": 20.0,
                            },
                            "latencySummaries": [{"avgLatencyMs": 5.0}],
                        },
                        {
                            "networkId": "N_3",
                            "networkName": "Branch2",
                            "usageSummary": {
                                "sentInKilobytes": 30.0,
                                "receivedInKilobytes": 40.0,
                            },
                            "latencySummaries": [{"avgLatencyMs": 8.0}],
                        },
                    ],
                }
            ]
        )

        await vpn_collector.collect_vpn_stats("org1", "Test Org")

        sent_calls = {
            c[0][1]["peer_network_id"]: c[0][2]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is vpn_collector._vpn_usage_sent_bytes
        }
        assert sent_calls == {"N_2": pytest.approx(10000.0), "N_3": pytest.approx(30000.0)}

        latency_calls = {
            c[0][1]["peer_network_id"]: c[0][2]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is vpn_collector._vpn_stats_avg_latency_seconds
        }
        assert latency_calls == {"N_2": pytest.approx(0.005), "N_3": pytest.approx(0.008)}

    async def test_network_filter_skips_excluded_network(
        self,
        vpn_collector: MXVpnCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Rows for networks outside the configured filter must be skipped."""
        mock_api.appliance.getOrganizationApplianceVpnStats = MagicMock(
            return_value=[
                {
                    "networkId": "N_INCLUDED",
                    "networkName": "Prod",
                    "merakiVpnPeers": [
                        {
                            "networkId": "N_PEER",
                            "networkName": "Peer",
                            "usageSummary": {
                                "sentInKilobytes": 1.0,
                                "receivedInKilobytes": 2.0,
                            },
                            "latencySummaries": [],
                        }
                    ],
                },
                {
                    "networkId": "N_EXCLUDED",
                    "networkName": "Lab",
                    "merakiVpnPeers": [
                        {
                            "networkId": "N_PEER",
                            "networkName": "Peer",
                            "usageSummary": {
                                "sentInKilobytes": 99.0,
                                "receivedInKilobytes": 99.0,
                            },
                            "latencySummaries": [],
                        }
                    ],
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await vpn_collector.collect_vpn_stats("org1", "My Org")

        for call in mock_parent._set_metric.call_args_list:
            labels = call[0][1]
            assert labels.get("network_id") != "N_EXCLUDED"
        assert any(
            call[0][1].get("network_id") == "N_INCLUDED"
            for call in mock_parent._set_metric.call_args_list
        )


def test_vpn_stats_row_validates_via_domain_model() -> None:
    """F-023: the VPN stats peer row is parsed via a typed Pydantic domain model."""
    from meraki_dashboard_exporter.core.domain_models import ApplianceVpnStats

    row = ApplianceVpnStats.model_validate({
        "networkId": "N_1",
        "networkName": "HQ",
        "merakiVpnPeers": [
            {
                "networkId": "N_2",
                "usageSummary": {"sentInKilobytes": 123.4, "receivedInKilobytes": 567.8},
                "latencySummaries": [{"avgLatencyMs": 10.0}, {"avgLatencyMs": None}],
            }
        ],
    })

    peer = row.merakiVpnPeers[0]
    assert peer.networkId == "N_2"
    assert peer.usageSummary is not None
    assert peer.usageSummary.sentInKilobytes == 123.4
    assert [s.avgLatencyMs for s in peer.latencySummaries] == [10.0, None]
