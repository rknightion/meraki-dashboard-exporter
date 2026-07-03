"""Scheduler-gate mark_ran semantics for MR sub-collectors (#629).

Canonical rule (#629): an endpoint group is marked ran iff the cycle achieved
>=1 SUCCESSFUL fetch for that group.

- Total failure (every sub-fetch errors) => group NOT marked => gate stays open
  so the next cycle retries.
- Partial fan-out success (>=1 sub-fetch succeeds) => group marked.
- A successful fetch returning an empty list is a successful cycle => marked.

Covered sites (all in ``devices/mr``):
- ``MRClientsCollector.collect_connection_stats``  (MR_CONNECTION_STATS)
- ``MRPerformanceCollector.collect_cpu_load``      (MR_CPU_LOAD)
- ``MRPerformanceCollector.collect_packet_loss``   (MR_PACKET_LOSS)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from meraki_dashboard_exporter.collectors.devices.mr.clients import MRClientsCollector
from meraki_dashboard_exporter.collectors.devices.mr.performance import (
    MRPerformanceCollector,
)
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName


def _make_parent() -> MagicMock:
    """Build a minimal mock DeviceCollector parent for an MR sub-collector.

    ``_should_run_group`` returns True (gate open), the mark/ttl/set helpers are
    spies, and ``inventory`` is None so no NetworkFilter narrowing runs.
    """
    parent = MagicMock()
    parent.api = MagicMock()
    parent.api.wireless = MagicMock()
    parent.settings = MagicMock()
    parent.settings.api.batch_size = 20
    parent.inventory = None
    parent.rate_limiter = None
    parent._should_run_group = MagicMock(return_value=True)
    parent._group_ttl_seconds = MagicMock(return_value=600.0)
    parent._mark_group_ran = MagicMock()
    parent._set_metric = MagicMock()
    parent._create_gauge = MagicMock(side_effect=lambda *a, **k: MagicMock())
    return parent


# --------------------------------------------------------------------------- #
# MR_CONNECTION_STATS (clients.py)
# --------------------------------------------------------------------------- #

_WIRELESS_NETS = [
    {"id": "N1", "name": "net1", "productTypes": ["wireless"]},
    {"id": "N2", "name": "net2", "productTypes": ["wireless"]},
]


async def test_connection_stats_total_failure_does_not_mark_ran() -> None:
    """Every network's connection-stats fetch errors => group NOT marked ran."""
    parent = _make_parent()
    parent.api.wireless.getNetworkWirelessDevicesConnectionStats.side_effect = Exception(
        "boom"
    )
    collector = MRClientsCollector(parent)

    await collector.collect_connection_stats("org1", "Org", _WIRELESS_NETS, {})

    marked = [c.args[0] for c in parent._mark_group_ran.call_args_list]
    assert EndpointGroupName.MR_CONNECTION_STATS not in marked


async def test_connection_stats_partial_success_marks_ran() -> None:
    """One network succeeds (empty), one errors => group marked ran once."""
    parent = _make_parent()
    parent.api.wireless.getNetworkWirelessDevicesConnectionStats.side_effect = [
        [],  # N1 succeeds (empty)
        Exception("boom"),  # N2 fails
    ]
    collector = MRClientsCollector(parent)

    await collector.collect_connection_stats("org1", "Org", _WIRELESS_NETS, {})

    parent._mark_group_ran.assert_called_once_with(
        EndpointGroupName.MR_CONNECTION_STATS
    )


# --------------------------------------------------------------------------- #
# MR_CPU_LOAD (performance.py)
# --------------------------------------------------------------------------- #

_MR_DEVICES = [
    {"serial": "Q1", "name": "AP1", "model": "MR36", "networkId": "n1"},
    {"serial": "Q2", "name": "AP2", "model": "MR36", "networkId": "n1"},
]


async def test_cpu_load_total_failure_does_not_mark_ran() -> None:
    """Every CPU-load batch fetch errors => group NOT marked ran."""
    parent = _make_parent()
    parent.settings.api.batch_size = 20  # single batch
    parent.api.wireless.getOrganizationWirelessDevicesSystemCpuLoadHistory.side_effect = (
        Exception("boom")
    )
    collector = MRPerformanceCollector(parent)

    await collector.collect_cpu_load("org1", "Org", _MR_DEVICES)

    marked = [c.args[0] for c in parent._mark_group_ran.call_args_list]
    assert EndpointGroupName.MR_CPU_LOAD not in marked


async def test_cpu_load_partial_success_marks_ran() -> None:
    """One batch succeeds, one errors => group marked ran once."""
    parent = _make_parent()
    parent.settings.api.batch_size = 1  # two single-device batches
    parent.api.wireless.getOrganizationWirelessDevicesSystemCpuLoadHistory.side_effect = [
        [{"serial": "Q1", "history": [{"load": 10.0}]}],  # batch 1 ok
        Exception("boom"),  # batch 2 fails
    ]
    collector = MRPerformanceCollector(parent)

    with patch(
        "meraki_dashboard_exporter.collectors.devices.mr.performance.asyncio.sleep",
        new=AsyncMock(),
    ):
        await collector.collect_cpu_load("org1", "Org", _MR_DEVICES)

    parent._mark_group_ran.assert_called_once_with(EndpointGroupName.MR_CPU_LOAD)


# --------------------------------------------------------------------------- #
# MR_PACKET_LOSS (performance.py) - opposite bug: successful-empty must mark
# --------------------------------------------------------------------------- #


async def test_packet_loss_empty_success_marks_ran() -> None:
    """Successful fetch returning [] (no packet-loss data) => group marked ran."""
    parent = _make_parent()
    parent.api.wireless.getOrganizationWirelessDevicesPacketLossByNetwork.return_value = []
    parent.api.wireless.getOrganizationWirelessDevicesPacketLossByDevice.return_value = []
    collector = MRPerformanceCollector(parent)

    await collector.collect_packet_loss("org1", "Org", {})

    parent._mark_group_ran.assert_called_once_with(EndpointGroupName.MR_PACKET_LOSS)


async def test_packet_loss_total_failure_does_not_mark_ran() -> None:
    """Both packet-loss fetches error => group NOT marked ran."""
    parent = _make_parent()
    parent.api.wireless.getOrganizationWirelessDevicesPacketLossByNetwork.side_effect = (
        Exception("boom")
    )
    parent.api.wireless.getOrganizationWirelessDevicesPacketLossByDevice.side_effect = (
        Exception("boom")
    )
    collector = MRPerformanceCollector(parent)

    await collector.collect_packet_loss("org1", "Org", {})

    marked = [c.args[0] for c in parent._mark_group_ran.call_args_list]
    assert EndpointGroupName.MR_PACKET_LOSS not in marked
