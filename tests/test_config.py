"""Tests for configuration management."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from meraki_dashboard_exporter.core import config as config_mod
from meraki_dashboard_exporter.core.config import Settings


def test_settings_with_valid_api_key(monkeypatch):
    """Test settings with valid API key."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)

    settings = Settings()
    assert settings.meraki.api_key.get_secret_value() == "a" * 40
    assert settings.server.host == "0.0.0.0"
    assert settings.server.port == 9099


def test_settings_with_invalid_api_key(monkeypatch):
    """Test settings with invalid API key."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "short")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert "Invalid API key format" in str(exc_info.value)


def test_settings_with_otel_enabled_without_endpoint(monkeypatch):
    """Test OTEL validation when enabled without endpoint."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_OTEL__ENABLED", "true")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert "OTEL endpoint must be provided" in str(exc_info.value)


def test_settings_with_custom_values(monkeypatch):
    """Test settings with custom values."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__ORG_ID", "123456")
    monkeypatch.setenv("MERAKI_EXPORTER_LOGGING__LEVEL", "DEBUG")

    settings = Settings()
    assert settings.meraki.org_id == "123456"
    assert settings.logging.level == "DEBUG"


def test_detiered_scheduler_and_collector_defaults(monkeypatch):
    """Post-#631 knobs replacing the removed update-interval/per-tier surface.

    The FAST/MEDIUM/SLOW per-tier update-interval model and per-tier concurrency
    limits are gone; the remaining cadence/concurrency knobs are the scheduler
    failure-retry backoff and the collector concurrency cap.
    """
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)

    settings = Settings()
    assert settings.scheduler.failure_retry_seconds == 300
    assert settings.collectors.max_concurrent_collectors == 5


def test_network_filter_env_parsing(monkeypatch):
    """Network filter env vars parse as comma-separated lists."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_NETWORK_FILTER__INCLUDE_NAMES", "prod-*,staging-*")
    monkeypatch.setenv("MERAKI_EXPORTER_NETWORK_FILTER__EXCLUDE_TAGS", "lab")

    settings = Settings()
    assert settings.network_filter.include_names == ["prod-*", "staging-*"]
    assert settings.network_filter.exclude_tags == ["lab"]
    assert settings.network_filter.is_active is True


def test_network_filter_inactive_by_default(monkeypatch):
    """When no filter env vars are set, the filter is inactive."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.delenv("MERAKI_EXPORTER_NETWORK_FILTER__INCLUDE_NAMES", raising=False)

    settings = Settings()
    assert settings.network_filter.is_active is False
    assert settings.network_filter.include_names == []


def test_collectors_csv_env_parsing(monkeypatch):
    """COLLECTORS enable/disable accept comma-separated env values (#514)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_COLLECTORS__ENABLED_COLLECTORS", "device,organization")
    monkeypatch.setenv("MERAKI_EXPORTER_COLLECTORS__DISABLE_COLLECTORS", "clients")

    settings = Settings()
    assert settings.collectors.enabled_collectors == {"device", "organization"}
    assert settings.collectors.disable_collectors == {"clients"}


def test_collectors_json_env_parsing(monkeypatch):
    """COLLECTORS enable list still accepts the JSON-array env form (#514)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv(
        "MERAKI_EXPORTER_COLLECTORS__ENABLED_COLLECTORS", '["device","organization"]'
    )

    settings = Settings()
    assert settings.collectors.enabled_collectors == {"device", "organization"}


def test_log_level_lowercase_env(monkeypatch):
    """Lowercase LOG level env value is normalised to upper (#598)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_LOGGING__LEVEL", "info")

    settings = Settings()
    assert settings.logging.level == "INFO"


def test_org_id_optional_at_settings_layer(monkeypatch):
    """org_id may be omitted entirely; Settings() builds with org_id=None (#585)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.delenv("MERAKI_EXPORTER_MERAKI__ORG_ID", raising=False)

    settings = Settings()
    assert settings.meraki.org_id is None


def test_new_config_field_defaults(monkeypatch):
    """New v1 config fields default sanely without any env (#586/#310/#558/#561)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)

    settings = Settings()
    assert settings.api.requests_proxy is None
    assert settings.api.certificate_path is None
    assert settings.logging.log_format == "json"
    assert settings.server.ui_enabled is True
    assert settings.webhooks.allow_insecure is False


def test_log_format_json_env(monkeypatch):
    """log_format env value is accepted and normalised to lower-case (#310)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_LOGGING__LOG_FORMAT", "JSON")

    settings = Settings()
    assert settings.logging.log_format == "json"


def test_api_key_loaded_from_file_secret(monkeypatch, tmp_path):
    """MERAKI_EXPORTER_MERAKI__API_KEY_FILE loads the key from a mounted file (#587)."""
    # chdir into a clean dir so the repo's local .env (a dotenv source that sits
    # above the file-secret source) doesn't supply an api_key and mask the file.
    monkeypatch.chdir(tmp_path)
    key_file = tmp_path / "meraki_api_key"
    key_file.write_text("a" * 40)
    monkeypatch.delenv("MERAKI_EXPORTER_MERAKI__API_KEY", raising=False)
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY_FILE", str(key_file))

    settings = Settings()
    assert settings.meraki.api_key.get_secret_value() == "a" * 40


def test_direct_env_wins_over_file_secret(monkeypatch, tmp_path):
    """A directly-set env var beats the *_FILE source (#587)."""
    key_file = tmp_path / "meraki_api_key"
    key_file.write_text("b" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY_FILE", str(key_file))

    settings = Settings()
    assert settings.meraki.api_key.get_secret_value() == "a" * 40


def test_unrecognized_env_var_warns(monkeypatch):
    """An unknown MERAKI_EXPORTER_* key warns once and does not crash (#515).

    structlog routes through its own pipeline so caplog does not capture these;
    spying on the config module's logger directly is reliable.
    """
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_FOO", "bar")

    captured: list[dict] = []

    def _fake_warning(message: str, **kwargs: object) -> None:
        captured.append({"message": message, **kwargs})

    monkeypatch.setattr(config_mod.logger, "warning", _fake_warning)

    settings = Settings()  # must not raise
    assert settings.meraki.api_key.get_secret_value() == "a" * 40

    assert captured, "expected a warning for the unrecognized env var"
    blob = repr(captured)
    assert "MERAKI_EXPORTER_FOO" in blob
    # The value must never be logged.
    assert "bar" not in blob


def test_shared_fraction_default_headroom(monkeypatch):
    """rate_limit_shared_fraction defaults to 0.8 through Settings (#550)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)

    settings = Settings()
    assert settings.api.rate_limit_shared_fraction == 0.8


def test_new_api_scale_field_defaults(monkeypatch):
    """New RETRY/deadline/executor API fields default sanely (#546/#550/RETRY seam)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)

    settings = Settings()
    assert settings.api.retry_after_max_seconds == 60
    assert settings.api.executor_workers == 10
    assert settings.api.per_fetch_deadline_seconds == 120


def test_cardinality_settings_defaults(monkeypatch):
    """CardinalitySettings mounts on Settings with the frozen defaults (SCALE-01)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)

    settings = Settings()
    assert settings.cardinality.max_series_per_family == 50000
    assert settings.cardinality.action == "warn"
    assert settings.cardinality.disabled_metrics == set()
    assert settings.cardinality.monitor_interval_seconds == 300
    assert settings.cardinality.monitor_max_label_values == 100


def test_cardinality_env_parsing(monkeypatch):
    """CARDINALITY__ env vars parse, incl. CSV disabled_metrics (SCALE-01)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_CARDINALITY__ACTION", "drop")
    monkeypatch.setenv("MERAKI_EXPORTER_CARDINALITY__MAX_SERIES_PER_FAMILY", "12345")
    monkeypatch.setenv("MERAKI_EXPORTER_CARDINALITY__DISABLED_METRICS", "meraki_foo,meraki_bar")

    settings = Settings()
    assert settings.cardinality.action == "drop"
    assert settings.cardinality.max_series_per_family == 12345
    assert settings.cardinality.disabled_metrics == {"meraki_foo", "meraki_bar"}


def test_scheduler_settings_defaults(monkeypatch):
    """SchedulerSettings mounts on Settings with the frozen §1d defaults (#617)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)

    settings = Settings()
    assert settings.scheduler.mode == "adaptive"
    assert settings.scheduler.target_utilization == 0.7
    assert settings.scheduler.max_stretch_factor == 4.0
    assert settings.scheduler.max_interval_seconds == 3600
    assert settings.scheduler.resolve_interval_seconds == 900
    assert settings.scheduler.aimd_enabled is True
    assert settings.scheduler.aimd_backoff_multiplier == 0.5
    assert settings.scheduler.aimd_recovery_rps_per_minute == 0.1
    assert settings.scheduler.aimd_resolve_hysteresis == 0.2
    assert settings.scheduler.group_interval_overrides == {}


def test_scheduler_env_parsing(monkeypatch):
    """SCHEDULER__ env vars parse, incl. JSON-object group_interval_overrides (#617)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_SCHEDULER__MODE", "fixed")
    monkeypatch.setenv("MERAKI_EXPORTER_SCHEDULER__TARGET_UTILIZATION", "0.5")
    monkeypatch.setenv(
        "MERAKI_EXPORTER_SCHEDULER__GROUP_INTERVAL_OVERRIDES",
        '{"nh_connection_stats": 900}',
    )

    settings = Settings()
    assert settings.scheduler.mode == "fixed"
    assert settings.scheduler.target_utilization == 0.5
    assert settings.scheduler.group_interval_overrides == {"nh_connection_stats": 900}


def test_china_base_url_bumps_low_timeout(monkeypatch):
    """api.meraki.cn base URL bumps a sub-45s timeout to 45 (#518)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_BASE_URL", "https://api.meraki.cn/api/v1")
    monkeypatch.setenv("MERAKI_EXPORTER_API__TIMEOUT", "30")

    settings = Settings()
    assert settings.api.timeout == 45


def test_default_region_does_not_bump_timeout(monkeypatch):
    """The default region leaves a low timeout untouched (#518)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_API__TIMEOUT", "30")

    settings = Settings()
    assert settings.api.timeout == 30
