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


class CameraSenseConfig(BaseModel):
    """Response of ``getDeviceCameraSense`` (#305).

    ⚠ Phase-6 LIVE VERIFICATION (APIORG-01 lesson): confirm the field names
    (``senseEnabled``, ``mqttBrokerId``) against the live spec before
    freezing - no MV Sense-capable camera exists in the homelab.
    ``extra="allow"`` keeps parsing forward-compatible until then.
    """

    senseEnabled: bool | None = None
    mqttBrokerId: str | int | None = None

    model_config = ConfigDict(extra="allow")


class CameraOnboardingNetworkRef(BaseModel):
    """The ``network`` object of a camera onboarding-status entry (#306)."""

    id: str | None = None

    model_config = ConfigDict(extra="allow")


class CameraOnboardingStatusEntry(BaseModel):
    """One row from ``getOrganizationCameraOnboardingStatuses`` (#306).

    ⚠ Phase-6 LIVE VERIFICATION: no verified sample response was available for
    this endpoint. Both a nested ``network.id`` and a flat ``networkId`` are
    accepted (only one is expected to actually appear) so parsing degrades
    gracefully either way; ``extra="allow"`` keeps it forward-compatible.
    """

    serial: str | None = None
    networkId: str | None = None
    network: CameraOnboardingNetworkRef | None = None
    status: str | None = None

    model_config = ConfigDict(extra="allow")

    @property
    def resolved_network_id(self) -> str:
        """Best-effort network ID from either the nested or flat field."""
        if self.network is not None and self.network.id:
            return self.network.id
        return self.networkId or ""


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

        # Phase 4 (#305): analogous per-serial gate for the mv_sense_config
        # group (floor 900s, 1 call/camera) - independent cadence bookkeeping
        # from mv_analytics even though both currently share the same floor.
        self._last_sense_collection: dict[str, float] = {}

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

        # Phase 4 (#305): MV Sense enablement/MQTT-broker configuration.
        self._mv_sense_enabled = self.parent._create_gauge(
            MVMetricName.MV_SENSE_ENABLED,
            "Whether MV Sense is enabled on the camera (1 = enabled)",
            labelnames=device_labels,
        )
        self._mv_sense_mqtt_broker_configured = self.parent._create_gauge(
            MVMetricName.MV_SENSE_MQTT_BROKER_CONFIGURED,
            "Whether an MQTT broker is configured for MV Sense (1 = configured)",
            labelnames=device_labels,
        )

        # Phase 4 (#306): org-wide camera onboarding status (id-only labels -
        # no model/device_type since the source endpoint is org-wide, not
        # per-device).
        self._mv_onboarding_status = self.parent._create_gauge(
            MVMetricName.MV_ONBOARDING_STATUS,
            "MV camera onboarding status (1 = current status; bounded enum, "
            "unknown values normalize to 'other')",
            labelnames=[
                LabelName.ORG_ID.value,
                LabelName.NETWORK_ID.value,
                LabelName.SERIAL.value,
                LabelName.STATUS.value,
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

    def _sense_ttl_seconds(self) -> float | None:
        """Solved per-series TTL for the mv_sense_config group (#305)."""
        ttl: float | None = self.parent._group_ttl_seconds(EndpointGroupName.MV_SENSE_CONFIG)
        return ttl

    def _should_collect_sense(self, serial: str) -> bool:
        """Return whether the mv_sense_config group is due for this camera.

        Mirrors ``_should_collect_analytics`` (#305): a per-serial timestamp
        gate reading the interval from the #617 scheduler
        (``parent._group_interval(MV_SENSE_CONFIG)``, floor 900s), since
        ``collect()`` is invoked every MEDIUM-tier (300s) cycle by
        ``DeviceCollector``'s per-device fan-out.
        """
        interval: float = self.parent._group_interval(EndpointGroupName.MV_SENSE_CONFIG)
        if interval <= 0:
            return True
        last = self._last_sense_collection.get(serial, 0.0)
        return (time.time() - last) >= interval

    def _mark_sense_collected(self, serial: str) -> None:
        """Record that the mv_sense_config group was just collected for this camera."""
        self._last_sense_collection[serial] = time.time()

    @staticmethod
    def _normalize_onboarding_status(status: str | None) -> str:
        """Bound the onboarding ``status`` value to a fixed enum (#306).

        ⚠ Phase-6 LIVE VERIFICATION: this allow-list is a best-effort guess
        pending a verified live sample; any value outside it (including the
        true live value set, until verified) normalizes to ``"other"`` so
        cardinality stays bounded regardless.
        """
        allowed = {"complete", "onboarding", "failed", "settingUp"}
        return status if status in allowed else "other"

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

        MV Sense enablement (#305, ``mv_sense_config`` group) is gated and
        collected independently via its own per-serial timestamp gate
        (``_should_collect_sense``) before the analytics block, so its cadence
        can diverge from ``mv_analytics`` under adaptive budgeting even though
        both currently share the same 900s floor.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)
        serial = device.get("serial", "")

        if self._should_collect_sense(serial):
            # The fetcher is @with_error_handling(continue_on_error=True), so it
            # returns None on failure and a truthy sentinel on success. Only mark
            # the group ran when the fetch actually succeeded (#629) - a swallowed
            # failure must leave the gate open so diagnostics/backoff can retry.
            sense_ok = await self._collect_sense_config(
                device, org_id=org_id, org_name=org_name, serial=serial
            )
            self._mark_sense_collected(serial)
            if sense_ok is not None:
                self.parent._mark_group_ran(EndpointGroupName.MV_SENSE_CONFIG)

        if not self._should_collect_analytics(serial):
            logger.debug(
                "Skipping MV analytics collection (mv_analytics cadence not yet elapsed)",
                serial=serial,
                interval_seconds=self.parent._group_interval(EndpointGroupName.MV_ANALYTICS),
            )
            return

        # Each fetcher is @with_error_handling(continue_on_error=True): it returns
        # None when swallowed and a non-None value on success. Track whether ANY
        # of the three succeeded so the group is marked ran only on >=1 successful
        # sub-fetch (#629). Total fan-out failure must leave the gate open so the
        # next cycle retries rather than silently marking a failed cycle "ran".
        zones_ok = await self._collect_analytics_zones(
            device, org_id=org_id, org_name=org_name, serial=serial
        )
        recent_ok = await self._collect_analytics_recent(
            device, org_id=org_id, org_name=org_name, serial=serial
        )
        quality_ok = await self._collect_quality_and_retention(
            device, org_id=org_id, org_name=org_name, serial=serial
        )

        self._mark_analytics_collected(serial)
        # Feed the scheduler's diagnostics/last-ran bookkeeping. Gating itself is
        # per-serial (above); this keeps the group's diagnostics live, but only
        # when at least one sub-fetch succeeded (successful-empty still counts).
        if zones_ok is not None or recent_ok is not None or quality_ok is not None:
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

        # zone.zoneId is the live wire field (#630); str() so it matches the
        # zone_id label built from getDeviceCameraAnalyticsRecent's zoneId.
        zone_map = {str(zone.zoneId): (zone.label or "") for zone in zone_models}
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
    ) -> bool:
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

        Returns
        -------
        bool
            ``True`` on a successful fetch (used by ``collect`` to decide whether
            to mark the ``mv_analytics`` group ran, #629). On failure the
            ``@with_error_handling(continue_on_error=True)`` wrapper returns
            ``None`` instead.

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

        return True

    @log_api_call("getDeviceCameraQualityAndRetention")
    @with_error_handling(
        operation="Collect MV quality and retention",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_quality_and_retention(
        self, device: dict[str, Any], org_id: str, org_name: str, serial: str
    ) -> bool:
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

        Returns
        -------
        bool
            ``True`` on a successful fetch (used by ``collect`` to decide whether
            to mark the ``mv_analytics`` group ran, #629). On failure the
            ``@with_error_handling(continue_on_error=True)`` wrapper returns
            ``None`` instead.

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

        return True

    @log_api_call("getDeviceCameraSense")
    @with_error_handling(
        operation="Collect MV Sense configuration",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def _collect_sense_config(
        self, device: dict[str, Any], org_id: str, org_name: str, serial: str
    ) -> bool:
        """Collect MV Sense enablement/MQTT-broker configuration for a camera (#305).

        ⚠ Phase-6 LIVE VERIFICATION: confirm the field names (``senseEnabled``,
        ``mqttBrokerId``) against the live API - no MV Sense-capable camera
        exists in the homelab to verify against.

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
        bool
            ``True`` on a successful fetch (used by ``collect`` to decide whether
            to mark the ``mv_sense_config`` group ran, #629). On failure the
            ``@with_error_handling(continue_on_error=True)`` wrapper returns
            ``None`` instead.

        """
        sense = await asyncio.to_thread(
            self.api.camera.getDeviceCameraSense,
            serial,
        )
        sense = validate_response_format(
            sense, expected_type=dict, operation="getDeviceCameraSense"
        )
        sense_model = CameraSenseConfig.model_validate(sense)

        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)
        ttl_seconds = self._sense_ttl_seconds()

        self.parent._set_metric(
            self._mv_sense_enabled,
            device_labels,
            1.0 if sense_model.senseEnabled else 0.0,
            MVMetricName.MV_SENSE_ENABLED.value,
            ttl_seconds=ttl_seconds,
        )
        self.parent._set_metric(
            self._mv_sense_mqtt_broker_configured,
            device_labels,
            1.0 if sense_model.mqttBrokerId else 0.0,
            MVMetricName.MV_SENSE_MQTT_BROKER_CONFIGURED.value,
            ttl_seconds=ttl_seconds,
        )

        return True

    @log_api_call("getOrganizationCameraOnboardingStatuses")
    @with_error_handling(
        operation="Collect MV camera onboarding statuses",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_onboarding_statuses(self, org_id: str, org_name: str) -> None:
        """Collect org-wide camera onboarding status (#306).

        Single org-wide call via ``getOrganizationCameraOnboardingStatuses``
        (the SDK method takes no ``total_pages``/pagination kwarg - this
        endpoint is not paginated). Stale ``status`` label transitions are
        removed by the metric-expiration manager (``parent._set_metric``
        tracking), not by an explicit gauge-clear - mirrors
        ``mx.py``'s ``collect_uplink_statuses``.

        This is NOT invoked by ``DeviceCollector`` yet (#618 Phase-4 lane
        boundary: this lane does not edit ``device.py``) - see the wiring
        snippet in the accompanying issue/PR description for the exact
        call-site the integration pass should add.

        ⚠ Phase-6 LIVE VERIFICATION: confirm the response shape (the network
        ID field name, and the bounded ``status`` value set in
        ``_normalize_onboarding_status``) against a live org - no verified
        sample response was available.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name. Retained for call-site symmetry with other
            org-wide collectors (e.g. ``mx.py``'s ``collect_uplink_statuses``);
            NOT emitted (id-only numeric series, issue #534).

        """
        if not self.parent._should_run_group(EndpointGroupName.MV_ONBOARDING):
            return

        raw = await asyncio.to_thread(
            self.api.camera.getOrganizationCameraOnboardingStatuses,
            org_id,
        )
        raw = validate_response_format(
            raw, expected_type=list, operation="getOrganizationCameraOnboardingStatuses"
        )

        if not raw:
            self.parent._mark_group_ran(EndpointGroupName.MV_ONBOARDING)
            return

        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )

        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MV_ONBOARDING)

        for raw_entry in raw:
            try:
                entry = CameraOnboardingStatusEntry.model_validate(raw_entry)
            except Exception:
                logger.debug(
                    "Failed to parse camera onboarding status entry",
                    org_id=org_id,
                )
                continue

            if not entry.serial:
                continue

            network_id = entry.resolved_network_id
            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                continue

            status = self._normalize_onboarding_status(entry.status)
            labels = create_labels(
                org_id=org_id,
                network_id=network_id,
                serial=entry.serial,
                status=status,
            )
            self.parent._set_metric(
                self._mv_onboarding_status,
                labels,
                1,
                MVMetricName.MV_ONBOARDING_STATUS.value,
                ttl_seconds=ttl_seconds,
            )

        self.parent._mark_group_ran(EndpointGroupName.MV_ONBOARDING)
