"""Regression coverage for cardinality accounting and client-store eviction (#711)."""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest
from prometheus_client import CollectorRegistry, Gauge, generate_latest

from meraki_dashboard_exporter.core.api_models import NetworkClient
from meraki_dashboard_exporter.core.cardinality import CardinalityMonitor
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.constants.metrics_constants import CollectorMetricName
from meraki_dashboard_exporter.services.client_store import ClientStore


def _scrape_sample_count(registry: CollectorRegistry) -> int:
    """Return the number of sample lines in a real Prometheus text scrape."""
    scrape = generate_latest(registry).decode()
    return sum(bool(line) and not line.startswith("#") for line in scrape.splitlines())


def _make_client(client_id: str) -> NetworkClient:
    """Create the smallest valid client record for store-churn coverage."""
    now = datetime.now(UTC)
    return NetworkClient(
        id=client_id,
        mac=f"aa:bb:cc:dd:ee:{int(client_id):02x}",
        ip="10.0.0.1",
        firstSeen=now,
        lastSeen=now,
        status="Online",
    )


def test_cardinality_endpoint_total_reconciles_with_generated_scrape() -> None:
    """#711: report product, self, and exact exposed sample totals separately."""
    registry = CollectorRegistry()
    monitor = CardinalityMonitor(registry=registry)
    monitor.mark_first_run_complete()
    Gauge("issue_711_product_metric", "A product metric", registry=registry).set(1)

    analysis = monitor.analyze_cardinality(use_cache=False)
    scrape_sample_count = _scrape_sample_count(registry)

    assert analysis["product_series"] == 1
    assert analysis["self_series"] > 0
    assert analysis["exposed_series"] == scrape_sample_count
    assert analysis["product_series"] + analysis["self_series"] == scrape_sample_count
    assert analysis["total_series"] == scrape_sample_count

    scrape = generate_latest(registry).decode()
    for metric_name, expected in {
        CollectorMetricName.CARDINALITY_PRODUCT_SERIES.value: analysis["product_series"],
        CollectorMetricName.CARDINALITY_SELF_SERIES.value: analysis["self_series"],
        CollectorMetricName.CARDINALITY_EXPOSED_SERIES.value: analysis["exposed_series"],
    }.items():
        assert f"{metric_name} {expected}.0" in scrape


@pytest.fixture
def client_store(monkeypatch: pytest.MonkeyPatch) -> ClientStore:
    """Create a client store with valid local test settings."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    return ClientStore(Settings())


def test_stale_network_churn_evicts_all_client_store_maps(client_store: ClientStore) -> None:
    """#711: replacing stale networks cannot retain display or organization metadata."""
    for index in range(100):
        network_id = f"network-{index}"
        client_store.update_clients(
            network_id,
            [_make_client(str(index))],
            network_name=f"Network {index}",
            org_id=f"org-{index}",
        )
        client_store._last_update[network_id] = time.time() - client_store.cache_ttl - 1

        assert client_store.cleanup_stale_networks() == 1
        assert network_id not in client_store._clients
        assert network_id not in client_store._last_update
        assert network_id not in client_store._network_names
        assert network_id not in client_store._network_orgs

    assert (
        len(client_store._clients),
        len(client_store._last_update),
        len(client_store._network_names),
        len(client_store._network_orgs),
    ) == (0, 0, 0, 0)
