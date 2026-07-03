"""Meraki MT (Sensor) metrics collector."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, cast

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ...core.config import Settings
    from ..device import DeviceCollector

from ...core.constants import (
    DeviceType,
    ProductType,
    SensorDataField,
    SensorMetricType,
)
from ...core.domain_models import SensorGatewayConnection, SensorMeasurement
from ...core.error_handling import ErrorCategory, NothingCollectedError, validate_response_format
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.metrics import create_labels
from ...core.scheduler import EndpointGroupName
from .base import BaseDeviceCollector

logger = get_logger(__name__)


class MTCollector(BaseDeviceCollector):
    """Collector for Meraki MT (Sensor) devices.

    This collector handles both device-level metrics (through DeviceCollector)
    and sensor-specific environmental metrics with FAST tier updates.
    """

    # Sensor data updates frequently

    # Shared rate limiter. None for sub-collectors (the @log_api_call decorator
    # falls back to self.parent.rate_limiter); set directly by as_standalone (#270).
    rate_limiter: Any | None = None

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MT collector as a sub-collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance.

        """
        super().__init__(parent)

    @classmethod
    def as_subcollector(cls, parent: DeviceCollector) -> MTCollector:
        """Create as a sub-collector of DeviceCollector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance.

        Returns
        -------
        MTCollector
            Initialized sub-collector.

        """
        return cls(parent)

    @classmethod
    def as_standalone(
        cls,
        api: DashboardAPI,
        settings: Settings,
        rate_limiter: Any | None = None,
    ) -> MTCollector:
        """Create as an independent collector for MTSensorCollector.

        Parameters
        ----------
        api : DashboardAPI
            Meraki API client.
        settings : Settings
            Application settings.
        rate_limiter : Any | None
            Shared OrgRateLimiter. Threaded through so the standalone MT
            fetchers (parent is None) still throttle via @log_api_call, which
            resolves ``self.rate_limiter`` (#270).

        Returns
        -------
        MTCollector
            Initialized standalone collector.

        """
        instance = object.__new__(cls)
        instance.parent = None
        instance.api = api
        instance.settings = settings
        instance.rate_limiter = rate_limiter
        return instance

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

        Raises
        ------
        NothingCollectedError
            If organizations were present but every org's sensor collection
            failed (#509) — a total-failure cycle must surface as a failure,
            not a silently-swallowed success.

        """
        # Prefer the shared inventory cache (injected on the parent) over
        # per-cycle API calls on the FAST 60s tier.
        inventory = self.parent.inventory if self.parent is not None else None

        # Get organizations
        if org_id:
            org_ids = [org_id]
        elif self.settings and self.settings.meraki.org_id:
            org_ids = [self.settings.meraki.org_id]
        elif inventory is not None:
            orgs = await inventory.get_organizations()
            org_ids = [org["id"] for org in orgs]
        else:
            if not self.api:
                logger.error("API client not initialized")
                return
            orgs = await self._fetch_organizations()
            org_ids = [org["id"] for org in orgs]

        # #617: gate both org-wide fetches (readings + gateway connections) as a
        # single endpoint group. Compute due-ness once; the fetch sites re-check
        # (fail-open) and this heartbeat marks the group ran only on success so
        # the scheduler's last-ran clock advances exactly once per real cycle.
        group = EndpointGroupName.MT_SENSOR_READINGS
        due = self.parent._should_run_group(group) if self.parent is not None else True

        # Collect sensors for each organization
        succeeded = 0
        failed = 0
        for organization_id in org_ids:
            try:
                # Reuse a caller-provided org_name for the requested org;
                # otherwise resolve it (from the inventory cache when available).
                if org_name is not None and organization_id == org_id:
                    current_org_name = org_name
                else:
                    current_org_name = await self._get_org_name(organization_id)

                await self._collect_org_sensors(organization_id, current_org_name, due=due)
                succeeded += 1
                await self._collect_org_gateway_connections(
                    organization_id, current_org_name, due=due
                )
            except Exception:
                logger.exception(
                    "Failed to collect sensors for organization",
                    org_id=organization_id,
                )
                if self.parent is not None:
                    self.parent._track_error(ErrorCategory.UNKNOWN)
                failed += 1
                # Continue with next organization

        if org_ids and succeeded == 0 and failed > 0:
            raise NothingCollectedError(
                self.__class__.__name__,
                attempted=len(org_ids),
                failed=failed,
            )

        # Mark the group ran only when it was due and at least one org succeeded.
        if due and succeeded > 0 and self.parent is not None:
            self.parent._mark_group_ran(group)

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
        raw = await asyncio.to_thread(self.api.organizations.getOrganizations)
        return cast(
            list[dict[str, Any]],
            validate_response_format(raw, expected_type=list, operation="getOrganizations"),
        )

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
            # Prefer the shared inventory cache to avoid a per-cycle getOrganization
            # call on the FAST tier.
            inventory = self.parent.inventory if self.parent is not None else None
            if inventory is not None:
                for org in await inventory.get_organizations():
                    if org.get("id") == org_id:
                        return str(org.get("name", org_id))

            if self.api is None:
                return org_id
            # Fallback direct call (no @log_api_call here): throttle explicitly.
            rate_limiter = (
                getattr(self.parent, "rate_limiter", None) if self.parent is not None else None
            )
            if rate_limiter is not None:
                await rate_limiter.acquire(org_id, "getOrganization")
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
        raw = await asyncio.to_thread(
            self.api.organizations.getOrganizationDevices,
            org_id,
            total_pages="all",
            productTypes=[ProductType.SENSOR],
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(raw, expected_type=list, operation="getOrganizationDevices"),
        )

    @log_api_call("getOrganizationSensorReadingsLatest")
    async def _fetch_sensor_readings(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch the latest sensor readings for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID. Also consumed by the ``@log_api_call`` decorator so
            the client-side ``OrgRateLimiter`` acquires against this org's
            budget (#553) instead of skipping rate-limiting entirely.

        Returns
        -------
        list[dict[str, Any]]
            List of sensor readings for every sensor in the organization.

        Notes
        -----
        Deliberately does NOT pass ``serials`` (#553): the org-wide endpoint
        already returns readings for every sensor without it, and passing every
        known serial explicitly only bloats the request. Sensors outside the
        locally-built ``device_map`` (e.g. filtered out by ``NetworkFilter``)
        are simply skipped in ``collect_batch``.

        """
        if self.api is None:
            raise RuntimeError("API client not initialized")
        raw = await asyncio.to_thread(
            self.api.sensor.getOrganizationSensorReadingsLatest,
            org_id,
            total_pages="all",
            # perPage 3-1000, default 1000 — pin the max explicitly so the
            # per-cycle page count is deterministic and matches the group
            # cost_fn's pages(sensor_count, 1000) term (live-verified 2026-07-03,
            # org 1019781; #630).
            perPage=1000,
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                raw, expected_type=list, operation="getOrganizationSensorReadingsLatest"
            ),
        )

    async def _collect_org_sensors(
        self, org_id: str, org_name: str | None = None, *, due: bool = True
    ) -> None:
        """Collect sensor metrics for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str | None
            Organization name.
        due : bool
            Whether the ``MT_SENSOR_READINGS`` group is due this cycle. Computed
            once by the caller (``collect_sensor_metrics``) and threaded in — the
            gate must not be re-evaluated here because ``_should_run_group``
            mutates the scheduler's attempt clock, so a second call would look
            like a failed retry and suppress the fetch on cold start.

        """
        try:
            if not self.api:
                logger.error("API client not initialized")
                return

            # #617 gate: skip the sensor-readings fetch when the group is not due.
            if not due:
                return

            inventory = self.parent.inventory if self.parent is not None else None

            # Get MT devices. Prefer the shared inventory cache (also enforces the
            # configured NetworkFilter); fall back to a direct fetch when inventory
            # is unavailable.
            with LogContext(org_id=org_id):
                if inventory is not None:
                    devices = await inventory.get_devices(org_id)
                else:
                    devices = await self._fetch_sensor_devices(org_id)

            if not devices:
                return

            # Org-wide device list may reference networks outside the configured
            # NetworkFilter — resolve the allow-list and skip excluded rows.
            allowed_network_ids = (
                await inventory.get_allowed_network_ids(org_id) if inventory is not None else None
            )

            # Build device lookup map (with org info) for MT sensors only.
            sensor_serials: list[str] = []
            device_map: dict[str, dict[str, Any]] = {}
            for d in devices:
                if not d.get("model", "").startswith(DeviceType.MT):
                    continue
                if (
                    allowed_network_ids is not None
                    and d.get("networkId", "") not in allowed_network_ids
                ):
                    continue
                d["orgId"] = org_id
                d["orgName"] = org_name or org_id
                device_map[d["serial"]] = d
                sensor_serials.append(d["serial"])

            if sensor_serials:
                # Use the shared API client (respects the global concurrency limit)
                # instead of constructing a new AsyncMerakiClient per cycle (#249).
                readings = await self._fetch_sensor_readings(org_id)

                # Process readings (#617: thread the group's per-series TTL so a
                # stretched-interval poll does not flap the emitted series).
                ttl_seconds = (
                    self.parent._group_ttl_seconds(EndpointGroupName.MT_SENSOR_READINGS)
                    if self.parent is not None
                    else None
                )
                self.collect_batch(readings, device_map, ttl_seconds=ttl_seconds)

        except Exception:
            logger.exception(
                "Failed to collect sensors for organization",
                org_id=org_id,
            )
            raise

    @log_api_call("getOrganizationSensorGatewaysConnectionsLatest")
    async def _fetch_gateway_connections(self, org_id: str) -> list[dict[str, Any]]:
        """Fetch latest sensor-to-gateway connectivity for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.

        Returns
        -------
        list[dict[str, Any]]
            List of sensor-to-gateway connection data.

        """
        if self.api is None:
            raise RuntimeError("API client not initialized")
        raw = await asyncio.to_thread(
            self.api.sensor.getOrganizationSensorGatewaysConnectionsLatest,
            org_id,
            total_pages="all",
        )
        return cast(
            list[dict[str, Any]],
            validate_response_format(
                raw,
                expected_type=list,
                operation="getOrganizationSensorGatewaysConnectionsLatest",
            ),
        )

    async def _collect_org_gateway_connections(
        self, org_id: str, org_name: str | None = None, *, due: bool = True
    ) -> None:
        """Collect sensor-to-gateway connectivity for an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str | None
            Organization name.
        due : bool
            Whether the ``MT_SENSOR_READINGS`` group is due this cycle, computed
            once by the caller and threaded in (the gate must not be re-evaluated
            here — ``_should_run_group`` mutates the scheduler attempt clock).

        """
        try:
            if not self.api:
                logger.error("API client not initialized")
                return

            # #617 gate: sensor-to-gateway connections share the readings group.
            # ``due`` is threaded in from the caller — do not re-evaluate the gate
            # here (``_should_run_group`` mutates the scheduler attempt clock).
            if not due:
                return

            with LogContext(org_id=org_id):
                connections = await self._fetch_gateway_connections(org_id)

            if not connections:
                return

            # Org-wide endpoint - enforce NetworkFilter (rows may reference networks
            # outside the configured filter).
            allowed_network_ids = (
                await self.parent.inventory.get_allowed_network_ids(org_id)
                if self.parent is not None and self.parent.inventory is not None
                else None
            )

            ttl_seconds = (
                self.parent._group_ttl_seconds(EndpointGroupName.MT_SENSOR_READINGS)
                if self.parent is not None
                else None
            )

            for raw_item in connections:
                item = SensorGatewayConnection.model_validate(raw_item)
                network_id = item.network.id

                if allowed_network_ids is not None and network_id not in allowed_network_ids:
                    continue

                labels = create_labels(
                    org_id=org_id,
                    network_id=network_id,
                    serial=item.sensor.serial,
                    gateway_serial=item.gateway.serial,
                )

                self._set_metric_value(
                    "_sensor_gateway_rssi", labels, item.rssi, ttl_seconds=ttl_seconds
                )

                epoch = self._parse_iso_timestamp(item.lastConnectedAt)
                self._set_metric_value(
                    "_sensor_gateway_last_connected", labels, epoch, ttl_seconds=ttl_seconds
                )

        except Exception:
            logger.exception(
                "Failed to collect sensor gateway connections for organization",
                org_id=org_id,
            )
            if self.parent is not None:
                self.parent._track_error(ErrorCategory.UNKNOWN)

    @staticmethod
    def _parse_iso_timestamp(value: str | None) -> float | None:
        """Parse an ISO-8601 timestamp string into epoch seconds.

        Parameters
        ----------
        value : str | None
            ISO-8601 timestamp, e.g. "2024-01-01T00:00:00Z".

        Returns
        -------
        float | None
            Epoch seconds, or None if the value is missing/unparseable.

        """
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError, TypeError:
            logger.debug("Failed to parse gateway connection timestamp", value=value)
            return None

    # NOTE: MTCollector intentionally does NOT override ``_set_metric_value``.
    # It inherits ``SubCollectorMixin._set_metric_value`` (via BaseDeviceCollector),
    # which delegates to ``self.parent._set_metric_value`` — i.e.
    # ``MetricCollector._set_metric_value`` on the owning MTSensorCollector — so every
    # MT sensor/gateway gauge is routed through ``_set_metric`` and registered with the
    # expiration manager for automatic stale-series cleanup (issues #246 / #269).

    def collect_batch(
        self,
        sensor_readings: list[dict[str, Any]],
        device_map: dict[str, dict[str, Any]],
        ttl_seconds: float | None = None,
    ) -> None:
        """Collect sensor metrics from batch API response.

        Parameters
        ----------
        sensor_readings : list[dict[str, Any]]
            List of sensor readings from the API.
        device_map : dict[str, dict[str, Any]]
            Mapping of serial numbers to device info.
        ttl_seconds : float | None
            Fully-resolved per-series TTL for the ``mt_sensor_readings`` group
            (#617 §1f), threaded to every emitted series. ``None`` ⇒ tier TTL.

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

            # MT20/MT30 button presses (#303): handled separately from the
            # generic per-metric loop below because it needs an extra
            # press_type label + the reading's own `ts` (not a metric_data
            # value) - the standard SensorMeasurement/_METRIC_ATTR_BY_TYPE path
            # only carries a bare device-labeled value.
            for reading in sensor_data.get("readings", []):
                if reading.get("metric") == SensorMetricType.BUTTON:
                    self._process_button_reading(device, reading, ttl_seconds=ttl_seconds)

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
                        self._process_validated_metric(device, measurement, ttl_seconds=ttl_seconds)
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
                        ttl_seconds=ttl_seconds,
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
        elif metric_type in {
            SensorMetricType.CO2,
            SensorMetricType.TVOC,
            SensorMetricType.PM25,
            SensorMetricType.NO2,
            SensorMetricType.O3,
            SensorMetricType.PM10,
        }:
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

    # Maps a sensor metric type (or the ``remoteLockoutSwitch`` raw key) to its
    # gauge attribute name. Shared by ``_process_validated_metric`` and the
    # ``_process_metric`` fallback so the two paths can never diverge.
    _METRIC_ATTR_BY_TYPE: ClassVar[dict[str, str]] = {
        SensorMetricType.TEMPERATURE: "_sensor_temperature",
        SensorMetricType.HUMIDITY: "_sensor_humidity",
        SensorMetricType.DOOR: "_sensor_door",
        SensorMetricType.WATER: "_sensor_water",
        SensorMetricType.CO2: "_sensor_co2",
        SensorMetricType.TVOC: "_sensor_tvoc",
        SensorMetricType.PM25: "_sensor_pm25",
        SensorMetricType.NO2: "_sensor_no2",
        SensorMetricType.O3: "_sensor_o3",
        SensorMetricType.PM10: "_sensor_pm10",
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

    def _process_button_reading(
        self,
        device: dict[str, Any],
        reading: dict[str, Any],
        ttl_seconds: float | None = None,
    ) -> None:
        """Process an MT20/MT30 button-press reading (#303).

        Rides the existing ``getOrganizationSensorReadingsLatest`` fetch (no
        new API call). Emits the epoch-seconds timestamp of the reading as the
        last-observed press per ``press_type`` (short/long). Because this is
        polling-based, individual presses between polling cycles are not
        guaranteed to be captured - see the HELP string on
        ``MT_BUTTON_LAST_PRESS_TIMESTAMP_SECONDS``; the webhook
        ``sensorAlert`` event is the reliable path for capturing every press.

        ⚠ Phase-6 LIVE VERIFICATION: the response shape (``button.pressType``,
        reading-level ``ts``) has not been confirmed against a live MT20/MT30 -
        none exist in the homelab. Absent rows for orgs without one of these
        models is the documented normal case.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with org/network info.
        reading : dict[str, Any]
            A single raw reading entry (one ``metric``/``ts`` pair).
        ttl_seconds : float | None
            Fully-resolved per-series TTL for the ``mt_sensor_readings`` group
            (#617 §1f). ``None`` ⇒ tier-derived TTL.

        """
        metric_data = reading.get(SensorMetricType.BUTTON)
        if not isinstance(metric_data, dict) or not metric_data:
            return

        press_type = metric_data.get(SensorDataField.PRESS_TYPE)
        if press_type not in {"short", "long"}:
            logger.debug(
                "Unexpected or missing MT button pressType",
                serial=device.get("serial", ""),
                press_type=press_type,
            )
            return

        ts = reading.get("ts")
        epoch = self._parse_iso_timestamp(ts) if isinstance(ts, str) else None
        if epoch is None:
            return

        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)
        labels = create_device_labels(
            device, org_id=org_id, org_name=org_name, press_type=press_type
        )
        self._set_metric_value(
            "_sensor_button_last_press",
            labels,
            epoch,
            ttl_seconds=ttl_seconds,
        )

    def _process_validated_metric(
        self,
        device: dict[str, Any],
        measurement: SensorMeasurement,
        ttl_seconds: float | None = None,
    ) -> None:
        """Process a validated sensor measurement.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with org/network info.
        measurement : SensorMeasurement
            Validated sensor measurement.
        ttl_seconds : float | None
            Fully-resolved per-series TTL for the ``mt_sensor_readings`` group
            (#617 §1f). ``None`` ⇒ tier-derived TTL.

        """
        metric_attr = self._METRIC_ATTR_BY_TYPE.get(measurement.metric)
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
                ttl_seconds=ttl_seconds,
            )

    def _process_metric(
        self,
        device: dict[str, Any],
        metric_type: str,
        metric_data: dict[str, Any],
        ttl_seconds: float | None = None,
    ) -> None:
        """Process a single metric reading (fallback when domain validation fails).

        Parameters
        ----------
        device : dict[str, Any]
            Device data with org/network info.
        metric_type : str
            Type of metric (temperature, humidity, etc.).
        metric_data : dict[str, Any]
            Metric-specific data.
        ttl_seconds : float | None
            Fully-resolved per-series TTL for the ``mt_sensor_readings`` group
            (#617 §1f). ``None`` ⇒ tier-derived TTL.

        """
        # Validate parent exists (skip check in standalone mode)
        if not self.parent:
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

            metric_attr = self._METRIC_ATTR_BY_TYPE.get(metric_type)
            if metric_attr is None:
                logger.debug(
                    "Unknown sensor metric type",
                    serial=device.get("serial", ""),
                    metric_type=metric_type,
                    metric_data=metric_data,
                )
                return

            # Reuse the shared extractor so value semantics match the validated
            # path exactly (door/water/downstream/lockout coercions included).
            value = self._extract_metric_value(metric_type, metric_data)
            if value is None:
                return

            self._set_metric_value(
                metric_attr,
                labels,
                value,
                ttl_seconds=ttl_seconds,
            )

        except Exception:
            logger.exception(
                "Failed to process sensor metric",
                serial=device.get("serial", ""),
                metric_type=metric_type,
            )
            if self.parent is not None:
                self.parent._track_error(ErrorCategory.UNKNOWN)
