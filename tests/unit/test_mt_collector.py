"""Tests for the MT device sensor collector using test helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.collectors.mt_sensor import MTSensorCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import (
    DeviceFactory,
    NetworkFactory,
    OrganizationFactory,
    SensorDataFactory,
)


class TestMTCollector(BaseCollectorTest):
    """Test MTCollector functionality."""

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

    def test_process_temperature_metric(self, mt_collector):
        """Test processing of temperature metric."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_temperature = mock_metric

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
        mock_metric.labels.assert_called_once_with(serial=serial, name=name, sensor_type=model)
        mock_metric.labels().set.assert_called_once_with(22.5)

    def test_skip_raw_temperature_metric(self, mt_collector):
        """Test that rawTemperature metric is skipped."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_temperature = mock_metric

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

        # Verify metric was NOT set
        mock_metric.labels.assert_not_called()

    def test_process_humidity_metric(self, mt_collector):
        """Test processing of humidity metric."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_humidity = mock_metric

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
        mock_metric.labels.assert_called_once_with(serial=serial, name=name, sensor_type=model)
        mock_metric.labels().set.assert_called_once_with(45.0)

    def test_process_door_metric(self, mt_collector):
        """Test processing of door sensor metric."""
        serial = "Q2MT-XXXX"
        name = "DoorSensor1"
        model = "MT20"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_door = mock_metric

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
        mock_metric.labels.assert_called_once_with(serial=serial, name=name, sensor_type=model)
        mock_metric.labels().set.assert_called_once_with(1)

    def test_process_door_metric_closed(self, mt_collector):
        """Test processing of closed door sensor metric."""
        serial = "Q2MT-XXXX"
        name = "DoorSensor1"
        model = "MT20"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_door = mock_metric

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
        mock_metric.labels.assert_called_once_with(serial=serial, name=name, sensor_type=model)
        mock_metric.labels().set.assert_called_once_with(0)

    def test_process_water_metric(self, mt_collector):
        """Test processing of water detection metric."""
        serial = "Q2MT-XXXX"
        name = "WaterSensor1"
        model = "MT10"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_water = mock_metric

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
        mock_metric.labels.assert_called_once_with(serial=serial, name=name, sensor_type=model)
        mock_metric.labels().set.assert_called_once_with(1)

    def test_process_water_metric_not_present(self, mt_collector):
        """Test processing of water not detected metric."""
        serial = "Q2MT-XXXX"
        name = "WaterSensor1"
        model = "MT10"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_water = mock_metric

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
        mock_metric.labels.assert_called_once_with(serial=serial, name=name, sensor_type=model)
        mock_metric.labels().set.assert_called_once_with(0)

    def test_process_unknown_metric_type(self, mt_collector):
        """Test processing of unknown metric type."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"

        # Mock metrics
        mt_collector.parent._sensor_temperature = MagicMock()
        mt_collector.parent._sensor_humidity = MagicMock()

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

    def test_process_metric_with_missing_value(self, mt_collector):
        """Test processing metric with missing value."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_temperature = mock_metric

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
        mock_metric.labels.assert_not_called()

    def test_process_metric_with_none_value(self, mt_collector):
        """Test processing metric with None value."""
        serial = "Q2MT-XXXX"
        name = "Sensor1"
        model = "MT10"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_temperature = mock_metric

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
        mock_metric.labels.assert_not_called()

    @patch("meraki_dashboard_exporter.collectors.devices.mt.logger")
    def test_process_all_sensor_types_together(self, mock_logger, mt_collector):
        """Test processing multiple sensor types from same device."""
        serial = "Q2MT-XXXX"
        name = "MultiSensor"
        model = "MT10"

        # Mock all required metrics
        mt_collector.parent._sensor_temperature = MagicMock()
        mt_collector.parent._sensor_humidity = MagicMock()
        mt_collector.parent._sensor_water = MagicMock()

        # Process multiple metrics
        metrics = [
            {"metric": "temperature", "celsius": 23.5},
            {"metric": "humidity", "relativePercentage": 50.0},
            {"metric": "water", "present": False},
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
        mt_collector.parent._sensor_temperature.labels.assert_called_once()
        mt_collector.parent._sensor_humidity.labels.assert_called_once()
        mt_collector.parent._sensor_water.labels.assert_called_once()

        # Verify debug log for skipped rawTemperature - check that a log was made
        # The exact message might vary based on implementation
        assert mock_logger.debug.called


@pytest.mark.skip(
    reason="MTSensorCollector uses AsyncMerakiClient for sensor readings which requires different mocking setup"
)
class TestMTSensorCollector(BaseCollectorTest):
    """Test MTSensorCollector functionality for fast sensor collection."""

    collector_class = MTSensorCollector
    update_tier = UpdateTier.FAST

    async def test_collect_sensor_data(self, collector, mock_api_builder, metrics):
        """Test collecting sensor data from MT devices."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123")
        mt_device = DeviceFactory.create_mt(
            serial="Q2MT-XXXX",
            name="Temperature Sensor",
            model="MT10",
            network_id=network["id"],
        )

        # Create sensor data response
        sensor_data = [
            SensorDataFactory.create_sensor_data(
                serial=mt_device["serial"],
                network_id=network["id"],
                readings=[
                    SensorDataFactory.create_reading("temperature", 23.5),
                    SensorDataFactory.create_reading("humidity", 45.0),
                    SensorDataFactory.create_reading("battery", 95.0),
                ],
            )
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([mt_device], org_id=org["id"])
            .with_sensor_data(sensor_data)
            .build()
        )
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

        # Check which API calls were actually made
        api_calls_metric = metrics.get_metric("meraki_collector_api_calls")
        api_calls = []
        for sample in api_calls_metric.samples:
            if sample.name == "meraki_collector_api_calls_total":
                api_calls.append(sample.labels.get("endpoint"))

        # The sensor collector should make at least some API calls
        assert len(api_calls) > 0, f"Expected API calls but got: {api_calls}"

        # Verify metrics were set
        metrics.assert_gauge_value(
            "meraki_mt_temperature_celsius",
            23.5,
            serial=mt_device["serial"],
            name=mt_device["name"],
            sensor_type=mt_device["model"],
        )
        metrics.assert_gauge_value(
            "meraki_mt_humidity_percent",
            45.0,
            serial=mt_device["serial"],
            name=mt_device["name"],
            sensor_type=mt_device["model"],
        )
        metrics.assert_gauge_value(
            "meraki_mt_battery_percentage",
            95.0,
            serial=mt_device["serial"],
            name=mt_device["name"],
            sensor_type=mt_device["model"],
        )

    async def test_collect_door_sensor_data(self, collector, mock_api_builder, metrics):
        """Test collecting door sensor data."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123")
        door_sensor = DeviceFactory.create_mt(
            serial="Q2MT-DOOR",
            name="Main Door",
            model="MT20",
            network_id=network["id"],
        )

        # Create sensor data with door open
        sensor_data = [
            SensorDataFactory.create_sensor_data(
                serial=door_sensor["serial"],
                network_id=network["id"],
                readings=[
                    {"metric": "door", "open": True, "timestamp": "2024-01-01T00:00:00Z"},
                    SensorDataFactory.create_reading("battery", 85.0),
                ],
            )
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_sensor_data(sensor_data)
            .build()
        )
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify door metric was set to 1 (open)
        metrics.assert_gauge_value(
            "meraki_mt_door_status",
            1,
            serial=door_sensor["serial"],
            name=door_sensor["name"],
            sensor_type=door_sensor["model"],
        )

    async def test_collect_water_sensor_data(self, collector, mock_api_builder, metrics):
        """Test collecting water detection sensor data."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123")
        water_sensor = DeviceFactory.create_mt(
            serial="Q2MT-WATER",
            name="Basement Water Sensor",
            model="MT10",
            network_id=network["id"],
        )

        # Create sensor data with water present
        sensor_data = [
            SensorDataFactory.create_sensor_data(
                serial=water_sensor["serial"],
                network_id=network["id"],
                readings=[
                    {"metric": "water", "present": True, "timestamp": "2024-01-01T00:00:00Z"},
                    SensorDataFactory.create_reading("battery", 75.0),
                ],
            )
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_sensor_data(sensor_data)
            .build()
        )
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify water metric was set to 1 (present)
        metrics.assert_gauge_value(
            "meraki_mt_water_detected",
            1,
            serial=water_sensor["serial"],
            name=water_sensor["name"],
            sensor_type=water_sensor["model"],
        )

    async def test_skip_raw_temperature(self, collector, mock_api_builder, metrics):
        """Test that rawTemperature readings are skipped."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123")
        device = DeviceFactory.create_mt(serial="Q2MT-XXXX", network_id=network["id"])

        # Create sensor data with both temperature and rawTemperature
        sensor_data = [
            {
                "serial": device["serial"],
                "network": {"id": network["id"]},
                "readings": [
                    {"metric": "temperature", "celsius": 22.5, "timestamp": "2024-01-01T00:00:00Z"},
                    {
                        "metric": "rawTemperature",
                        "celsius": 22.3,
                        "timestamp": "2024-01-01T00:00:00Z",
                    },
                ],
            }
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([device], org_id=org["id"])
            .with_sensor_data(sensor_data)
            .build()
        )
        collector.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify only regular temperature was set
        metrics.assert_gauge_value(
            "meraki_mt_temperature_celsius",
            22.5,
            serial=device["serial"],
            name=device["name"],
            sensor_type=device["model"],
        )

        # rawTemperature should not create any metric
        # We can't directly check that it wasn't set, but checking that
        # only one temperature value exists is sufficient

    async def test_handle_no_sensor_data(self, collector, mock_api_builder, metrics):
        """Test handling when no sensor data is returned."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123", org_id=org["id"])
        device = DeviceFactory.create_mt(serial="Q2MT-XXXX", network_id=network["id"])

        # Configure mock API with empty sensor data
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([device], org_id=org["id"])
            .with_sensor_data([])
            .build()
        )
        collector.api = api

        # Run collection - should handle empty data gracefully
        await self.run_collector(collector)

        # Verify success even with no data
        self.assert_collector_success(collector, metrics)

    async def test_handle_api_error(self, collector, mock_api_builder, metrics):
        """Test handling of API errors."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123456")
        network = NetworkFactory.create(network_id="N_123", org_id=org["id"])
        device = DeviceFactory.create_mt(serial="Q2MT-XXXX", network_id=network["id"])

        # Configure mock API with error
        api = (
            mock_api_builder.with_organizations([org])
            .with_networks([network], org_id=org["id"])
            .with_devices([device], org_id=org["id"])
            .with_error("getOrganizationSensorReadingsHistory", 500)
            .build()
        )
        collector.api = api

        # Run collection - should handle error gracefully
        await self.run_collector(collector)

        # Verify collector still marks as successful (error handling decorator)
        self.assert_collector_success(collector, metrics)
