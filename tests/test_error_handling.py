"""Tests for error handling utilities."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from meraki_dashboard_exporter.core.error_handling import (
    APINotAvailableError,
    CollectorError,
    DataValidationError,
    ErrorCategory,
    RetryableAPIError,
    batch_with_concurrency_limit,
    validate_response_format,
    with_error_handling,
    with_semaphore_limit,
)


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
    async def test_collector_context_extraction(self) -> None:
        """Test context extraction from collector instance."""

        class MockCollector:
            update_tier = MagicMock(value="MEDIUM")

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

        # Patch asyncio.sleep in the error_handling module
        with patch(
            "meraki_dashboard_exporter.core.error_handling.asyncio.sleep", mock_sleep
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

        with patch(
            "meraki_dashboard_exporter.core.error_handling.asyncio.sleep", mock_sleep
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
