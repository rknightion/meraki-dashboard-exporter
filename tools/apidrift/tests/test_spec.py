"""Tests for the OpenAPI spec loader."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from apidrift.spec import load_spec, load_spec_bytes, resolve_ref


def test_load_spec_plain_json(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"openapi": "3.0.1", "paths": {}}))
    spec = load_spec(str(p))
    assert spec["openapi"] == "3.0.1"


def test_load_spec_gzip(tmp_path: Path) -> None:
    p = tmp_path / "s.json.gz"
    p.write_bytes(gzip.compress(json.dumps({"openapi": "3.0.1"}).encode()))
    spec = load_spec(str(p))
    assert spec["openapi"] == "3.0.1"


def test_load_spec_bytes_detects_gzip() -> None:
    raw = gzip.compress(json.dumps({"openapi": "3.0.1"}).encode())
    assert load_spec_bytes(raw)["openapi"] == "3.0.1"


def test_resolve_ref_walks_pointer() -> None:
    spec = {"components": {"schemas": {"Foo": {"type": "object"}}}}
    assert resolve_ref(spec, "#/components/schemas/Foo") == {"type": "object"}
