"""Tests for MX Firewall & Security Policy collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

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
        parent._create_gauge = MagicMock(side_effect=_make_gauge)
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
        """All three firewall gauge metrics must be created during __init__."""
        assert mock_parent._create_gauge.call_count == 3

        created_names = {call.args[0] for call in mock_parent._create_gauge.call_args_list}
        assert MXMetricName.MX_FIREWALL_RULES_TOTAL in created_names
        assert MXMetricName.MX_FIREWALL_DEFAULT_POLICY in created_names
        assert MXMetricName.MX_SECURITY_EVENTS_TOTAL in created_names

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
        assert labels["network_name"] == "Office"
        assert labels["org_id"] == "org1"

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

    async def test_none_response_handled_gracefully(
        self,
        firewall_collector: MXFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """None API responses must not cause an exception."""
        mock_api.appliance.getNetworkApplianceFirewallL3FirewallRules = MagicMock(return_value=None)
        mock_api.appliance.getNetworkApplianceFirewallL7FirewallRules = MagicMock(return_value=None)

        # Should not raise
        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        # Rule counts of 0 should still be recorded
        rule_count_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._firewall_rules_total
        ]
        assert len(rule_count_calls) == 2

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

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
        """org_id, org_name, network_id, network_name must appear in all metric calls."""
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
            assert labels.get("org_name") == "My Organisation"
            assert labels.get("network_id") == "N_99"
            assert labels.get("network_name") == "Branch Office"

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
