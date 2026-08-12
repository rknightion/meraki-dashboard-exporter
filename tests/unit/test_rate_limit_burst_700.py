"""Regression coverage for the documented Meraki burst allowance (#700)."""

from __future__ import annotations

from meraki_dashboard_exporter.core.config_models import APISettings


def test_default_rate_limit_burst_respects_vendor_allowance() -> None:
    """A fresh bucket must not start with more than the documented +10 burst."""
    assert APISettings().rate_limit_burst == 10
