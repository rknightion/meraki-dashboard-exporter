"""Tests for configuration management."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from meraki_dashboard_exporter.core.config import Settings


def test_settings_with_valid_api_key(monkeypatch):
    """Test settings with valid API key."""
    monkeypatch.setenv("MERAKI_API_KEY", "a" * 40)
    
    settings = Settings()
    assert settings.api_key.get_secret_value() == "a" * 40
    assert settings.scrape_interval == 300
    assert settings.host == "0.0.0.0"
    assert settings.port == 9090


def test_settings_with_invalid_api_key(monkeypatch):
    """Test settings with invalid API key."""
    monkeypatch.setenv("MERAKI_API_KEY", "short")
    
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    
    assert "Invalid API key format" in str(exc_info.value)


def test_settings_with_otel_enabled_without_endpoint(monkeypatch):
    """Test OTEL validation when enabled without endpoint."""
    monkeypatch.setenv("MERAKI_API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_OTEL_ENABLED", "true")
    
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    
    assert "OTEL endpoint must be provided" in str(exc_info.value)


def test_settings_with_custom_values(monkeypatch):
    """Test settings with custom values."""
    monkeypatch.setenv("MERAKI_API_KEY", "a" * 40)
    monkeypatch.setenv("MERAKI_EXPORTER_ORG_ID", "123456")
    monkeypatch.setenv("MERAKI_EXPORTER_SCRAPE_INTERVAL", "600")
    monkeypatch.setenv("MERAKI_EXPORTER_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MERAKI_EXPORTER_DEVICE_TYPES", '["MS", "MR"]')
    
    settings = Settings()
    assert settings.org_id == "123456"
    assert settings.scrape_interval == 600
    assert settings.log_level == "DEBUG"
    assert settings.device_types == ["MS", "MR"]