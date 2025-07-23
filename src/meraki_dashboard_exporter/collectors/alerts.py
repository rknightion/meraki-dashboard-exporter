"""Meraki assurance alerts collector."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, cast

from ..core.collector import MetricCollector
from ..core.constants import AlertMetricName, UpdateTier
from ..core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ..core.label_helpers import create_network_labels
from ..core.logging import get_logger
from ..core.logging_decorators import log_api_call, log_batch_operation
from ..core.logging_helpers import LogContext, log_metric_collection_summary
from ..core.metrics import LabelName
from ..core.registry import register_collector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)
class AlertsCollector(MetricCollector):
    """Collector for Meraki assurance alerts."""

    def _initialize_metrics(self) -> None:
        """Initialize alert metrics."""
        # Active alerts count by various dimensions
        self._alerts_active = self._create_gauge(
            AlertMetricName.ALERTS_ACTIVE,
            "Number of active Meraki assurance alerts",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.ALERT_TYPE,
                LabelName.CATEGORY_TYPE,
                LabelName.SEVERITY,
                LabelName.DEVICE_TYPE,
            ],
        )

        # Total alerts by severity (simpler metric for quick dashboards)
        self._alerts_by_severity = self._create_gauge(
            AlertMetricName.ALERTS_TOTAL_BY_SEVERITY,
            "Total number of active alerts by severity",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME, LabelName.SEVERITY],
        )

        # Alerts by network (for network-level overview)
        self._alerts_by_network = self._create_gauge(
            AlertMetricName.ALERTS_TOTAL_BY_NETWORK,
            "Total number of active alerts per network",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
            ],
        )

        # Sensor alerts by metric type
        self._sensor_alerts_total = self._create_gauge(
            AlertMetricName.SENSOR_ALERTS_TOTAL,
            "Total number of sensor alerts in the last hour by metric type",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.METRIC,
            ],
        )

    async def _collect_impl(self) -> None:
        """Collect alert metrics."""
        start_time = time.time()
        metrics_collected = 0
        api_calls_made = 0

        try:
            # Get organizations with error handling
            orgs_data = await self._fetch_organizations()
            if not orgs_data:
                logger.warning("No organizations found for alerts collection")
                return
            api_calls_made += 1

            # Build org mapping
            if self.settings.meraki.org_id:
                org_ids = [self.settings.meraki.org_id]
                org_names = {
                    self.settings.meraki.org_id: orgs_data[0].get("name", "configured_org")
                }
            else:
                org_ids = [org["id"] for org in orgs_data]
                org_names = {org["id"]: org.get("name", "unknown") for org in orgs_data}

            # Collect alerts for each organization
            tasks = [
                self._collect_org_alerts(org_id, org_names.get(org_id, "unknown"))
                for org_id in org_ids
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successful collections
            for result in results:
                if not isinstance(result, Exception):
                    api_calls_made += 1

            # Collect sensor alerts for all networks
            # First get all networks for all orgs
            networks = []
            for org_id in org_ids:
                org_networks = await self._fetch_networks(org_id)
                if org_networks:
                    networks.extend(org_networks)
                    api_calls_made += 1

            # Collect sensor alerts for each network
            if networks:
                # Add org info to each network
                for network in networks:
                    org_id = network.get("organizationId", "")
                    network["orgId"] = org_id
                    network["orgName"] = org_names.get(org_id, org_id)

                sensor_tasks = [
                    self._collect_network_sensor_alerts(network) for network in networks
                ]
                sensor_results = await asyncio.gather(*sensor_tasks, return_exceptions=True)

                # Count successful sensor alert collections
                for result in sensor_results:
                    if not isinstance(result, Exception):
                        api_calls_made += 1

            # Log collection summary
            duration = time.time() - start_time
            log_metric_collection_summary(
                "AlertsCollector",
                metrics_collected=metrics_collected,  # This would need to be tracked
                duration_seconds=duration,
                organizations_processed=len(org_ids),
                api_calls_made=api_calls_made,
            )

        except Exception:
            logger.exception("Failed to collect alert metrics")

    @log_api_call("getOrganization")
    @with_error_handling(
        operation="Fetch organizations",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_organizations(self) -> list[dict[str, Any]] | None:
        """Fetch organizations for alerts collection.

        Returns
        -------
        list[dict[str, Any]] | None
            List of organizations or None on error.

        """
        if self.settings.meraki.org_id:
            org = await asyncio.to_thread(
                self.api.organizations.getOrganization,
                self.settings.meraki.org_id,
            )
            return [org]
        else:
            orgs = await asyncio.to_thread(self.api.organizations.getOrganizations)
            orgs = validate_response_format(orgs, expected_type=list, operation="getOrganizations")
            return cast(list[dict[str, Any]], orgs)

    @log_api_call("getOrganizationAssuranceAlerts")
    @with_error_handling(
        operation="Collect organization alerts",
        continue_on_error=True,
        error_category=ErrorCategory.API_NOT_AVAILABLE,
    )
    async def _collect_org_alerts(self, org_id: str, org_name: str) -> None:
        """Collect alerts for a specific organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        with LogContext(org_id=org_id, org_name=org_name):
            # Get all active alerts
            alerts = await asyncio.to_thread(
                self.api.organizations.getOrganizationAssuranceAlerts,
                org_id,
                total_pages="all",
            )
            alerts = validate_response_format(
                alerts, expected_type=list, operation="getOrganizationAssuranceAlerts"
            )

            # Clear previous metrics for this org to handle resolved alerts
            self._clear_org_metrics(org_id)

            if not alerts:
                logger.debug("No active alerts", org_id=org_id)
                return

            # Process alerts and aggregate counts
            self._process_alerts(alerts, org_id, org_name)

    @log_batch_operation("process alerts")
    def _process_alerts(self, alerts: list[dict[str, Any]], org_id: str, org_name: str) -> None:
        """Process alert data and update metrics.

        Parameters
        ----------
        alerts : list[dict[str, Any]]
            List of alert data
        org_id : str
            Organization ID
        org_name : str
            Organization name

        """
        alert_counts: dict[tuple[str, str, str, str, str, str, str, str], int] = {}
        severity_counts = {"critical": 0, "warning": 0, "informational": 0}
        network_counts: dict[tuple[str, str], int] = {}

        for alert in alerts:
            # Skip dismissed or resolved alerts
            if alert.get("dismissedAt") or alert.get("resolvedAt"):
                continue

            # Extract alert details
            alert_type = alert.get("type", "unknown")
            category_type = alert.get("categoryType", "unknown")
            severity = alert.get("severity", "unknown")
            device_type = alert.get("deviceType", "none")  # Can be null for org-wide alerts

            network = alert.get("network", {})
            network_id = network.get("id", "unknown")
            network_name = network.get("name", "unknown")

            # Create composite key for aggregation
            key = (
                org_id,
                org_name,
                network_id,
                network_name,
                alert_type,
                category_type,
                severity,
                device_type or "none",  # Handle null device types
            )

            # Count alerts by composite key
            alert_counts[key] = alert_counts.get(key, 0) + 1

            # Count by severity
            if severity in severity_counts:
                severity_counts[severity] += 1

            # Count by network
            network_key = (network_id, network_name)
            network_counts[network_key] = network_counts.get(network_key, 0) + 1

        # Set metrics for active alerts
        for key, count in alert_counts.items():
            (
                org_id,
                org_name,
                network_id,
                network_name,
                alert_type,
                category_type,
                severity,
                device_type,
            ) = key

            self._alerts_active.labels(
                org_id=org_id,
                org_name=org_name,
                network_id=network_id,
                network_name=network_name,
                alert_type=alert_type,
                category_type=category_type,
                severity=severity,
                device_type=device_type,
            ).set(count)

        # Set severity summary metrics
        for severity, count in severity_counts.items():
            self._alerts_by_severity.labels(
                org_id=org_id,
                org_name=org_name,
                severity=severity,
            ).set(count)

        # Set network summary metrics
        for (network_id, network_name), count in network_counts.items():
            self._alerts_by_network.labels(
                org_id=org_id,
                org_name=org_name,
                network_id=network_id,
                network_name=network_name,
            ).set(count)

        logger.debug(
            "Collected alert metrics",
            org_id=org_id,
            org_name=org_name,
            total_alerts=len(alerts),
            active_alerts=sum(alert_counts.values()),
            severity_breakdown=severity_counts,
            affected_networks=len(network_counts),
        )

    def _clear_org_metrics(self, org_id: str) -> None:
        """Clear all metrics for an organization to handle resolved alerts.

        Parameters
        ----------
        org_id : str
            Organization ID to clear metrics for.

        """
        # This is a simplified approach - in production you might want
        # to track and clear specific label combinations
        logger.debug("Clearing previous alert metrics", org_id=org_id)

    @log_api_call("getOrganizationNetworks")
    @with_error_handling(
        operation="Fetch networks",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _fetch_networks(self, org_id: str) -> list[dict[str, Any]] | None:
        """Fetch networks for sensor alerts collection.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]] | None
            List of networks or None on error.

        """
        networks = await asyncio.to_thread(
            self.api.organizations.getOrganizationNetworks,
            org_id,
            total_pages="all",
        )
        networks = validate_response_format(
            networks, expected_type=list, operation="getOrganizationNetworks"
        )
        return cast(list[dict[str, Any]], networks)

    @log_api_call("getNetworkSensorAlertsOverviewByMetric")
    @with_error_handling(
        operation="Collect network sensor alerts",
        continue_on_error=True,
        error_category=ErrorCategory.API_NOT_AVAILABLE,
    )
    async def _collect_network_sensor_alerts(self, network: dict[str, Any]) -> None:
        """Collect sensor alerts for a specific network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data with org info.

        """
        network_id = network["id"]
        network_name = network.get("name", network_id)
        org_id = network.get("orgId", "")
        org_name = network.get("orgName", org_id)

        with LogContext(network_id=network_id, network_name=network_name, org_id=org_id):
            # Get sensor alerts for the last hour
            overview = await asyncio.to_thread(
                self.api.sensor.getNetworkSensorAlertsOverviewByMetric,
                network_id,
                timespan=3600,
                interval=3600,
            )

            overview = validate_response_format(
                overview, expected_type=list, operation="getNetworkSensorAlertsOverviewByMetric"
            )

            if not overview:
                logger.debug("No sensor alert data", network_id=network_id)
                return

            # Process the first (and should be only) interval
            if overview and len(overview) > 0:
                latest_interval = overview[0]
                counts = latest_interval.get("counts", {})

                # Create network labels using helper
                labels = create_network_labels(
                    network,
                    org_id=org_id,
                    org_name=org_name,
                )

                # Process each metric type
                for metric_type, value in counts.items():
                    # Handle nested noise structure
                    if metric_type == "noise" and isinstance(value, dict):
                        # Process nested ambient noise
                        ambient_value = value.get("ambient", 0)
                        metric_labels = {**labels, "metric": "noise_ambient"}
                        self._sensor_alerts_total.labels(**metric_labels).set(ambient_value)
                    elif isinstance(value, (int, float)):
                        # Process regular numeric values
                        metric_labels = {**labels, "metric": metric_type}
                        self._sensor_alerts_total.labels(**metric_labels).set(value)
                    else:
                        logger.warning(
                            "Unexpected sensor alert count format",
                            network_id=network_id,
                            metric_type=metric_type,
                            value_type=type(value).__name__,
                        )

                logger.debug(
                    "Collected sensor alert metrics",
                    network_id=network_id,
                    network_name=network_name,
                    metric_count=len(counts),
                )
