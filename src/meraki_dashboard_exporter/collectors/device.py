"""Device-level metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..core.collector import MetricCollector
from ..core.constants import DeviceStatus, DeviceType, MetricName
from ..core.logging import get_logger
from .devices import MRCollector, MSCollector, MTCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings

logger = get_logger(__name__)


class DeviceCollector(MetricCollector):
    """Collector for device-level metrics."""

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
    ) -> None:
        """Initialize device collector with sub-collectors."""
        super().__init__(api, settings, registry)

        # Initialize device-specific collectors
        self.ms_collector = MSCollector(self)
        self.mr_collector = MRCollector(self)
        self.mt_collector = MTCollector(self)

    def _initialize_metrics(self) -> None:
        """Initialize device metrics."""
        # Common device metrics
        self._device_up = self._create_gauge(
            MetricName.DEVICE_UP,
            "Device online status (1 = online, 0 = offline)",
            labelnames=["serial", "name", "model", "network_id", "device_type"],
        )

        self._device_uptime = self._create_gauge(
            MetricName.DEVICE_UPTIME_SECONDS,
            "Device uptime in seconds",
            labelnames=["serial", "name", "model", "network_id", "device_type"],
        )

        self._device_cpu = self._create_gauge(
            MetricName.DEVICE_CPU_USAGE_PERCENT,
            "Device CPU usage percentage",
            labelnames=["serial", "name", "model", "network_id", "device_type"],
        )

        self._device_memory = self._create_gauge(
            MetricName.DEVICE_MEMORY_USAGE_PERCENT,
            "Device memory usage percentage",
            labelnames=["serial", "name", "model", "network_id", "device_type"],
        )

        # Switch-specific metrics
        self._switch_port_status = self._create_gauge(
            MetricName.MS_PORT_STATUS,
            "Switch port status (1 = connected, 0 = disconnected)",
            labelnames=["serial", "name", "port_id", "port_name"],
        )

        self._switch_port_traffic = self._create_gauge(
            MetricName.MS_PORT_TRAFFIC_BYTES,
            "Switch port traffic in bytes",
            labelnames=["serial", "name", "port_id", "port_name", "direction"],
        )

        self._switch_port_errors = self._create_gauge(
            MetricName.MS_PORT_ERRORS_TOTAL,
            "Switch port error count",
            labelnames=["serial", "name", "port_id", "port_name", "error_type"],
        )

        self._switch_power = self._create_gauge(
            MetricName.MS_POWER_USAGE_WATTS,
            "Switch power usage in watts",
            labelnames=["serial", "name", "model"],
        )

        # Wireless AP metrics
        self._ap_clients = self._create_gauge(
            MetricName.MR_CLIENTS_CONNECTED,
            "Number of clients connected to access point",
            labelnames=["serial", "name", "model", "network_id"],
        )

        self._ap_channel_utilization = self._create_gauge(
            MetricName.MR_CHANNEL_UTILIZATION_PERCENT,
            "Channel utilization percentage",
            labelnames=["serial", "name", "band", "channel"],
        )

        self._ap_traffic = self._create_gauge(
            MetricName.MR_TRAFFIC_BYTES,
            "Access point traffic in bytes",
            labelnames=["serial", "name", "direction"],
        )

        # Sensor metrics
        self._sensor_temperature = self._create_gauge(
            MetricName.MT_TEMPERATURE_CELSIUS,
            "Temperature reading in Celsius",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_humidity = self._create_gauge(
            MetricName.MT_HUMIDITY_PERCENT,
            "Humidity percentage",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_door = self._create_gauge(
            MetricName.MT_DOOR_STATUS,
            "Door sensor status (1 = open, 0 = closed)",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_water = self._create_gauge(
            MetricName.MT_WATER_DETECTED,
            "Water detection status (1 = detected, 0 = not detected)",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_co2 = self._create_gauge(
            MetricName.MT_CO2_PPM,
            "CO2 level in parts per million",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_tvoc = self._create_gauge(
            MetricName.MT_TVOC_PPB,
            "Total volatile organic compounds in parts per billion",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_pm25 = self._create_gauge(
            MetricName.MT_PM25_UG_M3,
            "PM2.5 particulate matter in micrograms per cubic meter",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_noise = self._create_gauge(
            MetricName.MT_NOISE_DB,
            "Noise level in decibels",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_battery = self._create_gauge(
            MetricName.MT_BATTERY_PERCENTAGE,
            "Battery level percentage",
            labelnames=["serial", "name", "sensor_type"],
        )

    async def collect(self) -> None:
        """Collect device metrics."""
        try:
            # Get organizations
            if self.settings.org_id:
                org_ids = [self.settings.org_id]
            else:
                orgs = await asyncio.to_thread(
                    self.api.organizations.getOrganizations
                )
                org_ids = [org["id"] for org in orgs]

            # Collect devices for each organization
            for org_id in org_ids:
                await self._collect_org_devices(org_id)

        except Exception:
            logger.exception("Failed to collect device metrics")

    async def _collect_org_devices(self, org_id: str) -> None:
        """Collect device metrics for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        """
        try:
            # Get all devices and their statuses
            devices, statuses = await asyncio.gather(
                asyncio.to_thread(
                    self.api.organizations.getOrganizationDevices,
                    org_id,
                    total_pages="all",
                ),
                asyncio.to_thread(
                    self.api.organizations.getOrganizationDevicesStatuses,
                    org_id,
                    total_pages="all",
                ),
                return_exceptions=True,
            )

            if isinstance(devices, Exception) or isinstance(statuses, Exception):
                logger.error(
                    "Failed to get devices or statuses",
                    org_id=org_id,
                    devices_error=devices if isinstance(devices, Exception) else None,
                    statuses_error=statuses if isinstance(statuses, Exception) else None,
                )
                return

            # Create status lookup
            status_map = {s["serial"]: s for s in statuses}

            # Collect sensor serials for batch fetching
            sensor_serials = []

            # Collect metrics for each device type
            tasks = []
            for device in devices:
                device_type = self._get_device_type(device)
                if device_type not in self.settings.device_types:
                    continue

                # Add status info to device
                device["status_info"] = status_map.get(device["serial"], {})

                # Collect common metrics
                self._collect_common_metrics(device)

                # Collect type-specific metrics
                if device_type == DeviceType.MS:
                    tasks.append(self.ms_collector.collect(device))
                elif device_type == DeviceType.MR:
                    tasks.append(self.mr_collector.collect(device))
                elif device_type == DeviceType.MT:
                    sensor_serials.append(device["serial"])

            # Batch fetch sensor readings if we have any sensors
            if sensor_serials:
                await self._collect_sensor_metrics_batch(org_id, sensor_serials, devices)

            # Run all device-specific collections concurrently
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception:
            logger.exception(
                "Failed to collect devices for organization",
                org_id=org_id,
            )

    def _get_device_type(self, device: dict[str, Any]) -> str:
        """Get device type from device model.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        Returns
        -------
        str
            Device type.

        """
        model = device.get("model", "")
        return model[:2] if len(model) >= 2 else "Unknown"

    def _collect_common_metrics(self, device: dict[str, Any]) -> None:
        """Collect common device metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with status_info added.

        """
        serial = device["serial"]
        name = device.get("name", serial)
        model = device.get("model", "Unknown")
        network_id = device.get("networkId", "")
        device_type = self._get_device_type(device)
        status_info = device.get("status_info", {})

        # Device up/down status
        status = status_info.get("status", DeviceStatus.OFFLINE)
        is_online = 1 if status == DeviceStatus.ONLINE else 0
        self._device_up.labels(
            serial=serial,
            name=name,
            model=model,
            network_id=network_id,
            device_type=device_type,
        ).set(is_online)

        # Uptime
        if "uptimeInSeconds" in device:
            self._device_uptime.labels(
                serial=serial,
                name=name,
                model=model,
                network_id=network_id,
                device_type=device_type,
            ).set(device["uptimeInSeconds"])

    async def _collect_sensor_metrics_batch(
        self, org_id: str, sensor_serials: list[str], all_devices: list[dict[str, Any]]
    ) -> None:
        """Collect sensor metrics in batch for better performance.

        Parameters
        ----------
        org_id : str
            Organization ID.
        sensor_serials : list[str]
            List of sensor serial numbers.
        all_devices : list[dict[str, Any]]
            All devices for looking up device info.

        """
        try:
            # Import here to avoid circular dependency
            from ..api.client import AsyncMerakiClient

            # Get latest sensor readings for all sensors at once
            client = AsyncMerakiClient(self.settings)
            readings = await client.get_sensor_readings_latest(org_id, sensor_serials)

            # Create device lookup map
            device_map = {d["serial"]: d for d in all_devices if d["serial"] in sensor_serials}

            # Use the MT collector to process the batch
            self.mt_collector.collect_batch(readings, device_map)

        except Exception:
            logger.exception(
                "Failed to collect sensor metrics",
                org_id=org_id,
                sensor_count=len(sensor_serials),
            )
