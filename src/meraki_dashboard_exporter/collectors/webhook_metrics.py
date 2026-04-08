"""Webhook event metrics collector.

Event-driven metric sink - not a polled collector. The webhook handler
calls record_event() on each received webhook push.

Integration point
-----------------
To wire this into the webhook processing pipeline, instantiate
``WebhookMetricsCollector`` once at application startup and pass it to
wherever ``WebhookHandler.process_webhook()`` is called (e.g. the FastAPI
route in ``app.py``).  After a successful ``WebhookHandler.process_webhook``
call, call::

    webhook_metrics.record_event(
        event_type="meraki_webhook",
        network_id=payload.network_id or "",
        alert_type=payload.alert_type or "",
    )

On error, call ``webhook_metrics.record_error(error_type=...)``.

This collector is intentionally NOT registered with the tier-based polling
system (no ``@register_collector`` decorator) because its metrics are
updated in response to inbound HTTP pushes, not on a schedule.
"""

from __future__ import annotations

import time

from prometheus_client import Counter, Gauge

from ..core.constants.metrics_constants import WebhookMetricName
from ..core.logging import get_logger
from ..core.metrics import LabelName

logger = get_logger(__name__)


class WebhookMetricsCollector:
    """Converts webhook events into Prometheus metrics.

    Not registered with the tier system - metrics are updated
    on each webhook push, not on a polling schedule.
    """

    def __init__(self) -> None:
        """Initialise Prometheus metrics for the webhook event sink."""
        self._events_total = Counter(
            WebhookMetricName.WEBHOOK_EVENTS_TOTAL.value,
            "Total webhook events received",
            [
                LabelName.EVENT_TYPE.value,
                LabelName.NETWORK_ID.value,
                LabelName.ALERT_TYPE.value,
            ],
        )
        self._last_event_timestamp = Gauge(
            WebhookMetricName.WEBHOOK_LAST_EVENT_TIMESTAMP.value,
            "Unix timestamp of last webhook event",
            [LabelName.EVENT_TYPE.value],
        )
        self._processing_errors_total = Counter(
            WebhookMetricName.WEBHOOK_PROCESSING_ERRORS_TOTAL.value,
            "Total webhook processing errors",
            [LabelName.ERROR_TYPE.value],
        )

    def record_event(
        self,
        event_type: str,
        network_id: str = "",
        alert_type: str = "",
    ) -> None:
        """Record a webhook event.

        Parameters
        ----------
        event_type : str
            Type of webhook event (e.g. ``"meraki_webhook"``).
        network_id : str
            Network ID from the webhook payload, or empty string if absent.
        alert_type : str
            Alert type from the webhook payload, or empty string if absent.

        """
        self._events_total.labels(
            event_type=event_type,
            network_id=network_id,
            alert_type=alert_type,
        ).inc()
        self._last_event_timestamp.labels(
            event_type=event_type,
        ).set(time.time())
        logger.debug(
            "Recorded webhook event",
            event_type=event_type,
            network_id=network_id,
            alert_type=alert_type,
        )

    def record_error(self, error_type: str) -> None:
        """Record a webhook processing error.

        Parameters
        ----------
        error_type : str
            Type of error that occurred (e.g. ``"validation_error"``).

        """
        self._processing_errors_total.labels(
            error_type=error_type,
        ).inc()
        logger.debug("Recorded webhook processing error", error_type=error_type)
