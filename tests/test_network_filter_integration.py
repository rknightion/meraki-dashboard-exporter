"""Integration regression tests proving the network filter covers all paths.

Each test pins one collector's network-fetch path to go through inventory
(or to apply NetworkFilter on a fallback). If any future refactor
re-introduces a direct SDK call that bypasses the filter, these tests
fail fast.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


async def test_network_health_uses_inventory() -> None:
    """NetworkHealthCollector._fetch_networks_for_health goes via inventory."""
    from meraki_dashboard_exporter.collectors.network_health import (
        NetworkHealthCollector,
    )

    collector = NetworkHealthCollector.__new__(NetworkHealthCollector)
    collector.inventory = AsyncMock()
    collector.inventory.get_networks.return_value = [{"id": "L_1", "name": "x"}]
    collector._track_api_call = MagicMock()

    result = await collector._fetch_networks_for_health("ORG")

    collector.inventory.get_networks.assert_awaited_once_with("ORG")
    assert result == [{"id": "L_1", "name": "x"}]


async def test_device_poe_uses_inventory() -> None:
    """DeviceCollector._fetch_networks_for_poe goes via inventory."""
    from meraki_dashboard_exporter.collectors.device import DeviceCollector

    collector = DeviceCollector.__new__(DeviceCollector)
    collector.inventory = AsyncMock()
    collector.inventory.get_networks.return_value = [{"id": "L_1", "name": "x"}]

    result = await collector._fetch_networks_for_poe("ORG")

    collector.inventory.get_networks.assert_awaited_once_with("ORG")
    assert result == [{"id": "L_1", "name": "x"}]


async def test_ms_stp_uses_parent_inventory() -> None:
    """MSCollector.collect_stp_priorities fetches via parent.inventory."""
    from meraki_dashboard_exporter.collectors.devices.ms import MSCollector

    collector = MSCollector.__new__(MSCollector)
    parent = MagicMock()
    parent.inventory = AsyncMock()
    # Return a network list that contains no switches so the rest of the
    # method short-circuits and we only verify the network fetch path.
    parent.inventory.get_networks.return_value = []
    collector.parent = parent
    # F-037 gates collect_stp_priorities on the SLOW cadence; satisfy the gate
    # (fresh instance, never collected) so the network-fetch path runs. The
    # interval now comes from the scheduler's MS_STP group (#617, floor 900s).
    collector.settings = MagicMock()
    collector.settings.update_intervals.slow = 900
    parent._group_interval = MagicMock(return_value=900.0)
    parent._group_ttl_seconds = MagicMock(return_value=None)
    collector._last_stp_collection = 0.0

    await collector.collect_stp_priorities("ORG", "Org Name", device_lookup={})

    # #292/#293/#295 fold: collect_stp_priorities now also invokes
    # collect_dhcp_security (#292 rogue DHCP + #293 DAI) and
    # collect_link_aggregations (#295) from this same per-org call site, and each
    # independently fetches networks via the CACHED
    # self.parent.inventory.get_networks(org_id). That is 3 awaits total
    # (dhcp-security + LACP + STP), all keyed by the same org; get_networks is
    # cached so the extra awaits are harmless.
    assert parent.inventory.get_networks.await_count == 3
    for call in parent.inventory.get_networks.await_args_list:
        assert call.args == ("ORG",)


async def test_mr_ssid_usage_does_not_fetch_per_network() -> None:
    """MRWirelessCollector.collect_ssid_usage no longer walks every network.

    The org-wide getOrganizationSummaryTopSsidsByUsage row is emitted at
    org+SSID level, so there is no per-network SSID mapping and therefore no
    per-network getNetworkWirelessSsids fan-out (F-035) and no per-network
    replication of the org total (F-082). This guards against a regression that
    re-introduces the mapping.
    """
    from meraki_dashboard_exporter.collectors.devices.mr.wireless import (
        MRWirelessCollector,
    )

    collector = MRWirelessCollector.__new__(MRWirelessCollector)
    parent = MagicMock()
    parent.inventory = AsyncMock()
    parent._set_metric = MagicMock()
    parent.rate_limiter = None  # avoid the decorator's async rate-limiter path
    collector.parent = parent
    collector.api = MagicMock()
    collector.api.organizations.getOrganizationSummaryTopSsidsByUsage = MagicMock(
        return_value=[
            {"name": "Corp", "usage": {"total": 100.0}, "clients": {"counts": {"total": 3}}},
        ]
    )
    # Attach the SSID gauges the emission path touches.
    for attr in (
        "_ssid_usage_total_mb",
        "_ssid_usage_downstream_mb",
        "_ssid_usage_upstream_mb",
        "_ssid_usage_percentage",
        "_ssid_client_count",
    ):
        setattr(collector, attr, MagicMock())

    await collector.collect_ssid_usage("ORG", "Org Name")

    # The mapping method is gone and no per-network calls happen.
    assert not hasattr(collector, "_build_ssid_to_network_mapping")
    parent.inventory.get_networks.assert_not_awaited()
    collector.api.wireless.getNetworkWirelessSsids.assert_not_called()
    # Emitted labels are org+SSID only — never a network label. The mutable
    # org_name has moved onto meraki_org_info (#534); numeric SSID-usage series
    # carry ID-only labels plus the retained ssid key.
    assert parent._set_metric.call_count == 5
    for call in parent._set_metric.call_args_list:
        labels = call[0][1]
        assert set(labels) == {"org_id", "ssid"}


async def test_alerts_direct_fallback_applies_filter() -> None:
    """AlertsCollector._fetch_networks_direct applies the filter."""
    from meraki_dashboard_exporter.collectors.alerts import AlertsCollector
    from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings

    collector = AlertsCollector.__new__(AlertsCollector)
    collector.api = MagicMock()
    collector.api.organizations.getOrganizationNetworks = MagicMock(
        return_value=[
            {"id": "L_1", "name": "prod", "tags": []},
            {"id": "L_2", "name": "lab", "tags": ["lab"]},
        ]
    )
    settings = MagicMock()
    settings.network_filter = NetworkFilterSettings(exclude_tags=["lab"])
    collector.settings = settings

    result = await collector._fetch_networks_direct("ORG")
    assert result is not None
    assert [n["id"] for n in result] == ["L_1"]


async def test_api_helpers_direct_fallback_applies_filter() -> None:
    """api_helpers._fetch_networks_direct applies the filter when inventory missing."""
    from meraki_dashboard_exporter.core.api_helpers import APIHelper
    from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings

    helper = APIHelper.__new__(APIHelper)
    helper.api = MagicMock()
    helper.api.organizations.getOrganizationNetworks = MagicMock(
        return_value=[
            {"id": "L_1", "name": "prod", "tags": []},
            {"id": "L_2", "name": "lab", "tags": ["lab"]},
        ]
    )
    helper.collector = MagicMock()
    helper.collector.settings.network_filter = NetworkFilterSettings(exclude_tags=["lab"])
    helper.collector._track_api_call = MagicMock()
    helper._acquire_rate_limit = AsyncMock()

    result = await helper._fetch_networks_direct("ORG")
    assert [n["id"] for n in result] == ["L_1"]


async def test_api_helpers_devices_direct_fallback_applies_filter() -> None:
    """api_helpers._fetch_devices_direct applies the filter when inventory missing (#520)."""
    from meraki_dashboard_exporter.core.api_helpers import APIHelper
    from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings

    helper = APIHelper.__new__(APIHelper)
    helper.api = MagicMock()
    helper.api.organizations.getOrganizationNetworks = MagicMock(
        return_value=[
            {"id": "L_1", "name": "prod", "tags": []},
            {"id": "L_2", "name": "lab", "tags": ["lab"]},
        ]
    )
    helper.api.organizations.getOrganizationDevices = MagicMock(
        return_value=[
            {"serial": "Q1", "productType": "switch", "networkId": "L_1"},
            {"serial": "Q2", "productType": "switch", "networkId": "L_2"},
        ]
    )
    helper.collector = MagicMock()
    helper.collector.settings.network_filter = NetworkFilterSettings(exclude_tags=["lab"])
    helper.collector._track_api_call = MagicMock()
    helper._acquire_rate_limit = AsyncMock()

    result = await helper._fetch_devices_direct("ORG")
    assert [d["serial"] for d in result] == ["Q1"]
