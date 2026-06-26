"""Render drift findings as Markdown or JSON."""

from __future__ import annotations

import json
from dataclasses import asdict

from apidrift.conformance import Finding

_ACTIONABLE = {"BREAKING", "WARNING"}
_ORDER = {"BREAKING": 0, "WARNING": 1, "INFO": 2}


def has_actionable(findings: list[Finding]) -> bool:
    """True if any finding is BREAKING or WARNING (i.e. should fail the gate)."""
    return any(f.severity in _ACTIONABLE for f in findings)


def render_markdown(findings: list[Finding]) -> str:
    """Render findings as a Markdown table, or a clean-run message."""
    if not findings:
        return "No drift detected on consumed operations.\n"
    lines = ["| Severity | Op | Kind | Detail |", "| --- | --- | --- | --- |"]
    for f in sorted(findings, key=lambda x: (_ORDER.get(x.severity, 9), x.op, x.kind)):
        lines.append(f"| {f.severity} | {f.op} | {f.kind} | {f.detail} |")
    return "\n".join(lines) + "\n"


def render_json(findings: list[Finding]) -> str:
    """Render findings as a JSON array."""
    return json.dumps([asdict(f) for f in findings], indent=2)
