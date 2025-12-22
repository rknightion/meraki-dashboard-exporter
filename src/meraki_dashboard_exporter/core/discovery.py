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
