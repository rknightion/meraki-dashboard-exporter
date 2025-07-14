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

    # Create mock metrics on the parent
    mock_parent._sensor_temperature = MagicMock()
    mock_parent._sensor_humidity = MagicMock()
    mock_parent._sensor_door = MagicMock()
    mock_parent._sensor_water = MagicMock()
    mock_parent._sensor_co2 = MagicMock()
    mock_parent._sensor_tvoc = MagicMock()
    mock_parent._sensor_pm25 = MagicMock()
    mock_parent._sensor_noise = MagicMock()
    mock_parent._sensor_battery = MagicMock()
    mock_parent._sensor_air_quality = MagicMock()
    mock_parent._sensor_voltage = MagicMock()
    mock_parent._sensor_current = MagicMock()
    mock_parent._sensor_real_power = MagicMock()
    mock_parent._sensor_apparent_power = MagicMock()
    mock_parent._sensor_power_factor = MagicMock()
    mock_parent._sensor_frequency = MagicMock()
    mock_parent._sensor_downstream_power = MagicMock()
    mock_parent._sensor_remote_lockout = MagicMock()

    collector = MTCollector(parent=mock_parent)
    return collector


class TestMTCollector:
    """Test MTCollector functionality."""

    def test_process_temperature_metric(self, mt_collector, mock_collector):
        """Test processing of temperature metric."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"

        # Process the metric
        mt_collector._process_metric(
            serial=serial,
            name=name,
            model=model,
            network_id="",
            network_name="",
            metric_type="temperature",
            metric_data={"celsius": 22.5},
        )

        # Verify temperature was set
        mt_collector.parent._sensor_temperature.labels.assert_called_once_with(
            serial=serial, name=name, sensor_type=model
        )
        mt_collector.parent._sensor_temperature.labels().set.assert_called_once_with(22.5)

    def test_skip_raw_temperature_metric(self, mt_collector, mock_collector):
        """Test that rawTemperature metric is skipped."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"

        # Process the metric
        mt_collector._process_metric(
            serial=serial,
            name=name,
            model=model,
            network_id="",
            network_name="",
            metric_type="rawTemperature",
            metric_data={"celsius": 22.5},
        )

        # Verify metric was NOT set - none of the sensor metrics should be called
        mt_collector.parent._sensor_temperature.labels.assert_not_called()

    def test_process_humidity_metric(self, mt_collector, mock_collector):
        """Test processing of humidity metric."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"

        # Process the metric
        mt_collector._process_metric(
            serial=serial,
            name=name,
            model=model,
            network_id="",
            network_name="",
            metric_type="humidity",
            metric_data={"relativePercentage": 45.0},
        )

        # Verify humidity was set
        mt_collector.parent._sensor_humidity.labels.assert_called_once_with(
            serial=serial, name=name, sensor_type=model
        )
        mt_collector.parent._sensor_humidity.labels().set.assert_called_once_with(45.0)

    def test_process_door_metric(self, mt_collector, mock_collector):
        """Test processing of door sensor metric."""
        serial = "Q2MT-XXXX"
        name = "DoorSensor1"
        model = "MT20"

        # Process the metric
        mt_collector._process_metric(
            serial=serial,
            name=name,
            model=model,
            network_id="",
            network_name="",
            metric_type="door",
            metric_data={"open": True},
        )

        # Verify door status was set (1 for open)
        mt_collector.parent._sensor_door.labels.assert_called_once_with(
            serial=serial, name=name, sensor_type=model
        )
        mt_collector.parent._sensor_door.labels().set.assert_called_once_with(1)

    def test_process_door_metric_closed(self, mt_collector, mock_collector):
        """Test processing of closed door sensor metric."""
        serial = "Q2MT-XXXX"
        name = "DoorSensor1"
        model = "MT20"

        # Process the metric
        mt_collector._process_metric(
            serial=serial,
            name=name,
            model=model,
            network_id="",
            network_name="",
            metric_type="door",
            metric_data={"open": False},
        )

        # Verify door status was set (0 for closed)
        mt_collector.parent._sensor_door.labels.assert_called_once_with(
            serial=serial, name=name, sensor_type=model
        )
        mt_collector.parent._sensor_door.labels().set.assert_called_once_with(0)

    def test_process_water_metric(self, mt_collector, mock_collector):
        """Test processing of water detection metric."""
        serial = "Q2MT-XXXX"
        name = "WaterSensor1"
        model = "MT10"

        # Process the metric
        mt_collector._process_metric(
            serial=serial,
            name=name,
            model=model,
            network_id="",
            network_name="",
            metric_type="water",
            metric_data={"present": True},
        )

        # Verify water detection was set (1 for present)
        mt_collector.parent._sensor_water.labels.assert_called_once_with(
            serial=serial, name=name, sensor_type=model
        )
        mt_collector.parent._sensor_water.labels().set.assert_called_once_with(1)

    def test_process_water_metric_not_present(self, mt_collector, mock_collector):
        """Test processing of water not detected metric."""
        serial = "Q2MT-XXXX"
        name = "WaterSensor1"
        model = "MT10"

        # Process the metric
        mt_collector._process_metric(
            serial=serial,
            name=name,
            model=model,
            network_id="",
            network_name="",
            metric_type="water",
            metric_data={"present": False},
        )

        # Verify water detection was set (0 for not present)
        mt_collector.parent._sensor_water.labels.assert_called_once_with(
            serial=serial, name=name, sensor_type=model
        )
        mt_collector.parent._sensor_water.labels().set.assert_called_once_with(0)

    def test_process_unknown_metric_type(self, mt_collector, mock_collector):
        """Test processing of unknown metric type."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"

        # Process the metric
        mt_collector._process_metric(
            serial=serial,
            name=name,
            model=model,
            network_id="",
            network_name="",
            metric_type="unknownType",
            metric_data={"value": 123},
        )

        # Verify no metric was set
        mt_collector.parent._sensor_temperature.labels.assert_not_called()
        mt_collector.parent._sensor_humidity.labels.assert_not_called()

    def test_process_metric_with_missing_value(self, mt_collector, mock_collector):
        """Test processing metric with missing value."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"

        # Process the metric
        mt_collector._process_metric(
            serial=serial,
            name=name,
            model=model,
            network_id="",
            network_name="",
            metric_type="temperature",
            metric_data={},  # Missing celsius value
        )

        # Verify no metric was set due to missing value
        mt_collector.parent._sensor_temperature.labels.assert_not_called()

    def test_process_metric_with_none_value(self, mt_collector, mock_collector):
        """Test processing metric with None value."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"

        # Process the metric
        mt_collector._process_metric(
            serial=serial,
            name=name,
            model=model,
            network_id="",
            network_name="",
            metric_type="temperature",
            metric_data={"celsius": None},
        )

        # Verify no metric was set due to None value
        mt_collector.parent._sensor_temperature.labels.assert_not_called()

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
            # Extract the metric type from the metric_data
            metric_type = metric_data.get("metric")
            # Remove the 'metric' key as it's passed separately
            actual_data = {k: v for k, v in metric_data.items() if k != "metric"}
            mt_collector._process_metric(
                serial=serial,
                name=name,
                model=model,
                network_id="",
                network_name="",
                metric_type=metric_type,
                metric_data=actual_data,
            )

        # Verify correct metrics were set (3 valid, 2 skipped)
        # Temperature should be set
        mt_collector.parent._sensor_temperature.labels.assert_called_once()
        # Humidity should be set
        mt_collector.parent._sensor_humidity.labels.assert_called_once()
        # Water should be set
        mt_collector.parent._sensor_water.labels.assert_called_once()

        # Verify debug log for skipped rawTemperature
        debug_calls = [
            call
            for call in mock_logger.debug.call_args_list
            if "Skipping undocumented rawTemperature" in str(call)
        ]
        assert len(debug_calls) == 1
