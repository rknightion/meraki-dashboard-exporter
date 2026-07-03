"""Fast-tier MT sensor metric collector.

This collector handles environmental sensor metrics from MT devices.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar

from ..core.collector import MetricCollector
from ..core.constants import MTMetricName, UpdateTier
from ..core.logging import get_logger
from ..core.logging_helpers import log_metric_collection_summary
from ..core.metrics import LabelName
from ..core.registry import register_collector
from ..core.scheduler import EndpointGroup, EndpointGroupName, pages
from .devices import MTCollector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry

    from ..core.config import Settings
    from ..core.metric_expiration import MetricExpirationManager
    from ..services.inventory import OrganizationInventory

logger = get_logger(__name__)


@register_collector(UpdateTier.FAST)
class MTSensorCollector(MetricCollector):
    """Collector for fast-moving sensor metrics (MT devices)."""

    # #617 §2 (FAST heartbeat). One group spans both org-wide fetches this
    # collector issues per cycle: the latest sensor readings and the
    # sensor-to-gateway connections. cost_fn: 1 page for gateway connections
    # plus pages(MT, 100) for readings (perPage ⚠ Phase-6-verify).
    endpoint_groups: ClassVar[tuple[EndpointGroup, ...]] = (
        EndpointGroup(
            name=EndpointGroupName.MT_SENSOR_READINGS,
            priority=2,
            floor_seconds=60,
            cost_fn=lambda shape: 2 + pages(shape.sensor_count, 100) - 1,
            tier=UpdateTier.FAST,
            enabled_fn=lambda shape: shape.sensor_count > 0,
        ),
    )

    def __init__(
        self,
        api: DashboardAPI,
        settings: Settings,
        registry: CollectorRegistry | None = None,
        inventory: OrganizationInventory | None = None,
        expiration_manager: MetricExpirationManager | None = None,
        rate_limiter: Any | None = None,
        scheduler: Any | None = None,
    ) -> None:
        """Initialize MT sensor collector."""
        super().__init__(
            api,
            settings,
            registry,
            inventory,
            expiration_manager,
            rate_limiter,
            scheduler=scheduler,
        )
        # Create MT collector in standalone mode
        self.mt_collector = MTCollector.as_standalone(
            api=api, settings=settings, rate_limiter=self.rate_limiter
        )
        # Pass this collector as the parent for metric access
        # This allows MTCollector to use MTSensorCollector's metrics
        self.mt_collector.parent = self

    def _initialize_metrics(self) -> None:
        """Initialize sensor metrics."""
        # Temperature sensors
        self._sensor_temperature = self._create_gauge(
            MTMetricName.MT_TEMPERATURE_CELSIUS,
            "Temperature reading in Celsius",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_humidity = self._create_gauge(
            MTMetricName.MT_HUMIDITY_PERCENT,
            "Humidity percentage",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_door = self._create_gauge(
            MTMetricName.MT_DOOR_STATUS,
            "Door sensor status (1 = open, 0 = closed)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_water = self._create_gauge(
            MTMetricName.MT_WATER_DETECTED,
            "Water detection status (1 = detected, 0 = not detected)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_co2 = self._create_gauge(
            MTMetricName.MT_CO2_PPM,
            "CO2 level in parts per million",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_tvoc = self._create_gauge(
            MTMetricName.MT_TVOC_PPB,
            "Total volatile organic compounds in parts per billion",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_pm25 = self._create_gauge(
            MTMetricName.MT_PM25_UG_M3,
            "PM2.5 particulate matter in micrograms per cubic meter",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_no2 = self._create_gauge(
            MTMetricName.MT_NO2_PPB,
            "NO2 (nitrogen dioxide) concentration in parts per billion",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_o3 = self._create_gauge(
            MTMetricName.MT_O3_PPB,
            "O3 (ozone) concentration in parts per billion",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_pm10 = self._create_gauge(
            MTMetricName.MT_PM10_UG_M3,
            "PM10 particulate matter in micrograms per cubic meter",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_noise = self._create_gauge(
            MTMetricName.MT_NOISE_DB,
            "Noise level in decibels",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_battery = self._create_gauge(
            MTMetricName.MT_BATTERY_PERCENT,
            "Battery level percentage",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_air_quality = self._create_gauge(
            MTMetricName.MT_INDOOR_AIR_QUALITY_SCORE,
            "Indoor air quality score (0-100)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_voltage = self._create_gauge(
            MTMetricName.MT_VOLTAGE_VOLTS,
            "Voltage in volts",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_current = self._create_gauge(
            MTMetricName.MT_CURRENT_AMPS,
            "Current in amperes",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_real_power = self._create_gauge(
            MTMetricName.MT_REAL_POWER_WATTS,
            "Real power in watts",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_apparent_power = self._create_gauge(
            MTMetricName.MT_APPARENT_POWER_VA,
            "Apparent power in volt-amperes",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_power_factor = self._create_gauge(
            MTMetricName.MT_POWER_FACTOR_PERCENT,
            "Power factor percentage",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_frequency = self._create_gauge(
            MTMetricName.MT_FREQUENCY_HZ,
            "Frequency in hertz",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_downstream_power = self._create_gauge(
            MTMetricName.MT_DOWNSTREAM_POWER_ENABLED,
            "Downstream power status (1 = enabled, 0 = disabled)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        self._sensor_remote_lockout = self._create_gauge(
            MTMetricName.MT_REMOTE_LOCKOUT_STATUS,
            "Remote lockout switch status (1 = locked, 0 = unlocked)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
            ],
        )

        # Sensor-to-gateway connectivity (#269)
        self._sensor_gateway_rssi = self._create_gauge(
            MTMetricName.MT_GATEWAY_RSSI,
            "MT sensor-to-gateway RSSI (dBm)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.GATEWAY_SERIAL,
            ],
        )

        self._sensor_gateway_last_connected = self._create_gauge(
            MTMetricName.MT_GATEWAY_LAST_CONNECTED_TIMESTAMP,
            "MT sensor-to-gateway last-connected Unix timestamp (seconds)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.GATEWAY_SERIAL,
            ],
        )

        # MT20/MT30 button presses (#303). Rides this collector's existing
        # getOrganizationSensorReadingsLatest fetch - zero new API calls.
        self._sensor_button_last_press = self._create_gauge(
            MTMetricName.MT_BUTTON_LAST_PRESS_TIMESTAMP_SECONDS,
            "Unix timestamp (seconds) of the last observed press via polling; "
            "individual presses between polls are not guaranteed to be captured - "
            "webhook sensorAlert events are the reliable path",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SERIAL,
                LabelName.MODEL,
                LabelName.DEVICE_TYPE,
                LabelName.PRESS_TYPE,
            ],
        )

    async def _collect_impl(self) -> None:
        """Collect sensor metrics by delegating to MT collector.

        No blanket error handling here (#509) — exceptions from
        ``collect_sensor_metrics`` (including ``NothingCollectedError``) must
        propagate so the manager records the cycle as a failure.
        """
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
