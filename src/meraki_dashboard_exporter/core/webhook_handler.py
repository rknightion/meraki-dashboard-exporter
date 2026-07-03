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


class WebhookSecurityError(RuntimeError):
    """Raised at startup when the webhook receiver is configured insecurely.

    See :func:`enforce_webhook_security` - the receiver refuses to start with
    ``require_secret=false`` unless the operator has explicitly opted in via
    ``webhooks.allow_insecure=true``.
    """


# SECURITY (SEC-03 / #561): the success path labels metrics by ``alert_type``.
# When ``require_secret=false`` the payload is attacker-controlled, so an
# unbounded ``alert_type`` would let an attacker mint arbitrary time series
# (a cardinality bomb). Bound it to a known set of Meraki alert types and
# bucket anything unrecognised as ``ALERT_TYPE_OTHER``. Missing/empty stays
# ``ALERT_TYPE_UNKNOWN`` (also bounded).
ALERT_TYPE_OTHER = "other"
ALERT_TYPE_UNKNOWN = "unknown"

# Curated set of common Meraki webhook alert types (bounded allowlist). This is
# deliberately conservative: unknown values bucket to ``other`` rather than the
# allowlist growing without bound. Add well-known types here as needed.
KNOWN_ALERT_TYPES: frozenset[str] = frozenset({
    "settings_changed",
    "settings changed",
    "client_connectivity",
    "connectivity",
    "device_down",
    "gateway_down",
    "gateway_to_repeater",
    "repeater_to_gateway",
    "dhcp_no_leases",
    "dhcp_lease",
    "rogue_ap",
    "rogue_dhcp",
    "port_error",
    "port_down",
    "port_link_change",
    "power_supply",
    "vpn_connectivity_change",
    "cellular_up",
    "cellular_down",
    "motion_detected",
    "motion_alert",
    "sensor_alert",
    "water_detected",
    "door_opened",
    "temperature",
    "humidity",
    "high_wireless_usage",
    "high_wired_usage",
    "network_usage",
    "onboarding",
    "config_changed",
    "failed_8021x_auth",
    "splash_auth",
    "air_marshal",
    "ip_conflict",
    "uplink_status_change",
})


def bound_alert_type(alert_type: str | None) -> str:
    """Bound an incoming ``alert_type`` to a fixed-cardinality label value.

    Parameters
    ----------
    alert_type : str | None
        Raw ``alertType`` from the webhook payload (attacker-controlled when
        ``require_secret=false``).

    Returns
    -------
    str
        The value unchanged if it is in :data:`KNOWN_ALERT_TYPES`,
        :data:`ALERT_TYPE_UNKNOWN` when missing/empty, otherwise
        :data:`ALERT_TYPE_OTHER`.

    """
    if not alert_type:
        return ALERT_TYPE_UNKNOWN
    if alert_type in KNOWN_ALERT_TYPES:
        return alert_type
    return ALERT_TYPE_OTHER


def bound_org_id(org_id: str | None, known_org_ids: set[str]) -> str:
    """Bound an incoming ``org_id`` to the configured/known org set.

    Any ``org_id`` not in ``known_org_ids`` (including an attacker-supplied one
    when ``require_secret=false``) is bucketed as ``ALERT_TYPE_OTHER`` to keep
    the metric label cardinality bounded.

    Parameters
    ----------
    org_id : str | None
        Raw ``organizationId`` from the webhook payload.
    known_org_ids : set[str]
        The set of organization IDs this exporter is configured for.

    Returns
    -------
    str
        ``org_id`` when it is a known org, otherwise ``"other"``.

    """
    if org_id and org_id in known_org_ids:
        return org_id
    return ALERT_TYPE_OTHER


def enforce_webhook_security(*, enabled: bool, require_secret: bool, allow_insecure: bool) -> None:
    """Refuse the insecure webhook combination at startup (SEC-03 / #561).

    Running the webhook receiver with ``require_secret=false`` lets an
    unauthenticated caller drive the success-path metric labels; combined with
    the (now bounded) label set the blast radius is limited, but it is still an
    unauthenticated write surface. Fail fast unless the operator has explicitly
    accepted the risk via ``allow_insecure=true``.

    Parameters
    ----------
    enabled : bool
        Whether the webhook receiver is enabled.
    require_secret : bool
        Whether shared-secret validation is required.
    allow_insecure : bool
        Explicit opt-in to run enabled + ``require_secret=false``.

    Raises
    ------
    WebhookSecurityError
        If ``enabled and not require_secret and not allow_insecure``.

    """
    if enabled and not require_secret and not allow_insecure:
        raise WebhookSecurityError(
            "Webhook receiver is enabled with require_secret=false. This accepts "
            "unauthenticated webhook POSTs. Set webhooks.require_secret=true "
            "(recommended) or explicitly opt in with webhooks.allow_insecure=true "
            "to run without a shared secret."
        )


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

        # SECURITY (SEC-03 / #561): the set of org IDs this exporter is
        # configured for. Success-path ``org_id`` labels are validated against
        # this so an attacker payload cannot inject a novel org_id label.
        self._known_org_ids: set[str] = (
            {settings.meraki.org_id} if settings.meraki.org_id else set()
        )

        # In-memory receiver health (surfaced on /status, #317). These are plain
        # counters/timestamps kept alongside the Prometheus metrics because the
        # latter are awkward to read back for a point-in-time status snapshot.
        self._events_received_total = 0
        self._events_processed_total = 0
        self._events_failed_total = 0
        self._validation_failures_total = 0
        self._last_event_time: float | None = None
        self._last_alert_type: str | None = None
        # Bounded (keys are always bound_alert_type outputs).
        self._events_by_type: dict[str, int] = {}

    def record_validation_failure(self, validation_error: str) -> None:
        """Record a webhook validation failure (Prometheus + in-memory, #317).

        Parameters
        ----------
        validation_error : str
            A bounded, caller-supplied reason string (never attacker-derived).

        """
        self.validation_failures.labels(validation_error=validation_error).inc()
        self._validation_failures_total += 1

    def get_status(self) -> dict[str, Any]:
        """Return a point-in-time snapshot of receiver health (#317)."""
        return {
            "events_received": self._events_received_total,
            "events_processed": self._events_processed_total,
            "events_failed": self._events_failed_total,
            "validation_failures": self._validation_failures_total,
            "last_event_time": self._last_event_time,
            "last_alert_type": self._last_alert_type,
            "events_by_type": dict(self._events_by_type),
        }

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
            self.record_validation_failure("secret_not_configured")
            return False

        # Validate the secret using a constant-time comparison (F-109 / CWE-208).
        # A plain `!=` compare leaks the length of the matching prefix via timing,
        # letting an attacker recover the secret byte-by-byte.
        expected_secret = self.settings.webhooks.shared_secret.get_secret_value()
        if payload_secret is None or not hmac.compare_digest(
            payload_secret.encode("utf-8"), expected_secret.encode("utf-8")
        ):
            logger.warning("Invalid shared secret in webhook payload")
            self.record_validation_failure("secret_mismatch")
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

            # SECURITY (SEC-03 / #561): bound the success-path labels. On the
            # insecure path org_id/alert_type are attacker-controlled, so
            # validate org_id against the known org set and bucket unknown
            # alert types to prevent an unbounded-cardinality label injection.
            org_id = bound_org_id(payload.organization_id, self._known_org_ids)
            alert_type = bound_alert_type(payload.alert_type)

            self.events_received.labels(
                org_id=org_id,
                alert_type=alert_type,
            ).inc()

            # Log the event (bounded label values only).
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

            # In-memory receiver health (#317). Keys are bounded alert types.
            self._events_received_total += 1
            self._events_processed_total += 1
            self._last_event_time = time.time()
            self._last_alert_type = alert_type
            self._events_by_type[alert_type] = self._events_by_type.get(alert_type, 0) + 1

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
            self.record_validation_failure("invalid_payload")

            # SECURITY (F-051): label only by the bounded error_type - payload_data
            # values are attacker-controlled and unbounded on the failure path.
            self.events_failed.labels(error_type="validation_error").inc()
            self._events_failed_total += 1

            return None

        except Exception as e:
            logger.exception("Unexpected error processing webhook")

            # SECURITY (F-051): bounded error_type label only.
            self.events_failed.labels(error_type=type(e).__name__).inc()
            self._events_failed_total += 1

            return None
