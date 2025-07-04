"""Meraki MS (Switch) metrics collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.logging import get_logger
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class MSCollector(BaseDeviceCollector):
    """Collector for Meraki MS (Switch) devices."""

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect switch-specific metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Switch device data.

        """
        serial = device["serial"]
        name = device.get("name", serial)

        try:
            # Get port statuses
            port_statuses = await asyncio.to_thread(
                self.api.switch.getDeviceSwitchPortsStatuses,
                serial,
            )

            for port in port_statuses:
                port_id = str(port.get("portId", ""))
                port_name = port.get("name", f"Port {port_id}")

                # Port status
                is_connected = 1 if port.get("status") == "Connected" else 0
                self.parent._switch_port_status.labels(
                    serial=serial,
                    name=name,
                    port_id=port_id,
                    port_name=port_name,
                ).set(is_connected)

                # Traffic counters
                if "trafficInKbps" in port:
                    traffic_counters = port["trafficInKbps"]

                    if "recv" in traffic_counters:
                        self.parent._switch_port_traffic.labels(
                            serial=serial,
                            name=name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="rx",
                        ).set(traffic_counters["recv"] * 1000 / 8)  # Convert to bytes

                    if "sent" in traffic_counters:
                        self.parent._switch_port_traffic.labels(
                            serial=serial,
                            name=name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="tx",
                        ).set(traffic_counters["sent"] * 1000 / 8)  # Convert to bytes

                # Error counters
                if "errors" in port and isinstance(port["errors"], dict):
                    for error_type, count in port["errors"].items():
                        self.parent._switch_port_errors.labels(
                            serial=serial,
                            name=name,
                            port_id=port_id,
                            port_name=port_name,
                            error_type=error_type,
                        ).set(count)

        except Exception:
            logger.exception(
                "Failed to collect switch metrics",
                serial=serial,
            )
