"""License collector for organization licensing metrics."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ...core.label_helpers import create_org_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from .base import BaseOrganizationCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class LicenseCollector(BaseOrganizationCollector):
    """Collector for organization license metrics."""

    @log_api_call("getOrganizationLicensesOverview")
    async def _fetch_licenses_overview(self, org_id: str) -> dict[str, Any]:
        """Fetch organization licenses overview.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        dict[str, Any]
            Licenses overview data.

        """
        self._track_api_call("getOrganizationLicensesOverview")
        return await asyncio.to_thread(
            self.api.organizations.getOrganizationLicensesOverview,
            org_id,
        )

    @log_api_call("getOrganizationLicenses")
    async def _fetch_licenses(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch organization licenses.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of licenses.

        """
        self._track_api_call("getOrganizationLicenses")
        return await asyncio.to_thread(
            self.api.organizations.getOrganizationLicenses,
            org_id,
            total_pages="all",
        )

    async def collect(self, org_id: str, org_name: str) -> None:
        """Collect license metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        try:
            with LogContext(org_id=org_id, org_name=org_name):
                overview = await self._fetch_licenses_overview(org_id)

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
                licenses = await self._fetch_licenses(org_id)

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
        for (license_type, status), count in license_counts.items():
            # Create org labels using helper
            org_data = {"id": org_id, "name": org_name}
            labels = create_org_labels(
                org_data,
                license_type=license_type,
                status=status,
            )
            self._set_metric_value(
                "_licenses_total",
                labels,
                count,
            )

        # Set expiring license metrics
        # Set counts for all license types (0 if not expiring)
        all_types = {lt for lt, _ in license_counts.keys()}
        for license_type in all_types:
            count = expiring_counts.get(license_type, 0)
            # Create org labels using helper
            org_data = {"id": org_id, "name": org_name}
            labels = create_org_labels(
                org_data,
                license_type=license_type,
            )
            self._set_metric_value(
                "_licenses_expiring",
                labels,
                count,
            )

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
        if licensed_device_counts:
            # Process each device type in the licensed device counts
            for device_type, count in licensed_device_counts.items():
                # Create org labels using helper
                org_data = {"id": org_id, "name": org_name}
                labels = create_org_labels(
                    org_data,
                    license_type=device_type,
                    status=status,
                )
                self._set_metric_value(
                    "_licenses_total",
                    labels,
                    count,
                )
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
                if licensed_device_counts:
                    for device_type, count in licensed_device_counts.items():
                        if days_until_expiry <= 30:
                            # Create org labels using helper
                            org_data = {"id": org_id, "name": org_name}
                            labels = create_org_labels(
                                org_data,
                                license_type=device_type,
                            )
                            self._set_metric_value(
                                "_licenses_expiring",
                                labels,
                                count,
                            )
                        else:
                            # Create org labels using helper
                            org_data = {"id": org_id, "name": org_name}
                            labels = create_org_labels(
                                org_data,
                                license_type=device_type,
                            )
                            self._set_metric_value(
                                "_licenses_expiring",
                                labels,
                                0,
                            )
            else:
                logger.warning(
                    "Could not parse expiration date",
                    org_id=org_id,
                    expiration_date=expiration_date,
                )
