"""Tests for the MT device sensor collector using test helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.collectors.devices.mt import MTCollector
from meraki_dashboard_exporter.collectors.mt_sensor import MTSensorCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.domain_models import SensorMeasurement
from meraki_dashboard_exporter.core.error_handling import RetryableAPIError
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

    # --- F-061: validate_response_format on standalone fetchers ---

    async def test_fetch_sensor_devices_validates_error_shape(self, mt_collector):
        """F-061: SDK exhausted-retry error dict is normalized via validate_response_format."""
        mt_collector.api.organizations.getOrganizationDevices = MagicMock(
            return_value={"errors": ["rate limit exceeded"]}
        )

        with pytest.raises(RetryableAPIError):
            await mt_collector._fetch_sensor_devices("123456")

    async def test_fetch_organizations_validates_error_shape(self, mt_collector):
        """F-061: SDK exhausted-retry error dict is normalized via validate_response_format."""
        mt_collector.api.organizations.getOrganizations = MagicMock(
            return_value={"errors": ["rate limit exceeded"]}
        )

        with pytest.raises(RetryableAPIError):
            await mt_collector._fetch_organizations()

    # --- F-031 / F-089: NetworkFilter enforcement on org-wide sensor readings ---

    async def test_collect_org_sensors_applies_network_filter(self, mt_collector, test_device):
        """F-031/F-089: devices in networks outside the filter are dropped before readings."""
        dev_in = dict(test_device, serial="Q2MT-IN", networkId="N_2")
        dev_out = dict(test_device, serial="Q2MT-OUT", networkId="N_1")

        mock_inventory = MagicMock()
        mock_inventory.get_devices = AsyncMock(return_value=[dev_in, dev_out])
        mock_inventory.get_allowed_network_ids = AsyncMock(return_value={"N_2"})
        mt_collector.parent.inventory = mock_inventory

        mt_collector.api.sensor.getOrganizationSensorReadingsLatest = MagicMock(return_value=[])

        await mt_collector._collect_org_sensors("123456", "Test Org")

        mock_inventory.get_allowed_network_ids.assert_called_once_with("123456")
        # Only the included-network sensor's serial is queried.
        mt_collector.api.sensor.getOrganizationSensorReadingsLatest.assert_called_once_with(
            "123456", serials=["Q2MT-IN"], total_pages="all"
        )

    async def test_collect_org_sensors_uses_inventory_device_cache(self, mt_collector, test_device):
        """F-092: device listing goes through the injected inventory cache, not a raw fetch."""
        mock_inventory = MagicMock()
        mock_inventory.get_devices = AsyncMock(return_value=[dict(test_device)])
        mock_inventory.get_allowed_network_ids = AsyncMock(return_value=None)
        mt_collector.parent.inventory = mock_inventory
        mt_collector.api.organizations.getOrganizationDevices = MagicMock()
        mt_collector.api.sensor.getOrganizationSensorReadingsLatest = MagicMock(return_value=[])

        await mt_collector._collect_org_sensors("123456", "Test Org")

        mock_inventory.get_devices.assert_awaited_once_with("123456")
        mt_collector.api.organizations.getOrganizationDevices.assert_not_called()

    # --- F-069 / F-092: org-name reuse + inventory cache in collect_sensor_metrics ---

    async def test_collect_sensor_metrics_reuses_provided_org_name(self, mt_collector):
        """F-069: a provided org_name is reused instead of re-fetched from the API."""
        mt_collector._collect_org_sensors = AsyncMock()
        mt_collector._collect_org_gateway_connections = AsyncMock()
        mt_collector._get_org_name = AsyncMock(return_value="FROM_API")

        await mt_collector.collect_sensor_metrics(org_id="org1", org_name="Provided Org")

        mt_collector._get_org_name.assert_not_called()
        mt_collector._collect_org_sensors.assert_awaited_once_with("org1", "Provided Org")

    async def test_collect_sensor_metrics_uses_inventory_org_list(self, mt_collector):
        """F-092: org list comes from the inventory cache, not getOrganizations, when available."""
        mock_inventory = MagicMock()
        mock_inventory.get_organizations = AsyncMock(return_value=[{"id": "orgA", "name": "A"}])
        mt_collector.parent.inventory = mock_inventory
        mt_collector._collect_org_sensors = AsyncMock()
        mt_collector._collect_org_gateway_connections = AsyncMock()
        mt_collector._fetch_organizations = AsyncMock(return_value=[])
        mt_collector._get_org_name = AsyncMock(return_value="A")

        await mt_collector.collect_sensor_metrics()

        mock_inventory.get_organizations.assert_awaited()
        mt_collector._fetch_organizations.assert_not_called()
        mt_collector._collect_org_sensors.assert_awaited_once_with("orgA", "A")

    async def test_get_org_name_prefers_inventory_cache(self, mt_collector):
        """F-092: org name is resolved from the inventory cache, not a per-cycle getOrganization."""
        mock_inventory = MagicMock()
        mock_inventory.get_organizations = AsyncMock(
            return_value=[{"id": "orgA", "name": "Cached Org A"}]
        )
        mt_collector.parent.inventory = mock_inventory
        mt_collector.api.organizations.getOrganization = MagicMock()

        name = await mt_collector._get_org_name("orgA")

        assert name == "Cached Org A"
        mt_collector.api.organizations.getOrganization.assert_not_called()


class TestMTExpirationTracking(BaseCollectorTest):
    """F-088 / F-021: MT metrics must route through parent._set_metric expiration tracking."""

    collector_class = MTSensorCollector
    update_tier = UpdateTier.FAST

    def test_no_local_set_metric_value_override(self) -> None:
        """F-088: MTCollector must not shadow SubCollectorMixin's delegating _set_metric_value."""
        assert "_set_metric_value" not in MTCollector.__dict__

    def test_sensor_metric_routes_through_expiration(self, collector) -> None:
        """F-088: emitting a sensor gauge records an expiration-tracking update."""
        collector.expiration_manager = MagicMock()
        mt = collector.mt_collector
        device = {
            "serial": "Q2MT-1",
            "name": "S1",
            "model": "MT10",
            "networkId": "N_1",
            "networkName": "Net1",
            "orgId": "o1",
            "orgName": "Org1",
        }

        mt._process_metric(device=device, metric_type="temperature", metric_data={"celsius": 21.0})

        assert collector.expiration_manager.track_metric_update.called
        names = {
            c.kwargs["metric_name"]
            for c in collector.expiration_manager.track_metric_update.call_args_list
        }
        assert "meraki_mt_temperature_celsius" in names

    async def test_gateway_metric_routes_through_expiration(self, collector) -> None:
        """F-021: emitting the gateway RSSI gauge records an expiration-tracking update."""
        collector.expiration_manager = MagicMock()
        mt = collector.mt_collector
        mt.parent.inventory = None
        connections = [
            {
                "rssi": -55,
                "lastConnectedAt": "2024-01-01T00:00:00Z",
                "network": {"id": "N_1", "name": "Net1"},
                "sensor": {"serial": "Q2MT-1", "name": "S1"},
                "gateway": {"serial": "Q2GW-1"},
            }
        ]
        mt.api.sensor.getOrganizationSensorGatewaysConnectionsLatest = MagicMock(
            return_value=connections
        )

        await mt._collect_org_gateway_connections("o1", "Org1")

        names = {
            c.kwargs["metric_name"]
            for c in collector.expiration_manager.track_metric_update.call_args_list
        }
        assert "meraki_mt_gateway_rssi" in names
