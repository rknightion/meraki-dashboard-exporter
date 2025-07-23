"""Fast-tier MT sensor metric collector.

This collector handles environmental sensor metrics from MT devices.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..core.collector import MetricCollector
from ..core.constants import MTMetricName, UpdateTier
from ..core.error_handling import with_error_handling
from ..core.logging import get_logger
from ..core.logging_helpers import log_metric_collection_summary
from ..core.metrics import LabelName
from ..core.registry import register_collector
from .devices import MTCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings

logger = get_logger(__name__)


@register_collector(UpdateTier.FAST)
class MTSensorCollector(MetricCollector):
    """Collector for fast-moving sensor metrics (MT devices)."""

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
        # Pass this collector as the parent for metric access
        # This allows MTCollector to use MTSensorCollector's metrics
        self.mt_collector.parent = self  # type: ignore[assignment]

    def _initialize_metrics(self) -> None:
        """Initialize sensor metrics."""
        # Temperature sensors
        self._sensor_temperature = self._create_gauge(
            MTMetricName.MT_TEMPERATURE_CELSIUS,
            "Temperature reading in Celsius",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_humidity = self._create_gauge(
            MTMetricName.MT_HUMIDITY_PERCENT,
            "Humidity percentage",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_door = self._create_gauge(
            MTMetricName.MT_DOOR_STATUS,
            "Door sensor status (1 = open, 0 = closed)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_water = self._create_gauge(
            MTMetricName.MT_WATER_DETECTED,
            "Water detection status (1 = detected, 0 = not detected)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_co2 = self._create_gauge(
            MTMetricName.MT_CO2_PPM,
            "CO2 level in parts per million",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_tvoc = self._create_gauge(
            MTMetricName.MT_TVOC_PPB,
            "Total volatile organic compounds in parts per billion",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_pm25 = self._create_gauge(
            MTMetricName.MT_PM25_UG_M3,
            "PM2.5 particulate matter in micrograms per cubic meter",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_noise = self._create_gauge(
            MTMetricName.MT_NOISE_DB,
            "Noise level in decibels",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_battery = self._create_gauge(
            MTMetricName.MT_BATTERY_PERCENTAGE,
            "Battery level percentage",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_air_quality = self._create_gauge(
            MTMetricName.MT_INDOOR_AIR_QUALITY_SCORE,
            "Indoor air quality score (0-100)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_voltage = self._create_gauge(
            MTMetricName.MT_VOLTAGE_VOLTS,
            "Voltage in volts",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_current = self._create_gauge(
            MTMetricName.MT_CURRENT_AMPS,
            "Current in amperes",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_real_power = self._create_gauge(
            MTMetricName.MT_REAL_POWER_WATTS,
            "Real power in watts",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_apparent_power = self._create_gauge(
            MTMetricName.MT_APPARENT_POWER_VA,
            "Apparent power in volt-amperes",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_power_factor = self._create_gauge(
            MTMetricName.MT_POWER_FACTOR_PERCENT,
            "Power factor percentage",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_frequency = self._create_gauge(
            MTMetricName.MT_FREQUENCY_HZ,
            "Frequency in hertz",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_downstream_power = self._create_gauge(
            MTMetricName.MT_DOWNSTREAM_POWER_ENABLED,
            "Downstream power status (1 = enabled, 0 = disabled)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_remote_lockout = self._create_gauge(
            MTMetricName.MT_REMOTE_LOCKOUT_STATUS,
            "Remote lockout switch status (1 = locked, 0 = unlocked)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SERIAL,
                LabelName.NAME,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

    @with_error_handling(
        operation="Collect MT sensor metrics",
        continue_on_error=True,
    )
    async def _collect_impl(self) -> None:
        """Collect sensor metrics by delegating to MT collector."""
        start_time = asyncio.get_event_loop().time()

        # Delegate to MT collector to collect sensor metrics
        await self.mt_collector.collect_sensor_metrics()

        # Log collection summary
        # The actual metrics count and API calls will be tracked by MTCollector
        log_metric_collection_summary(
            "MTSensorCollector",
            metrics_collected=0,  # Metrics tracked by MT collector
            duration_seconds=asyncio.get_event_loop().time() - start_time,
            organizations_processed=0,  # Will be set by MT collector
            api_calls_made=0,  # API calls tracked by MT collector
        )
