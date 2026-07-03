"""Tests for error handling utilities."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from meraki_dashboard_exporter.core.error_handling import (
    APINotAvailableError,
    CollectorError,
    DataValidationError,
    ErrorCategory,
    NothingCollectedError,
    RetryableAPIError,
    _categorize_error,  # noqa: PLC2701  (intentionally testing the private categorizer)
    _resolve_per_fetch_deadline,  # noqa: PLC2701  (deadline seam, #546)
    _resolve_retry_after_cap,  # noqa: PLC2701  (Retry-After cap seam, #545)
    batch_with_concurrency_limit,
    validate_response_format,
    with_error_handling,
    with_semaphore_limit,
)


class _StatusError(Exception):
    """Exception carrying an HTTP ``.status`` like ``meraki.exceptions.APIError``."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(message)


class TestErrorCategories:
    """Test error category enum values."""

    def test_error_category_values(self) -> None:
        """Test that error category enum has expected values."""
        assert ErrorCategory.API_RATE_LIMIT == "api_rate_limit"
        assert ErrorCategory.API_CLIENT_ERROR == "api_client_error"
        assert ErrorCategory.API_SERVER_ERROR == "api_server_error"
        assert ErrorCategory.API_NOT_AVAILABLE == "api_not_available"
        assert ErrorCategory.TIMEOUT == "timeout"
        assert ErrorCategory.PARSING == "parsing"
        assert ErrorCategory.VALIDATION == "validation"
        assert ErrorCategory.UNKNOWN == "unknown"


class TestCollectorErrors:
    """Test custom exception classes."""

    def test_collector_error_initialization(self) -> None:
        """Test CollectorError initialization."""
        error = CollectorError(
            "Test error",
            ErrorCategory.API_CLIENT_ERROR,
            {"request_id": "123", "status_code": 400},
        )
        assert str(error) == "Test error"
        assert error.category == ErrorCategory.API_CLIENT_ERROR
        assert error.context == {"request_id": "123", "status_code": 400}

    def test_collector_error_default_values(self) -> None:
        """Test CollectorError with default values."""
        error = CollectorError("Test error")
        assert error.category == ErrorCategory.UNKNOWN
        assert error.context == {}

    def test_api_not_available_error(self) -> None:
        """Test APINotAvailableError."""
        error = APINotAvailableError(
            "/api/v1/organizations/123/devices",
            {"org_id": "123"},
        )
        assert "API endpoint '/api/v1/organizations/123/devices' not available" in str(error)
        assert error.category == ErrorCategory.API_NOT_AVAILABLE
        assert error.context == {"org_id": "123"}

    def test_data_validation_error(self) -> None:
        """Test DataValidationError."""
        error = DataValidationError(
            "Expected list, got dict",
            {"response_type": "dict", "endpoint": "/devices"},
        )
        assert str(error) == "Expected list, got dict"
        assert error.category == ErrorCategory.VALIDATION
        assert error.context == {"response_type": "dict", "endpoint": "/devices"}

    def test_nothing_collected_error(self) -> None:
        """Test NothingCollectedError (#509 seam)."""
        error = NothingCollectedError("X", attempted=3, failed=3, skipped_backoff=1)
        assert isinstance(error, CollectorError)
        assert error.category == ErrorCategory.API_CLIENT_ERROR
        assert error.attempted == 3
        assert error.failed == 3
        assert error.skipped_backoff == 1
        assert "attempted=3" in str(error)


class TestWithErrorHandlingDecorator:
    """Test the with_error_handling decorator."""

    @pytest.mark.asyncio
    async def test_successful_operation(self) -> None:
        """Test decorator with successful operation."""

        @with_error_handling(operation="Test operation")
        async def successful_operation() -> str:
            return "success"

        result = await successful_operation()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_error_handling_continue_on_error(self) -> None:
        """Test decorator continues on error when configured."""

        @with_error_handling(operation="Test operation", continue_on_error=True)
        async def failing_operation() -> str:
            raise ValueError("Test error")

        result = await failing_operation()
        assert result is None

    @pytest.mark.asyncio
    async def test_error_handling_reraise(self) -> None:
        """Test decorator re-raises when continue_on_error=False."""

        @with_error_handling(operation="Test operation", continue_on_error=False)
        async def failing_operation() -> str:
            raise ValueError("Test error")

        with pytest.raises(CollectorError) as exc_info:
            await failing_operation()

        assert "Test operation failed: Test error" in str(exc_info.value)
        assert exc_info.value.category == ErrorCategory.UNKNOWN

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self) -> None:
        """Test timeout error handling."""

        @with_error_handling(operation="Test operation", continue_on_error=True)
        async def timeout_operation() -> str:
            raise TimeoutError("Operation timed out")

        result = await timeout_operation()
        assert result is None

    @pytest.mark.asyncio
    async def test_categorized_error_handling(self) -> None:
        """Test error handling with specific category."""

        @with_error_handling(
            operation="API call",
            continue_on_error=False,
            error_category=ErrorCategory.API_SERVER_ERROR,
        )
        async def api_operation() -> str:
            raise Exception("500 Internal Server Error")

        with pytest.raises(CollectorError) as exc_info:
            await api_operation()

        assert exc_info.value.category == ErrorCategory.API_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_404_error_special_handling(self) -> None:
        """Test 404 errors are handled specially."""

        @with_error_handling(operation="Fetch resource", continue_on_error=True)
        async def not_found_operation() -> str:
            raise Exception("404 Not Found")

        result = await not_found_operation()
        assert result is None

    @pytest.mark.asyncio
    async def test_500_status_with_404_in_message_not_downgraded(self) -> None:
        """A 500 whose message contains '404' is NOT downgraded (F-052).

        ``str(APIError)`` concatenates server-controlled body text, so a genuine
        500 whose message happens to contain '404' (a serial/ID fragment) must
        be categorized by its ``.status`` (500), not silently downgraded to a
        debug-level API_NOT_AVAILABLE.
        """

        @with_error_handling(operation="Fetch resource", continue_on_error=False)
        async def server_error() -> str:
            raise _StatusError(500, "Server error, device 404XYZ failed")

        with pytest.raises(CollectorError) as exc_info:
            await server_error()

        assert exc_info.value.category == ErrorCategory.API_SERVER_ERROR

    def test_categorize_500_status_with_404_in_message(self) -> None:
        """_categorize_error uses .status over substring for a 500 (F-052)."""
        error = _StatusError(500, "weird 404 fragment in body")
        assert _categorize_error(error) == ErrorCategory.API_SERVER_ERROR

    def test_categorize_404_status(self) -> None:
        """A genuine 404 status still maps to API_NOT_AVAILABLE (F-052)."""
        assert _categorize_error(_StatusError(404, "not here")) == (ErrorCategory.API_NOT_AVAILABLE)

    def test_categorize_404_message_fallback_without_status(self) -> None:
        """Non-APIError exceptions (no .status) still fall back to substrings."""
        assert _categorize_error(Exception("404 Not Found")) == (ErrorCategory.API_NOT_AVAILABLE)

    @pytest.mark.asyncio
    async def test_collector_context_extraction(self) -> None:
        """Test context extraction from collector instance."""

        class MockCollector:
            @with_error_handling(operation="Collect metrics", continue_on_error=True)
            async def collect(self) -> str:
                return "collected"

        collector = MockCollector()
        result = await collector.collect()
        assert result == "collected"

    @pytest.mark.asyncio
    async def test_error_tracking_integration(self) -> None:
        """Test error tracking when collector has _track_error method."""

        class MockCollector:
            def __init__(self) -> None:
                self._track_error = Mock()

            @with_error_handling(operation="Collect", continue_on_error=True)
            async def collect(self) -> str:
                raise ValueError("Test error")

        collector = MockCollector()
        await collector.collect()
        collector._track_error.assert_called_once_with(ErrorCategory.UNKNOWN)


class TestValidateResponseFormat:
    """Test response format validation."""

    def test_validate_list_response(self) -> None:
        """Test validating list responses."""
        response = [{"id": 1}, {"id": 2}]
        result = validate_response_format(response, list, "Fetch items")
        assert result == response

    def test_validate_dict_response(self) -> None:
        """Test validating dict responses."""
        response = {"status": "ok", "count": 5}
        result = validate_response_format(response, dict, "Get status")
        assert result == response

    def test_validate_wrapped_response(self) -> None:
        """Test validating wrapped responses with 'items' key."""
        response = {"items": [{"id": 1}, {"id": 2}], "meta": {"page": 1}}
        result = validate_response_format(response, list, "Fetch paginated")
        assert result == [{"id": 1}, {"id": 2}]

    def test_validate_invalid_type(self) -> None:
        """Test validation fails for wrong type."""
        response = {"id": 1}
        with pytest.raises(DataValidationError) as exc_info:
            validate_response_format(response, list, "Fetch list")

        assert "Expected list, got dict" in str(exc_info.value)
        assert exc_info.value.context["response_type"] == "dict"

    def test_validate_wrapped_invalid_type(self) -> None:
        """Test validation fails for wrong wrapped type."""
        response = {"items": {"id": 1}}
        with pytest.raises(DataValidationError) as exc_info:
            validate_response_format(response, list, "Fetch items")

        assert "Expected list, got dict" in str(exc_info.value)

    def test_validate_detects_rate_limit_error_response(self) -> None:
        """Test that rate limit error responses raise RetryableAPIError."""
        error_response = {"errors": ["API rate limit exceeded for organization"]}

        with pytest.raises(RetryableAPIError) as exc_info:
            validate_response_format(error_response, list, "getOrganizationDevices")

        assert "rate limit" in str(exc_info.value).lower()
        assert exc_info.value.category == ErrorCategory.API_RATE_LIMIT
        assert exc_info.value.context["operation"] == "getOrganizationDevices"
        assert exc_info.value.context["errors"] == ["API rate limit exceeded for organization"]

    def test_validate_detects_multiple_api_errors(self) -> None:
        """Test that multiple error messages are joined in the error output."""
        error_response = {"errors": ["Error 1", "Error 2", "Error 3"]}

        with pytest.raises(DataValidationError) as exc_info:
            validate_response_format(error_response, list, "getNetworkClients")

        error_msg = str(exc_info.value)
        assert "Error 1" in error_msg
        assert "Error 2" in error_msg
        assert "Error 3" in error_msg

    def test_validate_detects_string_error(self) -> None:
        """Test that non-list error values are handled correctly."""
        error_response = {"errors": "Single error message"}

        with pytest.raises(DataValidationError) as exc_info:
            validate_response_format(error_response, dict, "getDeviceStatus")

        assert "Single error message" in str(exc_info.value)

    def test_validate_dict_with_errors_key_as_data(self) -> None:
        """Test that a dict response expecting dict type with errors key raises error."""
        # Even when expecting dict type, an errors response should be detected
        error_response = {"errors": ["Not found"]}

        with pytest.raises(DataValidationError) as exc_info:
            validate_response_format(error_response, dict, "getDevice")

        assert "API returned errors" in str(exc_info.value)

    def test_validate_too_many_requests_raises_retryable(self) -> None:
        """Test that 'too many requests' errors raise RetryableAPIError."""
        error_response = {"errors": ["Too many requests, please wait"]}

        with pytest.raises(RetryableAPIError):
            validate_response_format(error_response, list, "getNetworks")

    def test_validate_throttled_raises_retryable(self) -> None:
        """Test that 'throttled' errors raise RetryableAPIError."""
        error_response = {"errors": ["Request throttled"]}

        with pytest.raises(RetryableAPIError):
            validate_response_format(error_response, list, "getDevices")


class TestRetryableAPIError:
    """Test RetryableAPIError exception class."""

    def test_retryable_error_initialization(self) -> None:
        """Test RetryableAPIError initialization."""
        error = RetryableAPIError(
            "Rate limit exceeded",
            retry_after=30.0,
            context={"org_id": "123"},
        )
        assert str(error) == "Rate limit exceeded"
        assert error.category == ErrorCategory.API_RATE_LIMIT
        assert error.retry_after == 30.0
        assert error.context == {"org_id": "123"}

    def test_retryable_error_default_retry_after(self) -> None:
        """Test RetryableAPIError with default retry_after."""
        error = RetryableAPIError("Rate limit exceeded")
        assert error.retry_after is None
        assert error.category == ErrorCategory.API_RATE_LIMIT


class TestWithErrorHandlingRetry:
    """Test retry behavior in with_error_handling decorator."""

    @pytest.mark.asyncio
    async def test_retries_on_retryable_error(self) -> None:
        """Test that decorator retries on RetryableAPIError."""
        call_count = 0

        @with_error_handling(
            operation="Test operation",
            max_retries=2,
            base_delay=0.01,  # Fast for testing
        )
        async def flaky_operation() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RetryableAPIError("Rate limit exceeded")
            return "success"

        result = await flaky_operation()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_respects_max_retries(self) -> None:
        """Test that decorator stops after max_retries."""
        call_count = 0

        @with_error_handling(
            operation="Test operation",
            continue_on_error=True,
            max_retries=2,
            base_delay=0.01,
        )
        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise RetryableAPIError("Rate limit exceeded")

        result = await always_fails()
        assert result is None
        assert call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_reraises_after_max_retries_when_not_continue(self) -> None:
        """Test that decorator re-raises after max_retries when continue_on_error=False."""
        call_count = 0

        @with_error_handling(
            operation="Test operation",
            continue_on_error=False,
            max_retries=1,
            base_delay=0.01,
        )
        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise RetryableAPIError("Rate limit exceeded")

        with pytest.raises(CollectorError) as exc_info:
            await always_fails()

        assert "failed after 1 retries" in str(exc_info.value)
        assert call_count == 2  # Initial + 1 retry

    @pytest.mark.asyncio
    async def test_uses_retry_after_from_exception(self) -> None:
        """Test that retry_after from exception is used when provided."""
        delays_used: list[float] = []

        async def mock_sleep(delay: float) -> None:
            delays_used.append(delay)

        call_count = 0

        @with_error_handling(
            operation="Test operation",
            max_retries=2,
            base_delay=100.0,  # Would be very long if used
        )
        async def fails_with_retry_after() -> str:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RetryableAPIError("Rate limit", retry_after=0.05)
            return "success"

        # Patch asyncio.sleep and disable jitter for deterministic testing
        with (
            patch("meraki_dashboard_exporter.core.error_handling.asyncio.sleep", mock_sleep),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0),
        ):
            result = await fails_with_retry_after()

        assert result == "success"
        assert len(delays_used) == 2
        assert all(d == 0.05 for d in delays_used)  # Should use retry_after

    @pytest.mark.asyncio
    async def test_non_retryable_errors_not_retried(self) -> None:
        """Test that non-retryable errors are not retried."""
        call_count = 0

        @with_error_handling(
            operation="Test operation",
            continue_on_error=True,
            max_retries=3,
            base_delay=0.01,
        )
        async def fails_with_validation_error() -> str:
            nonlocal call_count
            call_count += 1
            raise DataValidationError("Invalid format")

        result = await fails_with_validation_error()
        assert result is None
        assert call_count == 1  # No retries for DataValidationError

    @pytest.mark.asyncio
    async def test_exponential_backoff(self) -> None:
        """Test that exponential backoff is applied correctly."""
        delays_used: list[float] = []

        async def mock_sleep(delay: float) -> None:
            delays_used.append(delay)

        call_count = 0

        @with_error_handling(
            operation="Test operation",
            max_retries=3,
            base_delay=1.0,
            max_delay=60.0,
        )
        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise RetryableAPIError("Rate limit exceeded")

        # Disable jitter for deterministic testing
        with (
            patch("meraki_dashboard_exporter.core.error_handling.asyncio.sleep", mock_sleep),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0),
        ):
            result = await always_fails()

        assert result is None
        # Delays: 1.0 * 2^0 = 1.0, 1.0 * 2^1 = 2.0, 1.0 * 2^2 = 4.0
        assert delays_used == [1.0, 2.0, 4.0]


class TestConcurrencyUtilities:
    """Test concurrency limiting utilities."""

    @pytest.mark.asyncio
    async def test_with_semaphore_limit(self) -> None:
        """Test semaphore limiting wrapper."""
        semaphore = asyncio.Semaphore(2)
        call_count = 0

        async def task() -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return call_count

        result = await with_semaphore_limit(semaphore, task())
        assert result == 1

    @pytest.mark.asyncio
    async def test_batch_with_concurrency_limit(self) -> None:
        """Test batch concurrency limiting."""
        results = []

        async def task(value: int) -> int:
            await asyncio.sleep(0.01)
            results.append(value)
            return value

        tasks = [task(i) for i in range(10)]
        limited_tasks = batch_with_concurrency_limit(tasks, max_concurrent=3)

        assert len(limited_tasks) == 10

        # Execute all tasks
        await asyncio.gather(*limited_tasks)
        assert sorted(results) == list(range(10))

    @pytest.mark.asyncio
    async def test_concurrent_execution_limit(self) -> None:
        """Test that concurrency is actually limited."""
        max_concurrent = 0
        current_concurrent = 0

        async def track_concurrency() -> None:
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            current_concurrent -= 1

        tasks = [track_concurrency() for _ in range(10)]
        limited_tasks = batch_with_concurrency_limit(tasks, max_concurrent=3)

        await asyncio.gather(*limited_tasks)

        # Max concurrent should not exceed limit
        assert max_concurrent <= 3


class TestDecoratorReturnTypes:
    """Test decorator preserves proper return types."""

    @pytest.mark.asyncio
    async def test_return_type_preservation(self) -> None:
        """Test decorator preserves return type annotations."""

        @with_error_handling(operation="Test", continue_on_error=True)
        async def typed_function() -> list[dict[str, Any]]:
            return [{"key": "value"}]

        result = await typed_function()
        assert result == [{"key": "value"}]

    @pytest.mark.asyncio
    async def test_none_return_on_error(self) -> None:
        """Test decorator returns None on error when configured."""

        @with_error_handling(operation="Test", continue_on_error=True)
        async def failing_typed_function() -> list[dict[str, Any]]:
            raise ValueError("Error")

        result = await failing_typed_function()
        assert result is None


class TestErrorHandlingIntegration:
    """Test error handling integration scenarios."""

    @pytest.mark.asyncio
    async def test_nested_error_handling(self) -> None:
        """Test nested error handling decorators."""

        @with_error_handling(operation="Outer", continue_on_error=True)
        async def outer_function() -> str | None:
            return await inner_function()

        @with_error_handling(operation="Inner", continue_on_error=False)
        async def inner_function() -> str:
            raise ValueError("Inner error")

        result = await outer_function()
        assert result is None

    @pytest.mark.asyncio
    @patch("meraki_dashboard_exporter.core.error_handling.logger")
    async def test_logging_behavior(self, mock_logger: Mock) -> None:
        """Test logging behavior in error handling."""

        @with_error_handling(operation="Test operation", continue_on_error=True)
        async def operation_with_error() -> None:
            raise ValueError("Test error")

        await operation_with_error()

        # Verify error was logged
        mock_logger.exception.assert_called_once()
        call_args = mock_logger.exception.call_args
        assert "Test operation failed" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_performance_timing(self) -> None:
        """Test operation timing in error handling."""

        @with_error_handling(operation="Timed operation", continue_on_error=True)
        async def slow_operation() -> None:
            await asyncio.sleep(0.1)
            raise ValueError("Error after delay")

        start_time = asyncio.get_event_loop().time()
        await slow_operation()
        duration = asyncio.get_event_loop().time() - start_time

        # Operation should have taken at least 0.1 seconds
        assert duration >= 0.1


class _FakeCollector:
    """Instance shape used by the runtime settings seams (#545/#546).

    Mirrors just enough of ``MetricCollector``: ``.settings.api.<field>``,
    ``_track_error`` and ``_track_retry`` recorders.
    """

    def __init__(self, **api_fields: Any) -> None:
        self.settings = SimpleNamespace(api=SimpleNamespace(**api_fields))
        self.tracked_errors: list[ErrorCategory] = []
        self.tracked_retries: list[tuple[str, str]] = []

    def _track_error(self, category: ErrorCategory) -> None:
        self.tracked_errors.append(category)

    def _track_retry(self, operation: str, reason: str) -> None:
        self.tracked_retries.append((operation, reason))


class TestRetryAfterCap:
    """#545: server-sent Retry-After waits are capped by settings."""

    def test_resolve_cap_from_instance_settings(self) -> None:
        """Cap comes from settings.api.retry_after_max_seconds when present."""
        instance = _FakeCollector(retry_after_max_seconds=7)
        assert _resolve_retry_after_cap(instance, 60.0) == 7.0

    def test_resolve_cap_falls_back_without_settings(self) -> None:
        """No settings on the instance -> the decorator's max_delay fallback."""
        assert _resolve_retry_after_cap(object(), 60.0) == 60.0
        assert _resolve_retry_after_cap(None, 45.0) == 45.0

    def test_resolve_cap_falls_back_when_field_missing(self) -> None:
        """settings.api without the field (pre-seam) -> fallback."""
        instance = _FakeCollector()
        assert _resolve_retry_after_cap(instance, 60.0) == 60.0

    @pytest.mark.asyncio
    async def test_retry_after_wait_capped_by_settings(self) -> None:
        """A pathological Retry-After (4000s) is bounded to the configured cap."""
        delays_used: list[float] = []

        async def mock_sleep(delay: float) -> None:
            delays_used.append(delay)

        instance = _FakeCollector(retry_after_max_seconds=7)
        call_count = 0

        @with_error_handling(operation="Capped op", max_retries=2, base_delay=1.0)
        async def method(self: _FakeCollector) -> str:
            nonlocal call_count
            call_count += 1
            raise RetryableAPIError("Rate limit exceeded", retry_after=4000.0)

        with (
            patch("meraki_dashboard_exporter.core.error_handling.asyncio.sleep", mock_sleep),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0),
        ):
            result = await method(instance)

        assert result is None
        assert call_count == 3
        assert delays_used == [7.0, 7.0]

    @pytest.mark.asyncio
    async def test_429_status_retry_after_header_capped(self) -> None:
        """SDK-style 429 (status attr + retry_after) is capped the same way."""
        delays_used: list[float] = []

        async def mock_sleep(delay: float) -> None:
            delays_used.append(delay)

        class _RateLimitedError(Exception):
            status = 429
            retry_after = 4000.0

        instance = _FakeCollector(retry_after_max_seconds=5)
        call_count = 0

        @with_error_handling(operation="SDK 429 op", max_retries=3, base_delay=1.0)
        async def method(self: _FakeCollector) -> str:
            nonlocal call_count
            call_count += 1
            raise _RateLimitedError("429 Too Many Requests")

        with (
            patch("meraki_dashboard_exporter.core.error_handling.asyncio.sleep", mock_sleep),
            patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0),
        ):
            result = await method(instance)

        assert result is None
        # Single 429 owner: exactly 1 + max_retries logical HTTP attempts (#545),
        # nothing multiplied by an SDK-internal retry loop.
        assert call_count == 4
        assert delays_used == [5.0, 5.0, 5.0]
        assert instance.tracked_errors == [ErrorCategory.API_RATE_LIMIT]


class TestPerFetchDeadline:
    """#546: per-fetch wall-clock deadline with defined timeout semantics."""

    def test_resolve_deadline_from_instance_settings(self) -> None:
        """The deadline comes from settings.api.per_fetch_deadline_seconds."""
        instance = _FakeCollector(per_fetch_deadline_seconds=30)
        assert _resolve_per_fetch_deadline(instance) == 30.0

    def test_resolve_deadline_defaults_when_field_missing(self) -> None:
        """settings.api present but pre-seam (no field) -> frozen default 120s."""
        instance = _FakeCollector()
        assert _resolve_per_fetch_deadline(instance) == 120.0

    def test_resolve_deadline_none_without_settings(self) -> None:
        """Plain functions (no settings) keep the historic no-deadline behavior."""
        assert _resolve_per_fetch_deadline(object()) is None
        assert _resolve_per_fetch_deadline(None) is None

    def test_resolve_deadline_none_for_unusable_values(self) -> None:
        """Non-positive or mock (non-numeric) values disable the deadline."""
        instance = _FakeCollector(per_fetch_deadline_seconds=0)
        assert _resolve_per_fetch_deadline(instance) is None
        mock_instance = MagicMock()
        assert _resolve_per_fetch_deadline(mock_instance) is None

    @pytest.mark.asyncio
    async def test_deadline_cancels_slow_fetch_and_tracks_timeout(self) -> None:
        """Deadline expiry cancels a slow fetch and tracks a TIMEOUT failure.

        Yields None, so no partial result is returned for emission.
        """
        instance = _FakeCollector(per_fetch_deadline_seconds=0.1)
        started = asyncio.Event()

        @with_error_handling(operation="Slow fetch", continue_on_error=True)
        async def method(self: _FakeCollector) -> str:
            started.set()
            await asyncio.sleep(30)
            return "late"

        start = asyncio.get_event_loop().time()
        result = await method(instance)
        duration = asyncio.get_event_loop().time() - start

        assert started.is_set()
        assert result is None
        assert duration < 5.0
        assert instance.tracked_errors == [ErrorCategory.TIMEOUT]

    @pytest.mark.asyncio
    async def test_deadline_bounds_rate_limit_backoff(self) -> None:
        """The deadline also covers 429 backoff waits.

        A throttled fetch cannot sleep past its budget (coordinates #545's
        bounded, event-loop wait with #546's per-fetch deadline).
        """

        class _RateLimitedError(Exception):
            status = 429
            retry_after = 30.0

        instance = _FakeCollector(
            per_fetch_deadline_seconds=0.1,
            retry_after_max_seconds=60,
        )
        call_count = 0

        @with_error_handling(operation="Throttled fetch", continue_on_error=True)
        async def method(self: _FakeCollector) -> str:
            nonlocal call_count
            call_count += 1
            raise _RateLimitedError("429 Too Many Requests")

        start = asyncio.get_event_loop().time()
        result = await method(instance)
        duration = asyncio.get_event_loop().time() - start

        assert result is None
        assert duration < 5.0
        # First attempt raised instantly; the deadline fired during the first
        # (event-loop, cancellable) backoff sleep - no further attempts.
        assert call_count == 1
        assert instance.tracked_errors == [ErrorCategory.TIMEOUT]

    @pytest.mark.asyncio
    async def test_deadline_raises_collector_error_when_not_continue(self) -> None:
        """continue_on_error=False turns deadline expiry into CollectorError(TIMEOUT)."""
        instance = _FakeCollector(per_fetch_deadline_seconds=0.05)

        @with_error_handling(operation="Strict fetch", continue_on_error=False)
        async def method(self: _FakeCollector) -> str:
            await asyncio.sleep(30)
            return "late"

        with pytest.raises(CollectorError) as exc_info:
            await method(instance)

        assert exc_info.value.category == ErrorCategory.TIMEOUT
        assert "deadline" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_no_deadline_for_plain_functions(self) -> None:
        """Undecorated-instance/plain functions run without an implicit deadline."""

        @with_error_handling(operation="Plain op", continue_on_error=True)
        async def plain_function() -> str:
            await asyncio.sleep(0.05)
            return "done"

        assert await plain_function() == "done"

    @pytest.mark.asyncio
    async def test_func_raised_timeout_still_handled(self) -> None:
        """A TimeoutError raised *by* the fetch keeps the existing handling."""
        instance = _FakeCollector(per_fetch_deadline_seconds=60)

        @with_error_handling(operation="Inner timeout", continue_on_error=True)
        async def method(self: _FakeCollector) -> str:
            raise TimeoutError("inner timed out")

        result = await method(instance)
        assert result is None
        assert instance.tracked_errors == [ErrorCategory.TIMEOUT]


class _RateLimit429Error(Exception):
    """HTTP 429 shaped like meraki.exceptions.APIError (status + optional retry_after)."""

    def __init__(self, retry_after: float | None = None) -> None:
        self.status = 429
        self.retry_after = retry_after
        super().__init__("429 too many requests")


class TestAIMDThrottleFeedback:
    """#617: the single 429-retry owner feeds record_throttle_event on each retry."""

    @staticmethod
    async def _instant_sleep(_delay: float) -> None:
        """Drop-in for asyncio.sleep that never actually waits."""
        return None

    def _no_sleep(self) -> Any:
        return patch(
            "meraki_dashboard_exporter.core.error_handling.asyncio.sleep", self._instant_sleep
        )

    @staticmethod
    def _no_jitter() -> Any:
        return patch("meraki_dashboard_exporter.core.error_handling.random.uniform", return_value=0)

    @pytest.mark.asyncio
    async def test_http_429_storm_fires_once_per_retry(self) -> None:
        """A simulated 429 storm records once per retry with the capped Retry-After."""
        instance = _FakeCollector(retry_after_max_seconds=30)
        instance.rate_limiter = MagicMock()

        @with_error_handling(operation="429 op", max_retries=3, base_delay=0.01)
        async def method(self: _FakeCollector) -> str:
            raise _RateLimit429Error(retry_after=1.0)

        with self._no_sleep(), self._no_jitter():
            result = await method(instance)

        assert result is None
        assert instance.rate_limiter.record_throttle_event.call_count == 3
        for call in instance.rate_limiter.record_throttle_event.call_args_list:
            assert call.args == (None, 1.0)  # (org_id=None, capped retry_after)

    @pytest.mark.asyncio
    async def test_http_429_retry_after_capped_before_recording(self) -> None:
        """A pathological Retry-After is capped before it reaches record_throttle_event."""
        instance = _FakeCollector(retry_after_max_seconds=7)
        instance.rate_limiter = MagicMock()

        @with_error_handling(operation="429 op", max_retries=1, base_delay=0.01)
        async def method(self: _FakeCollector) -> str:
            raise _RateLimit429Error(retry_after=4000.0)

        with self._no_sleep(), self._no_jitter():
            await method(instance)

        instance.rate_limiter.record_throttle_event.assert_called_once_with(None, 7.0)

    @pytest.mark.asyncio
    async def test_retryable_api_error_branch_records_throttle(self) -> None:
        """The RetryableAPIError (HTTP-200 rate-limit) branch also feeds the controller."""
        instance = _FakeCollector(retry_after_max_seconds=30)
        instance.rate_limiter = MagicMock()

        @with_error_handling(operation="200-rl op", max_retries=2, base_delay=0.01)
        async def method(self: _FakeCollector) -> str:
            raise RetryableAPIError("Rate limit exceeded", retry_after=2.0)

        with self._no_sleep(), self._no_jitter():
            await method(instance)

        assert instance.rate_limiter.record_throttle_event.call_count == 2
        for call in instance.rate_limiter.record_throttle_event.call_args_list:
            assert call.args == (None, 2.0)

    @pytest.mark.asyncio
    async def test_no_retry_after_records_none(self) -> None:
        """With no server Retry-After the recorded value is None (backoff path)."""
        instance = _FakeCollector(retry_after_max_seconds=30)
        instance.rate_limiter = MagicMock()

        @with_error_handling(operation="429 op", max_retries=1, base_delay=0.01)
        async def method(self: _FakeCollector) -> str:
            raise _RateLimit429Error(retry_after=None)

        with self._no_sleep(), self._no_jitter():
            await method(instance)

        instance.rate_limiter.record_throttle_event.assert_called_once_with(None, None)

    @pytest.mark.asyncio
    async def test_rate_limiter_resolved_via_parent(self) -> None:
        """When the fetch site lacks its own limiter, the coordinator parent's is used."""
        instance = _FakeCollector(retry_after_max_seconds=30)
        instance.parent = SimpleNamespace(rate_limiter=MagicMock())

        @with_error_handling(operation="429 op", max_retries=1, base_delay=0.01)
        async def method(self: _FakeCollector) -> str:
            raise _RateLimit429Error(retry_after=1.0)

        with self._no_sleep(), self._no_jitter():
            await method(instance)

        instance.parent.rate_limiter.record_throttle_event.assert_called_once_with(None, 1.0)

    @pytest.mark.asyncio
    async def test_no_rate_limiter_is_safe_noop(self) -> None:
        """No limiter on the instance or parent -> the hook is a silent no-op."""
        instance = _FakeCollector(retry_after_max_seconds=30)

        @with_error_handling(operation="429 op", max_retries=1, base_delay=0.01)
        async def method(self: _FakeCollector) -> str:
            raise _RateLimit429Error(retry_after=1.0)

        with self._no_sleep(), self._no_jitter():
            result = await method(instance)

        assert result is None  # completed without raising despite no limiter
