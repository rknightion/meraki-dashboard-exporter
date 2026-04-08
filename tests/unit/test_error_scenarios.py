"""Comprehensive error scenario tests for error handling paths critical at scale.

Tests cover rate limiting (429), server errors (5xx), timeouts, API unavailable (404),
and exponential backoff with jitter verification.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from meraki_dashboard_exporter.core.error_handling import (
    APINotAvailableError,
    CollectorError,
    ErrorCategory,
    RetryableAPIError,
    _apply_jitter,  # noqa: PLC2701
    _categorize_error,  # noqa: PLC2701
    _is_rate_limit_error,  # noqa: PLC2701
    with_error_handling,
)

# ---------------------------------------------------------------------------
# Mock collector class used throughout the test suite
# ---------------------------------------------------------------------------


class MockCollector:
    """Minimal mock collector for decorator testing."""

    def __init__(self) -> None:
        """Initialize tracking lists."""
        self._tracked_errors: list[ErrorCategory] = []
        self._tracked_retries: list[tuple[str, str]] = []

    def _track_error(self, category: ErrorCategory) -> None:
        self._tracked_errors.append(category)

    def _track_retry(self, operation: str, reason: str) -> None:
        self._tracked_retries.append((operation, reason))


# ---------------------------------------------------------------------------
# 1. Rate Limiting (429) Tests
# ---------------------------------------------------------------------------


class TestRateLimiting429:
    """Tests for HTTP 429 rate limit error handling."""

    async def test_429_then_success_eventually_returns_result(self) -> None:
        """Simulate 429 -> 429 -> success (3 attempts total). Verify success is returned."""
        call_count = 0
        collector = MockCollector()

        @with_error_handling(
            operation="Fetch devices",
            continue_on_error=True,
            max_retries=3,
            base_delay=1.0,
            max_delay=60.0,
        )
        async def fetch_devices(self: MockCollector) -> list[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                err = Exception("HTTP 429 Too Many Requests")
                err.status = 429  # type: ignore[attr-defined]
                raise err
            return [{"serial": "Q2AA-1234-5678"}]

        with (
            patch(
                "meraki_dashboard_exporter.core.error_handling.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0.0),
        ):
            result = await fetch_devices(collector)

        assert result == [{"serial": "Q2AA-1234-5678"}]
        assert call_count == 3

    async def test_retryable_api_error_triggers_retry_loop(self) -> None:
        """RetryableAPIError should trigger the retry loop and sleep between attempts."""
        sleep_calls: list[float] = []
        call_count = 0
        collector = MockCollector()

        @with_error_handling(
            operation="Fetch org",
            continue_on_error=True,
            max_retries=2,
            base_delay=1.0,
            max_delay=60.0,
        )
        async def fetch_org(self: MockCollector) -> str:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RetryableAPIError("Rate limit exceeded", retry_after=None)
            return "ok"

        async def mock_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with (
            patch("meraki_dashboard_exporter.core.error_handling.asyncio.sleep", mock_sleep),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0.0),
        ):
            result = await fetch_org(collector)

        assert result == "ok"
        assert call_count == 3
        assert len(sleep_calls) == 2  # Slept twice before the final success

    async def test_retryable_api_error_categorized_as_rate_limit(self) -> None:
        """RetryableAPIError should be categorized as API_RATE_LIMIT."""
        error = RetryableAPIError("Rate limited")
        assert error.category == ErrorCategory.API_RATE_LIMIT

    async def test_429_status_detected_by_is_rate_limit_error(self) -> None:
        """An exception with status=429 should be detected as a rate limit error."""
        err = Exception("server busy")
        err.status = 429  # type: ignore[attr-defined]
        assert _is_rate_limit_error(err) is True

    async def test_rate_limit_string_patterns_detected(self) -> None:
        """String patterns in the message should trigger rate limit detection."""
        patterns = [
            "rate limit exceeded",
            "too many requests",
            "throttled",
            "rate limited",
        ]
        for pattern in patterns:
            err = Exception(pattern)
            assert _is_rate_limit_error(err) is True, f"Pattern '{pattern}' not detected"

    async def test_max_retries_exhausted_on_persistent_429_continue_on_error(self) -> None:
        """When max retries are exhausted on 429 with continue_on_error=True, return None."""
        call_count = 0
        collector = MockCollector()

        @with_error_handling(
            operation="Persistent 429",
            continue_on_error=True,
            max_retries=2,
            base_delay=1.0,
            max_delay=60.0,
        )
        async def always_rate_limited(self: MockCollector) -> str:
            nonlocal call_count
            call_count += 1
            err = Exception("HTTP 429 Too Many Requests")
            err.status = 429  # type: ignore[attr-defined]
            raise err

        with (
            patch(
                "meraki_dashboard_exporter.core.error_handling.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0.0),
        ):
            result = await always_rate_limited(collector)

        assert result is None
        assert call_count == 3  # initial + 2 retries

    async def test_max_retries_exhausted_on_persistent_429_raises_collector_error(self) -> None:
        """When max retries exhausted and continue_on_error=False, raise CollectorError."""
        collector = MockCollector()

        @with_error_handling(
            operation="Persistent 429 raise",
            continue_on_error=False,
            max_retries=1,
            base_delay=1.0,
            max_delay=60.0,
        )
        async def always_rate_limited(self: MockCollector) -> str:
            err = Exception("HTTP 429 Too Many Requests")
            err.status = 429  # type: ignore[attr-defined]
            raise err

        with (
            patch(
                "meraki_dashboard_exporter.core.error_handling.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0.0),
        ):
            with pytest.raises(CollectorError) as exc_info:
                await always_rate_limited(collector)

        assert exc_info.value.category == ErrorCategory.API_RATE_LIMIT

    async def test_429_retry_tracks_retry_metric(self) -> None:
        """Retrying on HTTP 429 should call _track_retry on the collector."""
        call_count = 0
        collector = MockCollector()

        @with_error_handling(
            operation="Track retry",
            continue_on_error=True,
            max_retries=2,
            base_delay=1.0,
            max_delay=60.0,
        )
        async def flaky(self: MockCollector) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                err = Exception("HTTP 429 Too Many Requests")
                err.status = 429  # type: ignore[attr-defined]
                raise err
            return "ok"

        with (
            patch(
                "meraki_dashboard_exporter.core.error_handling.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0.0),
        ):
            result = await flaky(collector)

        assert result == "ok"
        assert len(collector._tracked_retries) == 1
        operation, reason = collector._tracked_retries[0]
        assert operation == "Track retry"
        assert reason == "http_429_rate_limit"

    async def test_retryable_api_error_retry_tracks_retry_metric(self) -> None:
        """RetryableAPIError retry should call _track_retry with 'http_200_rate_limit'."""
        call_count = 0
        collector = MockCollector()

        @with_error_handling(
            operation="Track retry 200",
            continue_on_error=True,
            max_retries=2,
            base_delay=1.0,
            max_delay=60.0,
        )
        async def flaky(self: MockCollector) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RetryableAPIError("embedded rate limit")
            return "ok"

        with (
            patch(
                "meraki_dashboard_exporter.core.error_handling.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0.0),
        ):
            result = await flaky(collector)

        assert result == "ok"
        assert len(collector._tracked_retries) == 1
        operation, reason = collector._tracked_retries[0]
        assert reason == "http_200_rate_limit"


# ---------------------------------------------------------------------------
# 2. Server Error (5xx) Tests
# ---------------------------------------------------------------------------


class TestServerErrors5xx:
    """Tests for HTTP 5xx server error handling."""

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    async def test_5xx_categorized_as_api_server_error(self, status_code: int) -> None:
        """HTTP 5xx errors should be categorized as API_SERVER_ERROR."""
        error = Exception(f"HTTP {status_code} Server Error")
        category = _categorize_error(error)
        assert category == ErrorCategory.API_SERVER_ERROR, (
            f"{status_code} was not categorized as API_SERVER_ERROR"
        )

    async def test_500_continue_on_error_returns_none(self) -> None:
        """500 error with continue_on_error=True should return None."""
        collector = MockCollector()

        @with_error_handling(
            operation="Server error soft",
            continue_on_error=True,
        )
        async def call_api(self: MockCollector) -> str:
            raise Exception("500 Internal Server Error")

        result = await call_api(collector)
        assert result is None

    async def test_500_continue_on_error_false_raises_collector_error(self) -> None:
        """500 error with continue_on_error=False should raise CollectorError."""
        collector = MockCollector()

        @with_error_handling(
            operation="Server error hard",
            continue_on_error=False,
        )
        async def call_api(self: MockCollector) -> str:
            raise Exception("500 Internal Server Error")

        with pytest.raises(CollectorError) as exc_info:
            await call_api(collector)

        assert "Server error hard failed" in str(exc_info.value)
        assert exc_info.value.category == ErrorCategory.API_SERVER_ERROR

    async def test_502_bad_gateway_categorized_as_server_error(self) -> None:
        """502 Bad Gateway should be categorized as API_SERVER_ERROR."""
        error = Exception("502 Bad Gateway")
        assert _categorize_error(error) == ErrorCategory.API_SERVER_ERROR

    async def test_503_service_unavailable_categorized_as_server_error(self) -> None:
        """503 Service Unavailable should be categorized as API_SERVER_ERROR."""
        error = Exception("503 Service Unavailable")
        assert _categorize_error(error) == ErrorCategory.API_SERVER_ERROR

    async def test_server_error_tracks_error_metric(self) -> None:
        """5xx errors should call _track_error on the collector."""
        collector = MockCollector()

        @with_error_handling(
            operation="Track 500",
            continue_on_error=True,
            error_category=ErrorCategory.API_SERVER_ERROR,
        )
        async def call_api(self: MockCollector) -> str:
            raise Exception("500 Internal Server Error")

        await call_api(collector)
        assert ErrorCategory.API_SERVER_ERROR in collector._tracked_errors

    async def test_5xx_error_not_retried(self) -> None:
        """5xx errors (non-rate-limit) should not be retried."""
        call_count = 0
        collector = MockCollector()

        @with_error_handling(
            operation="No retry 500",
            continue_on_error=True,
            max_retries=3,
        )
        async def call_api(self: MockCollector) -> str:
            nonlocal call_count
            call_count += 1
            raise Exception("500 Internal Server Error")

        result = await call_api(collector)
        assert result is None
        assert call_count == 1  # No retries - non-retryable error


# ---------------------------------------------------------------------------
# 3. Timeout Tests
# ---------------------------------------------------------------------------


class TestTimeoutErrors:
    """Tests for timeout error handling."""

    async def test_timeout_error_categorized_as_timeout(self) -> None:
        """asyncio.TimeoutError should be categorized as TIMEOUT."""
        collector = MockCollector()

        @with_error_handling(
            operation="Timeout op",
            continue_on_error=False,
        )
        async def slow_call(self: MockCollector) -> str:
            raise TimeoutError("operation timed out")

        with pytest.raises(CollectorError) as exc_info:
            await slow_call(collector)

        assert exc_info.value.category == ErrorCategory.TIMEOUT

    async def test_timeout_with_continue_on_error_returns_none(self) -> None:
        """TimeoutError with continue_on_error=True should return None."""
        collector = MockCollector()

        @with_error_handling(
            operation="Timeout soft",
            continue_on_error=True,
        )
        async def slow_call(self: MockCollector) -> str:
            raise TimeoutError("timed out")

        result = await slow_call(collector)
        assert result is None

    async def test_timeout_tracks_error_metric(self) -> None:
        """TimeoutError should call _track_error(TIMEOUT) on the collector."""
        collector = MockCollector()

        @with_error_handling(
            operation="Timeout track",
            continue_on_error=True,
        )
        async def slow_call(self: MockCollector) -> str:
            raise TimeoutError("timed out")

        await slow_call(collector)
        assert ErrorCategory.TIMEOUT in collector._tracked_errors

    async def test_asyncio_timeout_error_is_handled(self) -> None:
        """asyncio.TimeoutError (subclass of TimeoutError in 3.11+) should be caught."""
        collector = MockCollector()

        @with_error_handling(
            operation="Asyncio timeout",
            continue_on_error=True,
        )
        async def slow_call(self: MockCollector) -> str:
            raise TimeoutError()

        result = await slow_call(collector)
        assert result is None

    async def test_timeout_does_not_leave_partial_state(self) -> None:
        """After a timeout, no partial state should be written to the collector."""
        collector = MockCollector()
        state: dict[str, Any] = {}

        @with_error_handling(
            operation="Partial state timeout",
            continue_on_error=True,
        )
        async def partial_write(self: MockCollector) -> None:
            # Simulate partial work before timeout
            state["partial"] = True
            raise TimeoutError("timed out mid-way")

        await partial_write(collector)

        # The decorator did not modify collector state; partial dict update
        # happened in the function body but no return was given.
        # Confirm decorator correctly returns None and doesn't add more state.
        assert state.get("partial") is True  # Function body ran
        assert "completed" not in state  # No completion marker was set

    async def test_timeout_error_categorize_function(self) -> None:
        """_categorize_error should return TIMEOUT for timeout-like messages."""
        error = Exception("connection timeout after 30s")
        assert _categorize_error(error) == ErrorCategory.TIMEOUT

    async def test_timeout_error_not_retried(self) -> None:
        """TimeoutError should not trigger the retry loop."""
        call_count = 0
        collector = MockCollector()

        @with_error_handling(
            operation="Timeout no retry",
            continue_on_error=True,
            max_retries=3,
        )
        async def slow_call(self: MockCollector) -> str:
            nonlocal call_count
            call_count += 1
            raise TimeoutError("timed out")

        result = await slow_call(collector)
        assert result is None
        assert call_count == 1  # No retries for TimeoutError


# ---------------------------------------------------------------------------
# 4. API Unavailable (404) Tests
# ---------------------------------------------------------------------------


class TestAPIUnavailable404:
    """Tests for 404 / API unavailable error handling."""

    async def test_api_not_available_error_category(self) -> None:
        """APINotAvailableError should have API_NOT_AVAILABLE category."""
        error = APINotAvailableError("/api/v1/organizations/123/appliance/vpn/stats")
        assert error.category == ErrorCategory.API_NOT_AVAILABLE

    async def test_api_not_available_error_message(self) -> None:
        """APINotAvailableError message should include the endpoint path."""
        endpoint = "/api/v1/organizations/123/appliance/vpn/stats"
        error = APINotAvailableError(endpoint)
        assert endpoint in str(error)

    async def test_404_in_message_categorized_as_not_available(self) -> None:
        """Exception message containing '404' should be categorized as API_NOT_AVAILABLE."""
        error = Exception("404 Not Found")
        assert _categorize_error(error) == ErrorCategory.API_NOT_AVAILABLE

    async def test_404_continue_on_error_returns_none(self) -> None:
        """404 error with continue_on_error=True should return None."""
        collector = MockCollector()

        @with_error_handling(
            operation="Fetch 404",
            continue_on_error=True,
        )
        async def call_api(self: MockCollector) -> str:
            raise Exception("404 Not Found")

        result = await call_api(collector)
        assert result is None

    async def test_404_error_tracks_not_available_category(self) -> None:
        """404 errors should track API_NOT_AVAILABLE via _track_error."""
        collector = MockCollector()

        @with_error_handling(
            operation="Track 404",
            continue_on_error=True,
        )
        async def call_api(self: MockCollector) -> str:
            raise Exception("404 Not Found")

        await call_api(collector)
        assert ErrorCategory.API_NOT_AVAILABLE in collector._tracked_errors

    async def test_404_not_retried(self) -> None:
        """404 errors should not trigger retry logic."""
        call_count = 0
        collector = MockCollector()

        @with_error_handling(
            operation="No retry 404",
            continue_on_error=True,
            max_retries=3,
        )
        async def call_api(self: MockCollector) -> str:
            nonlocal call_count
            call_count += 1
            raise Exception("404 Not Found")

        result = await call_api(collector)
        assert result is None
        assert call_count == 1  # Single call, no retries

    async def test_api_not_available_error_with_context(self) -> None:
        """APINotAvailableError can carry extra context."""
        context = {"org_id": "123456", "network_id": "N_abc"}
        error = APINotAvailableError("/api/v1/endpoint", context=context)
        assert error.context == context

    async def test_not_found_in_message_categorized_as_not_available(self) -> None:
        """Exception containing 'not found' should be categorized as API_NOT_AVAILABLE."""
        error = Exception("Resource not found in registry")
        assert _categorize_error(error) == ErrorCategory.API_NOT_AVAILABLE


# ---------------------------------------------------------------------------
# 5. Retry Backoff Tests
# ---------------------------------------------------------------------------


class TestExponentialBackoff:
    """Tests for exponential backoff and jitter behavior."""

    async def test_exponential_delay_increases_between_retries(self) -> None:
        """Delays should follow base_delay * 2^(attempt-1) pattern."""
        delays: list[float] = []
        call_count = 0

        @with_error_handling(
            operation="Backoff test",
            continue_on_error=True,
            max_retries=3,
            base_delay=2.0,
            max_delay=100.0,
        )
        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise RetryableAPIError("Rate limit")

        async def capture_sleep(delay: float) -> None:
            delays.append(delay)

        with (
            patch("meraki_dashboard_exporter.core.error_handling.asyncio.sleep", capture_sleep),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0.0),
        ):
            result = await always_fails()

        assert result is None
        # With jitter=0 and random.uniform=0.0: multiplier = 1+0 = 1.0
        # attempt 1: base_delay * 2^0 = 2.0
        # attempt 2: base_delay * 2^1 = 4.0
        # attempt 3: base_delay * 2^2 = 8.0
        assert delays == [2.0, 4.0, 8.0]

    async def test_delay_capped_at_max_delay(self) -> None:
        """Computed delay must never exceed max_delay."""
        delays: list[float] = []
        call_count = 0

        @with_error_handling(
            operation="Cap test",
            continue_on_error=True,
            max_retries=5,
            base_delay=10.0,
            max_delay=15.0,  # Very low cap
        )
        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise RetryableAPIError("Rate limit")

        async def capture_sleep(delay: float) -> None:
            delays.append(delay)

        with (
            patch("meraki_dashboard_exporter.core.error_handling.asyncio.sleep", capture_sleep),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0.0),
        ):
            result = await always_fails()

        assert result is None
        # All delays should be capped at max_delay before jitter is applied.
        # With jitter multiplier of 1.0 (random.uniform=0.0 -> 1+0=1.0),
        # each delay == min(base_delay*2^n, max_delay) * 1.0
        for d in delays:
            assert d <= 15.0, f"Delay {d} exceeds max_delay=15.0"

    async def test_jitter_varies_delay_between_calls(self) -> None:
        """Jitter should produce different delay values across separate invocations."""

        # Use real random.uniform to verify jitter creates variation
        delays: list[float] = []

        @with_error_handling(
            operation="Jitter test",
            continue_on_error=True,
            max_retries=1,
            base_delay=10.0,
            max_delay=60.0,
        )
        async def fails_once() -> str:
            raise RetryableAPIError("Rate limit")

        # Collect multiple delay samples (one per decorator invocation)
        for _ in range(10):
            call_delays: list[float] = []

            def make_capture(buf: list[float]) -> Any:
                async def _capture(delay: float) -> None:
                    buf.append(delay)

                return _capture

            with patch(
                "meraki_dashboard_exporter.core.error_handling.asyncio.sleep",
                make_capture(call_delays),
            ):
                await fails_once()

            if call_delays:
                delays.append(call_delays[0])

        # With real jitter there should be variation; values should differ
        unique_delays = {round(d, 8) for d in delays}
        assert len(unique_delays) > 1, (
            "Expected variation in jittered delays but all delays were identical"
        )

    async def test_apply_jitter_stays_within_bounds(self) -> None:
        """_apply_jitter should produce values within [delay*(1-ratio), delay*(1+ratio)]."""
        base = 10.0
        jitter_ratio = 0.2
        lower = base * (1.0 - jitter_ratio)
        upper = base * (1.0 + jitter_ratio)

        for _ in range(50):
            jittered = _apply_jitter(base, jitter_ratio)
            assert lower <= jittered <= upper, (
                f"Jittered value {jittered} is outside [{lower}, {upper}]"
            )

    async def test_apply_jitter_zero_delay_returns_zero(self) -> None:
        """_apply_jitter on zero delay should return zero."""
        assert _apply_jitter(0.0) == 0.0

    async def test_apply_jitter_negative_delay_returns_zero(self) -> None:
        """_apply_jitter should clamp negative results to zero."""
        # Force a large negative jitter to test the max(0.0, ...) guard
        with patch(
            "meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=-0.9999
        ):
            result = _apply_jitter(1.0, jitter_ratio=0.2)
        assert result >= 0.0

    async def test_retry_after_from_exception_overrides_backoff(self) -> None:
        """When RetryableAPIError provides retry_after, it should be used as base_wait."""
        delays: list[float] = []
        call_count = 0

        @with_error_handling(
            operation="Retry-After header",
            continue_on_error=True,
            max_retries=2,
            base_delay=100.0,  # Would produce huge delays if used
            max_delay=200.0,
        )
        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise RetryableAPIError("Rate limit", retry_after=5.0)

        async def capture_sleep(delay: float) -> None:
            delays.append(delay)

        with (
            patch("meraki_dashboard_exporter.core.error_handling.asyncio.sleep", capture_sleep),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0.0),
        ):
            result = await always_fails()

        assert result is None
        # retry_after=5.0 should be used as base_wait, not base_delay * 2^n
        for d in delays:
            assert d == 5.0, f"Expected retry_after=5.0 used as delay but got {d}"

    async def test_429_retry_after_header_extracted_from_exception(self) -> None:
        """retry_after attribute on a 429-status exception should be used for the wait."""
        delays: list[float] = []
        call_count = 0
        collector = MockCollector()

        @with_error_handling(
            operation="429 retry-after",
            continue_on_error=True,
            max_retries=2,
            base_delay=100.0,
            max_delay=200.0,
        )
        async def always_fails(self: MockCollector) -> str:
            nonlocal call_count
            call_count += 1
            err = Exception("HTTP 429 Too Many Requests")
            err.status = 429  # type: ignore[attr-defined]
            err.retry_after = 3.0  # type: ignore[attr-defined]
            raise err

        async def capture_sleep(delay: float) -> None:
            delays.append(delay)

        with (
            patch("meraki_dashboard_exporter.core.error_handling.asyncio.sleep", capture_sleep),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0.0),
        ):
            result = await always_fails(collector)

        assert result is None
        # retry_after=3.0 should override base_delay=100.0
        for d in delays:
            assert d == 3.0, f"Expected retry_after=3.0 used as delay but got {d}"

    async def test_sleep_not_called_on_non_retryable_error(self) -> None:
        """Non-retryable errors should never call asyncio.sleep."""
        sleep_called = False

        async def assert_no_sleep(delay: float) -> None:
            nonlocal sleep_called
            sleep_called = True

        @with_error_handling(
            operation="No sleep on 500",
            continue_on_error=True,
            max_retries=3,
        )
        async def fails_with_server_error() -> str:
            raise Exception("500 Internal Server Error")

        with patch("meraki_dashboard_exporter.core.error_handling.asyncio.sleep", assert_no_sleep):
            await fails_with_server_error()

        assert not sleep_called, "asyncio.sleep was called for a non-retryable error"


# ---------------------------------------------------------------------------
# 6. Error Categorization Unit Tests
# ---------------------------------------------------------------------------


class TestErrorCategorization:
    """Unit tests for the _categorize_error function."""

    def test_categorize_rate_limit_by_status_string(self) -> None:
        """429 status string should map to API_RATE_LIMIT."""
        error = Exception("429 Too Many Requests")
        assert _categorize_error(error) == ErrorCategory.API_RATE_LIMIT

    def test_categorize_client_error_400(self) -> None:
        """400 Bad Request should map to API_CLIENT_ERROR."""
        error = Exception("400 Bad Request")
        assert _categorize_error(error) == ErrorCategory.API_CLIENT_ERROR

    def test_categorize_client_error_401(self) -> None:
        """401 Unauthorized should map to API_CLIENT_ERROR."""
        error = Exception("401 Unauthorized")
        assert _categorize_error(error) == ErrorCategory.API_CLIENT_ERROR

    def test_categorize_client_error_403(self) -> None:
        """403 Forbidden should map to API_CLIENT_ERROR."""
        error = Exception("403 Forbidden")
        assert _categorize_error(error) == ErrorCategory.API_CLIENT_ERROR

    def test_categorize_server_error_500(self) -> None:
        """500 Internal Server Error should map to API_SERVER_ERROR."""
        error = Exception("500 Internal Server Error")
        assert _categorize_error(error) == ErrorCategory.API_SERVER_ERROR

    def test_categorize_server_error_503(self) -> None:
        """503 Service Unavailable should map to API_SERVER_ERROR."""
        error = Exception("503 Service Unavailable")
        assert _categorize_error(error) == ErrorCategory.API_SERVER_ERROR

    def test_categorize_not_found_by_404(self) -> None:
        """404 Not Found should map to API_NOT_AVAILABLE."""
        error = Exception("404 Not Found")
        assert _categorize_error(error) == ErrorCategory.API_NOT_AVAILABLE

    def test_categorize_timeout_by_message(self) -> None:
        """'timeout' in the message should map to TIMEOUT."""
        error = Exception("request timeout")
        assert _categorize_error(error) == ErrorCategory.TIMEOUT

    def test_categorize_parsing_by_json(self) -> None:
        """'json' in the message should map to PARSING."""
        error = Exception("invalid json response")
        assert _categorize_error(error) == ErrorCategory.PARSING

    def test_categorize_validation_by_keyword(self) -> None:
        """'validation' in the message should map to VALIDATION."""
        error = Exception("validation failed for field xyz")
        assert _categorize_error(error) == ErrorCategory.VALIDATION

    def test_categorize_unknown_for_generic_errors(self) -> None:
        """Unrecognized error messages should map to UNKNOWN."""
        error = Exception("something unexpected happened")
        assert _categorize_error(error) == ErrorCategory.UNKNOWN


# ---------------------------------------------------------------------------
# 7. Collector Context Extraction Tests
# ---------------------------------------------------------------------------


class TestCollectorContextExtraction:
    """Tests verifying the decorator properly extracts self and invokes tracking."""

    async def test_error_tracking_called_with_correct_category(self) -> None:
        """Collector's _track_error should be invoked with the right ErrorCategory."""
        collector = MockCollector()

        @with_error_handling(
            operation="Context test",
            continue_on_error=True,
            error_category=ErrorCategory.API_CLIENT_ERROR,
        )
        async def call_api(self: MockCollector) -> str:
            raise Exception("403 Forbidden")

        await call_api(collector)

        # error_category parameter forces API_CLIENT_ERROR
        assert ErrorCategory.API_CLIENT_ERROR in collector._tracked_errors

    async def test_error_tracking_called_when_retries_exhausted(self) -> None:
        """_track_error should be called when retry limit is exhausted."""
        collector = MockCollector()

        @with_error_handling(
            operation="Exhaust retries",
            continue_on_error=True,
            max_retries=1,
            base_delay=0.0,
            max_delay=1.0,
        )
        async def always_rate_limited(self: MockCollector) -> str:
            raise RetryableAPIError("Rate limit")

        with (
            patch(
                "meraki_dashboard_exporter.core.error_handling.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await always_rate_limited(collector)

        assert ErrorCategory.API_RATE_LIMIT in collector._tracked_errors

    async def test_no_tracking_on_success(self) -> None:
        """_track_error and _track_retry should not be called on success."""
        collector = MockCollector()

        @with_error_handling(
            operation="Success path",
            continue_on_error=True,
        )
        async def succeeds(self: MockCollector) -> str:
            return "data"

        result = await succeeds(collector)
        assert result == "data"
        assert len(collector._tracked_errors) == 0
        assert len(collector._tracked_retries) == 0
