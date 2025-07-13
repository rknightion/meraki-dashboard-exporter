"""Tests for the MT device sensor collector."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.collectors.devices.mt import MTCollector


@pytest.fixture
def mock_collector():
    """Create a mock collector with required attributes."""
    mock = MagicMock()
    mock._track_api_call = Mock()
    mock._set_metric_value = Mock()
    mock.logger = MagicMock()
    return mock


@pytest.fixture
def mt_collector(mock_collector, monkeypatch):
    """Create an MTCollector instance with mocked parent methods."""
    # Use isolated registry
    isolated_registry = CollectorRegistry()
    monkeypatch.setattr("meraki_dashboard_exporter.core.collector.REGISTRY", isolated_registry)

    # Create a mock parent for the MT collector
    mock_parent = MagicMock()
    mock_parent._track_api_call = mock_collector._track_api_call
    mock_parent._set_metric_value = mock_collector._set_metric_value

    collector = MTCollector(parent=mock_parent)
    # Inject mocked methods
    collector._track_api_call = mock_collector._track_api_call
    collector._set_metric_value = mock_collector._set_metric_value
    collector.logger = mock_collector.logger
    return collector


class TestMTCollector:
    """Test MTCollector functionality."""

    def test_process_temperature_metric(self, mt_collector, mock_collector):
        """Test processing of temperature metric."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"
        metric_data = {
            "metric": "temperature",
            "celsius": 22.5,
        }

        # Process the metric
        mt_collector._process_sensor_metric(serial, name, model, metric_data)

        # Verify temperature was set
        mock_collector._set_metric_value.assert_called_once_with(
            "_sensor_temperature",
            {"serial": serial, "name": name, "sensor_type": model},
            22.5,
        )

    def test_skip_raw_temperature_metric(self, mt_collector, mock_collector):
        """Test that rawTemperature metric is skipped."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"
        metric_data = {
            "metric": "rawTemperature",
            "celsius": 22.5,
        }

        # Process the metric
        mt_collector._process_sensor_metric(serial, name, model, metric_data)

        # Verify metric was NOT set
        mock_collector._set_metric_value.assert_not_called()

    def test_process_humidity_metric(self, mt_collector, mock_collector):
        """Test processing of humidity metric."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"
        metric_data = {
            "metric": "humidity",
            "relativePercentage": 45.0,
        }

        # Process the metric
        mt_collector._process_sensor_metric(serial, name, model, metric_data)

        # Verify humidity was set
        mock_collector._set_metric_value.assert_called_once_with(
            "_sensor_humidity",
            {"serial": serial, "name": name, "sensor_type": model},
            45.0,
        )

    def test_process_door_metric(self, mt_collector, mock_collector):
        """Test processing of door sensor metric."""
        serial = "Q2MT-XXXX"
        name = "DoorSensor1"
        model = "MT20"
        metric_data = {
            "metric": "door",
            "isOpen": True,
        }

        # Process the metric
        mt_collector._process_sensor_metric(serial, name, model, metric_data)

        # Verify door status was set (1.0 for open)
        mock_collector._set_metric_value.assert_called_once_with(
            "_sensor_door",
            {"serial": serial, "name": name, "sensor_type": model},
            1.0,
        )

    def test_process_door_metric_closed(self, mt_collector, mock_collector):
        """Test processing of closed door sensor metric."""
        serial = "Q2MT-XXXX"
        name = "DoorSensor1"
        model = "MT20"
        metric_data = {
            "metric": "door",
            "isOpen": False,
        }

        # Process the metric
        mt_collector._process_sensor_metric(serial, name, model, metric_data)

        # Verify door status was set (0.0 for closed)
        mock_collector._set_metric_value.assert_called_once_with(
            "_sensor_door",
            {"serial": serial, "name": name, "sensor_type": model},
            0.0,
        )

    def test_process_water_metric(self, mt_collector, mock_collector):
        """Test processing of water detection metric."""
        serial = "Q2MT-XXXX"
        name = "WaterSensor1"
        model = "MT10"
        metric_data = {
            "metric": "water",
            "isPresent": True,
        }

        # Process the metric
        mt_collector._process_sensor_metric(serial, name, model, metric_data)

        # Verify water detection was set (1.0 for present)
        mock_collector._set_metric_value.assert_called_once_with(
            "_sensor_water",
            {"serial": serial, "name": name, "sensor_type": model},
            1.0,
        )

    def test_process_water_metric_not_present(self, mt_collector, mock_collector):
        """Test processing of water not detected metric."""
        serial = "Q2MT-XXXX"
        name = "WaterSensor1"
        model = "MT10"
        metric_data = {
            "metric": "water",
            "isPresent": False,
        }

        # Process the metric
        mt_collector._process_sensor_metric(serial, name, model, metric_data)

        # Verify water detection was set (0.0 for not present)
        mock_collector._set_metric_value.assert_called_once_with(
            "_sensor_water",
            {"serial": serial, "name": name, "sensor_type": model},
            0.0,
        )

    def test_process_unknown_metric_type(self, mt_collector, mock_collector):
        """Test processing of unknown metric type."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"
        metric_data = {
            "metric": "unknownType",
            "value": 123,
        }

        # Process the metric
        mt_collector._process_sensor_metric(serial, name, model, metric_data)

        # Verify no metric was set
        mock_collector._set_metric_value.assert_not_called()

    def test_process_metric_with_missing_value(self, mt_collector, mock_collector):
        """Test processing metric with missing value."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"
        metric_data = {
            "metric": "temperature",
            # Missing celsius value
        }

        # Process the metric
        mt_collector._process_sensor_metric(serial, name, model, metric_data)

        # Verify no metric was set due to missing value
        mock_collector._set_metric_value.assert_not_called()

    def test_process_metric_with_none_value(self, mt_collector, mock_collector):
        """Test processing metric with None value."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"
        metric_data = {
            "metric": "temperature",
            "celsius": None,
        }

        # Process the metric
        mt_collector._process_sensor_metric(serial, name, model, metric_data)

        # Verify no metric was set due to None value
        mock_collector._set_metric_value.assert_not_called()

    def test_device_supported(self, mt_collector):
        """Test device support check."""
        assert mt_collector.is_device_supported({"model": "MT10"}) is True
        assert mt_collector.is_device_supported({"model": "MT12"}) is True
        assert mt_collector.is_device_supported({"model": "MT20"}) is True
        assert mt_collector.is_device_supported({"model": "MT21"}) is True
        assert mt_collector.is_device_supported({"model": "MR36"}) is False
        assert mt_collector.is_device_supported({"model": "MS120"}) is False
        assert mt_collector.is_device_supported({}) is False

    @patch("meraki_dashboard_exporter.collectors.devices.mt.logger")
    def test_process_all_sensor_types_together(self, mock_logger, mt_collector, mock_collector):
        """Test processing multiple sensor types from same device."""
        serial = "Q2MT-XXXX"
        name = "MultiSensor"
        model = "MT10"

        # Process multiple metrics
        metrics = [
            {"metric": "temperature", "celsius": 23.5},
            {"metric": "humidity", "relativePercentage": 50.0},
            {"metric": "water", "isPresent": False},
            {"metric": "rawTemperature", "celsius": 23.5},  # Should be skipped
            {"metric": "unknownMetric", "value": 999},  # Should log unknown
        ]

        for metric_data in metrics:
            mt_collector._process_sensor_metric(serial, name, model, metric_data)

        # Verify correct metrics were set (3 valid, 2 skipped)
        assert mock_collector._set_metric_value.call_count == 3

        # Verify debug log for skipped rawTemperature
        debug_calls = [
            call
            for call in mock_logger.debug.call_args_list
            if "Skipping undocumented rawTemperature" in str(call)
        ]
        assert len(debug_calls) == 1
