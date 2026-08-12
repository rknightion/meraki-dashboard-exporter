"""Transport-boundary tests for issues #697 and #698."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from meraki_dashboard_exporter.api import client as client_module
from meraki_dashboard_exporter.core.api_facade import FacadeRateLimitExhaustedError, MerakiApiFacade
from meraki_dashboard_exporter.core.error_handling import with_error_handling


@pytest.mark.asyncio
async def test_698_facade_acquires_one_limiter_token_before_the_sdk_attempt() -> None:
    """The facade, rather than a caller, owns the outbound pacing token."""
    limiter = SimpleNamespace(acquire=AsyncMock(return_value=0.0))
    facade = MerakiApiFacade(rate_limiter=limiter)

    assert await facade.call("getOrganization", lambda org_id: {"id": org_id}, "123") == {
        "id": "123"
    }
    limiter.acquire.assert_awaited_once_with("123", "getOrganization")


@pytest.mark.asyncio
async def test_698_facade_does_not_re_expose_an_exhausted_429_to_outer_retry_layers() -> None:
    """Facade exhaustion is terminal so decorators cannot become a second owner."""
    settings = SimpleNamespace(api=SimpleNamespace(max_retries=0, per_fetch_deadline_seconds=1))
    facade = MerakiApiFacade(settings=settings)

    class RateLimitedError(Exception):
        status = 429

    def request() -> None:
        raise RateLimitedError

    with pytest.raises(FacadeRateLimitExhaustedError):
        await facade.call("getOrganization", request)


@pytest.mark.asyncio
async def test_698_error_decorator_does_not_retry_facade_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The legacy decorator treats the facade terminal error as a final 429."""
    sleep = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep)

    class Owner:
        @with_error_handling(operation="fetch", max_retries=3)
        async def fetch(self) -> None:
            raise FacadeRateLimitExhaustedError("getOrganization exhausted facade attempts")

    assert await Owner().fetch() is None
    sleep.assert_not_awaited()


def _session_for_redirect_test() -> SimpleNamespace:
    client = httpx.Client(
        headers={"Authorization": "Bearer secret"},
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
    )
    session = SimpleNamespace(
        _base_url="https://api.meraki.com/api/v1",
        _client=client,
    )

    def send_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        return client.request(method, url, **kwargs)

    session._send_request = send_request
    return session


def test_697_same_origin_redirect_retains_authorization() -> None:
    """A regional same-origin redirect remains an authenticated SDK request."""
    session = _session_for_redirect_test()
    client_module._install_redirect_auth_boundary(SimpleNamespace(_session=session))
    request = httpx.Request("GET", "https://api.meraki.com/api/v1/organizations")
    response = session._send_request("GET", str(request.url))

    assert response.request.headers["Authorization"] == "Bearer secret"


def test_697_explicit_default_https_port_is_same_origin() -> None:
    """An explicit default port does not create a false redirect boundary."""
    session = _session_for_redirect_test()
    client_module._install_redirect_auth_boundary(SimpleNamespace(_session=session))
    response = session._send_request("GET", "https://api.meraki.com:443/api/v1/organizations")

    assert response.request.headers["Authorization"] == "Bearer secret"


def test_697_cross_origin_redirect_strips_authorization() -> None:
    """Authorization cannot traverse an origin boundary through ``Location``."""
    session = _session_for_redirect_test()
    client_module._install_redirect_auth_boundary(SimpleNamespace(_session=session))
    response = session._send_request("GET", "https://attacker.invalid/collect")

    assert "Authorization" not in response.request.headers
