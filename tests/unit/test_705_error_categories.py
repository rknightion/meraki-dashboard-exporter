"""Known upstream failures retain their bounded error categories (#705)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.core.batch_processing import process_in_batches_with_errors
from meraki_dashboard_exporter.core.error_handling import (
    CollectorError,
    ErrorCategory,
    categorize_error,
)


class _HTTPError(Exception):
    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"HTTP {status}")


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (402, ErrorCategory.API_NOT_AVAILABLE),
        (429, ErrorCategory.API_RATE_LIMIT),
        (502, ErrorCategory.API_SERVER_ERROR),
        (503, ErrorCategory.API_SERVER_ERROR),
        (530, ErrorCategory.API_SERVER_ERROR),
    ],
)
def test_known_http_failures_have_stable_categories(status: int, expected: ErrorCategory) -> None:
    """Observed gateway statuses, including Cloudflare 530, do not become unknown."""
    assert categorize_error(_HTTPError(status)) is expected


def test_collector_error_keeps_its_original_category() -> None:
    """Coordinator catches must retain classification from the failed fetcher."""
    error = CollectorError("upstream overloaded", ErrorCategory.API_SERVER_ERROR)
    assert categorize_error(error) is ErrorCategory.API_SERVER_ERROR


def test_connection_error_has_a_bounded_connectivity_category() -> None:
    """Multi-domain connectivity evidence must not collapse to unknown."""
    assert categorize_error(ConnectionError("connection reset")) is ErrorCategory.CONNECTIVITY


@pytest.mark.asyncio
async def test_batch_error_sink_receives_the_original_exception() -> None:
    """Coordinator batch catches classify a 429 instead of recording unknown."""
    categories: list[ErrorCategory] = []

    async def fail(_item: int) -> None:
        raise _HTTPError(429)

    await process_in_batches_with_errors(
        [1],
        fail,
        delay_between_batches=0,
        on_error=lambda error: categories.append(categorize_error(error)),
    )

    assert categories == [ErrorCategory.API_RATE_LIMIT]


@pytest.mark.asyncio
async def test_device_mr_coordinator_preserves_known_subcollector_category() -> None:
    """A known MR subcollector failure is not rewritten to unknown."""
    collector = object.__new__(DeviceCollector)
    collector.inventory = None
    collector.mr_collector = AsyncMock()
    collector.mr_collector.collect_wireless_clients.side_effect = _HTTPError(503)
    collector._track_error = MagicMock()  # type: ignore[method-assign]

    await collector._collect_mr_specific_metrics("org-1", "Org", [], {})

    collector._track_error.assert_any_call(ErrorCategory.API_SERVER_ERROR)
