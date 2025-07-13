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

    def _set_metric_value(self, metric_name: str, labels: dict[str, str], value: float) -> None:
        """Safely set a metric value with validation.

        Parameters
        ----------
        metric_name : str
            Name of the metric attribute on parent.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float
            Value to set.

        """
        if not self.parent:
            return

        metric = getattr(self.parent, metric_name, None)
        if metric is None:
            logger.debug(
                "Metric not available on parent collector",
                metric_name=metric_name,
                parent_type=type(self.parent).__name__,
            )
            return

        try:
            metric.labels(**labels).set(value)
        except Exception:
            logger.exception(
                "Failed to set metric value",
                metric_name=metric_name,
                labels=labels,
                value=value,
            )

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
        for sensor_data in sensor_readings:
            serial = sensor_data.get("serial")
            if not serial or serial not in device_map:
                continue

            device = device_map[serial]
            name = device.get("name", serial)
            model = device.get("model", "MT")
            network_info = sensor_data.get("network", {})
            network_id = network_info.get("id", "")
            network_name = network_info.get("name", "")

            # Process each reading for the sensor
            for reading in sensor_data.get("readings", []):
                metric_type = reading.get("metric")
                if not metric_type:
                    continue

                # Extract the metric-specific data
                metric_data = reading.get(metric_type, {})
                if not metric_data:
                    continue

                self._process_metric(
                    serial=serial,
                    name=name,
                    model=model,
                    network_id=network_id,
                    network_name=network_name,
                    metric_type=metric_type,
                    metric_data=metric_data,
                )

    def _process_metric(
        self,
        serial: str,
        name: str,
        model: str,
        network_id: str,
        network_name: str,
        metric_type: str,
        metric_data: dict[str, Any],
    ) -> None:
        """Process a single metric reading.

        Parameters
        ----------
        serial : str
            Device serial number.
        name : str
            Device name.
        model : str
            Device model.
        network_id : str
            Network ID.
        network_name : str
            Network name.
        metric_type : str
            Type of metric (temperature, humidity, etc.).
        metric_data : dict[str, Any]
            Metric-specific data.

        """
        # Validate parent exists
        if not self.parent:
            logger.error("Parent collector not set for MTCollector")
            return

        try:
            # Skip undocumented rawTemperature to avoid duplicate processing
            if metric_type == "rawTemperature":
                logger.debug(
                    "Skipping undocumented rawTemperature metric",
                    serial=serial,
                    metric_data=metric_data,
                )
                return

            if metric_type == "temperature":
                celsius = metric_data.get("celsius")
                if celsius is not None:
                    self._set_metric_value(
                        "_sensor_temperature",
                        {"serial": serial, "name": name, "sensor_type": model},
                        celsius,
                    )

            elif metric_type == "humidity":
                humidity = metric_data.get("relativePercentage")
                if humidity is not None:
                    self._set_metric_value(
                        "_sensor_humidity",
                        {"serial": serial, "name": name, "sensor_type": model},
                        humidity,
                    )

            elif metric_type == "door":
                is_open = metric_data.get("open")
                if is_open is not None:
                    self._set_metric_value(
                        "_sensor_door",
                        {"serial": serial, "name": name, "sensor_type": model},
                        1 if is_open else 0,
                    )

            elif metric_type == "water":
                # Note: The API example doesn't show water sensors, but keeping for completeness
                is_present = metric_data.get("present", False)
                self._set_metric_value(
                    "_sensor_water",
                    {"serial": serial, "name": name, "sensor_type": model},
                    1 if is_present else 0,
                )

            elif metric_type == "co2":
                concentration = metric_data.get("concentration")
                if concentration is not None:
                    self._set_metric_value(
                        "_sensor_co2",
                        {"serial": serial, "name": name, "sensor_type": model},
                        concentration,
                    )

            elif metric_type == "tvoc":
                concentration = metric_data.get("concentration")
                if concentration is not None:
                    self._set_metric_value(
                        "_sensor_tvoc",
                        {"serial": serial, "name": name, "sensor_type": model},
                        concentration,
                    )

            elif metric_type == "pm25":
                concentration = metric_data.get("concentration")
                if concentration is not None:
                    self._set_metric_value(
                        "_sensor_pm25",
                        {"serial": serial, "name": name, "sensor_type": model},
                        concentration,
                    )

            elif metric_type == "noise":
                ambient = metric_data.get("ambient", {})
                level = ambient.get("level")
                if level is not None:
                    self._set_metric_value(
                        "_sensor_noise",
                        {"serial": serial, "name": name, "sensor_type": model},
                        level,
                    )

            elif metric_type == "battery":
                percentage = metric_data.get("percentage")
                if percentage is not None:
                    self._set_metric_value(
                        "_sensor_battery",
                        {"serial": serial, "name": name, "sensor_type": model},
                        percentage,
                    )

            elif metric_type == "indoorAirQuality":
                score = metric_data.get("score")
                if score is not None:
                    self._set_metric_value(
                        "_sensor_air_quality",
                        {"serial": serial, "name": name, "sensor_type": model},
                        score,
                    )

            elif metric_type == "voltage":
                level = metric_data.get("level")
                if level is not None:
                    self._set_metric_value(
                        "_sensor_voltage",
                        {"serial": serial, "name": name, "sensor_type": model},
                        level,
                    )

            elif metric_type == "current":
                draw = metric_data.get("draw")
                if draw is not None:
                    self._set_metric_value(
                        "_sensor_current",
                        {"serial": serial, "name": name, "sensor_type": model},
                        draw,
                    )

            elif metric_type == "realPower":
                draw = metric_data.get("draw")
                if draw is not None:
                    self._set_metric_value(
                        "_sensor_real_power",
                        {"serial": serial, "name": name, "sensor_type": model},
                        draw,
                    )

            elif metric_type == "apparentPower":
                draw = metric_data.get("draw")
                if draw is not None:
                    self._set_metric_value(
                        "_sensor_apparent_power",
                        {"serial": serial, "name": name, "sensor_type": model},
                        draw,
                    )

            elif metric_type == "powerFactor":
                percentage = metric_data.get("percentage")
                if percentage is not None:
                    self._set_metric_value(
                        "_sensor_power_factor",
                        {"serial": serial, "name": name, "sensor_type": model},
                        percentage,
                    )

            elif metric_type == "frequency":
                level = metric_data.get("level")
                if level is not None:
                    self._set_metric_value(
                        "_sensor_frequency",
                        {"serial": serial, "name": name, "sensor_type": model},
                        level,
                    )

            elif metric_type == "downstreamPower":
                enabled = metric_data.get("enabled")
                if enabled is not None:
                    self._set_metric_value(
                        "_sensor_downstream_power",
                        {"serial": serial, "name": name, "sensor_type": model},
                        1 if enabled else 0,
                    )

            elif metric_type == "remoteLockoutSwitch":
                locked = metric_data.get("locked")
                if locked is not None:
                    self._set_metric_value(
                        "_sensor_remote_lockout",
                        {"serial": serial, "name": name, "sensor_type": model},
                        1 if locked else 0,
                    )

            else:
                logger.debug(
                    "Unknown sensor metric type",
                    serial=serial,
                    metric_type=metric_type,
                    metric_data=metric_data,
                )

        except Exception:
            logger.exception(
                "Failed to process sensor metric",
                serial=serial,
                metric_type=metric_type,
            )
