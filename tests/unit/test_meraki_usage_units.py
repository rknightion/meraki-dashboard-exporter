"""Meraki usage units are binary (#1032)."""

from meraki_dashboard_exporter.core.constants.api_constants import MERAKI_KB_BYTES, MERAKI_MB_BYTES


def test_meraki_usage_units_match_the_dashboard() -> None:
    """Worked example from the 2026-11-11 dashboard comparison.

    One client's 7-day usage was 1,539,028,878 KB in the clients endpoint and
    1,502,611.6 MB in the top-clients endpoint; the dashboard showed 1.43 TB.
    """
    assert MERAKI_KB_BYTES == 1024
    assert MERAKI_MB_BYTES == 1024 * MERAKI_KB_BYTES
    assert 1_539_028_878 * MERAKI_KB_BYTES == 1_575_965_571_072
    assert round(1_539_028_878 * MERAKI_KB_BYTES / 1024**4, 2) == 1.43
    assert round(1_502_611.6 * MERAKI_MB_BYTES / 1024**4, 2) == 1.43
