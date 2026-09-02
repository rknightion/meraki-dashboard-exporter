#!/usr/bin/env python3
"""Validate reviewed, expiring Trivy vulnerability exceptions."""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import NoReturn

REQUIRED_FIELDS = {"id", "purls", "statement", "expired_at"}

# Trivy reads this file with a Go RFC3339 time parser, so a bare YYYY-MM-DD aborts the
# entire scan before any finding is evaluated. Certifying a file the scanner cannot read
# would fail the publication gate for a reason unrelated to security, so the exact
# RFC3339 UTC form is the contract.
EXPIRY_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
EXPIRY_HINT = "RFC3339 UTC, e.g. 2026-12-01T00:00:00Z"


def _fail(message: str) -> NoReturn:
    raise ValueError(message)


def validate_exception_file(path: Path, *, today: date | None = None) -> None:
    """Validate the strict JSON-compatible YAML exception policy at ``path``."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"{path} must contain valid JSON-compatible YAML: {exc}")

    if not isinstance(payload, dict) or set(payload) != {"vulnerabilities"}:
        _fail("exception policy top level must contain only 'vulnerabilities'")

    vulnerabilities = payload["vulnerabilities"]
    if not isinstance(vulnerabilities, list):
        _fail("'vulnerabilities' must be a list")

    current_date = today or datetime.now(UTC).date()
    identifiers: set[str] = set()
    for index, entry in enumerate(vulnerabilities):
        if not isinstance(entry, dict) or set(entry) != REQUIRED_FIELDS:
            _fail(f"vulnerability #{index + 1} fields must be exactly {sorted(REQUIRED_FIELDS)}")

        identifier = entry["id"]
        purls = entry["purls"]
        statement = entry["statement"]
        expired_at = entry["expired_at"]
        if not isinstance(identifier, str) or not identifier.strip():
            _fail(f"vulnerability #{index + 1} id must be a non-empty string")
        # Trivy matches a bare ``id`` across the whole image, so an accepted base-image CVE
        # would also suppress the same identifier in a first-party dependency. Binding each
        # exception to the packages it was reviewed against keeps the gate meaningful.
        if not isinstance(purls, list) or not purls:
            _fail(f"vulnerability {identifier!r} purls must be a non-empty list")
        if any(not isinstance(purl, str) or not purl.strip() for purl in purls):
            _fail(f"vulnerability {identifier!r} purls entries must be non-empty strings")
        if not isinstance(statement, str) or not statement.strip():
            _fail(f"vulnerability {identifier!r} statement must be a non-empty string")
        if not isinstance(expired_at, str):
            _fail(f"vulnerability {identifier!r} expired_at must be {EXPIRY_HINT}")

        try:
            moment = datetime.strptime(expired_at, EXPIRY_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            _fail(f"vulnerability {identifier!r} expired_at must be {EXPIRY_HINT}")
        expiry = moment.date()
        if expiry <= current_date:
            _fail(f"vulnerability {identifier!r} exception expired on {expired_at}")
        if identifier in identifiers:
            _fail(f"duplicate vulnerability identifier: {identifier}")
        identifiers.add(identifier)


def main() -> None:
    """Validate the repository's committed Trivy exception file."""
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".trivyignore.yaml")
    try:
        validate_exception_file(path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
