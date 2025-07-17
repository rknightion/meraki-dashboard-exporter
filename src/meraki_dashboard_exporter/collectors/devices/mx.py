"""MX security appliance collector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.logging import get_logger
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class MXCollector(BaseDeviceCollector):
    """Collector for MX security appliance metrics."""

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect MX-specific metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with status_info added.

        """
        # Collect common metrics
        self.collect_common_metrics(device)

        # MX currently doesn't have specific metrics beyond common ones
        # Future MX-specific metrics can be added here
