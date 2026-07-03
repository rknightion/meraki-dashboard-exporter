"""Unit tests for WebhookHandler class (P5.1.2 - Phase 4.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from prometheus_client import REGISTRY
from pydantic import SecretStr

import meraki_dashboard_exporter.core.webhook_handler as webhook_handler_module
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

        # Metric labels are bounded (SEC-03 / #561): the payload org "org_123"
        # is not the configured org ("123456") so it buckets to "other"; the
        # known alert_type "settings_changed" passes through.
        received_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_received_total",
            {"org_id": "other", "alert_type": "settings_changed"},
        )
        assert received_metric is not None
        assert received_metric > 0

        processed_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_processed_total",
            {"org_id": "other", "alert_type": "settings_changed"},
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

        # Check that failed event was tracked (bounded error_type label only;
        # no attacker-controlled org_id/alert_type labels - see F-051)
        failed_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_failed_total",
            {"error_type": "validation_error"},
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

        # Should track with bounded labels: unknown org -> "other", missing
        # alert_type -> "unknown".
        metric_value = REGISTRY.get_sample_value(
            "meraki_webhook_events_received_total",
            {"org_id": "other", "alert_type": "unknown"},
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
            org_id="other",
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

        # Check that failed event was tracked (bounded error_type label only)
        failed_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_failed_total",
            {"error_type": "validation_error"},
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

    def test_known_org_and_unknown_org_bounded(
        self, webhook_handler: WebhookHandler, valid_payload: dict
    ) -> None:
        """A configured org keeps its id; an unknown org buckets to 'other' (#561).

        The handler is configured for org "123456", so a webhook from that org
        keeps ``org_id="123456"`` while an unknown org id buckets to ``other``
        (bounded cardinality) rather than minting a new label value.
        """
        # First webhook from the configured org.
        payload1 = valid_payload.copy()
        payload1["organizationId"] = "123456"
        webhook_handler.process_webhook(payload1)

        # Second webhook from an unknown org.
        payload2 = valid_payload.copy()
        payload2["organizationId"] = "org_456"
        webhook_handler.process_webhook(payload2)

        known_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_received_total",
            {"org_id": "123456", "alert_type": "settings_changed"},
        )
        other_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_received_total",
            {"org_id": "other", "alert_type": "settings_changed"},
        )

        assert known_metric == 1
        assert other_metric == 1
        # The attacker-supplied org id never becomes a label value.
        assert (
            REGISTRY.get_sample_value(
                "meraki_webhook_events_received_total",
                {"org_id": "org_456", "alert_type": "settings_changed"},
            )
            is None
        )

    def test_different_alert_types_tracked(
        self, webhook_handler: WebhookHandler, valid_payload: dict
    ) -> None:
        """Test that distinct known alert types are tracked separately."""
        # First: a known alert type.
        webhook_handler.process_webhook(valid_payload)

        # Second: a different known alert type.
        payload2 = valid_payload.copy()
        payload2["alertType"] = "motion_detected"
        webhook_handler.process_webhook(payload2)

        # Both known alert types are tracked (org buckets to "other").
        settings_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_received_total",
            {"org_id": "other", "alert_type": "settings_changed"},
        )
        motion_metric = REGISTRY.get_sample_value(
            "meraki_webhook_events_received_total",
            {"org_id": "other", "alert_type": "motion_detected"},
        )

        assert settings_metric is not None
        assert motion_metric is not None
        assert settings_metric > 0
        assert motion_metric > 0


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


class TestWebhookHandlerSecurity:
    """Security regression tests (F-109 timing, F-051 cardinality, F-166 secret leak)."""

    def test_validate_secret_uses_constant_time_compare(
        self, webhook_handler: WebhookHandler, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F-109: secret comparison must use hmac.compare_digest (constant-time)."""
        real_compare = webhook_handler_module.hmac.compare_digest
        calls: list[tuple] = []

        def spy(a: object, b: object) -> bool:
            calls.append((a, b))
            return real_compare(a, b)

        monkeypatch.setattr(webhook_handler_module.hmac, "compare_digest", spy)

        assert webhook_handler.validate_secret("test_secret_123") is True
        assert calls, "hmac.compare_digest was not used for secret validation"

    def test_validate_secret_constant_time_rejects_wrong_secret(
        self, webhook_handler: WebhookHandler, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F-109: constant-time compare still rejects an incorrect secret."""
        real_compare = webhook_handler_module.hmac.compare_digest
        calls: list[tuple] = []

        def spy(a: object, b: object) -> bool:
            calls.append((a, b))
            return real_compare(a, b)

        monkeypatch.setattr(webhook_handler_module.hmac, "compare_digest", spy)

        assert webhook_handler.validate_secret("wrong_secret") is False
        assert calls, "hmac.compare_digest was not used for secret validation"

    def test_failure_path_no_unbounded_label_series(self, webhook_handler: WebhookHandler) -> None:
        """F-051: many distinct malformed payloads must not create unbounded label series."""
        for i in range(50):
            webhook_handler.process_webhook({
                "version": "1.0",
                "organizationId": f"attacker_org_{i}",
                "alertType": f"attacker_alert_{i}",
                # Missing required fields -> ValidationError on the failure path.
            })

        series: set[tuple] = set()
        leaked: set[str] = set()
        for metric_family in REGISTRY.collect():
            for sample in metric_family.samples:
                if sample.name == "meraki_webhook_events_failed_total":
                    series.add(tuple(sorted(sample.labels.items())))
                    for value in sample.labels.values():
                        if "attacker" in value:
                            leaked.add(value)

        assert not leaked, f"attacker-controlled values leaked into label series: {leaked}"
        # A single bounded series (error_type=validation_error) regardless of 50 payloads.
        assert len(series) == 1, f"unbounded cardinality on failure path: {series}"

    def test_validation_failure_does_not_log_secret(
        self, webhook_handler: WebhookHandler, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F-166: a validation failure must not emit the sharedSecret value in logs."""
        fake_logger = MagicMock()
        monkeypatch.setattr(webhook_handler_module, "logger", fake_logger)

        secret = "SUPER_SECRET_SENTINEL_VALUE_9f3a"  # pragma: allowlist secret
        webhook_handler.process_webhook({
            "version": "1.0",
            "sharedSecret": secret,
            # Missing required fields -> ValidationError; pydantic embeds the raw
            # input (including sharedSecret) in errors()[i]["input"].
        })

        logged = " ".join(
            repr(call)
            for call in (
                *fake_logger.error.call_args_list,
                *fake_logger.exception.call_args_list,
                *fake_logger.warning.call_args_list,
                *fake_logger.info.call_args_list,
            )
        )
        assert secret not in logged, "sharedSecret value leaked into logs on validation failure"


class _StubApplier:
    """Records apply_webhook_device_state calls; returns a fixed verdict (#614)."""

    def __init__(self, verdict: bool) -> None:
        self._verdict = verdict
        self.calls: list[tuple[str, bool]] = []

    def apply_webhook_device_state(self, serial: str, up: bool) -> bool:
        self.calls.append((serial, up))
        return self._verdict


def _device_down_payload() -> dict:
    """A valid device_down webhook payload with a device serial."""
    return {
        "version": "1.0",
        "sharedSecret": "test_secret_123",
        "sentAt": datetime.now(UTC).isoformat(),
        "organizationId": "123456",
        "organizationName": "Test Organization",
        "organizationUrl": "https://dashboard.meraki.com/o/ABC123/manage/organization/overview",
        "networkId": "N_123",
        "networkName": "Test Network",
        "deviceSerial": "Q2XX-XXXX-XXXX",
        "deviceName": "Test Device",
        "alertType": "device_down",
        "alertData": {},
    }


class TestWebhookDeviceStateFastPath:
    """#614: process_webhook drives the device-state applier for down alerts."""

    def test_device_down_flips_and_counts_applied(self, settings_with_secret: Settings) -> None:
        """Test 1 (end-to-end): device_down for a known serial -> flip + applied."""
        applier = _StubApplier(verdict=True)
        handler = WebhookHandler(settings_with_secret, device_state_applier=applier)

        result = handler.process_webhook(_device_down_payload())

        assert result is not None
        # Applier invoked with the payload serial and up=False (DOWN in v1).
        assert applier.calls == [("Q2XX-XXXX-XXXX", False)]

        counter = REGISTRY.get_sample_value(
            "meraki_webhook_device_state_transitions_total",
            {"direction": "down", "result": "applied"},
        )
        assert counter == 1

    def test_unknown_serial_counts_unknown_serial(self, settings_with_secret: Settings) -> None:
        """Test 4: unknown serial still counts (result=unknown_serial) + events."""
        applier = _StubApplier(verdict=False)  # serial not poll-known
        handler = WebhookHandler(settings_with_secret, device_state_applier=applier)

        handler.process_webhook(_device_down_payload())

        assert applier.calls == [("Q2XX-XXXX-XXXX", False)]
        assert (
            REGISTRY.get_sample_value(
                "meraki_webhook_device_state_transitions_total",
                {"direction": "down", "result": "unknown_serial"},
            )
            == 1
        )
        # The event is still received + processed by the existing counters.
        assert (
            REGISTRY.get_sample_value(
                "meraki_webhook_events_received_total",
                {"org_id": "123456", "alert_type": "device_down"},
            )
            == 1
        )
        assert (
            REGISTRY.get_sample_value(
                "meraki_webhook_events_processed_total",
                {"org_id": "123456", "alert_type": "device_down"},
            )
            == 1
        )

    @pytest.mark.parametrize("alert_type", ["port_down", "cellular_down", "uplink_status_change"])
    def test_non_device_alert_types_do_not_flip(
        self, settings_with_secret: Settings, alert_type: str
    ) -> None:
        """Test 5: per-port/uplink/cellular-uplink alerts never flip device_up."""
        applier = _StubApplier(verdict=True)
        handler = WebhookHandler(settings_with_secret, device_state_applier=applier)

        payload = _device_down_payload()
        payload["alertType"] = alert_type
        handler.process_webhook(payload)

        assert applier.calls == []
        # No transition counter series were created at all.
        for result in ("applied", "unknown_serial"):
            for direction in ("down", "up"):
                assert (
                    REGISTRY.get_sample_value(
                        "meraki_webhook_device_state_transitions_total",
                        {"direction": direction, "result": result},
                    )
                    is None
                )

    def test_no_applier_configured_is_count_only(self, settings_with_secret: Settings) -> None:
        """Test 6: with no applier (device collector disabled) behave as today."""
        handler = WebhookHandler(settings_with_secret, device_state_applier=None)

        result = handler.process_webhook(_device_down_payload())

        assert result is not None
        # Event still counted; no transition counter incremented, no exception.
        assert (
            REGISTRY.get_sample_value(
                "meraki_webhook_events_processed_total",
                {"org_id": "123456", "alert_type": "device_down"},
            )
            == 1
        )
        for result_label in ("applied", "unknown_serial"):
            assert (
                REGISTRY.get_sample_value(
                    "meraki_webhook_device_state_transitions_total",
                    {"direction": "down", "result": result_label},
                )
                is None
            )
