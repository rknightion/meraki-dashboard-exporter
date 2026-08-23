"""Regression coverage for webhook freshness and replay protection (#715)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from prometheus_client import REGISTRY
from pydantic import SecretStr

from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings, WebhookSettings
from meraki_dashboard_exporter.core.webhook_handler import WebhookHandler, WebhookOutcome


class _RecordingApplier:
    """Record device-state applications made by the handler."""

    def __init__(self) -> None:
        """Initialize an empty application history."""
        self.calls: list[tuple[str, bool]] = []

    def apply_webhook_device_state(self, serial: str, up: bool) -> bool:
        """Record a device-state application and report a known serial."""
        self.calls.append((serial, up))
        return True


def _settings(*, replay_cache_max_entries: int = 10000) -> Settings:
    """Return a webhook-enabled configuration with replay protection enabled."""
    return Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
        webhooks=WebhookSettings(
            enabled=True,
            shared_secret=SecretStr("test_secret_123"),
            require_secret=True,
            replay_cache_max_entries=replay_cache_max_entries,
        ),
    )


def _device_down_payload() -> dict[str, object]:
    """Return a fresh, authenticated device-down alert with an alert ID."""
    return {
        "version": "1.0",
        "sharedSecret": "test_secret_123",
        "sentAt": datetime.now(UTC).isoformat(),
        "organizationId": "123456",
        "organizationName": "Test Organization",
        "organizationUrl": "https://dashboard.meraki.com/o/ABC123/manage/organization/overview",
        "deviceSerial": "Q2XX-XXXX-XXXX",
        "alertId": "alert-715",
        "alertType": "device_down",
        "alertData": {},
    }


def test_replayed_alert_records_two_deliveries_but_applies_device_state_once() -> None:
    """A Meraki delivery retry remains observable without repeating the state transition."""
    applier = _RecordingApplier()
    handler = WebhookHandler(_settings(), device_state_applier=applier)
    payload = _device_down_payload()

    assert handler.process_webhook(payload).outcome is WebhookOutcome.ACCEPTED
    assert handler.process_webhook(payload).outcome is WebhookOutcome.DUPLICATE
    assert applier.calls == [("Q2XX-XXXX-XXXX", False)]
    assert (
        REGISTRY.get_sample_value(
            "meraki_webhook_delivery_attempts_total",
            {"org_id": "123456", "alert_type": "device_down"},
        )
        == 2
    )
    assert (
        REGISTRY.get_sample_value(
            "meraki_webhook_unique_alerts_total",
            {"org_id": "123456", "alert_type": "device_down"},
        )
        == 1
    )
    assert (
        REGISTRY.get_sample_value(
            "meraki_webhook_replays_rejected_total",
            {"org_id": "123456", "alert_type": "device_down"},
        )
        == 1
    )


@pytest.mark.parametrize("offset", [-1, 1])
def test_out_of_window_alert_is_rejected_before_applying_device_state(offset: int) -> None:
    """An authenticated alert beyond either end of the skew window cannot flip state."""
    applier = _RecordingApplier()
    handler = WebhookHandler(_settings(), device_state_applier=applier)
    payload = _device_down_payload()
    payload["sentAt"] = datetime.fromtimestamp(
        datetime.now(UTC).timestamp()
        + offset * (handler.settings.webhooks.freshness_window_seconds + 1),
        UTC,
    ).isoformat()

    assert handler.process_webhook(payload).outcome is WebhookOutcome.STALE
    assert applier.calls == []
    assert (
        REGISTRY.get_sample_value(
            "meraki_webhook_delivery_attempts_total",
            {"org_id": "123456", "alert_type": "device_down"},
        )
        == 1
    )
    assert (
        REGISTRY.get_sample_value(
            "meraki_webhook_stale_rejected_total",
            {"org_id": "123456", "alert_type": "device_down"},
        )
        == 1
    )


def test_alert_without_id_is_deduplicated_by_body_fingerprint() -> None:
    """Payload identity falls back to a canonical body fingerprint when alertId is absent."""
    applier = _RecordingApplier()
    handler = WebhookHandler(_settings(), device_state_applier=applier)
    payload = _device_down_payload()
    payload.pop("alertId")

    assert handler.process_webhook(payload).outcome is WebhookOutcome.ACCEPTED
    assert handler.process_webhook(payload).outcome is WebhookOutcome.DUPLICATE
    assert applier.calls == [("Q2XX-XXXX-XXXX", False)]


def test_replay_cache_entry_expires_after_its_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """A later, non-replayed delivery is accepted after the configured TTL."""
    applier = _RecordingApplier()
    handler = WebhookHandler(_settings(), device_state_applier=applier)
    payload = _device_down_payload()
    monotonic_time = 100.0

    monkeypatch.setattr(
        "meraki_dashboard_exporter.core.webhook_handler.time.monotonic",
        lambda: monotonic_time,
    )
    assert handler.process_webhook(payload).outcome is WebhookOutcome.ACCEPTED
    assert handler.process_webhook(payload).outcome is WebhookOutcome.DUPLICATE

    monotonic_time += handler.settings.webhooks.replay_cache_ttl_seconds + 1
    assert handler.process_webhook(payload).outcome is WebhookOutcome.ACCEPTED
    assert applier.calls == [
        ("Q2XX-XXXX-XXXX", False),
        ("Q2XX-XXXX-XXXX", False),
    ]


def test_replay_cache_evicts_the_oldest_alert_at_its_entry_limit() -> None:
    """The configured cache entry cap bounds retained alert identities."""
    applier = _RecordingApplier()
    handler = WebhookHandler(_settings(replay_cache_max_entries=100), device_state_applier=applier)
    oldest_payload = _device_down_payload()

    assert handler.process_webhook(oldest_payload) is not None
    for number in range(1, 101):
        payload = _device_down_payload()
        payload["alertId"] = f"alert-715-{number}"
        assert handler.process_webhook(payload) is not None

    # The 101st distinct alert evicted the oldest cache entry, so its later
    # delivery is no longer treated as a replay.
    assert handler.process_webhook(oldest_payload) is not None
    assert len(applier.calls) == 102
