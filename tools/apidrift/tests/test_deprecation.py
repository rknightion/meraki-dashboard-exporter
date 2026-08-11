"""Tests for deprecated-operation detection over the consumed surface (#690)."""

from __future__ import annotations

from typing import Any

from apidrift.conformance import check_deprecated_operations


def _spec(ops: dict[str, bool]) -> dict[str, Any]:
    """Build a spec where each op maps to whether it is marked deprecated."""
    paths: dict[str, Any] = {}
    for op_id, deprecated in ops.items():
        operation: dict[str, Any] = {"operationId": op_id, "responses": {}}
        if deprecated:
            operation["deprecated"] = True
            operation["x-deprecation-notice"] = (
                "Deprecated: This operation has been marked as deprecated. For more "
                "information, visit the <a href='https://example.invalid/deprecated'>"
                "deprecated operations page</a>"
            )
        paths[f"/{op_id}"] = {"get": operation}
    return {"openapi": "3.0.1", "info": {"title": "t", "version": "1"}, "paths": paths}


def test_deprecated_in_both_is_info() -> None:
    """A long-standing deprecation is a visible backlog item, not gating drift."""
    baseline = _spec({"getThing": True})
    live = _spec({"getThing": True})

    findings = check_deprecated_operations(["getThing"], baseline, live)

    assert len(findings) == 1
    assert findings[0].severity == "INFO"
    assert findings[0].kind == "op-deprecated"
    assert findings[0].op == "getThing"


def test_newly_deprecated_is_warning() -> None:
    """Deprecated in live but not baseline is real drift and must gate (exit 3)."""
    baseline = _spec({"getThing": False})
    live = _spec({"getThing": True})

    findings = check_deprecated_operations(["getThing"], baseline, live)

    assert len(findings) == 1
    assert findings[0].severity == "WARNING"
    assert findings[0].kind == "op-newly-deprecated"


def test_not_deprecated_produces_no_finding() -> None:
    baseline = _spec({"getThing": False})
    live = _spec({"getThing": False})

    assert check_deprecated_operations(["getThing"], baseline, live) == []


def test_op_absent_from_live_is_ignored() -> None:
    """Scanner false positives (`api`, `serial`) must never produce a finding.

    A genuinely removed op is reported as BREAKING missing-op elsewhere, so this
    check stays silent rather than double-reporting.
    """
    baseline = _spec({"getThing": True})
    live = _spec({})

    assert check_deprecated_operations(["getThing", "serial"], baseline, live) == []


def test_absent_from_baseline_but_deprecated_in_live_is_newly_deprecated() -> None:
    """An op that never existed in the baseline can still be newly deprecated to us."""
    baseline = _spec({})
    live = _spec({"getThing": True})

    findings = check_deprecated_operations(["getThing"], baseline, live)

    assert [f.kind for f in findings] == ["op-newly-deprecated"]


def test_detail_carries_route_and_reference_url() -> None:
    """The finding must say which route, and where to read about the deprecation."""
    baseline = _spec({"getThing": True})
    live = _spec({"getThing": True})

    detail = check_deprecated_operations(["getThing"], baseline, live)[0].detail

    assert "GET /getThing" in detail
    assert "https://example.invalid/deprecated" in detail


def test_findings_are_sorted_and_deduped() -> None:
    baseline = _spec({"getA": True, "getB": True})
    live = _spec({"getA": True, "getB": True})

    findings = check_deprecated_operations(["getB", "getA", "getA"], baseline, live)

    assert [f.op for f in findings] == ["getA", "getB"]
