"""One-time discovery service for logging environment information."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

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

    async def run_discovery(self) -> None:
        """Run discovery scan and log environment information at INFO level."""
        logger.info("Starting Meraki environment discovery")

        try:
            # Get organizations
            if self.settings.org_id:
                logger.info("Configured for single organization", org_id=self.settings.org_id)
                org = await asyncio.to_thread(
                    self.api.organizations.getOrganization,
                    self.settings.org_id,
                )
                organizations = [org]
            else:
                organizations = await asyncio.to_thread(self.api.organizations.getOrganizations)
                logger.info(
                    "Discovered organizations",
                    count=len(organizations),
                    org_names=[org.get("name", "unknown") for org in organizations],
                )

            # Process each organization
            for org in organizations:
                org_id = org["id"]
                org_name = org.get("name", "unknown")

                # Log organization info
                logger.info(
                    "Organization details",
                    org_id=org_id,
                    org_name=org_name,
                    url=org.get("url", ""),
                )

                # Check licensing model
                try:
                    licenses = await asyncio.to_thread(
                        self.api.organizations.getOrganizationLicenses,
                        org_id,
                        total_pages="all",
                    )
                    logger.info(
                        "Organization uses per-device licensing",
                        org_name=org_name,
                        license_count=len(licenses),
                    )
                except Exception as e:
                    if "does not support per-device licensing" in str(e):
                        logger.info(
                            "Organization uses co-termination licensing model",
                            org_name=org_name,
                        )

                # Get networks
                try:
                    networks = await asyncio.to_thread(
                        self.api.organizations.getOrganizationNetworks,
                        org_id,
                        total_pages="all",
                    )

                    # Count by product type
                    product_counts: dict[str, int] = {}
                    for network in networks:
                        for product in network.get("productTypes", []):
                            product_counts[product] = product_counts.get(product, 0) + 1

                    logger.info(
                        "Network summary",
                        org_name=org_name,
                        total_networks=len(networks),
                        product_types=product_counts,
                    )
                except Exception:
                    logger.exception("Failed to fetch networks", org_name=org_name)

                # Get devices
                try:
                    devices = await asyncio.to_thread(
                        self.api.organizations.getOrganizationDevices,
                        org_id,
                        total_pages="all",
                    )

                    # Count by model prefix
                    device_counts: dict[str, int] = {}
                    for device in devices:
                        model = device.get("model", "unknown")
                        prefix = model[:2] if len(model) >= 2 else "unknown"
                        device_counts[prefix] = device_counts.get(prefix, 0) + 1

                    logger.info(
                        "Device summary",
                        org_name=org_name,
                        total_devices=len(devices),
                        device_types=device_counts,
                    )
                except Exception:
                    logger.exception("Failed to fetch devices", org_name=org_name)

                # Check alerts API availability
                try:
                    alerts = await asyncio.to_thread(
                        self.api.organizations.getOrganizationAssuranceAlerts,
                        org_id,
                        total_pages="all",
                    )
                    active_alerts = [
                        a for a in alerts if not a.get("dismissedAt") and not a.get("resolvedAt")
                    ]
                    logger.info(
                        "Assurance alerts API available",
                        org_name=org_name,
                        total_alerts=len(alerts),
                        active_alerts=len(active_alerts),
                    )
                except Exception as e:
                    if "404" in str(e):
                        logger.info(
                            "Assurance alerts API not available",
                            org_name=org_name,
                        )
                    else:
                        logger.debug(
                            "Failed to check alerts API",
                            org_name=org_name,
                            error=str(e),
                        )

            # Log collector configuration
            logger.info(
                "Collector configuration",
                enabled_device_types=self.settings.device_types,
                fast_update_interval=self.settings.fast_update_interval,
                medium_update_interval=self.settings.medium_update_interval,
            )

            logger.info("Environment discovery completed")

        except Exception:
            logger.exception("Failed to complete environment discovery")
