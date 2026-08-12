"""Many-network collection proof for the deterministic Issue #707 fleet fixtures."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.core.api_facade import facade_for
from meraki_dashboard_exporter.core.async_utils import ManagedTaskGroup
from meraki_dashboard_exporter.core.collector import MetricCollector
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.metric_expiration import MetricExpirationManager
from meraki_dashboard_exporter.services.inventory import OrganizationInventory
from tests.fixtures.fleet import FleetPreset, build_fleet, peak_rss_bytes
from tests.helpers.mock_api import HTTPError


class FleetInventoryProbe(MetricCollector):
    """Minimal real collector path for scale-fixture transport assertions.

    It is deliberately a test-only probe, not a synthetic production collector:
    the point is to exercise the real collector base, inventory cache, facade,
    executor, bounded fan-out, metric tracking, and expiry lifecycle together.
    """

    def _initialize_metrics(self) -> None:
        """Register the bounded per-network result gauge."""
        self.network_client_rows = self._create_gauge(
            "test_fleet_network_client_rows",
            "Fixture client rows returned for one network.",
            labelnames=["network_id"],
        )

    async def _collect_impl(self) -> None:
        """Fetch inventory then make one facade-bound client request per network."""
        assert self.inventory is not None
        organizations = await self.inventory.get_organizations()
        async with ManagedTaskGroup(name="fleet_inventory_probe", max_concurrency=25) as group:
            for organization in organizations:
                networks = await self.inventory.get_networks(str(organization["id"]))
                for network in networks:
                    await group.create_task(
                        self._collect_network(str(network["id"])), name=str(network["id"])
                    )

    async def _collect_network(self, network_id: str) -> None:
        """Treat an individual network failure as partial collection, not a fabricated zero."""
        try:
            response = await facade_for(self).call(
                "getNetworkClients",
                self.api.networks.getNetworkClients,
                network_id,
                total_pages="all",
            )
        except Exception:
            return
        self._set_metric(
            self.network_client_rows,
            {"network_id": network_id},
            float(len(response)),
            "test_fleet_network_client_rows",
            ttl_seconds=0.001,
        )


@pytest.fixture
def fleet_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Fast, deterministic facade settings for the probe's error matrix."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    settings = Settings()
    settings.api.max_retries = 1
    settings.api.per_fetch_deadline_seconds = 2.0
    return settings


@pytest.fixture
def isolated_probe_registry(monkeypatch: pytest.MonkeyPatch) -> CollectorRegistry:
    """Prevent the probe's base collector metrics leaking into neighbouring tests."""
    registry = CollectorRegistry()
    monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", registry)
    monkeypatch.setattr(MetricCollector, "_metrics_initialized", False)
    monkeypatch.setattr(MetricCollector, "_collector_duration", None)
    monkeypatch.setattr(MetricCollector, "_collector_errors", None)
    monkeypatch.setattr(MetricCollector, "_collector_last_success", None)
    monkeypatch.setattr(MetricCollector, "_collector_api_calls", None)
    return registry


def _fleet_api(
    network_clients: Callable[..., list[dict[str, object]]]
) -> tuple[MagicMock, int]:
    """Create a real SDK-shaped mock from the branch topology and return its width."""
    fleet = build_fleet(FleetPreset.BRANCH_RETAIL)
    organization = fleet.organizations[0]
    org_id = str(organization["id"])
    api = MagicMock()
    api.organizations = MagicMock()
    api.networks = MagicMock()
    api.organizations.getOrganizations = MagicMock(return_value=fleet.organizations)
    api.organizations.getOrganizationNetworks = MagicMock(return_value=fleet.networks_by_org[org_id])
    api.networks.getNetworkClients = MagicMock(side_effect=network_clients)
    return api, fleet.network_count


async def test_branch_retail_executes_real_many_network_inventory_and_facade_path(
    fleet_settings: Settings,
    isolated_probe_registry: CollectorRegistry,
) -> None:
    """750 networks exercise one inventory fetch and 750 bounded executor calls."""
    fleet = build_fleet(FleetPreset.BRANCH_RETAIL)

    def clients(network_id: str, **_: object) -> list[dict[str, object]]:
        return fleet.clients_by_network[network_id]

    api, network_count = _fleet_api(clients)
    expiration = MetricExpirationManager(fleet_settings)
    collector = FleetInventoryProbe(
        api=api,
        settings=fleet_settings,
        registry=isolated_probe_registry,
        inventory=OrganizationInventory(api, fleet_settings),
        expiration_manager=expiration,
    )

    started = time.perf_counter()
    await collector.collect()
    report = fleet.measured_report(
        isolated_probe_registry,
        api_calls=api.networks.getNetworkClients.call_count + 2,
        rss_bytes=peak_rss_bytes(),
        scrape_render_seconds=time.perf_counter() - started,
    )

    api.organizations.getOrganizations.assert_called_once_with(total_pages="all")
    api.organizations.getOrganizationNetworks.assert_called_once_with(
        fleet.organizations[0]["id"], total_pages="all"
    )
    assert api.networks.getNetworkClients.call_count == network_count
    samples = [
        sample
        for metric in isolated_probe_registry.collect()
        if metric.name == "test_fleet_network_client_rows"
        for sample in metric.samples
    ]
    assert len(samples) == network_count
    assert {sample.value for sample in samples} == {10.0}
    assert report.preset is FleetPreset.BRANCH_RETAIL
    assert report.calls_per_cycle == network_count + 2
    assert report.series_count >= network_count
    assert report.payload_bytes > 0
    assert report.rss_bytes > 0
    assert report.scrape_render_seconds >= 0
    assert report.shape_assumptions == ("SHAPE-ASSUMED:MX",)


async def test_fanout_records_429_timeout_and_partial_failure_without_fabricating_series(
    monkeypatch: pytest.MonkeyPatch,
    fleet_settings: Settings,
    isolated_probe_registry: CollectorRegistry,
) -> None:
    """One real branch fan-out has a retry, timeout, and partial failure with exact fallout."""
    fleet = build_fleet(FleetPreset.BRANCH_RETAIL)
    first_network = str(fleet.networks_by_org[str(fleet.organizations[0]["id"])][0]["id"])
    timeout_network = str(fleet.networks_by_org[str(fleet.organizations[0]["id"])][1]["id"])
    failed_network = str(fleet.networks_by_org[str(fleet.organizations[0]["id"])][2]["id"])
    retry_attempts = 0

    async def no_wait(_: float) -> None:
        return None

    monkeypatch.setattr("meraki_dashboard_exporter.core.api_facade.asyncio.sleep", AsyncMock(side_effect=no_wait))
    fleet_settings.api.per_fetch_deadline_seconds = 0.1

    def clients(network_id: str, **_: object) -> list[dict[str, object]]:
        nonlocal retry_attempts
        if network_id == first_network and retry_attempts == 0:
            retry_attempts += 1
            raise HTTPError("HTTP 429", 429)
        if network_id == timeout_network:
            time.sleep(0.2)
        if network_id == failed_network:
            raise RuntimeError("partial fixture failure")
        return fleet.clients_by_network[network_id]

    api, network_count = _fleet_api(clients)
    expiration = MetricExpirationManager(fleet_settings)
    collector = FleetInventoryProbe(
        api=api,
        settings=fleet_settings,
        registry=isolated_probe_registry,
        inventory=OrganizationInventory(api, fleet_settings),
        expiration_manager=expiration,
    )

    await collector.collect()

    assert retry_attempts == 1
    assert api.networks.getNetworkClients.call_count == network_count + 1
    samples = [
        sample
        for metric in isolated_probe_registry.collect()
        if metric.name == "test_fleet_network_client_rows"
        for sample in metric.samples
    ]
    assert len(samples) == network_count - 2
    assert {sample.labels["network_id"] for sample in samples}.isdisjoint(
        {timeout_network, failed_network}
    )

    await asyncio.sleep(0.002)
    await expiration._cleanup_expired_metrics()
    assert isolated_probe_registry.get_sample_value(
        "test_fleet_network_client_rows", {"network_id": first_network}
    ) is None


async def test_two_overlapping_collection_runs_share_inventory_but_not_network_metrics(
    fleet_settings: Settings,
    isolated_probe_registry: CollectorRegistry,
) -> None:
    """Concurrent cycles deduplicate organization/network inventory and keep all 750 series."""
    fleet = build_fleet(FleetPreset.BRANCH_RETAIL)

    def clients(network_id: str, **_: object) -> list[dict[str, object]]:
        return fleet.clients_by_network[network_id]

    api, network_count = _fleet_api(clients)
    collector = FleetInventoryProbe(
        api=api,
        settings=fleet_settings,
        registry=isolated_probe_registry,
        inventory=OrganizationInventory(api, fleet_settings),
    )

    await asyncio.gather(collector.collect(), collector.collect())

    api.organizations.getOrganizations.assert_called_once_with(total_pages="all")
    api.organizations.getOrganizationNetworks.assert_called_once()
    assert api.networks.getNetworkClients.call_count == network_count * 2
