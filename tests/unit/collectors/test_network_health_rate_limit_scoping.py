"""F-170: network-scoped health fetchers must key the rate limiter by owning org.

The client-side rate limiter buckets by ``org_id or "global"``. The bluetooth,
data-rate and SSID-performance fetchers previously passed only ``network_id``, so
``logging_decorators._extract_context`` could not resolve an org and every call
landed in the shared "global" bucket, causing cross-org self-throttling. These
tests assert the org flows through to ``rate_limiter.acquire``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from meraki_dashboard_exporter.collectors.network_health_collectors.bluetooth import (
    BluetoothCollector,
)
from meraki_dashboard_exporter.collectors.network_health_collectors.data_rates import (
    DataRatesCollector,
)
from meraki_dashboard_exporter.collectors.network_health_collectors.ssid_performance import (
    SSIDPerformanceCollector,
)


def _make_parent(api: MagicMock) -> MagicMock:
    """Build a parent stub exposing the rate limiter and api the fetcher needs."""
    parent = MagicMock()
    parent.api = api
    parent.rate_limiter = MagicMock()
    parent.rate_limiter.acquire = AsyncMock(return_value=0.0)
    return parent


async def test_data_rates_fetcher_keys_rate_limiter_by_org() -> None:
    """DataRates fetcher passes org_id to the rate limiter, not None."""
    api = MagicMock()
    api.wireless.getNetworkWirelessDataRateHistory = MagicMock(return_value=[])
    parent = _make_parent(api)
    collector = DataRatesCollector(parent)

    await collector._fetch_data_rate_history("N_1", org_id="org_owner")

    parent.rate_limiter.acquire.assert_awaited_once_with(
        "org_owner", "getNetworkWirelessDataRateHistory"
    )


async def test_bluetooth_fetcher_keys_rate_limiter_by_org() -> None:
    """Bluetooth fetcher passes org_id to the rate limiter, not None."""
    api = MagicMock()
    api.networks.getNetworkBluetoothClients = MagicMock(return_value=[])
    parent = _make_parent(api)
    collector = BluetoothCollector(parent)

    await collector._fetch_bluetooth_clients("N_1", org_id="org_owner")

    parent.rate_limiter.acquire.assert_awaited_once_with("org_owner", "getNetworkBluetoothClients")


async def test_ssid_performance_fetcher_keys_rate_limiter_by_org() -> None:
    """SSID-performance fetcher passes org_id to the rate limiter, not None."""
    api = MagicMock()
    api.wireless.getNetworkWirelessFailedConnections = MagicMock(return_value=[])
    parent = _make_parent(api)
    collector = SSIDPerformanceCollector(parent)

    await collector._fetch_failed_connections("N_1", org_id="org_owner")

    parent.rate_limiter.acquire.assert_awaited_once_with(
        "org_owner", "getNetworkWirelessFailedConnections"
    )
