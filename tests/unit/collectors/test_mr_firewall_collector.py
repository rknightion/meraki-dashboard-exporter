"""Tests for MR SSID firewall rule count & LAN-access collector (#290)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mr.firewall import MRFirewallCollector
from meraki_dashboard_exporter.core.constants.metrics_constants import MRMetricName
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName

if TYPE_CHECKING:
    pass


def _make_gauge(name: str, description: str, labelnames: list[str]) -> Gauge:
    """Create a real Prometheus Gauge using the enum value as the metric name."""
    return Gauge(name.value if hasattr(name, "value") else name, description, labelnames)


class TestMRFirewallCollector:
    """Test MR SSID firewall rule & LAN-access collector."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock Meraki DashboardAPI client."""
        api = MagicMock()
        api.wireless = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent collector (DeviceCollector) instance."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        # Real int required: collect_ssid_firewall fans out via ManagedTaskGroup,
        # which builds asyncio.Semaphore(max_concurrency).
        parent.settings.api.concurrency_limit = 5
        parent.rate_limiter = None
        # No inventory means no NetworkFilter — collector emits all rows.
        parent.inventory = None
        parent._create_gauge = MagicMock(side_effect=_make_gauge)
        parent._should_run_group = MagicMock(return_value=True)
        parent._group_ttl_seconds = MagicMock(return_value=None)
        parent._mark_group_ran = MagicMock()
        return parent

    @pytest.fixture
    def firewall_collector(self, mock_parent: MagicMock) -> MRFirewallCollector:
        """Create an MRFirewallCollector instance backed by mock parent."""
        return MRFirewallCollector(mock_parent)

    @staticmethod
    def _ssids(*, enabled_numbers: list[int], all_numbers: list[int] | None = None) -> list[dict]:
        numbers = all_numbers or enabled_numbers
        return [
            {"number": n, "name": f"SSID {n}", "enabled": n in enabled_numbers} for n in numbers
        ]

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def test_initialisation_creates_all_metrics(
        self,
        firewall_collector: MRFirewallCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Both firewall gauge metrics must be created during __init__."""
        assert mock_parent._create_gauge.call_count == 2
        created_names = {call.args[0] for call in mock_parent._create_gauge.call_args_list}
        assert MRMetricName.MR_SSID_FIREWALL_RULES in created_names
        assert MRMetricName.MR_SSID_ALLOW_LAN_ACCESS in created_names

    def test_initialisation_stores_parent_api_settings(
        self,
        firewall_collector: MRFirewallCollector,
        mock_parent: MagicMock,
        mock_api: MagicMock,
    ) -> None:
        """Collector should hold references to parent, api, and settings."""
        assert firewall_collector.parent is mock_parent
        assert firewall_collector.api is mock_api
        assert firewall_collector.settings is mock_parent.settings

    # ------------------------------------------------------------------
    # Enabled-only SSID filtering (mandatory, call-volume bound)
    # ------------------------------------------------------------------

    async def test_only_enabled_ssids_fetch_firewall_rules(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Disabled SSIDs must not trigger L3/L7 firewall-rule fetches."""
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(
            return_value=self._ssids(enabled_numbers=[0], all_numbers=[0, 1, 2])
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules = MagicMock(
            return_value={"rules": [], "allowLanAccess": True}
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        assert mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.call_count == 1
        assert mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.call_count == 1
        l3_call = mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.call_args
        assert l3_call.args == ("N_1", "0")

    # ------------------------------------------------------------------
    # L3 rule count / default-rule exclusion
    # ------------------------------------------------------------------

    async def test_l3_rule_count_excludes_default_rule(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """L3 user rule count must exclude the built-in 'Default rule'."""
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(
            return_value=self._ssids(enabled_numbers=[0])
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules = MagicMock(
            return_value={
                "rules": [
                    {"comment": "Allow internal", "policy": "allow", "protocol": "any"},
                    {"comment": "Block telnet", "policy": "deny", "protocol": "tcp"},
                    {"comment": "Default rule", "policy": "allow", "protocol": "any"},
                ],
                "allowLanAccess": True,
            }
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        l3_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._ssid_firewall_rules
            and c[0][1].get("rule_type") == "L3"
        ]
        assert len(l3_calls) == 1
        _, labels, value = l3_calls[0][0]
        assert value == 2.0
        assert labels["network_id"] == "N_1"
        assert labels["org_id"] == "org1"
        assert labels["ssid"] == "SSID 0"

    async def test_l7_rule_count(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """L7 rule count must reflect all rules returned by the API."""
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(
            return_value=self._ssids(enabled_numbers=[0])
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules = MagicMock(
            return_value={"rules": [{"comment": "Default rule", "policy": "allow"}]}
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules = MagicMock(
            return_value={
                "rules": [
                    {"type": "application", "value": "netflix"},
                    {"type": "host", "value": "blocked.example.com"},
                ]
            }
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        l7_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._ssid_firewall_rules
            and c[0][1].get("rule_type") == "L7"
        ]
        assert len(l7_calls) == 1
        _, _, value = l7_calls[0][0]
        assert value == 2.0

    # ------------------------------------------------------------------
    # allowLanAccess
    # ------------------------------------------------------------------

    async def test_allow_lan_access_true_sets_1(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """allowLanAccess: true must emit 1.0."""
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(
            return_value=self._ssids(enabled_numbers=[0])
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules = MagicMock(
            return_value={"rules": [], "allowLanAccess": True}
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        lan_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._ssid_allow_lan_access
        ]
        assert len(lan_calls) == 1
        assert lan_calls[0][0][2] == 1.0

    async def test_allow_lan_access_false_sets_0(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """allowLanAccess: false must emit 0.0."""
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(
            return_value=self._ssids(enabled_numbers=[0])
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules = MagicMock(
            return_value={"rules": [], "allowLanAccess": False}
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        lan_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._ssid_allow_lan_access
        ]
        assert len(lan_calls) == 1
        assert lan_calls[0][0][2] == 0.0

    async def test_allow_lan_access_absent_not_set(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """When allowLanAccess is missing from the response, do not emit a false value."""
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(
            return_value=self._ssids(enabled_numbers=[0])
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        lan_calls = [
            c
            for c in mock_parent._set_metric.call_args_list
            if c[0][0] is firewall_collector._ssid_allow_lan_access
        ]
        assert lan_calls == []

    # ------------------------------------------------------------------
    # Error / empty-response handling
    # ------------------------------------------------------------------

    async def test_l3_error_shape_response_raises_and_emits_nothing_for_ssid(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """The SDK exhausted-retry error shape on L3 must be absorbed, not emit false zeros."""
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(
            return_value=self._ssids(enabled_numbers=[0])
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules = MagicMock(
            return_value={"errors": ["server error, retries exhausted"]}
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        # Should not raise: the per-SSID try/except in collect_for_network absorbs it.
        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        mock_parent._set_metric.assert_not_called()

    async def test_ssids_fetch_error_handled_gracefully(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An error listing SSIDs must not propagate — @with_error_handling absorbs it."""
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(side_effect=Exception("API timeout"))

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        mock_parent._set_metric.assert_not_called()

    async def test_no_enabled_ssids_emits_nothing(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A network with only disabled SSIDs must fetch and emit nothing."""
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(
            return_value=self._ssids(enabled_numbers=[], all_numbers=[0, 1])
        )

        await firewall_collector.collect_for_network("org1", "Test Org", "N_1", "Office")

        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.assert_not_called()
        mock_parent._set_metric.assert_not_called()

    # ------------------------------------------------------------------
    # Org-level fan-out (collect_ssid_firewall)
    # ------------------------------------------------------------------

    async def test_collect_ssid_firewall_skips_non_wireless_networks(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Only networks with 'wireless' in productTypes are fetched."""
        networks = [
            {"id": "net_wireless", "name": "WiFi", "productTypes": ["wireless"]},
            {"id": "net_switch", "name": "Switching", "productTypes": ["switch"]},
        ]
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(
            return_value=self._ssids(enabled_numbers=[0])
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_ssid_firewall("org1", "Test Org", networks)

        assert mock_api.wireless.getNetworkWirelessSsids.call_count == 1
        mock_api.wireless.getNetworkWirelessSsids.assert_called_once_with("net_wireless")

    async def test_collect_ssid_firewall_gate_closed_skips_fetch(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """#617: a closed mr_ssid_firewall gate must skip the fan-out entirely."""
        mock_parent._should_run_group = MagicMock(return_value=False)
        networks = [{"id": "net1", "name": "N1", "productTypes": ["wireless"]}]

        await firewall_collector.collect_ssid_firewall("org1", "Test Org", networks)

        mock_api.wireless.getNetworkWirelessSsids.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_collect_ssid_firewall_marks_group_ran_after_success(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A successful fan-out marks the mr_ssid_firewall group ran exactly once."""
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(
            return_value=self._ssids(enabled_numbers=[0])
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )
        networks = [{"id": "net1", "name": "N1", "productTypes": ["wireless"]}]

        await firewall_collector.collect_ssid_firewall("org1", "Test Org", networks)

        mock_parent._mark_group_ran.assert_called_once_with(EndpointGroupName.MR_SSID_FIREWALL)

    async def test_collect_ssid_firewall_fans_out_multiple_networks(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Every wireless network is fetched (bounded by settings.api.concurrency_limit)."""
        networks = [
            {"id": "net1", "name": "N1", "productTypes": ["wireless"]},
            {"id": "net2", "name": "N2", "productTypes": ["wireless"]},
        ]
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(
            return_value=self._ssids(enabled_numbers=[0])
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules = MagicMock(
            return_value={"rules": []}
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules = MagicMock(
            return_value={"rules": []}
        )

        await firewall_collector.collect_ssid_firewall("org1", "Test Org", networks)

        assert mock_api.wireless.getNetworkWirelessSsids.call_count == 2
        called_network_ids = {
            c.args[0] for c in mock_api.wireless.getNetworkWirelessSsids.call_args_list
        }
        assert called_network_ids == {"net1", "net2"}

    # ------------------------------------------------------------------
    # Domain-model validation (F-023 style)
    # ------------------------------------------------------------------

    def test_firewall_rules_validate_via_domain_model(self) -> None:
        """L3/L7 SSID rule responses are parsed via typed Pydantic domain models."""
        from meraki_dashboard_exporter.core.domain_models import (
            WirelessSsidFirewallL3Rules,
            WirelessSsidFirewallL7Rules,
        )

        l3 = WirelessSsidFirewallL3Rules.model_validate({
            "rules": [
                {"comment": "Allow internal", "policy": "allow"},
                {"comment": "Default rule", "policy": "deny"},
            ],
            "allowLanAccess": True,
        })
        assert l3.allowLanAccess is True
        assert l3.rules[-1].comment == "Default rule"

        l7 = WirelessSsidFirewallL7Rules.model_validate({
            "rules": [{"type": "host", "value": "bad.example.com"}]
        })
        assert len(l7.rules) == 1
        assert l7.rules[0].comment is None
