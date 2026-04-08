"""Unit tests for WebhookMetricsCollector (Phase 4.5)."""

from __future__ import annotations

import time

import pytest
from prometheus_client import REGISTRY

from meraki_dashboard_exporter.collectors.webhook_metrics import WebhookMetricsCollector


@pytest.fixture
def collector() -> WebhookMetricsCollector:
    """Create a fresh WebhookMetricsCollector for each test."""
    return WebhookMetricsCollector()


class TestRecordEvent:
    """Tests for WebhookMetricsCollector.record_event()."""

    def test_record_event_increments_counter(self, collector: WebhookMetricsCollector) -> None:
        """Calling record_event increments the events_total counter."""
        collector.record_event(
            event_type="meraki_webhook",
            network_id="N_123",
            alert_type="settings_changed",
        )

        value = REGISTRY.get_sample_value(
            "meraki_webhook_events_total",
            {
                "event_type": "meraki_webhook",
                "network_id": "N_123",
                "alert_type": "settings_changed",
            },
        )
        assert value == 1.0

    def test_record_event_multiple_calls_accumulate(
        self, collector: WebhookMetricsCollector
    ) -> None:
        """Multiple calls with the same labels accumulate in the counter."""
        for _ in range(3):
            collector.record_event(
                event_type="meraki_webhook",
                network_id="N_123",
                alert_type="offline_device",
            )

        value = REGISTRY.get_sample_value(
            "meraki_webhook_events_total",
            {
                "event_type": "meraki_webhook",
                "network_id": "N_123",
                "alert_type": "offline_device",
            },
        )
        assert value == 3.0

    def test_record_event_sets_timestamp(self, collector: WebhookMetricsCollector) -> None:
        """record_event sets the last_event_timestamp gauge."""
        before = time.time()
        collector.record_event(event_type="meraki_webhook")
        after = time.time()

        value = REGISTRY.get_sample_value(
            "meraki_webhook_last_event_timestamp",
            {"event_type": "meraki_webhook"},
        )
        assert value is not None
        assert before <= value <= after

    def test_record_event_timestamp_updates_on_repeat(
        self, collector: WebhookMetricsCollector
    ) -> None:
        """The timestamp gauge reflects the most recent event."""
        collector.record_event(event_type="meraki_webhook")
        first_ts = REGISTRY.get_sample_value(
            "meraki_webhook_last_event_timestamp",
            {"event_type": "meraki_webhook"},
        )

        # A brief pause ensures the second timestamp is at least equal.
        collector.record_event(event_type="meraki_webhook")
        second_ts = REGISTRY.get_sample_value(
            "meraki_webhook_last_event_timestamp",
            {"event_type": "meraki_webhook"},
        )

        assert second_ts is not None
        assert first_ts is not None
        assert second_ts >= first_ts

    def test_record_event_default_labels(self, collector: WebhookMetricsCollector) -> None:
        """record_event works with only event_type (defaults for optional args)."""
        collector.record_event(event_type="meraki_webhook")

        value = REGISTRY.get_sample_value(
            "meraki_webhook_events_total",
            {"event_type": "meraki_webhook", "network_id": "", "alert_type": ""},
        )
        assert value == 1.0

    def test_record_event_different_labels_tracked_separately(
        self, collector: WebhookMetricsCollector
    ) -> None:
        """Events with different labels are counted independently."""
        collector.record_event(
            event_type="meraki_webhook",
            network_id="N_001",
            alert_type="settings_changed",
        )
        collector.record_event(
            event_type="meraki_webhook",
            network_id="N_002",
            alert_type="offline_device",
        )

        value_n001 = REGISTRY.get_sample_value(
            "meraki_webhook_events_total",
            {
                "event_type": "meraki_webhook",
                "network_id": "N_001",
                "alert_type": "settings_changed",
            },
        )
        value_n002 = REGISTRY.get_sample_value(
            "meraki_webhook_events_total",
            {
                "event_type": "meraki_webhook",
                "network_id": "N_002",
                "alert_type": "offline_device",
            },
        )

        assert value_n001 == 1.0
        assert value_n002 == 1.0

    def test_record_event_different_event_types_have_separate_timestamps(
        self, collector: WebhookMetricsCollector
    ) -> None:
        """Different event_type values each have their own timestamp gauge."""
        collector.record_event(event_type="type_a")
        collector.record_event(event_type="type_b")

        ts_a = REGISTRY.get_sample_value(
            "meraki_webhook_last_event_timestamp",
            {"event_type": "type_a"},
        )
        ts_b = REGISTRY.get_sample_value(
            "meraki_webhook_last_event_timestamp",
            {"event_type": "type_b"},
        )

        assert ts_a is not None
        assert ts_b is not None


class TestRecordError:
    """Tests for WebhookMetricsCollector.record_error()."""

    def test_record_error_increments_counter(self, collector: WebhookMetricsCollector) -> None:
        """Calling record_error increments the processing_errors_total counter."""
        collector.record_error(error_type="validation_error")

        value = REGISTRY.get_sample_value(
            "meraki_webhook_processing_errors_total",
            {"error_type": "validation_error"},
        )
        assert value == 1.0

    def test_record_error_multiple_calls_accumulate(
        self, collector: WebhookMetricsCollector
    ) -> None:
        """Multiple calls with the same error_type accumulate."""
        for _ in range(5):
            collector.record_error(error_type="timeout")

        value = REGISTRY.get_sample_value(
            "meraki_webhook_processing_errors_total",
            {"error_type": "timeout"},
        )
        assert value == 5.0

    def test_record_error_different_types_tracked_separately(
        self, collector: WebhookMetricsCollector
    ) -> None:
        """Different error types are tracked under independent label sets."""
        collector.record_error(error_type="validation_error")
        collector.record_error(error_type="timeout")
        collector.record_error(error_type="timeout")

        value_validation = REGISTRY.get_sample_value(
            "meraki_webhook_processing_errors_total",
            {"error_type": "validation_error"},
        )
        value_timeout = REGISTRY.get_sample_value(
            "meraki_webhook_processing_errors_total",
            {"error_type": "timeout"},
        )

        assert value_validation == 1.0
        assert value_timeout == 2.0

    def test_record_error_does_not_affect_event_counter(
        self, collector: WebhookMetricsCollector
    ) -> None:
        """record_error must not touch the events_total counter."""
        collector.record_error(error_type="some_error")

        # No event counter should exist (labels have never been set)
        value = REGISTRY.get_sample_value(
            "meraki_webhook_events_total",
            {"event_type": "meraki_webhook", "network_id": "", "alert_type": ""},
        )
        assert value is None


class TestMetricInitialisation:
    """Smoke tests verifying metric objects are created correctly."""

    def test_collector_creates_events_counter(self, collector: WebhookMetricsCollector) -> None:
        """The internal Counter object is accessible."""
        assert collector._events_total is not None  # noqa: SLF001

    def test_collector_creates_timestamp_gauge(self, collector: WebhookMetricsCollector) -> None:
        """The internal Gauge object is accessible."""
        assert collector._last_event_timestamp is not None  # noqa: SLF001

    def test_collector_creates_error_counter(self, collector: WebhookMetricsCollector) -> None:
        """The internal errors Counter is accessible."""
        assert collector._processing_errors_total is not None  # noqa: SLF001
