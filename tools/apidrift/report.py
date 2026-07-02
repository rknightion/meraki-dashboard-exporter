"""Render drift findings as Markdown or JSON."""

from __future__ import annotations

import json
from dataclasses import asdict

from apidrift.conformance import Coverage, Finding

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


def render_coverage_markdown(cov: Coverage) -> str:
    """Render an annotation-coverage summary as Markdown."""
    lines = [
        "## apidrift annotation coverage",
        "",
        "| Bucket | Count |",
        "| --- | --- |",
        f"| mapped (`__meraki_op__`) | {len(cov.mapped)} |",
        f"| &nbsp;&nbsp;of which beta-channel (`__meraki_beta__`) | {len(cov.beta)} |",
        f"| derived (`__meraki_derived__`) | {len(cov.derived)} |",
        f"| unmapped (no annotation) | {len(cov.unmapped)} |",
        f"| **total** | **{cov.total}** |",
    ]
    if cov.unmapped:
        lines += ["", "Unmapped models:", *(f"- {name}" for name in cov.unmapped)]
    else:
        lines += ["", "No unmapped models — every model is mapped or explicitly derived."]
    if cov.beta:
        lines += [
            "",
            "Beta-channel models (drift blind spot):",
            *(f"- {name}" for name in cov.beta),
        ]
    return "\n".join(lines) + "\n"


def render_coverage_json(cov: Coverage) -> str:
    """Render the annotation-coverage summary as JSON."""
    return json.dumps(asdict(cov), indent=2)
