"""Tests for the :class:`DNSResolver` service."""

# ruff: noqa: S101

import asyncio
import threading
from unittest.mock import MagicMock

import pytest
from structlog.testing import capture_logs

from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.services.dns_resolver import DNSResolver


@pytest.fixture
def resolver(monkeypatch):
    """Create a resolver instance with default settings."""

    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    settings = Settings()
    return DNSResolver(settings)


@pytest.mark.asyncio
async def test_resolve_hostname_caches_result(resolver, monkeypatch):
    """Repeated lookups should hit the cache."""

    calls = 0

    async def fake_lookup(ip: str) -> str:
        nonlocal calls
        calls += 1
        return "example.com"

    monkeypatch.setattr(resolver, "_perform_lookup", fake_lookup)

    host1 = await resolver.resolve_hostname("1.1.1.1")
    host2 = await resolver.resolve_hostname("1.1.1.1")

    assert host1 == "example"
    assert host2 == "example"
    assert calls == 1
    assert resolver.cache_size == 1


@pytest.mark.asyncio
async def test_resolve_hostname_invalid_ip(resolver, monkeypatch):
    """Invalid IP addresses return ``None`` without lookup."""

    called = False

    async def fake_lookup(ip: str) -> str:
        nonlocal called
        called = True
        return "should-not-call"

    monkeypatch.setattr(resolver, "_perform_lookup", fake_lookup)

    result = await resolver.resolve_hostname("not-an-ip")

    assert result is None
    assert resolver.cache_size == 1
    assert called is False


@pytest.mark.asyncio
async def test_resolve_multiple_uses_resolver(monkeypatch, resolver):
    """``resolve_multiple`` should delegate to :meth:`resolve_hostname`."""

    calls: list[str] = []

    async def fake_resolve(ip: str, client_id: str | None = None) -> str:
        calls.append(ip)
        return ip.split(".", maxsplit=1)[0]

    monkeypatch.setattr(resolver, "resolve_hostname", fake_resolve)

    result = await resolver.resolve_multiple([
        ("c1", "1.1.1.1", None),
        ("c2", "2.2.2.2", None),
    ])

    assert calls == ["1.1.1.1", "2.2.2.2"]
    assert result == {"1.1.1.1": "1", "2.2.2.2": "2"}


@pytest.mark.asyncio
async def test_resolve_multiple_reports_producer_backlog_not_handoff_queue(resolver, monkeypatch):
    """The backlog metric distinguishes a small batch from a fleet-sized batch."""

    async def fake_resolve(ip: str, client_id: str | None = None) -> str:
        return ip

    monkeypatch.setattr(resolver, "resolve_hostname", fake_resolve)

    await resolver.resolve_multiple([("small", "192.0.2.1", None)])
    assert resolver.get_cache_stats()["queue_peak_depth"] == 1

    fleet_batch = [(f"client-{i}", f"192.0.2.{i + 1}", None) for i in range(40)]
    await resolver.resolve_multiple(fleet_batch)
    assert resolver.get_cache_stats()["queue_peak_depth"] == len(fleet_batch)


@pytest.mark.asyncio
async def test_overlapping_batches_cannot_overwrite_newer_backlog_measurement(
    resolver, monkeypatch
):
    """A late-finishing old batch must not reset a later batch's backlog value."""

    resolver.max_concurrent_lookups = 1
    old_batch_started = asyncio.Event()
    release_old_batch = asyncio.Event()

    async def fake_resolve(ip: str, client_id: str | None = None) -> str:
        if ip.startswith("198.51.100."):
            old_batch_started.set()
            await release_old_batch.wait()
        return ip

    monkeypatch.setattr(resolver, "resolve_hostname", fake_resolve)

    old_batch = asyncio.create_task(
        resolver.resolve_multiple([(f"old-{i}", f"198.51.100.{i + 1}", None) for i in range(3)])
    )
    await old_batch_started.wait()
    await resolver.resolve_multiple([("new", "203.0.113.1", None)])
    assert resolver.get_cache_stats()["queue_peak_depth"] == 1

    release_old_batch.set()
    await old_batch
    assert resolver.get_cache_stats()["queue_peak_depth"] == 1


@pytest.mark.asyncio
async def test_perform_lookup_applies_timeout(monkeypatch, resolver):
    """Reverse lookups are always bounded by the configured dns_timeout (F-076)."""
    import meraki_dashboard_exporter.services.dns_resolver as dns_mod

    captured: dict[str, float] = {}

    async def fake_wait_for(coro, timeout):
        captured["timeout"] = timeout
        coro.close()  # avoid un-awaited coroutine warning
        return "host.example.com"

    monkeypatch.setattr(dns_mod.asyncio, "wait_for", fake_wait_for)

    result = await resolver._perform_lookup("1.1.1.1")

    assert result.hostname == "host.example.com"
    assert captured["timeout"] == resolver.timeout


@pytest.mark.asyncio
async def test_timeout_is_not_counted_as_resolver_failure_or_logged_with_ip(
    resolver, monkeypatch, force_debug_log_capture
):
    """Deadline expiry increments only the timeout outcome and keeps logs identifier-free."""

    resolver.timeout = 0.001

    async def slow_system_lookup(ip: str) -> str | None:
        await asyncio.sleep(0.01)
        return "host.example.com"

    monkeypatch.setattr(resolver, "_system_dns_lookup", slow_system_lookup)
    client_ip = "198.51.100.42"

    with capture_logs() as captured:
        assert await resolver.resolve_hostname(client_ip, client_id="private-client-id") is None

    stats = resolver.get_cache_stats()
    assert stats["lookup_timeouts"] == 1
    assert stats["failed_lookups"] == 0
    warning = next(event for event in captured if event["event"] == "Reverse DNS lookup timed out")
    assert warning["log_level"] == "warning"
    assert all(
        value not in str(event)
        for event in captured
        if event["log_level"] in {"info", "warning", "error"}
        for value in {client_ip, "private-client-id"}
    )


@pytest.mark.asyncio
async def test_resolver_exception_is_not_counted_as_timeout(resolver, monkeypatch):
    """A resolver exception uses the existing non-timeout failure outcome."""

    async def failing_system_lookup(ip: str) -> str | None:
        raise RuntimeError(f"resolver rejected {ip}")

    monkeypatch.setattr(resolver, "_system_dns_lookup", failing_system_lookup)

    assert await resolver.resolve_hostname("198.51.100.43") is None

    stats = resolver.get_cache_stats()
    assert stats["lookup_timeouts"] == 0
    assert stats["failed_lookups"] == 1


@pytest.mark.asyncio
async def test_system_dns_lookup_uses_dedicated_executor(monkeypatch, resolver):
    """Blocking reverse-DNS runs on the resolver's own pool, not the loop default (F-075).

    Routing gethostbyaddr through the default executor (run_in_executor(None, ...))
    would share the pool with asyncio.to_thread() Meraki API calls; a hung,
    un-cancellable lookup could then starve API collection. The resolver owns a
    dedicated bounded ThreadPoolExecutor instead.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import meraki_dashboard_exporter.services.dns_resolver as dns_mod

    # A dedicated, bounded executor exists.
    assert isinstance(resolver._executor, ThreadPoolExecutor)

    thread_names: list[str] = []

    def fake_gethostbyaddr(ip: str):
        thread_names.append(threading.current_thread().name)
        return ("host.example.com", [], [ip])

    monkeypatch.setattr(dns_mod.socket, "gethostbyaddr", fake_gethostbyaddr)

    result = await resolver._system_dns_lookup("1.1.1.1")

    assert result == "host.example.com"
    # Ran on a thread from the dedicated pool, not a default-executor thread.
    assert thread_names
    assert thread_names[0].startswith("dns-resolver")


@pytest.mark.asyncio
async def test_close_drains_dedicated_lookup_executor(resolver):
    """Shutdown joins reverse-DNS workers before the process exits."""
    executor = MagicMock()
    resolver._executor = executor

    assert await resolver.close() is True
    assert await resolver.close() is True

    executor.shutdown.assert_called_once_with(wait=True, cancel_futures=True)


@pytest.mark.asyncio
async def test_close_bounds_blocked_lookup_without_freezing_loop(resolver):
    """A stuck resolver thread is abandoned after the deadline while asyncio keeps running."""
    release = threading.Event()
    started = threading.Event()

    def blocked_lookup() -> None:
        started.set()
        release.wait()

    worker = resolver._executor.submit(blocked_lookup)
    assert started.wait(timeout=1.0)
    heartbeat_ticks = 0

    async def heartbeat() -> None:
        nonlocal heartbeat_ticks
        while True:
            heartbeat_ticks += 1
            await asyncio.sleep(0.005)

    heartbeat_task = asyncio.create_task(heartbeat())
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    try:
        assert await resolver.close(timeout_seconds=0.05) is False
        assert await resolver.close(timeout_seconds=0.05) is False
        assert loop.time() - started_at < 0.15
        assert heartbeat_ticks >= 3
    finally:
        heartbeat_task.cancel()
        release.set()
        await asyncio.to_thread(worker.result, 1.0)


@pytest.mark.asyncio
async def test_clear_cache(monkeypatch, resolver):
    """Cache can be cleared manually."""

    async def fake_lookup(ip: str) -> str:
        return "example.com"

    monkeypatch.setattr(resolver, "_perform_lookup", fake_lookup)
    await resolver.resolve_hostname("1.1.1.1")
    assert resolver.cache_size == 1

    resolver.clear_cache()
    assert resolver.cache_size == 0


@pytest.mark.asyncio
async def test_clear_cache_discards_in_flight_resolution(resolver, monkeypatch):
    """A lookup started before clear cannot repopulate cache or statistics."""

    resolver.max_concurrent_lookups = 1
    lookup_started = asyncio.Event()
    release_lookup = asyncio.Event()

    async def blocked_lookup(ip: str) -> str:
        lookup_started.set()
        await release_lookup.wait()
        return "pre-clear.example.com"

    monkeypatch.setattr(resolver, "_perform_lookup", blocked_lookup)

    resolution = asyncio.create_task(
        resolver.resolve_multiple([("client", "192.0.2.1", "description")])
    )
    await lookup_started.wait()
    assert resolver.get_cache_stats()["total_lookups"] == 1

    resolver.clear_cache()
    release_lookup.set()
    assert await resolution == {}

    stats = resolver.get_cache_stats()
    assert resolver._cache == {}
    assert stats["total_entries"] == 0
    assert stats["valid_entries"] == 0
    assert stats["expired_entries"] == 0
    assert stats["tracked_clients"] == 0
    assert stats["total_lookups"] == 0
    assert stats["successful_lookups"] == 0
    assert stats["failed_lookups"] == 0
    assert stats["cache_hits"] == 0
    assert stats["cache_hit_ratio"] == 0.0
    assert stats["total_resolution_time"] == 0.0
    assert stats["queue_wait_seconds"] == 0.0
    assert stats["queue_wait_count"] == 0
    assert stats["queue_peak_depth"] == 0
    assert stats["lookup_timeouts"] == 0


@pytest.mark.asyncio
async def test_cache_is_bounded_under_churn(monkeypatch):
    """#543: the reverse-DNS cache must stay bounded under unique-IP churn."""

    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    settings = Settings()
    settings.clients.dns_cache_max_entries = 10
    resolver = DNSResolver(settings)

    async def fake_lookup(ip: str) -> str:
        return "host.example.com"

    monkeypatch.setattr(resolver, "_perform_lookup", fake_lookup)

    for i in range(500):
        await resolver.resolve_hostname(f"10.0.{i // 256}.{i % 256}")

    assert resolver.cache_size <= 10


@pytest.mark.asyncio
async def test_client_tracking_is_bounded_under_churn(monkeypatch):
    """#543: per-client IP tracking must stay bounded under client churn."""

    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    settings = Settings()
    settings.clients.dns_cache_max_entries = 10
    resolver = DNSResolver(settings)

    for i in range(500):
        resolver.track_client(f"client-{i}", f"10.0.{i // 256}.{i % 256}", "desc")

    assert len(resolver._client_tracking) <= 10


@pytest.mark.asyncio
async def test_stats_expose_hit_ratio_and_resolution_time(resolver, monkeypatch):
    """#319: cache-hit ratio and cumulative resolution time are exposed for metrics."""

    async def fake_lookup(ip: str) -> str:
        return "example.com"

    monkeypatch.setattr(resolver, "_perform_lookup", fake_lookup)

    await resolver.resolve_hostname("1.1.1.1")  # miss -> real lookup
    await resolver.resolve_hostname("1.1.1.1")  # served from cache

    stats = resolver.get_cache_stats()
    assert stats["total_lookups"] == 2
    assert stats["cache_hits"] == 1
    assert stats["cache_hit_ratio"] == 0.5
    assert stats["total_resolution_time"] >= 0.0


@pytest.mark.asyncio
async def test_clear_cache_resets_resolution_time(resolver, monkeypatch):
    """clear_cache resets the cumulative resolution timer (#319)."""

    async def fake_lookup(ip: str) -> str:
        return "example.com"

    monkeypatch.setattr(resolver, "_perform_lookup", fake_lookup)
    await resolver.resolve_hostname("1.1.1.1")

    resolver.clear_cache()
    stats = resolver.get_cache_stats()
    assert stats["total_resolution_time"] == 0.0
    assert stats["cache_hit_ratio"] == 0.0
