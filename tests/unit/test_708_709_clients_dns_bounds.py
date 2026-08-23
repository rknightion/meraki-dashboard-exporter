"""Contract tests for bounded client application and reverse-DNS work (#708, #709)."""

from __future__ import annotations

import asyncio
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.collectors.clients import ClientsCollector
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.constants.metrics_constants import CollectorMetricName
from meraki_dashboard_exporter.services.dns_resolver import DNSResolver
from tests.fixtures.fleet import FleetPreset, build_fleet


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Return client-enabled settings without using a real API."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    result = Settings()
    result.clients.enabled = True
    return result


def test_708_application_rows_are_top_n_allowlisted_and_stably_tie_broken(
    settings: Settings,
) -> None:
    """Top-N is per client, ranks bytes descending, then label ascending, with one other row."""
    settings.clients.application_top_n = 2
    settings.clients.application_allowlist = ["Always Keep"]
    collector = object.__new__(ClientsCollector)
    collector.settings = settings

    bounded = collector._bound_application_usage([
        {"application": "Zulu", "received": 10, "sent": 0},
        {"application": "Alpha", "received": 10, "sent": 0},
        {"application": "Bravo", "received": 1, "sent": 0},
        {"application": "Always Keep", "received": 2, "sent": 0},
    ])

    assert bounded == {
        "alpha": (10.0, 0.0),
        "always_keep": (2.0, 0.0),
        "__other__": (1.0, 0.0),
        "zulu": (10.0, 0.0),
    }
    # Per-client rows are bounded from config alone: top-N + allowlist + other.
    assert len(bounded) <= (
        settings.clients.application_top_n
        + len(settings.clients.application_allowlist)
        + int(settings.clients.application_other_bucket)
    )


def test_708_genuine_other_application_cannot_collide_with_aggregate(
    settings: Settings,
) -> None:
    """The reserved aggregate label is outside the sanitizer's output space."""
    settings.clients.application_top_n = 1
    collector = object.__new__(ClientsCollector)
    collector.settings = settings

    bounded = collector._bound_application_usage([
        {"application": "other", "received": 10, "sent": 0},
        {"application": "Zulu", "received": 1, "sent": 0},
    ])

    assert bounded == {"other": (10.0, 0.0), "__other__": (1.0, 0.0)}


def test_708_campus_application_series_bound_is_configuration_derived(settings: Settings) -> None:
    """Every CAMPUS client has no more than configured application label rows."""
    settings.clients.application_top_n = 1
    settings.clients.application_allowlist = ["Fixture Application 2"]
    collector = object.__new__(ClientsCollector)
    collector.settings = settings
    campus = build_fleet(FleetPreset.CAMPUS)
    max_rows_per_client = (
        settings.clients.application_top_n
        + len(settings.clients.application_allowlist)
        + int(settings.clients.application_other_bucket)
    )

    for entries in campus.application_usage_by_network.values():
        for entry in entries:
            application_usage = cast(list[dict[str, Any]], entry["applicationUsage"])
            assert len(collector._bound_application_usage(application_usage)) <= max_rows_per_client


@pytest.mark.asyncio
async def test_709_reverse_dns_toggle_skips_queries_independently_of_clients_enabled(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Disabling reverse DNS keeps client collection enabled but makes no resolver query."""
    settings.clients.dns_reverse_lookup_enabled = False
    resolver = DNSResolver(settings)
    called = False

    async def lookup(_: str) -> str:
        nonlocal called
        called = True
        return "should-not-be-called.example"

    monkeypatch.setattr(resolver, "_perform_lookup", lookup)

    assert await resolver.resolve_multiple([("client-1", "10.0.0.1", "Laptop")]) == {}
    assert called is False


@pytest.mark.asyncio
async def test_709_dns_work_is_bounded_by_configured_peak_in_flight(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CAMPUS-sized batch runs only the configured number of DNS lookups at once."""
    settings.clients.dns_max_concurrent_lookups = 3
    resolver = DNSResolver(settings)
    active = 0
    peak_active = 0

    async def lookup(ip: str, client_id: str | None = None) -> str:
        nonlocal active, peak_active
        active += 1
        peak_active = max(peak_active, active)
        await asyncio.sleep(0)
        active -= 1
        return ip

    monkeypatch.setattr(resolver, "resolve_hostname", lookup)
    clients: list[tuple[str, str | None, str | None]] = [
        (f"client-{index}", f"10.0.{index // 256}.{index % 256}", None) for index in range(2000)
    ]

    resolved = await resolver.resolve_multiple(clients)

    assert len(resolved) == 2000
    assert peak_active == settings.clients.dns_max_concurrent_lookups
    assert resolver.get_cache_stats()["queue_peak_depth"] == len(clients)


def test_709_collector_exports_dns_queue_and_timeout_metrics(settings: Settings) -> None:
    """The resolver's bounded-work telemetry is exported on the Prometheus surface."""
    registry = CollectorRegistry()
    collector = ClientsCollector(api=MagicMock(), settings=settings, registry=registry)

    collector._update_cache_metrics()

    assert registry.get_sample_value(CollectorMetricName.CLIENT_DNS_QUEUE_DEPTH.value) == 0.0
    assert registry.get_sample_value(CollectorMetricName.CLIENT_DNS_QUEUE_WAIT_SECONDS.value) == 0.0
    assert (
        registry.get_sample_value(CollectorMetricName.CLIENT_DNS_LOOKUPS_TIMEOUT_TOTAL.value) == 0.0
    )
