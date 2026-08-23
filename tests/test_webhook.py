"""Tests for webhook receiver functionality (Phase 4.2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings, WebhookSettings


@pytest.fixture
def webhook_enabled_settings() -> Settings:
    """Create settings with webhooks enabled."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
        webhooks=WebhookSettings(
            enabled=True,
            shared_secret=SecretStr("test_secret"),
            require_secret=True,
        ),
    )


@pytest.fixture
def webhook_disabled_settings() -> Settings:
    """Create settings with webhooks disabled."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
        webhooks=WebhookSettings(
            enabled=False,
        ),
    )


@pytest.fixture
def valid_webhook_payload() -> dict:
    """Create a valid webhook payload for testing."""
    return {
        "version": "1.0",
        "sharedSecret": "test_secret",
        "sentAt": datetime.now(UTC).isoformat(),
        "organizationId": "123456",
        "organizationName": "Test Org",
        "organizationUrl": "https://dashboard.meraki.com/o/123456",
        "networkId": "N_123456",
        "networkName": "Test Network",
        "networkUrl": "https://dashboard.meraki.com/o/123456/n/N_123456",
        "deviceSerial": "Q2XX-XXXX-XXXX",
        "deviceMac": "00:11:22:33:44:55",
        "deviceName": "Test Device",
        "deviceUrl": "https://dashboard.meraki.com/o/123456/n/N_123456/manage/nodes/Q2XX-XXXX-XXXX",
        "alertId": "alert_001",
        "alertType": "settings_changed",
        "alertTypeId": "settings_changed",
        "alertLevel": "warning",
        "occurredAt": datetime.now(UTC).isoformat(),
        "alertData": {
            "setting": "ssid_enabled",
            "old_value": "false",
            "new_value": "true",
        },
    }


def test_webhook_endpoint_disabled(webhook_disabled_settings: Settings) -> None:
    """Test webhook endpoint returns 404 when disabled."""
    exporter = ExporterApp(webhook_disabled_settings)
    app = exporter.create_app()
    client = TestClient(app)

    response = client.post(
        "/api/webhooks/meraki",
        json={"test": "data"},
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 404
    assert "not enabled" in response.json()["detail"].lower()


def test_webhook_endpoint_invalid_content_type(
    webhook_enabled_settings: Settings, valid_webhook_payload: dict
) -> None:
    """Test webhook endpoint rejects invalid content type."""
    exporter = ExporterApp(webhook_enabled_settings)
    app = exporter.create_app()
    client = TestClient(app)

    response = client.post(
        "/api/webhooks/meraki",
        content="not json",
        headers={"Content-Type": "text/plain"},
    )

    assert response.status_code == 400
    assert "content-type" in response.json()["detail"].lower()


def test_webhook_endpoint_invalid_json(webhook_enabled_settings: Settings) -> None:
    """Test webhook endpoint rejects invalid JSON."""
    exporter = ExporterApp(webhook_enabled_settings)
    app = exporter.create_app()
    client = TestClient(app)

    response = client.post(
        "/api/webhooks/meraki",
        content="not valid json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert "invalid json" in response.json()["detail"].lower()


def test_webhook_endpoint_payload_too_large(
    webhook_enabled_settings: Settings, valid_webhook_payload: dict
) -> None:
    """Test webhook endpoint rejects payload that is too large."""
    # Set max payload size to 100 bytes
    webhook_enabled_settings.webhooks.max_payload_size = 100

    exporter = ExporterApp(webhook_enabled_settings)
    app = exporter.create_app()
    client = TestClient(app)

    # Create large payload
    large_payload = valid_webhook_payload.copy()
    large_payload["alertData"] = {"data": "x" * 10000}  # Make it large

    response = client.post(
        "/api/webhooks/meraki",
        json=large_payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


def test_webhook_endpoint_invalid_secret(
    webhook_enabled_settings: Settings, valid_webhook_payload: dict
) -> None:
    """Test webhook endpoint rejects invalid shared secret."""
    exporter = ExporterApp(webhook_enabled_settings)
    app = exporter.create_app()
    client = TestClient(app)

    # Use wrong shared secret
    payload = valid_webhook_payload.copy()
    payload["sharedSecret"] = "wrong_secret"

    response = client.post(
        "/api/webhooks/meraki",
        json=payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 401
    assert "validation failed" in response.json()["detail"].lower()


def test_webhook_endpoint_valid_payload(
    webhook_enabled_settings: Settings, valid_webhook_payload: dict
) -> None:
    """Test webhook endpoint processes valid payload successfully."""
    exporter = ExporterApp(webhook_enabled_settings)
    app = exporter.create_app()
    client = TestClient(app)

    response = client.post(
        "/api/webhooks/meraki",
        json=valid_webhook_payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert "processed" in response.json()["message"].lower()


def test_webhook_endpoint_duplicate_is_idempotent_success(
    webhook_enabled_settings: Settings, valid_webhook_payload: dict
) -> None:
    """An authenticated delivery retry is acknowledged without reprocessing."""
    exporter = ExporterApp(webhook_enabled_settings)
    client = TestClient(exporter.create_app())

    first = client.post("/api/webhooks/meraki", json=valid_webhook_payload)
    duplicate = client.post("/api/webhooks/meraki", json=valid_webhook_payload)

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"


def test_webhook_endpoint_stale_authenticated_delivery_is_acknowledged(
    webhook_enabled_settings: Settings, valid_webhook_payload: dict
) -> None:
    """A stale authenticated delivery cannot become fresh by being retried."""
    exporter = ExporterApp(webhook_enabled_settings)
    client = TestClient(exporter.create_app())
    payload = {**valid_webhook_payload, "sentAt": "2020-01-01T00:00:00+00:00"}

    response = client.post("/api/webhooks/meraki", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "stale"


def test_webhook_endpoint_processing_failure_is_retryable(
    webhook_enabled_settings: Settings, valid_webhook_payload: dict
) -> None:
    """A 5xx processing failure leaves the delivery eligible for a successful retry."""

    class FailOnceApplier:
        def __init__(self) -> None:
            self.calls = 0

        def apply_webhook_device_state(self, serial: str, up: bool) -> bool:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient state failure")
            return True

    exporter = ExporterApp(webhook_enabled_settings)
    assert exporter.webhook_handler is not None
    applier = FailOnceApplier()
    exporter.webhook_handler._device_state_applier = applier
    client = TestClient(exporter.create_app())
    payload = {**valid_webhook_payload, "alertType": "device_down"}

    failed = client.post("/api/webhooks/meraki", json=payload)
    retried = client.post("/api/webhooks/meraki", json=payload)
    duplicate = client.post("/api/webhooks/meraki", json=payload)

    assert failed.status_code == 500
    assert retried.status_code == 200
    assert retried.json()["status"] == "success"
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    assert applier.calls == 2


def test_webhook_enabled_without_secret_fails_fast(
    webhook_enabled_settings: Settings,
) -> None:
    """SEC-03 / #561: enabled + require_secret=false without opt-in refuses at startup.

    Previously this insecure combination silently accepted unauthenticated
    POSTs; it now raises ``WebhookSecurityError`` when the app is constructed,
    unless the operator explicitly opts in via ``webhooks.allow_insecure=true``.
    """
    from meraki_dashboard_exporter.core.webhook_handler import WebhookSecurityError

    # Disable secret validation without opting in.
    webhook_enabled_settings.webhooks.require_secret = False

    with pytest.raises(WebhookSecurityError):
        ExporterApp(webhook_enabled_settings)


def test_webhook_endpoint_missing_required_fields(
    webhook_enabled_settings: Settings,
) -> None:
    """Test webhook endpoint rejects payload with missing required fields."""
    exporter = ExporterApp(webhook_enabled_settings)
    app = exporter.create_app()
    client = TestClient(app)

    # Minimal payload missing required fields
    payload = {
        "version": "1.0",
        "sharedSecret": "test_secret",
        # Missing sentAt, organizationId, organizationName, organizationUrl
    }

    response = client.post(
        "/api/webhooks/meraki",
        json=payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    # Validation should fail due to missing required fields
