"""Meraki MS (Switch) metrics collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants import MetricName
from ...core.logging import get_logger
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class MSCollector(BaseDeviceCollector):
    """Collector for Meraki MS (Switch) devices."""

    def _initialize_metrics(self) -> None:
        """Initialize MS-specific metrics."""
        # Switch port metrics
        self._switch_port_status = self.parent._create_gauge(
            MetricName.MS_PORT_STATUS,
            "Switch port status (1 = connected, 0 = disconnected)",
            labelnames=["serial", "name", "port_id", "port_name"],
        )

        self._switch_port_traffic = self.parent._create_gauge(
            MetricName.MS_PORT_TRAFFIC_BYTES,
            "Switch port traffic in bytes",
            labelnames=["serial", "name", "port_id", "port_name", "direction"],
        )

        self._switch_port_errors = self.parent._create_gauge(
            MetricName.MS_PORT_ERRORS_TOTAL,
            "Switch port error count",
            labelnames=["serial", "name", "port_id", "port_name", "error_type"],
        )

        # Switch power metrics
        self._switch_power = self.parent._create_gauge(
            MetricName.MS_POWER_USAGE_WATTS,
            "Switch power usage in watts",
            labelnames=["serial", "name", "model"],
        )

        # POE metrics
        self._switch_poe_port_power = self.parent._create_gauge(
            MetricName.MS_POE_PORT_POWER_WATTS,
            "Per-port POE power consumption in watt-hours (Wh)",
            labelnames=["serial", "name", "port_id", "port_name"],
        )

        self._switch_poe_total_power = self.parent._create_gauge(
            MetricName.MS_POE_TOTAL_POWER_WATTS,
            "Total POE power consumption for switch in watt-hours (Wh)",
            labelnames=["serial", "name", "model", "network_id"],
        )

        self._switch_poe_budget = self.parent._create_gauge(
            MetricName.MS_POE_BUDGET_WATTS,
            "Total POE power budget for switch in watts",
            labelnames=["serial", "name", "model", "network_id"],
        )

        self._switch_poe_network_total = self.parent._create_gauge(
            MetricName.MS_POE_NETWORK_TOTAL_WATTS,
            "Total POE power consumption for all switches in network in watt-hours (Wh)",
            labelnames=["network_id", "network_name"],
        )

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

            port_statuses = await asyncio.to_thread(
                self.api.switch.getDeviceSwitchPortsStatuses,
                serial,
            )

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
                self._switch_port_status.labels(
                    serial=serial,
                    name=name,
                    port_id=port_id,
                    port_name=port_name,
                ).set(is_connected)

                # Traffic counters
                if "trafficInKbps" in port:
                    traffic_counters = port["trafficInKbps"]

                    if "recv" in traffic_counters:
                        self._switch_port_traffic.labels(
                            serial=serial,
                            name=name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="rx",
                        ).set(traffic_counters["recv"] * 1000 / 8)  # Convert to bytes

                    if "sent" in traffic_counters:
                        self._switch_port_traffic.labels(
                            serial=serial,
                            name=name,
                            port_id=port_id,
                            port_name=port_name,
                            direction="tx",
                        ).set(traffic_counters["sent"] * 1000 / 8)  # Convert to bytes

                # Error counters
                if "errors" in port and isinstance(port["errors"], dict):
                    for error_type, count in port["errors"].items():
                        self._switch_port_errors.labels(
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

                    self._switch_poe_port_power.labels(
                        serial=serial,
                        name=name,
                        port_id=port_id,
                        port_name=port_name,
                    ).set(power_used)

                    total_poe_consumption += power_used
                else:
                    # Port is not drawing POE power
                    self._switch_poe_port_power.labels(
                        serial=serial,
                        name=name,
                        port_id=port_id,
                        port_name=port_name,
                    ).set(0)

            # Set switch-level POE total
            self._switch_poe_total_power.labels(
                serial=serial,
                name=name,
                model=model,
                network_id=network_id,
            ).set(total_poe_consumption)

            # Set total switch power usage (POE consumption is the main power draw)
            # This is an approximation - actual switch base power consumption varies by model
            self._switch_power.labels(
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
