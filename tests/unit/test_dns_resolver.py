"""Tests for the :class:`DNSResolver` service."""

# ruff: noqa: S101

import pytest

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
async def test_perform_lookup_applies_timeout(monkeypatch, resolver):
    """Reverse lookups are always bounded by the configured dns_timeout (F-076)."""
    import meraki_dashboard_exporter.services.dns_resolver as dns_mod

    captured: dict[str, float] = {}

    async def fake_with_timeout(coro, timeout, operation="operation", default=None):
        captured["timeout"] = timeout
        coro.close()  # avoid un-awaited coroutine warning
        return "host.example.com"

    monkeypatch.setattr(dns_mod, "with_timeout", fake_with_timeout)

    result = await resolver._perform_lookup("1.1.1.1")

    assert result == "host.example.com"
    assert captured["timeout"] == resolver.timeout


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
