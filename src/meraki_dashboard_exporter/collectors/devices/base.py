"""Base device collector with common functionality."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from ...core.constants import DeviceStatus
from ...core.logging import get_logger

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ...core.config import Settings
    from ..device import DeviceCollector

logger = get_logger(__name__)


class BaseDeviceCollector(ABC):
    """Base class for device-specific collectors."""

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize base device collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance that has metrics defined.

        """
        self.parent = parent
        self.api: DashboardAPI = parent.api
        self.settings: Settings = parent.settings

    @abstractmethod
    async def collect(self, device: dict[str, Any]) -> None:
        """Collect device-specific metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with status_info added.

        """
        ...

    def collect_common_metrics(self, device: dict[str, Any]) -> None:
        """Collect common device metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with status_info added.

        """
        serial = device["serial"]
        name = device.get("name", serial)
        model = device.get("model", "Unknown")
        network_id = device.get("networkId", "")
        device_type = self._get_device_type(device)
        status_info = device.get("status_info", {})

        # Device up/down status
        status = status_info.get("status", DeviceStatus.OFFLINE)
        is_online = 1 if status == DeviceStatus.ONLINE else 0
        self.parent._device_up.labels(
            serial=serial,
            name=name,
            model=model,
            network_id=network_id,
            device_type=device_type,
        ).set(is_online)

        # Uptime
        if "uptimeInSeconds" in device:
            # Check if uptime metric exists (it was removed in a previous cleanup)
            if hasattr(self.parent, "_device_uptime"):
                self.parent._device_uptime.labels(
                    serial=serial,
                    name=name,
                    model=model,
                    network_id=network_id,
                    device_type=device_type,
                ).set(device["uptimeInSeconds"])

    def _get_device_type(self, device: dict[str, Any]) -> str:
        """Get device type from device model.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        Returns
        -------
        str
            Device type.

        """
        model = device.get("model", "")
        return model[:2] if len(model) >= 2 else "Unknown"

    def _track_api_call(self, method_name: str) -> None:
        """Track API call in parent collector.

        Parameters
        ----------
        method_name : str
            Name of the API method being called.

        """
        if hasattr(self.parent, "_track_api_call"):
            self.parent._track_api_call(method_name)

    async def collect_memory_metrics(self, org_id: str, device_lookup: dict[str, dict[str, Any]] | None = None) -> None:
        """Collect memory metrics for all devices in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        device_lookup : dict[str, dict[str, Any]] | None
            Optional device lookup table. If not provided, uses parent's _device_lookup.

        """
        try:
            # Use a short timespan (300 seconds = 5 minutes) with 300 second interval
            # This gives us the most recent memory data block
            logger.debug("Fetching device memory usage history", org_id=org_id)
            self._track_api_call("getOrganizationDevicesSystemMemoryUsageHistoryByInterval")

            memory_response = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval,
                org_id,
                timespan=300,
                interval=300,
            )

            # Handle different API response formats
            if isinstance(memory_response, dict) and "items" in memory_response:
                memory_data = memory_response["items"]
            elif isinstance(memory_response, list):
                memory_data = memory_response
            else:
                logger.warning(
                    "Unexpected memory data format",
                    org_id=org_id,
                    response_type=type(memory_response).__name__,
                )
                memory_data = []

            logger.debug(
                "Successfully fetched memory data",
                org_id=org_id,
                device_count=len(memory_data) if memory_data else 0,
            )

            # Process each device's memory data
            for device_data in memory_data:
                serial = device_data.get("serial", "")
                name = device_data.get("name", serial)
                model = device_data.get("model", "Unknown")
                network_id = device_data.get("network", {}).get("id", "")
                device_type = model[:2] if len(model) >= 2 else "Unknown"

                # Total provisioned memory
                provisioned_kb = device_data.get("provisioned")
                if provisioned_kb and provisioned_kb > 0:
                    self._set_metric_value(
                        "_device_memory_total_bytes",
                        {
                            "serial": serial,
                            "name": name,
                            "model": model,
                            "network_id": network_id,
                            "device_type": device_type,
                        },
                        provisioned_kb * 1024,  # Convert KB to bytes
                    )

                # Get the most recent interval data
                intervals = device_data.get("intervals", [])
                if intervals:
                    # Use the first interval (most recent)
                    latest_interval = intervals[0]
                    memory_stats = latest_interval.get("memory", {})

                    # Used memory stats
                    used_stats = memory_stats.get("used", {})
                    if used_stats:
                        # Maximum used
                        if "maximum" in used_stats:
                            self._set_metric_value(
                                "_device_memory_used_bytes",
                                {
                                    "serial": serial,
                                    "name": name,
                                    "model": model,
                                    "network_id": network_id,
                                    "device_type": device_type,
                                    "stat": "max",
                                },
                                used_stats["maximum"] * 1024,  # Convert KB to bytes
                            )

                        # Memory usage percentage (use maximum percentage)
                        percentages = used_stats.get("percentages", {})
                        if "maximum" in percentages:
                            self._set_metric_value(
                                "_device_memory_usage_percent",
                                {
                                    "serial": serial,
                                    "name": name,
                                    "model": model,
                                    "network_id": network_id,
                                    "device_type": device_type,
                                },
                                percentages["maximum"],
                            )

                    # Free memory stats
                    free_stats = memory_stats.get("free", {})
                    if free_stats:
                        # Minimum free
                        if "minimum" in free_stats:
                            self._set_metric_value(
                                "_device_memory_free_bytes",
                                {
                                    "serial": serial,
                                    "name": name,
                                    "model": model,
                                    "network_id": network_id,
                                    "device_type": device_type,
                                    "stat": "min",
                                },
                                free_stats["minimum"] * 1024,  # Convert KB to bytes
                            )

        except Exception:
            logger.exception(
                "Failed to collect memory metrics",
                org_id=org_id,
            )
    
    def _set_metric_value(
        self, metric_name: str, labels: dict[str, str], value: float | None
    ) -> None:
        """Set a metric value through parent collector.
        
        Parameters
        ----------
        metric_name : str
            Name of the metric attribute.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float | None
            Value to set. If None, the metric will not be updated.
            
        """
        if self.parent and hasattr(self.parent, "_set_metric_value"):
            self.parent._set_metric_value(metric_name, labels, value)
