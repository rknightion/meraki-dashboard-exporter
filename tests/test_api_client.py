"""Tests for the AsyncMerakiClient wrapper."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.api.client import AsyncMerakiClient
from meraki_dashboard_exporter.core.config import Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = MagicMock()

    # Create nested mock objects
    settings.meraki = MagicMock()
    settings.meraki.api_key = SecretStr("test-api-key")
    settings.meraki.api_base_url = "https://api.meraki.com/api/v1"

    settings.api = MagicMock()
    settings.api.concurrency_limit = 5
    settings.api.timeout = 30
    settings.api.max_retries = 3
    settings.api.action_batch_retry_wait = 10
    settings.api.rate_limit_retry_wait = 5
    settings.api.validate_kwargs = False
    # #544: dedicated SDK executor sizing.
    settings.api.executor_workers = 4
    # #586: proxy + custom-CA settings default to None (unset -> env-var fallback).
    settings.api.requests_proxy = None
    settings.api.certificate_path = None

    return settings


@pytest.fixture
def mock_dashboard_api() -> Mock:
    """Create mock DashboardAPI instance."""
    api = MagicMock()

    # Mock organization endpoints
    api.organizations.getOrganizations = MagicMock(return_value=[])
    api.organizations.getOrganization = MagicMock(return_value={})
    api.organizations.getOrganizationNetworks = MagicMock(return_value=[])
    api.organizations.getOrganizationDevices = MagicMock(return_value=[])
    api.organizations.getOrganizationDevicesAvailabilities = MagicMock(return_value=[])
    api.organizations.getOrganizationLicenses = MagicMock(return_value=[])
    api.organizations.getOrganizationApiRequests = MagicMock(return_value=[])

    # Mock device endpoints
    api.switch.getDeviceSwitchPortsStatuses = MagicMock(return_value=[])
    api.wireless.getDeviceWirelessStatus = MagicMock(return_value={})

    # Mock sensor endpoints
    api.sensor.getOrganizationSensorReadingsLatest = MagicMock(return_value=[])

    return api


class TestAsyncMerakiClientInitialization:
    """Test client initialization and configuration."""

    def test_init_with_settings(self, mock_settings: Settings) -> None:
        """Test client initialization with settings."""
        client = AsyncMerakiClient(mock_settings)

        assert client.settings == mock_settings
        assert client._api is None
        assert isinstance(client._api_lock, asyncio.Lock)
        assert client._api_call_count == 0
        # #544: the dead, never-acquired semaphore was removed; the dedicated
        # executor is the real global concurrency ceiling for SDK calls.
        assert not hasattr(client, "_semaphore")
        client._executor.shutdown(wait=False)

    def test_dedicated_executor_sized_from_settings(self, mock_settings: Settings) -> None:
        """#544: the client owns a dedicated SDK executor sized by settings."""
        client = AsyncMerakiClient(mock_settings)
        try:
            assert isinstance(client.executor, ThreadPoolExecutor)
            assert client.executor._max_workers == 4
            assert client.executor._thread_name_prefix == "meraki-sdk"
        finally:
            client.executor.shutdown(wait=False)

    def test_dedicated_executor_default_when_field_missing(self) -> None:
        """Pre-seam settings (no executor_workers field) fall back to 10 workers."""
        settings = SimpleNamespace(
            meraki=SimpleNamespace(
                api_key=SecretStr("test-api-key"),
                api_base_url="https://api.meraki.com/api/v1",
            ),
            api=SimpleNamespace(
                concurrency_limit=5,
                timeout=30,
                max_retries=3,
            ),
        )
        client = AsyncMerakiClient(settings)  # type: ignore[arg-type]
        try:
            assert client.executor._max_workers == 10
        finally:
            client.executor.shutdown(wait=False)

    @patch("meraki_dashboard_exporter.api.client.meraki.DashboardAPI")
    def test_api_property_lazy_initialization(
        self,
        mock_dashboard_class: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test API client is created lazily on first access."""
        mock_dashboard_class.return_value = mock_dashboard_api

        client = AsyncMerakiClient(mock_settings)
        assert client._api is None

        # First access creates the API
        api = client.api
        assert api == mock_dashboard_api
        assert client._api == mock_dashboard_api

        # Verify initialization parameters
        mock_dashboard_class.assert_called_once_with(
            api_key="test-api-key",
            base_url="https://api.meraki.com/api/v1",
            output_log=False,
            # #633: the SDK's own logger is suppressed so the exporter's
            # @log_api_call is the single owner of API-call logging (benign 4xx
            # like the mesh 404 are logged once, at debug, not double-logged).
            suppress_logging=True,
            inherit_logging_config=True,
            single_request_timeout=30,
            maximum_retries=3,
            action_batch_retry_wait_time=10,
            nginx_429_retry_wait_time=5,
            # #545: the exporter's with_error_handling is the single 429 retry
            # owner; the SDK's unbounded in-thread Retry-After sleep is disabled.
            wait_on_rate_limit=False,
            retry_4xx_error=False,
            caller="merakidashboardexporter rknightion",
            validate_kwargs=False,
            requests_proxy=None,
            certificate_path=None,
        )

    @patch("meraki_dashboard_exporter.api.client.meraki.DashboardAPI")
    def test_api_property_reuses_instance(
        self,
        mock_dashboard_class: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test API property reuses existing instance."""
        mock_dashboard_class.return_value = mock_dashboard_api

        client = AsyncMerakiClient(mock_settings)

        # Multiple accesses should return same instance
        api1 = client.api
        api2 = client.api

        assert api1 == api2
        assert mock_dashboard_class.call_count == 1


class TestProxyAndCustomCA:
    """#586: first-class proxy + custom-CA support wired through to the SDK."""

    @patch("meraki_dashboard_exporter.api.client.meraki.DashboardAPI")
    def test_proxy_and_ca_passed_to_sdk(
        self,
        mock_dashboard_class: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """When configured, requests_proxy/certificate_path reach DashboardAPI."""
        mock_dashboard_class.return_value = mock_dashboard_api
        mock_settings.api.requests_proxy = "http://proxy.corp.example:3128"
        mock_settings.api.certificate_path = "/etc/ssl/corp-ca.pem"

        client = AsyncMerakiClient(mock_settings)
        _ = client.api

        _, kwargs = mock_dashboard_class.call_args
        assert kwargs["requests_proxy"] == "http://proxy.corp.example:3128"
        assert kwargs["certificate_path"] == "/etc/ssl/corp-ca.pem"

    @patch("meraki_dashboard_exporter.api.client.meraki.DashboardAPI")
    def test_proxy_and_ca_default_none_preserves_env_fallback(
        self,
        mock_dashboard_class: Mock,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Unset (None) proxy/CA are forwarded as None so the SDK ignores them.

        The Meraki SDK guards both with a truthiness check
        (``if self._requests_proxy:``), so a None/empty value leaves the
        underlying ``requests`` session to honour ``HTTPS_PROXY``/``NO_PROXY``.
        """
        mock_dashboard_class.return_value = mock_dashboard_api

        client = AsyncMerakiClient(mock_settings)
        _ = client.api

        _, kwargs = mock_dashboard_class.call_args
        assert kwargs["requests_proxy"] is None
        assert kwargs["certificate_path"] is None


class TestClientLifecycle:
    """Test client lifecycle management."""

    @pytest.mark.asyncio
    async def test_close_client(
        self,
        mock_settings: Settings,
        mock_dashboard_api: Mock,
    ) -> None:
        """Test closing the client."""
        client = AsyncMerakiClient(mock_settings)

        # Force API creation
        with patch(
            "meraki_dashboard_exporter.api.client.meraki.DashboardAPI",
            return_value=mock_dashboard_api,
        ):
            _ = client.api
            assert client._api is not None

        # Close should clear the API instance and shut down the SDK executor.
        await client.close()
        assert client._api is None
        assert client.executor._shutdown


class TestApiRequestTotalAccessor:
    """F-028/F-074: expose the real Meraki API request total for /status."""

    def test_get_total_api_requests_reflects_increments(self, mock_settings: Settings) -> None:
        """The accessor sums the shared request counter across all labels.

        The legacy ``_api_call_count`` attribute was never incremented, so
        /status always reported zero. ``get_total_api_requests`` reads the real
        ``_api_requests_total`` counter that inventory increments per call.
        """
        client = AsyncMerakiClient(mock_settings)

        before = client.get_total_api_requests()

        assert AsyncMerakiClient._api_requests_total is not None
        AsyncMerakiClient._api_requests_total.labels(
            endpoint="getOrganizations", method="GET", status_code="200"
        ).inc()
        AsyncMerakiClient._api_requests_total.labels(
            endpoint="getOrganizationDevices", method="GET", status_code="200"
        ).inc(2)

        assert client.get_total_api_requests() == before + 3


class TestAuthOutcomeLatch:
    """#509: auth-outcome latch used for /status `authenticated` and readiness."""

    def test_auth_outcome_latch(self) -> None:
        """get_auth_ok() tracks record_auth_outcome()/reset_auth_state()."""
        AsyncMerakiClient.reset_auth_state()
        assert AsyncMerakiClient.get_auth_ok() is None

        AsyncMerakiClient.record_auth_outcome(False)
        assert AsyncMerakiClient.get_auth_ok() is False

        AsyncMerakiClient.record_auth_outcome(True)
        assert AsyncMerakiClient.get_auth_ok() is True

        AsyncMerakiClient.reset_auth_state()
        assert AsyncMerakiClient.get_auth_ok() is None

    def test_get_successful_api_requests_counts_only_200(self, mock_settings: Settings) -> None:
        """get_successful_api_requests sums only status_code=200 samples."""
        client = AsyncMerakiClient(mock_settings)

        before = client.get_successful_api_requests()

        assert AsyncMerakiClient._api_requests_total is not None
        AsyncMerakiClient._api_requests_total.labels(
            endpoint="getOrganizations", method="GET", status_code="200"
        ).inc(2)
        AsyncMerakiClient._api_requests_total.labels(
            endpoint="getOrganizations", method="GET", status_code="401"
        ).inc(5)

        assert client.get_successful_api_requests() == before + 2


class Test429StormThreadIsolation:
    """#545 x #544: bounded 429 backoff must not hold SDK executor threads.

    With ``wait_on_rate_limit=False`` the SDK raises immediately on a 429 (no
    in-thread ``Retry-After`` sleep), and the exporter's retry owner waits on
    the *event loop* - so even a 1-worker SDK executor stays free for other
    work during the backoff.
    """

    @pytest.mark.asyncio
    async def test_backoff_does_not_hold_executor_thread(self) -> None:
        """During a simulated 429 storm the sole executor thread stays free."""
        from meraki_dashboard_exporter.core.error_handling import with_error_handling

        class _RateLimitedError(Exception):
            status = 429
            retry_after = 0.3

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meraki-sdk-test")
        loop = asyncio.get_running_loop()
        loop.set_default_executor(executor)

        attempts = 0

        def fake_sdk_call() -> str:
            # Mimics the SDK with wait_on_rate_limit=False: raises the 429
            # immediately instead of sleeping Retry-After in the worker thread.
            nonlocal attempts
            attempts += 1
            raise _RateLimitedError("429 Too Many Requests")

        instance = SimpleNamespace(
            settings=SimpleNamespace(
                api=SimpleNamespace(retry_after_max_seconds=60, per_fetch_deadline_seconds=120)
            )
        )

        @with_error_handling(operation="Storm fetch", continue_on_error=True, max_retries=1)
        async def fetch(self: SimpleNamespace) -> str:
            return await asyncio.to_thread(fake_sdk_call)

        async def probe_executor_free() -> float:
            """Measure how long a trivial job queues behind the fetch's thread."""
            start = time.monotonic()
            await asyncio.to_thread(lambda: None)
            return time.monotonic() - start

        fetch_task = asyncio.create_task(fetch(instance))
        # Let the first attempt raise and the ~0.3s event-loop backoff begin.
        await asyncio.sleep(0.1)

        probe_wait = await probe_executor_free()

        result = await fetch_task
        executor.shutdown(wait=False)

        assert result is None
        # 1 initial + 1 retry HTTP attempt - not multiplied by SDK retries.
        assert attempts == 2
        # The probe ran while the fetch was mid-backoff: had the worker thread
        # been held sleeping Retry-After, it would have queued ~0.2s+.
        assert probe_wait < 0.15
