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
async def test_clear_cache(monkeypatch, resolver):
    """Cache can be cleared manually."""

    async def fake_lookup(ip: str) -> str:
        return "example.com"

    monkeypatch.setattr(resolver, "_perform_lookup", fake_lookup)
    await resolver.resolve_hostname("1.1.1.1")
    assert resolver.cache_size == 1

    resolver.clear_cache()
    assert resolver.cache_size == 0
