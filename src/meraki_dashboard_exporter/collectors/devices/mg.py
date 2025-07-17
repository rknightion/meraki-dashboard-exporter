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

        Parameters
        ----------
        device : dict[str, Any]
            Device data with status_info added.

        """
        # Collect common metrics
        self.collect_common_metrics(device)

        # MG currently doesn't have specific metrics beyond common ones
        # Future MG-specific metrics (cellular signal strength, data usage, etc.) can be added here
