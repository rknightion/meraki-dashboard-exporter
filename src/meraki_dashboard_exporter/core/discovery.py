"""One-time discovery service for logging environment information."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..core.error_handling import validate_response_format
from ..core.logging import get_logger

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ..core.config import Settings

logger = get_logger(__name__)


class OrgResolutionError(RuntimeError):
    """Raised at startup when the single-organization contract cannot be satisfied.

    Either the API key sees no organizations, or it sees several while no
    ``org_id`` is configured (an ambiguous multi-org key). Raised before the
    exporter starts serving so the process fails fast (aborting startup) instead
    of silently polling an arbitrary organization. See ``resolve_org_id``.
    """


async def resolve_org_id(api: DashboardAPI, settings: Settings) -> str:
    """Resolve the single organization this exporter instance will poll (#585).

    Enforces the v1 single-org contract (one poller instance = one organization):

    - If ``settings.meraki.org_id`` is set, it is used as-is. Its existence is
      probed separately by :meth:`DiscoveryService.run_discovery`, which calls
      ``getOrganization`` on it, so no extra ``getOrganizations`` list call is
      made on the startup critical path here (and a correctly-pinned instance
      cannot crash-loop on a transient list-orgs failure).
    - If ``org_id`` is unset and the key sees exactly one org, that org is
      auto-selected and written back onto ``settings.meraki.org_id``.
    - If ``org_id`` is unset and the key sees several orgs, raise
      :class:`OrgResolutionError` listing the visible orgs and pointing at the
      sharding / HA guide and the Helm multi-instance example (one instance per
      org).

    Parameters
    ----------
    api : DashboardAPI
        The Meraki SDK client.
    settings : Settings
        Application settings. ``settings.meraki.org_id`` is mutated in place in
        the auto-select case so the rest of the app reads the resolved id.

    Returns
    -------
    str
        The resolved organization id.

    Raises
    ------
    OrgResolutionError
        If the single-org contract cannot be satisfied: the key sees no orgs, or
        it sees several while no ``org_id`` is configured.

    """
    configured = settings.meraki.org_id
    if configured:
        logger.info(
            "Using configured organization (single-org contract)",
            org_id=configured,
        )
        return configured

    organizations = await asyncio.to_thread(api.organizations.getOrganizations)
    organizations = validate_response_format(
        organizations, expected_type=list, operation="getOrganizations"
    )

    visible = [
        (str(org.get("id", "")), str(org.get("name", "unknown")))
        for org in organizations
        if org.get("id")
    ]

    if not visible:
        raise OrgResolutionError(
            "The Meraki API key can see no organizations. Check that the key is "
            "valid and has access to at least one organization."
        )

    if len(visible) == 1:
        org_id, org_name = visible[0]
        settings.meraki.org_id = org_id
        logger.info(
            "Auto-selected the only visible organization (single-org contract)",
            org_id=org_id,
            org_name=org_name,
        )
        return org_id

    org_lines = "\n".join(f"  - {org_id} ({org_name})" for org_id, org_name in visible)
    raise OrgResolutionError(
        "This API key can see multiple organizations, but each exporter instance "
        "must poll exactly one organization (the v1 single-org contract: 1 poller "
        "= 1 org).\n"
        "Set MERAKI_EXPORTER_MERAKI__ORG_ID to one of the visible organizations:\n"
        f"{org_lines}\n"
        "To monitor several organizations, run one exporter instance per org "
        "(shard by organization). See the sharding / HA guide "
        "(docs/scaling-guide.md) and the Helm chart's multi-instance example "
        "(charts/meraki-dashboard-exporter) for one-instance-per-org recipes."
    )


class DiscoveryService:
    """Service to perform one-time discovery and log environment information."""

    def __init__(self, api: DashboardAPI, settings: Settings) -> None:
        """Initialize discovery service."""
        self.api = api
        self.settings = settings

    async def run_discovery(self) -> dict[str, Any]:
        """Run discovery scan and return environment summary for startup logging."""
        summary: dict[str, Any] = {
            "organizations": [],
            "networks": {},
            "errors": [],
        }

        logger.debug("Starting Meraki environment discovery")

        try:
            # Get organizations
            if self.settings.meraki.org_id:
                org = await asyncio.to_thread(
                    self.api.organizations.getOrganization,
                    self.settings.meraki.org_id,
                )
                org = validate_response_format(org, expected_type=dict, operation="getOrganization")
                organizations = [org]
            else:
                organizations = await asyncio.to_thread(self.api.organizations.getOrganizations)
                organizations = validate_response_format(
                    organizations, expected_type=list, operation="getOrganizations"
                )

            summary["organizations"] = [
                {
                    "id": org.get("id", ""),
                    "name": org.get("name", "unknown"),
                }
                for org in organizations
            ]

            # Process each organization for network summaries
            for org in organizations:
                org_id = org.get("id", "")
                org_name = org.get("name", "unknown")
                if not org_id:
                    continue

                try:
                    # NOTE: This call deliberately bypasses the network filter.
                    # EnvironmentDiscovery emits a startup diagnostic listing
                    # every network in the org so operators can verify their
                    # filter rules. Routing through inventory.get_networks
                    # would hide excluded networks and defeat that purpose.
                    networks = await asyncio.to_thread(
                        self.api.organizations.getOrganizationNetworks,
                        org_id,
                        total_pages="all",
                    )
                    networks = validate_response_format(
                        networks, expected_type=list, operation="getOrganizationNetworks"
                    )

                    # Count by product type
                    product_counts: dict[str, int] = {}
                    for network in networks:
                        for product in network.get("productTypes", []):
                            product_counts[product] = product_counts.get(product, 0) + 1

                    summary["networks"][org_id] = {
                        "org_name": org_name,
                        "count": len(networks),
                        "product_types": product_counts,
                    }
                except Exception as e:
                    logger.warning(
                        "Failed to fetch networks during discovery",
                        org_id=org_id,
                        org_name=org_name,
                        error=str(e),
                    )
                    summary["errors"].append(f"{org_id}: networks_fetch_failed")

            logger.debug("Environment discovery completed")
            return summary

        except Exception as e:
            logger.warning("Failed to complete environment discovery", error=str(e))
            summary["errors"].append("discovery_failed")
            return summary
