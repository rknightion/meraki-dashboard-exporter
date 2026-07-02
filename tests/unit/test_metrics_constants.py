"""Tests for metric constant naming consistency."""

from __future__ import annotations

import pytest

from meraki_dashboard_exporter.core.constants.metrics_constants import (
    CollectorMetricName,
    MSMetricName,
)


class TestMSMetricNaming:
    """Verify MS metric enum names match their string values."""

    @pytest.mark.parametrize(
        "enum_member,expected_unit",
        [
            ("MS_POE_PORT_POWER_WATTHOURS", "watthours"),
            ("MS_POE_TOTAL_POWER_WATTHOURS", "watthours"),
            ("MS_POE_NETWORK_TOTAL_WATTHOURS", "watthours"),
            ("MS_POE_BUDGET_WATTS", "watts"),
            ("MS_POWER_USAGE_WATTS", "watts"),
        ],
    )
    def test_poe_metric_unit_consistency(self, enum_member: str, expected_unit: str) -> None:
        """Verify POE metric enum names match their string value units."""
        member = MSMetricName[enum_member]
        assert expected_unit in member.value, (
            f"Enum {enum_member} value '{member.value}' does not contain expected unit '{expected_unit}'"
        )


class TestCollectorPerformanceMetricNames:
    """F-108: per-collector performance metric names are enum-backed and byte-identical.

    These 6 names were previously emitted as hardcoded string literals in
    core/collector.py and collectors/manager.py, violating the repo's
    no-hardcoded-metric-names rule. They must now exist on CollectorMetricName
    with exactly the same wire names.
    """

    @pytest.mark.parametrize(
        "enum_member,expected_value",
        [
            ("COLLECTOR_DURATION_SECONDS", "meraki_exporter_collector_duration_seconds"),
            ("COLLECTOR_ERRORS_TOTAL", "meraki_exporter_collector_errors_total"),
            (
                "COLLECTOR_SUCCESS_TIMESTAMP_SECONDS",
                "meraki_exporter_collector_success_timestamp_seconds",
            ),
            ("COLLECTOR_API_CALLS_TOTAL", "meraki_exporter_collector_api_calls_total"),
            ("COLLECTOR_FAILURE_STREAK", "meraki_exporter_collector_failure_streak"),
        ],
    )
    def test_enum_value_byte_identical(self, enum_member: str, expected_value: str) -> None:
        """Enum value must equal the previously-hardcoded metric name exactly."""
        assert CollectorMetricName[enum_member].value == expected_value

    def test_no_hardcoded_names_in_source(self) -> None:
        """The literal metric-name strings must no longer appear in the source files.

        They should be referenced via CollectorMetricName.<X>.value instead.
        """
        from pathlib import Path

        import meraki_dashboard_exporter as pkg

        root = Path(pkg.__file__).parent
        collector_src = (root / "core" / "collector.py").read_text()
        manager_src = (root / "collectors" / "manager.py").read_text()

        for literal in (
            '"meraki_exporter_collector_duration_seconds"',
            '"meraki_exporter_collector_errors_total"',
            '"meraki_exporter_collector_success_timestamp_seconds"',
            '"meraki_exporter_collector_api_calls_total"',
        ):
            assert literal not in collector_src, f"hardcoded {literal} still in collector.py"

        assert '"meraki_exporter_collector_failure_streak"' not in manager_src
