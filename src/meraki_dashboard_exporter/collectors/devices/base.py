"""Base device collector with common functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.constants import DeviceStatus
from ...core.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class BaseDeviceCollector:
    """Base class for device-specific collectors."""

    def __init__(self, parent: Any) -> None:
        """Initialize base device collector.

        Parameters
        ----------
        parent : Any
            Parent DeviceCollector instance that has metrics defined.

        """
        self.parent = parent
        self.api = parent.api
        self.settings = parent.settings

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
