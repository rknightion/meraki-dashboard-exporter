"""Tests for webhook success-path label bounding + insecure-combo fail-fast.

Covers SEC-03 / #561 (bound org_id/alert_type, refuse require_secret=false
without opt-in) and the in-memory receiver health used by /status (#317).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings, WebhookSettings
from meraki_dashboard_exporter.core.webhook_handler import (
    ALERT_TYPE_OTHER,
    ALERT_TYPE_UNKNOWN,
    WebhookHandler,
    WebhookSecurityError,
    bound_alert_type,
    bound_org_id,
    enforce_webhook_security,
)


class TestBoundAlertType:
    """Bounding of the attacker-controlled alert_type label."""

    def test_known_alert_type_passes_through(self) -> None:
        """Known alert type passes through."""
        assert bound_alert_type("motion_detected") == "motion_detected"

    def test_unknown_alert_type_buckets_to_other(self) -> None:
        """Unknown alert type buckets to other."""
        assert bound_alert_type("'; DROP TABLE metrics; --") == ALERT_TYPE_OTHER
        assert bound_alert_type("novel-attacker-value") == ALERT_TYPE_OTHER

    def test_missing_alert_type_is_unknown(self) -> None:
        """Missing alert type is unknown."""
        assert bound_alert_type(None) == ALERT_TYPE_UNKNOWN
        assert bound_alert_type("") == ALERT_TYPE_UNKNOWN


class TestBoundOrgId:
    """Bounding of the attacker-controlled org_id label."""

    def test_known_org_passes_through(self) -> None:
        """Known org passes through."""
        assert bound_org_id("123456", {"123456"}) == "123456"

    def test_unknown_org_buckets_to_other(self) -> None:
        """Unknown org buckets to other."""
        assert bound_org_id("evilorg", {"123456"}) == ALERT_TYPE_OTHER

    def test_none_org_buckets_to_other(self) -> None:
        """None org buckets to other."""
        assert bound_org_id(None, {"123456"}) == ALERT_TYPE_OTHER

    def test_empty_known_set_buckets_everything(self) -> None:
        """Empty known set buckets everything."""
        assert bound_org_id("123456", set()) == ALERT_TYPE_OTHER


class TestEnforceWebhookSecurity:
    """Fail-fast on the insecure require_secret=false combination."""

    def test_insecure_combo_without_optin_raises(self) -> None:
        """Insecure combo without optin raises."""
        with pytest.raises(WebhookSecurityError):
            enforce_webhook_security(enabled=True, require_secret=False, allow_insecure=False)

    def test_insecure_combo_with_optin_allowed(self) -> None:
        """Insecure combo with optin allowed."""
        # Explicit opt-in does not raise.
        enforce_webhook_security(enabled=True, require_secret=False, allow_insecure=True)

    def test_secure_combo_allowed(self) -> None:
        """Secure combo allowed."""
        enforce_webhook_security(enabled=True, require_secret=True, allow_insecure=False)

    def test_disabled_receiver_allowed(self) -> None:
        """Disabled receiver allowed."""
        enforce_webhook_security(enabled=False, require_secret=False, allow_insecure=False)


def _insecure_settings() -> Settings:
    """Settings with require_secret=false so the success path is reachable."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
        webhooks=WebhookSettings(enabled=True, require_secret=False),
    )


def _payload(*, org_id: str, alert_type: str | None) -> dict:
    payload = {
        "version": "1.0",
        "sentAt": datetime.now(UTC).isoformat(),
        "organizationId": org_id,
        "organizationName": "Attacker Org",
        "organizationUrl": "https://dashboard.meraki.com/o/x",
    }
    if alert_type is not None:
        payload["alertType"] = alert_type
    return payload


class TestSuccessPathLabelBounding:
    """An attacker payload cannot inject a novel org_id/alert_type label."""

    def test_attacker_labels_are_bounded(self) -> None:
        """Attacker labels are bounded."""
        handler = WebhookHandler(_insecure_settings())

        result = handler.process_webhook(
            _payload(org_id="evilorg-<script>", alert_type="evil-injection-<x>")
        )
        assert result is not None

        # In-memory status reflects the bounded values only.
        status = handler.get_status()
        assert status["events_received"] == 1
        assert status["events_processed"] == 1
        assert status["last_alert_type"] == ALERT_TYPE_OTHER
        assert status["events_by_type"] == {ALERT_TYPE_OTHER: 1}
        assert status["last_event_time"] is not None

        # The emitted metric carries no attacker-derived label values.
        samples = list(handler.events_received.collect())[0].samples
        org_values = {s.labels["org_id"] for s in samples}
        alert_values = {s.labels["alert_type"] for s in samples}
        assert "evilorg-<script>" not in org_values
        assert "evil-injection-<x>" not in alert_values
        assert org_values == {ALERT_TYPE_OTHER}
        assert alert_values == {ALERT_TYPE_OTHER}

    def test_known_org_and_alert_type_preserved(self) -> None:
        """Known org and alert type preserved."""
        handler = WebhookHandler(_insecure_settings())

        result = handler.process_webhook(_payload(org_id="123456", alert_type="motion_detected"))
        assert result is not None

        status = handler.get_status()
        assert status["last_alert_type"] == "motion_detected"
        samples = list(handler.events_received.collect())[0].samples
        assert {s.labels["org_id"] for s in samples} == {"123456"}
        assert {s.labels["alert_type"] for s in samples} == {"motion_detected"}


class TestReceiverHealthTracking:
    """Validation failures and events are tracked in-memory for /status (#317)."""

    def test_record_validation_failure_increments(self) -> None:
        """Record validation failure increments."""
        handler = WebhookHandler(_insecure_settings())
        handler.record_validation_failure("invalid_json")
        handler.record_validation_failure("payload_too_large")
        assert handler.get_status()["validation_failures"] == 2

    def test_failed_processing_counted(self) -> None:
        """Failed processing counted."""
        handler = WebhookHandler(_insecure_settings())
        # Missing required fields -> ValidationError -> failure path.
        handler.process_webhook({"version": "1.0"})
        status = handler.get_status()
        assert status["events_failed"] == 1
        assert status["events_received"] == 0
