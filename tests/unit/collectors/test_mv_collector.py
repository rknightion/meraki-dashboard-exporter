"""Tests for MV (Security Camera) collector.

Covers the #617 ``mv_analytics`` scheduler group gate (per-serial timestamp
gate reading its interval from ``parent._group_interval`` + per-series
``ttl_seconds`` threading) and the #549 migration off the deprecated
``getDeviceCameraAnalyticsLive`` endpoint to ``getDeviceCameraAnalyticsRecent``,
plus the explicit per-org rate-limiter keying fix.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mv import (
    CameraAnalyticsRecentZone,
    MVCollector,
)
from meraki_dashboard_exporter.core.domain_models import (
    CameraAnalyticsZone,
    CameraQualityAndRetention,
)
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName

if TYPE_CHECKING:
    pass


class TestMVCollector:
    """Test MV collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.camera = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent DeviceCollector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        # Legacy setting; the mv_analytics gate now reads its interval from the
        # scheduler (parent._group_interval), NOT from update_intervals.slow.
        parent.settings.update_intervals.slow = 900
        parent.rate_limiter = None
        parent.inventory = None

        # #617 scheduler gate helpers for the mv_analytics group. The MV
        # collector is a per-camera fan-out, so it self-gates via a per-serial
        # timestamp map keyed on _group_interval (floor 900s), and threads the
        # solved TTL through _set_metric.
        parent._group_interval = MagicMock(return_value=900.0)
        parent._group_ttl_seconds = MagicMock(return_value=1800.0)
        parent._should_run_group = MagicMock(return_value=True)
        parent._mark_group_ran = MagicMock()

        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        parent._set_metric = MagicMock()
        return parent

    @pytest.fixture
    def mv_collector(
        self,
        mock_parent: MagicMock,
    ) -> MVCollector:
        """Create MV collector instance."""
        return MVCollector(mock_parent)

    @pytest.fixture
    def device(self) -> dict:
        """Create a standard MV camera device dict."""
        return {
            "serial": "Q2CC-1234-5678",
            "name": "Lobby Camera",
            "model": "MV12",
            "networkId": "N_111",
            "networkName": "HQ Network",
            "orgId": "org1",
            "orgName": "Test Org",
        }

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _zones(*rows: dict) -> MagicMock:
        return MagicMock(return_value=list(rows))

    @staticmethod
    def _recent(*rows: dict) -> MagicMock:
        return MagicMock(return_value=list(rows))

    @staticmethod
    def _quality(**overrides) -> MagicMock:
        payload = {
            "motionBasedRetentionEnabled": True,
            "audioRecordingEnabled": False,
            "restrictedBandwidthModeEnabled": False,
            "quality": "Standard",
            "resolution": "1280x720",
            "profileId": "123",
        }
        payload.update(overrides)
        return MagicMock(return_value=payload)

    def _set_all_responses(self, mock_api: MagicMock) -> None:
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones({
            "id": "0",
            "label": "Entrance",
            "type": ["person"],
        })
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent({
            "zoneId": "0",
            "entrances": 4,
            "averageCount": 2,
        })
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def test_mv_collector_initialization(
        self,
        mv_collector: MVCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test MV collector initialization."""
        assert mv_collector.parent == mock_parent
        assert mv_collector.api == mock_parent.api
        assert mv_collector.settings == mock_parent.settings

    def test_mv_gauges_created(
        self,
        mv_collector: MVCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test that all MV gauges are created on init."""
        mock_parent._create_gauge.assert_called()
        assert mv_collector._mv_people_count is not None
        assert mv_collector._mv_zone_info is not None
        assert mv_collector._mv_analytics_zones is not None
        assert mv_collector._mv_motion_based_retention_enabled is not None
        assert mv_collector._mv_audio_recording_enabled is not None
        assert mv_collector._mv_restricted_bandwidth_mode_enabled is not None
        assert mv_collector._mv_quality_retention_info is not None

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    async def test_collect_zones_count(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Test analytics zones count is emitted."""
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones(
            # Real getDeviceCameraAnalyticsZones responses key the zone object
            # on `id`, not `zoneId` (verified against the vendored OpenAPI
            # spec) - see F-024.
            {"id": "0", "label": "Entrance", "type": ["person"]},
            {"id": "1", "label": "Lobby", "type": ["person"]},
        )
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent()
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality()

        await mv_collector.collect(device)

        zones_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_analytics_zones
        ]
        assert len(zones_calls) == 1
        _, labels, value = zones_calls[0][0][:3]
        assert value == 2
        assert labels["serial"] == "Q2CC-1234-5678"
        # Name-family labels are dropped from numeric series (issue #534).
        assert "name" not in labels
        assert "org_name" not in labels
        assert "network_name" not in labels

    async def test_collect_people_count_from_recent_endpoint(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """meraki_mv_people_count is sourced from getDeviceCameraAnalyticsRecent (#549).

        The deprecated getDeviceCameraAnalyticsLive endpoint must NOT be
        called; per-zone person count comes from the recent record's
        ``averageCount`` keyed on ``zoneId``. Labels remain id-only (#534, D2):
        zone_name joins via meraki_mv_zone_info on (serial, zone_id).
        """
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones(
            {"id": "0", "label": "Entrance", "type": ["person"]},
            {"id": "1", "label": "Lobby", "type": ["person"]},
        )
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent(
            {"zoneId": "0", "entrances": 9, "averageCount": 3},
            {"zoneId": "1", "entrances": 0, "averageCount": 0},
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality()

        await mv_collector.collect(device)

        # Deprecated endpoint is fully retired.
        assert mock_api.camera.getDeviceCameraAnalyticsLive.call_count == 0
        assert mock_api.camera.getDeviceCameraAnalyticsRecent.call_count == 1

        people_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_people_count
        ]
        assert len(people_calls) == 2

        by_zone = {call[0][1]["zone_id"]: call for call in people_calls}
        _, labels_0, value_0 = by_zone["0"][0][:3]
        assert value_0 == 3
        assert "zone_name" not in labels_0
        assert labels_0 == {
            "org_id": "org1",
            "network_id": "N_111",
            "serial": "Q2CC-1234-5678",
            "model": "MV12",
            "device_type": "MV",
            "zone_id": "0",
        }

        _, labels_1, value_1 = by_zone["1"][0][:3]
        assert value_1 == 0
        assert "zone_name" not in labels_1

    async def test_collect_zone_info_emitted_per_zone(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """meraki_mv_zone_info (NI-3, issue #534) emits one series per zone."""
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones(
            {"id": "0", "label": "Entrance", "type": ["person"]},
            {"id": "1", "label": "Lobby", "type": ["person"]},
        )
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent()
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality()

        await mv_collector.collect(device)

        zone_info_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_zone_info
        ]
        assert len(zone_info_calls) == 2
        for call in zone_info_calls:
            assert call[0][2] == 1

        by_zone = {call[0][1]["zone_id"]: call[0][1] for call in zone_info_calls}
        assert by_zone["0"] == {
            "org_id": "org1",
            "network_id": "N_111",
            "serial": "Q2CC-1234-5678",
            "zone_id": "0",
            "zone_name": "Entrance",
        }
        assert by_zone["1"] == {
            "org_id": "org1",
            "network_id": "N_111",
            "serial": "Q2CC-1234-5678",
            "zone_id": "1",
            "zone_name": "Lobby",
        }

    async def test_collect_quality_booleans(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Test quality/retention boolean gauges map true->1 and false->0."""
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones()
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent()
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality(
            motionBasedRetentionEnabled=True,
            audioRecordingEnabled=False,
            restrictedBandwidthModeEnabled=True,
            quality="Enhanced",
            resolution="1920x1080",
            profileId="456",
        )

        await mv_collector.collect(device)

        def value_for(gauge):
            for call in mock_parent._set_metric.call_args_list:
                if call[0][0] is gauge:
                    return call[0][2]
            raise AssertionError("gauge not set")

        assert value_for(mv_collector._mv_motion_based_retention_enabled) == 1.0
        assert value_for(mv_collector._mv_audio_recording_enabled) == 0.0
        assert value_for(mv_collector._mv_restricted_bandwidth_mode_enabled) == 1.0

    async def test_collect_quality_retention_info_labels(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Test quality retention info gauge carries quality/resolution/profile_id labels."""
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones()
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent()
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality(
            quality="High", resolution="2688x1512", profileId="789"
        )

        await mv_collector.collect(device)

        info_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_quality_retention_info
        ]
        assert len(info_calls) == 1
        _, labels, value = info_calls[0][0][:3]
        assert value == 1
        assert labels["quality"] == "High"
        assert labels["resolution"] == "2688x1512"
        assert labels["profile_id"] == "789"

    # ------------------------------------------------------------------
    # Independent-failure isolation (@with_error_handling)
    # ------------------------------------------------------------------

    async def test_collect_recent_failure_does_not_block_others(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """A failing recent-analytics call still lets the other two emit metrics."""
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones({
            "id": "0",
            "label": "Entrance",
            "type": ["person"],
        })
        mock_api.camera.getDeviceCameraAnalyticsRecent = MagicMock(
            side_effect=Exception("API connection failed")
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality()

        # Should not raise - @with_error_handling(continue_on_error=True) catches it.
        await mv_collector.collect(device)

        gauges_set = {call[0][0] for call in mock_parent._set_metric.call_args_list}
        assert mv_collector._mv_analytics_zones in gauges_set
        assert mv_collector._mv_zone_info in gauges_set
        assert mv_collector._mv_motion_based_retention_enabled in gauges_set
        assert mv_collector._mv_quality_retention_info in gauges_set
        # The recent call failed, so no people-count metrics should exist.
        assert mv_collector._mv_people_count not in gauges_set

    async def test_collect_zones_exhausted_retry_error_shape_handled_gracefully(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """The SDK exhausted-retry error shape (dict with 'errors') must be absorbed."""
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(
            return_value={"errors": ["internal server error"]}
        )
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent()
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality()

        await mv_collector.collect(device)

        gauges_set = {call[0][0] for call in mock_parent._set_metric.call_args_list}
        assert mv_collector._mv_analytics_zones not in gauges_set
        assert mv_collector._mv_zone_info not in gauges_set
        assert mv_collector._mv_quality_retention_info in gauges_set

    async def test_collect_recent_exhausted_retry_error_shape_handled_gracefully(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """A {'errors': [...]} recent response (expected_type=list) must be absorbed."""
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones({
            "id": "0",
            "label": "Entrance",
            "type": ["person"],
        })
        mock_api.camera.getDeviceCameraAnalyticsRecent = MagicMock(
            return_value={"errors": ["internal server error"]}
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality()

        await mv_collector.collect(device)

        gauges_set = {call[0][0] for call in mock_parent._set_metric.call_args_list}
        assert mv_collector._mv_analytics_zones in gauges_set
        assert mv_collector._mv_zone_info in gauges_set
        assert mv_collector._mv_quality_retention_info in gauges_set
        assert mv_collector._mv_people_count not in gauges_set

    async def test_collect_quality_retention_exhausted_retry_error_shape_handled_gracefully(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """A {'errors': [...]} quality/retention response must be absorbed."""
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones({
            "id": "0",
            "label": "Entrance",
            "type": ["person"],
        })
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent({
            "zoneId": "0",
            "averageCount": 1,
        })
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={"errors": ["internal server error"]}
        )

        await mv_collector.collect(device)

        gauges_set = {call[0][0] for call in mock_parent._set_metric.call_args_list}
        assert mv_collector._mv_analytics_zones in gauges_set
        assert mv_collector._mv_zone_info in gauges_set
        assert mv_collector._mv_people_count in gauges_set
        assert mv_collector._mv_quality_retention_info not in gauges_set

    async def test_collect_empty_zones(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Test that an empty zones list still emits a zero-count gauge."""
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones()
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent()
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality(
            motionBasedRetentionEnabled=False
        )

        await mv_collector.collect(device)

        zones_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_analytics_zones
        ]
        assert len(zones_calls) == 1
        assert zones_calls[0][0][2] == 0

    async def test_collect_quality_retention_info_null_values_emit_empty_labels(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Null quality/resolution/profileId must emit "" labels, not the string "None"."""
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones()
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent()
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality(
            motionBasedRetentionEnabled=False,
            quality=None,
            resolution=None,
            profileId=None,
        )

        await mv_collector.collect(device)

        info_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_quality_retention_info
        ]
        assert len(info_calls) == 1
        _, labels, _value = info_calls[0][0][:3]
        assert not labels["quality"]
        assert not labels["resolution"]
        assert not labels["profile_id"]
        assert "None" not in labels.values()

    # ------------------------------------------------------------------
    # #617 mv_analytics group gate (per-serial timestamp, interval from scheduler)
    #
    # collect() is dispatched every MEDIUM-tier (300s) cycle by DeviceCollector,
    # but ALL three analytics fetches (zones, recent person-count,
    # quality/retention) belong to the SLOW-class mv_analytics group (floor
    # 900s). A per-serial timestamp gate self-enforces the group cadence,
    # reading its interval from parent._group_interval(MV_ANALYTICS).
    # ------------------------------------------------------------------

    async def test_analytics_skipped_within_group_interval(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """A second immediate cycle must not re-fetch ANY of the three analytics calls."""
        self._set_all_responses(mock_api)

        await mv_collector.collect(device)
        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 1
        assert mock_api.camera.getDeviceCameraAnalyticsRecent.call_count == 1
        assert mock_api.camera.getDeviceCameraQualityAndRetention.call_count == 1

        await mv_collector.collect(device)
        # All three are folded into the same 900s group and gated together.
        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 1
        assert mock_api.camera.getDeviceCameraAnalyticsRecent.call_count == 1
        assert mock_api.camera.getDeviceCameraQualityAndRetention.call_count == 1

    async def test_analytics_collected_again_after_group_interval_elapses(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Once the group interval has elapsed, the next cycle re-fetches all three."""
        self._set_all_responses(mock_api)

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv.time.time",
            return_value=1_000.0,
        ):
            await mv_collector.collect(device)
        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 1

        # Still short of the 900s interval.
        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv.time.time",
            return_value=1_000.0 + 300,
        ):
            await mv_collector.collect(device)
        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 1

        # Past the interval.
        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv.time.time",
            return_value=1_000.0 + 901,
        ):
            await mv_collector.collect(device)
        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 2
        assert mock_api.camera.getDeviceCameraAnalyticsRecent.call_count == 2
        assert mock_api.camera.getDeviceCameraQualityAndRetention.call_count == 2

    async def test_analytics_gating_is_per_camera(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Gating state must be tracked per camera serial, not globally."""
        self._set_all_responses(mock_api)
        other_device = {**device, "serial": "Q2CC-9999-0000", "name": "Other Camera"}

        await mv_collector.collect(device)
        await mv_collector.collect(other_device)

        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 2
        assert mock_api.camera.getDeviceCameraAnalyticsRecent.call_count == 2

    async def test_gate_interval_read_from_scheduler_not_settings(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """The gate cadence comes from _group_interval(MV_ANALYTICS), not settings.slow."""
        self._set_all_responses(mock_api)
        # A tiny scheduler interval means the very next cycle is already due,
        # even though the legacy settings.update_intervals.slow is still 900.
        mock_parent._group_interval.return_value = 1.0

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv.time.time",
            return_value=1_000.0,
        ):
            await mv_collector.collect(device)
        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv.time.time",
            return_value=1_000.0 + 2,
        ):
            await mv_collector.collect(device)

        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 2
        mock_parent._group_interval.assert_called_with(EndpointGroupName.MV_ANALYTICS)

    async def test_gate_interval_zero_disables_gating(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """A non-positive group interval must disable gating (always collect)."""
        mock_parent._group_interval.return_value = 0
        self._set_all_responses(mock_api)

        await mv_collector.collect(device)
        await mv_collector.collect(device)

        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 2
        assert mock_api.camera.getDeviceCameraAnalyticsRecent.call_count == 2

    async def test_mark_group_ran_after_successful_collection(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """A completed analytics cycle marks the mv_analytics group as run (diagnostics)."""
        self._set_all_responses(mock_api)

        await mv_collector.collect(device)

        mock_parent._mark_group_ran.assert_called_with(EndpointGroupName.MV_ANALYTICS)

    async def test_stale_zone_not_reemitted_after_removal(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """A zone removed from the camera config stops being emitted on the next fetch."""
        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv.time.time",
            return_value=1_000.0,
        ):
            mock_api.camera.getDeviceCameraAnalyticsZones = self._zones(
                {"id": "0", "label": "Entrance", "type": ["person"]},
                {"id": "1", "label": "Lobby", "type": ["person"]},
            )
            mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent()
            mock_api.camera.getDeviceCameraQualityAndRetention = self._quality()
            await mv_collector.collect(device)

        zone_ids = {
            call[0][1]["zone_id"]
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_zone_info
        }
        assert zone_ids == {"0", "1"}
        mock_parent._set_metric.reset_mock()

        # Zone "1" removed; interval elapsed so a fresh fetch happens.
        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv.time.time",
            return_value=1_000.0 + 901,
        ):
            mock_api.camera.getDeviceCameraAnalyticsZones = self._zones({
                "id": "0",
                "label": "Entrance",
                "type": ["person"],
            })
            await mv_collector.collect(device)

        zone_ids = {
            call[0][1]["zone_id"]
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_zone_info
        }
        assert zone_ids == {"0"}

    # ------------------------------------------------------------------
    # #617 §1f per-series TTL threading
    # ------------------------------------------------------------------

    async def test_ttl_seconds_threaded_on_every_mv_series(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Every _set_metric for an mv_analytics series carries the solved ttl_seconds."""
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones({
            "id": "0",
            "label": "Entrance",
            "type": ["person"],
        })
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent({
            "zoneId": "0",
            "averageCount": 2,
        })
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality()

        await mv_collector.collect(device)

        assert mock_parent._set_metric.call_args_list  # sanity: some series emitted
        for call in mock_parent._set_metric.call_args_list:
            assert call.kwargs.get("ttl_seconds") == 1800.0
        mock_parent._group_ttl_seconds.assert_called_with(EndpointGroupName.MV_ANALYTICS)

    # ------------------------------------------------------------------
    # #549 rate-limiter org keying
    # ------------------------------------------------------------------

    async def test_rate_limiter_keyed_to_org_bucket(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Every analytics fetch acquires the limiter against the org bucket.

        collect() passes org_id as a keyword to each fetcher so log_api_call's
        context extraction keys the limiter deterministically to the org
        instead of the global (None) bucket (#549 / #270).
        """
        acquire = AsyncMock(return_value=0.0)
        mock_parent.rate_limiter = MagicMock()
        mock_parent.rate_limiter.acquire = acquire
        self._set_all_responses(mock_api)

        await mv_collector.collect(device)

        # One acquire per analytics fetch (zones, recent, quality/retention).
        assert acquire.await_count >= 3
        for call in acquire.await_args_list:
            assert call.args[0] == "org1"

    # ------------------------------------------------------------------
    # Pydantic domain-model validation
    # ------------------------------------------------------------------

    async def test_collect_validates_zones_via_domain_model(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Each zone row must be validated via CameraAnalyticsZone.model_validate."""
        zone_row = {"id": "0", "label": "Entrance", "type": ["person"]}
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(return_value=[zone_row])
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent()
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality()

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv.CameraAnalyticsZone.model_validate",
            wraps=CameraAnalyticsZone.model_validate,
        ) as spy:
            await mv_collector.collect(device)

        spy.assert_called_once_with(zone_row)

    async def test_collect_validates_recent_via_domain_model(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Each recent record must be validated via CameraAnalyticsRecentZone.model_validate."""
        recent_row = {"zoneId": "0", "entrances": 4, "averageCount": 2}
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones({
            "id": "0",
            "label": "Entrance",
            "type": ["person"],
        })
        mock_api.camera.getDeviceCameraAnalyticsRecent = MagicMock(return_value=[recent_row])
        mock_api.camera.getDeviceCameraQualityAndRetention = self._quality()

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv."
            "CameraAnalyticsRecentZone.model_validate",
            wraps=CameraAnalyticsRecentZone.model_validate,
        ) as spy:
            await mv_collector.collect(device)

        spy.assert_called_once_with(recent_row)

    async def test_collect_validates_quality_retention_via_domain_model(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """The quality/retention response must be validated via CameraQualityAndRetention."""
        qr_response = {
            "motionBasedRetentionEnabled": True,
            "audioRecordingEnabled": False,
            "restrictedBandwidthModeEnabled": False,
            "quality": "Standard",
            "resolution": "1280x720",
            "profileId": "123",
        }
        mock_api.camera.getDeviceCameraAnalyticsZones = self._zones()
        mock_api.camera.getDeviceCameraAnalyticsRecent = self._recent()
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(return_value=qr_response)

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv."
            "CameraQualityAndRetention.model_validate",
            wraps=CameraQualityAndRetention.model_validate,
        ) as spy:
            await mv_collector.collect(device)

        spy.assert_called_once_with(qr_response)

    async def test_collect_tolerates_missing_and_extra_fields(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Missing optional fields and unexpected extra fields must not raise."""
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(
            return_value=[{"id": "0", "someBrandNewField": "x"}]  # "label" omitted
        )
        mock_api.camera.getDeviceCameraAnalyticsRecent = MagicMock(
            return_value=[
                {"zoneId": "0", "averageCount": 2, "aFutureApiField": "unexpected"},
            ]
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={
                "quality": "Standard",
                "yetAnotherFutureField": 1,
            }
        )

        await mv_collector.collect(device)

        people_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_people_count
        ]
        assert len(people_calls) == 1
        _, labels, value = people_calls[0][0][:3]
        assert value == 2
        assert "zone_name" not in labels

        zone_info_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_zone_info
        ]
        assert len(zone_info_calls) == 1
        # Missing "label" on the zone row must still emit "" (not "None"), see F-004.
        assert zone_info_calls[0][0][1]["zone_name"] == ""  # noqa: PLC1901

        def value_for(gauge):
            for call in mock_parent._set_metric.call_args_list:
                if call[0][0] is gauge:
                    return call[0][2]
            raise AssertionError("gauge not set")

        assert value_for(mv_collector._mv_motion_based_retention_enabled) == 0.0
        assert value_for(mv_collector._mv_audio_recording_enabled) == 0.0
        assert value_for(mv_collector._mv_restricted_bandwidth_mode_enabled) == 0.0


class TestCameraAnalyticsRecentZone:
    """Unit tests for the inline recent-analytics response model (#549)."""

    def test_parses_typical_row(self) -> None:
        """A typical recent record parses zoneId + averageCount."""
        model = CameraAnalyticsRecentZone.model_validate({
            "zoneId": "0",
            "entrances": 4,
            "averageCount": 2,
        })
        assert str(model.zoneId) == "0"
        assert model.averageCount == 2

    def test_tolerates_missing_and_extra_fields(self) -> None:
        """Missing averageCount and unknown fields must not raise."""
        model = CameraAnalyticsRecentZone.model_validate({"zoneId": "3", "brandNew": "x"})
        assert str(model.zoneId) == "3"
        assert model.averageCount is None
