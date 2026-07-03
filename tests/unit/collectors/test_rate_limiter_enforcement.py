"""#270: raw SDK call sites must proactively acquire the client-side rate limiter.

Most fetchers are throttled implicitly via the ``@log_api_call`` decorator (which
resolves ``self.rate_limiter``/``self.parent.rate_limiter`` and calls
``rate_limiter.acquire`` before the SDK call). A handful of raw
``asyncio.to_thread(self.api.X.Y, ...)`` sites were previously un-throttled:

* ``MRPerformanceCollector._fetch_network_packet_loss`` (now decorated)
* ``MRPerformanceCollector._process_cpu_load_batch`` (decorator moved here from the
  non-calling ``collect_cpu_load`` wrapper — the wrapper made no direct SDK call, so
  decorating it acquired one token per invocation while N batch calls ran un-throttled;
  moving it also prevents double-acquire)
* ``MTCollector._get_org_name`` inventory-less fallback (explicit, parent-None safe)
* ``MSCollector.collect_stp_priorities``'s nested per-network STP fetch (explicit)

These tests pin that each site acquires the limiter, keyed by the owning org, and that
the CPU-load path acquires exactly once per real API call (no double-acquire).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mr.performance import (
    MRPerformanceCollector,
)
from meraki_dashboard_exporter.collectors.devices.ms import MSCollector
from meraki_dashboard_exporter.collectors.devices.mt import MTCollector


def _limiter() -> MagicMock:
    """Build a rate-limiter stub whose ``acquire`` is an awaitable no-op."""
    limiter = MagicMock()
    limiter.acquire = AsyncMock(return_value=0.0)
    return limiter


def _gauge_parent() -> MagicMock:
    """Parent stub that hands out real gauges and a working ``_set_metric``."""
    parent = MagicMock()
    parent.settings = MagicMock()
    parent.inventory = None
    parent.rate_limiter = _limiter()

    def create_gauge(name, description, labelnames):
        return Gauge(name.value, description, labelnames)

    def set_metric(metric, labels, value, metric_name=None):
        metric.labels(**labels).set(value)

    parent._create_gauge = MagicMock(side_effect=create_gauge)
    parent._set_metric = MagicMock(side_effect=set_metric)
    return parent


# --------------------------------------------------------------------------- #
# MR performance: decorator-covered sites
# --------------------------------------------------------------------------- #


async def test_mr_network_packet_loss_acquires_rate_limiter() -> None:
    """_fetch_network_packet_loss (now @log_api_call) throttles, keyed by org."""
    parent = _gauge_parent()
    parent.api = MagicMock()
    parent.api.wireless.getOrganizationWirelessDevicesPacketLossByNetwork = MagicMock(
        return_value=[]
    )
    collector = MRPerformanceCollector(parent)

    await collector._fetch_network_packet_loss("123456")

    parent.rate_limiter.acquire.assert_awaited_once_with(
        "123456", "getOrganizationWirelessDevicesPacketLossByNetwork"
    )


async def test_mr_cpu_load_acquires_exactly_once_no_double() -> None:
    """collect_cpu_load must acquire once per real batch call, not twice.

    Regression guard: the ``@log_api_call`` decorator now lives on
    ``_process_cpu_load_batch`` (the method that actually calls the SDK), NOT on
    the ``collect_cpu_load`` wrapper. A single batch therefore yields exactly one
    ``acquire`` — proving the wrapper no longer double-throttles.
    """
    parent = _gauge_parent()
    parent.settings.api.batch_size = 20
    parent.api = MagicMock()
    parent.api.wireless.getOrganizationWirelessDevicesSystemCpuLoadHistory = MagicMock(
        return_value=[{"serial": "Q123", "history": [{"load": 12.0}]}]
    )
    collector = MRPerformanceCollector(parent)

    devices = [{"serial": "Q123", "name": "AP1", "model": "MR46", "networkId": "net1"}]
    await collector.collect_cpu_load("123456", "Test Org", devices)

    parent.rate_limiter.acquire.assert_awaited_once_with(
        "123456", "getOrganizationWirelessDevicesSystemCpuLoadHistory"
    )


# --------------------------------------------------------------------------- #
# Explicit-acquire fallbacks
# --------------------------------------------------------------------------- #


async def test_mt_get_org_name_fallback_acquires() -> None:
    """MT _get_org_name direct fallback throttles when inventory has no match."""
    parent = MagicMock()
    parent.api = MagicMock()
    parent.api.organizations.getOrganization = MagicMock(return_value={"name": "OrgName"})
    parent.settings = MagicMock()
    parent.inventory = MagicMock()
    parent.inventory.get_organizations = AsyncMock(return_value=[])  # no cache match
    parent.rate_limiter = _limiter()
    collector = MTCollector(parent)

    name = await collector._get_org_name("123456")

    assert name == "OrgName"
    parent.rate_limiter.acquire.assert_awaited_once_with("123456", "getOrganization")


async def test_mt_get_org_name_standalone_no_limiter() -> None:
    """Standalone MT (parent=None) must not crash resolving the rate limiter."""
    api = MagicMock()
    api.organizations.getOrganization = MagicMock(return_value={"name": "StandaloneOrg"})
    collector = MTCollector.as_standalone(api, MagicMock())

    # parent is None -> no limiter reachable; the guarded getattr must skip acquire
    # rather than raise, and the direct SDK call still returns the org name.
    name = await collector._get_org_name("123456")

    assert name == "StandaloneOrg"


async def test_ms_stp_fetch_acquires_per_network() -> None:
    """The nested per-network STP fetch throttles once per network, keyed by org."""
    parent = MagicMock()
    parent.api = MagicMock()
    parent.settings = MagicMock()
    parent.settings.api.concurrency_limit = 5
    parent.settings.update_intervals.slow = 900
    parent.rate_limiter = _limiter()
    parent.inventory = MagicMock()
    parent.inventory.get_networks = AsyncMock(
        return_value=[
            {"id": "net1", "name": "Net 1", "productTypes": ["switch"]},
            {"id": "net2", "name": "Net 2", "productTypes": ["switch"]},
        ]
    )

    def create_gauge(name, description, labelnames):
        return Gauge(name.value, description, labelnames)

    def set_metric(metric, labels, value, metric_name=None, ttl_seconds=None):
        metric.labels(**labels).set(value)

    parent._create_gauge = MagicMock(side_effect=create_gauge)
    parent._set_metric = MagicMock(side_effect=set_metric)
    # #617 gate helpers: STP self-gates on the MS_STP interval (floor 900s).
    parent._should_run_group = MagicMock(return_value=True)
    parent._mark_group_ran = MagicMock()
    parent._group_interval = MagicMock(return_value=900.0)
    parent._group_ttl_seconds = MagicMock(return_value=None)

    parent.api.switch.getNetworkSwitchStp = MagicMock(
        return_value={"rstpEnabled": True, "stpBridgePriority": []}
    )

    collector = MSCollector(parent)
    collector._last_stp_collection = 0.0  # defeat the interval gate

    await collector.collect_stp_priorities("org123", "Org 123", {})

    assert parent.rate_limiter.acquire.await_count == 2
    for call in parent.rate_limiter.acquire.await_args_list:
        assert call.args == ("org123", "getNetworkSwitchStp")
