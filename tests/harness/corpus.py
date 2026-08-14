"""Digest-pinned, provenance-bearing corpus loading for the failure harness."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

LIVE_VERIFIED: Final = "LIVE-VERIFIED"
SHAPE_ASSUMED: Final = "SHAPE-ASSUMED"
REQUIRED_OPERATIONS: Final = frozenset({
    "getOrganization",
    "getOrganizationNetworks",
    "getOrganizationDevices",
    "getOrganizationDevicesAvailabilities",
})


class CorpusError(ValueError):
    """Raised when a replay corpus is absent, unsafe, or unverifiable."""


@dataclass(frozen=True)
class Fixture:
    """One immutable route and its verified response fixture."""

    file: Path
    method: str
    path: str
    query: str
    sdk_operation: str


@dataclass(frozen=True)
class Corpus:
    """Verified fixtures rooted at the manifest directory."""

    fixtures: tuple[Fixture, ...]


def load_manifest(manifest_path: Path, *, require_real: bool) -> Corpus:
    """Load a manifest only when every row has valid provenance and digest."""
    if not manifest_path.is_file():
        raise CorpusError(f"corpus manifest is absent: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CorpusError(f"invalid manifest JSON: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise CorpusError("unsupported manifest schema_version")
    rows = manifest.get("fixtures")
    if not isinstance(rows, list) or not rows:
        raise CorpusError("manifest must contain at least one fixture")

    fixtures: list[Fixture] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CorpusError(f"fixture row {index} is not an object")
        _validate_row(row, index, require_real)
        fixture_name = row["fixture"]
        if not isinstance(fixture_name, str):  # guarded by _validate_row; narrows for mypy
            raise CorpusError(f"fixture row {index} fixture must be a string")
        fixture_path = manifest_path.parent / fixture_name
        if not fixture_path.is_file():
            raise CorpusError(f"fixture row {index} is absent: {fixture_name}")
        digest = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            raise CorpusError(f"fixture row {index} digest mismatch")
        fixtures.append(
            Fixture(
                file=fixture_path,
                method=row["method"],
                path=row["path"],
                query=row.get("query", ""),
                sdk_operation=row["sdk_operation"],
            )
        )
    if require_real:
        _validate_real_corpus_contract(fixtures)
    return Corpus(tuple(fixtures))


def _validate_real_corpus_contract(fixtures: list[Fixture]) -> None:
    """Require the one complete, route-unique capture set accepted by the runner."""
    operations = [fixture.sdk_operation for fixture in fixtures]
    duplicate_operations = sorted({
        operation for operation in operations if operations.count(operation) > 1
    })
    if duplicate_operations:
        raise CorpusError(f"duplicate sdk_operation: {', '.join(duplicate_operations)}")
    if set(operations) != REQUIRED_OPERATIONS:
        missing = sorted(REQUIRED_OPERATIONS - set(operations))
        unexpected = sorted(set(operations) - REQUIRED_OPERATIONS)
        detail = ", ".join(
            part
            for part in (
                f"missing {', '.join(missing)}" if missing else "",
                f"unexpected {', '.join(unexpected)}" if unexpected else "",
            )
            if part
        )
        raise CorpusError(f"real corpus must contain exactly the required operations ({detail})")
    routes = [(fixture.method, fixture.path, fixture.query) for fixture in fixtures]
    if len(routes) != len(set(routes)):
        raise CorpusError("duplicate method/path/query route")


def _validate_row(row: dict[str, object], index: int, require_real: bool) -> None:
    required_strings = (
        "fixture",
        "sha256",
        "capture_date_utc",
        "product_family",
        "method",
        "path",
        "sdk_operation",
        "evidence_source",
        "evidence_status",
    )
    missing = [
        field for field in required_strings if not isinstance(row.get(field), str) or not row[field]
    ]
    if missing:
        raise CorpusError(f"fixture row {index} missing required fields: {', '.join(missing)}")
    sanitizer = row.get("sanitizer")
    if not isinstance(sanitizer, dict) or not all(
        isinstance(sanitizer.get(field), str) and sanitizer[field]
        for field in ("name", "version", "method")
    ):
        raise CorpusError(f"fixture row {index} has incomplete sanitizer provenance")
    status = row["evidence_status"]
    if status not in {LIVE_VERIFIED, SHAPE_ASSUMED}:
        raise CorpusError(f"fixture row {index} has invalid evidence status")
    if require_real and status != LIVE_VERIFIED:
        raise CorpusError(f"fixture row {index} must be {LIVE_VERIFIED}")
    if not str(row["path"]).startswith("/"):
        raise CorpusError(f"fixture row {index} path must start with /")
    if not str(row["method"]).isupper():
        raise CorpusError(f"fixture row {index} method must be uppercase")
