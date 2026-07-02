"""Tests for MV (Security Camera) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mv import MVCollector

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
        # SLOW-tier throttle interval for the near-static analytics-zones /
        # quality-retention calls (see F-027). 900s is the real-world default.
        parent.settings.update_intervals.slow = 900
        parent.rate_limiter = None
        parent.inventory = None

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
        assert mv_collector._mv_analytics_zones is not None
        assert mv_collector._mv_motion_based_retention_enabled is not None
        assert mv_collector._mv_audio_recording_enabled is not None
        assert mv_collector._mv_restricted_bandwidth_mode_enabled is not None
        assert mv_collector._mv_quality_retention_info is not None

    async def test_collect_zones_count(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Test analytics zones count is emitted."""
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(
            return_value=[
                # Real getDeviceCameraAnalyticsZones responses key the zone
                # object on `id`, not `zoneId` (verified against the vendored
                # OpenAPI spec) - see F-024.
                {"id": "0", "label": "Entrance", "type": ["person"]},
                {"id": "1", "label": "Lobby", "type": ["person"]},
            ]
        )
        mock_api.camera.getDeviceCameraAnalyticsLive = MagicMock(
            return_value={"ts": "2026-07-01T00:00:00Z", "zones": {}}
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={
                "motionBasedRetentionEnabled": True,
                "audioRecordingEnabled": False,
                "restrictedBandwidthModeEnabled": False,
                "quality": "Standard",
                "resolution": "1280x720",
                "profileId": "123",
            }
        )

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

    async def test_collect_people_count_with_zone_name_resolution(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Test per-zone people counts are emitted with resolved zone names."""
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(
            return_value=[
                # Real API field is `id`, not `zoneId` - see F-024.
                {"id": "0", "label": "Entrance", "type": ["person"]},
                {"id": "1", "label": "Lobby", "type": ["person"]},
            ]
        )
        mock_api.camera.getDeviceCameraAnalyticsLive = MagicMock(
            return_value={
                "ts": "2026-07-01T00:00:00Z",
                "zones": {"0": {"person": 3}, "1": {"person": 0}},
            }
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={
                "motionBasedRetentionEnabled": True,
                "audioRecordingEnabled": False,
                "restrictedBandwidthModeEnabled": False,
                "quality": "Standard",
                "resolution": "1280x720",
                "profileId": "123",
            }
        )

        await mv_collector.collect(device)

        people_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_people_count
        ]
        assert len(people_calls) == 2

        by_zone = {call[0][1]["zone_id"]: call for call in people_calls}
        _, labels_0, value_0 = by_zone["0"][0][:3]
        assert value_0 == 3
        assert labels_0["zone_name"] == "Entrance"

        _, labels_1, value_1 = by_zone["1"][0][:3]
        assert value_1 == 0
        assert labels_1["zone_name"] == "Lobby"

    async def test_collect_quality_booleans(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Test quality/retention boolean gauges map true->1 and false->0."""
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(return_value=[])
        mock_api.camera.getDeviceCameraAnalyticsLive = MagicMock(
            return_value={"ts": "2026-07-01T00:00:00Z", "zones": {}}
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={
                "motionBasedRetentionEnabled": True,
                "audioRecordingEnabled": False,
                "restrictedBandwidthModeEnabled": True,
                "quality": "Enhanced",
                "resolution": "1920x1080",
                "profileId": "456",
            }
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
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(return_value=[])
        mock_api.camera.getDeviceCameraAnalyticsLive = MagicMock(
            return_value={"ts": "2026-07-01T00:00:00Z", "zones": {}}
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={
                "motionBasedRetentionEnabled": True,
                "audioRecordingEnabled": False,
                "restrictedBandwidthModeEnabled": False,
                "quality": "High",
                "resolution": "2688x1512",
                "profileId": "789",
            }
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

    async def test_collect_analytics_live_failure_does_not_block_others(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Test that one failing call still lets the other two emit metrics."""
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(
            return_value=[{"id": "0", "label": "Entrance", "type": ["person"]}]
        )
        mock_api.camera.getDeviceCameraAnalyticsLive = MagicMock(
            side_effect=Exception("API connection failed")
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={
                "motionBasedRetentionEnabled": True,
                "audioRecordingEnabled": False,
                "restrictedBandwidthModeEnabled": False,
                "quality": "Standard",
                "resolution": "1280x720",
                "profileId": "123",
            }
        )

        # Should not raise - @with_error_handling(continue_on_error=True) catches it.
        await mv_collector.collect(device)

        gauges_set = {call[0][0] for call in mock_parent._set_metric.call_args_list}
        assert mv_collector._mv_analytics_zones in gauges_set
        assert mv_collector._mv_motion_based_retention_enabled in gauges_set
        assert mv_collector._mv_audio_recording_enabled in gauges_set
        assert mv_collector._mv_restricted_bandwidth_mode_enabled in gauges_set
        assert mv_collector._mv_quality_retention_info in gauges_set
        # The live call failed, so no people-count metrics should exist.
        assert mv_collector._mv_people_count not in gauges_set

    async def test_collect_zones_exhausted_retry_error_shape_handled_gracefully(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """The SDK exhausted-retry error shape (dict with 'errors') must be handled, not raised.

        getDeviceCameraAnalyticsZones is validated via validate_response_format
        (expected_type=list); a {"errors": [...]} response must raise internally
        and be absorbed by @with_error_handling, not propagate or emit a metric.
        """
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(
            return_value={"errors": ["internal server error"]}
        )
        mock_api.camera.getDeviceCameraAnalyticsLive = MagicMock(
            return_value={"ts": "2026-07-01T00:00:00Z", "zones": {}}
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={
                "motionBasedRetentionEnabled": True,
                "audioRecordingEnabled": False,
                "restrictedBandwidthModeEnabled": False,
                "quality": "Standard",
                "resolution": "1280x720",
                "profileId": "123",
            }
        )

        # Should not raise - validate_response_format raises internally, and
        # @with_error_handling absorbs it.
        await mv_collector.collect(device)

        gauges_set = {call[0][0] for call in mock_parent._set_metric.call_args_list}
        assert mv_collector._mv_analytics_zones not in gauges_set
        # The live-analytics call also has no zone map, but must still be
        # unaffected by the zones failure.
        assert mv_collector._mv_quality_retention_info in gauges_set

    async def test_collect_live_exhausted_retry_error_shape_handled_gracefully(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """The SDK exhausted-retry error shape (dict with 'errors') must be handled, not raised.

        getDeviceCameraAnalyticsLive is validated via validate_response_format
        (expected_type=dict); a {"errors": [...]} response must raise internally
        and be absorbed by @with_error_handling, not propagate or emit a metric.
        """
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(
            return_value=[{"id": "0", "label": "Entrance", "type": ["person"]}]
        )
        mock_api.camera.getDeviceCameraAnalyticsLive = MagicMock(
            return_value={"errors": ["internal server error"]}
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={
                "motionBasedRetentionEnabled": True,
                "audioRecordingEnabled": False,
                "restrictedBandwidthModeEnabled": False,
                "quality": "Standard",
                "resolution": "1280x720",
                "profileId": "123",
            }
        )

        # Should not raise - validate_response_format raises internally, and
        # @with_error_handling absorbs it.
        await mv_collector.collect(device)

        gauges_set = {call[0][0] for call in mock_parent._set_metric.call_args_list}
        assert mv_collector._mv_analytics_zones in gauges_set
        assert mv_collector._mv_quality_retention_info in gauges_set
        assert mv_collector._mv_people_count not in gauges_set

    async def test_collect_quality_retention_exhausted_retry_error_shape_handled_gracefully(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """The SDK exhausted-retry error shape (dict with 'errors') must be handled, not raised.

        getDeviceCameraQualityAndRetention is validated via validate_response_format
        (expected_type=dict); a {"errors": [...]} response must raise internally
        and be absorbed by @with_error_handling, not propagate or emit a metric.
        """
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(
            return_value=[{"id": "0", "label": "Entrance", "type": ["person"]}]
        )
        mock_api.camera.getDeviceCameraAnalyticsLive = MagicMock(
            return_value={"ts": "2026-07-01T00:00:00Z", "zones": {"0": {"person": 1}}}
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={"errors": ["internal server error"]}
        )

        # Should not raise - validate_response_format raises internally, and
        # @with_error_handling absorbs it.
        await mv_collector.collect(device)

        gauges_set = {call[0][0] for call in mock_parent._set_metric.call_args_list}
        assert mv_collector._mv_analytics_zones in gauges_set
        assert mv_collector._mv_people_count in gauges_set
        assert mv_collector._mv_motion_based_retention_enabled not in gauges_set
        assert mv_collector._mv_audio_recording_enabled not in gauges_set
        assert mv_collector._mv_restricted_bandwidth_mode_enabled not in gauges_set
        assert mv_collector._mv_quality_retention_info not in gauges_set

    async def test_collect_empty_zones(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Test that an empty zones list still emits a zero-count gauge."""
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(return_value=[])
        mock_api.camera.getDeviceCameraAnalyticsLive = MagicMock(
            return_value={"ts": "2026-07-01T00:00:00Z", "zones": {}}
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={
                "motionBasedRetentionEnabled": False,
                "audioRecordingEnabled": False,
                "restrictedBandwidthModeEnabled": False,
                "quality": "Standard",
                "resolution": "1280x720",
                "profileId": "123",
            }
        )

        await mv_collector.collect(device)

        zones_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_analytics_zones
        ]
        assert len(zones_calls) == 1
        assert zones_calls[0][0][2] == 0

    # ------------------------------------------------------------------
    # Null quality/resolution/profileId label handling (F-004)
    #
    # The OpenAPI schema for getDeviceCameraQualityAndRetention marks all
    # three fields nullable=true. str(None) would previously produce the
    # literal label value "None"; these must come through as "".
    # ------------------------------------------------------------------

    async def test_collect_quality_retention_info_null_values_emit_empty_labels(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Null quality/resolution/profileId must emit "" labels, not the string "None"."""
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(return_value=[])
        mock_api.camera.getDeviceCameraAnalyticsLive = MagicMock(
            return_value={"ts": "2026-07-01T00:00:00Z", "zones": {}}
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={
                "motionBasedRetentionEnabled": False,
                "audioRecordingEnabled": False,
                "restrictedBandwidthModeEnabled": False,
                "quality": None,
                "resolution": None,
                "profileId": None,
            }
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
    # SLOW-tier throttle gating for near-static config (F-027)
    #
    # collect() is dispatched every MEDIUM-tier (300s) cycle by
    # DeviceCollector, but analytics-zones and quality/retention are
    # near-static camera config self-gated to the SLOW cadence
    # (settings.update_intervals.slow). Only the live-analytics call must
    # run every cycle.
    # ------------------------------------------------------------------

    def _set_all_responses(self, mock_api: MagicMock) -> None:
        mock_api.camera.getDeviceCameraAnalyticsZones = MagicMock(
            return_value=[{"id": "0", "label": "Entrance", "type": ["person"]}]
        )
        mock_api.camera.getDeviceCameraAnalyticsLive = MagicMock(
            return_value={"ts": "2026-07-01T00:00:00Z", "zones": {"0": {"person": 2}}}
        )
        mock_api.camera.getDeviceCameraQualityAndRetention = MagicMock(
            return_value={
                "motionBasedRetentionEnabled": True,
                "audioRecordingEnabled": False,
                "restrictedBandwidthModeEnabled": False,
                "quality": "Standard",
                "resolution": "1280x720",
                "profileId": "123",
            }
        )

    async def test_static_config_skipped_within_slow_interval(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """A second call on the very next (MEDIUM-tier) cycle must not re-fetch zones/quality."""
        self._set_all_responses(mock_api)

        await mv_collector.collect(device)
        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 1
        assert mock_api.camera.getDeviceCameraQualityAndRetention.call_count == 1
        assert mock_api.camera.getDeviceCameraAnalyticsLive.call_count == 1

        await mv_collector.collect(device)
        # Static config calls must not repeat...
        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 1
        assert mock_api.camera.getDeviceCameraQualityAndRetention.call_count == 1
        # ...but the volatile live-analytics call must run every cycle.
        assert mock_api.camera.getDeviceCameraAnalyticsLive.call_count == 2

    async def test_zone_name_resolution_uses_cached_map_when_static_config_skipped(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """zone_name must still resolve on a cycle where the zones call is gated out."""
        self._set_all_responses(mock_api)

        await mv_collector.collect(device)
        mock_parent._set_metric.reset_mock()

        await mv_collector.collect(device)

        people_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_people_count
        ]
        assert len(people_calls) == 1
        _, labels, _value = people_calls[0][0][:3]
        assert labels["zone_name"] == "Entrance"

    async def test_static_config_collected_again_after_slow_interval_elapses(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """Once the SLOW interval has elapsed, the next cycle must hit the API again."""
        self._set_all_responses(mock_api)

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv.time.time",
            return_value=1_000.0,
        ):
            await mv_collector.collect(device)
        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 1

        # Still short of the 900s SLOW interval.
        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv.time.time",
            return_value=1_000.0 + 300,
        ):
            await mv_collector.collect(device)
        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 1

        # Now past the SLOW interval (3 MEDIUM cycles later) - must collect again.
        with patch(
            "meraki_dashboard_exporter.collectors.devices.mv.time.time",
            return_value=1_000.0 + 901,
        ):
            await mv_collector.collect(device)
        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 2
        assert mock_api.camera.getDeviceCameraQualityAndRetention.call_count == 2

    async def test_static_config_gating_is_per_camera(
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
        assert mock_api.camera.getDeviceCameraQualityAndRetention.call_count == 2

    async def test_static_config_interval_zero_disables_gating(
        self,
        mv_collector: MVCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
        device: dict,
    ) -> None:
        """A non-positive SLOW interval must disable gating (always collect)."""
        mock_parent.settings.update_intervals.slow = 0
        self._set_all_responses(mock_api)

        await mv_collector.collect(device)
        await mv_collector.collect(device)

        assert mock_api.camera.getDeviceCameraAnalyticsZones.call_count == 2
        assert mock_api.camera.getDeviceCameraQualityAndRetention.call_count == 2
