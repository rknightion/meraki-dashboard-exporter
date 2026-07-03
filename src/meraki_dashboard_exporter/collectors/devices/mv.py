"""MV security camera collector."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from ...core.constants import MVMetricName
from ...core.domain_models import (
    CameraAnalyticsZone,
    CameraQualityAndRetention,
)
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName, create_labels
from ...core.scheduler import EndpointGroupName
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    from ..device import DeviceCollector

logger = get_logger(__name__)


class CameraAnalyticsRecentZone(BaseModel):
    """One per-zone record from ``getDeviceCameraAnalyticsRecent`` (#549).

    Replacement for the DEPRECATED ``getDeviceCameraAnalyticsLive`` per-zone
    ``person`` count. The ``recent`` endpoint returns the most recent
    aggregated record per analytics zone; ``averageCount`` is used as the
    person-count analog for ``meraki_mv_people_count``.

    ⚠ Phase-6 LIVE VERIFICATION (APIORG-01 lesson): confirm the response field
    names (``zoneId``/``averageCount``) and the person-count semantics against
    the live spec (v1.72.0+) before freezing. ``extra="allow"`` keeps parsing
    forward-compatible until then. Should be relocated to
    ``core/domain_models.py`` (with ``__meraki_op__`` for apidrift tracking)
    during the #617 integration/wiring pass — it lives here to keep the MV lane
    within its owned file set while ``domain_models.py`` is a shared seam.
    """

    zoneId: str | int | None = None
    entrances: float | None = None
    averageCount: float | None = None

    model_config = ConfigDict(extra="allow")


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

        # Tracks the last time the mv_analytics group (analytics zones, recent
        # person-count, quality/retention) was collected, keyed by serial, so
        # the group cadence can be self-enforced per-camera even though
        # collect() is dispatched every MEDIUM-tier (300s) cycle by
        # DeviceCollector's per-device fan-out (see F-027). The interval comes
        # from the #617 scheduler (parent._group_interval(MV_ANALYTICS), floor
        # 900s), NOT from a raw setting. Mirrors the per-serial gate pattern in
        # mx_firewall.py/ms.py, which the #617 spec carves out for per-device
        # fan-outs (a single group-level should_run gate would incorrectly skip
        # every camera after the first within one cycle).
        self._last_analytics_collection: dict[str, float] = {}

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

    def _analytics_ttl_seconds(self) -> float | None:
        """Solved per-series TTL for the mv_analytics group (#617 §1f)."""
        ttl: float | None = self.parent._group_ttl_seconds(EndpointGroupName.MV_ANALYTICS)
        return ttl

    def _should_collect_analytics(self, serial: str) -> bool:
        """Return whether the mv_analytics group is due for this camera.

        Reads the group interval from the #617 scheduler
        (``parent._group_interval(MV_ANALYTICS)``, floor 900s) rather than a
        raw setting; a non-positive interval disables gating (always collect).
        ``collect()`` is invoked every MEDIUM-tier (300s) cycle by
        ``DeviceCollector``'s per-device fan-out, so this per-serial timestamp
        gate self-enforces the SLOW-class group cadence.
        """
        interval: float = self.parent._group_interval(EndpointGroupName.MV_ANALYTICS)
        if interval <= 0:
            return True
        last = self._last_analytics_collection.get(serial, 0.0)
        return (time.time() - last) >= interval

    def _mark_analytics_collected(self, serial: str) -> None:
        """Record that the mv_analytics group was just collected for this camera."""
        self._last_analytics_collection[serial] = time.time()

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect MV-specific metrics.

        Common device metrics (device_up, status_info, uptime) are handled
        by DeviceCollector._collect_common_metrics() before this is called.

        All three analytics fetches - configured zones, recent per-zone
        person-count, and quality/retention config - belong to the single
        SLOW-class ``mv_analytics`` scheduler group (#617, floor 900s,
        priority 4). ``collect()`` runs at the parent DeviceCollector's MEDIUM
        (300s) per-device cadence, so a per-serial timestamp gate
        (``_should_collect_analytics``) self-enforces the group cadence, and
        the solved TTL (``_analytics_ttl_seconds``) is threaded onto every
        emitted series so a series polled slower than its tier heartbeat does
        not flap (#617 §1f). ``org_id`` is passed explicitly to each fetcher so
        the client-side rate limiter is keyed to the org bucket (#549 / #270).
        The three calls are independent (each ``@with_error_handling``
        ``continue_on_error=True``) so a failure in one does not block the
        others.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)
        serial = device.get("serial", "")

        if not self._should_collect_analytics(serial):
            logger.debug(
                "Skipping MV analytics collection (mv_analytics cadence not yet elapsed)",
                serial=serial,
                interval_seconds=self.parent._group_interval(EndpointGroupName.MV_ANALYTICS),
            )
            return

        await self._collect_analytics_zones(device, org_id=org_id, org_name=org_name, serial=serial)
        await self._collect_analytics_recent(
            device, org_id=org_id, org_name=org_name, serial=serial
        )
        await self._collect_quality_and_retention(
            device, org_id=org_id, org_name=org_name, serial=serial
        )

        self._mark_analytics_collected(serial)
        # Feed the scheduler's diagnostics/last-ran bookkeeping. Gating itself
        # is per-serial (above); this keeps the group's diagnostics live.
        self.parent._mark_group_ran(EndpointGroupName.MV_ANALYTICS)

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
        ttl_seconds = self._analytics_ttl_seconds()
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
                ttl_seconds=ttl_seconds,
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

        Emits ``meraki_mv_analytics_zones`` (count) and, via
        ``_emit_zone_info``, the ``meraki_mv_zone_info`` id->name join carrier.

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
            Mapping of zone ID (as string) to zone label.

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
            ttl_seconds=self._analytics_ttl_seconds(),
        )

        zone_map = {str(zone.id): (zone.label or "") for zone in zone_models}
        self._emit_zone_info(device, org_id, org_name, zone_map)
        return zone_map

    @log_api_call("getDeviceCameraAnalyticsRecent")
    @with_error_handling(
        operation="Collect MV analytics recent",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_analytics_recent(
        self,
        device: dict[str, Any],
        org_id: str,
        org_name: str,
        serial: str,
    ) -> None:
        """Collect recent per-zone person-count analytics for a camera (#549).

        Replaces the DEPRECATED ``getDeviceCameraAnalyticsLive`` endpoint with
        ``getDeviceCameraAnalyticsRecent``; ``averageCount`` is used as the
        per-zone person-count analog for ``meraki_mv_people_count``.

        ``zone_name`` is no longer a label on ``meraki_mv_people_count`` (issue
        #534, decision D2) - it joins via ``meraki_mv_zone_info`` on
        ``(serial, zone_id)``.

        ⚠ Phase-6: the replacement endpoint's field names/semantics
        (``zoneId``/``averageCount``) need live verification (v1.72.0+).

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
        recent = await asyncio.to_thread(
            self.api.camera.getDeviceCameraAnalyticsRecent,
            serial,
        )
        recent = validate_response_format(
            recent, expected_type=list, operation="getDeviceCameraAnalyticsRecent"
        )
        records = [CameraAnalyticsRecentZone.model_validate(record) for record in recent]

        ttl_seconds = self._analytics_ttl_seconds()
        for record in records:
            if record.zoneId is None:
                continue
            person_count = record.averageCount if record.averageCount is not None else 0.0
            labels = create_device_labels(
                device,
                org_id=org_id,
                org_name=org_name,
                zone_id=str(record.zoneId),
            )
            self.parent._set_metric(
                self._mv_people_count,
                labels,
                person_count,
                MVMetricName.MV_PEOPLE_COUNT.value,
                ttl_seconds=ttl_seconds,
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
        ttl_seconds = self._analytics_ttl_seconds()

        self.parent._set_metric(
            self._mv_motion_based_retention_enabled,
            device_labels,
            1.0 if qr_model.motionBasedRetentionEnabled else 0.0,
            MVMetricName.MV_MOTION_BASED_RETENTION_ENABLED.value,
            ttl_seconds=ttl_seconds,
        )
        self.parent._set_metric(
            self._mv_audio_recording_enabled,
            device_labels,
            1.0 if qr_model.audioRecordingEnabled else 0.0,
            MVMetricName.MV_AUDIO_RECORDING_ENABLED.value,
            ttl_seconds=ttl_seconds,
        )
        self.parent._set_metric(
            self._mv_restricted_bandwidth_mode_enabled,
            device_labels,
            1.0 if qr_model.restrictedBandwidthModeEnabled else 0.0,
            MVMetricName.MV_RESTRICTED_BANDWIDTH_MODE_ENABLED.value,
            ttl_seconds=ttl_seconds,
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
            ttl_seconds=ttl_seconds,
        )
