"""Tests for __main__.py entry point to increase coverage."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from meraki_dashboard_exporter.__main__ import main


class TestMainHelp:
    """Tests for the --help flag."""

    def test_help_flag_prints_usage_and_exits(self) -> None:
        """Test that --help prints usage text and exits with 0."""
        with patch("sys.argv", ["meraki-dashboard-exporter", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_short_help_flag(self) -> None:
        """Test that -h prints usage text and exits with 0."""
        with patch("sys.argv", ["meraki-dashboard-exporter", "-h"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestMainValidationError:
    """Tests for configuration validation error handling."""

    def test_missing_api_key_shows_error(self) -> None:
        """Test that missing API key produces a helpful error message."""
        with (
            patch("sys.argv", ["meraki-dashboard-exporter"]),
            patch.dict("os.environ", {}, clear=True),
            patch(
                "meraki_dashboard_exporter.__main__.Settings",
                side_effect=_make_api_key_validation_error(),
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_other_validation_error_shows_details(self) -> None:
        """Test that non-API-key validation errors are displayed."""
        with (
            patch("sys.argv", ["meraki-dashboard-exporter"]),
            patch.dict("os.environ", {}, clear=True),
            patch(
                "meraki_dashboard_exporter.__main__.Settings",
                side_effect=_make_other_validation_error(),
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


def _make_api_key_validation_error() -> Exception:
    """Create a ValidationError that looks like a missing API key."""
    from pydantic import ValidationError

    from meraki_dashboard_exporter.core.config import Settings

    try:
        Settings.model_validate({"meraki": {"api_key": None, "org_id": "123"}})
    except ValidationError:
        # Rebuild with the specific error format the code checks for
        return _build_validation_error_with_loc(("api_key",), "missing")
    return RuntimeError("Should not reach here")


def _make_other_validation_error() -> Exception:
    """Create a ValidationError for a non-API-key field."""
    return _build_validation_error_with_loc(("server", "port"), "value_error")


def _build_validation_error_with_loc(loc: tuple[str, ...], error_type: str) -> Exception:
    """Build a pydantic-like ValidationError with a specific loc and type."""
    from pydantic import ValidationError
    from pydantic_core import InitErrorDetails, PydanticCustomError

    error = PydanticCustomError(error_type, f"Validation error at {loc}")
    details: list[InitErrorDetails] = [
        {"type": error, "loc": loc, "input": None},
    ]
    return ValidationError.from_exception_data(title="Settings", line_errors=details)
