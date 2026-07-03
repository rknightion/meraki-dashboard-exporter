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


_FAKE_API_KEY = "test_api_key_at_least_30_characters_long"  # pragma: allowlist secret


def _valid_settings() -> object:
    """Build a valid Settings instance for --check tests (no env dependency)."""
    from pydantic import SecretStr

    from meraki_dashboard_exporter.core.config import Settings
    from meraki_dashboard_exporter.core.config_models import MerakiSettings

    return Settings(
        meraki=MerakiSettings(api_key=SecretStr(_FAKE_API_KEY), org_id="123456"),
    )


class TestCheckMode:
    """Tests for the --check config-validation / dry-run mode (issue #588)."""

    def test_help_mentions_check_flag(self, capsys: pytest.CaptureFixture) -> None:
        """--help must advertise the --check flag so operators can find it."""
        with patch("sys.argv", ["meraki-dashboard-exporter", "--help"]):
            with pytest.raises(SystemExit):
                main()
        out = capsys.readouterr().out
        assert "--check" in out

    def test_check_valid_config_exits_zero(self) -> None:
        """--check with valid config exits 0 and does not start the server."""
        with (
            patch("sys.argv", ["meraki-dashboard-exporter", "--check"]),
            patch(
                "meraki_dashboard_exporter.__main__.Settings",
                return_value=_valid_settings(),
            ),
            patch("meraki_dashboard_exporter.__main__.uvicorn.run") as mock_run,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0
        mock_run.assert_not_called()

    def test_check_prints_redacted_summary_and_hides_key(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """--check prints a redacted summary that never contains the API key."""
        with (
            patch("sys.argv", ["meraki-dashboard-exporter", "--check"]),
            patch(
                "meraki_dashboard_exporter.__main__.Settings",
                return_value=_valid_settings(),
            ),
            patch("meraki_dashboard_exporter.__main__.uvicorn.run"),
        ):
            with pytest.raises(SystemExit):
                main()
        out = capsys.readouterr().out
        assert "***REDACTED***" in out
        # The real key value must never be printed.
        assert _FAKE_API_KEY not in out
        # A clear validity verdict is shown.
        assert "VALID" in out

    def test_check_invalid_config_exits_nonzero(self) -> None:
        """--check with invalid config exits non-zero (validation failure)."""
        with (
            patch("sys.argv", ["meraki-dashboard-exporter", "--check"]),
            patch(
                "meraki_dashboard_exporter.__main__.Settings",
                side_effect=_make_other_validation_error(),
            ),
            patch("meraki_dashboard_exporter.__main__.uvicorn.run") as mock_run,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1
        mock_run.assert_not_called()

    def test_check_offline_does_not_probe(self) -> None:
        """Default --check performs no live auth probe (offline-safe for CI)."""
        with (
            patch("sys.argv", ["meraki-dashboard-exporter", "--check"]),
            patch(
                "meraki_dashboard_exporter.__main__.Settings",
                return_value=_valid_settings(),
            ),
            patch("meraki_dashboard_exporter.__main__.uvicorn.run"),
            patch("meraki_dashboard_exporter.__main__._run_auth_probe") as mock_probe,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0
        mock_probe.assert_not_called()

    def test_check_probe_success_exits_zero(self) -> None:
        """--check --probe runs the auth probe; success exits 0."""
        with (
            patch("sys.argv", ["meraki-dashboard-exporter", "--check", "--probe"]),
            patch(
                "meraki_dashboard_exporter.__main__.Settings",
                return_value=_valid_settings(),
            ),
            patch("meraki_dashboard_exporter.__main__.uvicorn.run"),
            patch(
                "meraki_dashboard_exporter.__main__._run_auth_probe",
                return_value=True,
            ) as mock_probe,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0
        mock_probe.assert_called_once()

    def test_check_probe_failure_exits_nonzero(self) -> None:
        """--check --probe with a failing auth probe exits non-zero."""
        with (
            patch("sys.argv", ["meraki-dashboard-exporter", "--check", "--probe"]),
            patch(
                "meraki_dashboard_exporter.__main__.Settings",
                return_value=_valid_settings(),
            ),
            patch("meraki_dashboard_exporter.__main__.uvicorn.run"),
            patch(
                "meraki_dashboard_exporter.__main__._run_auth_probe",
                return_value=False,
            ) as mock_probe,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1
        mock_probe.assert_called_once()


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
