"""Tests for finding rendering."""

from __future__ import annotations

import json

from apidrift.conformance import Coverage, Finding
from apidrift.report import (
    has_actionable,
    render_coverage_json,
    render_coverage_markdown,
    render_json,
    render_markdown,
)


def test_has_actionable() -> None:
    assert has_actionable([Finding("BREAKING", "k", "op", "d")])
    assert has_actionable([Finding("WARNING", "k", "op", "d")])
    assert not has_actionable([Finding("INFO", "k", "op", "d")])
    assert not has_actionable([])


def test_render_markdown_has_table_header() -> None:
    md = render_markdown([Finding("BREAKING", "missing-field", "getX", "detail")])
    assert "| Severity | Op | Kind | Detail |" in md
    assert "getX" in md


def test_render_markdown_empty_is_clean_message() -> None:
    assert "No drift" in render_markdown([])


def test_render_json_roundtrips() -> None:
    out = render_json([Finding("INFO", "unmapped", "M", "d")])
    assert json.loads(out)[0]["kind"] == "unmapped"


def test_render_coverage_markdown_lists_unmapped() -> None:
    cov = Coverage(total=3, mapped=["A"], beta=[], derived=["B"], unmapped=["C"])
    md = render_coverage_markdown(cov)
    assert "annotation coverage" in md
    assert "- C" in md  # unmapped model listed


def test_render_coverage_json_roundtrips() -> None:
    cov = Coverage(total=2, mapped=["A"], beta=["A"], derived=[], unmapped=[])
    out = json.loads(render_coverage_json(cov))
    assert out["total"] == 2
    assert out["beta"] == ["A"]


# --- report layout: actionable first, routine INFO collapsed (#693) -------------


def test_actionable_findings_come_before_informational() -> None:
    findings = [
        Finding("INFO", "derived", "Thing", "computed model, not API-mapped"),
        Finding("WARNING", "type-mismatch", "getA", "Model.x mismatch"),
    ]

    out = render_markdown(findings)

    assert out.index("## Actionable (1)") < out.index("<details>")
    assert out.index("type-mismatch") < out.index("derived")


def test_informational_summary_carries_per_kind_counts() -> None:
    findings = [
        Finding("INFO", "derived", "A", "d"),
        Finding("INFO", "derived", "B", "d"),
        Finding("INFO", "model-extra", "C", "e"),
    ]

    out = render_markdown(findings)

    assert "Informational (3)" in out
    assert "derived x2" in out
    assert "model-extra x1" in out


def test_no_actionable_findings_says_so_explicitly() -> None:
    out = render_markdown([Finding("INFO", "derived", "A", "d")])

    assert "## Actionable (0)" in out
    assert "Nothing actionable" in out


def test_clean_run_message_unchanged() -> None:
    assert render_markdown([]) == "No drift detected on consumed operations.\n"
