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
                    "statement": "No reachable vulnerable code path in the published image.",
                    "expired_at": "2099-01-01",
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
                        "statement": "reason",
                        "expired_at": "2099-01-01",
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
                        "statement": "   ",
                        "expired_at": "2099-01-01",
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
                        "statement": "reason",
                        "expired_at": "01-01-2099",
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
        "statement": "reason",
        "expired_at": "2099-01-01",
    }
    path = _write_policy(tmp_path, {"vulnerabilities": [entry, entry]})

    with pytest.raises(ValueError, match="duplicate"):
        validator.validate_exception_file(path, today=date(2026, 9, 1))


@pytest.mark.parametrize("expired_at", ["2026-09-01", "2026-08-31"])
def test_expired_or_today_exception_is_rejected(tmp_path: Path, expired_at: str) -> None:
    """An exception must remain valid beyond the current UTC date."""
    path = _write_policy(
        tmp_path,
        {
            "vulnerabilities": [
                {
                    "id": "CVE-2099-0001",
                    "statement": "reason",
                    "expired_at": expired_at,
                }
            ]
        },
    )

    with pytest.raises(ValueError, match="expired"):
        validator.validate_exception_file(path, today=date(2026, 9, 1))
