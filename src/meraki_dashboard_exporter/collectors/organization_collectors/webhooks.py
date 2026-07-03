"""Organization webhook delivery-log collector (#300, #622).

Samples ``getOrganizationWebhooksLogs`` over a trailing 1-hour window and emits
a windowed count of delivery attempts by HTTP response status code. The gauge is
a per-cycle *count* (``_count``, not a monotonic ``_total``): it is fully
re-derived each cycle, and status codes that stop appearing are explicitly
zeroed so a code that no longer occurs reports 0 rather than freezing.

The log is empty unless webhook receivers are configured Meraki-side, which is a
normal, non-error state. The webhook target URL is deliberately never a label
(unbounded/attacker-influenced); only the bounded HTTP status code is labelled.

**Per-delivery OTel data log (#622).** The same fetched rows (no second API
call) are also, when the OTel data-log emitter is enabled and the
``ORG_WEBHOOK_DELIVERY`` event is allowlisted, emitted one log record per
delivery attempt via ``self.parent.data_log_emitter`` — complementing the
bounded aggregate metric above with unbounded per-delivery detail (status code,
alert type, URL *host* only) for operators with a log backend. See
``core/otel_data_logs.py`` for the emitter contract.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_org_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.otel_data_logs import DataLogEvent
from ...core.scheduler import EndpointGroupName
from .base import BaseOrganizationCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Trailing window sampled each cycle (1 hour), matching the metric's stated window.
_WEBHOOK_LOG_TIMESPAN = 3600

# Status-code label used when a delivery attempt produced no HTTP response
# (e.g. connection failure) — a non-2xx value so it counts as a failure in
# PromQL (status_code!~"2..").
_NO_RESPONSE_CODE = "0"


class WebhookLogsCollector(BaseOrganizationCollector):
    """Collector for organization webhook delivery-log metrics."""

    def __init__(self, parent: Any) -> None:
        """Initialize the collector.

        Parameters
        ----------
        parent : OrganizationCollector
            Parent OrganizationCollector instance that has metrics defined.

        """
        super().__init__(parent)
        # Status codes emitted on a previous cycle, per org — used to zero out
        # codes that are absent this cycle instead of leaving a stale count.
        self._seen_status_codes: dict[str, set[str]] = {}

    @log_api_call("getOrganizationWebhooksLogs")
    async def _fetch_webhook_logs(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch the organization's webhook delivery logs for the last hour."""
        self._track_api_call("getOrganizationWebhooksLogs")
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationWebhooksLogs,
            org_id,
            timespan=_WEBHOOK_LOG_TIMESPAN,
            total_pages="all",
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationWebhooksLogs",
            ),
        )

    @with_error_handling(
        operation="Collect webhook delivery log metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect(self, org_id: str, org_name: str) -> bool:
        """Collect webhook delivery-log metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        Returns
        -------
        bool
            ``True`` on success or when the endpoint is unavailable for this org
            (404); on a real failure the error is re-raised so the decorator can
            retry then swallow it. The coordinator treats any non-``True`` result
            as a failure (F-172).

        """
        if not self.parent._should_run_group(EndpointGroupName.ORG_WEBHOOK_LOGS):
            return True

        try:
            with LogContext(org_id=org_id, org_name=org_name):
                logs = await self._fetch_webhook_logs(org_id)

            self.parent._mark_group_ran(EndpointGroupName.ORG_WEBHOOK_LOGS)

            # Always process (even an empty list) so status codes that stop
            # appearing this window are explicitly zeroed.
            self._process_webhook_logs(org_id, org_name, logs)
            return True

        except Exception as e:
            if "404" in str(e):
                logger.debug(
                    "Webhook logs not available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
                return True
            raise  # Let decorator handle non-404 errors (retry + swallow)

    def _process_webhook_logs(self, org_id: str, org_name: str, logs: list[dict[str, Any]]) -> None:
        """Aggregate webhook delivery attempts by HTTP response status code.

        Also emits one OTel data-log record per delivery attempt (#622) when the
        emitter is enabled — reuses these same already-fetched rows, no second
        API call.
        """
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.ORG_WEBHOOK_LOGS)
        org_data = {"id": org_id, "name": org_name}

        emitter = getattr(self.parent, "data_log_emitter", None)
        emit_logs = emitter is not None and emitter.is_event_enabled(
            DataLogEvent.ORG_WEBHOOK_DELIVERY
        )

        counts: dict[str, int] = {}
        for entry in logs:
            # ⚠ Phase-6 live verification: confirm the response-code field name.
            code = entry.get("responseCode")
            status_code = str(code) if code is not None else _NO_RESPONSE_CODE
            counts[status_code] = counts.get(status_code, 0) + 1

            if emit_logs:
                self._emit_delivery_log(emitter, org_id, status_code, entry)

        # Zero out codes seen last cycle but absent now (windowed count resets).
        seen = self._seen_status_codes.setdefault(org_id, set())
        for stale_code in seen - counts.keys():
            labels = create_org_labels(org_data, status_code=stale_code)
            self._set_metric_value("_org_webhook_deliveries_count", labels, 0, ttl_seconds=ttl)

        for status_code, count in counts.items():
            labels = create_org_labels(org_data, status_code=status_code)
            self._set_metric_value("_org_webhook_deliveries_count", labels, count, ttl_seconds=ttl)

        seen.clear()
        seen.update(counts.keys())

        logger.debug(
            "Collected webhook delivery-log metrics",
            org_id=org_id,
            org_name=org_name,
            total_deliveries=len(logs),
            distinct_status_codes=len(counts),
        )

    @staticmethod
    def _emit_delivery_log(
        emitter: Any, org_id: str, status_code: str, entry: dict[str, Any]
    ) -> None:
        """Emit one ``ORG_WEBHOOK_DELIVERY`` data-log record for a delivery row.

        Bounded attributes only: no full URL (host only) and no raw payload.
        """
        attributes: dict[str, str | int | float | bool] = {
            "org.id": org_id,
            "status_code": status_code,
            "data.window_seconds": _WEBHOOK_LOG_TIMESPAN,
        }

        # ⚠ Phase-6 live verification: confirm the networkId/alertType field names.
        network_id = entry.get("networkId")
        if network_id:
            attributes["network.id"] = str(network_id)

        alert_type = entry.get("alertType")
        if alert_type:
            attributes["webhook.alert_type"] = str(alert_type)

        # URL *host* only — the full target URL is unbounded/attacker-influenced
        # and must never be emitted (matches the aggregate metric's rule).
        url = entry.get("url")
        if url:
            host = urlparse(str(url)).hostname
            if host:
                attributes["url.host"] = host

        emitter.emit(
            DataLogEvent.ORG_WEBHOOK_DELIVERY,
            attributes=attributes,
            body=f"webhook delivery attempt, status_code={status_code}",
        )
