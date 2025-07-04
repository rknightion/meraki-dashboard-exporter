"""Meraki MT (Sensor) metrics collector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.logging import get_logger
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class MTCollector(BaseDeviceCollector):
    """Collector for Meraki MT (Sensor) devices."""

    def collect_batch(
        self, sensor_readings: list[dict[str, Any]], device_map: dict[str, dict[str, Any]]
    ) -> None:
        """Collect sensor metrics from batch API response.

        Parameters
        ----------
        sensor_readings : list[dict[str, Any]]
            List of sensor readings from the API.
        device_map : dict[str, dict[str, Any]]
            Mapping of serial numbers to device info.

        """
        for reading in sensor_readings:
            serial = reading.get("serial")
            if not serial or serial not in device_map:
                continue

            device = device_map[serial]
            name = device.get("name", serial)
            model = device.get("model", "MT")

            # Process each metric in the reading
            for metric in reading.get("readings", []):
                metric_type = metric.get("metric")
                value = metric.get("value")

                if value is None:
                    continue

                self._set_metric_value(serial, name, model, metric_type, value)

    def _set_metric_value(
        self, serial: str, name: str, model: str, metric_type: str, value: Any
    ) -> None:
        """Set the appropriate metric based on type.

        Parameters
        ----------
        serial : str
            Device serial number.
        name : str
            Device name.
        model : str
            Device model.
        metric_type : str
            Type of metric (temperature, humidity, etc.).
        value : Any
            Metric value.

        """
        # Map metric types to our prometheus metrics
        if metric_type == "temperature":
            self.parent._sensor_temperature.labels(
                serial=serial,
                name=name,
                sensor_type=model,
            ).set(value)

        elif metric_type == "humidity":
            self.parent._sensor_humidity.labels(
                serial=serial,
                name=name,
                sensor_type=model,
            ).set(value)

        elif metric_type == "door":
            # Door sensor: value is "open" or "closed"
            is_open = 1 if value == "open" else 0
            self.parent._sensor_door.labels(
                serial=serial,
                name=name,
                sensor_type=model,
            ).set(is_open)

        elif metric_type == "water":
            # Water sensor: value is "present" or "absent"
            is_detected = 1 if value == "present" else 0
            self.parent._sensor_water.labels(
                serial=serial,
                name=name,
                sensor_type=model,
            ).set(is_detected)

        elif metric_type == "co2":
            self.parent._sensor_co2.labels(
                serial=serial,
                name=name,
                sensor_type=model,
            ).set(value)

        elif metric_type == "tvoc":
            self.parent._sensor_tvoc.labels(
                serial=serial,
                name=name,
                sensor_type=model,
            ).set(value)

        elif metric_type == "pm25":
            self.parent._sensor_pm25.labels(
                serial=serial,
                name=name,
                sensor_type=model,
            ).set(value)

        elif metric_type == "noise":
            self.parent._sensor_noise.labels(
                serial=serial,
                name=name,
                sensor_type=model,
            ).set(value)

        elif metric_type == "battery":
            self.parent._sensor_battery.labels(
                serial=serial,
                name=name,
                sensor_type=model,
            ).set(value)

        elif metric_type == "indoorAirQuality":
            # Some sensors report an overall air quality score
            logger.debug(
                "Indoor air quality metric not yet implemented",
                serial=serial,
                value=value,
            )
