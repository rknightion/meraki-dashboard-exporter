"""Regression tests for discovery's metered API facade boundary (#723)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Counter

from meraki_dashboard_exporter.core.api_facade import MerakiApiFacade
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.discovery import DiscoveryService
from tests.helpers.factories import NetworkFactory, OrganizationFactory


def _settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    return Settings()


def _api_with_organizations(*organizations: dict[str, str]) -> MagicMock:
    api = MagicMock()
    api.organizations.getOrganizations.return_value = list(organizations)
    api.organizations.getOrganizationNetworks.return_value = [
        NetworkFactory.create(network_id="N_unfiltered", name="excluded-network")
    ]
    return api


@pytest.mark.asyncio
async def test_723_multi_org_discovery_uses_facade_and_preserves_unfiltered_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discovery meters every request but deliberately does not apply NetworkFilter."""
    settings = _settings(monkeypatch)
    settings.network_filter.exclude_names = ["excluded-*"]
    organizations = (
        OrganizationFactory.create(org_id="123", name="One"),
        OrganizationFactory.create(org_id="456", name="Two"),
    )
    api = _api_with_organizations(*organizations)

    attempts = Counter("test_723_attempts", "test", ["operation", "status"])
    requests = Counter("test_723_requests", "test", ["endpoint", "method", "status_code"])
    monkeypatch.setattr(MerakiApiFacade, "_attempts_total", attempts)
    monkeypatch.setattr(MerakiApiFacade, "_requests_total", requests)

    result = await DiscoveryService(api, settings).run_discovery()

    assert result["networks"]["123"]["count"] == 1
    assert result["networks"]["456"]["count"] == 1
    assert attempts.labels(operation="getOrganizations", status="200")._value.get() == 1
    assert attempts.labels(operation="getOrganizationNetworks", status="200")._value.get() == 2


@pytest.mark.asyncio
async def test_723_discovery_429_reaches_shared_limiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A discovery 429 reports feedback through the same limiter as collectors."""
    settings = _settings(monkeypatch)
    settings.meraki.org_id = "123"
    settings.api.max_retries = 1
    api = MagicMock()
    api.organizations.getOrganization.return_value = OrganizationFactory.create(org_id="123")

    class RateLimitedError(Exception):
        status = 429

    api.organizations.getOrganizationNetworks.side_effect = RateLimitedError()
    limiter = SimpleNamespace(
        acquire=AsyncMock(return_value=0.0), record_throttle_event=MagicMock()
    )
    sleep = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep)

    result = await DiscoveryService(api, settings, rate_limiter=limiter).run_discovery()

    assert "123: networks_fetch_failed" in result["errors"]
    limiter.record_throttle_event.assert_called_once_with("123", None)
