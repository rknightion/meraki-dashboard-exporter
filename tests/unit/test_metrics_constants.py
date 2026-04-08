"""Tests for metric constant naming consistency."""

from __future__ import annotations

import pytest

from meraki_dashboard_exporter.core.constants.metrics_constants import MSMetricName


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
