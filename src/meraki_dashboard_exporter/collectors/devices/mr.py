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
            # Get wireless status with timeout
            logger.debug(
                "Fetching wireless status",
                serial=serial,
                name=name,
            )
            self.parent._track_api_call("getDeviceWirelessStatus")

            try:
                status = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.api.wireless.getDeviceWirelessStatus,
                        serial,
                    ),
                    timeout=30.0,  # 10 second timeout
                )
            except TimeoutError:
                logger.error(
                    "Timeout fetching wireless status",
                    serial=serial,
                    name=name,
                )
                return

            logger.debug(
                "Successfully fetched wireless status",
                serial=serial,
            )

            # Client count
            if "clientCount" in status:
                self.parent._ap_clients.labels(
                    serial=serial,
                    name=name,
                    model=model,
                    network_id=network_id,
                ).set(status["clientCount"])

            # Get connection stats (30 minute window)
            await self._collect_connection_stats(serial, name, model, network_id)

        except Exception:
            logger.exception(
                "Failed to collect wireless metrics",
                serial=serial,
            )

    async def _collect_connection_stats(
        self, serial: str, name: str, model: str, network_id: str
    ) -> None:
        """Collect wireless connection statistics for the device.

        Parameters
        ----------
        serial : str
            Device serial number.
        name : str
            Device name.
        model : str
            Device model.
        network_id : str
            Network ID.

        """
        try:
            logger.debug(
                "Fetching connection stats",
                serial=serial,
                name=name,
            )

            # Track API call
            self.parent._track_api_call("getDeviceWirelessConnectionStats")

            # Use 30 minute (1800 second) timespan as minimum
            connection_stats = await asyncio.wait_for(
                asyncio.to_thread(
                    self.api.wireless.getDeviceWirelessConnectionStats,
                    serial,
                    timespan=1800,  # 30 minutes
                ),
                timeout=30.0,  # 10 second timeout
            )

            # Handle empty response (no data in timespan)
            if not connection_stats or "connectionStats" not in connection_stats:
                logger.debug(
                    "No connection stats data available",
                    serial=serial,
                    timespan="30m",
                )
                # Set all stats to 0 when no data
                for stat_type in ("assoc", "auth", "dhcp", "dns", "success"):
                    self.parent._ap_connection_stats.labels(
                        serial=serial,
                        name=name,
                        model=model,
                        network_id=network_id,
                        stat_type=stat_type,
                    ).set(0)
                return

            stats = connection_stats.get("connectionStats", {})

            # Set metrics for each connection stat type
            for stat_type, value in stats.items():
                if stat_type in {"assoc", "auth", "dhcp", "dns", "success"}:
                    self.parent._ap_connection_stats.labels(
                        serial=serial,
                        name=name,
                        model=model,
                        network_id=network_id,
                        stat_type=stat_type,
                    ).set(value)

            logger.debug(
                "Successfully collected connection stats",
                serial=serial,
                stats=stats,
            )

        except TimeoutError:
            logger.error(
                "Timeout fetching connection stats",
                serial=serial,
                name=name,
            )
        except Exception:
            logger.exception(
                "Failed to collect connection stats",
                serial=serial,
            )
