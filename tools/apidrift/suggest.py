"""Suggest source operations for unmapped Pydantic models by field overlap.

Turns the otherwise-archaeological task of mapping a model to its source Meraki
operation into a review step: for each model, score every spec operation by how
much of the model's field set its response schema covers, and surface the best
candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apidrift.conformance import response_properties
from apidrift.reducer import index_operations


@dataclass(frozen=True)
class Suggestion:
    """A candidate source operation for a model, with overlap score."""

    op: str
    score: float  # fraction of the model's fields present in the op response
    covered: int
    total: int


def _model_aliases(model: type) -> set[str]:
    fields: dict[str, Any] = getattr(model, "model_fields", {})
    return {getattr(info, "alias", None) or fname for fname, info in fields.items()}


def suggest_for_model(
    model: type, spec: dict[str, Any], *, op_ids: list[str] | None = None, top: int = 3
) -> list[Suggestion]:
    """Rank operations by how fully their response covers the model's fields."""
    aliases = _model_aliases(model)
    if not aliases:
        return []
    candidates = op_ids if op_ids is not None else list(index_operations(spec))
    scored: list[Suggestion] = []
    for op in candidates:
        schema = response_properties(spec, op)
        if schema is None:
            continue
        props = set((schema.get("properties") or {}).keys())
        covered = len(aliases & props)
        if covered == 0:
            continue
        scored.append(Suggestion(op, covered / len(aliases), covered, len(aliases)))
    scored.sort(key=lambda s: (s.score, s.covered), reverse=True)
    return scored[:top]


def render_suggestions(models: list[type], spec: dict[str, Any], op_ids: list[str]) -> str:
    """Render mapping suggestions for unmapped, non-derived models as Markdown."""
    lines = ["| Model | Candidate op | Coverage |", "| --- | --- | --- |"]
    for model in sorted(models, key=lambda m: m.__name__):
        if model.__dict__.get("__meraki_op__") or model.__dict__.get("__meraki_derived__"):
            continue
        suggestions = suggest_for_model(model, spec, op_ids=op_ids)
        if not suggestions:
            lines.append(f"| {model.__name__} | _(no overlap with consumed ops)_ | — |")
            continue
        for s in suggestions:
            lines.append(f"| {model.__name__} | {s.op} | {s.covered}/{s.total} ({s.score:.0%}) |")
    return "\n".join(lines) + "\n"
