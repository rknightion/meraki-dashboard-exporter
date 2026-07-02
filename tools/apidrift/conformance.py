"""Check Pydantic model fields against the live spec's response schemas.

Findings are intentionally conservative. A model field absent from every mapped
op is reported as INFO (``model-extra``) — the exporter's models legitimately
carry derived/enrichment fields — so it never gates a build. Only a concrete
``type-mismatch`` or a vanished mapped op (``model-op-absent``) is WARNING.
Genuine upstream field removals are caught independently by oasdiff against the
reduced specs, so this layer is the secondary "is our parsing stale" signal.

Models declare their source via own (non-inherited) class attributes:
``__meraki_op__`` (a str or list[str] of source operationIds — a list is the
UNION conformance surface for models that aggregate several endpoints) or
``__meraki_derived__ = True`` for computed/transformed shapes with no single
upstream response. Unannotated models are reported INFO so the gap stays visible.

A model may additionally set ``__meraki_beta__ = True`` to declare that its
``__meraki_op__`` operation(s) live on Meraki's *beta* spec channel, which this
tool does NOT fetch (it pulls a single fixed GA spec). A mapped op that is absent
from the GA spec is then reported INFO ``beta-blind-spot`` — a *visible* record
that this operation's drift is out of scope — instead of a false WARNING
``model-op-absent`` (or a silent skip). This is the minimal, honest treatment of
the beta blind spot until/unless full beta-channel fetching is implemented.
"""

from __future__ import annotations

import datetime
import types
import typing
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from apidrift.reducer import index_operations

_UNION_ORIGINS = frozenset({typing.Union, types.UnionType})

# OpenAPI type -> acceptable Python types. datetime/date are accepted for string
# (ISO-8601) AND integer/number (epoch) because Pydantic coerces both — a common,
# correct pattern in this codebase (e.g. getNetworkClients firstSeen/lastSeen).
_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "string": (str, datetime.datetime, datetime.date),
    "integer": (int, datetime.datetime, datetime.date),
    "number": (float, int, datetime.datetime, datetime.date),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (dict,),
}


@dataclass(frozen=True)
class Finding:
    """A single drift finding."""

    severity: str  # BREAKING | WARNING | INFO
    kind: str
    op: str
    detail: str


def _concrete_types(annotation: Any) -> tuple[type, ...]:
    """Flatten a type annotation to its concrete runtime types.

    Unwraps ``X | None`` / ``Optional[X]`` / ``Union`` and reduces generic
    aliases (``list[int]`` -> ``list``). Returns an empty tuple for things with
    no usable runtime type (e.g. ``Literal[...]``, ``None``).
    """
    if annotation is Any:
        # Intentionally untyped — never a mismatch.
        return ()
    origin = typing.get_origin(annotation)
    if origin in _UNION_ORIGINS:
        out: list[type] = []
        for arg in typing.get_args(annotation):
            out.extend(_concrete_types(arg))
        return tuple(out)
    if origin is not None:
        return (origin,) if isinstance(origin, type) else ()
    if annotation is type(None):
        return ()
    return (annotation,) if isinstance(annotation, type) else ()


def response_properties(spec: dict[str, Any], op_id: str) -> dict[str, Any] | None:
    """Return the 2xx application/json response schema for op_id (array -> item schema).

    Returns None when the operation is absent or has no usable JSON response schema.
    """
    idx = index_operations(spec)
    loc = idx.get(op_id)
    if loc is None:
        return None
    path, method = loc
    operation = spec["paths"][path][method]
    for code, resp in (operation.get("responses") or {}).items():
        if not str(code).startswith("2"):
            continue
        schema = resp.get("content", {}).get("application/json", {}).get("schema")
        if isinstance(schema, dict):
            if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
                items: dict[str, Any] = schema["items"]
                return items
            return schema
    return None


def _normalize_ops(value: object) -> list[str]:
    """Coerce a ``__meraki_op__`` annotation (str or list[str]) to a list."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return []


def _union_properties(
    spec: dict[str, Any], op_ids: list[str]
) -> tuple[dict[str, set[str | None]], list[str], list[str]]:
    """Merge the response properties of several ops.

    Returns ``(alias -> set of spec types across ops, resolved_ops, missing_ops)``.
    A field present in *any* mapped op is considered present; a type is acceptable
    if it matches in *any* mapped op (aggregate models source fields from several
    endpoints, so the union is the correct conformance surface).
    """
    union: dict[str, set[str | None]] = {}
    resolved: list[str] = []
    missing: list[str] = []
    for op_id in op_ids:
        schema = response_properties(spec, op_id)
        if schema is None:
            missing.append(op_id)
            continue
        resolved.append(op_id)
        for name, pschema in (schema.get("properties") or {}).items():
            spec_type = pschema.get("type") if isinstance(pschema, dict) else None
            union.setdefault(name, set()).add(spec_type)
    return union, resolved, missing


def check_models(models: list[type], spec: dict[str, Any]) -> list[Finding]:
    """Return findings comparing each model's fields to its mapped operation(s).

    Mapping is declared per model via class attributes (own attribute only, never
    inherited): ``__meraki_op__`` (a str or list[str] of source operationIds) or
    ``__meraki_derived__ = True`` for models that are transformed/computed shapes
    with no single upstream response. Unannotated models are reported INFO so the
    coverage gap stays visible.
    """
    findings: list[Finding] = []
    for model in models:
        name = model.__name__
        if model.__dict__.get("__meraki_derived__") is True:
            findings.append(Finding("INFO", "derived", name, "computed model, not API-mapped"))
            continue
        op_ids = _normalize_ops(model.__dict__.get("__meraki_op__"))
        if not op_ids:
            findings.append(Finding("INFO", "unmapped", name, "no __meraki_op__ annotation"))
            continue

        is_beta = model.__dict__.get("__meraki_beta__") is True
        union, resolved, missing = _union_properties(spec, op_ids)
        label = "+".join(op_ids)
        if not resolved:
            # Every mapped op is missing from the (GA) spec. For a beta-declared
            # model this is expected — the op lives on the un-fetched beta channel —
            # so surface it as a visible, non-gating blind spot rather than a false
            # WARNING that the exporter's parsing is stale.
            if is_beta:
                findings.append(
                    Finding(
                        "INFO",
                        "beta-blind-spot",
                        label,
                        f"{name}: mapped op(s) on beta channel, absent from GA spec (drift out of scope)",
                    )
                )
            else:
                findings.append(
                    Finding(
                        "WARNING", "model-op-absent", label, f"{name}: no mapped op has a schema"
                    )
                )
            continue
        for op_id in missing:
            if is_beta:
                findings.append(
                    Finding(
                        "INFO",
                        "beta-blind-spot",
                        op_id,
                        f"{name}: beta-channel op not in GA spec (drift out of scope)",
                    )
                )
            else:
                findings.append(
                    Finding(
                        "WARNING", "model-op-absent", op_id, f"{name}: mapped op absent from spec"
                    )
                )

        fields: dict[str, Any] = getattr(model, "model_fields", {})
        for fname, info in fields.items():
            alias = getattr(info, "alias", None) or fname
            if alias not in union:
                # Informational, not gating: the model carries a field absent from
                # every mapped op response. Usually a derived/enrichment field or a
                # stale one worth a human look — not, by itself, upstream drift.
                findings.append(
                    Finding(
                        "INFO",
                        "model-extra",
                        label,
                        f"{name}.{fname} ('{alias}') not in any mapped op response",
                    )
                )
                continue
            concrete = _concrete_types(info.annotation)
            if not concrete:
                continue
            spec_types = union[alias]
            # Acceptable if the model type matches the spec type in ANY mapped op,
            # or where the spec gives no type (untyped/object) for this field.
            ok = any(t is None for t in spec_types) or any(
                issubclass(c, _TYPE_MAP[t]) for t in spec_types if t in _TYPE_MAP for c in concrete
            )
            if not ok:
                # Strictly-narrower typing: the spec declares the field a bare
                # ``object`` (an untyped dict) but the model gives it a structured
                # Pydantic submodel. That is a legitimate, correct narrowing — the
                # exporter parses a known nested shape the spec left unstructured —
                # not upstream drift, so report INFO (does not gate the build).
                # Genuine mismatches (e.g. spec integer vs model str) stay WARNING.
                if spec_types == {"object"} and all(
                    isinstance(c, type) and issubclass(c, BaseModel) for c in concrete
                ):
                    findings.append(
                        Finding(
                            "INFO",
                            "model-narrower",
                            label,
                            f"{name}.{fname}: model {concrete} narrows spec 'object'",
                        )
                    )
                    continue
                findings.append(
                    Finding(
                        "WARNING",
                        "type-mismatch",
                        label,
                        f"{name}.{fname}: model {concrete} vs spec {sorted(t or '?' for t in spec_types)}",
                    )
                )
    return findings


@dataclass(frozen=True)
class Coverage:
    """apidrift annotation-coverage summary over the registered models.

    Every registered Pydantic model falls into exactly one bucket:

    * ``mapped`` - carries ``__meraki_op__``; its fields are conformance-checked
      against the live spec (``beta`` is the subset whose ops are declared
      beta-channel via ``__meraki_beta__``, a known drift blind spot).
    * ``derived`` - carries ``__meraki_derived__ = True``; a computed/transformed
      shape or a nested sub-object with no single upstream response.
    * ``unmapped`` - no annotation; the coverage gap that should be driven to zero
      for top-level API-response models (each entry is a model class name).
    """

    total: int
    mapped: list[str]
    beta: list[str]
    derived: list[str]
    unmapped: list[str]


def coverage(models: list[type]) -> Coverage:
    """Classify each model by its apidrift annotation for a coverage report.

    Uses the same own/non-inherited attribute lookup as :func:`check_models`, so
    a subclass never inherits its parent's ``__meraki_op__``/``__meraki_derived__``.
    """
    mapped: list[str] = []
    beta: list[str] = []
    derived: list[str] = []
    unmapped: list[str] = []
    for model in models:
        name = model.__name__
        if model.__dict__.get("__meraki_derived__") is True:
            derived.append(name)
        elif _normalize_ops(model.__dict__.get("__meraki_op__")):
            mapped.append(name)
            if model.__dict__.get("__meraki_beta__") is True:
                beta.append(name)
        else:
            unmapped.append(name)
    return Coverage(
        total=len(models),
        mapped=sorted(mapped),
        beta=sorted(beta),
        derived=sorted(derived),
        unmapped=sorted(unmapped),
    )
