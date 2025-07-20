"""Common API call patterns and helpers.

This module provides higher-level API client methods for common patterns,
reducing code duplication and ensuring consistent behavior across collectors.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, cast

from .error_handling import ErrorCategory, with_error_handling
from .logging import get_logger

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from .collector import MetricCollector

logger = get_logger(__name__)

T = TypeVar("T")


class APIHelper:
    """Helper class for common API call patterns."""

    def __init__(self, collector: MetricCollector) -> None:
        """Initialize API helper.

        Parameters
        ----------
        collector : MetricCollector
            The collector instance to use for API calls.

        """
        self.collector = collector
        self.api: DashboardAPI = collector.api
        self.settings = collector.settings

    @with_error_handling(
        operation="Fetch organizations",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def get_organizations(self) -> list[dict[str, Any]]:
        """Get all organizations or configured organization.

        Returns
        -------
        list[dict[str, Any]]
            List of organization dictionaries.

        """
        if self.collector.settings.meraki.org_id:
            # Single organization configured
            logger.debug(
                "Using configured organization", org_id=self.collector.settings.meraki.org_id
            )
            self.collector._track_api_call("getOrganization")
            org = await asyncio.to_thread(
                self.api.organizations.getOrganization,
                self.collector.settings.meraki.org_id,
            )
            return [org]
        else:
            # Fetch all organizations
            logger.debug("Fetching all organizations")
            self.collector._track_api_call("getOrganizations")
            orgs = await asyncio.to_thread(self.api.organizations.getOrganizations)
            logger.debug("Successfully fetched organizations", count=len(orgs))
            return cast(list[dict[str, Any]], orgs)

    @with_error_handling(
        operation="Fetch organization networks",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def get_organization_networks(
        self, org_id: str, product_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Get all networks for an organization, optionally filtered by product type.

        Parameters
        ----------
        org_id : str
            Organization ID.
        product_types : list[str] | None
            Optional list of product types to filter by (e.g., ["wireless", "switch"]).

        Returns
        -------
        list[dict[str, Any]]
            List of network dictionaries.

        """
        logger.debug("Fetching networks", org_id=org_id, product_types=product_types)
        self.collector._track_api_call("getOrganizationNetworks")
        networks = await asyncio.to_thread(
            self.api.organizations.getOrganizationNetworks,
            org_id,
            total_pages="all",
        )
        logger.debug("Successfully fetched networks", org_id=org_id, count=len(networks))

        # Filter by product types if specified
        if product_types:
            networks = [
                network
                for network in networks
                if any(pt in network.get("productTypes", []) for pt in product_types)
            ]
            logger.debug(
                "Filtered networks by product types",
                org_id=org_id,
                product_types=product_types,
                filtered_count=len(networks),
            )

        return cast(list[dict[str, Any]], networks)

    @with_error_handling(
        operation="Fetch organization devices",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def get_organization_devices(
        self,
        org_id: str,
        product_types: list[str] | None = None,
        models: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get all devices for an organization with optional filtering.

        Parameters
        ----------
        org_id : str
            Organization ID.
        product_types : list[str] | None
            Optional list of product types to filter by (e.g., ["sensor", "wireless"]).
        models : list[str] | None
            Optional list of models to filter by (e.g., ["MR", "MS"]).

        Returns
        -------
        list[dict[str, Any]]
            List of device dictionaries.

        """
        logger.debug(
            "Fetching devices",
            org_id=org_id,
            product_types=product_types,
            models=models,
        )
        self.collector._track_api_call("getOrganizationDevices")

        # Build API call parameters
        params: dict[str, Any] = {"total_pages": "all"}
        if product_types:
            params["productTypes"] = product_types

        devices: list[dict[str, Any]] = await asyncio.to_thread(
            self.api.organizations.getOrganizationDevices,
            org_id,
            **params,
        )
        logger.debug("Successfully fetched devices", org_id=org_id, count=len(devices))

        # Additional model filtering if specified
        if models:
            devices = [
                device
                for device in devices
                if any(device.get("model", "").startswith(model) for model in models)
            ]
            logger.debug(
                "Filtered devices by models",
                org_id=org_id,
                models=models,
                filtered_count=len(devices),
            )

        return devices

    async def process_in_batches(
        self,
        items: list[T],
        process_func: Callable[[T], Any],
        batch_size: int | None = None,
        description: str = "items",
    ) -> list[Any]:
        """Process items in batches to avoid overwhelming the API.

        Parameters
        ----------
        items : list[T]
            List of items to process.
        process_func : Callable[[T], Any]
            Async function to process each item.
        batch_size : int
            Number of items to process concurrently.
        description : str
            Description of items for logging.

        Returns
        -------
        list[Any]
            Results from processing all items.

        """
        results = []
        total_items = len(items)

        # Use configured batch size if not specified
        if batch_size is None:
            batch_size = self.settings.api.batch_size

        for i in range(0, total_items, batch_size):
            batch = items[i : i + batch_size]
            batch_end = min(i + batch_size, total_items)

            logger.debug(
                f"Processing batch of {description}",
                batch_start=i + 1,
                batch_end=batch_end,
                total=total_items,
            )

            # Create tasks for batch
            tasks = [process_func(item) for item in batch]

            # Process batch concurrently
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out exceptions but log them
            for idx, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(
                        f"Failed to process {description}",
                        error=str(result),
                        item_index=i + idx,
                    )
                else:
                    results.append(result)

        logger.debug(
            f"Completed batch processing of {description}",
            total_processed=total_items,
            successful=len(results),
            failed=total_items - len(results),
        )

        return results

    @with_error_handling(
        operation="Fetch time-based data",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def get_time_based_data(
        self,
        api_method: Callable[..., Any],
        method_name: str,
        timespan: int = 300,
        interval: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Fetch time-based data with standard parameters.

        Parameters
        ----------
        api_method : Callable
            The API method to call.
        method_name : str
            Name of the method for tracking.
        timespan : int
            Timespan in seconds (default: 300 for 5 minutes).
        interval : int | None
            Interval in seconds for aggregation.
        **kwargs : Any
            Additional arguments for the API method.

        Returns
        -------
        dict[str, Any] | list[dict[str, Any]]
            API response data.

        """
        logger.debug(
            f"Fetching time-based data: {method_name}",
            timespan=timespan,
            interval=interval,
            kwargs=kwargs,
        )
        self.collector._track_api_call(method_name)

        # Build parameters
        params = {"timespan": timespan}
        if interval is not None:
            params["interval"] = interval
        params.update(kwargs)

        response = await asyncio.to_thread(api_method, **params)

        # Handle wrapped responses
        if isinstance(response, dict) and "items" in response:
            data = response["items"]
            logger.debug(
                f"Successfully fetched time-based data: {method_name}",
                item_count=len(data) if isinstance(data, list) else 1,
                wrapped_response=True,
            )
            return cast(dict[str, Any] | list[dict[str, Any]], data)

        logger.debug(
            f"Successfully fetched time-based data: {method_name}",
            item_count=len(response) if isinstance(response, list) else 1,
            wrapped_response=False,
        )
        return cast(dict[str, Any] | list[dict[str, Any]], response)


def create_api_helper(collector: MetricCollector) -> APIHelper:
    """Create an API helper instance for a collector.

    Parameters
    ----------
    collector : MetricCollector
        The collector to create the helper for.

    Returns
    -------
    APIHelper
        Configured API helper instance.

    """
    return APIHelper(collector)
