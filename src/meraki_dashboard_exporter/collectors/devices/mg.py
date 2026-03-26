"""MG cellular gateway collector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.logging import get_logger
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class MGCollector(BaseDeviceCollector):
    """Collector for MG cellular gateway metrics."""

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect MG-specific metrics.

        Common device metrics (device_up, status_info, uptime) are handled
        by DeviceCollector._collect_common_metrics() before this is called.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        # Future MG-specific metrics (cellular signal strength, data usage, etc.) can be added here
