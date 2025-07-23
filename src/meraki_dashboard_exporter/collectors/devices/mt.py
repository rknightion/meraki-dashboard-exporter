"""Meraki MT (Sensor) metrics collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from meraki import DashboardAPI

from ...api.client import AsyncMerakiClient
from ...core.constants import (
    DeviceType,
    ProductType,
    SensorDataField,
    SensorMetricType,
    UpdateTier,
)
from ...core.domain_models import SensorMeasurement
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
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
            # Standalone mode - initialize base attributes without calling parent init
            # This avoids the "Parent collector not set" error
            self.parent = None  # type: ignore[assignment]
            self.api: DashboardAPI | None = None
            self.settings = None  # type: ignore[assignment]
            # Set a flag to indicate standalone mode for error checking
            self._standalone_mode = True

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
            # In standalone mode, tracking is not needed
            pass

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
        pass

    async def collect_sensor_metrics(
        self, org_id: str | None = None, org_name: str | None = None
    ) -> None:
        """Collect sensor metrics for all MT devices.

        This method handles the full sensor collection process including
        fetching devices and their readings.

        Parameters
        ----------
        org_id : str | None
            Organization ID. If None, collects for all orgs.
        org_name : str | None
            Organization name. If None, will be determined based on org_id.

        """
        try:
            # Get organizations
            if org_id:
                org_ids = [org_id]
            elif self.settings and self.settings.meraki.org_id:
                org_ids = [self.settings.meraki.org_id]
            else:
                if not self.api:
                    logger.error("API client not initialized")
                    return
                orgs = await self._fetch_organizations()
                org_ids = [org["id"] for org in orgs]

            # Collect sensors for each organization
            for organization_id in org_ids:
                try:
                    # Get org name if not provided
                    if org_name is None and organization_id == org_id:
                        current_org_name = org_name
                    else:
                        # Try to get org name from API
                        current_org_name = await self._get_org_name(organization_id)

                    await self._collect_org_sensors(organization_id, current_org_name)
                except Exception:
                    logger.exception(
                        "Failed to collect sensors for organization",
                        org_id=organization_id,
                    )
                    # Continue with next organization

        except Exception:
            logger.exception("Failed to collect sensor metrics")

    @log_api_call("getOrganizations")
    async def _fetch_organizations(self) -> list[dict[str, Any]]:
        """Fetch all organizations.

        Returns
        -------
        list[dict[str, Any]]
            List of organizations.

        """
        if self.api is None:
            raise RuntimeError("API client not initialized")
        # Access the API - self.api should already be the DashboardAPI
        return await asyncio.to_thread(self.api.organizations.getOrganizations)

    async def _get_org_name(self, org_id: str) -> str:
        """Get organization name.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        str
            Organization name or org_id if not found.

        """
        try:
            if self.api is None:
                return org_id
            org = await asyncio.to_thread(self.api.organizations.getOrganization, org_id)
            return str(org.get("name", org_id))
        except Exception:
            logger.debug("Failed to get org name", org_id=org_id)
            return org_id

    @log_api_call("getOrganizationDevices")
    async def _fetch_sensor_devices(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch sensor devices for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of sensor devices.

        """
        if self.api is None:
            raise RuntimeError("API client not initialized")
        return await asyncio.to_thread(
            self.api.organizations.getOrganizationDevices,
            org_id,
            total_pages="all",
            productTypes=[ProductType.SENSOR],
        )

    async def _collect_org_sensors(self, org_id: str, org_name: str | None = None) -> None:
        """Collect sensor metrics for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str | None
            Organization name.

        """
        try:
            if not self.api:
                logger.error("API client not initialized")
                return

            # Get all MT devices
            with LogContext(org_id=org_id):
                devices = await self._fetch_sensor_devices(org_id)

            if not devices:
                return

            # Extract sensor serials
            sensor_serials = [
                d["serial"] for d in devices if d.get("model", "").startswith(DeviceType.MT)
            ]

            if sensor_serials:
                # Create device lookup map with org info
                device_map = {}
                for d in devices:
                    d["orgId"] = org_id
                    d["orgName"] = org_name or org_id
                    device_map[d["serial"]] = d

                # Use async client for batch sensor reading
                client = AsyncMerakiClient(self.settings)
                readings = await client.get_sensor_readings_latest(org_id, sensor_serials)

                # Process readings
                self.collect_batch(readings, device_map)

        except Exception:
            logger.exception(
                "Failed to collect sensors for organization",
                org_id=org_id,
            )

    def _set_metric_value(
        self, metric_name: str, labels: dict[str, str], value: float | None
    ) -> None:
        """Safely set a metric value with validation.

        Parameters
        ----------
        metric_name : str
            Name of the metric attribute on parent.
        labels : dict[str, str]
            Labels to apply to the metric.
        value : float | None
            Value to set. If None, the metric will not be updated.

        """
        if value is None:
            return

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

            # Get network info from sensor data and merge with device
            network_info = sensor_data.get("network", {})
            device["networkId"] = network_info.get("id", device.get("networkId", ""))
            device["networkName"] = network_info.get(
                "name", device.get("networkName", device["networkId"])
            )

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
                        measurement = SensorMeasurement(metric=metric_type, value=value)
                        measurements.append(measurement)

                if measurements:
                    # Process validated measurements
                    for measurement in measurements:
                        self._process_validated_metric(device, measurement)
            except Exception as e:
                logger.debug(
                    "Failed to parse sensor data to domain model", serial=serial, error=str(e)
                )
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
                        device=device,
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
        if metric_type == SensorMetricType.TEMPERATURE:
            return metric_data.get(SensorDataField.CELSIUS)
        elif metric_type == SensorMetricType.HUMIDITY:
            return metric_data.get(SensorDataField.RELATIVE_PERCENTAGE)
        elif metric_type == SensorMetricType.DOOR:
            is_open = metric_data.get(SensorDataField.OPEN)
            return 1 if is_open else 0 if is_open is not None else None
        elif metric_type == SensorMetricType.WATER:
            is_present = metric_data.get(SensorDataField.PRESENT, False)
            return 1 if is_present else 0
        elif metric_type in {SensorMetricType.CO2, SensorMetricType.TVOC, SensorMetricType.PM25}:
            return metric_data.get(SensorDataField.CONCENTRATION)
        elif metric_type == SensorMetricType.NOISE:
            ambient = metric_data.get(SensorDataField.AMBIENT, {})
            level = ambient.get(SensorDataField.LEVEL) if isinstance(ambient, dict) else None
            return cast(float | None, level)
        elif metric_type == SensorMetricType.BATTERY:
            return metric_data.get(SensorDataField.PERCENTAGE)
        elif metric_type == SensorMetricType.INDOOR_AIR_QUALITY:
            return metric_data.get(SensorDataField.SCORE)
        elif metric_type == SensorMetricType.VOLTAGE:
            return metric_data.get(SensorDataField.LEVEL)
        elif metric_type == SensorMetricType.CURRENT:
            return metric_data.get(SensorDataField.DRAW)
        elif metric_type == SensorMetricType.REAL_POWER:
            return metric_data.get(SensorDataField.DRAW)
        elif metric_type == SensorMetricType.APPARENT_POWER:
            return metric_data.get(SensorDataField.DRAW)
        elif metric_type == SensorMetricType.POWER_FACTOR:
            return metric_data.get(SensorDataField.PERCENTAGE)
        elif metric_type == SensorMetricType.FREQUENCY:
            return metric_data.get(SensorDataField.LEVEL)
        elif metric_type == SensorMetricType.DOWNSTREAM_POWER:
            enabled = metric_data.get(SensorDataField.ENABLED)
            return 1 if enabled else 0 if enabled is not None else None
        elif metric_type == "remoteLockoutSwitch":
            locked = metric_data.get("locked")
            return 1 if locked else 0 if locked is not None else None
        return None

    def _process_validated_metric(
        self,
        device: dict[str, Any],
        measurement: SensorMeasurement,
    ) -> None:
        """Process a validated sensor measurement.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with org/network info.
        measurement : SensorMeasurement
            Validated sensor measurement.

        """
        metric_map = {
            SensorMetricType.TEMPERATURE: "_sensor_temperature",
            SensorMetricType.HUMIDITY: "_sensor_humidity",
            SensorMetricType.DOOR: "_sensor_door",
            SensorMetricType.WATER: "_sensor_water",
            SensorMetricType.CO2: "_sensor_co2",
            SensorMetricType.TVOC: "_sensor_tvoc",
            SensorMetricType.PM25: "_sensor_pm25",
            SensorMetricType.NOISE: "_sensor_noise",
            SensorMetricType.BATTERY: "_sensor_battery",
            SensorMetricType.INDOOR_AIR_QUALITY: "_sensor_air_quality",
            SensorMetricType.VOLTAGE: "_sensor_voltage",
            SensorMetricType.CURRENT: "_sensor_current",
            SensorMetricType.REAL_POWER: "_sensor_real_power",
            SensorMetricType.APPARENT_POWER: "_sensor_apparent_power",
            SensorMetricType.POWER_FACTOR: "_sensor_power_factor",
            SensorMetricType.FREQUENCY: "_sensor_frequency",
            SensorMetricType.DOWNSTREAM_POWER: "_sensor_downstream_power",
            "remoteLockoutSwitch": "_sensor_remote_lockout",
        }

        metric_attr = metric_map.get(measurement.metric)
        if metric_attr:
            # Extract org info from device data
            org_id = device.get("orgId", "")
            org_name = device.get("orgName", org_id)

            # Create standard device labels
            labels = create_device_labels(device, org_id=org_id, org_name=org_name)

            self._set_metric_value(
                metric_attr,
                labels,
                measurement.value,
            )

    def _process_metric(
        self,
        device: dict[str, Any],
        metric_type: str,
        metric_data: dict[str, Any],
    ) -> None:
        """Process a single metric reading.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with org/network info.
        metric_type : str
            Type of metric (temperature, humidity, etc.).
        metric_data : dict[str, Any]
            Metric-specific data.

        """
        # Validate parent exists (skip check in standalone mode)
        if not self.parent and not getattr(self, "_standalone_mode", False):
            logger.error("Parent collector not set for MTCollector")
            return

        # Extract org info from device data
        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)

        # Create standard device labels
        labels = create_device_labels(device, org_id=org_id, org_name=org_name)

        try:
            # Skip undocumented rawTemperature to avoid duplicate processing
            if metric_type == "rawTemperature":
                return

            if metric_type == SensorMetricType.TEMPERATURE:
                celsius = metric_data.get(SensorDataField.CELSIUS)
                if celsius is not None:
                    self._set_metric_value(
                        "_sensor_temperature",
                        labels,
                        celsius,
                    )

            elif metric_type == SensorMetricType.HUMIDITY:
                humidity = metric_data.get(SensorDataField.RELATIVE_PERCENTAGE)
                if humidity is not None:
                    self._set_metric_value(
                        "_sensor_humidity",
                        labels,
                        humidity,
                    )

            elif metric_type == SensorMetricType.DOOR:
                is_open = metric_data.get(SensorDataField.OPEN)
                if is_open is not None:
                    self._set_metric_value(
                        "_sensor_door",
                        labels,
                        1 if is_open else 0,
                    )

            elif metric_type == SensorMetricType.WATER:
                # Note: The API example doesn't show water sensors, but keeping for completeness
                is_present = metric_data.get(SensorDataField.PRESENT, False)
                self._set_metric_value(
                    "_sensor_water",
                    labels,
                    1 if is_present else 0,
                )

            elif metric_type == SensorMetricType.CO2:
                concentration = metric_data.get(SensorDataField.CONCENTRATION)
                if concentration is not None:
                    self._set_metric_value(
                        "_sensor_co2",
                        labels,
                        concentration,
                    )

            elif metric_type == SensorMetricType.TVOC:
                concentration = metric_data.get(SensorDataField.CONCENTRATION)
                if concentration is not None:
                    self._set_metric_value(
                        "_sensor_tvoc",
                        labels,
                        concentration,
                    )

            elif metric_type == SensorMetricType.PM25:
                concentration = metric_data.get(SensorDataField.CONCENTRATION)
                if concentration is not None:
                    self._set_metric_value(
                        "_sensor_pm25",
                        labels,
                        concentration,
                    )

            elif metric_type == SensorMetricType.NOISE:
                ambient = metric_data.get(SensorDataField.AMBIENT, {})
                level = ambient.get(SensorDataField.LEVEL)
                if level is not None:
                    self._set_metric_value(
                        "_sensor_noise",
                        labels,
                        level,
                    )

            elif metric_type == SensorMetricType.BATTERY:
                percentage = metric_data.get(SensorDataField.PERCENTAGE)
                if percentage is not None:
                    self._set_metric_value(
                        "_sensor_battery",
                        labels,
                        percentage,
                    )

            elif metric_type == SensorMetricType.INDOOR_AIR_QUALITY:
                score = metric_data.get(SensorDataField.SCORE)
                if score is not None:
                    self._set_metric_value(
                        "_sensor_air_quality",
                        labels,
                        score,
                    )

            elif metric_type == SensorMetricType.VOLTAGE:
                level = metric_data.get(SensorDataField.LEVEL)
                if level is not None:
                    self._set_metric_value(
                        "_sensor_voltage",
                        labels,
                        level,
                    )

            elif metric_type == SensorMetricType.CURRENT:
                draw = metric_data.get(SensorDataField.DRAW)
                if draw is not None:
                    self._set_metric_value(
                        "_sensor_current",
                        labels,
                        draw,
                    )

            elif metric_type == SensorMetricType.REAL_POWER:
                draw = metric_data.get(SensorDataField.DRAW)
                if draw is not None:
                    self._set_metric_value(
                        "_sensor_real_power",
                        labels,
                        draw,
                    )

            elif metric_type == SensorMetricType.APPARENT_POWER:
                draw = metric_data.get(SensorDataField.DRAW)
                if draw is not None:
                    self._set_metric_value(
                        "_sensor_apparent_power",
                        labels,
                        draw,
                    )

            elif metric_type == SensorMetricType.POWER_FACTOR:
                percentage = metric_data.get(SensorDataField.PERCENTAGE)
                if percentage is not None:
                    self._set_metric_value(
                        "_sensor_power_factor",
                        labels,
                        percentage,
                    )

            elif metric_type == SensorMetricType.FREQUENCY:
                level = metric_data.get(SensorDataField.LEVEL)
                if level is not None:
                    self._set_metric_value(
                        "_sensor_frequency",
                        labels,
                        level,
                    )

            elif metric_type == SensorMetricType.DOWNSTREAM_POWER:
                enabled = metric_data.get(SensorDataField.ENABLED)
                if enabled is not None:
                    self._set_metric_value(
                        "_sensor_downstream_power",
                        labels,
                        1 if enabled else 0,
                    )

            elif metric_type == "remoteLockoutSwitch":
                locked = metric_data.get("locked")
                if locked is not None:
                    self._set_metric_value(
                        "_sensor_remote_lockout",
                        labels,
                        1 if locked else 0,
                    )

            else:
                logger.debug(
                    "Unknown sensor metric type",
                    serial=device.get("serial", ""),
                    metric_type=metric_type,
                    metric_data=metric_data,
                )

        except Exception:
            logger.exception(
                "Failed to process sensor metric",
                serial=device.get("serial", ""),
                metric_type=metric_type,
            )
