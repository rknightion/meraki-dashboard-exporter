"""Bluetooth collector for wireless network Bluetooth client metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.logging import get_logger
from .base import BaseNetworkHealthCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class BluetoothCollector(BaseNetworkHealthCollector):
    """Collector for Bluetooth clients detected by MR devices in a network."""

    async def collect(self, network: dict[str, Any]) -> None:
        """Collect Bluetooth clients detected by MR devices in a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        network_id = network["id"]
        network_name = network.get("name", network_id)

        try:
            logger.debug(
                "Fetching Bluetooth clients",
                network_id=network_id,
                network_name=network_name,
            )

            # Track API call
            self._track_api_call("getNetworkBluetoothClients")

            # Get Bluetooth clients for the last 5 minutes with page size 1000
            bluetooth_clients = await asyncio.to_thread(
                self.api.networks.getNetworkBluetoothClients,
                network_id,
                timespan=300,  # 5 minutes
                perPage=1000,
                total_pages="all",
            )

            # Count the total number of Bluetooth clients
            client_count = len(bluetooth_clients) if bluetooth_clients else 0

            # Set the metric
            self._set_metric_value(
                "_network_bluetooth_clients_total",
                {
                    "network_id": network_id,
                    "network_name": network_name,
                },
                client_count,
            )

            logger.debug(
                "Successfully collected Bluetooth clients",
                network_id=network_id,
                network_name=network_name,
                client_count=client_count,
            )

        except Exception as e:
            # Log at debug level if it's just not available (400/404 errors)
            error_str = str(e)
            if "400" in error_str or "404" in error_str or "Bad Request" in error_str:
                logger.debug(
                    "Bluetooth clients API not available",
                    network_id=network_id,
                    network_name=network_name,
                    error=error_str,
                )
                # Set metric to 0 when API is not available
                self._set_metric_value(
                    "_network_bluetooth_clients_total",
                    {
                        "network_id": network_id,
                        "network_name": network_name,
                    },
                    0,
                )
            else:
                logger.exception(
                    "Failed to collect Bluetooth clients",
                    network_id=network_id,
                    network_name=network_name,
                )
