"""Tests for MR SSID firewall rule count & LAN-access collector (#290)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.collectors.devices.mr.firewall import MRFirewallCollector
from meraki_dashboard_exporter.core.constants.metrics_constants import MRMetricName
from meraki_dashboard_exporter.core.fanout_cursor import FanoutCursor
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest

if TYPE_CHECKING:
    pass


class TestRealFirewallPath(BaseCollectorTest):
    """Exercise the real owner, facade, fetchers and registry with an SDK fake."""

    collector_class = DeviceCollector

    async def test_bounded_sweep_emits_each_enabled_ssid(
        self, collector, mock_api, settings, isolated_registry
    ) -> None:
        """A budget smaller than the fleet yields every enabled SSID's real metric."""
        settings.api.per_fetch_deadline_seconds = 2
        settings.api.rate_limit_requests_per_second = 3
        settings.api.rate_limit_shared_fraction = 1
        networks = [{"id": f"net-{n}", "productTypes": ["wireless"]} for n in range(4)]
        calls: list[tuple[str, str]] = []

        def discover(network):
            calls.append(("discovery", network))
            count = {"net-0": 3, "net-1": 1, "net-2": 0, "net-3": 1}[network]
            return [{"number": n, "name": f"ssid-{n}", "enabled": True} for n in range(count)]

        def l3(network, number):
            calls.append(("L3", network))
            return {"rules": [], "allowLanAccess": True}

        def l7(network, number):
            calls.append(("L7", network))
            return {"rules": []}

        mock_api.wireless.getNetworkWirelessSsids.side_effect = discover
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.side_effect = l3
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.side_effect = l7
        for _ in range(12):
            before = len(calls)
            await collector.mr_collector.firewall.collect_ssid_firewall("org", "Org", networks)
            assert len(calls) - before <= 3
        samples = {
            (sample.labels["network_id"], sample.labels["ssid"], sample.labels["rule_type"])
            for metric in isolated_registry.collect()
            if metric.name == "meraki_mr_ssid_firewall_rules"
            for sample in metric.samples
        }
        assert samples == {
            (network, ssid, kind)
            for network, ssid in [
                ("net-0", "ssid-0"),
                ("net-0", "ssid-1"),
                ("net-0", "ssid-2"),
                ("net-1", "ssid-0"),
                ("net-3", "ssid-0"),
            ]
            for kind in ("L3", "L7")
        }

    @pytest.mark.parametrize(
        ("failed_stage", "error_type"), [("discovery", "timeout"), ("rules", "api_rate_limit")]
    )
    async def test_failed_item_records_owner_error_and_healthy_sibling_progresses(
        self, collector, mock_api, settings, isolated_registry, failed_stage, error_type
    ) -> None:
        """A swallowed item failure remains visible without starving other networks."""
        settings.api.per_fetch_deadline_seconds = 2
        settings.api.rate_limit_requests_per_second = 10
        settings.api.rate_limit_shared_fraction = 1
        networks = [{"id": n, "productTypes": ["wireless"]} for n in ("bad", "good")]

        class ThrottledError(Exception):
            status = 429

        def discover(network):
            if network == "bad" and failed_stage == "discovery":
                raise TimeoutError("fetch timed out")
            return [{"number": 0, "name": "guest", "enabled": True}]

        def l3(network, number):
            if network == "bad" and failed_stage == "rules":
                raise ThrottledError("busy")
            return {"rules": []}

        mock_api.wireless.getNetworkWirelessSsids.side_effect = discover
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.side_effect = l3
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.return_value = {"rules": []}
        await collector.mr_collector.firewall.collect_ssid_firewall("org", "Org", networks)
        assert (
            isolated_registry.get_sample_value(
                "meraki_mr_ssid_firewall_rules",
                {"org_id": "org", "network_id": "good", "ssid": "guest", "rule_type": "L7"},
            )
            == 0
        )
        assert (
            isolated_registry.get_sample_value(
                "meraki_exporter_collector_errors_total",
                {"collector": "DeviceCollector", "error_type": error_type},
            )
            == 1
        )

    async def test_fetch_deadline_isolated_from_healthy_sibling(
        self, collector, mock_api, settings, isolated_registry
    ) -> None:
        """A slow first fetch times out per item rather than aborting the sweep."""
        settings.api.per_fetch_deadline_seconds = 1
        settings.api.rate_limit_requests_per_second = 10
        settings.api.rate_limit_shared_fraction = 1

        def discover(network):
            if network == "bad":
                time.sleep(1.2)
            return [{"number": 0, "name": "guest", "enabled": True}]

        mock_api.wireless.getNetworkWirelessSsids.side_effect = discover
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.return_value = {"rules": []}
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.return_value = {"rules": []}
        networks = [{"id": n, "productTypes": ["wireless"]} for n in ("bad", "good")]
        await collector.mr_collector.firewall.collect_ssid_firewall("org", "Org", networks)
        assert (
            isolated_registry.get_sample_value(
                "meraki_exporter_collector_errors_total",
                {"collector": "DeviceCollector", "error_type": "timeout"},
            )
            == 1
        )
        assert (
            isolated_registry.get_sample_value(
                "meraki_mr_ssid_firewall_rules",
                {"org_id": "org", "network_id": "good", "ssid": "guest", "rule_type": "L7"},
            )
            == 0
        )

    async def test_planning_work_scales_with_fleet_not_fleet_times_budget(
        self, collector, mock_api, settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Count real cursor inputs while a large first sweep makes bounded progress."""
        settings.api.per_fetch_deadline_seconds = 20
        settings.api.rate_limit_requests_per_second = 3
        settings.api.rate_limit_shared_fraction = 1
        networks = [{"id": f"net-{n}", "productTypes": ["wireless"]} for n in range(40)]
        mock_api.wireless.getNetworkWirelessSsids.return_value = [{"number": 0, "enabled": True}]
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.return_value = {"rules": []}
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.return_value = {"rules": []}
        original = FanoutCursor.select
        scanned = [0]

        def count_select(cursor, keys, **kwargs):
            scanned[0] += len(keys)
            return original(cursor, keys, **kwargs)

        monkeypatch.setattr(FanoutCursor, "select", count_select)
        await collector.mr_collector.firewall.collect_ssid_firewall("org", "Org", networks)
        assert mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.call_count > 0
        assert scanned[0] <= 2 * len(networks) + 30

    async def test_failed_refresh_does_not_renew_stale_rules(
        self, collector, mock_api, settings, isolated_registry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed refresh blocks stale rules until discovery recovers with changed SSIDs."""
        now = [100.0]
        monkeypatch.setattr(
            "meraki_dashboard_exporter.collectors.devices.mr.firewall.monotonic", lambda: now[0]
        )
        settings.api.per_fetch_deadline_seconds = 20
        settings.api.rate_limit_requests_per_second = 2
        settings.api.rate_limit_shared_fraction = 1
        networks = [{"id": n, "productTypes": ["wireless"]} for n in ("bad", "good")]
        mode = ["initial"]
        calls: list[tuple[str, str, str]] = []

        def discover(network):
            calls.append(("discovery", network, ""))
            if network == "bad" and mode[0] == "failed":
                raise ValueError("offline")
            if network == "bad" and mode[0] == "recovered":
                return [
                    {"number": 0, "name": "old", "enabled": False},
                    {"number": 1, "name": "new", "enabled": True},
                ]
            return [{"number": 0, "name": "old", "enabled": True}]

        def l3(network, number):
            calls.append(("L3", network, number))
            return {"rules": [], "allowLanAccess": True}

        def l7(network, number):
            calls.append(("L7", network, number))
            return {"rules": []}

        mock_api.wireless.getNetworkWirelessSsids.side_effect = discover
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.side_effect = l3
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.side_effect = l7
        firewall = collector.mr_collector.firewall
        await firewall.collect_ssid_firewall("org", "Org", networks)
        assert ("L7", "bad", "0") in calls
        calls.clear()
        mode[0] = "failed"
        now[0] += 901
        await firewall.collect_ssid_firewall("org", "Org", networks)
        await firewall.collect_ssid_firewall("org", "Org", networks)
        assert ("discovery", "bad", "") in calls
        assert not any(kind in {"L3", "L7"} and network == "bad" for kind, network, _ in calls)
        assert ("L7", "good", "0") in calls
        calls.clear()
        mode[0] = "recovered"
        now[0] += 301
        await firewall.collect_ssid_firewall("org", "Org", networks)
        assert ("L7", "bad", "1") in calls
        assert ("L7", "bad", "0") not in calls
        assert (
            isolated_registry.get_sample_value(
                "meraki_mr_ssid_firewall_rules",
                {"org_id": "org", "network_id": "bad", "ssid": "new", "rule_type": "L7"},
            )
            == 0
        )


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

    async def test_budgeted_sweep_resumes_across_networks_and_ssids(
        self, firewall_collector: MRFirewallCollector, mock_api: MagicMock, mock_parent: MagicMock
    ) -> None:
        """A small raw-call budget still reaches each enabled SSID over successive wakes."""
        mock_parent.settings.api.per_fetch_deadline_seconds = 2
        mock_parent.settings.api.rate_limit_requests_per_second = 3
        mock_parent.settings.api.rate_limit_shared_fraction = 1
        mock_parent._group_interval.return_value = 900
        networks = [{"id": f"net-{n}", "productTypes": ["wireless"]} for n in range(4)] + [
            {"id": "wired", "productTypes": ["switch"]}
        ]
        rows = {
            "net-0": self._ssids(enabled_numbers=[0, 1, 2], all_numbers=[0, 1, 2, 3]),
            "net-1": self._ssids(enabled_numbers=[0]),
            "net-2": [],
            "net-3": self._ssids(enabled_numbers=[1], all_numbers=[0, 1]),
        }
        calls: list[tuple[str, str, str]] = []

        def discover(network: str) -> list[dict]:
            calls.append(("discovery", network, ""))
            return rows[network]

        def rules(kind: str, network: str, number: str) -> dict:
            calls.append((kind, network, number))
            return {"rules": []}

        mock_api.wireless.getNetworkWirelessSsids.side_effect = discover
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.side_effect = (
            lambda network, number: rules("L3", network, number)
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.side_effect = (
            lambda network, number: rules("L7", network, number)
        )
        for _ in range(12):
            before = len(calls)
            await firewall_collector.collect_ssid_firewall("org", "Org", networks)
            assert len(calls) - before <= 3

        assert {(network, number) for kind, network, number in calls if kind == "L7"} == {
            ("net-0", "0"),
            ("net-0", "1"),
            ("net-0", "2"),
            ("net-1", "0"),
            ("net-3", "1"),
        }
        assert {network for kind, network, _ in calls if kind == "discovery"} == set(rows)

    async def test_one_call_floor_and_refresh_disabled_ssid(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The one-item floor permits a pair, not discovery plus a pair; refresh removes disabled keys."""
        now = [100.0]
        monkeypatch.setattr(
            "meraki_dashboard_exporter.collectors.devices.mr.firewall.monotonic",
            lambda: now[0],
            raising=False,
        )
        mock_parent.settings.api.per_fetch_deadline_seconds = 1
        mock_parent.settings.api.rate_limit_requests_per_second = 1
        mock_parent.settings.api.rate_limit_shared_fraction = 1
        mock_parent._group_interval.return_value = 10
        networks = [{"id": "net-0", "productTypes": ["wireless"]}]
        enabled = [True]
        calls: list[str] = []

        def discover(network: str) -> list[dict]:
            calls.append("discovery")
            return [{"number": 0, "name": "guest", "enabled": enabled[0]}]

        def rules(kind: str, network: str, number: str) -> dict:
            calls.append(kind)
            return {"rules": []}

        mock_api.wireless.getNetworkWirelessSsids.side_effect = discover
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.side_effect = lambda n, s: (
            rules("L3", n, s)
        )
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.side_effect = lambda n, s: (
            rules("L7", n, s)
        )
        for _ in range(2):
            before = len(calls)
            await firewall_collector.collect_ssid_firewall("org", "Org", networks)
            attempt = calls[before:]
            assert attempt in (["discovery"], ["L3", "L7"])
        assert calls == ["discovery", "L3", "L7"]

        enabled[0] = False
        now[0] += 11
        await firewall_collector.collect_ssid_firewall("org", "Org", networks)
        await firewall_collector.collect_ssid_firewall("org", "Org", networks)
        assert calls == ["discovery", "L3", "L7", "discovery"]

    async def test_failed_items_do_not_starve_siblings_and_retry(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Failures consume allowance but other networks progress, then retries recover."""
        now = [100.0]
        monkeypatch.setattr(
            "meraki_dashboard_exporter.collectors.devices.mr.firewall.monotonic",
            lambda: now[0],
            raising=False,
        )
        mock_parent.settings.api.per_fetch_deadline_seconds = 1
        mock_parent.settings.api.rate_limit_requests_per_second = 1
        mock_parent.settings.api.rate_limit_shared_fraction = 1
        mock_parent.settings.scheduler.failure_retry_seconds = 5
        mock_parent._group_interval.return_value = 100
        networks = [{"id": n, "productTypes": ["wireless"]} for n in ("bad", "good")]
        broken = [True]
        calls: list[tuple[str, str]] = []

        def discover(network: str) -> list[dict]:
            calls.append(("discover", network))
            if network == "bad" and broken[0]:
                raise ValueError("offline")
            return [{"number": 0, "enabled": True}]

        def l3(network: str, number: str) -> dict:
            calls.append(("L3", network))
            return {"rules": []}

        def l7(network: str, number: str) -> dict:
            calls.append(("L7", network))
            return {"rules": []}

        mock_api.wireless.getNetworkWirelessSsids.side_effect = discover
        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.side_effect = l3
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.side_effect = l7
        for _ in range(3):
            before = len(calls)
            await firewall_collector.collect_ssid_firewall("org", "Org", networks)
            assert len(calls) - before <= 2
            now[0] += 6
        assert ("L7", "good") in calls
        assert calls.count(("discover", "bad")) == 1
        broken[0] = False
        now[0] += 6
        for _ in range(2):
            await firewall_collector.collect_ssid_firewall("org", "Org", networks)
        assert ("L7", "bad") in calls

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

        await firewall_collector.collect_ssid_firewall(
            "org1", "Test Org", [{"id": "N_1", "productTypes": ["wireless"]}]
        )

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

        await firewall_collector.collect_ssid_firewall(
            "org1", "Test Org", [{"id": "N_1", "productTypes": ["wireless"]}]
        )

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

        await firewall_collector.collect_ssid_firewall(
            "org1", "Test Org", [{"id": "N_1", "productTypes": ["wireless"]}]
        )

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

        await firewall_collector.collect_ssid_firewall(
            "org1", "Test Org", [{"id": "N_1", "productTypes": ["wireless"]}]
        )

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

        await firewall_collector.collect_ssid_firewall(
            "org1", "Test Org", [{"id": "N_1", "productTypes": ["wireless"]}]
        )

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

        await firewall_collector.collect_ssid_firewall(
            "org1", "Test Org", [{"id": "N_1", "productTypes": ["wireless"]}]
        )

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

        # Should not raise: the per-SSID failure is isolated.
        await firewall_collector.collect_ssid_firewall(
            "org1", "Test Org", [{"id": "N_1", "productTypes": ["wireless"]}]
        )

        mock_parent._set_metric.assert_not_called()

    async def test_ssids_fetch_error_handled_gracefully(
        self,
        firewall_collector: MRFirewallCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An error listing SSIDs must not propagate — @with_error_handling absorbs it."""
        mock_api.wireless.getNetworkWirelessSsids = MagicMock(side_effect=Exception("API timeout"))

        await firewall_collector.collect_ssid_firewall(
            "org1", "Test Org", [{"id": "N_1", "productTypes": ["wireless"]}]
        )

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

        await firewall_collector.collect_ssid_firewall(
            "org1", "Test Org", [{"id": "N_1", "productTypes": ["wireless"]}]
        )

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
        """A disabled or shed group must skip the self-paced fan-out entirely."""
        mock_parent.scheduler.is_enabled.return_value = False
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
