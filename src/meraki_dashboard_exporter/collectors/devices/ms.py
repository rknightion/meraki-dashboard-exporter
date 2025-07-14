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
        model = device.get("model", "")
        network_id = device.get("networkId", "")

        try:
            # Get port statuses with timeout
            logger.debug(
                "Fetching switch port statuses",
                serial=serial,
                name=name,
            )
            self.parent._track_api_call("getDeviceSwitchPortsStatuses")

            try:
                port_statuses = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.api.switch.getDeviceSwitchPortsStatuses,
                        serial,
                    ),
                    timeout=30.0,  # 10 second timeout
                )
            except TimeoutError:
                logger.error(
                    "Timeout fetching switch port statuses",
                    serial=serial,
                    name=name,
                )
                return

            logger.debug(
                "Successfully fetched port statuses",
                serial=serial,
                port_count=len(port_statuses) if port_statuses else 0,
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

            # Extract POE data from port statuses (POE data is included in port status)
            total_poe_consumption = 0

            for port in port_statuses:
                port_id = str(port.get("portId", ""))
                port_name = port.get("name", f"Port {port_id}")

                # Check if port has POE data
                poe_info = port.get("poe", {})
                if poe_info.get("isAllocated", False):
                    # Port is drawing POE power
                    power_used = port.get("powerUsageInWh", 0)

                    self.parent._switch_poe_port_power.labels(
                        serial=serial,
                        name=name,
                        port_id=port_id,
                        port_name=port_name,
                    ).set(power_used)

                    total_poe_consumption += power_used
                else:
                    # Port is not drawing POE power
                    self.parent._switch_poe_port_power.labels(
                        serial=serial,
                        name=name,
                        port_id=port_id,
                        port_name=port_name,
                    ).set(0)

            # Set switch-level POE total
            self.parent._switch_poe_total_power.labels(
                serial=serial,
                name=name,
                model=model,
                network_id=network_id,
            ).set(total_poe_consumption)

            # Set total switch power usage (POE consumption is the main power draw)
            # This is an approximation - actual switch base power consumption varies by model
            self.parent._switch_power.labels(
                serial=serial,
                name=name,
                model=model,
            ).set(total_poe_consumption)

            # Note: POE budget is not available via API, would need a lookup table by model

        except Exception:
            logger.exception(
                "Failed to collect switch metrics",
                serial=serial,
            )
