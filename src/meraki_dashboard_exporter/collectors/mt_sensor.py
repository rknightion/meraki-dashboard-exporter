"""Fast-tier MT sensor metric collector.

This collector handles environmental sensor metrics from MT devices.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.collector import MetricCollector
from ..core.constants import MetricName, UpdateTier
from ..core.logging import get_logger
from .devices import MTCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings

logger = get_logger(__name__)


class MTSensorCollector(MetricCollector):
    """Collector for fast-moving sensor metrics (MT devices)."""

    # Sensor data updates frequently
    update_tier: UpdateTier = UpdateTier.FAST

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
    ) -> None:
        """Initialize MT sensor collector."""
        super().__init__(api, settings, registry)
        # Create MT collector in standalone mode
        self.mt_collector = MTCollector(None)
        # Pass API and settings to MT collector
        self.mt_collector.api = api
        self.mt_collector.settings = settings

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

        # Pass self as parent to MT collector so it can access metrics
        self.mt_collector.parent = self

    async def _collect_impl(self) -> None:
        """Collect sensor metrics by delegating to MT collector."""
        await self.mt_collector.collect_sensor_metrics()