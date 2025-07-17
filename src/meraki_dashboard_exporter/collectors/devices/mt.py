"""Meraki MT (Sensor) metrics collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...api.client import AsyncMerakiClient
from ...core.constants import UpdateTier
from ...core.domain_models import MTSensorReading, SensorMeasurement
from ...core.logging import get_logger
from .base import BaseDeviceCollector

if TYPE_CHECKING:

    from ..device import DeviceCollector

logger = get_logger(__name__)


class MTCollector(BaseDeviceCollector):
    """Collector for Meraki MT (Sensor) devices.
    
    This collector handles both device-level metrics (through DeviceCollector)
    and sensor-specific environmental metrics with FAST tier updates.
    """
    
    # Sensor data updates frequently
    update_tier: UpdateTier = UpdateTier.FAST

    def __init__(self, parent: DeviceCollector | None = None) -> None:
        """Initialize MT collector.
        
        Parameters
        ----------
        parent : DeviceCollector | None
            Parent DeviceCollector instance. If None, this collector
            operates in standalone sensor mode.
            
        """
        if parent:
            super().__init__(parent)
        else:
            # Standalone mode - initialize without parent
            self.parent = None
            self.api = None  # Will be set later
            self.settings = None  # Will be set later
    
    def _track_api_call(self, method_name: str) -> None:
        """Track API call, handling standalone mode.
        
        Parameters
        ----------
        method_name : str
            Name of the API method being called.
            
        """
        if self.parent and hasattr(self.parent, "_track_api_call"):
            self.parent._track_api_call(method_name)
        else:
            # In standalone mode, just log
            logger.debug("API call tracked", method=method_name)
    
    async def collect(self, device: dict[str, Any]) -> None:
        """Collect device-level MT metrics.
        
        This is called by DeviceCollector for each MT device.
        
        Parameters
        ----------
        device : dict[str, Any]
            Device data from Meraki API.
            
        """
        # MT devices don't have device-specific metrics beyond common ones
        # Their main metrics come from sensor readings
        logger.debug(
            "MT device metrics collection (device-level)",
            serial=device.get("serial"),
            name=device.get("name"),
        )
    
    async def collect_sensor_metrics(self, org_id: str | None = None) -> None:
        """Collect sensor metrics for all MT devices.
        
        This method handles the full sensor collection process including
        fetching devices and their readings.
        
        Parameters
        ----------
        org_id : str | None
            Organization ID. If None, collects for all orgs.
            
        """
        try:
            # Get organizations
            if org_id:
                org_ids = [org_id]
            elif self.settings and self.settings.org_id:
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
                self.collect_batch(readings, device_map)

        except Exception:
            logger.exception(
                "Failed to collect sensors for organization",
                org_id=org_id,
            )

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
            
            # Try to parse to domain model for validation
            try:
                measurements = []
                for reading in sensor_data.get("readings", []):
                    metric_type = reading.get("metric")
                    if not metric_type:
                        continue
                    # Skip undocumented rawTemperature
                    if metric_type == "rawTemperature":
                        continue
                    # Extract the metric-specific data
                    metric_data = reading.get(metric_type, {})
                    if not metric_data:
                        continue
                    # Extract value based on metric type
                    value = self._extract_metric_value(metric_type, metric_data)
                    if value is not None:
                        measurement = SensorMeasurement(
                            metric=metric_type,
                            value=value
                        )
                        measurements.append(measurement)
                
                if measurements:
                    # Process validated measurements
                    for measurement in measurements:
                        self._process_validated_metric(
                            serial, name, model, network_id, network_name, measurement
                        )
            except Exception as e:
                logger.debug("Failed to parse sensor data to domain model", serial=serial, error=str(e))
                # Fall back to direct processing
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

    def _extract_metric_value(self, metric_type: str, metric_data: dict[str, Any]) -> float | None:
        """Extract metric value from raw API data.
        
        Parameters
        ----------
        metric_type : str
            Type of metric.
        metric_data : dict[str, Any]
            Raw metric data from API.
            
        Returns
        -------
        float | None
            Extracted value or None if not found.
        """
        if metric_type == "temperature":
            return metric_data.get("celsius")
        elif metric_type == "humidity":
            return metric_data.get("relativePercentage")
        elif metric_type == "door":
            is_open = metric_data.get("open")
            return 1 if is_open else 0 if is_open is not None else None
        elif metric_type == "water":
            is_present = metric_data.get("present", False)
            return 1 if is_present else 0
        elif metric_type in ("co2", "tvoc", "pm25"):
            return metric_data.get("concentration")
        elif metric_type == "noise":
            ambient = metric_data.get("ambient", {})
            return ambient.get("level")
        elif metric_type == "battery":
            return metric_data.get("percentage")
        elif metric_type == "indoorAirQuality":
            return metric_data.get("score")
        elif metric_type == "voltage":
            return metric_data.get("level")
        elif metric_type == "current":
            return metric_data.get("draw")
        elif metric_type == "realPower":
            return metric_data.get("draw")
        elif metric_type == "apparentPower":
            return metric_data.get("draw")
        elif metric_type == "powerFactor":
            return metric_data.get("percentage")
        elif metric_type == "frequency":
            return metric_data.get("level")
        elif metric_type == "downstreamPower":
            enabled = metric_data.get("enabled")
            return 1 if enabled else 0 if enabled is not None else None
        elif metric_type == "remoteLockoutSwitch":
            locked = metric_data.get("locked")
            return 1 if locked else 0 if locked is not None else None
        return None
    
    def _process_validated_metric(
        self,
        serial: str,
        name: str,
        model: str,
        network_id: str,
        network_name: str,
        measurement: SensorMeasurement,
    ) -> None:
        """Process a validated sensor measurement.
        
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
        measurement : SensorMeasurement
            Validated sensor measurement.
        """
        metric_map = {
            "temperature": "_sensor_temperature",
            "humidity": "_sensor_humidity",
            "door": "_sensor_door",
            "water": "_sensor_water",
            "co2": "_sensor_co2",
            "tvoc": "_sensor_tvoc",
            "pm25": "_sensor_pm25",
            "noise": "_sensor_noise",
            "battery": "_sensor_battery",
            "indoorAirQuality": "_sensor_air_quality",
            "voltage": "_sensor_voltage",
            "current": "_sensor_current",
            "realPower": "_sensor_real_power",
            "apparentPower": "_sensor_apparent_power",
            "powerFactor": "_sensor_power_factor",
            "frequency": "_sensor_frequency",
            "downstreamPower": "_sensor_downstream_power",
            "remoteLockoutSwitch": "_sensor_remote_lockout",
        }
        
        metric_attr = metric_map.get(measurement.metric)
        if metric_attr:
            self._set_metric_value(
                metric_attr,
                {"serial": serial, "name": name, "sensor_type": model},
                measurement.value,
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
