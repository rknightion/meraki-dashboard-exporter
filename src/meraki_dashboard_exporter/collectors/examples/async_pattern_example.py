"""Example collector demonstrating standardized async patterns.

This example shows how to use the async utilities for consistent patterns.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.async_utils import (
    AsyncRetry,
    ManagedTaskGroup,
    chunked_async_iter,
    managed_resource,
    rate_limited_gather,
    safe_gather,
    with_timeout,
)
from ...core.collector import MetricCollector
from ...core.constants import UpdateTier
from ...core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class AsyncPatternExampleCollector(MetricCollector):
    """Example collector showing async pattern usage."""

    update_tier = UpdateTier.MEDIUM

    def _initialize_metrics(self) -> None:
        """Initialize example metrics."""
        self._example_gauge = self._create_gauge(
            "example_async_metric",
            "Example metric for async patterns",
            labelnames=["org_id", "network_id"],
        )

    async def _collect_impl(self) -> None:
        """Demonstrate async pattern usage."""
        # Example 1: Using ManagedTaskGroup for structured concurrency
        async with ManagedTaskGroup("org_collection") as task_group:
            organizations = await self._fetch_organizations()

            # Create tasks for each organization
            for org in organizations:
                await task_group.create_task(
                    self._collect_org_metrics(org),
                    name=f"org_{org['id']}",
                )

            # All tasks are automatically awaited when exiting context

        # Example 2: Using with_timeout for operations
        networks = await with_timeout(
            self._fetch_all_networks(),
            timeout=30.0,
            operation="fetch networks",
            default=[],
        )

        # Example 3: Using safe_gather for concurrent operations
        network_tasks = [
            self._collect_network_metrics(net)
            for net in networks[:10]  # Limit for example
        ]

        results = await safe_gather(
            *network_tasks,
            description="network metrics",
            log_errors=True,
        )

        # Example 4: Using rate_limited_gather with semaphore
        semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent

        device_tasks = [
            self._fetch_device_details(device_id) for device_id in ["device1", "device2", "device3"]
        ]

        device_results = await rate_limited_gather(
            device_tasks,
            semaphore,
            description="device fetches",
        )

        # Example 5: Using AsyncRetry for flaky operations
        retry = AsyncRetry(
            max_attempts=3,
            base_delay=2.0,
            retry_on=(ConnectionError, TimeoutError),
        )

        config_data = await retry.execute(
            lambda: self._fetch_configuration(),
            operation="fetch configuration",
        )

        # Example 6: Using chunked_async_iter for batch processing
        all_devices = ["device1", "device2", "device3", "device4", "device5"]

        async for device_chunk in chunked_async_iter(
            all_devices,
            chunk_size=2,
            delay_between_chunks=1.0,
        ):
            # Process each chunk
            chunk_tasks = [self._process_device(device_id) for device_id in device_chunk]
            await safe_gather(*chunk_tasks, description="device chunk")

        # Example 7: Using managed_resource for resource cleanup
        async with managed_resource(
            resource_factory=self._create_temp_connection,
            cleanup_func=self._close_temp_connection,
            resource_name="temp_connection",
        ) as connection:
            # Use the connection
            await self._use_connection(connection)

    async def _fetch_organizations(self) -> list[dict[str, Any]]:
        """Fetch organizations (mock implementation)."""
        await asyncio.sleep(0.1)  # Simulate API delay
        return [
            {"id": "org1", "name": "Organization 1"},
            {"id": "org2", "name": "Organization 2"},
        ]

    async def _collect_org_metrics(self, org: dict[str, Any]) -> None:
        """Collect metrics for an organization."""
        await asyncio.sleep(0.2)  # Simulate work
        logger.debug(f"Collected metrics for org {org['id']}")

    async def _fetch_all_networks(self) -> list[dict[str, Any]]:
        """Fetch all networks."""
        await asyncio.sleep(0.3)
        return [
            {"id": "net1", "name": "Network 1"},
            {"id": "net2", "name": "Network 2"},
        ]

    async def _collect_network_metrics(self, network: dict[str, Any]) -> None:
        """Collect metrics for a network."""
        await asyncio.sleep(0.1)
        self._example_gauge.labels(
            org_id="org1",
            network_id=network["id"],
        ).set(1)

    async def _fetch_device_details(self, device_id: str) -> dict[str, Any]:
        """Fetch device details."""
        await asyncio.sleep(0.1)
        return {"id": device_id, "status": "online"}

    async def _fetch_configuration(self) -> dict[str, Any]:
        """Fetch configuration (may fail)."""
        await asyncio.sleep(0.1)
        # Simulate occasional failure
        import random

        if random.random() < 0.3:
            raise ConnectionError("Simulated connection error")
        return {"config": "data"}

    async def _process_device(self, device_id: str) -> None:
        """Process a device."""
        await asyncio.sleep(0.05)
        logger.debug(f"Processed device {device_id}")

    async def _create_temp_connection(self) -> dict[str, Any]:
        """Create a temporary connection."""
        await asyncio.sleep(0.1)
        return {"connection_id": "temp123", "active": True}

    async def _close_temp_connection(self, connection: dict[str, Any]) -> None:
        """Close the temporary connection."""
        await asyncio.sleep(0.05)
        connection["active"] = False
        logger.debug(f"Closed connection {connection['connection_id']}")

    async def _use_connection(self, connection: dict[str, Any]) -> None:
        """Use the connection."""
        await asyncio.sleep(0.1)
        logger.debug(f"Using connection {connection['connection_id']}")


# Example usage in other collectors:

"""
# In organization.py or any collector:

from ..core.async_utils import ManagedTaskGroup, safe_gather, with_timeout

async def _collect_impl(self) -> None:
    # Use task group for organization collection
    async with ManagedTaskGroup("organization_metrics") as group:
        organizations = await self._fetch_organizations()

        for org in organizations:
            await group.create_task(
                self._collect_org_metrics(org["id"]),
                name=f"org_{org['id']}",
            )

    # Use with_timeout for potentially slow operations
    slow_data = await with_timeout(
        self._fetch_slow_data(),
        timeout=60.0,
        operation="fetch slow data",
        default={},
    )

    # Use safe_gather for concurrent API calls
    api_tasks = [
        self.api_helper.get_organization_networks(org_id),
        self.api_helper.get_organization_devices(org_id),
        self._fetch_licenses(org_id),
    ]

    results = await safe_gather(
        *api_tasks,
        description="organization data",
    )
"""
