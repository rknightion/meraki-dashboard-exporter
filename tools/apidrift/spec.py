"""Load and dereference OpenAPI specs for drift detection."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any


def load_spec(path: str) -> dict[str, Any]:
    """Load an OpenAPI spec from an (optionally gzipped) JSON file."""
    raw = Path(path).read_bytes()
    if path.endswith(".gz") or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    result: dict[str, Any] = json.loads(raw)
    return result


def load_spec_bytes(raw: bytes) -> dict[str, Any]:
    """Parse an OpenAPI spec from raw (optionally gzipped) bytes."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    result: dict[str, Any] = json.loads(raw)
    return result


def resolve_ref(spec: dict[str, Any], ref: str) -> Any:
    """Resolve a local JSON pointer like ``#/components/schemas/Foo``."""
    if not ref.startswith("#/"):
        raise ValueError(f"only local refs supported: {ref}")
    node: Any = spec
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node
