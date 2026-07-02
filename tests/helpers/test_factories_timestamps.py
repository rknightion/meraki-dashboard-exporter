"""Regression tests for factory-generated timestamp formats.

Covers bug-bash finding F-164: `DeviceStatusFactory` and `TimeSeriesFactory`
built timestamps as `datetime.now(UTC).isoformat() + "Z"`, which produces a
malformed double-tz-suffix string like `2026-07-02T00:00:00+00:00Z`. That
string cannot be parsed by the `value.replace("Z", "+00:00")` /
`datetime.fromisoformat(...)` pattern used across the production codebase
(e.g. `collectors/devices/mt.py`) to parse Meraki timestamps.
"""

from __future__ import annotations

from datetime import datetime

from tests.helpers.factories import DeviceStatusFactory, TimeSeriesFactory


def _parse_like_production(value: str) -> datetime:
    """Mirror the `value.replace("Z", "+00:00")` parsing pattern used in production."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class TestDeviceStatusFactoryTimestamps:
    """DeviceStatusFactory timestamps must be parseable, not double-suffixed."""

    def test_create_last_reported_at_is_parseable(self) -> None:
        """create()'s lastReportedAt must not carry a double timezone suffix."""
        status = DeviceStatusFactory.create()
        value = status["lastReportedAt"]

        assert not value.endswith("+00:00Z"), f"malformed double-tz timestamp: {value}"
        _parse_like_production(value)  # must not raise

    def test_create_availability_last_reported_at_is_parseable(self) -> None:
        """create_availability()'s lastReportedAt must not carry a double timezone suffix."""
        availability = DeviceStatusFactory.create_availability()
        value = availability["lastReportedAt"]

        assert not value.endswith("+00:00Z"), f"malformed double-tz timestamp: {value}"
        _parse_like_production(value)  # must not raise


class TestTimeSeriesFactoryTimestamps:
    """TimeSeriesFactory timestamps must be parseable, not double-suffixed."""

    def test_create_data_points_timestamps_are_parseable(self) -> None:
        """create_data_points()'s timestamp field must not carry a double tz suffix."""
        points = TimeSeriesFactory.create_data_points(count=3)

        assert len(points) == 3
        for point in points:
            value = point["timestamp"]
            assert not value.endswith("+00:00Z"), f"malformed double-tz timestamp: {value}"
            _parse_like_production(value)  # must not raise

    def test_create_memory_usage_ts_is_parseable(self) -> None:
        """create_memory_usage()'s ts field must not carry a double tz suffix."""
        usage = TimeSeriesFactory.create_memory_usage(count=3)

        assert len(usage) == 3
        for entry in usage:
            value = entry["ts"]
            assert not value.endswith("+00:00Z"), f"malformed double-tz timestamp: {value}"
            _parse_like_production(value)  # must not raise
