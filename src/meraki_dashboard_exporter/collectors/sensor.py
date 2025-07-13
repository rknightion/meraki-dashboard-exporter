"""Fast-tier sensor metric collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..api.client import AsyncMerakiClient
from ..core.collector import MetricCollector
from ..core.constants import MetricName, UpdateTier
from ..core.logging import get_logger
from .devices import MTCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings

logger = get_logger(__name__)


class SensorCollector(MetricCollector):
    """Collector for fast-moving sensor metrics (MT devices)."""

    # Sensor data updates frequently
    update_tier: UpdateTier = UpdateTier.FAST

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
    ) -> None:
        """Initialize sensor collector with sub-collectors."""
        super().__init__(api, settings, registry)
        self.mt_collector = MTCollector(self)

    def _initialize_metrics(self) -> None:
        """Initialize sensor metrics."""
        # Temperature sensors
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

        self._sensor_air_quality = self._create_gauge(
            MetricName.MT_INDOOR_AIR_QUALITY_SCORE,
            "Indoor air quality score (0-100)",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_voltage = self._create_gauge(
            MetricName.MT_VOLTAGE_VOLTS,
            "Voltage in volts",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_current = self._create_gauge(
            MetricName.MT_CURRENT_AMPS,
            "Current in amperes",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_real_power = self._create_gauge(
            MetricName.MT_REAL_POWER_WATTS,
            "Real power in watts",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_apparent_power = self._create_gauge(
            MetricName.MT_APPARENT_POWER_VA,
            "Apparent power in volt-amperes",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_power_factor = self._create_gauge(
            MetricName.MT_POWER_FACTOR_PERCENT,
            "Power factor percentage",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_frequency = self._create_gauge(
            MetricName.MT_FREQUENCY_HZ,
            "Frequency in hertz",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_downstream_power = self._create_gauge(
            MetricName.MT_DOWNSTREAM_POWER_ENABLED,
            "Downstream power status (1 = enabled, 0 = disabled)",
            labelnames=["serial", "name", "sensor_type"],
        )

        self._sensor_remote_lockout = self._create_gauge(
            MetricName.MT_REMOTE_LOCKOUT_STATUS,
            "Remote lockout switch status (1 = locked, 0 = unlocked)",
            labelnames=["serial", "name", "sensor_type"],
        )

    async def _collect_impl(self) -> None:
        """Collect sensor metrics."""
        try:
            # Get organizations
            if self.settings.org_id:
                org_ids = [self.settings.org_id]
            else:
                logger.debug("Fetching all organizations for sensor collection")
                self._track_api_call("getOrganizations")
                orgs = await asyncio.to_thread(self.api.organizations.getOrganizations)
                org_ids = [org["id"] for org in orgs]
                logger.debug("Successfully fetched organizations", count=len(org_ids))

            # Collect sensors for each organization
            for org_id in org_ids:
                try:
                    await self._collect_org_sensors(org_id)
                except Exception:
                    logger.exception(
                        "Failed to collect sensors for organization",
                        org_id=org_id,
                    )
                    # Continue with next organization

        except Exception:
            logger.exception("Failed to collect sensor metrics")

    async def _collect_org_sensors(self, org_id: str) -> None:
        """Collect sensor metrics for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        """
        try:
            # Get all MT devices
            logger.debug("Fetching sensor devices", org_id=org_id)
            self._track_api_call("getOrganizationDevices")
            devices = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevices,
                org_id,
                total_pages="all",
                productTypes=["sensor"],
            )
            logger.debug("Successfully fetched sensor devices", org_id=org_id, count=len(devices))

            if not devices:
                return

            # Extract sensor serials
            sensor_serials = [d["serial"] for d in devices if d.get("model", "").startswith("MT")]

            if sensor_serials:
                # Create device lookup map
                device_map = {d["serial"]: d for d in devices}

                # Use async client for batch sensor reading
                client = AsyncMerakiClient(self.settings)
                readings = await client.get_sensor_readings_latest(org_id, sensor_serials)

                # Process readings
                logger.debug(
                    "Processing sensor readings",
                    org_id=org_id,
                    sensor_count=len(sensor_serials),
                    readings_count=len(readings),
                )
                self.mt_collector.collect_batch(readings, device_map)

        except Exception:
            logger.exception(
                "Failed to collect sensors for organization",
                org_id=org_id,
            )
