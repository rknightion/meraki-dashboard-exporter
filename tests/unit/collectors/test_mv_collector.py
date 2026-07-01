"""Tests for MV (Security Camera) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

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
                {"zoneId": 0, "label": "Entrance", "type": ["person"]},
                {"zoneId": 1, "label": "Lobby", "type": ["person"]},
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
                {"zoneId": 0, "label": "Entrance", "type": ["person"]},
                {"zoneId": 1, "label": "Lobby", "type": ["person"]},
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
            return_value=[{"zoneId": 0, "label": "Entrance", "type": ["person"]}]
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

        people_calls = [
            call
            for call in mock_parent._set_metric.call_args_list
            if call[0][0] is mv_collector._mv_people_count
        ]
        assert len(people_calls) == 0
