"""Tests for logging decorator helper functions."""

# ruff: noqa: S101

import meraki_dashboard_exporter.core.logging_decorators as ld


def test_extract_context_from_args_and_kwargs():
    """Should prefer kwargs but fallback to first arg for org_id."""
    ctx = ld._extract_context(("org_123",), {"network_id": "n1", "name": "Test"})
    assert ctx == {"network_id": "n1", "name": "Test", "org_id": "org_123"}


def test_get_result_info_various_types():
    """Ensure result info summarises data correctly."""
    assert ld._get_result_info(None) == {"result": "none"}
    assert ld._get_result_info([1, 2]) == {"result_count": 2, "result_type": "list"}
    assert ld._get_result_info({"items": [1]}) == {"result_type": "dict", "result_count": 1}
    assert ld._get_result_info({"a": 1}) == {"result_type": "dict"}
    assert ld._get_result_info("hi") == {"result_type": "str"}
