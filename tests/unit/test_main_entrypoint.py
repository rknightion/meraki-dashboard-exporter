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

    def test_help_text_uses_correct_env_var_names(self, capsys: pytest.CaptureFixture) -> None:
        """--help must reference the *real* nested env var names.

        Settings uses env_prefix="MERAKI_EXPORTER_" + env_nested_delimiter="__", so the
        real vars are e.g. MERAKI_EXPORTER_MERAKI__API_KEY, not MERAKI_API_KEY / the
        un-nested MERAKI_EXPORTER_ORG_ID etc that used to be printed.
        """
        with patch("sys.argv", ["meraki-dashboard-exporter", "--help"]):
            with pytest.raises(SystemExit):
                main()
        output = capsys.readouterr().out
        assert "MERAKI_EXPORTER_MERAKI__API_KEY" in output
        assert "MERAKI_EXPORTER_MERAKI__ORG_ID" in output
        assert "MERAKI_EXPORTER_SERVER__HOST" in output
        assert "MERAKI_EXPORTER_SERVER__PORT" in output
        assert "MERAKI_EXPORTER_LOGGING__LEVEL" in output
        # The old, wrong (un-nested) var names must not remain.
        assert "MERAKI_API_KEY " not in output
        assert "MERAKI_EXPORTER_ORG_ID " not in output
        assert "MERAKI_EXPORTER_HOST " not in output
        assert "MERAKI_EXPORTER_PORT " not in output
        assert "MERAKI_EXPORTER_LOG_LEVEL " not in output


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

    def test_missing_api_key_shows_friendly_message_and_correct_env_var(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """The dead-code guided message must actually trigger and name the real env var.

        Real pydantic loc for a wholly-missing nested `meraki` model is ("meraki",) —
        NOT ("api_key",) as the old (dead) check assumed.
        """
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
        err = capsys.readouterr().err
        assert "Meraki API key is required" in err
        assert "MERAKI_EXPORTER_MERAKI__API_KEY" in err
        assert "MERAKI_API_KEY'" not in err
        assert "export MERAKI_API_KEY" not in err

    def test_missing_api_key_nested_loc_shows_friendly_message(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """The real nested loc ("meraki", "api_key") must also trigger the friendly message."""
        with (
            patch("sys.argv", ["meraki-dashboard-exporter"]),
            patch.dict("os.environ", {}, clear=True),
            patch(
                "meraki_dashboard_exporter.__main__.Settings",
                side_effect=_build_validation_error_with_loc(("meraki", "api_key"), "missing"),
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "Meraki API key is required" in err
        assert "MERAKI_EXPORTER_MERAKI__API_KEY" in err

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

    def test_other_validation_error_does_not_use_friendly_message(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """A validation error unrelated to `meraki` must fall through to the generic path."""
        with (
            patch("sys.argv", ["meraki-dashboard-exporter"]),
            patch.dict("os.environ", {}, clear=True),
            patch(
                "meraki_dashboard_exporter.__main__.Settings",
                side_effect=_make_other_validation_error(),
            ),
        ):
            with pytest.raises(SystemExit):
                main()
        err = capsys.readouterr().err
        assert "Meraki API key is required" not in err
        assert "Configuration Error" in err


def _make_api_key_validation_error() -> Exception:
    """Create a ValidationError that looks like a wholly-missing nested `meraki` model.

    This is the real shape pydantic-settings produces when no MERAKI_EXPORTER_MERAKI__*
    env vars are set at all: loc == ("meraki",), type == "missing" (verified against a
    live `Settings()` call with a cleaned environment).
    """
    return _build_validation_error_with_loc(("meraki",), "missing")


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
