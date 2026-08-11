"""Tests for the apidrift acknowledge (ignore) file (#693)."""

from __future__ import annotations

from pathlib import Path

from apidrift.acknowledge import apply_acknowledgements, load_patterns
from apidrift.conformance import Finding
from apidrift.report import has_actionable


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "apidrift-ignore.txt"
    path.write_text(text)
    return path


def test_comments_and_blanks_are_skipped(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "# a comment\n\n   \nop-deprecated\n  # indented comment\ntype-mismatch\n",
    )

    assert load_patterns(path) == ["op-deprecated", "type-mismatch"]


def test_missing_file_yields_no_patterns(tmp_path: Path) -> None:
    assert load_patterns(tmp_path / "nope.txt") == []


def test_none_path_yields_no_patterns() -> None:
    assert load_patterns(None) == []


def test_acknowledged_warning_is_downgraded_not_dropped() -> None:
    """An accepted risk must stay visible, or it gets forgotten."""
    findings = [Finding("WARNING", "op-newly-deprecated", "getThing", "GET /thing deprecated")]

    out = apply_acknowledgements(findings, ["op-newly-deprecated"])

    assert len(out) == 1
    assert out[0].severity == "INFO"
    assert out[0].kind == "op-newly-deprecated-acknowledged"
    assert out[0].op == "getThing"
    assert not has_actionable(out)


def test_unmatched_finding_still_gates() -> None:
    findings = [Finding("WARNING", "type-mismatch", "getOther", "Model.x: int vs string")]

    out = apply_acknowledgements(findings, ["op-newly-deprecated"])

    assert out == findings
    assert has_actionable(out)


def test_match_is_case_insensitive_and_substring() -> None:
    findings = [Finding("BREAKING", "missing-op", "getThing", "consumed op removed")]

    out = apply_acknowledgements(findings, ["GETTHING"])

    assert out[0].severity == "INFO"


def test_pattern_can_target_the_detail_text() -> None:
    findings = [
        Finding("WARNING", "type-mismatch", "getA", "ModelA.count: (str,) vs spec ['integer']"),
        Finding("WARNING", "type-mismatch", "getB", "ModelB.name: (int,) vs spec ['string']"),
    ]

    out = apply_acknowledgements(findings, ["ModelA.count"])

    assert [f.severity for f in out] == ["INFO", "WARNING"]


def test_info_findings_are_left_alone() -> None:
    """Acknowledging is about gating; an INFO has nothing to downgrade."""
    findings = [Finding("INFO", "derived", "Thing", "computed model, not API-mapped")]

    assert apply_acknowledgements(findings, ["derived"]) == findings


def test_no_patterns_is_identity() -> None:
    findings = [Finding("WARNING", "type-mismatch", "getA", "x")]

    assert apply_acknowledgements(findings, []) == findings
