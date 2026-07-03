"""Tests for core.config_logger to increase coverage."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.core import config_logger as config_logger_mod
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_logger import (
    get_env_vars,
    log_startup_summary,
    mask_sensitive_value,
)
from meraki_dashboard_exporter.core.config_models import MerakiSettings


@pytest.fixture
def test_settings() -> Settings:
    """Create minimal settings for config logger testing."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )


class TestMaskSensitiveValue:
    """Tests for mask_sensitive_value."""

    def test_masks_api_key(self) -> None:
        """Test that api_key values are redacted."""
        assert mask_sensitive_value("api_key", "secret123") == "***REDACTED***"

    def test_masks_password(self) -> None:
        """Test that password values are redacted."""
        assert mask_sensitive_value("db_password", "p@ss") == "***REDACTED***"

    def test_masks_token(self) -> None:
        """Test that token values are redacted."""
        assert mask_sensitive_value("auth_token", "tok") == "***REDACTED***"

    def test_masks_secret(self) -> None:
        """Test that secret values are redacted."""
        assert mask_sensitive_value("webhook_secret", "s") == "***REDACTED***"

    def test_masks_credential(self) -> None:
        """Test that credential values are redacted."""
        assert mask_sensitive_value("my_credential", "c") == "***REDACTED***"

    def test_does_not_mask_normal_key(self) -> None:
        """Test that known-safe keys are not masked."""
        assert mask_sensitive_value("host", "localhost") == "localhost"

    def test_case_insensitive(self) -> None:
        """Test that masking is case-insensitive."""
        assert mask_sensitive_value("API_KEY", "val") == "***REDACTED***"

    def test_redacts_unknown_field_by_default(self) -> None:
        """SEC-07: an unlisted field is redacted by default (allowlist model).

        The old substring heuristic only redacted keys matching known secret
        substrings, so any new secret-bearing field whose name didn't match was
        logged in the clear. Inverted model: redact unless the key is known-safe.
        """
        # A novel, secret-shaped field that matches NO old heuristic substring:
        # under the old code this leaked; now it is redacted with no extra wiring.
        assert mask_sensitive_value("MERAKI_EXPORTER_VAULT__UNSEAL", "hunter2") == "***REDACTED***"
        # A plausibly-secret field the old substring list also missed.
        assert mask_sensitive_value("service_passphrase", "correct-horse") == "***REDACTED***"
        # A completely arbitrary unknown key is redacted by default.
        assert mask_sensitive_value("totally_unknown_key_name", "x") == "***REDACTED***"

    def test_known_safe_env_var_still_visible(self) -> None:
        """Known-safe config knobs remain visible for startup diagnostics."""
        assert mask_sensitive_value("MERAKI_EXPORTER_SERVER__PORT", "9099") == "9099"
        assert mask_sensitive_value("MERAKI_EXPORTER_API__TIMEOUT", "30") == "30"


class TestGetEnvVars:
    """Tests for get_env_vars."""

    def test_returns_dict(self) -> None:
        """Test that get_env_vars returns a dictionary."""
        result = get_env_vars()
        assert isinstance(result, dict)

    @patch.dict(os.environ, {"MERAKI_EXPORTER_FOO": "bar"}, clear=False)
    def test_captures_meraki_exporter_vars(self) -> None:
        """MERAKI_EXPORTER_ prefixed vars are captured but redacted by default (SEC-07).

        Under the redact-by-default (allowlist) model, an unrecognised env var
        like MERAKI_EXPORTER_FOO is captured but its value is masked rather than
        logged in the clear.
        """
        result = get_env_vars()
        assert "MERAKI_EXPORTER_FOO" in result
        assert result["MERAKI_EXPORTER_FOO"] == "***REDACTED***"

    @patch.dict(os.environ, {"MERAKI_EXPORTER_SERVER__HOST": "0.0.0.0"}, clear=False)
    def test_captures_known_safe_var_in_clear(self) -> None:
        """A known-safe env var is captured and shown in the clear."""
        result = get_env_vars()
        assert result["MERAKI_EXPORTER_SERVER__HOST"] == "0.0.0.0"

    def test_bare_api_key_env_not_emitted(self) -> None:
        """Bare MERAKI_API_KEY is never emitted, even redacted (#529).

        It is never consumed as a config source (only
        MERAKI_EXPORTER_MERAKI__API_KEY is read by Settings), so the startup env
        dump must not emit it at all.
        """
        fake_key = "my-fake-test-value"  # pragma: allowlist secret
        with patch.dict(os.environ, {"MERAKI_API_KEY": fake_key}, clear=False):
            result = get_env_vars()
        assert "MERAKI_API_KEY" not in result

    @patch.dict(os.environ, {"UNRELATED_VAR": "val"}, clear=False)
    def test_ignores_unrelated_vars(self) -> None:
        """Test that non-MERAKI vars are not included."""
        result = get_env_vars()
        assert "UNRELATED_VAR" not in result


class TestTruncateList:
    """Tests for the _truncate_list helper."""

    def test_short_list_not_truncated(self) -> None:
        """Test that a short list is returned as-is."""
        truncate = config_logger_mod._truncate_list  # noqa: SLF001
        values, truncated = truncate(["a", "b", "c"], max_items=5)
        assert values == ["a", "b", "c"]
        assert truncated is False

    def test_exact_length_not_truncated(self) -> None:
        """Test that a list at exactly max_items is not truncated."""
        truncate = config_logger_mod._truncate_list  # noqa: SLF001
        values, truncated = truncate(["a", "b", "c"], max_items=3)
        assert values == ["a", "b", "c"]
        assert truncated is False

    def test_long_list_truncated(self) -> None:
        """Test that a list over max_items is truncated."""
        truncate = config_logger_mod._truncate_list  # noqa: SLF001
        values, truncated = truncate(["a", "b", "c", "d", "e"], max_items=3)
        assert values == ["a", "b", "c"]
        assert truncated is True


class TestDeadCodeRemoved:
    """Guards for CFG-12 cleanup (issue #599)."""

    def test_log_configuration_removed(self) -> None:
        """The dead `log_configuration()` stub must no longer exist."""
        assert not hasattr(config_logger_mod, "log_configuration")


class TestLogStartupSummary:
    """Tests for log_startup_summary."""

    def test_basic_summary(self, test_settings: Settings) -> None:
        """Test startup summary with minimal args."""
        log_startup_summary(test_settings)

    def test_with_discovery_summary(self, test_settings: Settings) -> None:
        """Test startup summary with discovery data."""
        discovery = {
            "organizations": [
                {"name": "Test Org", "id": "123456"},
            ],
            "networks": {
                "123456": {
                    "count": 5,
                    "org_name": "Test Org",
                    "product_types": {"wireless": 3, "switch": 2},
                },
            },
            "errors": [],
        }
        log_startup_summary(test_settings, discovery_summary=discovery)

    def test_with_scheduling(self, test_settings: Settings) -> None:
        """Test startup summary with scheduling diagnostics (per-collector cadences)."""
        scheduling = {
            "collectors": [
                {
                    "collector": "DeviceCollector",
                    "cadence_seconds": 300.0,
                    "phase_offset_seconds": 12.0,
                },
                {
                    "collector": "MTSensorCollector",
                    "cadence_seconds": 60.0,
                    "phase_offset_seconds": 3.0,
                },
            ],
            "scheduler": {
                "mode": "adaptive",
                "groups": [
                    {
                        "name": "nh_connection_stats",
                        "interval_seconds": 1800.0,
                        "stretch_factor": 2.0,
                    },
                ],
            },
        }
        log_startup_summary(test_settings, scheduling=scheduling)

    def test_with_discovery_errors(self, test_settings: Settings) -> None:
        """Test startup summary with discovery errors."""
        discovery = {
            "organizations": [],
            "errors": ["discovery_failed"],
        }
        log_startup_summary(test_settings, discovery_summary=discovery)

    def test_without_org_id(self, test_settings: Settings) -> None:
        """Test startup summary with no org_id set."""
        test_settings.meraki.org_id = ""
        log_startup_summary(test_settings)

    def test_with_otel_enabled(self, test_settings: Settings) -> None:
        """Test startup summary with OTEL enabled."""
        test_settings.otel.enabled = True
        test_settings.otel.endpoint = "http://localhost:4317"
        test_settings.otel.service_name = "meraki-exporter"
        log_startup_summary(test_settings)

    def test_summary_not_double_logged(self, test_settings: Settings) -> None:
        """The summary is emitted once, via the unfiltered startup logger (#599).

        Before the CFG-12 cleanup the whole configuration was logged a second
        time through the module `logger` (the `logger.info(...)` "Feature Status"
        block). That duplicate is removed, so the module logger must not be used
        by the startup summary at all.
        """
        with patch.object(config_logger_mod.logger, "info") as mock_info:
            log_startup_summary(test_settings)
        assert mock_info.call_count == 0

    def _enabled_collectors(self, test_settings: Settings) -> list[str]:
        """Capture the enabled-collectors list from the startup summary (F-005).

        The summary is emitted via the unfiltered startup logger, so patch its
        factory and read the structured `  Enabled Collectors` event.
        """
        mock_logger = MagicMock()
        with patch.object(config_logger_mod, "_get_unfiltered_logger", return_value=mock_logger):
            log_startup_summary(test_settings)
        for call in mock_logger.warning.call_args_list:
            if call.args and call.args[0] == "  Enabled Collectors":
                return list(call.kwargs.get("collectors", []))
        raise AssertionError("'  Enabled Collectors' line was not emitted")

    def test_networkhealth_and_mtsensor_reported_enabled_by_default(
        self, test_settings: Settings
    ) -> None:
        """Network Health and MT Sensors must show as enabled by default (F-005)."""
        collectors = self._enabled_collectors(test_settings)

        assert "networkhealth" in collectors
        assert "mtsensor" in collectors

    def test_disabled_collector_is_reflected(self, test_settings: Settings) -> None:
        """Disabling a collector via disable_collectors is reflected in the summary (F-005)."""
        test_settings.collectors.disable_collectors = {"networkhealth"}

        collectors = self._enabled_collectors(test_settings)

        assert "networkhealth" not in collectors
