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
