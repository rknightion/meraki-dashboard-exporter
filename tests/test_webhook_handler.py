"""Unit tests for WebhookHandler class (P5.1.2 - Phase 4.2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from prometheus_client import REGISTRY
from pydantic import SecretStr

from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings, WebhookSettings
from meraki_dashboard_exporter.core.webhook_handler import WebhookHandler


@pytest.fixture
def settings_with_secret() -> Settings:
    """Create settings with secret validation enabled."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
        webhooks=WebhookSettings(
            enabled=True,
            shared_secret=SecretStr("test_secret_123"),
            require_secret=True,
        ),
    )


@pytest.fixture
def settings_without_secret() -> Settings:
    """Create settings with secret validation disabled."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
        webhooks=WebhookSettings(
            enabled=True,
            require_secret=False,
        ),
    )


@pytest.fixture
def settings_secret_not_configured() -> Settings:
    """Create settings requiring secret but not configured."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
        webhooks=WebhookSettings(
            enabled=True,
            require_secret=True,
            shared_secret=None,
        ),
    )


@pytest.fixture
def webhook_handler(settings_with_secret: Settings) -> WebhookHandler:
    """Create a webhook handler instance."""
    return WebhookHandler(settings_with_secret)


@pytest.fixture
def valid_payload() -> dict:
    """Create a valid webhook payload."""
    return {
        "version": "1.0",
        "sharedSecret": "test_secret_123",
        "sentAt": datetime.now(UTC).isoformat(),
        "organizationId": "org_123",
        "organizationName": "Test Organization",
        "organizationUrl": "https://dashboard.meraki.com/o/ABC123/manage/organization/overview",
        "networkId": "N_123",
        "networkName": "Test Network",
        "deviceSerial": "Q2XX-XXXX-XXXX",
        "deviceName": "Test Device",
        "alertType": "settings_changed",
        "alertData": {
            "change_type": "configuration",
        },
    }


class TestWebhookHandlerSecretValidation:
    """Test secret validation functionality."""

    def test_validate_secret_success(self, webhook_handler: WebhookHandler) -> None:
        """Test successful secret validation."""
        result = webhook_handler.validate_secret("test_secret_123")
        assert result is True

    def test_validate_secret_mismatch(self, webhook_handler: WebhookHandler) -> None:
        """Test secret validation with mismatched secret."""
        result = webhook_handler.validate_secret("wrong_secret")
        assert result is False

        # Check that validation failure metric was incremented
        metric_value = REGISTRY.get_sample_value(
            "meraki_webhook_validation_failures_total",
            {"validation_error": "secret_mismatch"},
        )
        assert metric_value is not None
        assert metric_value > 0

    def test_validate_secret_none(self, webhook_handler: WebhookHandler) -> None:
        """Test secret validation with None."""
        result = webhook_handler.validate_secret(None)
        assert result is False

    def test_validate_secret_not_required(self, settings_without_secret: Settings) -> None:
        """Test secret validation when not required."""
        handler = WebhookHandler(settings_without_secret)
        result = handler.validate_secret(None)
        assert result is True

    def test_validate_secret_required_but_not_configured(
        self, settings_secret_not_configured: Settings
    ) -> None:
        """Test secret validation when required but not configured."""
        handler = WebhookHandler(settings_secret_not_configured)
        result = handler.validate_secret("any_secret")
        assert result is False

        # Check that validation failure metric was incremented
        metric_value = REGISTRY.get_sample_value(
            "meraki_webhook_validation_failures_total",
            {"validation_error": "secret_not_configured"},
        )
        assert metric_value is not None
        assert metric_value > 0


class TestWebhookHandlerProcessing:
    """Test webhook processing functionality."""

    def test_process_valid_webhook(
        self, webhook_handler: WebhookHandler, valid_payload: dict
    ) -> None:
        """Test processing a valid webhook payload."""
        result = webhook_handler.process_webhook(valid_payload)

        assert result is not None
        assert result.version == "1.0"
        assert result.organization_id == "org_123"
        assert result.alert_type == "settings_changed"
        assert result.device_serial == "Q2XX-XXXX-XXXX"

        # Check that events were tracked
        received_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_received_total",
            {"org_id": "org_123", "alert_type": "settings_changed"},
        )
        assert received_metric is not None
        assert received_metric > 0

        processed_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_processed_total",
            {"org_id": "org_123", "alert_type": "settings_changed"},
        )
        assert processed_metric is not None
        assert processed_metric > 0

    def test_process_webhook_invalid_secret(
        self, webhook_handler: WebhookHandler, valid_payload: dict
    ) -> None:
        """Test processing webhook with invalid secret."""
        valid_payload["sharedSecret"] = "wrong_secret"
        result = webhook_handler.process_webhook(valid_payload)

        assert result is None

    def test_process_webhook_missing_required_fields(self, webhook_handler: WebhookHandler) -> None:
        """Test processing webhook with missing required fields."""
        invalid_payload = {
            "version": "1.0",
            "sharedSecret": "test_secret_123",
            # Missing sentAt, organizationId, etc.
        }

        result = webhook_handler.process_webhook(invalid_payload)
        assert result is None

        # Check that validation failure was tracked
        validation_metric = REGISTRY.get_sample_value(
            "meraki_webhook_validation_failures_total",
            {"validation_error": "invalid_payload"},
        )
        assert validation_metric is not None
        assert validation_metric > 0

        # Check that failed event was tracked
        failed_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_failed_total",
            {
                "org_id": "unknown",
                "alert_type": "unknown",
                "error_type": "validation_error",
            },
        )
        assert failed_metric is not None
        assert failed_metric > 0

    def test_process_webhook_with_partial_data(self, webhook_handler: WebhookHandler) -> None:
        """Test processing webhook with minimal required fields."""
        payload = {
            "version": "1.0",
            "sharedSecret": "test_secret_123",
            "sentAt": datetime.now(UTC).isoformat(),
            "organizationId": "org_123",
            "organizationName": "Test Organization",
            "organizationUrl": "https://dashboard.meraki.com/o/ABC123/manage/organization/overview",
        }

        result = webhook_handler.process_webhook(payload)

        # Should succeed even without optional fields
        assert result is not None
        assert result.organization_id == "org_123"
        assert result.alert_type is None
        assert result.network_id is None
        assert result.device_serial is None

        # Should track with "unknown" alert type
        metric_value = REGISTRY.get_sample_value(
            "meraki_webhook_events_received_total",
            {"org_id": "org_123", "alert_type": "unknown"},
        )
        assert metric_value is not None
        assert metric_value > 0

    def test_process_webhook_tracks_duration(
        self, webhook_handler: WebhookHandler, valid_payload: dict
    ) -> None:
        """Test that processing duration is tracked."""
        webhook_handler.process_webhook(valid_payload)

        # Check that processing duration histogram has samples
        # Note: We can't easily check the actual value, but we can check it exists
        histogram = webhook_handler.processing_duration.labels(
            org_id="org_123",
            alert_type="settings_changed",
        )
        # The histogram should have been observed at least once
        assert histogram._sum._value > 0  # noqa: SLF001

    def test_process_webhook_exception_handling(self, webhook_handler: WebhookHandler) -> None:
        """Test exception handling during webhook processing."""
        # Create a payload that will cause an exception (invalid datetime)
        invalid_payload = {
            "version": "1.0",
            "sharedSecret": "test_secret_123",
            "sentAt": "not-a-valid-datetime",
            "organizationId": "org_123",
            "organizationName": "Test Organization",
        }

        result = webhook_handler.process_webhook(invalid_payload)
        assert result is None

        # Check that failed event was tracked
        failed_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_failed_total",
            {
                "org_id": "org_123",
                "alert_type": "unknown",
                "error_type": "validation_error",
            },
        )
        assert failed_metric is not None
        assert failed_metric > 0


class TestWebhookHandlerMetrics:
    """Test metrics tracking."""

    def test_metrics_initialized(self, webhook_handler: WebhookHandler) -> None:
        """Test that all metrics are properly initialized."""
        assert webhook_handler.events_received is not None
        assert webhook_handler.events_processed is not None
        assert webhook_handler.events_failed is not None
        assert webhook_handler.processing_duration is not None
        assert webhook_handler.validation_failures is not None

    def test_multiple_webhooks_tracked_separately(
        self, webhook_handler: WebhookHandler, valid_payload: dict
    ) -> None:
        """Test that webhooks from different orgs are tracked separately."""
        # Process first webhook
        webhook_handler.process_webhook(valid_payload)

        # Process second webhook with different org
        payload2 = valid_payload.copy()
        payload2["organizationId"] = "org_456"
        webhook_handler.process_webhook(payload2)

        # Check that both orgs were tracked
        org1_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_received_total",
            {"org_id": "org_123", "alert_type": "settings_changed"},
        )
        org2_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_received_total",
            {"org_id": "org_456", "alert_type": "settings_changed"},
        )

        assert org1_metric is not None
        assert org2_metric is not None
        assert org1_metric > 0
        assert org2_metric > 0

    def test_different_alert_types_tracked(
        self, webhook_handler: WebhookHandler, valid_payload: dict
    ) -> None:
        """Test that different alert types are tracked separately."""
        # Process first alert type
        webhook_handler.process_webhook(valid_payload)

        # Process second alert type
        payload2 = valid_payload.copy()
        payload2["alertType"] = "offline_device"
        webhook_handler.process_webhook(payload2)

        # Check that both alert types were tracked
        settings_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_received_total",
            {"org_id": "org_123", "alert_type": "settings_changed"},
        )
        offline_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_received_total",
            {"org_id": "org_123", "alert_type": "offline_device"},
        )

        assert settings_metric is not None
        assert offline_metric is not None
        assert settings_metric > 0
        assert offline_metric > 0


class TestWebhookHandlerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_payload(self, webhook_handler: WebhookHandler) -> None:
        """Test processing an empty payload."""
        result = webhook_handler.process_webhook({})
        assert result is None

    def test_payload_with_extra_fields(
        self, webhook_handler: WebhookHandler, valid_payload: dict
    ) -> None:
        """Test that extra fields in payload are handled gracefully."""
        valid_payload["unknownField"] = "some_value"
        valid_payload["anotherExtraField"] = 12345

        result = webhook_handler.process_webhook(valid_payload)

        # Should succeed and ignore extra fields
        assert result is not None
        assert result.organization_id == "org_123"

    def test_payload_with_null_optional_fields(self, webhook_handler: WebhookHandler) -> None:
        """Test payload with explicit null values for optional fields."""
        payload = {
            "version": "1.0",
            "sharedSecret": "test_secret_123",
            "sentAt": datetime.now(UTC).isoformat(),
            "organizationId": "org_123",
            "organizationName": "Test Organization",
            "organizationUrl": "https://dashboard.meraki.com/o/ABC123/manage/organization/overview",
            "networkId": None,
            "networkName": None,
            "deviceSerial": None,
            "deviceName": None,
            "alertType": None,
            # alertData omitted - will use default empty dict
        }

        result = webhook_handler.process_webhook(payload)
        assert result is not None
        assert result.organization_id == "org_123"
        assert result.network_id is None
        assert result.device_serial is None
        assert result.alert_type is None
        assert result.alert_data == {}  # Should use default empty dict

    def test_very_long_organization_name(
        self, webhook_handler: WebhookHandler, valid_payload: dict
    ) -> None:
        """Test handling of very long organization names."""
        valid_payload["organizationName"] = "A" * 1000

        result = webhook_handler.process_webhook(valid_payload)
        assert result is not None
        assert len(result.organization_name) == 1000

    def test_special_characters_in_alert_type(
        self, webhook_handler: WebhookHandler, valid_payload: dict
    ) -> None:
        """Test handling of special characters in alert types."""
        valid_payload["alertType"] = "test/alert-type_with.special:chars"

        result = webhook_handler.process_webhook(valid_payload)
        assert result is not None
        assert result.alert_type == "test/alert-type_with.special:chars"
