"""Acknowledge (ignore) support for apidrift findings.

`spec/oasdiff-ignore.txt` lets a known oasdiff change be accepted without re-vendoring
the whole baseline. This is the equivalent for apidrift's own findings, and exists for
the same reason: without it, a WARNING we have consciously decided not to act on gates
the build forever and pins the daily tracking issue open, which trains everyone to
ignore the lane.

An acknowledged finding is **downgraded, never dropped**. It stays in the report as
``INFO <kind>-acknowledged`` so the accepted risk remains visible — deleting it would
make it invisible, which is how accepted risks get forgotten. Only its ability to gate
(exit 3) is removed.
"""

from __future__ import annotations

from pathlib import Path

from apidrift.conformance import Finding

_ACTIONABLE = {"BREAKING", "WARNING"}


def load_patterns(path: str | Path | None) -> list[str]:
    """Read acknowledge patterns from a file, one per line.

    Blank lines and ``#`` comments are skipped. A missing file is not an error — the
    acknowledge file is optional, and the common case is not having one.
    """
    if path is None:
        return []
    file = Path(path)
    if not file.is_file():
        return []
    patterns: list[str] = []
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _haystack(finding: Finding) -> str:
    return f"{finding.kind}|{finding.op}|{finding.detail}".casefold()


def apply_acknowledgements(findings: list[Finding], patterns: list[str]) -> list[Finding]:
    """Downgrade any actionable finding matching an acknowledge pattern to INFO.

    Matching is a case-insensitive substring test against ``kind|op|detail``, so a
    pattern can be as coarse as a finding kind (``op-deprecated``) or as precise as a
    single model field (``ModelA.count``).

    INFO findings pass through untouched: acknowledging is purely about gating, and an
    INFO has nothing to downgrade.
    """
    if not patterns:
        return findings
    folded = [p.casefold() for p in patterns]
    out: list[Finding] = []
    for finding in findings:
        if finding.severity not in _ACTIONABLE:
            out.append(finding)
            continue
        haystack = _haystack(finding)
        if any(pattern in haystack for pattern in folded):
            out.append(Finding("INFO", f"{finding.kind}-acknowledged", finding.op, finding.detail))
        else:
            out.append(finding)
    return out
