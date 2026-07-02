"""Webhook event handler with metrics tracking."""

from __future__ import annotations

import hmac
import time
from typing import TYPE_CHECKING, Any

from prometheus_client import Counter, Histogram
from pydantic import ValidationError

from ..models.webhook import WebhookPayload
from .constants.metrics_constants import WebhookMetricName
from .logging import get_logger
from .metrics import LabelName

if TYPE_CHECKING:
    from .config import Settings

logger = get_logger(__name__)


class WebhookHandler:
    """Handler for processing Meraki webhook events with metrics tracking.

    Parameters
    ----------
    settings : Settings
        Application settings including webhook configuration.

    """

    def __init__(self, settings: Settings) -> None:
        """Initialize webhook handler with metrics."""
        self.settings = settings
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics for webhook tracking."""
        # Event counters
        self.events_received = Counter(
            WebhookMetricName.WEBHOOK_EVENTS_RECEIVED_TOTAL.value,
            "Total webhook events received by the active WebhookHandler request pipeline "
            "(POST /api/webhooks/meraki), labeled by org_id and alert_type",
            [LabelName.ORG_ID.value, LabelName.ALERT_TYPE.value],
        )

        self.events_processed = Counter(
            WebhookMetricName.WEBHOOK_EVENTS_PROCESSED_TOTAL.value,
            "Total webhook events successfully processed",
            [LabelName.ORG_ID.value, LabelName.ALERT_TYPE.value],
        )

        # SECURITY (F-051): the failure path is reachable before the shared secret is
        # verified, and org_id/alert_type on a malformed payload are attacker-controlled,
        # unbounded strings. Label the failure counter ONLY by the bounded error_type to
        # prevent unauthenticated cardinality injection.
        self.events_failed = Counter(
            WebhookMetricName.WEBHOOK_EVENTS_FAILED_TOTAL.value,
            "Total webhook events that failed processing",
            [LabelName.ERROR_TYPE.value],
        )

        # Processing latency
        self.processing_duration = Histogram(
            WebhookMetricName.WEBHOOK_PROCESSING_DURATION_SECONDS.value,
            "Time spent processing webhook events",
            [LabelName.ORG_ID.value, LabelName.ALERT_TYPE.value],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        )

        # Validation failures
        self.validation_failures = Counter(
            WebhookMetricName.WEBHOOK_VALIDATION_FAILURES_TOTAL.value,
            "Total webhook validation failures",
            [LabelName.VALIDATION_ERROR.value],
        )

    def validate_secret(self, payload_secret: str | None) -> bool:
        """Validate webhook shared secret.

        Parameters
        ----------
        payload_secret : str | None
            Shared secret from the webhook payload.

        Returns
        -------
        bool
            True if validation passes or is not required, False otherwise.

        """
        # If secret validation is not required, always pass
        if not self.settings.webhooks.require_secret:
            logger.debug("Shared secret validation not required, skipping")
            return True

        # If secret validation is required but not configured, reject
        if not self.settings.webhooks.shared_secret:
            logger.warning("Shared secret validation required but not configured")
            self.validation_failures.labels(validation_error="secret_not_configured").inc()
            return False

        # Validate the secret using a constant-time comparison (F-109 / CWE-208).
        # A plain `!=` compare leaks the length of the matching prefix via timing,
        # letting an attacker recover the secret byte-by-byte.
        expected_secret = self.settings.webhooks.shared_secret.get_secret_value()
        if payload_secret is None or not hmac.compare_digest(
            payload_secret.encode("utf-8"), expected_secret.encode("utf-8")
        ):
            logger.warning("Invalid shared secret in webhook payload")
            self.validation_failures.labels(validation_error="secret_mismatch").inc()
            return False

        return True

    def process_webhook(self, payload_data: dict[str, Any]) -> WebhookPayload | None:
        """Process a webhook event.

        Parameters
        ----------
        payload_data : dict
            Raw webhook payload data.

        Returns
        -------
        WebhookPayload | None
            Validated webhook payload, or None if validation fails.

        """
        start_time = time.time()

        try:
            # Parse and validate payload
            payload = WebhookPayload.model_validate(payload_data)

            # Validate shared secret
            if not self.validate_secret(payload.shared_secret):
                return None

            # Track received event
            org_id = payload.organization_id
            alert_type = payload.alert_type or "unknown"

            self.events_received.labels(
                org_id=org_id,
                alert_type=alert_type,
            ).inc()

            # Log the event
            logger.info(
                "Webhook event received",
                org_id=org_id,
                alert_type=alert_type,
                network_id=payload.network_id,
                device_serial=payload.device_serial,
            )

            # Track successful processing
            self.events_processed.labels(
                org_id=org_id,
                alert_type=alert_type,
            ).inc()

            # Track processing duration
            duration = time.time() - start_time
            self.processing_duration.labels(
                org_id=org_id,
                alert_type=alert_type,
            ).observe(duration)

            return payload

        except ValidationError as e:
            # SECURITY (F-166): never log raw error input. Pydantic embeds the ENTIRE
            # raw payload (including sharedSecret) in errors()[i]["input"] on
            # missing-field errors, and str(e) does the same. Log only the field
            # locations and error types - never the values.
            sanitized_errors = [
                {
                    "loc": ".".join(str(part) for part in err.get("loc", ())),
                    "type": err.get("type", ""),
                }
                for err in e.errors()
            ]
            logger.error(
                "Webhook payload validation failed",
                error_count=len(sanitized_errors),
                errors=sanitized_errors,
            )
            self.validation_failures.labels(validation_error="invalid_payload").inc()

            # SECURITY (F-051): label only by the bounded error_type - payload_data
            # values are attacker-controlled and unbounded on the failure path.
            self.events_failed.labels(error_type="validation_error").inc()

            return None

        except Exception as e:
            logger.exception("Unexpected error processing webhook")

            # SECURITY (F-051): bounded error_type label only.
            self.events_failed.labels(error_type=type(e).__name__).inc()

            return None
