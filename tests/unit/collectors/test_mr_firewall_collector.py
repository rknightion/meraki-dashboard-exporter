"""Tests for MR SSID firewall rule count & LAN-access collector (#290)."""

from __future__ import annotations

import asyncio
import time
from inspect import signature
from threading import Event
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from meraki.api.wireless import Wireless
from prometheus_client import Gauge
from structlog.testing import capture_logs

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.collectors.devices.mr.firewall import MRFirewallCollector
from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.core.api_facade import MerakiApiFacade
from meraki_dashboard_exporter.core.fanout_cursor import FanoutCursor
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest
from tests.helpers.mock_api import HTTPError

if TYPE_CHECKING:
    pass


async def _no_pacing_delay(*args, **kwargs) -> None:
    """Keep pacer delay out of the independently controlled SDK latency."""


class TestRealFirewallPath(BaseCollectorTest):
    """Exercise the real owner, facade, fetchers and registry with an SDK fake."""

    collector_class = DeviceCollector

    @staticmethod
    def _device_manager(settings, mock_api_builder, allowed, monkeypatch):
        settings.collectors.enabled_collectors = {"device"}
        settings.network_filter.include_ids = allowed
        networks = ["excluded", *allowed]
        api = (
            mock_api_builder
            .with_organizations([{"id": "org", "name": "Org"}])
            .with_networks([
                {"id": network, "name": network, "productTypes": ["wireless"]}
                for network in networks
            ])
            .with_devices(
                [{"serial": "test-ap", "model": "MR46", "networkId": allowed[0]}], org_id="org"
            )
            .build()
        )
        manager = CollectorManager(client=MagicMock(api=api), settings=settings)
        collector = manager.get_collector_by_class_name("DeviceCollector")
        assert isinstance(collector, DeviceCollector)

        monkeypatch.setattr(manager.rate_limiter, "acquire", _no_pacing_delay)
        return api, manager, collector

    @pytest.fixture
    async def sdk_clock(self, monkeypatch):
        """Provide a virtual clock for the synchronous SDK executor.

        Returns ``(pause_sdk, advance)``: ``pause_sdk(latency)`` elapses ``latency``
        virtual seconds while an SDK call is pending, and ``advance(seconds)`` moves
        the clock directly.
        """
        # Keep the real facade timeouts and SDK executor; elapse virtual seconds
        # one timer turn at a time while the synchronous SDK call is pending.
        loop = asyncio.get_running_loop()
        real_time = loop.time
        offset = 0
        monkeypatch.setattr(loop, "time", lambda: real_time() + offset)
        monkeypatch.setattr(
            "meraki_dashboard_exporter.collectors.devices.mr.firewall.monotonic", loop.time
        )

        def advance(seconds: int) -> None:
            nonlocal offset
            offset += seconds

        def pause_sdk(latency: int) -> None:
            complete = Event()

            def tick(remaining: int) -> None:
                if remaining:
                    advance(1)
                    loop.call_soon(tick, remaining - 1)
                else:
                    complete.set()

            loop.call_soon_threadsafe(tick, latency)
            assert complete.wait(2), "virtual SDK clock stopped"

        return pause_sdk, advance

    @pytest.mark.parametrize(("timeout", "sdk_latency"), [(30, 5), (240, 39)])
    async def test_cycle_yields_before_cap_and_resumes_unattempted_networks(
        self,
        settings,
        mock_api_builder,
        isolated_registry,
        monkeypatch,
        sdk_clock,
        timeout,
        sdk_latency,
    ) -> None:
        """Run the manager, device cycle and facade against a latency-controlled SDK."""
        settings.collectors.collector_timeout = timeout
        settings.api.per_fetch_deadline_seconds = timeout // 3
        allowed = [f"net-{n}" for n in range(6)]
        api, manager, collector = self._device_manager(
            settings, mock_api_builder, allowed, monkeypatch
        )
        pause_sdk, advance = sdk_clock
        latency = sdk_latency
        loop = asyncio.get_running_loop()
        discovered: list[str] = []
        sibling_times: list[float] = []

        def discover(network):
            discovered.append(network)
            pause_sdk(latency)
            return [{"number": 0, "name": "guest", "enabled": True}]

        def rules(network, number):
            pause_sdk(latency)
            return {"rules": []}

        def ethernet(*args, **kwargs):
            sibling_times.append(loop.time())
            return []

        api.wireless.getNetworkWirelessSsids.side_effect = discover
        api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.side_effect = rules
        api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.side_effect = rules
        api.wireless.getOrganizationWirelessDevicesEthernetStatuses.side_effect = ethernet

        started = loop.time()
        await manager.run_collector_once(collector)
        health = manager.collector_health["DeviceCollector"]
        assert health["total_successes"] == 1, "firewall consumed the manager's cycle cap"
        # The next group's real SDK fetch is reached while the manager still has time.
        assert len(sibling_times) == 1 and sibling_times[0] - started < timeout - 2
        assert 0 < len(discovered) < len(allowed)
        first = discovered.copy()
        assert set(first) <= set(allowed)
        assert (
            isolated_registry.get_sample_value(
                "meraki_exporter_collector_errors_total",
                {"collector": "DeviceCollector", "error_type": "timeout"},
            )
            is None
        )

        def collected_rules(network):
            return [
                isolated_registry.get_sample_value(
                    "meraki_mr_ssid_firewall_rules",
                    {"org_id": "org", "network_id": network, "ssid": "guest", "rule_type": kind},
                )
                for kind in ("L3", "L7")
            ]

        assert collected_rules(first[0]) == [0, 0]
        latency = 0
        await manager.run_collector_once(collector)
        assert health["total_successes"] == 2
        assert sorted(discovered) == sorted(allowed)
        for network in set(allowed) - set(first):
            assert collected_rules(network) == [0, 0]

        # An interrupted pair was not declared fresh; it can complete after the
        # incomplete-attempt spacing without rediscovering already-fresh networks.
        advance(settings.scheduler.failure_retry_seconds + 1)
        await manager.run_collector_once(collector)
        assert health["total_successes"] == 3
        assert sorted(discovered) == sorted(allowed)
        assert all(collected_rules(network) == [0, 0] for network in allowed)

    async def test_rule_pair_split_across_device_cycles(
        self, settings, mock_api_builder, isolated_registry, monkeypatch, sdk_clock
    ) -> None:
        """Both fetches fit their own deadline, but never fit the same firewall window."""
        settings.collectors.collector_timeout = 30
        settings.api.per_fetch_deadline_seconds = 20
        api, manager, collector = self._device_manager(
            settings, mock_api_builder, ["net"], monkeypatch
        )
        pause_sdk, advance = sdk_clock
        calls = []

        def rules(kind, network, number):
            calls.append((kind, network, number))
            pause_sdk(13)
            return {"rules": []}

        api.wireless.getNetworkWirelessSsids.return_value = [{"number": 0, "enabled": True}]
        api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.side_effect = lambda n, s: rules(
            "L3", n, s
        )
        api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.side_effect = lambda n, s: rules(
            "L7", n, s
        )

        def sample(kind):
            return isolated_registry.get_sample_value(
                "meraki_mr_ssid_firewall_rules",
                {"org_id": "org", "network_id": "net", "ssid": "0", "rule_type": kind},
            )

        await manager.run_collector_once(collector)
        assert calls == [("L3", "net", "0"), ("L7", "net", "0")]
        assert (sample("L3"), sample("L7")) == (0, None)
        calls.clear()
        advance(settings.scheduler.failure_retry_seconds + 1)
        await manager.run_collector_once(collector)
        assert calls == [("L7", "net", "0")]
        assert (sample("L3"), sample("L7")) == (0, 0)
        assert manager.collector_health["DeviceCollector"]["total_successes"] == 2

    @pytest.mark.parametrize(
        ("call_budget", "passes"), [(3, 12), (30, 1)], ids=["bounded", "ample"]
    )
    async def test_sweep_fetches_and_emits_each_enabled_ssid(
        self, collector, mock_api, settings, isolated_registry, call_budget, passes
    ) -> None:
        """Complete the wireless fleet within budget, without fetching disabled SSIDs."""
        # Half of the two-second deadline gives one second of the configured API rate.
        settings.api.per_fetch_deadline_seconds = 2
        settings.api.rate_limit_requests_per_second = call_budget
        settings.api.rate_limit_shared_fraction = 1
        rows = {
            "net-0": [(0, True), (1, True), (2, True), (3, False)],
            "net-1": [(0, True)],
            "net-2": [],
            "net-3": [(0, False), (1, True)],
        }
        networks = [{"id": network, "productTypes": ["wireless"]} for network in rows] + [
            {"id": "wired", "productTypes": ["switch"]}
        ]
        calls: list[tuple[str, str, str]] = []

        def discover(network: str):
            calls.append(("discovery", network, ""))
            return [
                {"number": n, "name": f"ssid-{n}", "enabled": enabled}
                for n, enabled in rows.get(network, ())
            ]

        def l3(network: str, number: str):
            calls.append(("L3", network, number))
            return {"rules": [], "allowLanAccess": True}

        def l7(network: str, number: str):
            calls.append(("L7", network, number))
            return {"rules": []}

        def sdk_call(method, respond):
            # Bind as the installed SDK would, without invoking it or requiring positional calls.
            sdk_signature = signature(method)

            def call(*args, **kwargs):
                bound = sdk_signature.bind(None, *args, **kwargs)
                return respond(*bound.args[1:], **bound.kwargs)

            return call

        for method, respond in (
            (Wireless.getNetworkWirelessSsids, discover),
            (Wireless.getNetworkWirelessSsidFirewallL3FirewallRules, l3),
            (Wireless.getNetworkWirelessSsidFirewallL7FirewallRules, l7),
        ):
            getattr(mock_api.wireless, method.__name__).side_effect = sdk_call(method, respond)
        for _ in range(passes):
            before = len(calls)
            await collector.mr_collector.firewall.collect_ssid_firewall("org", "Org", networks)
            assert len(calls) - before <= call_budget

        expected_rules = {
            (kind, network, str(number))
            for network, number in [
                ("net-0", 0),
                ("net-0", 1),
                ("net-0", 2),
                ("net-1", 0),
                ("net-3", 1),
            ]
            for kind in ("L3", "L7")
        }
        expected_discoveries = [("discovery", network, "") for network in rows]
        assert sorted(calls) == sorted([*expected_discoveries, *expected_rules])
        samples = {
            (sample.labels["network_id"], sample.labels["ssid"], sample.labels["rule_type"])
            for metric in isolated_registry.collect()
            if metric.name == "meraki_mr_ssid_firewall_rules"
            for sample in metric.samples
        }
        assert samples == {
            (network, f"ssid-{number}", kind) for kind, network, number in expected_rules
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

    @pytest.mark.parametrize("status", [402, 404])
    async def test_unavailable_discovery_is_empty_and_quiet(
        self, collector, mock_api, settings, isolated_registry, monkeypatch, status
    ) -> None:
        """Expected unavailability is a normal empty sweep, not a failed retry."""
        now = 100.0
        monkeypatch.setattr(
            "meraki_dashboard_exporter.collectors.devices.mr.firewall.monotonic", lambda: now
        )
        settings.scheduler.failure_retry_seconds = 60
        networks = [{"id": n, "productTypes": ["wireless"]} for n in ("unlicensed", "broken")]
        calls: list[str] = []

        def discover(network):
            calls.append(network)
            if network == "unlicensed":
                raise HTTPError("Feature unavailable", status)
            raise HTTPError(f"Server failure referring to {status}", 500)

        mock_api.wireless.getNetworkWirelessSsids.side_effect = discover
        firewall = collector.mr_collector.firewall
        with capture_logs() as logs:
            await firewall.collect_ssid_firewall("org", "Org", networks)
        assert calls == ["unlicensed", "broken"]
        errors = {
            sample.labels["error_type"]: sample.value
            for metric in isolated_registry.collect()
            if metric.name == "meraki_exporter_collector_errors"
            for sample in metric.samples
            if sample.name == "meraki_exporter_collector_errors_total"
            and sample.labels["collector"] == "DeviceCollector"
        }
        assert errors == {"api_server_error": 1}
        # The inner API logger and the outer sweep must both avoid error noise.
        noisy = [log for log in logs if log["log_level"] in {"error", "warning", "exception"}]
        assert {log.get("network_id") for log in noisy} == {"broken"}
        attempts = MerakiApiFacade.requests_total().collect()[0].samples
        assert any(
            sample.name.endswith("_total")
            and sample.labels
            == {
                "endpoint": "getNetworkWirelessSsids",
                "method": "GET",
                "status_code": str(status),
            }
            and sample.value == 1
            for sample in attempts
        )

        now += 61
        await firewall.collect_ssid_firewall("org", "Org", networks)
        assert calls == ["unlicensed", "broken", "broken"]

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

    async def test_l3_refreshes_while_l7_keeps_failing(
        self, collector, mock_api, settings, isolated_registry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failing L7 endpoint must not stop healthy L3 series from refreshing."""
        now = [100.0]
        monkeypatch.setattr(
            "meraki_dashboard_exporter.collectors.devices.mr.firewall.monotonic", lambda: now[0]
        )
        settings.api.per_fetch_deadline_seconds = 20
        settings.api.rate_limit_requests_per_second = 2
        settings.api.rate_limit_shared_fraction = 1
        networks = [{"id": "net", "productTypes": ["wireless"]}]
        calls: list[str] = []

        mock_api.wireless.getNetworkWirelessSsids.return_value = [
            {"number": 0, "name": "corp", "enabled": True}
        ]

        def l3(network, number):
            calls.append("L3")
            return {"rules": [], "allowLanAccess": True}

        def l7(network, number):
            calls.append("L7")
            raise ValueError("l7 offline")

        mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules.side_effect = l3
        mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules.side_effect = l7
        firewall = collector.mr_collector.firewall
        interval = float(firewall.parent._group_interval(EndpointGroupName.MR_SSID_FIREWALL))

        await firewall.collect_ssid_firewall("org", "Org", networks)
        assert calls == ["L3", "L7"]
        calls.clear()

        # A retry soon after the failure resumes at L7 without repeating L3.
        now[0] += settings.scheduler.failure_retry_seconds + 1
        assert now[0] - 100.0 < interval
        await firewall.collect_ssid_firewall("org", "Org", networks)
        assert calls == ["L7"]
        calls.clear()

        # Once the checkpointed L3 is older than the sweep interval, L3 refreshes
        # again before L7 so its series do not expire behind the L7 failure.
        now[0] += interval + 1
        await firewall.collect_ssid_firewall("org", "Org", networks)
        assert calls == ["L3", "L7"]
        calls.clear()

        # The refreshed L3 checkpoint resumes at L7 again on the next retry.
        now[0] += settings.scheduler.failure_retry_seconds + 1
        await firewall.collect_ssid_firewall("org", "Org", networks)
        assert calls == ["L7"]


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
        parent.ssid_firewall_cutoff = None
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

    @pytest.mark.parametrize("removed", ["network", "ssid"])
    async def test_reappearing_ssid_starts_from_l3(
        self, firewall_collector, mock_api, mock_parent, monkeypatch, removed
    ) -> None:
        """A re-used SSID slot cannot inherit a missing SSID's partial pair."""
        now = 100.0
        monkeypatch.setattr(
            "meraki_dashboard_exporter.collectors.devices.mr.firewall.monotonic", lambda: now
        )
        mock_parent._group_interval.return_value = 10
        networks = [{"id": "net", "productTypes": ["wireless"]}]
        discover = mock_api.wireless.getNetworkWirelessSsids
        l3 = mock_api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules
        l7 = mock_api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules
        discover.return_value = self._ssids(enabled_numbers=[0])
        l3.return_value = {"rules": []}
        l7.side_effect = [TimeoutError(), {"rules": []}, {"rules": []}]
        sweep = firewall_collector.collect_ssid_firewall
        await sweep("org", "Org", networks)
        assert (l3.call_count, l7.call_count) == (1, 1)
        mock_parent._mark_group_ran.assert_not_called()

        now += 11
        discover.return_value = self._ssids(enabled_numbers=[], all_numbers=[0])
        await sweep("org", "Org", [] if removed == "network" else networks)
        assert (l3.call_count, l7.call_count) == (1, 1)

        discover.return_value = self._ssids(enabled_numbers=[0])
        now += 11
        await sweep("org", "Org", networks)
        assert (l3.call_count, l7.call_count) == (2, 2)
        # A completed pair leaves no checkpoint for the next normal refresh either.
        now += 11
        await sweep("org", "Org", networks)
        assert (l3.call_count, l7.call_count) == (3, 3)

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
