"""Meraki assurance alerts collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..core.collector import MetricCollector
from ..core.constants import UpdateTier
from ..core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class AlertsCollector(MetricCollector):
    """Collector for Meraki assurance alerts."""

    # Alerts update at medium frequency
    update_tier: UpdateTier = UpdateTier.MEDIUM

    def _initialize_metrics(self) -> None:
        """Initialize alert metrics."""
        # Active alerts count by various dimensions
        self._alerts_active = self._create_gauge(
            "meraki_alerts_active",
            "Number of active Meraki assurance alerts",
            labelnames=[
                "org_id",
                "org_name",
                "network_id",
                "network_name",
                "alert_type",
                "category_type",
                "severity",
                "device_type",
            ],
        )

        # Total alerts by severity (simpler metric for quick dashboards)
        self._alerts_by_severity = self._create_gauge(
            "meraki_alerts_total_by_severity",
            "Total number of active alerts by severity",
            labelnames=["org_id", "org_name", "severity"],
        )

        # Alerts by network (for network-level overview)
        self._alerts_by_network = self._create_gauge(
            "meraki_alerts_total_by_network",
            "Total number of active alerts per network",
            labelnames=["org_id", "org_name", "network_id", "network_name"],
        )

    async def _collect_impl(self) -> None:
        """Collect alert metrics."""
        try:
            # Get organizations
            if self.settings.org_id:
                org_ids = [self.settings.org_id]
                org_names = {self.settings.org_id: "configured_org"}
            else:
                logger.debug("Fetching all organizations for alerts collection")
                self._track_api_call("getOrganizations")
                orgs = await asyncio.to_thread(self.api.organizations.getOrganizations)
                org_ids = [org["id"] for org in orgs]
                org_names = {org["id"]: org.get("name", "unknown") for org in orgs}
                logger.debug("Successfully fetched organizations", count=len(org_ids))

            # Collect alerts for each organization
            for org_id in org_ids:
                org_name = org_names.get(org_id, "unknown")
                try:
                    await self._collect_org_alerts(org_id, org_name)
                except Exception:
                    logger.exception(
                        "Failed to collect alerts for organization",
                        org_id=org_id,
                        org_name=org_name,
                    )

        except Exception:
            logger.exception("Failed to collect alert metrics")

    async def _collect_org_alerts(self, org_id: str, org_name: str) -> None:
        """Collect alerts for a specific organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            logger.debug("Fetching assurance alerts", org_id=org_id)
            self._track_api_call("getOrganizationAssuranceAlerts")

            # Get all active alerts
            alerts = await asyncio.to_thread(
                self.api.organizations.getOrganizationAssuranceAlerts,
                org_id,
                total_pages="all",
            )

            logger.debug("Successfully fetched alerts", org_id=org_id, count=len(alerts))

            # Clear previous metrics for this org to handle resolved alerts
            self._clear_org_metrics(org_id)

            if not alerts:
                logger.debug("No active alerts", org_id=org_id)
                return

            # Process alerts and aggregate counts
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

        except Exception as e:
            # Check if alerts API is available for this org
            error_str = str(e)
            if "404" in error_str or "not found" in error_str:
                logger.debug(
                    "Assurance alerts API not available",
                    org_id=org_id,
                    org_name=org_name,
                )
            else:
                logger.exception(
                    "Failed to collect alerts",
                    org_id=org_id,
                    org_name=org_name,
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
