"""Contract tests for reviewed Trivy vulnerability exceptions."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_trivy_exceptions as validator  # noqa: E402


def _write_policy(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / ".trivyignore.yaml"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_empty_exception_policy_is_valid(tmp_path: Path) -> None:
    """An empty reviewed-exception list is a valid strict policy."""
    path = _write_policy(tmp_path, {"vulnerabilities": []})

    validator.validate_exception_file(path, today=date(2026, 9, 1))


def test_future_reviewed_exception_is_valid(tmp_path: Path) -> None:
    """A complete reviewed exception with a future expiry is valid."""
    path = _write_policy(
        tmp_path,
        {
            "vulnerabilities": [
                {
                    "id": "CVE-2099-0001",
                    "purls": ["pkg:deb/debian/example*"],
                    "statement": "No reachable vulnerable code path in the published image.",
                    "expired_at": "2099-01-01T00:00:00Z",
                }
            ]
        },
    )

    validator.validate_exception_file(path, today=date(2026, 9, 1))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "top level"),
        ({"vulnerabilities": {}, "extra": []}, "top level"),
        ({"vulnerabilities": [{}]}, "fields"),
        (
            {
                "vulnerabilities": [
                    {
                        "id": "CVE-2099-0001",
                        "purls": ["pkg:deb/debian/example*"],
                        "statement": "reason",
                        "expired_at": "2099-01-01T00:00:00Z",
                        "extra": "no",
                    }
                ]
            },
            "fields",
        ),
        (
            {
                "vulnerabilities": [
                    {
                        "id": "CVE-2099-0001",
                        "purls": ["pkg:deb/debian/example*"],
                        "statement": "   ",
                        "expired_at": "2099-01-01T00:00:00Z",
                    }
                ]
            },
            "statement",
        ),
        (
            {
                "vulnerabilities": [
                    {
                        "id": "CVE-2099-0001",
                        "purls": ["pkg:deb/debian/example*"],
                        "statement": "reason",
                        "expired_at": "01-01-2099T00:00:00Z",
                    }
                ]
            },
            "expired_at",
        ),
    ],
)
def test_malformed_exception_policy_is_rejected(
    tmp_path: Path, payload: object, message: str
) -> None:
    """Malformed structures and entries fail closed with a useful reason."""
    path = _write_policy(tmp_path, payload)

    with pytest.raises(ValueError, match=message):
        validator.validate_exception_file(path, today=date(2026, 9, 1))


def test_malformed_json_is_rejected(tmp_path: Path) -> None:
    """Invalid JSON cannot silently weaken the exception policy."""
    path = tmp_path / ".trivyignore.yaml"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="valid JSON"):
        validator.validate_exception_file(path, today=date(2026, 9, 1))


def test_duplicate_identifier_is_rejected(tmp_path: Path) -> None:
    """One vulnerability identifier cannot carry competing reviews."""
    entry = {
        "id": "CVE-2099-0001",
        "purls": ["pkg:deb/debian/example*"],
        "statement": "reason",
        "expired_at": "2099-01-01T00:00:00Z",
    }
    path = _write_policy(tmp_path, {"vulnerabilities": [entry, entry]})

    with pytest.raises(ValueError, match="duplicate"):
        validator.validate_exception_file(path, today=date(2026, 9, 1))


@pytest.mark.parametrize("expired_at", ["2026-09-01T00:00:00Z", "2026-08-31T00:00:00Z"])
def test_expired_or_today_exception_is_rejected(tmp_path: Path, expired_at: str) -> None:
    """An exception must remain valid beyond the current UTC date."""
    path = _write_policy(
        tmp_path,
        {
            "vulnerabilities": [
                {
                    "id": "CVE-2099-0001",
                    "purls": ["pkg:deb/debian/example*"],
                    "statement": "reason",
                    "expired_at": expired_at,
                }
            ]
        },
    )

    with pytest.raises(ValueError, match="expired"):
        validator.validate_exception_file(path, today=date(2026, 9, 1))


def test_rfc3339_expiry_is_required(tmp_path: Path) -> None:
    """Trivy parses ``expired_at`` from a JSON-shaped ignore file as RFC3339 only.

    A bare ``YYYY-MM-DD`` makes Trivy abort the whole scan with
    ``parsing time "..." as "2006-01-02T15:04:05Z07:00"``, which fails the publication
    gate for a reason unrelated to any finding. The validator must therefore reject the
    date-only form rather than certify a file the scanner cannot read.
    """
    path = _write_policy(
        tmp_path,
        {
            "vulnerabilities": [
                {
                    "id": "CVE-2099-0001",
                    "purls": ["pkg:deb/debian/example*"],
                    "statement": "reason",
                    "expired_at": "2099-01-01",
                }
            ]
        },
    )

    with pytest.raises(ValueError, match="expired_at"):
        validator.validate_exception_file(path, today=date(2026, 9, 1))


def test_committed_policy_matches_the_scanner_contract() -> None:
    """The repository's own committed exception file must satisfy the validator."""
    committed = Path(__file__).resolve().parents[2] / ".trivyignore.yaml"

    validator.validate_exception_file(committed)


def test_exception_without_purls_is_rejected(tmp_path: Path) -> None:
    """An identifier-only suppression silently covers every package that ever carries it.

    Trivy matches ``id`` alone across the whole image, so an accepted base-image CVE would
    also suppress the same identifier if it later appeared in a first-party dependency.
    Every exception must name the packages it was reviewed against.
    """
    path = _write_policy(
        tmp_path,
        {
            "vulnerabilities": [
                {
                    "id": "CVE-2099-0001",
                    "statement": "reason",
                    "expired_at": "2099-01-01T00:00:00Z",
                }
            ]
        },
    )

    with pytest.raises(ValueError, match="purls"):
        validator.validate_exception_file(path, today=date(2026, 9, 1))


def test_empty_purls_list_is_rejected(tmp_path: Path) -> None:
    """An empty package list is the identifier-only suppression wearing a field name."""
    path = _write_policy(
        tmp_path,
        {
            "vulnerabilities": [
                {
                    "id": "CVE-2099-0001",
                    "purls": [],
                    "statement": "reason",
                    "expired_at": "2099-01-01T00:00:00Z",
                }
            ]
        },
    )

    with pytest.raises(ValueError, match="purls"):
        validator.validate_exception_file(path, today=date(2026, 9, 1))
