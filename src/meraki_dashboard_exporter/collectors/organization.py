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

        self._devices_by_model_total = self._create_gauge(
            "meraki_org_devices_by_model_total",
            "Total number of devices by specific model",
            labelnames=["org_id", "org_name", "model"],
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

        # Client metrics
        self._clients_total = self._create_gauge(
            "meraki_org_clients_total",
            "Total number of active clients in the organization (5-minute window from last complete interval)",
            labelnames=["org_id", "org_name"],
        )

        # Usage metrics (in KB for the 5-minute window)
        self._usage_total_kb = self._create_gauge(
            "meraki_org_usage_total_kb",
            "Total data usage in KB for the 5-minute window (last complete 5-min interval, e.g., 11:04 call returns 10:55-11:00)",
            labelnames=["org_id", "org_name"],
        )

        self._usage_downstream_kb = self._create_gauge(
            "meraki_org_usage_downstream_kb",
            "Downstream data usage in KB for the 5-minute window (last complete 5-min interval)",
            labelnames=["org_id", "org_name"],
        )

        self._usage_upstream_kb = self._create_gauge(
            "meraki_org_usage_upstream_kb",
            "Upstream data usage in KB for the 5-minute window (last complete 5-min interval)",
            labelnames=["org_id", "org_name"],
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

            logger.debug("Collecting device counts by model", org_id=org_id)
            await self._collect_device_counts_by_model(org_id, org_name)

            logger.debug("Collecting license metrics", org_id=org_id)
            await self._collect_license_metrics(org_id, org_name)

            logger.debug("Collecting client overview metrics", org_id=org_id)
            await self._collect_client_overview(org_id, org_name)

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
            logger.debug("Fetching API requests", org_id=org_id)
            self._track_api_call("getOrganizationApiRequests")
            api_requests = await asyncio.to_thread(
                self.api.organizations.getOrganizationApiRequests,
                org_id,
                total_pages="all",
                timespan=86400,  # Last 24 hours
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

                # Get rate limit if available
                # Rate limit is usually consistent across all requests
                if api_requests and api_requests[0].get("responseCodeCounts"):
                    # Look for 429 responses which indicate rate limiting
                    # This is a simplified approach - actual rate limit may vary
                    # TODO: Get actual rate limit from headers or API response
                    logger.debug(
                        "Successfully collected API metrics",
                        org_id=org_id,
                        total_requests=total_requests,
                    )
                else:
                    logger.debug("No API request data available", org_id=org_id)

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
            logger.debug("Fetching networks", org_id=org_id)
            self._track_api_call("getOrganizationNetworks")
            networks = await asyncio.to_thread(
                self.api.organizations.getOrganizationNetworks,
                org_id,
                total_pages="all",
            )

            # Count total networks
            total_networks = len(networks)
            if self._networks_total:
                self._networks_total.labels(
                    org_id=org_id,
                    org_name=org_name,
                ).set(total_networks)
                logger.debug(
                    "Successfully collected network metrics",
                    org_id=org_id,
                    total_networks=total_networks,
                )
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
            logger.debug("Fetching devices", org_id=org_id)
            self._track_api_call("getOrganizationDevices")
            devices = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevices,
                org_id,
                total_pages="all",
            )

            # Count devices by type
            device_counts: dict[str, int] = {}
            for device in devices:
                model = device.get("model", "")
                # Extract device type from model (e.g., "MS" from "MS210-8")
                device_type = model[:2] if len(model) >= 2 else "Unknown"
                device_counts[device_type] = device_counts.get(device_type, 0) + 1

            # Set metrics for each device type
            if self._devices_total:
                for device_type, count in device_counts.items():
                    self._devices_total.labels(
                        org_id=org_id,
                        org_name=org_name,
                        device_type=device_type,
                    ).set(count)
                    logger.debug(
                        "Set device count",
                        org_id=org_id,
                        device_type=device_type,
                        count=count,
                    )
            else:
                logger.error("_devices_total metric not initialized")

        except Exception:
            logger.exception(
                "Failed to collect device metrics",
                org_id=org_id,
                org_name=org_name,
            )

    async def _collect_device_counts_by_model(self, org_id: str, org_name: str) -> None:
        """Collect device counts by specific model.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            logger.debug("Fetching device counts by model", org_id=org_id)
            self._track_api_call("getOrganizationDevicesOverviewByModel")
            overview = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevicesOverviewByModel,
                org_id,
            )

            # Response can be either the direct object or wrapped in {"items": []}
            if isinstance(overview, dict) and "items" in overview:
                items = overview["items"]
            elif isinstance(overview, dict) and "counts" in overview:
                # Direct response format
                counts = overview.get("counts", [])
            else:
                logger.warning(
                    "Unexpected response format for device overview by model",
                    org_id=org_id,
                    response_type=type(overview).__name__,
                )
                return

            # Process counts
            if "counts" in locals():
                if self._devices_by_model_total:
                    for model_data in counts:
                        model = model_data.get("model", "Unknown")
                        count = model_data.get("total", 0)
                        self._devices_by_model_total.labels(
                            org_id=org_id,
                            org_name=org_name,
                            model=model,
                        ).set(count)
                        logger.debug(
                            "Set device count by model",
                            org_id=org_id,
                            model=model,
                            count=count,
                        )
                else:
                    logger.error("_devices_by_model_total metric not initialized")

        except Exception:
            logger.exception(
                "Failed to collect device counts by model",
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
            logger.debug("Fetching licensing overview", org_id=org_id)
            self._track_api_call("getOrganizationLicensesOverview")
            overview = await asyncio.to_thread(
                self.api.organizations.getOrganizationLicensesOverview,
                org_id,
            )

            # Check if this is co-termination or per-device licensing
            if overview.get("licensedDeviceCounts"):
                logger.debug(
                    "Organization uses co-termination licensing model",
                    org_id=org_id,
                    org_name=org_name,
                )
                # Process co-termination licensing
                self._process_licensing_overview(org_id, org_name, overview)
            else:
                # Per-device licensing
                logger.debug(
                    "Organization uses per-device licensing model",
                    org_id=org_id,
                    org_name=org_name,
                )
                # Fetch individual licenses
                self._track_api_call("getOrganizationLicenses")
                licenses = await asyncio.to_thread(
                    self.api.organizations.getOrganizationLicenses,
                    org_id,
                    total_pages="all",
                )

                if licenses:
                    self._process_per_device_licenses(org_id, org_name, licenses)
                else:
                    logger.warning("No license data available", org_id=org_id)

        except Exception as e:
            # Check if this is a 404 error (no licensing info)
            if "404" in str(e):
                logger.debug(
                    "No licensing information available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
            else:
                logger.exception(
                    "Failed to collect license metrics",
                    org_id=org_id,
                    org_name=org_name,
                )

    def _process_per_device_licenses(
        self, org_id: str, org_name: str, licenses: list[dict[str, Any]]
    ) -> None:
        """Process per-device licenses.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        licenses : list[dict[str, Any]]
            List of licenses.

        """
        # Count licenses by type and status
        license_counts: dict[tuple[str, str], int] = {}
        expiring_counts: dict[str, int] = {}

        now = datetime.now(UTC)

        for lic in licenses:
            license_type = lic.get("licenseType", "Unknown")
            status = lic.get("state", "Unknown")

            # Count by type and status
            key = (license_type, status)
            license_counts[key] = license_counts.get(key, 0) + 1

            # Check if expiring within 30 days
            expiration_date = lic.get("expirationDate")
            if expiration_date and status == "active":
                exp_dt = self._parse_meraki_date(expiration_date)
                if exp_dt:
                    days_until_expiry = (exp_dt - now).days
                    if days_until_expiry <= 30:
                        expiring_counts[license_type] = expiring_counts.get(license_type, 0) + 1

        # Set total license metrics
        if self._licenses_total:
            for (license_type, status), count in license_counts.items():
                self._licenses_total.labels(
                    org_id=org_id,
                    org_name=org_name,
                    license_type=license_type,
                    status=status,
                ).set(count)
                logger.debug(
                    "Set license count",
                    org_id=org_id,
                    license_type=license_type,
                    status=status,
                    count=count,
                )
        else:
            logger.error("_licenses_total metric not initialized")

        # Set expiring license metrics
        if self._licenses_expiring:
            # Set counts for all license types (0 if not expiring)
            all_types = {lt for lt, _ in license_counts.keys()}
            for license_type in all_types:
                count = expiring_counts.get(license_type, 0)
                self._licenses_expiring.labels(
                    org_id=org_id,
                    org_name=org_name,
                    license_type=license_type,
                ).set(count)
                logger.debug(
                    "Set expiring license count",
                    org_id=org_id,
                    license_type=license_type,
                    count=count,
                )
        else:
            logger.error("_licenses_expiring metric not initialized")

    def _parse_meraki_date(self, date_str: str) -> datetime | None:
        """Parse a date string from Meraki API.

        Parameters
        ----------
        date_str : str
            Date string in various Meraki formats.

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
        licensed_device_counts = overview.get("licensedDeviceCounts", {})

        # Set total licenses metric for each device type in co-termination model
        if self._licenses_total and licensed_device_counts:
            # Process each device type in the licensed device counts
            for device_type, count in licensed_device_counts.items():
                self._licenses_total.labels(
                    org_id=org_id,
                    org_name=org_name,
                    license_type=device_type,
                    status=status,
                ).set(count)
                logger.debug(
                    "Set license count",
                    org_id=org_id,
                    device_type=device_type,
                    count=count,
                    status=status,
                )
        elif not self._licenses_total:
            logger.error("_licenses_total metric not initialized")
        else:
            logger.warning(
                "No licensed device counts in overview",
                org_id=org_id,
                org_name=org_name,
            )

        # Check if expiring soon
        if expiration_date and status == "OK":
            now = datetime.now(UTC)
            exp_dt = self._parse_meraki_date(expiration_date)
            if exp_dt:
                days_until_expiry = (exp_dt - now).days

                # For co-termination, all licenses expire together
                # Set expiring metric for each device type if within 30 days
                if self._licenses_expiring and licensed_device_counts:
                    for device_type, count in licensed_device_counts.items():
                        if days_until_expiry <= 30:
                            self._licenses_expiring.labels(
                                org_id=org_id,
                                org_name=org_name,
                                license_type=device_type,
                            ).set(count)
                        else:
                            self._licenses_expiring.labels(
                                org_id=org_id,
                                org_name=org_name,
                                license_type=device_type,
                            ).set(0)
                        logger.debug(
                            "Set expiring license count",
                            org_id=org_id,
                            device_type=device_type,
                            count=count if days_until_expiry <= 30 else 0,
                            days_until_expiry=days_until_expiry,
                        )
            else:
                logger.warning(
                    "Could not parse expiration date",
                    org_id=org_id,
                    expiration_date=expiration_date,
                )

    async def _collect_client_overview(self, org_id: str, org_name: str) -> None:
        """Collect client overview metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            logger.debug("Fetching client overview", org_id=org_id)
            self._track_api_call("getOrganizationClientsOverview")

            # Use 5-minute timespan to get the last complete 5-minute window
            client_overview = await asyncio.to_thread(
                self.api.organizations.getOrganizationClientsOverview,
                org_id,
                timespan=300,  # 5 minutes
            )

            if client_overview:
                # Extract client count
                counts = client_overview.get("counts", {})
                total_clients = counts.get("total", 0)

                if self._clients_total:
                    self._clients_total.labels(
                        org_id=org_id,
                        org_name=org_name,
                    ).set(total_clients)
                    logger.debug(
                        "Set client count",
                        org_id=org_id,
                        total_clients=total_clients,
                    )
                else:
                    logger.error("_clients_total metric not initialized")

                # Extract usage data (in KB)
                usage = client_overview.get("usage", {})
                overall_usage = usage.get("overall", {})

                total_kb = overall_usage.get("total", 0)
                downstream_kb = overall_usage.get("downstream", 0)
                upstream_kb = overall_usage.get("upstream", 0)

                # Set usage metrics
                if self._usage_total_kb:
                    self._usage_total_kb.labels(
                        org_id=org_id,
                        org_name=org_name,
                    ).set(total_kb)
                else:
                    logger.error("_usage_total_kb metric not initialized")

                if self._usage_downstream_kb:
                    self._usage_downstream_kb.labels(
                        org_id=org_id,
                        org_name=org_name,
                    ).set(downstream_kb)
                else:
                    logger.error("_usage_downstream_kb metric not initialized")

                if self._usage_upstream_kb:
                    self._usage_upstream_kb.labels(
                        org_id=org_id,
                        org_name=org_name,
                    ).set(upstream_kb)
                else:
                    logger.error("_usage_upstream_kb metric not initialized")

                logger.debug(
                    "Successfully collected client overview metrics",
                    org_id=org_id,
                    total_clients=total_clients,
                    total_kb=total_kb,
                    downstream_kb=downstream_kb,
                    upstream_kb=upstream_kb,
                )
            else:
                logger.warning("No client overview data available", org_id=org_id)

        except Exception as e:
            # Check if this is a 404 error (endpoint might not be available)
            if "404" in str(e):
                logger.debug(
                    "Client overview API not available for organization",
                    org_id=org_id,
                    org_name=org_name,
                )
            else:
                logger.exception(
                    "Failed to collect client overview metrics",
                    org_id=org_id,
                    org_name=org_name,
                )
