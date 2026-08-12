"""Regression coverage for client child scheduler groups (#703)."""

from __future__ import annotations

import asyncio
import math
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.collectors.clients import ClientsCollector
from meraki_dashboard_exporter.core.api_models import NetworkClient
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName, EndpointScheduler, OrgShape


class _Limiter:
    """Fixed budget double for scheduler-only tests."""

    def effective_rate_per_second(self) -> float:
        """Return a deliberately ample rate so floors remain visible."""
        return math.inf


def _settings(
    *, signal_quality_enabled: bool = False, profile: str | None = "full"
) -> SimpleNamespace:
    """Minimal settings surface used by the client collector and scheduler."""
    return SimpleNamespace(
        api=SimpleNamespace(
            rate_limit_requests_per_second=10.0,
            rate_limit_shared_fraction=1.0,
            model_fields_set=set(),
        ),
        clients=SimpleNamespace(enabled=True, signal_quality_enabled=signal_quality_enabled),
        collectors=SimpleNamespace(profile=profile),
        monitoring=SimpleNamespace(metric_ttl_multiplier=2.0),
        scheduler=SimpleNamespace(
            mode="fixed",
            target_utilization=0.7,
            max_stretch_factor=4.0,
            max_interval_seconds=3600,
            resolve_interval_seconds=900,
            aimd_enabled=False,
            aimd_resolve_hysteresis=0.2,
            group_interval_overrides={},
            failure_retry_seconds=300,
        ),
    )


def _shape(*, wireless_networks: int) -> OrgShape:
    """Return a client-relevant organization shape."""
    return OrgShape(
        org_id="703",
        network_count=wireless_networks,
        wireless_network_count=wireless_networks,
        switch_network_count=0,
        appliance_network_count=0,
        sensor_network_count=0,
        camera_network_count=0,
        cellular_network_count=0,
        device_count=0,
        ap_count=0,
        switch_count=0,
        appliance_count=0,
        physical_mx_count=0,
        camera_count=0,
        sensor_count=0,
        cellular_count=0,
    )


def _collector(settings: SimpleNamespace) -> ClientsCollector:
    """Build only the settings-bearing part needed by get_endpoint_groups."""
    collector = object.__new__(ClientsCollector)
    collector.settings = settings  # type: ignore[assignment]
    return collector


def test_703_disabled_signal_quality_is_not_registered_or_costed() -> None:
    """The 500-network default excludes exactly 500 * 200 / 600 rps of phantom demand."""
    settings = _settings(signal_quality_enabled=False)
    scheduler = EndpointScheduler(settings, _Limiter())  # type: ignore[arg-type]
    scheduler.register_groups(_collector(settings).get_endpoint_groups())
    scheduler.resolve(_shape(wireless_networks=500))

    assert EndpointGroupName.CLIENTS_SIGNAL_QUALITY not in {
        group.name for group in _collector(settings).get_endpoint_groups()
    }
    # clients_list: 500 / 300; clients_app_usage: 500 / 600. The missing
    # signal-quality term is exactly 500 * 200 / 600 = 166.66666666666666 rps.
    assert scheduler.diagnostics()["total_demand_rps"] == pytest.approx(2.5)


def test_703_default_client_groups_sleep_until_clients_list_is_due() -> None:
    """After local app work succeeds, no disabled child forces the outer 1s floor."""
    settings = _settings(signal_quality_enabled=False)
    scheduler = EndpointScheduler(settings, _Limiter())  # type: ignore[arg-type]
    scheduler.register_groups(_collector(settings).get_endpoint_groups())
    scheduler.resolve(_shape(wireless_networks=1))
    scheduler.mark_ran(EndpointGroupName.CLIENTS_LIST, now=100.0)
    scheduler.mark_ran(EndpointGroupName.CLIENTS_APP_USAGE, now=100.0)

    assert scheduler.seconds_until_due(
        [group.name for group in _collector(settings).get_endpoint_groups()], now=100.0
    ) == pytest.approx(270.0)


@pytest.mark.asyncio
async def test_703_outer_loop_uses_the_client_due_interval_not_one_second_floor() -> None:
    """The production outer loop sleeps 270s after default client local work succeeds."""
    settings = _settings(signal_quality_enabled=False)
    scheduler = EndpointScheduler(settings, _Limiter())  # type: ignore[arg-type]
    collector = _collector(settings)
    scheduler.register_groups(collector.get_endpoint_groups())
    scheduler.resolve(_shape(wireless_networks=1))

    exporter = object.__new__(ExporterApp)
    exporter._shutdown_event = asyncio.Event()
    exporter.settings = settings  # type: ignore[assignment]
    waits: list[float] = []

    async def run_once(_: object) -> None:
        now = time.monotonic()
        scheduler.mark_ran(EndpointGroupName.CLIENTS_LIST, now=now)
        scheduler.mark_ran(EndpointGroupName.CLIENTS_APP_USAGE, now=now)

    async def sleep(seconds: float) -> None:
        waits.append(seconds)
        exporter._shutdown_event.set()

    exporter.collector_manager = SimpleNamespace(  # type: ignore[assignment]
        scheduler=scheduler, run_collector_once=run_once
    )
    exporter._interruptible_sleep = sleep  # type: ignore[method-assign]

    await exporter._collector_loop(collector, initial_run_completed=False)

    assert waits == [pytest.approx(270.0)]


@pytest.mark.asyncio
async def test_703_local_application_usage_marks_its_scheduler_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful application collection closes the scheduler gate, rather than remaining due."""
    settings = _settings()
    settings.clients.application_top_n = 20
    settings.clients.application_allowlist = []
    settings.clients.application_other_bucket = True
    collector = _collector(settings)
    collector.api = MagicMock()
    collector._last_app_usage_by_network = {}
    collector._group_interval = MagicMock(return_value=600.0)  # type: ignore[method-assign]
    collector._group_ttl_seconds = MagicMock(return_value=1200.0)  # type: ignore[method-assign]
    collector._set_metric = MagicMock()  # type: ignore[method-assign]
    collector.client_app_usage_sent = MagicMock()
    collector.client_app_usage_recv = MagicMock()
    collector.client_app_usage_total = MagicMock()
    collector._track_api_call = MagicMock()  # type: ignore[method-assign]
    collector._track_error = MagicMock()  # type: ignore[method-assign]
    marked: list[EndpointGroupName] = []
    collector._mark_group_ran = marked.append  # type: ignore[assignment, method-assign]

    class _Facade:
        async def call(self, *_: object, **__: object) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(
        "meraki_dashboard_exporter.collectors.clients.facade_for", lambda _: _Facade()
    )
    client = NetworkClient.model_validate({
        "id": "client-703",
        "mac": "00:00:00:00:00:01",
        "firstSeen": "2026-08-13T00:00:00Z",
        "lastSeen": "2026-08-13T00:00:00Z",
    })

    await collector._collect_application_usage("org", "Org", "network", "Network", [client])

    assert marked == [EndpointGroupName.CLIENTS_APP_USAGE]
