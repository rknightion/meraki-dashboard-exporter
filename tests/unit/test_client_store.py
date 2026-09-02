"""Unit tests for the :mod:`client_store` service."""

# ruff: noqa: S101

import time
from datetime import UTC, datetime

import pytest
from structlog.testing import capture_logs

from meraki_dashboard_exporter.core.api_models import NetworkClient
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.services.client_store import ClientStore


@pytest.fixture
def store(monkeypatch):
    """Create a :class:`ClientStore` instance for testing."""

    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    settings = Settings()
    return ClientStore(settings)


def _make_client(client_id: str, ip: str, status: str = "Online") -> NetworkClient:
    """Create a minimal :class:`NetworkClient` model."""
    now = datetime.now(UTC)
    return NetworkClient(
        id=client_id,
        mac="aa:bb:cc:dd:ee:" + client_id[-2:],
        ip=ip,
        firstSeen=now,
        lastSeen=now,
        status=status,
    )


def test_update_and_retrieve_client(store):
    """Verify clients can be added, updated and retrieved."""

    c1 = _make_client("c1", "10.0.0.1")
    store.update_clients(
        "N1", [c1], network_name="Net1", org_id="O1", hostnames={"10.0.0.1": "host1"}
    )

    retrieved = store.get_client("N1", "c1")
    assert retrieved is not None
    assert retrieved.hostname == "host1"
    assert store.get_client_by_mac(c1.mac) == retrieved
    assert store.get_clients_by_ip("10.0.0.1") == [retrieved]
    assert store.get_network_clients("N1") == [retrieved]
    assert store.get_all_clients() == [retrieved]
    assert store.get_network_names() == {"N1": "Net1"}
    assert store.is_network_stale("N1") is False

    # update existing client
    updated = _make_client("c1", "10.0.0.2", status="Offline")
    store.update_clients("N1", [updated])
    retrieved2 = store.get_client("N1", "c1")
    assert retrieved2.ip == "10.0.0.2"
    assert retrieved2.status == "Offline"


def test_is_network_stale_and_cleanup(store):
    """Ensure stale networks are detected and removed."""

    c1 = _make_client("c1", "10.0.0.1")
    store.update_clients("N1", [c1])
    # Force last update to be old
    store._last_update["N1"] = time.time() - store.cache_ttl - 1
    assert store.is_network_stale("N1") is True
    removed = store.cleanup_stale_networks()
    assert removed == 1
    assert store.get_network_clients("N1") == []


def test_update_clients_per_network_log_is_debug(store, force_debug_log_capture):
    """F-171: the per-network "Updated client data" line must be debug-level.

    At ~100 networks this fired once per network per cycle at INFO, flooding
    logs (~2,400 lines/hour). It is demoted to debug.
    """
    c1 = _make_client("c1", "10.0.0.1")

    with capture_logs() as caps:
        store.update_clients("N1", [c1], network_name="Net1", org_id="O1")

    updated_events = [e for e in caps if e.get("event") == "Updated client data"]
    assert updated_events, "expected an 'Updated client data' log event"
    assert all(e["log_level"] == "debug" for e in updated_events), (
        f"'Updated client data' must be debug-level, got: {updated_events}"
    )


def test_global_cap_blocks_new_clients_but_updates_existing(store):
    """#533: a global cap on stored clients blocks NEW clients once reached.

    Updates to already-stored clients must still proceed even when the global
    cap is reached, and a warning must be logged when new clients are skipped.
    """

    store.settings.clients.max_clients_total = 2
    store.max_clients_total = 2

    c1 = _make_client("c1", "10.0.0.1")
    c2 = _make_client("c2", "10.0.0.2")
    store.update_clients("N_A", [c1, c2], network_name="NetA", org_id="O1")

    assert store.get_client("N_A", "c1") is not None
    assert store.get_client("N_A", "c2") is not None
    assert len(store.get_all_clients()) == 2

    c3 = _make_client("c3", "10.0.1.1")
    c4 = _make_client("c4", "10.0.1.2")
    with capture_logs() as caps:
        store.update_clients("N_B", [c3, c4], network_name="NetB", org_id="O1")

    assert store.get_client("N_B", "c3") is None
    assert store.get_client("N_B", "c4") is None
    assert len(store.get_all_clients()) == 2

    cap_events = [e for e in caps if "cap" in e.get("event", "").lower()]
    assert cap_events, f"expected a global-cap warning event, got: {caps}"
    assert any(e["log_level"] == "warning" for e in cap_events)

    updated_c1 = _make_client("c1", "10.0.0.1", status="Offline")
    store.update_clients("N_A", [updated_c1])
    retrieved = store.get_client("N_A", "c1")
    assert retrieved.status == "Offline"


def test_complete_snapshot_reclaims_departed_clients_before_global_cap(store):
    """A complete replacement snapshot frees departed IDs before admitting new ones."""

    store.settings.clients.max_clients_total = 2
    store.max_clients_total = 2

    c1 = _make_client("c1", "10.0.0.1")
    c2 = _make_client("c2", "10.0.0.2")
    store.update_clients("N1", [c1, c2], complete_snapshot=True)

    c3 = _make_client("c3", "10.0.0.3")
    store.update_clients("N1", [c2, c3], complete_snapshot=True)

    assert {client.id for client in store.get_network_clients("N1")} == {"c2", "c3"}


def test_incomplete_snapshot_retains_departed_clients(store):
    """A failed or capped partial result must not erase retained membership."""

    c1 = _make_client("c1", "10.0.0.1")
    c2 = _make_client("c2", "10.0.0.2")
    store.update_clients("N1", [c1, c2], complete_snapshot=True)

    store.update_clients("N1", [c2], complete_snapshot=False)

    assert {client.id for client in store.get_network_clients("N1")} == {"c1", "c2"}


def test_existing_client_refreshes_api_owned_identity_and_display_fields(store):
    """Existing records refresh API data while retaining a prior DNS-derived hostname."""

    original = _make_client("c1", "10.0.0.1").model_copy(
        update={
            "description": "Old description",
            "manufacturer": "Old manufacturer",
            "os": "Old OS",
        }
    )
    store.update_clients(
        "N1",
        [original],
        network_name="Old network",
        org_id="old-org",
        hostnames={"10.0.0.1": "old-host.example"},
        complete_snapshot=True,
    )

    refreshed = _make_client("c1", "10.0.0.2").model_copy(
        update={
            "mac": "ff:ee:dd:cc:bb:aa",
            "description": "New description",
            "manufacturer": "New manufacturer",
            "os": "New OS",
        }
    )
    store.update_clients(
        "N1",
        [refreshed],
        network_name="Renamed network",
        org_id="new-org",
        hostnames={},
        complete_snapshot=True,
    )

    client = store.get_client("N1", "c1")
    assert client is not None
    assert client.mac == "ff:ee:dd:cc:bb:aa"
    assert client.description == "New description"
    assert client.manufacturer == "New manufacturer"
    assert client.os == "New OS"
    assert client.networkName == "Renamed network"
    assert client.organizationId == "new-org"
    assert client.hostname == "old-host.example"
    assert client.calculatedHostname == "New description"
    assert store.get_network_names() == {"N1": "Renamed network"}


def test_get_statistics(store):
    """Check that statistics reporting aggregates correctly."""

    c1 = _make_client("c1", "10.0.0.1")
    c2 = _make_client("c2", "10.0.0.2", status="Offline")
    store.update_clients("N1", [c1, c2])
    stats = store.get_statistics()
    assert stats["total_networks"] == 1
    assert stats["total_clients"] == 2
    assert stats["online_clients"] == 1
    assert stats["offline_clients"] == 1
