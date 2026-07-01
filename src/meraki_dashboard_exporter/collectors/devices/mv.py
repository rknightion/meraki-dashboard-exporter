"""MV security camera collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.constants import MVMetricName
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName
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

        # Common device label set shared by every MV gauge. Kept as a local
        # variable (not a module constant) so the metrics doc generator, which
        # resolves function-local label lists, picks up the full label set.
        device_labels = [
            LabelName.ORG_ID.value,
            LabelName.ORG_NAME.value,
            LabelName.NETWORK_ID.value,
            LabelName.NETWORK_NAME.value,
            LabelName.SERIAL.value,
            LabelName.NAME.value,
            LabelName.MODEL.value,
            LabelName.DEVICE_TYPE.value,
        ]

        self._mv_people_count = self.parent._create_gauge(
            MVMetricName.MV_PEOPLE_COUNT,
            "Current person count reported by MV camera analytics zone",
            labelnames=[
                LabelName.ORG_ID.value,
                LabelName.ORG_NAME.value,
                LabelName.NETWORK_ID.value,
                LabelName.NETWORK_NAME.value,
                LabelName.SERIAL.value,
                LabelName.NAME.value,
                LabelName.MODEL.value,
                LabelName.DEVICE_TYPE.value,
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
                LabelName.ORG_NAME.value,
                LabelName.NETWORK_ID.value,
                LabelName.NETWORK_NAME.value,
                LabelName.SERIAL.value,
                LabelName.NAME.value,
                LabelName.MODEL.value,
                LabelName.DEVICE_TYPE.value,
                LabelName.QUALITY.value,
                LabelName.RESOLUTION.value,
                LabelName.PROFILE_ID.value,
            ],
        )

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect MV-specific metrics.

        Common device metrics (device_up, status_info, uptime) are handled
        by DeviceCollector._collect_common_metrics() before this is called.

        Runs at the parent DeviceCollector's MEDIUM (300s) per-device cadence:
        camera analytics/config data tolerates 5-minute freshness. Each camera
        makes one zones call, one live-analytics call, and one quality/retention
        call per cycle, bounded by the coordinator's existing per-device
        ManagedTaskGroup fan-out. The three calls are independent so a failure
        in one does not block the others.

        Parameters
        ----------
        device : dict[str, Any]
            Device data.

        """
        org_id = device.get("orgId", "")
        org_name = device.get("orgName", org_id)
        serial = device.get("serial", "")

        zone_map = await self._collect_analytics_zones(device, org_id, org_name, serial)
        await self._collect_analytics_live(device, org_id, org_name, serial, zone_map or {})
        await self._collect_quality_and_retention(device, org_id, org_name, serial)

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

        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)
        self.parent._set_metric(
            self._mv_analytics_zones,
            device_labels,
            len(zones),
            MVMetricName.MV_ANALYTICS_ZONES.value,
        )

        return {str(zone.get("zoneId")): zone.get("label", "") for zone in zones}

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
        zone_map: dict[str, str],
    ) -> None:
        """Collect live person-count analytics per zone for a camera.

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
        zone_map : dict[str, str]
            Mapping of zone ID to zone label, from the zones call.

        """
        live = await asyncio.to_thread(
            self.api.camera.getDeviceCameraAnalyticsLive,
            serial,
        )
        live = validate_response_format(
            live, expected_type=dict, operation="getDeviceCameraAnalyticsLive"
        )

        for zone_id, zone_data in live.get("zones", {}).items():
            person_count = zone_data.get("person", 0)
            labels = create_device_labels(
                device,
                org_id=org_id,
                org_name=org_name,
                zone_id=str(zone_id),
                zone_name=zone_map.get(str(zone_id), ""),
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

        device_labels = create_device_labels(device, org_id=org_id, org_name=org_name)

        self.parent._set_metric(
            self._mv_motion_based_retention_enabled,
            device_labels,
            1.0 if quality_retention.get("motionBasedRetentionEnabled") else 0.0,
            MVMetricName.MV_MOTION_BASED_RETENTION_ENABLED.value,
        )
        self.parent._set_metric(
            self._mv_audio_recording_enabled,
            device_labels,
            1.0 if quality_retention.get("audioRecordingEnabled") else 0.0,
            MVMetricName.MV_AUDIO_RECORDING_ENABLED.value,
        )
        self.parent._set_metric(
            self._mv_restricted_bandwidth_mode_enabled,
            device_labels,
            1.0 if quality_retention.get("restrictedBandwidthModeEnabled") else 0.0,
            MVMetricName.MV_RESTRICTED_BANDWIDTH_MODE_ENABLED.value,
        )

        quality_labels = create_device_labels(
            device,
            org_id=org_id,
            org_name=org_name,
            quality=str(quality_retention.get("quality", "")),
            resolution=str(quality_retention.get("resolution", "")),
            profile_id=str(quality_retention.get("profileId", "")),
        )
        self.parent._set_metric(
            self._mv_quality_retention_info,
            quality_labels,
            1,
            MVMetricName.MV_QUALITY_RETENTION_INFO.value,
        )
