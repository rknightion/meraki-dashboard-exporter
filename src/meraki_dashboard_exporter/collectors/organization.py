"""Organization-level metric collector."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..core.collector import MetricCollector
from ..core.constants import MetricName, UpdateTier
from ..core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class OrganizationCollector(MetricCollector):
    """Collector for organization-level metrics."""

    # Organization data updates at medium frequency
    update_tier: UpdateTier = UpdateTier.MEDIUM

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

    async def _collect_impl(self) -> None:
        """Collect organization metrics."""
        try:
            # Get organizations
            if self.settings.org_id:
                # Single organization
                logger.debug("Fetching single organization", org_id=self.settings.org_id)
                self._track_api_call("getOrganization")
                org = await asyncio.to_thread(
                    self.api.organizations.getOrganization,
                    self.settings.org_id,
                )
                organizations = [org]
                logger.debug(
                    "Successfully fetched organization", org_name=org.get("name", "unknown")
                )
            else:
                # All accessible organizations
                logger.debug("Fetching all organizations")
                self._track_api_call("getOrganizations")
                organizations = await asyncio.to_thread(self.api.organizations.getOrganizations)
                logger.debug("Successfully fetched organizations", count=len(organizations))

            # Collect metrics for each organization
            tasks = [self._collect_org_metrics(org) for org in organizations]
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
            if self._org_info:
                self._org_info.labels(
                    org_id=org_id,
                    org_name=org_name,
                ).info({
                    "url": org.get("url", ""),
                    "api_enabled": str(org.get("api", {}).get("enabled", False)),
                })
            else:
                logger.error("_org_info metric not initialized")

            # Collect various metrics sequentially with logging
            # Skip API metrics for now - it's often problematic
            # logger.info("Collecting API metrics", org_id=org_id)
            # await self._collect_api_metrics(org_id, org_name)

            logger.debug("Collecting network metrics", org_id=org_id)
            await self._collect_network_metrics(org_id, org_name)

            logger.debug("Collecting device metrics", org_id=org_id)
            await self._collect_device_metrics(org_id, org_name)

            logger.debug("Collecting license metrics", org_id=org_id)
            await self._collect_license_metrics(org_id, org_name)

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
            # Get API request stats with timeout
            logger.debug("Fetching API request stats", org_id=org_id)
            self._track_api_call("getOrganizationApiRequests")
            api_requests = await asyncio.wait_for(
                asyncio.to_thread(
                    self.api.organizations.getOrganizationApiRequests,
                    org_id,
                    total_pages="all",
                ),
                timeout=30.0,
            )
            logger.debug(
                "Successfully fetched API request stats",
                org_id=org_id,
                count=len(api_requests) if api_requests else 0,
            )

            if api_requests:
                # Sum up total requests
                total_requests = sum(req.get("total", 0) for req in api_requests)
                if self._api_requests_total:
                    self._api_requests_total.labels(
                        org_id=org_id,
                        org_name=org_name,
                    ).set(total_requests)
                else:
                    logger.error("_api_requests_total metric not initialized")
            else:
                # No API request data available
                logger.debug("No API request data available", org_id=org_id)

            # Note: Rate limit info would need to be extracted from response headers
            # For now, we'll set a placeholder
            if self._api_rate_limit:
                self._api_rate_limit.labels(
                    org_id=org_id,
                    org_name=org_name,
                ).set(5)  # Default Meraki rate limit

        except TimeoutError:
            logger.error(
                "Timeout collecting API metrics",
                org_id=org_id,
                org_name=org_name,
            )
        except Exception:
            logger.exception(
                "Failed to collect API metrics",
                org_id=org_id,
                org_name=org_name,
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
            logger.debug("Fetching organization networks", org_id=org_id)
            self._track_api_call("getOrganizationNetworks")
            networks = await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )
            logger.debug("Successfully fetched networks", org_id=org_id, count=len(networks))

            if self._networks_total:
                self._networks_total.labels(
                    org_id=org_id,
                    org_name=org_name,
                ).set(len(networks))
            else:
                logger.error("_networks_total metric not initialized")

        except Exception:
            logger.exception(
                "Failed to collect network metrics",
                org_id=org_id,
                org_name=org_name,
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
            logger.debug("Fetching organization devices", org_id=org_id)
            self._track_api_call("getOrganizationDevices")
            devices = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevices,
                org_id,
                total_pages="all",
            )
            logger.debug("Successfully fetched devices", org_id=org_id, count=len(devices))

            # Count devices by type
            device_counts: dict[str, int] = {}
            for device in devices:
                model = device.get("model", "")
                device_type = model[:2] if len(model) >= 2 else "Unknown"
                device_counts[device_type] = device_counts.get(device_type, 0) + 1

            # Set metrics for each device type
            for device_type, count in device_counts.items():
                if self._devices_total:
                    self._devices_total.labels(
                        org_id=org_id,
                        org_name=org_name,
                        device_type=device_type,
                    ).set(count)
                else:
                    logger.error("_devices_total metric not initialized")

        except Exception:
            logger.exception(
                "Failed to collect device metrics",
                org_id=org_id,
                org_name=org_name,
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
            # First check if organization uses per-device licensing
            # If not, try to get licensing overview instead
            licenses = []
            try:
                logger.debug("Fetching organization licenses", org_id=org_id)
                self._track_api_call("getOrganizationLicenses")
                licenses = await asyncio.to_thread(
                    self.api.organizations.getOrganizationLicenses,
                    org_id,
                    total_pages="all",
                )
                logger.debug("Successfully fetched licenses", org_id=org_id, count=len(licenses))
            except Exception as e:
                # Check if it's a licensing model issue
                if "does not support per-device licensing" in str(e):
                    logger.debug(
                        "Organization uses co-termination licensing model",
                        org_id=org_id,
                        org_name=org_name,
                    )
                    # Try to get licensing overview for co-termination model
                    try:
                        logger.debug("Fetching license overview", org_id=org_id)
                        self._track_api_call("getOrganizationLicensesOverview")
                        overview = await asyncio.wait_for(
                            asyncio.to_thread(
                                self.api.organizations.getOrganizationLicensesOverview,
                                org_id,
                            ),
                            timeout=30.0,
                        )
                        logger.debug("Successfully fetched license overview", org_id=org_id)
                        # Convert overview to a format we can process
                        if overview:
                            # Set metrics based on overview data
                            self._process_licensing_overview(org_id, org_name, overview)
                            return
                    except Exception:
                        logger.warning(
                            "Could not get licensing overview",
                            org_id=org_id,
                            org_name=org_name,
                        )
                    return
                else:
                    # Re-raise if it's a different error
                    raise

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
                    exp_dt = self._parse_meraki_date(expiration_date)
                    if exp_dt:
                        days_until_expiry = (exp_dt - now).days
                        if days_until_expiry <= 30:
                            expiring_counts[license_type] = expiring_counts.get(license_type, 0) + 1

            # Set license count metrics
            for (license_type, status), count in license_counts.items():
                if self._licenses_total:
                    self._licenses_total.labels(
                        org_id=org_id,
                        org_name=org_name,
                        license_type=license_type,
                        status=status,
                    ).set(count)
                else:
                    logger.error("_licenses_total metric not initialized")

            # Set expiring license metrics
            for license_type, count in expiring_counts.items():
                if self._licenses_expiring:
                    self._licenses_expiring.labels(
                        org_id=org_id,
                        org_name=org_name,
                        license_type=license_type,
                    ).set(count)
                else:
                    logger.error("_licenses_expiring metric not initialized")

        except Exception:
            logger.exception(
                "Failed to collect license metrics",
                org_id=org_id,
                org_name=org_name,
            )

    def _parse_meraki_date(self, date_str: str) -> datetime | None:
        """Parse Meraki date formats.

        Parameters
        ----------
        date_str : str
            Date string from Meraki API (e.g., "Mar 13, 2027 UTC" or ISO format).

        Returns
        -------
        datetime | None
            Parsed datetime or None if parsing failed.

        """
        if not date_str:
            return None

        try:
            # First try ISO format (e.g., "2027-03-13T00:00:00Z")
            if "T" in date_str or date_str.endswith("Z"):
                try:
                    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except ValueError:
                    # Not a valid ISO format, continue to other formats
                    pass

            # Try Meraki's human-readable format (e.g., "Mar 13, 2027 UTC")
            # Remove timezone suffix and parse
            date_str_clean = date_str.replace(" UTC", "").replace(" GMT", "").strip()
            # Handle both "Mar 13, 2027" and "March 13, 2027" formats
            for fmt in ["%b %d, %Y", "%B %d, %Y"]:
                try:
                    return datetime.strptime(date_str_clean, fmt).replace(tzinfo=UTC)
                except ValueError:
                    continue

            # If we get here, we couldn't parse the date
            raise ValueError(f"Unknown date format: {date_str}")

        except Exception as e:
            logger.warning(
                "Could not parse date",
                date_str=date_str,
                error=str(e),
            )
            return None

    def _process_licensing_overview(
        self, org_id: str, org_name: str, overview: dict[str, Any]
    ) -> None:
        """Process licensing overview for co-termination licensing model.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        overview : dict[str, Any]
            Licensing overview data.

        """
        # Extract data from overview
        status = overview.get("status", "Unknown")
        expiration_date = overview.get("expirationDate")

        # Set total licenses metric for co-termination model
        if self._licenses_total:
            self._licenses_total.labels(
                org_id=org_id,
                org_name=org_name,
                license_type="co-termination",
                status=status,
            ).set(1)  # Co-term is a single license
        else:
            logger.error("_licenses_total metric not initialized")

        # Check if expiring soon
        if expiration_date and status == "OK" and self._licenses_expiring:
            now = datetime.now(UTC)
            exp_dt = self._parse_meraki_date(expiration_date)
            if exp_dt:
                days_until_expiry = (exp_dt - now).days
                if days_until_expiry <= 30:
                    self._licenses_expiring.labels(
                        org_id=org_id,
                        org_name=org_name,
                        license_type="co-termination",
                    ).set(1)
                else:
                    self._licenses_expiring.labels(
                        org_id=org_id,
                        org_name=org_name,
                        license_type="co-termination",
                    ).set(0)
            else:
                # Set to 0 if we couldn't parse the date
                self._licenses_expiring.labels(
                    org_id=org_id,
                    org_name=org_name,
                    license_type="co-termination",
                ).set(0)
        elif not self._licenses_expiring:
            logger.error("_licenses_expiring metric not initialized")
