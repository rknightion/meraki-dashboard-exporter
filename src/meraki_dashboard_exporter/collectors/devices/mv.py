"""MV security camera collector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.logging import get_logger
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class MVCollector(BaseDeviceCollector):
    """Collector for MV security camera metrics."""

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect MV-specific metrics.

        Common device metrics (device_up, status_info, uptime) are handled
        by DeviceCollector._collect_common_metrics() before this is called.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        # Future MV-specific metrics (video quality, storage usage, etc.) can be added here
