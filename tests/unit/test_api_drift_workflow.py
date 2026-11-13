"""Contracts for the API drift workflow report and token scope."""

from pathlib import Path


def _workflow() -> str:
    return Path(".github/workflows/api-drift.yml").read_text(encoding="utf-8")


def test_oasdiff_stderr_stays_out_of_the_fingerprinted_report() -> None:
    """Docker progress must not alter the report's fingerprint."""
    step = (
        _workflow().split("- name: oasdiff breaking on reduced specs", 1)[1].split("- name:", 1)[0]
    )
    assert "2>&1" not in step
    assert ">> /tmp/drift.md 2>/tmp/oasdiff.stderr" in step


def test_oasdiff_tool_error_prints_stderr() -> None:
    """Tool errors remain visible in the job log."""
    step = (
        _workflow()
        .split("- name: Fail on oasdiff tool error (exit not 0/1)", 1)[1]
        .split("- name:", 1)[0]
    )
    assert "cat /tmp/oasdiff.stderr || true" in step
    assert step.index("cat /tmp/oasdiff.stderr") < step.index("cat /tmp/drift.md")


def test_drift_workflow_token_has_no_pull_request_scope() -> None:
    """Only the required contents and issue scopes are granted."""
    workflow = _workflow()
    assert "pull-requests:" not in workflow
    permissions = workflow.split("permissions:\n", 1)[1].split("\njobs:", 1)[0]
    assert permissions.strip().splitlines() == ["contents: read", "  issues: write"]
