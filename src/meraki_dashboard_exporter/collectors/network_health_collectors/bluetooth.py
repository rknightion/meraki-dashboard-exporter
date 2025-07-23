"""Bluetooth collector for wireless network Bluetooth client metrics."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.label_helpers import create_network_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from .base import BaseNetworkHealthCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class BluetoothCollector(BaseNetworkHealthCollector):
    """Collector for Bluetooth clients detected by MR devices in a network."""

    @log_api_call("getNetworkBluetoothClients")
    async def _fetch_bluetooth_clients(self, network_id: str) -> list[dict[str, Any]]:
        """Fetch Bluetooth clients for a network.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[dict[str, Any]]
            List of Bluetooth clients.

        """
        return await asyncio.to_thread(
            self.api.networks.getNetworkBluetoothClients,
            network_id,
            timespan=300,  # 5 minutes
            perPage=1000,
            total_pages="all",
        )

    async def collect(self, network: dict[str, Any]) -> None:
        """Collect Bluetooth clients detected by MR devices in a network.

        Parameters
        ----------
        network : dict[str, Any]
            Network data.

        """
        network_id = network["id"]
        network_name = network.get("name", network_id)
        org_id = network.get("orgId", "")
        org_name = network.get("orgName", org_id)

        try:
            with LogContext(network_id=network_id, network_name=network_name, org_id=org_id):
                # Get Bluetooth clients for the last 5 minutes with page size 1000
                bluetooth_clients = await self._fetch_bluetooth_clients(network_id)

            # Count the total number of Bluetooth clients
            client_count = len(bluetooth_clients) if bluetooth_clients else 0

            # Create network labels using helper
            labels = create_network_labels(
                network,
                org_id=org_id,
                org_name=org_name,
            )

            # Set the metric
            self._set_metric_value(
                "_network_bluetooth_clients_total",
                labels,
                client_count,
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
                # Create network labels using helper
                labels = create_network_labels(
                    network,
                    org_id=org_id,
                    org_name=org_name,
                )

                # Set metric to 0 when API is not available
                self._set_metric_value(
                    "_network_bluetooth_clients_total",
                    labels,
                    0,
                )
            else:
                logger.exception(
                    "Failed to collect Bluetooth clients",
                    network_id=network_id,
                    network_name=network_name,
                )
