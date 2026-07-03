"""License collector for organization licensing metrics."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from ...core.constants.api_constants import LicenseState
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_org_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.scheduler import EndpointGroupName
from .base import BaseOrganizationCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# The licenses-overview ``states`` counts are org-wide aggregates by license
# state with no per-device-type breakdown, so state-derived series carry this
# bounded sentinel as their ``license_type`` label (used for subscription and
# state-based per-device licensing orgs - #516).
_AGGREGATE_LICENSE_TYPE = "All"


class LicenseCollector(BaseOrganizationCollector):
    """Collector for organization license metrics."""

    @log_api_call("getOrganizationLicensesOverview")
    async def _fetch_licenses_overview(self, org_id: str) -> dict[str, Any] | None:
        """Fetch organization licenses overview.

        Uses inventory cache with 30-minute TTL for efficiency since
        license data rarely changes.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        dict[str, Any] | None
            Licenses overview data, or ``None`` when the fetch failed (only
            possible via the inventory-cached path, which swallows errors so
            a transient failure can be distinguished from a legitimately
            empty overview - see F-100).

        """
        # Use inventory cache if available (30-min TTL for licenses)
        if self.inventory:
            return await self.inventory.get_licenses_overview(org_id)

        # Fallback to direct API call
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationLicensesOverview,
            org_id,
        )
        return cast(
            dict[str, Any],
            validate_response_format(
                response,
                expected_type=dict,
                operation="getOrganizationLicensesOverview",
            ),
        )

    @log_api_call("getOrganizationLicenses")
    async def _fetch_licenses(self, org_id: str) -> list[dict[str, Any]] | None:
        """Fetch organization licenses (per-device licensing model).

        Uses inventory cache with the same 30-minute TTL as the licenses
        overview for efficiency, since license data rarely changes (F-102) -
        previously this full-list fetch ran uncached on every collection
        cycle.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]] | None
            List of licenses, or ``None`` when the fetch failed (only
            possible via the inventory-cached path).

        """
        # Use inventory cache if available (30-min TTL, mirrors the overview)
        if self.inventory:
            return await self.inventory.get_licenses(org_id)

        # Fallback to direct API call
        response = await asyncio.to_thread(
            self.api.organizations.getOrganizationLicenses,
            org_id,
            total_pages="all",
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationLicenses",
            ),
        )

    @with_error_handling(
        operation="Collect license metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect(self, org_id: str, org_name: str) -> bool:
        """Collect license metrics.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        Returns
        -------
        bool
            ``True`` on success, on a deliberately-skipped cycle (transient
            inventory-cached fetch failure), or when the endpoint is
            unavailable for this org (404). On a real (non-404) failure the
            error is re-raised so the ``with_error_handling`` decorator can
            retry rate limits and then swallow it (returning ``None``); the
            parent coordinator treats any non-``True`` result as a failure so
            it is counted by ``OrgHealthTracker`` (F-172).

        """
        if not self.parent._should_run_group(EndpointGroupName.ORG_LICENSES):
            return True

        try:
            with LogContext(org_id=org_id, org_name=org_name):
                overview = await self._fetch_licenses_overview(org_id)

            # A None overview means the fetch itself failed (e.g. transient
            # 429/500) - distinct from a legitimately empty {} response.
            # Skip this cycle rather than misrouting to the per-device
            # getOrganizationLicenses call, which co-term orgs don't support
            # (F-100).
            if overview is None:
                logger.debug(
                    "Licenses overview fetch failed; skipping license metrics this cycle",
                    org_id=org_id,
                    org_name=org_name,
                )
                return True

            # Overview fetch succeeded — record the group ran so gating stretches.
            self.parent._mark_group_ran(EndpointGroupName.ORG_LICENSES)

            # Check if this is co-termination or per-device licensing
            if overview.get("licensedDeviceCounts"):
                logger.debug(
                    "Organization uses co-termination licensing model",
                    org_id=org_id,
                    org_name=org_name,
                )
                # Process co-termination licensing
                self._process_licensing_overview(org_id, org_name, overview)
            elif overview.get("states"):
                # No licensedDeviceCounts but the overview carries its own
                # per-state license counts. This covers both per-device and
                # subscription licensing. Subscription orgs 400 on
                # getOrganizationLicenses ("does not support per-device
                # licensing"), so preferring the overview's own state counts
                # avoids the unsupported call entirely and keeps the org
                # healthy rather than permanently red (#516, F-100 sibling).
                logger.debug(
                    "Organization uses subscription/per-device licensing; "
                    "using overview state counts",
                    org_id=org_id,
                    org_name=org_name,
                )
                self._process_licensing_states(org_id, org_name, overview["states"])
            else:
                # Per-device licensing without state counts in the overview:
                # fetch the full per-device license list.
                logger.debug(
                    "Organization uses per-device licensing model",
                    org_id=org_id,
                    org_name=org_name,
                )
                # Fetch individual licenses
                licenses = await self._fetch_licenses(org_id)

                if licenses is None:
                    logger.debug(
                        "Licenses fetch failed; skipping license metrics this cycle",
                        org_id=org_id,
                        org_name=org_name,
                    )
                elif licenses:
                    self._process_per_device_licenses(org_id, org_name, licenses)
                else:
                    logger.warning("No license data available", org_id=org_id)

            return True

        except Exception as e:
            # A 404 means the licensing endpoint isn't available for this org;
            # a 400 (or an explicit "does not support" message) means the org
            # uses a licensing model that doesn't support the per-device
            # endpoint (e.g. subscription licensing). Both are soft-skips, not
            # failures - otherwise a healthy subscription org would be stuck at
            # org_collection_status=0 forever (#516).
            err = str(e)
            if "404" in err or "400" in err or "does not support" in err.lower():
                logger.debug(
                    "Licensing endpoint unavailable/unsupported for organization; "
                    "soft-skipping license metrics this cycle",
                    org_id=org_id,
                    org_name=org_name,
                )
                return True
            raise  # Let decorator handle other errors (retry + swallow)

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
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.ORG_LICENSES)

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

            # Check if expiring within 30 days. Include both 'active' and
            # 'expiring' states - the Meraki API itself moves a license to
            # state 'expiring' as it approaches expiration, and excluding
            # that state undercounts the gauge (F-097).
            expiration_date = lic.get("expirationDate")
            if expiration_date and status in {LicenseState.ACTIVE, LicenseState.EXPIRING}:
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
                ttl_seconds=ttl,
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
                ttl_seconds=ttl,
            )

    def _process_licensing_states(self, org_id: str, org_name: str, states: dict[str, Any]) -> None:
        """Process the licenses-overview ``states`` counts.

        The ``states`` object (``getOrganizationLicensesOverview``) reports
        org-wide license counts by state (``active``, ``expiring``,
        ``expired``, ``unused`` ...) with no per-device-type breakdown. This
        is the co-term/subscription-agnostic source used when the overview
        carries no ``licensedDeviceCounts`` - notably subscription-licensing
        orgs, which do not support the per-device ``getOrganizationLicenses``
        endpoint (#516).

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        states : dict[str, Any]
            The ``states`` object from the licenses overview.

        """
        org_data = {"id": org_id, "name": org_name}
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.ORG_LICENSES)

        # One `_licenses_total` series per state, keyed by the aggregate
        # sentinel license_type since states carry no per-type breakdown.
        for state_name, state_data in states.items():
            count = self._extract_state_count(state_data)
            if count is None:
                continue
            labels = create_org_labels(
                org_data,
                license_type=_AGGREGATE_LICENSE_TYPE,
                status=state_name,
            )
            self._set_metric_value("_licenses_total", labels, count, ttl_seconds=ttl)

        # Expiring gauge sourced from states.expiring.count (Meraki's own
        # expiring bucket), mirroring the co-term/per-device expiring metric.
        expiring_count = self._extract_state_count(states.get("expiring"))
        labels = create_org_labels(
            org_data,
            license_type=_AGGREGATE_LICENSE_TYPE,
        )
        self._set_metric_value("_licenses_expiring", labels, expiring_count or 0, ttl_seconds=ttl)

    @staticmethod
    def _extract_state_count(state_data: Any) -> int | None:
        """Extract a ``count`` integer from a licenses-overview state entry.

        Each state entry is normally a dict with a ``count`` key; guard
        against unexpected shapes (bare ints or missing counts) so a single
        malformed state cannot break the whole emission.

        Parameters
        ----------
        state_data : Any
            A single value from the overview ``states`` object.

        Returns
        -------
        int | None
            The license count, or ``None`` when no numeric count is present.

        """
        if isinstance(state_data, dict):
            count = state_data.get("count")
        elif isinstance(state_data, (int, float)) and not isinstance(state_data, bool):
            count = state_data
        else:
            count = None
        return (
            int(count) if isinstance(count, (int, float)) and not isinstance(count, bool) else None
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
        ttl = self.parent._group_ttl_seconds(EndpointGroupName.ORG_LICENSES)
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
                    ttl_seconds=ttl,
                )
        else:
            logger.warning(
                "No licensed device counts in overview",
                org_id=org_id,
                org_name=org_name,
            )

        # Check if expiring soon. Evaluate regardless of overall co-term
        # `status` - gating on status == "OK" meant an org reported in any
        # other status (e.g. "EXPIRED") never had its expiring gauge
        # updated, leaving it stale or absent (F-097).
        if expiration_date:
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
                                ttl_seconds=ttl,
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
                                ttl_seconds=ttl,
                            )
            else:
                logger.warning(
                    "Could not parse expiration date",
                    org_id=org_id,
                    expiration_date=expiration_date,
                )
