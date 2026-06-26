"""Reduce an OpenAPI spec to a consumed-operation sub-spec.

The Meraki spec (v1.71.0) inlines all schemas, so the transitive ``$ref``
resolution below is effectively a no-op today; it is retained so the reducer
stays correct if Meraki ever switches to component references.
"""

from __future__ import annotations

import copy
from typing import Any

_METHODS = ("get", "put", "post", "delete", "patch", "options", "head")


def index_operations(spec: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Map operationId -> (path, method) for every operation in the spec."""
    out: dict[str, tuple[str, str]] = {}
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in _METHODS:
            op = item.get(method)
            if isinstance(op, dict) and "operationId" in op:
                out[op["operationId"]] = (path, method)
    return out


def _collect_refs(node: Any, acc: set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            acc.add(ref)
        for value in node.values():
            _collect_refs(value, acc)
    elif isinstance(node, list):
        for value in node:
            _collect_refs(value, acc)


def _component_for(ref: str) -> tuple[str, str] | None:
    """Map ``#/components/schemas/Foo`` -> ``("schemas", "Foo")``."""
    parts = ref.lstrip("#/").split("/")
    if len(parts) == 3 and parts[0] == "components":
        return parts[1], parts[2]
    return None


def reduce_spec(spec: dict[str, Any], op_ids: set[str]) -> dict[str, Any]:
    """Build a sub-spec with only op_ids' operations + transitively referenced components."""
    idx = index_operations(spec)
    reduced: dict[str, Any] = {
        "openapi": spec.get("openapi", "3.0.0"),
        "info": spec.get("info", {"title": "reduced", "version": "0"}),
        "paths": {},
        "components": {},
    }
    refs: set[str] = set()
    for op_id in sorted(op_ids):
        loc = idx.get(op_id)
        if loc is None:
            continue
        path, method = loc
        operation = copy.deepcopy(spec["paths"][path][method])
        reduced["paths"].setdefault(path, {})[method] = operation
        _collect_refs(operation, refs)

    src_components = spec.get("components", {})
    seen: set[str] = set()
    while refs:
        ref = refs.pop()
        if ref in seen:
            continue
        seen.add(ref)
        comp = _component_for(ref)
        if comp is None:
            continue
        section, name = comp
        node = src_components.get(section, {}).get(name)
        if node is None:
            continue
        reduced["components"].setdefault(section, {})[name] = copy.deepcopy(node)
        _collect_refs(node, refs)
    return reduced
