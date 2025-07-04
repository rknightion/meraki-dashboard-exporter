"""Meraki MR (Wireless AP) metrics collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.logging import get_logger
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class MRCollector(BaseDeviceCollector):
    """Collector for Meraki MR (Wireless AP) devices."""

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect wireless AP metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Wireless device data.

        """
        serial = device["serial"]
        name = device.get("name", serial)
        model = device.get("model", "Unknown")
        network_id = device.get("networkId", "")

        try:
            # Get wireless status
            status = await asyncio.to_thread(
                self.api.wireless.getDeviceWirelessStatus,
                serial,
            )

            # Client count
            if "clientCount" in status:
                self.parent._ap_clients.labels(
                    serial=serial,
                    name=name,
                    model=model,
                    network_id=network_id,
                ).set(status["clientCount"])

            # Channel utilization
            if "basicServiceSets" in status:
                for bss in status["basicServiceSets"]:
                    band = bss.get("band", "")
                    channel = str(bss.get("channel", ""))
                    utilization = bss.get("utilization", 0)

                    self.parent._ap_channel_utilization.labels(
                        serial=serial,
                        name=name,
                        band=band,
                        channel=channel,
                    ).set(utilization)

        except Exception:
            logger.exception(
                "Failed to collect wireless metrics",
                serial=serial,
            )
