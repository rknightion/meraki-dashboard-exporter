"""Tests for MX Firewall & Security Policy collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mx_firewall import MXFirewallCollector
from meraki_dashboard_exporter.core.constants.metrics_constants import MXMetricName

if TYPE_CHECKING:
    pass


def _make_gauge(name: str, description: str, labelnames: list[str]) -> Gauge:
    """Create a real Prometheus Gauge using the enum value as the metric name."""
    return Gauge(name.value if hasattr(name, "value") else name, description, labelnames)


class TestMXFirewallCollector:
    """Test MX firewall & security policy collector."""

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
        parent._create_gauge = MagicMock(side_effect=_make_gauge)
        # #617: the firewall-config throttle reads its interval from the
        # mx_firewall_config endpoint group via the parent's _group_interval.
        # Default to the 900s floor.
        parent._group_interval = MagicMock(return_value=900)
        parent._group_ttl_seconds = MagicMock(return_value=None)
        parent._should_run_group = MagicMock(return_value=True)
        return parent

    @pytest.fixture
    def firewall_collector(self, mock_parent: MagicMock) -> MXFirewallCollector:
        """Create an MXFirewallCollector instance backed by mock parent."""
        return MXFirewallCollector(mock_parent)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def test_initialisation_creates_all_metrics(
        self,
        firewall_collector: MXFirewallCollector,
        mock_parent: MagicMock,
    ) -> None:
        """All 16 firewall/security/NAT/VLAN gauge metrics must be created during __init__."""
        assert mock_parent._create_gauge.call_count == 16

        created_names = {call.args[0] for call in mock_parent._create_gauge.call_args_list}
        assert MXMetricName.MX_FIREWALL_RULES in created_names
        assert MXMetricName.MX_FIREWALL_DEFAULT_POLICY in created_names
        assert MXMetricName.MX_SECURITY_EVENTS_COUNT in created_names
        # Phase 4 (#285): content filtering / malware / IDS/IPS
        assert MXMetricName.MX_CONTENT_FILTERING_BLOCKED_CATEGORIES in created_names
        assert MXMetricName.MX_CONTENT_FILTERING_BLOCKED_URL_PATTERNS in created_names
        assert MXMetricName.MX_CONTENT_FILTERING_ALLOWED_URL_PATTERNS in created_names
        assert MXMetricName.MX_MALWARE_PROTECTION_ENABLED in created_names
        assert MXMetricName.MX_MALWARE_ALLOWED_URLS in created_names
        assert MXMetricName.MX_MALWARE_ALLOWED_FILES in created_names
        assert MXMetricName.MX_IDS_MODE in created_names
        assert MXMetricName.MX_IDS_RULESET in created_names
        # Phase 4 (#288): port-forwarding / NAT
        assert MXMetricName.MX_PORT_FORWARDING_RULES in created_names
        assert MXMetricName.MX_NAT_RULES in created_names
        # Phase 4 (#289): VLANs / static routes
        assert MXMetricName.MX_VLANS in created_names
        assert MXMetricName.MX_STATIC_ROUTES in created_names
        assert MXMetricName.MX_STATIC_ROUTES_ENABLED in created_names

    def test_initialisation_stores_parent_api_settings(
        self,
        firewall_collector: MXFirewallCollector,
        mock_parent: MagicMock,
        mock_api: MagicMock,
    ) -> None:
        """Collector should hold references to parent, api, and settings."""
        assert firewall_collector.parent is mock_parent
        assert firewall_collector.api is mock_api
        assert firewall_collector.settings is mock_parent.settings

    # ------------------------------------------------------------------
    # L3 rule count
    # ------------------------------------------------------------------

    async def test_l3_rule_count_excludes_default_rule(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """L3 user rule count must exclude the built-in 'Default rule'."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={
                "rules": [
                    {"comment": "Allow internal", "policy": "allow", "protocol": "any"},
                    {"comment": "Block telnet", "policy": "deny", "protocol": "tcp"},
                    {"comment": "Default rule", "policy": "allow", "protocol": "any"},
                ]
            }
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        l3_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._firewall_rules_total
            and c[0][1].get("rule_type") == "L3"
        ]
        assert len(l3_calls) == 1
        _, labels, value = l3_calls[0][0]
        # 2 user rules; default rule excluded
        assert value == 2.0
        assert labels["network_id"] == "N_1"
        assert labels["org_id"] == "org1"
        assert "network_name" not in labels

    async def test_l3_rule_count_no_user_rules(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Only the default rule present should yield a count of 0."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={
                "rules": [
                    {"comment": "Default rule", "policy": "deny", "protocol": "any"},
                ]
            }
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        l3_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._firewall_rules_total
            and c[0][1].get("rule_type") == "L3"
        ]
        assert len(l3_calls) == 1
        _, _, value = l3_calls[0][0]
        assert value == 0.0

    # ------------------------------------------------------------------
    # L7 rule count
    # ------------------------------------------------------------------

    async def test_l7_rule_count(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """L7 rule count must reflect all rules returned by the API."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={
                "rules": [
                    {"comment": "Default rule", "policy": "deny", "protocol": "any"},
                ]
            }
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={
                "rules": [
                    {"type": "application", "value": "netflix"},
                    {"type": "applicationCategory", "value": "gaming"},
                    {"type": "host", "value": "blocked.example.com"},
                ]
            }
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        l7_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._firewall_rules_total
            and c[0][1].get("rule_type") == "L7"
        ]
        assert len(l7_calls) == 1
        _, labels, value = l7_calls[0][0]
        assert value == 3.0
        assert labels["rule_type"] == "L7"

    async def test_l7_rule_count_empty(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An empty L7 rules list should yield a count of 0."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={
                "rules": [
                    {"comment": "Default rule", "policy": "deny", "protocol": "any"},
                ]
            }
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        l7_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._firewall_rules_total
            and c[0][1].get("rule_type") == "L7"
        ]
        assert len(l7_calls) == 1
        _, _, value = l7_calls[0][0]
        assert value == 0.0

    # ------------------------------------------------------------------
    # Default policy detection
    # ------------------------------------------------------------------

    async def test_default_policy_allow_sets_1(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """When the last rule's policy is 'allow', default_policy metric must be 1.0."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={
                "rules": [
                    {"comment": "Default rule", "policy": "allow", "protocol": "any"},
                ]
            }
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        policy_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._firewall_default_policy
        ]
        assert len(policy_calls) == 1
        _, _, value = policy_calls[0][0]
        assert value == 1.0

    async def test_default_policy_deny_sets_0(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """When the last rule's policy is 'deny', default_policy metric must be 0.0."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={
                "rules": [
                    {"comment": "Allow SSH", "policy": "allow", "protocol": "tcp"},
                    {"comment": "Default rule", "policy": "deny", "protocol": "any"},
                ]
            }
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        policy_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._firewall_default_policy
        ]
        assert len(policy_calls) == 1
        _, _, value = policy_calls[0][0]
        assert value == 0.0

    async def test_default_policy_not_set_when_rules_empty(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """When L3 rules list is empty, default_policy metric must not be set."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        policy_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._firewall_default_policy
        ]
        assert len(policy_calls) == 0

    # ------------------------------------------------------------------
    # Empty / missing response handling
    # ------------------------------------------------------------------

    async def test_empty_rules_response(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A response with empty rules lists should still set rule counts to 0."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        rule_count_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._firewall_rules_total
        ]
        # One call for L3, one for L7
        assert len(rule_count_calls) == 2
        for call in rule_count_calls:
            _, _, value = call[0]
            assert value == 0.0

    async def test_none_response_skips_without_false_zeros(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A None (invalid, non-dict) L3 response must be skipped, not emit a false-zero.

        After F-034 the L3/L7 fetch is wrapped in ``validate_response_format`` so a
        non-dict response (None, or the SDK exhausted-retry ``{"errors": [...]}``
        shape) raises internally and is absorbed by ``@with_error_handling`` — the
        cycle emits nothing rather than recording a misleading rule count of 0.
        """
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(return_value=None)
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(return_value=None)

        # Should not raise – the exception is absorbed by the decorator.
        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        # No rule-count series should be emitted for an invalid response shape.
        mock_parent._set_metric.assert_not_called()

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    async def test_l3_error_shape_response_raises_and_emits_nothing(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The SDK exhausted-retry error shape on L3 must raise (F-034), not emit false zeros.

        ``getNetworkApplianceFirewallL3FirewallRules`` returning a dict with an
        ``errors`` key (the retries-exhausted body) must be normalized by
        ``validate_response_format`` into a raised error that ``@with_error_handling``
        absorbs — so the L3/L7 rule counts and default policy are NOT set to a
        misleading 0 for that cycle.
        """
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={"errors": ["server error, retries exhausted"]}
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        # Should not raise – validate_response_format raises internally, and
        # @with_error_handling absorbs it.
        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        # L3 raised before any emission, so nothing (incl. L7) is recorded.
        mock_parent._set_metric.assert_not_called()

    async def test_l7_error_shape_response_raises_and_emits_nothing(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The SDK exhausted-retry error shape on L7 must raise (F-034), not emit a false zero."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={"rules": [{"comment": "Default rule", "policy": "deny"}]}
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={"errors": ["server error, retries exhausted"]}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        # L7 raised, so no L7 rule-count series is emitted for this cycle.
        l7_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._firewall_rules_total
            and c[0][1].get("rule_type") == "L7"
        ]
        assert l7_calls == []

    async def test_l3_api_error_handled_gracefully(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An L3 API exception must not propagate – @with_error_handling absorbs it."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            side_effect=Exception("API timeout")
        )

        # Should not raise
        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        mock_parent._set_metric.assert_not_called()

    async def test_l7_api_error_handled_gracefully(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An L7 API exception after L3 succeeds must not propagate."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={
                "rules": [
                    {"comment": "Default rule", "policy": "deny", "protocol": "any"},
                ]
            }
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            side_effect=Exception("rate limit")
        )

        # Should not raise – the whole method is wrapped by @with_error_handling
        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

    # ------------------------------------------------------------------
    # Label correctness
    # ------------------------------------------------------------------

    async def test_labels_propagated_to_all_rule_metrics(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """org_id and network_id (ID-only, issue #534) must appear in all metric calls."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={
                "rules": [
                    {"comment": "Default rule", "policy": "deny", "protocol": "any"},
                ]
            }
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={"rules": [{"type": "host", "value": "bad.example.com"}]}
        )

        await firewall_collector.collect_for_network(
            "org-xyz", "My Organisation", "N_99", "Branch Office"
        )

        for call in mock_parent._set_metric.call_args_list:
            _, labels, _ = call[0]
            assert labels.get("org_id") == "org-xyz"
            assert labels.get("network_id") == "N_99"
            assert "org_name" not in labels
            assert "network_name" not in labels

    async def test_rule_type_label_l3_and_l7(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """rule_type label must be 'L3' for L3 calls and 'L7' for L7 calls."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={
                "rules": [
                    {"comment": "Default rule", "policy": "allow", "protocol": "any"},
                ]
            }
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        rule_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._firewall_rules_total
        ]
        rule_types = {c[0][1]["rule_type"] for c in rule_calls}
        assert rule_types == {"L3", "L7"}

    # ------------------------------------------------------------------
    # Org-wide security events (getOrganizationApplianceSecurityEvents)
    # ------------------------------------------------------------------

    async def test_security_events_gate_closed_skips_fetch(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A closed mx_security_events gate skips the API call and does not mark (#617)."""
        mock_parent._should_run_group = MagicMock(return_value=False)
        mock_api.appliance.getOrganizationApplianceSecurityEvents = MagicMock(
            return_value=[{"eventType": "IDS Alert", "networkId": "N_1"}]
        )

        await firewall_collector.collect_org_security_events("org1", "Test Org")

        mock_api.appliance.getOrganizationApplianceSecurityEvents.assert_not_called()
        mock_parent._set_metric.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_security_events_marks_group_ran_and_threads_ttl(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A successful security-events fetch marks mx_security_events and threads TTL (#617)."""
        mock_parent._should_run_group = MagicMock(return_value=True)
        mock_parent._group_ttl_seconds = MagicMock(return_value=600.0)
        mock_api.appliance.getOrganizationApplianceSecurityEvents = MagicMock(
            return_value=[{"eventType": "IDS Alert", "networkId": "N_1"}]
        )

        await firewall_collector.collect_org_security_events("org1", "Test Org")

        from meraki_dashboard_exporter.core.scheduler import EndpointGroupName

        mock_parent._mark_group_ran.assert_called_once_with(EndpointGroupName.MX_SECURITY_EVENTS)
        for call in mock_parent._set_metric.call_args_list:
            assert call.kwargs["ttl_seconds"] == 600.0

    async def test_firewall_config_throttle_reads_group_interval(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The firewall-config SLOW throttle sources its interval from the group (#617)."""
        mock_parent._group_interval = MagicMock(return_value=900)
        self._set_l3_l7_responses(mock_api)

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        from meraki_dashboard_exporter.core.scheduler import EndpointGroupName

        mock_parent._group_interval.assert_any_call(EndpointGroupName.MX_FIREWALL_CONFIG)

    async def test_security_events_aggregated_by_event_type(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Events must be aggregated into per-eventType counts."""
        mock_api.appliance.getOrganizationApplianceSecurityEvents = MagicMock(
            return_value=[
                {"eventType": "IDS Alert", "networkId": "N_1", "ts": "2026-07-01T00:00:00Z"},
                {"eventType": "IDS Alert", "networkId": "N_1", "ts": "2026-07-01T00:01:00Z"},
                {"eventType": "File Scanned", "networkId": "N_1", "ts": "2026-07-01T00:02:00Z"},
            ]
        )

        await firewall_collector.collect_org_security_events("org1", "Test Org")

        calls = {
            c[0][1]["event_type"]: c[0][2]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._security_events_count
        }
        assert calls == {"IDS Alert": 2.0, "File Scanned": 1.0}

    async def test_security_events_respects_network_filter(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Events referencing a network outside the filter must be dropped."""
        mock_api.appliance.getOrganizationApplianceSecurityEvents = MagicMock(
            return_value=[
                {"eventType": "IDS Alert", "networkId": "N_INCLUDED"},
                {"eventType": "IDS Alert", "networkId": "N_EXCLUDED"},
                {"eventType": "IDS Alert", "networkId": "N_EXCLUDED"},
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await firewall_collector.collect_org_security_events("org1", "Test Org")

        calls = {
            c[0][1]["event_type"]: c[0][2]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._security_events_count
        }
        # Only the single in-filter event should be counted.
        assert calls == {"IDS Alert": 1.0}

    async def test_security_events_uses_group_interval_as_timespan(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """timespan must be bounded to the solved MX_SECURITY_EVENTS group interval (#631)."""
        from meraki_dashboard_exporter.core.scheduler import EndpointGroupName

        mock_parent._group_interval = MagicMock(return_value=450)
        mock_api.appliance.getOrganizationApplianceSecurityEvents = MagicMock(return_value=[])

        await firewall_collector.collect_org_security_events("org1", "Test Org")

        mock_parent._group_interval.assert_any_call(EndpointGroupName.MX_SECURITY_EVENTS)
        _, kwargs = mock_api.appliance.getOrganizationApplianceSecurityEvents.call_args
        assert kwargs["timespan"] == 450
        assert kwargs["total_pages"] == "all"

    async def test_security_events_empty_response_sets_nothing(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An empty events response must not set any metric.

        It must also NOT wipe the shared gauge: the collector runs once per org
        concurrently, so a global _metrics.clear() would erase every other org's
        series (the F-087 multi-org wipe bug). Stale series are reclaimed by the
        expiration manager instead.
        """
        # Seed a series for another org — a global clear() would wipe it.
        firewall_collector._security_events_count.labels(org_id="org2", event_type="IDS Alert").set(
            3
        )

        mock_api.appliance.getOrganizationApplianceSecurityEvents = MagicMock(return_value=[])

        await firewall_collector.collect_org_security_events("org1", "Test Org")

        assert not any(
            c[0][0] is firewall_collector._security_events_count
            for c in mock_parent._set_metric.call_args_list
        )
        # org2's series must survive org1's empty-response collection.
        assert len(firewall_collector._security_events_count._metrics) == 1

    async def test_security_events_does_not_wipe_other_orgs(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Collecting one org must not clear another org's series on the shared gauge.

        ``mock_parent._set_metric`` is a mock (doesn't write through to the real
        ``Gauge``), so this checks the real gauge is not globally cleared: a series
        pre-seeded for a *different* org must survive org1's collection cycle, and
        the current cycle's event type must still be passed to _set_metric.
        """
        firewall_collector._security_events_count.labels(org_id="org2", event_type="Old Type").set(
            5
        )
        assert len(firewall_collector._security_events_count._metrics) == 1

        mock_api.appliance.getOrganizationApplianceSecurityEvents = MagicMock(
            return_value=[{"eventType": "File Scanned", "networkId": "N_1"}]
        )
        await firewall_collector.collect_org_security_events("org1", "Test Org")

        # org2's series must NOT have been wiped by org1's collection.
        assert len(firewall_collector._security_events_count._metrics) == 1

        # And the new event type must have been passed to _set_metric.
        calls = {
            c[0][1]["event_type"]: c[0][2]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._security_events_count
        }
        assert calls == {"File Scanned": 1.0}

    async def test_security_events_api_error_handled_gracefully(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An API exception must not propagate – @with_error_handling absorbs it."""
        mock_api.appliance.getOrganizationApplianceSecurityEvents = MagicMock(
            side_effect=Exception("connection reset by peer")
        )

        await firewall_collector.collect_org_security_events("org1", "Test Org")

        assert not any(
            c[0][0] is firewall_collector._security_events_count
            for c in mock_parent._set_metric.call_args_list
        )

    async def test_security_events_invalid_response_shape_handled_gracefully(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The SDK exhausted-retry error shape (dict with 'errors') must be handled, not raised."""
        mock_api.appliance.getOrganizationApplianceSecurityEvents = MagicMock(
            return_value={"errors": ["internal server error"]}
        )

        # Should not raise – validate_response_format raises internally, and
        # @with_error_handling absorbs it.
        await firewall_collector.collect_org_security_events("org1", "Test Org")

        assert not any(
            c[0][0] is firewall_collector._security_events_count
            for c in mock_parent._set_metric.call_args_list
        )

    async def test_security_events_org_labels_propagated(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """org_id (ID-only, issue #534) must appear on every emitted series."""
        mock_api.appliance.getOrganizationApplianceSecurityEvents = MagicMock(
            return_value=[{"eventType": "IDS Alert", "networkId": "N_1"}]
        )

        await firewall_collector.collect_org_security_events("org-abc", "My Org")

        calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._security_events_count
        ]
        assert len(calls) == 1
        _, labels, _ = calls[0][0]
        assert labels["org_id"] == "org-abc"
        assert "org_name" not in labels
        assert labels["event_type"] == "IDS Alert"

    async def test_security_events_uses_perpage_1000(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """perPage must be set to the SDK's max (1000) to minimize pagination calls.

        VERIFIED FACT (installed meraki 3.3.0): the SDK docstring for
        getOrganizationApplianceSecurityEvents states ``perPage (integer): ...
        Acceptable range is 3 - 1000. Default is 100.`` Without an explicit
        perPage, a noisy org pages at 100 rows/call -> up to 10x pagination
        calls (F-093).
        """
        mock_api.appliance.getOrganizationApplianceSecurityEvents = MagicMock(return_value=[])

        await firewall_collector.collect_org_security_events("org1", "Test Org")

        _, kwargs = mock_api.appliance.getOrganizationApplianceSecurityEvents.call_args
        assert kwargs["perPage"] == 1000

    async def test_security_events_missing_event_type_defaults_to_unknown(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A row without eventType must be aggregated under 'unknown' rather than dropped."""
        mock_api.appliance.getOrganizationApplianceSecurityEvents = MagicMock(
            return_value=[{"networkId": "N_1"}]
        )

        await firewall_collector.collect_org_security_events("org1", "Test Org")

        calls = {
            c[0][1]["event_type"]: c[0][2]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._security_events_count
        }
        assert calls == {"unknown": 1.0}

    # ------------------------------------------------------------------
    # Firewall-config throttle gating (F-085)
    #
    # collect_for_network is dispatched on every DeviceCollector poll cycle
    # (300s), but the class docstring promises a slower 900s cadence for
    # near-static firewall config. These tests assert the self-enforced gate
    # keyed on the mx_firewall_config endpoint group's solved interval.
    # ------------------------------------------------------------------

    def _set_l3_l7_responses(self, mock_api: MagicMock) -> None:
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(
            return_value={"rules": [{"comment": "Default rule", "policy": "allow"}]}
        )
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

    async def test_firewall_rules_skipped_within_config_interval(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A second call on the very next poll cycle must not hit the API again."""
        self._set_l3_l7_responses(mock_api)

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")
        assert mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules.call_count == 1
        assert mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules.call_count == 1

        # Simulate the very next poll dispatch (well within the config interval).
        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")
        assert mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules.call_count == 1
        assert mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules.call_count == 1

    async def test_firewall_rules_skipped_call_does_not_set_metrics(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A gated (skipped) call must not touch _set_metric at all."""
        self._set_l3_l7_responses(mock_api)

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")
        mock_parent._set_metric.reset_mock()

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")
        mock_parent._set_metric.assert_not_called()

    async def test_firewall_rules_collected_again_after_config_interval_elapses(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Once the config interval has elapsed, the next call must hit the API again."""
        self._set_l3_l7_responses(mock_api)

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx_firewall.time.time",
            return_value=1_000.0,
        ):
            await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")
        assert mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules.call_count == 1

        # Still short of the 900s config interval.
        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx_firewall.time.time",
            return_value=1_000.0 + 300,
        ):
            await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")
        assert mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules.call_count == 1

        # Now past the config interval — must collect again.
        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx_firewall.time.time",
            return_value=1_000.0 + 901,
        ):
            await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")
        assert mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules.call_count == 2

    async def test_firewall_rules_gating_is_per_network(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Gating state must be tracked per network_id, not globally."""
        self._set_l3_l7_responses(mock_api)

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")
        await firewall_collector.collect_for_network("org1", "Test Org", "N_2", "Branch")

        assert mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules.call_count == 2

    async def test_firewall_rules_interval_zero_disables_gating(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A non-positive group interval must disable gating (always collect)."""
        mock_parent._group_interval = MagicMock(return_value=0)
        self._set_l3_l7_responses(mock_api)

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")
        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        assert mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules.call_count == 2

    def test_firewall_rules_validate_via_domain_model(self) -> None:
        """F-023: L3/L7 rule responses are parsed via a typed Pydantic domain model."""
        from meraki_dashboard_exporter.core.domain_models import ApplianceFirewallRules

        parsed = ApplianceFirewallRules.model_validate({
            "rules": [
                {"comment": "Allow internal", "policy": "allow", "protocol": "any"},
                {"comment": "Default rule", "policy": "deny", "protocol": "any"},
            ]
        })

        assert parsed.rules[0].comment == "Allow internal"
        assert parsed.rules[0].policy == "allow"
        assert parsed.rules[-1].comment == "Default rule"

        # L7 rules carry different fields; extras are permitted and count still works.
        l7 = ApplianceFirewallRules.model_validate({
            "rules": [{"type": "host", "value": "bad.example.com"}]
        })
        assert len(l7.rules) == 1

    # ------------------------------------------------------------------
    # #285: content filtering + malware + IDS/IPS config drift
    # ------------------------------------------------------------------

    async def test_content_filtering_counts_emitted(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Content-filtering category/pattern counts must be emitted."""
        mock_api.appliance.getNetworkApplianceContentFiltering = MagicMock(
            return_value={
                "blockedUrlCategories": [{"id": "1", "name": "Gambling"}],
                "blockedUrlPatterns": ["bad.example.com", "worse.example.com"],
                "allowedUrlPatterns": ["good.example.com"],
            }
        )
        mock_api.appliance.getNetworkApplianceSecurityMalware = MagicMock(
            return_value={"mode": "enabled", "allowedUrls": [], "allowedFiles": []}
        )
        mock_api.appliance.getNetworkApplianceSecurityIntrusion = MagicMock(
            return_value={"mode": "prevention", "idsRulesets": "balanced"}
        )

        await firewall_collector.collect_security_config("org1", "N_1")

        calls = {c[0][0]: c[0][2] for c in mock_parent._set_metric.call_args_list}
        assert calls[firewall_collector._content_filtering_blocked_categories] == 1.0
        assert calls[firewall_collector._content_filtering_blocked_url_patterns] == 2.0
        assert calls[firewall_collector._content_filtering_allowed_url_patterns] == 1.0

    async def test_malware_enabled_sets_1(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """mode == 'enabled' must set malware_protection_enabled to 1."""
        mock_api.appliance.getNetworkApplianceContentFiltering = MagicMock(
            return_value={
                "blockedUrlCategories": [],
                "blockedUrlPatterns": [],
                "allowedUrlPatterns": [],
            }
        )
        mock_api.appliance.getNetworkApplianceSecurityMalware = MagicMock(
            return_value={
                "mode": "enabled",
                "allowedUrls": [{"url": "example.com"}],
                "allowedFiles": [{"sha256": "abc"}, {"sha256": "def"}],
            }
        )
        mock_api.appliance.getNetworkApplianceSecurityIntrusion = MagicMock(
            return_value={"mode": "disabled", "idsRulesets": None}
        )

        await firewall_collector.collect_security_config("org1", "N_1")

        calls = {c[0][0]: c[0][2] for c in mock_parent._set_metric.call_args_list}
        assert calls[firewall_collector._malware_protection_enabled] == 1.0
        assert calls[firewall_collector._malware_allowed_urls] == 1.0
        assert calls[firewall_collector._malware_allowed_files] == 2.0

    async def test_malware_disabled_sets_0(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """mode == 'disabled' must set malware_protection_enabled to 0."""
        mock_api.appliance.getNetworkApplianceContentFiltering = MagicMock(
            return_value={
                "blockedUrlCategories": [],
                "blockedUrlPatterns": [],
                "allowedUrlPatterns": [],
            }
        )
        mock_api.appliance.getNetworkApplianceSecurityMalware = MagicMock(
            return_value={"mode": "disabled", "allowedUrls": [], "allowedFiles": []}
        )
        mock_api.appliance.getNetworkApplianceSecurityIntrusion = MagicMock(
            return_value={"mode": "disabled", "idsRulesets": None}
        )

        await firewall_collector.collect_security_config("org1", "N_1")

        calls = {c[0][0]: c[0][2] for c in mock_parent._set_metric.call_args_list}
        assert calls[firewall_collector._malware_protection_enabled] == 0.0

    async def test_malware_400_is_debug_skip_not_error(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A 400/404 from the malware endpoint (no Advanced Security license) must be skipped.

        Content filtering and IDS/IPS must still be collected -- one licensed-feature
        gap must not block the others.
        """
        from meraki.exceptions import APIError

        mock_api.appliance.getNetworkApplianceContentFiltering = MagicMock(
            return_value={
                "blockedUrlCategories": [],
                "blockedUrlPatterns": [],
                "allowedUrlPatterns": [],
            }
        )

        response = MagicMock()
        response.status_code = 400
        response.reason = "Bad Request"
        response.json.return_value = {"errors": ["Advanced Security license required"]}
        error = APIError(
            {"tags": ["configure"], "operation": "getNetworkApplianceSecurityMalware"},
            response,
        )
        mock_api.appliance.getNetworkApplianceSecurityMalware = MagicMock(side_effect=error)
        mock_api.appliance.getNetworkApplianceSecurityIntrusion = MagicMock(
            return_value={"mode": "prevention", "idsRulesets": "balanced"}
        )

        # Should not raise.
        await firewall_collector.collect_security_config("org1", "N_1")

        called_gauges = {c[0][0] for c in mock_parent._set_metric.call_args_list}
        assert firewall_collector._malware_protection_enabled not in called_gauges
        assert firewall_collector._content_filtering_blocked_categories in called_gauges
        assert firewall_collector._ids_mode in called_gauges

    async def test_intrusion_404_is_debug_skip_not_error(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A 404 from the intrusion endpoint must be skipped, not raised."""
        from meraki.exceptions import APIError

        mock_api.appliance.getNetworkApplianceContentFiltering = MagicMock(
            return_value={
                "blockedUrlCategories": [],
                "blockedUrlPatterns": [],
                "allowedUrlPatterns": [],
            }
        )
        mock_api.appliance.getNetworkApplianceSecurityMalware = MagicMock(
            return_value={"mode": "enabled", "allowedUrls": [], "allowedFiles": []}
        )

        response = MagicMock()
        response.status_code = 404
        response.reason = "Not Found"
        response.json.return_value = {"errors": ["not found"]}
        error = APIError(
            {"tags": ["configure"], "operation": "getNetworkApplianceSecurityIntrusion"},
            response,
        )
        mock_api.appliance.getNetworkApplianceSecurityIntrusion = MagicMock(side_effect=error)

        await firewall_collector.collect_security_config("org1", "N_1")

        called_gauges = {c[0][0] for c in mock_parent._set_metric.call_args_list}
        assert firewall_collector._ids_mode not in called_gauges
        assert firewall_collector._ids_ruleset not in called_gauges
        assert firewall_collector._malware_protection_enabled in called_gauges

    async def test_ids_mode_and_ruleset_one_hot_labels(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """IDS mode/ruleset must be emitted as one-hot series with the active value as a label."""
        mock_api.appliance.getNetworkApplianceContentFiltering = MagicMock(
            return_value={
                "blockedUrlCategories": [],
                "blockedUrlPatterns": [],
                "allowedUrlPatterns": [],
            }
        )
        mock_api.appliance.getNetworkApplianceSecurityMalware = MagicMock(
            return_value={"mode": "disabled", "allowedUrls": [], "allowedFiles": []}
        )
        mock_api.appliance.getNetworkApplianceSecurityIntrusion = MagicMock(
            return_value={"mode": "prevention", "idsRulesets": "security"}
        )

        await firewall_collector.collect_security_config("org1", "N_1")

        mode_call = next(
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._ids_mode
        )
        _, labels, value = mode_call[0]
        assert labels["mode"] == "prevention"
        assert value == 1.0

        ruleset_call = next(
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._ids_ruleset
        )
        _, labels, value = ruleset_call[0]
        assert labels["ruleset"] == "security"
        assert value == 1.0

    async def test_security_config_throttled_per_network(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A second call within the group interval must not hit the API again."""
        mock_api.appliance.getNetworkApplianceContentFiltering = MagicMock(
            return_value={
                "blockedUrlCategories": [],
                "blockedUrlPatterns": [],
                "allowedUrlPatterns": [],
            }
        )
        mock_api.appliance.getNetworkApplianceSecurityMalware = MagicMock(
            return_value={"mode": "disabled", "allowedUrls": [], "allowedFiles": []}
        )
        mock_api.appliance.getNetworkApplianceSecurityIntrusion = MagicMock(
            return_value={"mode": "disabled", "idsRulesets": None}
        )

        await firewall_collector.collect_security_config("org1", "N_1")
        await firewall_collector.collect_security_config("org1", "N_1")

        assert mock_api.appliance.getNetworkApplianceContentFiltering.call_count == 1

    async def test_security_config_threads_group_ttl(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """_set_metric calls must carry the mx_security_config group's TTL."""
        mock_parent._group_ttl_seconds = MagicMock(return_value=555.0)
        mock_api.appliance.getNetworkApplianceContentFiltering = MagicMock(
            return_value={
                "blockedUrlCategories": [],
                "blockedUrlPatterns": [],
                "allowedUrlPatterns": [],
            }
        )
        mock_api.appliance.getNetworkApplianceSecurityMalware = MagicMock(
            return_value={"mode": "disabled", "allowedUrls": [], "allowedFiles": []}
        )
        mock_api.appliance.getNetworkApplianceSecurityIntrusion = MagicMock(
            return_value={"mode": "disabled", "idsRulesets": None}
        )

        await firewall_collector.collect_security_config("org1", "N_1")

        for call in mock_parent._set_metric.call_args_list:
            assert call.kwargs["ttl_seconds"] == 555.0

    # ------------------------------------------------------------------
    # #288: port forwarding + NAT rule counts
    # ------------------------------------------------------------------

    async def test_nat_config_counts_emitted(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Port-forwarding and both NAT rule-type counts must be emitted."""
        mock_api.appliance.getNetworkApplianceFirewallPortForwardingRules = MagicMock(
            return_value={"rules": [{"name": "web"}, {"name": "ssh"}]}
        )
        mock_api.appliance.getNetworkApplianceFirewallOneToOneNatRules = MagicMock(
            return_value={"rules": [{"name": "server1"}]}
        )
        mock_api.appliance.getNetworkApplianceFirewallOneToManyNatRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_nat_config("org1", "N_1")

        pf_call = next(
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._port_forwarding_rules
        )
        assert pf_call[0][2] == 2.0

        nat_calls = {
            c[0][1]["nat_type"]: c[0][2]
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._nat_rules
        }
        assert nat_calls == {"1:1": 1.0, "1:many": 0.0}

    async def test_nat_config_empty_arrays_emit_zero(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Empty rule arrays are a normal response and must emit counts of 0."""
        mock_api.appliance.getNetworkApplianceFirewallPortForwardingRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.appliance.getNetworkApplianceFirewallOneToOneNatRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.appliance.getNetworkApplianceFirewallOneToManyNatRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_nat_config("org1", "N_1")

        for call in mock_parent._set_metric.call_args_list:
            assert call[0][2] == 0.0

    async def test_nat_config_throttled_per_network(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A second call within the group interval must not hit the API again."""
        mock_api.appliance.getNetworkApplianceFirewallPortForwardingRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.appliance.getNetworkApplianceFirewallOneToOneNatRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.appliance.getNetworkApplianceFirewallOneToManyNatRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_nat_config("org1", "N_1")
        await firewall_collector.collect_nat_config("org1", "N_1")

        assert mock_api.appliance.getNetworkApplianceFirewallPortForwardingRules.call_count == 1

    async def test_nat_config_api_error_handled_gracefully(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A genuine API exception must not propagate."""
        mock_api.appliance.getNetworkApplianceFirewallPortForwardingRules = MagicMock(
            side_effect=Exception("connection reset")
        )

        await firewall_collector.collect_nat_config("org1", "N_1")

        mock_parent._set_metric.assert_not_called()

    # ------------------------------------------------------------------
    # #289: VLAN + static-route counts
    # ------------------------------------------------------------------

    async def test_vlan_config_counts_emitted(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """VLAN and static-route counts (total + enabled) must be emitted."""
        mock_api.appliance.getNetworkApplianceVlans = MagicMock(
            return_value=[{"id": "1"}, {"id": "2"}, {"id": "3"}]
        )
        mock_api.appliance.getNetworkApplianceStaticRoutes = MagicMock(
            return_value=[
                {"id": "r1", "enabled": True},
                {"id": "r2", "enabled": False},
                {"id": "r3", "enabled": True},
            ]
        )

        await firewall_collector.collect_vlan_config("org1", "N_1")

        calls = {c[0][0]: c[0][2] for c in mock_parent._set_metric.call_args_list}
        assert calls[firewall_collector._vlans_total] == 3.0
        assert calls[firewall_collector._static_routes_total] == 3.0
        assert calls[firewall_collector._static_routes_enabled] == 2.0

    async def test_vlan_config_400_is_debug_skip_not_error(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A 400 from getNetworkApplianceVlans (VLANs not enabled) must be skipped.

        Static routes must still be collected -- the VLAN-disabled condition must
        not block the rest of this method.
        """
        from meraki.exceptions import APIError

        response = MagicMock()
        response.status_code = 400
        response.reason = "Bad Request"
        response.json.return_value = {"errors": ["VLANs are not enabled for this network"]}
        error = APIError(
            {"tags": ["configure"], "operation": "getNetworkApplianceVlans"},
            response,
        )
        mock_api.appliance.getNetworkApplianceVlans = MagicMock(side_effect=error)
        mock_api.appliance.getNetworkApplianceStaticRoutes = MagicMock(
            return_value=[{"id": "r1", "enabled": True}]
        )

        # Should not raise.
        await firewall_collector.collect_vlan_config("org1", "N_1")

        called_gauges = {c[0][0] for c in mock_parent._set_metric.call_args_list}
        assert firewall_collector._vlans_total not in called_gauges
        assert firewall_collector._static_routes_total in called_gauges

    async def test_vlan_config_no_static_routes_emits_zero(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An empty static-routes list must emit total=0 and enabled=0."""
        mock_api.appliance.getNetworkApplianceVlans = MagicMock(return_value=[])
        mock_api.appliance.getNetworkApplianceStaticRoutes = MagicMock(return_value=[])

        await firewall_collector.collect_vlan_config("org1", "N_1")

        calls = {c[0][0]: c[0][2] for c in mock_parent._set_metric.call_args_list}
        assert calls[firewall_collector._vlans_total] == 0.0
        assert calls[firewall_collector._static_routes_total] == 0.0
        assert calls[firewall_collector._static_routes_enabled] == 0.0

    async def test_vlan_config_throttled_per_network(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A second call within the group interval must not hit the API again."""
        mock_api.appliance.getNetworkApplianceVlans = MagicMock(return_value=[])
        mock_api.appliance.getNetworkApplianceStaticRoutes = MagicMock(return_value=[])

        await firewall_collector.collect_vlan_config("org1", "N_1")
        await firewall_collector.collect_vlan_config("org1", "N_1")

        assert mock_api.appliance.getNetworkApplianceVlans.call_count == 1

    async def test_vlan_config_api_error_handled_gracefully(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A genuine (non-400/404) API exception must not propagate."""
        mock_api.appliance.getNetworkApplianceVlans = MagicMock(
            side_effect=Exception("connection reset")
        )
        mock_api.appliance.getNetworkApplianceStaticRoutes = MagicMock(return_value=[])

        await firewall_collector.collect_vlan_config("org1", "N_1")

        mock_parent._set_metric.assert_not_called()

    # ------------------------------------------------------------------
    # collect_for_network dispatches the three new config-drift domains
    # ------------------------------------------------------------------

    async def test_collect_for_network_calls_new_config_domains(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """collect_for_network must also collect security/NAT/VLAN config for the network."""
        self._set_l3_l7_responses(mock_api)
        mock_api.appliance.getNetworkApplianceContentFiltering = MagicMock(
            return_value={
                "blockedUrlCategories": [],
                "blockedUrlPatterns": [],
                "allowedUrlPatterns": [],
            }
        )
        mock_api.appliance.getNetworkApplianceSecurityMalware = MagicMock(
            return_value={"mode": "disabled", "allowedUrls": [], "allowedFiles": []}
        )
        mock_api.appliance.getNetworkApplianceSecurityIntrusion = MagicMock(
            return_value={"mode": "disabled", "idsRulesets": None}
        )
        mock_api.appliance.getNetworkApplianceFirewallPortForwardingRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.appliance.getNetworkApplianceFirewallOneToOneNatRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.appliance.getNetworkApplianceFirewallOneToManyNatRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.appliance.getNetworkApplianceVlans = MagicMock(return_value=[])
        mock_api.appliance.getNetworkApplianceStaticRoutes = MagicMock(return_value=[])

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        called_gauges = {c[0][0] for c in mock_parent._set_metric.call_args_list}
        assert firewall_collector._content_filtering_blocked_categories in called_gauges
        assert firewall_collector._port_forwarding_rules in called_gauges
        assert firewall_collector._vlans_total in called_gauges

    async def test_collect_for_network_new_domains_run_even_when_firewall_gate_closed(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The new config-drift domains must run on their own cadence, decoupled from firewall rules.

        A closed mx_firewall_config gate must not block the independently-gated
        mx_security_config/mx_nat_config/mx_vlan_config domains.
        """
        self._set_l3_l7_responses(mock_api)
        # Prime the firewall-rules throttle so it's closed on the second call.
        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")
        assert mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules.call_count == 1

        mock_api.appliance.getNetworkApplianceContentFiltering = MagicMock(
            return_value={
                "blockedUrlCategories": [{"id": "1"}],
                "blockedUrlPatterns": [],
                "allowedUrlPatterns": [],
            }
        )
        mock_api.appliance.getNetworkApplianceSecurityMalware = MagicMock(
            return_value={"mode": "disabled", "allowedUrls": [], "allowedFiles": []}
        )
        mock_api.appliance.getNetworkApplianceSecurityIntrusion = MagicMock(
            return_value={"mode": "disabled", "idsRulesets": None}
        )
        mock_api.appliance.getNetworkApplianceFirewallPortForwardingRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.appliance.getNetworkApplianceFirewallOneToOneNatRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.appliance.getNetworkApplianceFirewallOneToManyNatRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.appliance.getNetworkApplianceVlans = MagicMock(return_value=[])
        mock_api.appliance.getNetworkApplianceStaticRoutes = MagicMock(return_value=[])

        # Second call: firewall-rules gate is now closed, but the new domains
        # are collected for the first time and must still run.
        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        # Firewall rules must NOT have been re-fetched (gate closed).
        assert mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules.call_count == 1
        # But the new config-drift domains must have run.
        mock_api.appliance.getNetworkApplianceContentFiltering.assert_called_once()
