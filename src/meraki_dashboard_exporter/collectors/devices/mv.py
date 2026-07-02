"""MV security camera collector."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from ...core.constants import MVMetricName
from ...core.domain_models import (
    CameraAnalyticsLive,
    CameraAnalyticsZone,
    CameraQualityAndRetention,
)
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName, create_labels
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    from ..device import DeviceCollector

logger = get_logger(__name__)


class MVCollector(BaseDeviceCollector):
    """Collector for MV security camera metrics."""

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MV collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance.

        """
        super().__init__(parent)

        # Tracks the last time near-static per-camera config (analytics zones,
        # quality/retention) was collected, keyed by serial, so the SLOW
        # cadence can be self-enforced even though collect() is dispatched
        # every MEDIUM-tier (300s) cycle by DeviceCollector's per-device
        # fan-out (see F-027). Mirrors the
        # _should_collect_firewall_rules/_should_collect_port_usage throttle
        # pattern in mx_firewall.py/ms.py.
        self._last_static_config_collection: dict[str, float] = {}
        # Cache of the last known zone_id -> zone_label map per camera
        # serial, so meraki_mv_zone_info (the id-keyed join carrier for
        # zone_name, issue #534) can still be re-emitted on cycles where the
        # SLOW-gated zones call is skipped - the id-only meraki_mv_people_count
        # series would otherwise have no live zone_name join target between
        # zones-API fetches.
        self._last_zone_maps: dict[str, dict[str, str]] = {}

        # Common device label set shared by every MV gauge. Kept as a local
        # variable (not a module constant) so the metrics doc generator, which
        # resolves function-local label lists, picks up the full label set.
        # ID-only (issue #534, Option B) - the device display name joins via
        # meraki_device_status_info on serial.
        device_labels = [
            LabelName.ORG_ID.value,
            LabelName.NETWORK_ID.value,
            LabelName.SERIAL.value,
            LabelName.MODEL.value,
            LabelName.DEVICE_TYPE.value,
        ]

        self._mv_people_count = self.parent._create_gauge(
            MVMetricName.MV_PEOPLE_COUNT,
            "Current person count reported by MV camera analytics zone",
            labelnames=[
                LabelName.ORG_ID.value,
                LabelName.NETWORK_ID.value,
                LabelName.SERIAL.value,
                LabelName.MODEL.value,
                LabelName.DEVICE_TYPE.value,
                LabelName.ZONE_ID.value,
            ],
        )
        self._mv_zone_info = self.parent._create_gauge(
            MVMetricName.MV_ZONE_INFO,
            "MV camera analytics zone ID to zone name mapping (1 = present)",
            labelnames=[
                LabelName.ORG_ID.value,
                LabelName.NETWORK_ID.value,
                LabelName.SERIAL.value,
                LabelName.ZONE_ID.value,
                LabelName.ZONE_NAME.value,
            ],
        )
        self._mv_analytics_zones = self.parent._create_gauge(
            MVMetricName.MV_ANALYTICS_ZONES,
            "Number of configured analytics zones on the MV camera",
            labelnames=device_labels,
        )
        self._mv_motion_based_retention_enabled = self.parent._create_gauge(
            MVMetricName.MV_MOTION_BASED_RETENTION_ENABLED,
            "Whether motion-based retention is enabled (1 = enabled)",
            labelnames=device_labels,
        )
        self._mv_audio_recording_enabled = self.parent._create_gauge(
            MVMetricName.MV_AUDIO_RECORDING_ENABLED,
            "Whether audio recording is enabled (1 = enabled)",
            labelnames=device_labels,
        )
        self._mv_restricted_bandwidth_mode_enabled = self.parent._create_gauge(
            MVMetricName.MV_RESTRICTED_BANDWIDTH_MODE_ENABLED,
            "Whether restricted bandwidth mode is enabled (1 = enabled)",
            labelnames=device_labels,
        )
        self._mv_quality_retention_info = self.parent._create_gauge(
            MVMetricName.MV_QUALITY_RETENTION_INFO,
            "MV camera quality and retention configuration info (1 = present)",
            labelnames=[
                LabelName.ORG_ID.value,
                LabelName.NETWORK_ID.value,
                LabelName.SERIAL.value,
                LabelName.MODEL.value,
                LabelName.DEVICE_TYPE.value,
                LabelName.QUALITY.value,
                LabelName.RESOLUTION.value,
                LabelName.PROFILE_ID.value,
            ],
        )

    def _should_collect_static_config(self, serial: str) -> bool:
        """Return whether enough time has elapsed to (re)collect near-static camera config.

        Mirrors the ``_should_collect_firewall_rules``/``_should_collect_port_usage``
        throttle pattern in ``mx_firewall.py``/``ms.py``, keyed on
        ``settings.update_intervals.slow`` instead of a dedicated interval
        setting: analytics-zone layout and quality/retention config change
        infrequently, but ``collect()`` is invoked every MEDIUM-tier (300s)
        cycle by ``DeviceCollector``'s per-device fan-out (see F-027).
        """
        interval = self.settings.update_intervals.slow
        if interval <= 0:
            return True
        last = self._last_static_config_collection.get(serial, 0.0)
        return (time.time() - last) >= interval

    def _mark_static_config_collected(self, serial: str) -> None:
        """Record that near-static config was just collected for this camera."""
        self._last_static_config_collection[serial] = time.time()

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect MV-specific metrics.

        Common device metrics (device_up, status_info, uptime) are handled
        by DeviceCollector._collect_common_metrics() before this is called.

        Runs at the parent DeviceCollector's MEDIUM (300s) per-device cadence,
        but only the live-analytics (person-count) call is genuinely volatile
        enough to warrant that cadence. The analytics-zones and
        quality/retention calls are near-static camera configuration, so they
        are self-gated to the SLOW cadence (``settings.update_intervals.slow``,
        900s default) via ``_should_collect_static_config`` (see F-027) - this
        cuts steady-state per-camera API traffic from 3 calls/cycle to
        effectively 1 call/cycle plus 2 calls every third cycle. The
        zone-id -> zone-label map from the last static-config collection is
        cached (``_last_zone_maps``) so ``meraki_mv_zone_info`` (the id-keyed
        join carrier for zone_name, issue #534) can be re-emitted on cycles
        where the zones call is skipped, keeping the join target live between
        fetches. The three calls are independent so a failure in one does not
        block the others.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)
        serial = device.get("serial", "")

        if self._should_collect_static_config(serial):
            zone_map = await self._collect_analytics_zones(device, org_id, org_name, serial)
            if zone_map is not None:
                self._last_zone_maps[serial] = zone_map
            await self._collect_quality_and_retention(device, org_id, org_name, serial)
            self._mark_static_config_collected(serial)
        else:
            logger.debug(
                "Skipping MV static config collection (SLOW-tier cadence not yet elapsed)",
                serial=serial,
                interval_seconds=self.settings.update_intervals.slow,
            )
            # meraki_mv_zone_info is only (re)emitted from a fresh zones-API
            # fetch in _collect_analytics_zones - re-emit from the cached map
            # here so the id-keyed join carrier doesn't go stale/expire on a
            # cycle where that fetch is skipped (mirrors how the live call
            # used to resolve zone names from this same cache).
            self._emit_zone_info(device, org_id, org_name, self._last_zone_maps.get(serial, {}))

        await self._collect_analytics_live(device, org_id, org_name, serial)

    def _emit_zone_info(
        self,
        device: dict[str, Any],
        org_id: str,
        org_name: str,
        zone_map: dict[str, str],
    ) -> None:
        """Emit ``meraki_mv_zone_info`` for every zone in the given zone map.

        Id-keyed join carrier (issue #534, Option B): maps
        ``serial``+``zone_id`` -> ``zone_name`` so ``meraki_mv_people_count``
        (id-only) can re-attach the display name via
        ``on(serial, zone_id) group_left(zone_name)``. Built directly via
        ``create_labels`` (not ``create_device_labels``) because this metric's
        label set is ``{org_id, network_id, serial, zone_id, zone_name}`` only
        - no ``model``/``device_type``.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.
        org_id : str
            Organization ID.
        org_name : str
            Organization name. Retained for call-site symmetry; not emitted.
        zone_map : dict[str, str]
            Mapping of zone ID to zone label.

        """
        network_id = device.get("networkId", "")
        serial = device.get("serial", "")
        for zone_id, zone_name in zone_map.items():
            labels = create_labels(
                org_id=org_id,
                network_id=network_id,
                serial=serial,
                zone_id=zone_id,
                zone_name=zone_name,
            )
            self.parent._set_metric(
                self._mv_zone_info,
                labels,
                1,
                MVMetricName.MV_ZONE_INFO.value,
            )

    @log_api_call("getDeviceCameraAnalyticsZones")
    @with_error_handling(
        operation="Collect MV analytics zones",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_analytics_zones(
        self, device: dict[str, Any], org_id: str, org_name: str, serial: str
    ) -> dict[str, str]:
        """Collect configured analytics zones for a camera.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        serial : str
            Camera serial number.

        Returns
        -------
        dict[str, str]
            Mapping of zone ID (as string) to zone label, for use by the
            live-analytics call.

        """
        zones = await asyncio.to_thread(
            self.api.camera.getDeviceCameraAnalyticsZones,
            serial,
        )
        zones = validate_response_format(
            zones, expected_type=list, operation="getDeviceCameraAnalyticsZones"
        )
        zone_models = [CameraAnalyticsZone.model_validate(zone) for zone in zones]

        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)
        self.parent._set_metric(
            self._mv_analytics_zones,
            device_labels,
            len(zone_models),
            MVMetricName.MV_ANALYTICS_ZONES.value,
        )

        zone_map = {str(zone.id): (zone.label or "") for zone in zone_models}
        self._emit_zone_info(device, org_id, org_name, zone_map)
        return zone_map

    @log_api_call("getDeviceCameraAnalyticsLive")
    @with_error_handling(
        operation="Collect MV analytics live",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_analytics_live(
        self,
        device: dict[str, Any],
        org_id: str,
        org_name: str,
        serial: str,
    ) -> None:
        """Collect live person-count analytics per zone for a camera.

        ``zone_name`` is no longer a label on ``meraki_mv_people_count`` (issue
        #534, decision D2) - it joins via ``meraki_mv_zone_info`` on
        ``(serial, zone_id)`` instead, so this call no longer needs the
        zone-id -> zone-label map.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        serial : str
            Camera serial number.

        """
        live = await asyncio.to_thread(
            self.api.camera.getDeviceCameraAnalyticsLive,
            serial,
        )
        live = validate_response_format(
            live, expected_type=dict, operation="getDeviceCameraAnalyticsLive"
        )
        live_model = CameraAnalyticsLive.model_validate(live)

        for zone_id, zone_data in live_model.zones.items():
            person_count = zone_data.person
            labels = create_device_labels(
                device,
                org_id=org_id,
                org_name=org_name,
                zone_id=str(zone_id),
            )
            self.parent._set_metric(
                self._mv_people_count,
                labels,
                person_count,
                MVMetricName.MV_PEOPLE_COUNT.value,
            )

    @log_api_call("getDeviceCameraQualityAndRetention")
    @with_error_handling(
        operation="Collect MV quality and retention",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_quality_and_retention(
        self, device: dict[str, Any], org_id: str, org_name: str, serial: str
    ) -> None:
        """Collect quality/retention configuration for a camera.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        serial : str
            Camera serial number.

        """
        quality_retention = await asyncio.to_thread(
            self.api.camera.getDeviceCameraQualityAndRetention,
            serial,
        )
        quality_retention = validate_response_format(
            quality_retention,
            expected_type=dict,
            operation="getDeviceCameraQualityAndRetention",
        )
        qr_model = CameraQualityAndRetention.model_validate(quality_retention)

        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)

        self.parent._set_metric(
            self._mv_motion_based_retention_enabled,
            device_labels,
            1.0 if qr_model.motionBasedRetentionEnabled else 0.0,
            MVMetricName.MV_MOTION_BASED_RETENTION_ENABLED.value,
        )
        self.parent._set_metric(
            self._mv_audio_recording_enabled,
            device_labels,
            1.0 if qr_model.audioRecordingEnabled else 0.0,
            MVMetricName.MV_AUDIO_RECORDING_ENABLED.value,
        )
        self.parent._set_metric(
            self._mv_restricted_bandwidth_mode_enabled,
            device_labels,
            1.0 if qr_model.restrictedBandwidthModeEnabled else 0.0,
            MVMetricName.MV_RESTRICTED_BANDWIDTH_MODE_ENABLED.value,
        )

        # quality/resolution/profileId are all documented as nullable in the
        # OpenAPI spec (e.g. profileId is null when the camera isn't assigned
        # to a profile) - `or ""` avoids emitting the literal string "None"
        # for a null value (see F-004).
        quality_labels = create_device_labels(
            device,
            org_id=org_id,
            org_name=org_name,
            quality=str(qr_model.quality or ""),
            resolution=str(qr_model.resolution or ""),
            profile_id=str(qr_model.profileId or ""),
        )
        self.parent._set_metric(
            self._mv_quality_retention_info,
            quality_labels,
            1,
            MVMetricName.MV_QUALITY_RETENTION_INFO.value,
        )
