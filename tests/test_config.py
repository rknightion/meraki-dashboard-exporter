"""Tests for configuration management."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from meraki_dashboard_exporter.core.config import Settings


def test_settings_with_valid_api_key(monkeypatch):
    """Test settings with valid API key."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)

    settings = Settings()
    assert settings.meraki.api_key.get_secret_value() == "a" * 40
    assert settings.update_intervals.fast == 60  # fast_update_interval is the default
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
    monkeypatch.setenv("MERAKI_EXPORTER_UPDATE_INTERVALS__FAST", "60")
    monkeypatch.setenv("MERAKI_EXPORTER_UPDATE_INTERVALS__MEDIUM", "300")
    monkeypatch.setenv("MERAKI_EXPORTER_UPDATE_INTERVALS__SLOW", "900")
    monkeypatch.setenv("MERAKI_EXPORTER_LOGGING__LEVEL", "DEBUG")

    settings = Settings()
    assert settings.meraki.org_id == "123456"

    assert settings.update_intervals.fast == 60
    assert settings.update_intervals.medium == 300
    assert settings.update_intervals.slow == 900
    assert settings.logging.level == "DEBUG"
