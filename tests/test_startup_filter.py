"""Startup-time fail-fast and observability tests for the network filter.

These tests avoid constructing the full CollectorManager (which spins up
the entire collector graph and rate limiter) by exercising
``_validate_network_filter`` directly against a bare instance, and the
metrics gauges via a real OrganizationInventory.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import REGISTRY

from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings

pytestmark = pytest.mark.asyncio


def _bare_manager(*, networks_by_org, filter_settings) -> CollectorManager:
    """Build a CollectorManager bare instance with just enough stubs.

    Skips full ``__init__`` and only sets the attributes
    ``_validate_network_filter`` reads.
    """
    manager = CollectorManager.__new__(CollectorManager)

    settings = MagicMock()
    settings.network_filter = filter_settings
    manager.settings = settings

    inventory = AsyncMock()
    inventory.get_organizations.return_value = [
        {"id": org_id, "name": org_id} for org_id in networks_by_org
    ]

    async def _get_networks(org_id, *, unfiltered=False):
        nets = list(networks_by_org.get(org_id, []))
        if unfiltered or not filter_settings.is_active:
            return nets
        from meraki_dashboard_exporter.core.network_filter import NetworkFilter

        return NetworkFilter(filter_settings).apply(nets)

    inventory.get_networks.side_effect = _get_networks
    manager.inventory = inventory  # type: ignore[assignment]
    return manager


async def test_filter_resolving_to_zero_in_all_orgs_raises() -> None:
    """If the active filter resolves to zero across all orgs, raise RuntimeError."""
    manager = _bare_manager(
        networks_by_org={"ORG_A": [{"id": "L_1", "name": "prod", "tags": []}]},
        filter_settings=NetworkFilterSettings(include_names=["nope-*"]),
    )
    with pytest.raises(RuntimeError, match="resolved to zero networks"):
        await manager._validate_network_filter()


async def test_filter_resolving_to_zero_in_one_org_logs_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When one of several orgs resolves to zero, log ERROR but do not raise.

    structlog routes through its own pipeline, so caplog doesn't capture
    these messages. Spying on the manager's logger directly is reliable.
    """
    from meraki_dashboard_exporter.collectors import manager as manager_mod

    captured: list[dict] = []

    def _fake_error(message: str, **kwargs: object) -> None:
        captured.append({"message": message, **kwargs})

    monkeypatch.setattr(manager_mod.logger, "error", _fake_error)

    manager = _bare_manager(
        networks_by_org={
            "ORG_A": [{"id": "L_1", "name": "prod-a", "tags": []}],
            "ORG_B": [{"id": "L_2", "name": "lab-b", "tags": ["lab"]}],
        },
        filter_settings=NetworkFilterSettings(include_names=["prod-*"]),
    )
    await manager._validate_network_filter()  # must NOT raise

    assert any(entry.get("org_id") == "ORG_B" for entry in captured), (
        f"Expected an ERROR log for ORG_B but captured: {captured}"
    )


async def test_filter_match_metric_emitted() -> None:
    """The filter observability metrics are populated on each cache refresh."""
    from meraki_dashboard_exporter.core.network_filter import NetworkFilter
    from meraki_dashboard_exporter.services.inventory import OrganizationInventory

    api = MagicMock()
    api.organizations.getOrganizationNetworks = MagicMock(
        return_value=[
            {"id": "L_1", "name": "prod", "tags": []},
            {"id": "L_2", "name": "lab", "tags": ["lab"]},
        ]
    )
    nf = NetworkFilter(NetworkFilterSettings(exclude_tags=["lab"]))
    inv = OrganizationInventory(api, MagicMock(), network_filter=nf)
    await inv.get_networks("ORG")

    resolved = REGISTRY.get_sample_value("meraki_network_filter_resolved", {"org_id": "ORG"})
    total = REGISTRY.get_sample_value("meraki_network_filter_networks", {"org_id": "ORG"})
    assert resolved == 1
    assert total == 2

    included_l1 = REGISTRY.get_sample_value(
        "meraki_network_filter_match",
        {"org_id": "ORG", "network_id": "L_1"},
    )
    excluded_l2 = REGISTRY.get_sample_value(
        "meraki_network_filter_match",
        {"org_id": "ORG", "network_id": "L_2"},
    )
    assert included_l1 == 1.0
    assert excluded_l2 == 0.0


async def test_filter_match_metric_one_for_all_when_filter_inactive() -> None:
    """When no filter is active, every network's gauge is 1.0."""
    from meraki_dashboard_exporter.services.inventory import OrganizationInventory

    api = MagicMock()
    api.organizations.getOrganizationNetworks = MagicMock(
        return_value=[
            {"id": "L_A", "name": "alpha", "tags": []},
            {"id": "L_B", "name": "beta", "tags": []},
        ]
    )
    inv = OrganizationInventory(api, MagicMock(), network_filter=None)
    await inv.get_networks("ORG2")

    a = REGISTRY.get_sample_value(
        "meraki_network_filter_match", {"org_id": "ORG2", "network_id": "L_A"}
    )
    b = REGISTRY.get_sample_value(
        "meraki_network_filter_match", {"org_id": "ORG2", "network_id": "L_B"}
    )
    assert a == 1.0
    assert b == 1.0


async def test_filter_match_metric_no_stale_labels_after_filter_change() -> None:
    """A subsequent refresh under a different filter must not leave stale series.

    Without the value-as-1/0 fix, the same (org_id, network_id) could carry
    both ``included=true`` and ``included=false`` series at value 1 after a
    filter swap. With the fix, exactly one series exists per network and its
    value tracks the current filter.
    """
    from meraki_dashboard_exporter.core.network_filter import NetworkFilter
    from meraki_dashboard_exporter.services.inventory import OrganizationInventory

    api = MagicMock()
    api.organizations.getOrganizationNetworks = MagicMock(
        return_value=[
            {"id": "L_X", "name": "prod", "tags": []},
            {"id": "L_Y", "name": "lab", "tags": ["lab"]},
        ]
    )

    nf_excl = NetworkFilter(NetworkFilterSettings(exclude_tags=["lab"]))
    inv = OrganizationInventory(api, MagicMock(), network_filter=nf_excl)
    await inv.get_networks("ORG3")

    assert (
        REGISTRY.get_sample_value(
            "meraki_network_filter_match", {"org_id": "ORG3", "network_id": "L_X"}
        )
        == 1.0
    )
    assert (
        REGISTRY.get_sample_value(
            "meraki_network_filter_match", {"org_id": "ORG3", "network_id": "L_Y"}
        )
        == 0.0
    )

    # Swap the filter (simulating a config reload) and force a refresh.
    inv._network_filter = NetworkFilter(NetworkFilterSettings(include_tags=["lab"]))
    await inv.get_networks("ORG3", force_refresh=True)

    assert (
        REGISTRY.get_sample_value(
            "meraki_network_filter_match", {"org_id": "ORG3", "network_id": "L_X"}
        )
        == 0.0
    )
    assert (
        REGISTRY.get_sample_value(
            "meraki_network_filter_match", {"org_id": "ORG3", "network_id": "L_Y"}
        )
        == 1.0
    )
