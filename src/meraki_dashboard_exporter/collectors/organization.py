"""Organization-level metric collector."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..core.collector import MetricCollector
from ..core.constants import MetricName
from ..core.logging import get_logger

if TYPE_CHECKING:

    pass

logger = get_logger(__name__)


class OrganizationCollector(MetricCollector):
    """Collector for organization-level metrics."""

    def _initialize_metrics(self) -> None:
        """Initialize organization metrics."""
        # Organization info
        self._org_info = self._create_info(
            "meraki_org_info",
            "Organization information",
            labelnames=["org_id", "org_name"],
        )

        # API metrics
        self._api_requests_total = self._create_gauge(
            MetricName.ORG_API_REQUESTS_TOTAL,
            "Total API requests made by the organization",
            labelnames=["org_id", "org_name"],
        )

        self._api_rate_limit = self._create_gauge(
            MetricName.ORG_API_REQUESTS_RATE_LIMIT,
            "API rate limit for the organization",
            labelnames=["org_id", "org_name"],
        )

        # Network metrics
        self._networks_total = self._create_gauge(
            MetricName.ORG_NETWORKS_TOTAL,
            "Total number of networks in the organization",
            labelnames=["org_id", "org_name"],
        )

        # Device metrics
        self._devices_total = self._create_gauge(
            MetricName.ORG_DEVICES_TOTAL,
            "Total number of devices in the organization",
            labelnames=["org_id", "org_name", "device_type"],
        )

        # License metrics
        self._licenses_total = self._create_gauge(
            MetricName.ORG_LICENSES_TOTAL,
            "Total number of licenses",
            labelnames=["org_id", "org_name", "license_type", "status"],
        )

        self._licenses_expiring = self._create_gauge(
            MetricName.ORG_LICENSES_EXPIRING,
            "Number of licenses expiring within 30 days",
            labelnames=["org_id", "org_name", "license_type"],
        )

    async def collect(self) -> None:
        """Collect organization metrics."""
        try:
            # Get organizations
            if self.settings.org_id:
                # Single organization
                org = await asyncio.to_thread(
                    self.api.organizations.getOrganization,
                    self.settings.org_id,
                )
                organizations = [org]
            else:
                # All accessible organizations
                organizations = await asyncio.to_thread(
                    self.api.organizations.getOrganizations
                )

            # Collect metrics for each organization
            tasks = [
                self._collect_org_metrics(org)
                for org in organizations
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception:
            logger.exception("Failed to collect organization metrics")

    async def _collect_org_metrics(self, org: dict[str, Any]) -> None:
        """Collect metrics for a specific organization.

        Parameters
        ----------
        org : dict[str, Any]
            Organization data.

        """
        org_id = org["id"]
        org_name = org["name"]

        try:
            # Set organization info
            self._org_info.labels(
                org_id=org_id,
                org_name=org_name,
            ).info({
                "url": org.get("url", ""),
                "api_enabled": str(org.get("api", {}).get("enabled", False)),
            })

            # Collect various metrics concurrently
            await asyncio.gather(
                self._collect_api_metrics(org_id, org_name),
                self._collect_network_metrics(org_id, org_name),
                self._collect_device_metrics(org_id, org_name),
                self._collect_license_metrics(org_id, org_name),
                return_exceptions=True,
            )

        except Exception:
            logger.exception(
                "Failed to collect metrics for organization",
                org_id=org_id,
                org_name=org_name,
            )

    async def _collect_api_metrics(self, org_id: str, org_name: str) -> None:
        """Collect API usage metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            # Get API request stats
            api_requests = await asyncio.to_thread(
                self.api.organizations.getOrganizationApiRequests,
                org_id,
                total_pages="all",
            )

            if api_requests:
                # Sum up total requests
                total_requests = sum(req.get("total", 0) for req in api_requests)
                self._api_requests_total.labels(
                    org_id=org_id,
                    org_name=org_name,
                ).set(total_requests)

            # Note: Rate limit info would need to be extracted from response headers
            # For now, we'll set a placeholder
            self._api_rate_limit.labels(
                org_id=org_id,
                org_name=org_name,
            ).set(5)  # Default Meraki rate limit

        except Exception:
            logger.error(
                "Failed to collect API metrics",
                org_id=org_id,
                exc_info=True,
            )

    async def _collect_network_metrics(self, org_id: str, org_name: str) -> None:
        """Collect network metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            networks = await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )

            self._networks_total.labels(
                org_id=org_id,
                org_name=org_name,
            ).set(len(networks))

        except Exception:
            logger.error(
                "Failed to collect network metrics",
                org_id=org_id,
                exc_info=True,
            )

    async def _collect_device_metrics(self, org_id: str, org_name: str) -> None:
        """Collect device metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            devices = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevices,
                org_id,
                total_pages="all",
            )

            # Count devices by type
            device_counts: dict[str, int] = {}
            for device in devices:
                model = device.get("model", "")
                device_type = model[:2] if len(model) >= 2 else "Unknown"
                device_counts[device_type] = device_counts.get(device_type, 0) + 1

            # Set metrics for each device type
            for device_type, count in device_counts.items():
                self._devices_total.labels(
                    org_id=org_id,
                    org_name=org_name,
                    device_type=device_type,
                ).set(count)

        except Exception:
            logger.error(
                "Failed to collect device metrics",
                org_id=org_id,
                exc_info=True,
            )

    async def _collect_license_metrics(self, org_id: str, org_name: str) -> None:
        """Collect license metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            licenses = await asyncio.to_thread(
                self.api.organizations.getOrganizationLicenses,
                org_id,
                total_pages="all",
            )

            # Count licenses by type and status
            license_counts: dict[tuple[str, str], int] = {}
            expiring_counts: dict[str, int] = {}

            now = datetime.now(UTC)

            for license in licenses:
                license_type = license.get("licenseType", "Unknown")
                status = license.get("state", "Unknown")

                # Count by type and status
                key = (license_type, status)
                license_counts[key] = license_counts.get(key, 0) + 1

                # Check if expiring soon (within 30 days)
                expiration_date = license.get("expirationDate")
                if expiration_date and status == "active":
                    try:
                        exp_dt = datetime.fromisoformat(
                            expiration_date.replace("Z", "+00:00")
                        )
                        days_until_expiry = (exp_dt - now).days
                        if days_until_expiry <= 30:
                            expiring_counts[license_type] = (
                                expiring_counts.get(license_type, 0) + 1
                            )
                    except Exception:
                        pass

            # Set license count metrics
            for (license_type, status), count in license_counts.items():
                self._licenses_total.labels(
                    org_id=org_id,
                    org_name=org_name,
                    license_type=license_type,
                    status=status,
                ).set(count)

            # Set expiring license metrics
            for license_type, count in expiring_counts.items():
                self._licenses_expiring.labels(
                    org_id=org_id,
                    org_name=org_name,
                    license_type=license_type,
                ).set(count)

        except Exception:
            logger.error(
                "Failed to collect license metrics",
                org_id=org_id,
                exc_info=True,
            )
