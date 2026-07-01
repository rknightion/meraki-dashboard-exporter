"""Tests for the MT device sensor collector using test helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.collectors.mt_sensor import MTSensorCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.domain_models import SensorMeasurement
from tests.helpers.base import BaseCollectorTest


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

    @pytest.fixture
    def test_device(self):
        """Create a test device with all required fields."""
        return {
            "serial": "Q2MT-XXXX",
            "name": "Sensor1",
            "model": "MT10",
            "networkId": "N_123",
            "networkName": "Test Network",
            "orgId": "123456",
            "orgName": "Test Org",
        }

    def test_process_temperature_metric(self, mt_collector, test_device):
        """Test processing of temperature metric."""
        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_temperature = mock_metric

        # Process the metric
        mt_collector._process_metric(
            device=test_device,
            metric_type="temperature",
            metric_data={"celsius": 22.5},
        )

        # Verify temperature was set with new labels including org/network
        expected_labels = {
            "serial": test_device["serial"],
            "name": test_device["name"],
            "model": test_device["model"],
            "org_id": test_device["orgId"],
            "org_name": test_device["orgName"],
            "network_id": test_device["networkId"],
            "network_name": test_device["networkName"],
            "device_type": "MT",
        }
        mock_metric.labels.assert_called_once_with(**expected_labels)
        mock_metric.labels().set.assert_called_once_with(22.5)

    def test_skip_raw_temperature_metric(self, mt_collector, test_device):
        """Test that rawTemperature metric is skipped."""
        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_temperature = mock_metric

        # Process the metric
        mt_collector._process_metric(
            device=test_device,
            metric_type="rawTemperature",
            metric_data={"celsius": 22.5},
        )

        # Verify metric was NOT set
        mock_metric.labels.assert_not_called()

    def test_process_humidity_metric(self, mt_collector, test_device):
        """Test processing of humidity metric."""
        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_humidity = mock_metric

        # Process the metric
        mt_collector._process_metric(
            device=test_device,
            metric_type="humidity",
            metric_data={"relativePercentage": 45.0},
        )

        # Verify humidity was set with new labels including org/network
        expected_labels = {
            "serial": test_device["serial"],
            "name": test_device["name"],
            "model": test_device["model"],
            "org_id": test_device["orgId"],
            "org_name": test_device["orgName"],
            "network_id": test_device["networkId"],
            "network_name": test_device["networkName"],
            "device_type": "MT",
        }
        mock_metric.labels.assert_called_once_with(**expected_labels)
        mock_metric.labels().set.assert_called_once_with(45.0)

    def test_process_door_metric(self, mt_collector, test_device):
        """Test processing of door sensor metric."""
        # Update test device model to MT20 for door sensor
        test_device = dict(test_device)
        test_device["model"] = "MT20"
        test_device["name"] = "DoorSensor1"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_door = mock_metric

        # Process the metric
        mt_collector._process_metric(
            device=test_device,
            metric_type="door",
            metric_data={"open": True},
        )

        # Verify door status was set (1 for open) with new labels
        expected_labels = {
            "serial": test_device["serial"],
            "name": test_device["name"],
            "model": test_device["model"],
            "org_id": test_device["orgId"],
            "org_name": test_device["orgName"],
            "network_id": test_device["networkId"],
            "network_name": test_device["networkName"],
            "device_type": "MT",
        }
        mock_metric.labels.assert_called_once_with(**expected_labels)
        mock_metric.labels().set.assert_called_once_with(1)

    def test_process_door_metric_closed(self, mt_collector, test_device):
        """Test processing of closed door sensor metric."""
        # Update test device model to MT20 for door sensor
        test_device = dict(test_device)
        test_device["model"] = "MT20"
        test_device["name"] = "DoorSensor1"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_door = mock_metric

        # Process the metric
        mt_collector._process_metric(
            device=test_device,
            metric_type="door",
            metric_data={"open": False},
        )

        # Verify door status was set (0 for closed) with new labels
        expected_labels = {
            "serial": test_device["serial"],
            "name": test_device["name"],
            "model": test_device["model"],
            "org_id": test_device["orgId"],
            "org_name": test_device["orgName"],
            "network_id": test_device["networkId"],
            "network_name": test_device["networkName"],
            "device_type": "MT",
        }
        mock_metric.labels.assert_called_once_with(**expected_labels)
        mock_metric.labels().set.assert_called_once_with(0)

    def test_process_water_metric(self, mt_collector, test_device):
        """Test processing of water detection metric."""
        # Update test device name for water sensor
        test_device = dict(test_device)
        test_device["name"] = "WaterSensor1"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_water = mock_metric

        # Process the metric
        mt_collector._process_metric(
            device=test_device,
            metric_type="water",
            metric_data={"present": True},
        )

        # Verify water detection was set (1 for present) with new labels
        expected_labels = {
            "serial": test_device["serial"],
            "name": test_device["name"],
            "model": test_device["model"],
            "org_id": test_device["orgId"],
            "org_name": test_device["orgName"],
            "network_id": test_device["networkId"],
            "network_name": test_device["networkName"],
            "device_type": "MT",
        }
        mock_metric.labels.assert_called_once_with(**expected_labels)
        mock_metric.labels().set.assert_called_once_with(1)

    def test_process_water_metric_not_present(self, mt_collector, test_device):
        """Test processing of water not detected metric."""
        # Update test device name for water sensor
        test_device = dict(test_device)
        test_device["name"] = "WaterSensor1"

        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_water = mock_metric

        # Process the metric
        mt_collector._process_metric(
            device=test_device,
            metric_type="water",
            metric_data={"present": False},
        )

        # Verify water detection was set (0 for not present) with new labels
        expected_labels = {
            "serial": test_device["serial"],
            "name": test_device["name"],
            "model": test_device["model"],
            "org_id": test_device["orgId"],
            "org_name": test_device["orgName"],
            "network_id": test_device["networkId"],
            "network_name": test_device["networkName"],
            "device_type": "MT",
        }
        mock_metric.labels.assert_called_once_with(**expected_labels)
        mock_metric.labels().set.assert_called_once_with(0)

    def test_process_unknown_metric_type(self, mt_collector, test_device):
        """Test processing of unknown metric type."""
        # Mock metrics
        mt_collector.parent._sensor_temperature = MagicMock()
        mt_collector.parent._sensor_humidity = MagicMock()

        # Process the metric
        mt_collector._process_metric(
            device=test_device,
            metric_type="unknownType",
            metric_data={"value": 123},
        )

        # Verify no metric was set
        mt_collector.parent._sensor_temperature.labels.assert_not_called()
        mt_collector.parent._sensor_humidity.labels.assert_not_called()

    def test_process_metric_with_missing_value(self, mt_collector, test_device):
        """Test processing metric with missing value."""
        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_temperature = mock_metric

        # Process the metric
        mt_collector._process_metric(
            device=test_device,
            metric_type="temperature",
            metric_data={},  # Missing celsius value
        )

        # Verify no metric was set due to missing value
        mock_metric.labels.assert_not_called()

    def test_process_metric_with_none_value(self, mt_collector, test_device):
        """Test processing metric with None value."""
        # Mock the parent's metric
        mock_metric = MagicMock()
        mt_collector.parent._sensor_temperature = mock_metric

        # Process the metric
        mt_collector._process_metric(
            device=test_device,
            metric_type="temperature",
            metric_data={"celsius": None},
        )

        # Verify no metric was set due to None value
        mock_metric.labels.assert_not_called()

    @patch("meraki_dashboard_exporter.collectors.devices.mt.logger")
    def test_process_all_sensor_types_together(self, mock_logger, mt_collector, test_device):
        """Test processing multiple sensor types from same device."""
        # Update test device name
        test_device = dict(test_device)
        test_device["name"] = "MultiSensor"

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
                device=test_device,
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

    # --- Issue #246: no2 / o3 / pm10 sensor metrics ---

    def test_process_no2_metric(self, mt_collector, test_device):
        """Test processing of NO2 concentration metric (fallback direct-processing path)."""
        mock_metric = MagicMock()
        mt_collector.parent._sensor_no2 = mock_metric

        mt_collector._process_metric(
            device=test_device,
            metric_type="no2",
            metric_data={"concentration": 12},
        )

        expected_labels = {
            "serial": test_device["serial"],
            "name": test_device["name"],
            "model": test_device["model"],
            "org_id": test_device["orgId"],
            "org_name": test_device["orgName"],
            "network_id": test_device["networkId"],
            "network_name": test_device["networkName"],
            "device_type": "MT",
        }
        mock_metric.labels.assert_called_once_with(**expected_labels)
        mock_metric.labels().set.assert_called_once_with(12)

    def test_process_o3_metric(self, mt_collector, test_device):
        """Test processing of O3 concentration metric (fallback direct-processing path)."""
        mock_metric = MagicMock()
        mt_collector.parent._sensor_o3 = mock_metric

        mt_collector._process_metric(
            device=test_device,
            metric_type="o3",
            metric_data={"concentration": 34},
        )

        expected_labels = {
            "serial": test_device["serial"],
            "name": test_device["name"],
            "model": test_device["model"],
            "org_id": test_device["orgId"],
            "org_name": test_device["orgName"],
            "network_id": test_device["networkId"],
            "network_name": test_device["networkName"],
            "device_type": "MT",
        }
        mock_metric.labels.assert_called_once_with(**expected_labels)
        mock_metric.labels().set.assert_called_once_with(34)

    def test_process_pm10_metric(self, mt_collector, test_device):
        """Test processing of PM10 concentration metric (fallback direct-processing path)."""
        mock_metric = MagicMock()
        mt_collector.parent._sensor_pm10 = mock_metric

        mt_collector._process_metric(
            device=test_device,
            metric_type="pm10",
            metric_data={"concentration": 5},
        )

        expected_labels = {
            "serial": test_device["serial"],
            "name": test_device["name"],
            "model": test_device["model"],
            "org_id": test_device["orgId"],
            "org_name": test_device["orgName"],
            "network_id": test_device["networkId"],
            "network_name": test_device["networkName"],
            "device_type": "MT",
        }
        mock_metric.labels.assert_called_once_with(**expected_labels)
        mock_metric.labels().set.assert_called_once_with(5)

    def test_extract_metric_value_no2_o3_pm10(self, mt_collector):
        """#246: no2/o3/pm10 read from the `concentration` field like co2/tvoc/pm25."""
        assert mt_collector._extract_metric_value("no2", {"concentration": 12}) == 12
        assert mt_collector._extract_metric_value("o3", {"concentration": 34}) == 34
        assert mt_collector._extract_metric_value("pm10", {"concentration": 5}) == 5

    def test_process_validated_metric_no2(self, mt_collector, test_device):
        """#246: validated SensorMeasurement path routes no2 to its own gauge."""
        mock_metric = MagicMock()
        mt_collector.parent._sensor_no2 = mock_metric

        mt_collector._process_validated_metric(
            device=test_device,
            measurement=SensorMeasurement(metric="no2", value=12.0),
        )

        mock_metric.labels().set.assert_called_once_with(12.0)

    def test_process_validated_metric_o3(self, mt_collector, test_device):
        """#246: validated SensorMeasurement path routes o3 to its own gauge."""
        mock_metric = MagicMock()
        mt_collector.parent._sensor_o3 = mock_metric

        mt_collector._process_validated_metric(
            device=test_device,
            measurement=SensorMeasurement(metric="o3", value=34.0),
        )

        mock_metric.labels().set.assert_called_once_with(34.0)

    def test_process_validated_metric_pm10(self, mt_collector, test_device):
        """#246: validated SensorMeasurement path routes pm10 to its own gauge."""
        mock_metric = MagicMock()
        mt_collector.parent._sensor_pm10 = mock_metric

        mt_collector._process_validated_metric(
            device=test_device,
            measurement=SensorMeasurement(metric="pm10", value=5.0),
        )

        mock_metric.labels().set.assert_called_once_with(5.0)

    # --- Issue #249: _collect_org_sensors must use the shared API client ---

    async def test_collect_org_sensors_uses_shared_api_client(self, mt_collector, test_device):
        """_collect_org_sensors must call self.api.sensor directly, not build a new client."""
        devices = [dict(test_device)]
        mt_collector.api.organizations.getOrganizationDevices = MagicMock(return_value=devices)

        readings = [
            {
                "serial": test_device["serial"],
                "network": {
                    "id": test_device["networkId"],
                    "name": test_device["networkName"],
                },
                "readings": [{"metric": "temperature", "celsius": 21.0}],
            }
        ]
        mt_collector.api.sensor.getOrganizationSensorReadingsLatest = MagicMock(
            return_value=readings
        )

        await mt_collector._collect_org_sensors("123456", "Test Org")

        mt_collector.api.sensor.getOrganizationSensorReadingsLatest.assert_called_once_with(
            "123456", serials=[test_device["serial"]], total_pages="all"
        )
