"""Example refactoring of alerts collector with standardized logging patterns."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..core.collector import MetricCollector
from ..core.constants import NetworkMetricName, OrgMetricName, UpdateTier
from ..core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ..core.logging import get_logger
from ..core.logging_decorators import log_api_call, log_batch_operation, log_collection_progress
from ..core.logging_helpers import LogContext, log_discovery_info, log_metric_collection_summary
from ..core.metrics import LabelName
from ..core.registry import register_collector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings

logger = get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)
class AlertsCollectorWithLogging(MetricCollector):
    """Collector for assurance alerts from the Meraki Dashboard API.

    This example shows how to use the new standardized logging patterns.
    """

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
    ) -> None:
        """Initialize the alerts collector."""
        super().__init__(api, settings, registry)
        self._logger = logger.bind(collector="AlertsCollector")

    def _initialize_metrics(self) -> None:
        """Initialize alert metrics."""
        # Alert count by type
        self._alerts_by_type = self._create_gauge(
            OrgMetricName.ORG_ALERTS_ACTIVE_BY_TYPE,
            "Number of active alerts by type and category",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ALERT_TYPE,
                LabelName.CATEGORY,
                LabelName.SEVERITY,
            ],
        )

        # Alert count by severity
        self._alerts_by_severity = self._create_gauge(
            OrgMetricName.ORG_ALERTS_ACTIVE_BY_SEVERITY_TOTAL,
            "Total number of active alerts by severity",
            labelnames=[LabelName.ORG_ID, LabelName.SEVERITY],
        )

        # Alert count by network
        self._alerts_by_network = self._create_gauge(
            NetworkMetricName.NETWORK_ALERTS_ACTIVE_TOTAL,
            "Number of active alerts per network",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SEVERITY,
            ],
        )

    @with_error_handling(
        operation="Collect assurance alerts",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_impl(self) -> None:
        """Collect alert metrics."""
        start_time = time.time()
        metrics_collected = 0
        api_calls_made = 0

        # Use context manager for structured logging context
        with LogContext(tier=self.update_tier.value):
            # First, fetch organizations
            organizations = await self._fetch_organizations()
            if not organizations:
                self._logger.warning("No organizations to process")
                return

            # Log discovery info once
            log_discovery_info(
                "organizations",
                count=len(organizations),
                org_ids=[org.get("id") for org in organizations],
            )

            # Process each organization
            for idx, org in enumerate(organizations, 1):
                org_id = org.get("id", "")
                org_name = org.get("name", "Unknown")

                # Add org context for all logs in this scope
                with LogContext(org_id=org_id, org_name=org_name):
                    # Use progress logging decorator
                    await self._process_organization_alerts(
                        org_id=org_id, org_name=org_name, current=idx, total=len(organizations)
                    )

                    metrics_collected += await self._get_metrics_count_for_org(org_id)
                    api_calls_made += 1

            # Log collection summary
            duration = time.time() - start_time
            log_metric_collection_summary(
                "AlertsCollector",
                metrics_collected=metrics_collected,
                duration_seconds=duration,
                organizations_processed=len(organizations),
                api_calls_made=api_calls_made,
            )

    @log_api_call("getOrganizations")
    @with_error_handling(
        operation="Fetch organizations for alerts",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_organizations(self) -> list[dict[str, Any]] | None:
        """Fetch organizations from API with logging."""
        return await self.api.organizations.getOrganizations()

    @log_collection_progress("organization alerts")
    async def _process_organization_alerts(
        self, org_id: str, org_name: str, current: int, total: int
    ) -> None:
        """Process alerts for a single organization."""
        alerts = await self._fetch_alerts_for_org(org_id)
        if alerts:
            await self._process_alerts_batch(org_id, alerts)

    @log_api_call("getOrganizationAssuranceAlerts")
    @with_error_handling(
        operation="Fetch alerts",
        continue_on_error=True,
        error_category=ErrorCategory.API_NOT_AVAILABLE,
    )
    async def _fetch_alerts_for_org(self, org_id: str) -> list[dict[str, Any]] | None:
        """Fetch alerts for an organization."""
        try:
            # API call with automatic logging via decorator
            alerts = await self.api.organizations.getOrganizationAssuranceAlerts(
                organizationId=org_id
            )

            # Validate response format
            alerts = validate_response_format(
                alerts, expected_type=list, operation="getOrganizationAssuranceAlerts"
            )

            # Filter for active alerts only
            active_alerts = [a for a in alerts if a.get("status") == "active"]

            self._logger.debug(
                "Filtered active alerts",
                total_alerts=len(alerts),
                active_alerts=len(active_alerts),
            )

            return active_alerts

        except Exception:
            # Error already logged by decorator
            return None

    @log_batch_operation("process alerts", batch_size=50)
    async def _process_alerts_batch(self, org_id: str, alerts: list[dict[str, Any]]) -> None:
        """Process a batch of alerts."""
        # Group alerts for metric updates
        alerts_by_type: dict[tuple[str, str, str], int] = {}
        alerts_by_severity: dict[str, int] = {}
        alerts_by_network: dict[tuple[str, str, str], int] = {}

        for alert in alerts:
            alert_type = alert.get("type", "unknown")
            category = alert.get("category", "unknown")
            severity = alert.get("severity", "unknown")
            network_id = alert.get("networkId", "")
            network_name = alert.get("networkName", "Unknown")

            # Count by type
            key = (alert_type, category, severity)
            alerts_by_type[key] = alerts_by_type.get(key, 0) + 1

            # Count by severity
            alerts_by_severity[severity] = alerts_by_severity.get(severity, 0) + 1

            # Count by network if available
            if network_id:
                net_key = (network_id, network_name, severity)
                alerts_by_network[net_key] = alerts_by_network.get(net_key, 0) + 1

        # Update metrics with batched data
        self._update_alert_metrics(org_id, alerts_by_type, alerts_by_severity, alerts_by_network)

    def _update_alert_metrics(
        self,
        org_id: str,
        alerts_by_type: dict[tuple[str, str, str], int],
        alerts_by_severity: dict[str, int],
        alerts_by_network: dict[tuple[str, str, str], int],
    ) -> None:
        """Update alert metrics."""
        # Update type metrics
        for (alert_type, category, severity), count in alerts_by_type.items():
            self._set_metric_value(
                "_alerts_by_type",
                {
                    LabelName.ORG_ID: org_id,
                    LabelName.ALERT_TYPE: alert_type,
                    LabelName.CATEGORY: category,
                    LabelName.SEVERITY: severity,
                },
                count,
            )

        # Update severity metrics
        for severity, count in alerts_by_severity.items():
            self._set_metric_value(
                "_alerts_by_severity",
                {
                    LabelName.ORG_ID: org_id,
                    LabelName.SEVERITY: severity,
                },
                count,
            )

        # Update network metrics
        for (network_id, network_name, severity), count in alerts_by_network.items():
            self._set_metric_value(
                "_alerts_by_network",
                {
                    LabelName.ORG_ID: org_id,
                    LabelName.NETWORK_ID: network_id,
                    LabelName.NETWORK_NAME: network_name,
                    LabelName.SEVERITY: severity,
                },
                count,
            )

    async def _get_metrics_count_for_org(self, org_id: str) -> int:
        """Calculate number of metrics collected for an organization."""
        # This is a simplified count - in reality you'd track actual metrics set
        return 10  # placeholder


# Import time at the end
import time
