"""Regression contracts for the paced Meraki SDK facade."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Counter

from meraki_dashboard_exporter.api.client import AsyncMerakiClient
from meraki_dashboard_exporter.core.api_facade import (
    FacadeRateLimiterUnavailableError,
    MerakiApiFacade,
    facade_for,
)


@pytest.fixture
def metric_facade(monkeypatch: pytest.MonkeyPatch) -> MerakiApiFacade:
    """Provide isolated facade counters for each metric-contract test."""
    attempts = Counter("test_facade_attempts", "test", ["operation", "status"])
    requests = Counter("test_facade_requests", "test", ["endpoint", "method", "status_code"])
    retries = Counter("test_facade_retries", "test", ["endpoint", "retry_reason"])
    monkeypatch.setattr(MerakiApiFacade, "_attempts_total", attempts)
    monkeypatch.setattr(MerakiApiFacade, "_requests_total", requests)
    monkeypatch.setattr(AsyncMerakiClient, "_api_retry_attempts", retries)
    return MerakiApiFacade(
        settings=SimpleNamespace(
            api=SimpleNamespace(
                max_retries=1,
                per_fetch_deadline_seconds=30,
                retry_after_max_seconds=7,
            )
        ),
        rate_limiter=SimpleNamespace(
            acquire=AsyncMock(return_value=0.0),
            record_throttle_event=MagicMock(),
        ),
    )


@pytest.mark.asyncio
async def test_facade_paces_explicit_org_without_forwarding_it_to_sdk(
    metric_facade: MerakiApiFacade,
) -> None:
    """The pacing key is explicit facade metadata, not an SDK keyword argument."""
    sdk_call = MagicMock(return_value=[])

    assert (
        await metric_facade.call(
            "getNetworkSwitchLinkAggregations",
            sdk_call,
            "network-id",
            org_id="org-id",
        )
        == []
    )

    limiter = metric_facade._rate_limiter
    limiter.acquire.assert_awaited_once_with("org-id", "getNetworkSwitchLinkAggregations")
    sdk_call.assert_called_once_with("network-id")
    requests = MerakiApiFacade._requests_total
    assert requests is not None
    assert (
        requests.labels(
            endpoint="getNetworkSwitchLinkAggregations", method="GET", status_code="200"
        )._value.get()
        == 1
    )


@pytest.mark.asyncio
async def test_network_identifier_is_never_inferred_as_an_organization(
    metric_facade: MerakiApiFacade,
) -> None:
    """Network-shaped strings must not select an organization limiter bucket."""
    sdk_call = MagicMock(return_value=[])
    network_id = "N_1234567890123456"

    await metric_facade.call("getNetworkSwitchStp", sdk_call, network_id)

    limiter = metric_facade._rate_limiter
    limiter.acquire.assert_awaited_once_with(None, "getNetworkSwitchStp")


@pytest.mark.asyncio
@pytest.mark.strict_facade_limiter
async def test_unresolved_limiter_fails_before_an_unpaced_sdk_call() -> None:
    """A broken owner tree must fail closed instead of silently bypassing pacing."""
    sdk_call = MagicMock(return_value=[])
    facade = MerakiApiFacade(settings=SimpleNamespace(api=SimpleNamespace()), rate_limiter=None)

    with pytest.raises(FacadeRateLimiterUnavailableError):
        await facade.call("getOrganizations", sdk_call)

    sdk_call.assert_not_called()


@pytest.mark.asyncio
async def test_facade_for_resolves_parent_tree_limiter() -> None:
    """Sub-collector facade owners inherit the coordinator's configured limiter."""
    limiter = SimpleNamespace(
        acquire=AsyncMock(return_value=0.0), record_throttle_event=MagicMock()
    )
    owner = SimpleNamespace(parent=SimpleNamespace(parent=SimpleNamespace(rate_limiter=limiter)))
    sdk_call = MagicMock(return_value=[])

    await facade_for(owner).call("getOrganizationDevices", sdk_call, "org-id")

    limiter.acquire.assert_awaited_once_with("org-id", "getOrganizationDevices")


@pytest.mark.asyncio
async def test_facade_retry_records_one_compatibility_retry_and_honors_capped_retry_after(
    monkeypatch: pytest.MonkeyPatch, metric_facade: MerakiApiFacade
) -> None:
    """One 429 retry makes one counter increment and one jittered capped wait."""

    class RateLimitedError(Exception):
        status = 429
        retry_after = 99

    sdk_call = MagicMock(side_effect=[RateLimitedError(), []])
    sleep = AsyncMock()
    monkeypatch.setattr("meraki_dashboard_exporter.core.api_facade.asyncio.sleep", sleep)
    monkeypatch.setattr(
        "meraki_dashboard_exporter.core.api_facade._apply_jitter", lambda delay, _: delay
    )

    assert await metric_facade.call("getOrganizationDevices", sdk_call, "org-id") == []

    retries = AsyncMerakiClient._api_retry_attempts
    assert retries is not None
    assert (
        retries.labels(
            endpoint="getOrganizationDevices", retry_reason="http_429_rate_limit"
        )._value.get()
        == 1
    )
    metric_facade._rate_limiter.record_throttle_event.assert_called_once_with("org-id", 7.0)
    sleep.assert_awaited_once_with(7.0)


@pytest.mark.asyncio
async def test_facade_retry_uses_the_documented_ten_second_jittered_base(
    monkeypatch: pytest.MonkeyPatch, metric_facade: MerakiApiFacade
) -> None:
    """Absent Retry-After starts the facade's exponential sequence at ten seconds."""

    class RateLimitedError(Exception):
        status = 429

    sdk_call = MagicMock(side_effect=[RateLimitedError(), []])
    sleep = AsyncMock()
    monkeypatch.setattr("meraki_dashboard_exporter.core.api_facade.asyncio.sleep", sleep)
    monkeypatch.setattr(
        "meraki_dashboard_exporter.core.api_facade._apply_jitter", lambda delay, _: delay
    )

    assert await metric_facade.call("getOrganizationDevices", sdk_call, "org-id") == []

    sleep.assert_awaited_once_with(10.0)


@pytest.mark.asyncio
async def test_non_http_exception_is_an_attempt_outcome_not_an_http_status(
    metric_facade: MerakiApiFacade,
) -> None:
    """The compatibility HTTP counter never contains exception-class label values."""
    sdk_call = MagicMock(side_effect=RuntimeError("socket closed"))

    with pytest.raises(RuntimeError, match="socket closed"):
        await metric_facade.call("getOrganizationDevices", sdk_call, "org-id")

    attempts = MerakiApiFacade._attempts_total
    requests = MerakiApiFacade._requests_total
    assert attempts is not None
    assert requests is not None
    assert attempts.labels(operation="getOrganizationDevices", status="exception")._value.get() == 1
    assert requests.collect()[0].samples == []
