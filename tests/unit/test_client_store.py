"""Unit tests for the :mod:`client_store` service."""

# ruff: noqa: S101

import time
from datetime import UTC, datetime

import pytest

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
