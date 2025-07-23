"""Base device collector with common functionality."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from ...core.constants import DeviceStatus
from ...core.error_handling import ErrorCategory, with_error_handling
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext

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
        status_info = device.get("status_info", {})
        status = status_info.get("status", DeviceStatus.OFFLINE)
        is_online = 1 if status == DeviceStatus.ONLINE else 0

        # Extract org info from device data
        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)

        # Create standard device labels
        labels = create_device_labels(device, org_id=org_id, org_name=org_name)

        logger.debug(
            "Setting device status metric",
            serial=labels["serial"],
            name=labels["name"],
            model=labels["model"],
            device_type=labels["device_type"],
            status=status,
            is_online=is_online,
        )

        self.parent._device_up.labels(**labels).set(is_online)

        # Uptime
        if "uptimeInSeconds" in device:
            # Check if uptime metric exists (it was removed in a previous cleanup)
            if hasattr(self.parent, "_device_uptime"):
                logger.debug(
                    "Setting device uptime metric",
                    serial=labels["serial"],
                    uptime_seconds=device["uptimeInSeconds"],
                )
                self.parent._device_uptime.labels(**labels).set(device["uptimeInSeconds"])

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
        device_type = model[:2] if len(model) >= 2 else "Unknown"

        if device_type == "Unknown":
            logger.warning(
                "Unable to determine device type from model",
                model=model,
                serial=device.get("serial", "unknown"),
            )

        return device_type

    def _track_api_call(self, method_name: str) -> None:
        """Track API call in parent collector.

        Parameters
        ----------
        method_name : str
            Name of the API method being called.

        """
        if hasattr(self.parent, "_track_api_call"):
            self.parent._track_api_call(method_name)

    @log_api_call("getOrganizationDevicesSystemMemoryUsageHistoryByInterval")
    @with_error_handling(
        operation="Collect device memory metrics",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_memory_metrics(
        self, org_id: str, org_name: str, device_lookup: dict[str, dict[str, Any]] | None = None
    ) -> None:
        """Collect memory metrics for all devices in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]] | None
            Optional device lookup table. If not provided, uses parent's _device_lookup.

        """
        try:
            # Use a short timespan (300 seconds = 5 minutes) with 300 second interval
            # This gives us the most recent memory data block
            with LogContext(org_id=org_id):
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

            if memory_data:
                logger.debug(
                    "Processing memory data for devices",
                    org_id=org_id,
                    device_count=len(memory_data),
                )

            # Process each device's memory data
            for device_data in memory_data:
                # Add org info to device data for label creation
                device_data["orgId"] = org_id
                device_data["orgName"] = org_name

                # Extract network info from nested structure
                network_info = device_data.get("network", {})
                device_data["networkId"] = network_info.get("id", "")
                device_data["networkName"] = network_info.get("name", device_data["networkId"])

                # Create standard device labels
                labels = create_device_labels(device_data, org_id=org_id, org_name=org_name)

                # Total provisioned memory
                provisioned_kb = device_data.get("provisioned")
                if provisioned_kb and provisioned_kb > 0:
                    self._set_metric_value(
                        "_device_memory_total_bytes",
                        labels,
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
                            # Create labels with stat
                            used_labels = create_device_labels(
                                device_data, org_id=org_id, org_name=org_name, stat="max"
                            )
                            self._set_metric_value(
                                "_device_memory_used_bytes",
                                used_labels,
                                used_stats["maximum"] * 1024,  # Convert KB to bytes
                            )

                        # Memory usage percentage (use maximum percentage)
                        percentages = used_stats.get("percentages", {})
                        if "maximum" in percentages:
                            self._set_metric_value(
                                "_device_memory_usage_percent",
                                labels,
                                percentages["maximum"],
                            )

                    # Free memory stats
                    free_stats = memory_stats.get("free", {})
                    if free_stats:
                        # Minimum free
                        if "minimum" in free_stats:
                            # Create labels with stat
                            free_labels = create_device_labels(
                                device_data, org_id=org_id, org_name=org_name, stat="min"
                            )
                            self._set_metric_value(
                                "_device_memory_free_bytes",
                                free_labels,
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
