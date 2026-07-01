"""Tests for MTCollector sensor-to-gateway connectivity (#269)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.collectors.mt_sensor import MTSensorCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.error_handling import RetryableAPIError
from tests.helpers.base import BaseCollectorTest


class TestMTGatewayConnections(BaseCollectorTest):
    """Test MTCollector's getOrganizationSensorGatewaysConnectionsLatest handling."""

    collector_class = MTSensorCollector  # We'll test through the main sensor collector
    update_tier = UpdateTier.FAST

    @pytest.fixture
    def device_collector(self, mock_api, settings, isolated_registry):
        """Create a device collector for testing MT device metrics."""
        return DeviceCollector(api=mock_api, settings=settings)

    @pytest.fixture
    def mt_collector(self, device_collector):
        """Get the MT collector from the device collector."""
        return device_collector.mt_collector

    # --- _parse_iso_timestamp ---

    def test_parse_iso_timestamp_with_z_suffix(self, mt_collector):
        """A trailing 'Z' is normalized to +00:00 before parsing."""
        result = mt_collector._parse_iso_timestamp("2024-01-01T00:00:00Z")
        expected = datetime.fromisoformat("2024-01-01T00:00:00+00:00").timestamp()
        assert result == expected

    def test_parse_iso_timestamp_with_offset(self, mt_collector):
        """Timestamps with an explicit offset parse without modification."""
        result = mt_collector._parse_iso_timestamp("2024-01-01T00:00:00+02:00")
        expected = datetime.fromisoformat("2024-01-01T00:00:00+02:00").timestamp()
        assert result == expected

    def test_parse_iso_timestamp_none(self, mt_collector):
        """A missing timestamp yields None."""
        assert mt_collector._parse_iso_timestamp(None) is None

    def test_parse_iso_timestamp_empty_string(self, mt_collector):
        """An empty string yields None."""
        assert mt_collector._parse_iso_timestamp("") is None

    def test_parse_iso_timestamp_invalid(self, mt_collector):
        """An unparseable string yields None instead of raising."""
        assert mt_collector._parse_iso_timestamp("not-a-timestamp") is None

    # --- _fetch_gateway_connections ---

    async def test_fetch_gateway_connections_uses_shared_api_client(self, mt_collector):
        """Fetcher calls the raw SDK sensor controller with total_pages='all'."""
        connections = [{"rssi": -50}]
        mt_collector.api.sensor.getOrganizationSensorGatewaysConnectionsLatest = MagicMock(
            return_value=connections
        )

        result = await mt_collector._fetch_gateway_connections("123456")

        assert result == connections
        mt_collector.api.sensor.getOrganizationSensorGatewaysConnectionsLatest.assert_called_once_with(
            "123456", total_pages="all"
        )

    async def test_fetch_gateway_connections_validates_error_shape(self, mt_collector):
        """The SDK exhausted-retry error shape is normalized via validate_response_format."""
        mt_collector.api.sensor.getOrganizationSensorGatewaysConnectionsLatest = MagicMock(
            return_value={"errors": ["rate limit exceeded"]}
        )

        with pytest.raises(RetryableAPIError):
            await mt_collector._fetch_gateway_connections("123456")

    # --- _collect_org_gateway_connections ---

    async def test_collect_org_gateway_connections_emits_rssi_and_timestamp(self, mt_collector):
        """Happy path: rssi and last-connected epoch are emitted with the full label set."""
        rssi_metric = MagicMock()
        last_connected_metric = MagicMock()
        mt_collector.parent._sensor_gateway_rssi = rssi_metric
        mt_collector.parent._sensor_gateway_last_connected = last_connected_metric
        mt_collector.parent.inventory = None  # unfiltered

        connections = [
            {
                "lastReportedAt": "2024-01-01T00:00:00Z",
                "lastConnectedAt": "2024-01-01T00:00:00Z",
                "rssi": -55,
                "network": {"id": "N_1", "name": "Net 1"},
                "sensor": {"serial": "Q2MT-1", "name": "Sensor1", "mac": "00:00:00:00:00:01"},
                "gateway": {"serial": "Q2GW-1", "name": "Gateway1", "mac": "00:00:00:00:00:02"},
            }
        ]
        mt_collector.api.sensor.getOrganizationSensorGatewaysConnectionsLatest = MagicMock(
            return_value=connections
        )

        await mt_collector._collect_org_gateway_connections("123456", "Test Org")

        expected_labels = {
            "org_id": "123456",
            "org_name": "Test Org",
            "network_id": "N_1",
            "network_name": "Net 1",
            "sensor_serial": "Q2MT-1",
            "sensor_name": "Sensor1",
            "gateway_serial": "Q2GW-1",
        }
        rssi_metric.labels.assert_called_once_with(**expected_labels)
        rssi_metric.labels().set.assert_called_once_with(-55)

        last_connected_metric.labels.assert_called_once_with(**expected_labels)
        expected_epoch = datetime.fromisoformat("2024-01-01T00:00:00+00:00").timestamp()
        last_connected_metric.labels().set.assert_called_once_with(expected_epoch)

    async def test_collect_org_gateway_connections_skips_bad_timestamp(self, mt_collector):
        """An unparseable lastConnectedAt does not set the timestamp gauge, but rssi still is."""
        rssi_metric = MagicMock()
        last_connected_metric = MagicMock()
        mt_collector.parent._sensor_gateway_rssi = rssi_metric
        mt_collector.parent._sensor_gateway_last_connected = last_connected_metric
        mt_collector.parent.inventory = None

        connections = [
            {
                "lastConnectedAt": "garbage",
                "rssi": -60,
                "network": {"id": "N_1", "name": "Net 1"},
                "sensor": {"serial": "Q2MT-1", "name": "Sensor1"},
                "gateway": {"serial": "Q2GW-1"},
            }
        ]
        mt_collector.api.sensor.getOrganizationSensorGatewaysConnectionsLatest = MagicMock(
            return_value=connections
        )

        await mt_collector._collect_org_gateway_connections("123456", "Test Org")

        rssi_metric.labels.assert_called_once()
        rssi_metric.labels().set.assert_called_once_with(-60)
        last_connected_metric.labels.assert_not_called()

    async def test_collect_org_gateway_connections_missing_rssi(self, mt_collector):
        """A missing rssi value does not set the rssi gauge."""
        rssi_metric = MagicMock()
        last_connected_metric = MagicMock()
        mt_collector.parent._sensor_gateway_rssi = rssi_metric
        mt_collector.parent._sensor_gateway_last_connected = last_connected_metric
        mt_collector.parent.inventory = None

        connections = [
            {
                "lastConnectedAt": "2024-01-01T00:00:00Z",
                "network": {"id": "N_1", "name": "Net 1"},
                "sensor": {"serial": "Q2MT-1", "name": "Sensor1"},
                "gateway": {"serial": "Q2GW-1"},
            }
        ]
        mt_collector.api.sensor.getOrganizationSensorGatewaysConnectionsLatest = MagicMock(
            return_value=connections
        )

        await mt_collector._collect_org_gateway_connections("123456", "Test Org")

        rssi_metric.labels.assert_not_called()
        last_connected_metric.labels.assert_called_once()

    async def test_collect_org_gateway_connections_empty(self, mt_collector):
        """No connections returned -> no metrics emitted."""
        rssi_metric = MagicMock()
        mt_collector.parent._sensor_gateway_rssi = rssi_metric
        mt_collector.parent.inventory = None
        mt_collector.api.sensor.getOrganizationSensorGatewaysConnectionsLatest = MagicMock(
            return_value=[]
        )

        await mt_collector._collect_org_gateway_connections("123456", "Test Org")

        rssi_metric.labels.assert_not_called()

    async def test_collect_org_gateway_connections_applies_network_filter(self, mt_collector):
        """Rows outside the configured NetworkFilter allow-list are skipped."""
        rssi_metric = MagicMock()
        mt_collector.parent._sensor_gateway_rssi = rssi_metric
        mt_collector.parent._sensor_gateway_last_connected = MagicMock()

        mock_inventory = MagicMock()
        mock_inventory.get_allowed_network_ids = AsyncMock(return_value={"N_2"})
        mt_collector.parent.inventory = mock_inventory

        connections = [
            {
                "rssi": -55,
                "network": {"id": "N_1", "name": "Excluded Net"},
                "sensor": {"serial": "Q2MT-1", "name": "Sensor1"},
                "gateway": {"serial": "Q2GW-1"},
            },
            {
                "rssi": -60,
                "network": {"id": "N_2", "name": "Included Net"},
                "sensor": {"serial": "Q2MT-2", "name": "Sensor2"},
                "gateway": {"serial": "Q2GW-2"},
            },
        ]
        mt_collector.api.sensor.getOrganizationSensorGatewaysConnectionsLatest = MagicMock(
            return_value=connections
        )

        await mt_collector._collect_org_gateway_connections("123456", "Test Org")

        rssi_metric.labels.assert_called_once()
        rssi_metric.labels().set.assert_called_once_with(-60)
        mock_inventory.get_allowed_network_ids.assert_called_once_with("123456")


class TestMTSensorGatewayGauges(BaseCollectorTest):
    """Verify the two new gauges are registered under the frozen metric names/labels."""

    collector_class = MTSensorCollector
    update_tier = UpdateTier.FAST

    def test_gateway_rssi_gauge_registered_with_full_label_set(self, collector, metrics) -> None:
        """The rssi gauge exists under its frozen name with the full documented label set."""
        collector._sensor_gateway_rssi.labels(
            org_id="123456",
            org_name="Test Org",
            network_id="N_1",
            network_name="Net 1",
            sensor_serial="Q2MT-1",
            sensor_name="Sensor1",
            gateway_serial="Q2GW-1",
        ).set(-55)

        metrics.assert_gauge_value(
            "meraki_mt_gateway_rssi",
            -55,
            org_id="123456",
            org_name="Test Org",
            network_id="N_1",
            network_name="Net 1",
            sensor_serial="Q2MT-1",
            sensor_name="Sensor1",
            gateway_serial="Q2GW-1",
        )

    def test_gateway_last_connected_gauge_registered_with_full_label_set(
        self, collector, metrics
    ) -> None:
        """The last-connected gauge exists under its frozen name with the full label set."""
        collector._sensor_gateway_last_connected.labels(
            org_id="123456",
            org_name="Test Org",
            network_id="N_1",
            network_name="Net 1",
            sensor_serial="Q2MT-1",
            sensor_name="Sensor1",
            gateway_serial="Q2GW-1",
        ).set(1704067200.0)

        metrics.assert_gauge_value(
            "meraki_mt_gateway_last_connected_timestamp_seconds",
            1704067200.0,
            org_id="123456",
            org_name="Test Org",
            network_id="N_1",
            network_name="Net 1",
            sensor_serial="Q2MT-1",
            sensor_name="Sensor1",
            gateway_serial="Q2GW-1",
        )
