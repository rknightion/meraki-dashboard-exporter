"""Tests for metrics creation and management."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from meraki_dashboard_exporter.core.metrics import (
    LabelName,
    MetricDefinition,
    MetricFactory,
    MetricType,
    create_info_labels,
    validate_metric_name,
)


class TestLabelNameEnum:
    """Test LabelName enum values."""

    def test_organization_labels(self) -> None:
        """Test organization label names."""
        assert LabelName.ORG_ID == "org_id"
        assert LabelName.ORG_NAME == "org_name"

    def test_network_labels(self) -> None:
        """Test network label names."""
        assert LabelName.NETWORK_ID == "network_id"
        assert LabelName.NETWORK_NAME == "network_name"

    def test_device_labels(self) -> None:
        """Test device label names."""
        assert LabelName.SERIAL == "serial"
        assert LabelName.NAME == "name"
        assert LabelName.MODEL == "model"
        assert LabelName.DEVICE_TYPE == "device_type"

    def test_port_labels(self) -> None:
        """Test port/interface label names."""
        assert LabelName.PORT_ID == "port_id"
        assert LabelName.PORT_NAME == "port_name"

    def test_status_labels(self) -> None:
        """Test status/state label names."""
        assert LabelName.STATUS == "status"
        assert LabelName.STATE == "state"
        assert LabelName.STATUS_CODE == "status_code"

    def test_wireless_labels(self) -> None:
        """Test wireless specific labels."""
        assert LabelName.SSID == "ssid"
        assert LabelName.BAND == "band"
        assert LabelName.RADIO == "radio"

    def test_sensor_labels(self) -> None:
        """Test sensor specific labels."""
        assert LabelName.METRIC == "metric"
        assert LabelName.SENSOR_SERIAL == "sensor_serial"
        assert LabelName.SENSOR_NAME == "sensor_name"
        assert LabelName.SENSOR_TYPE == "sensor_type"

    def test_client_labels(self) -> None:
        """Test client specific labels."""
        assert LabelName.CLIENT_ID == "client_id"
        assert LabelName.MAC == "mac"
        assert LabelName.HOSTNAME == "hostname"
        assert LabelName.IP == "ip"
        assert LabelName.VLAN == "vlan"

    def test_enum_string_conversion(self) -> None:
        """Test that enum values convert to strings properly."""
        # Test string conversion
        assert str(LabelName.ORG_ID) == "org_id"

        # Test that it works in f-strings
        assert f"{LabelName.NETWORK_ID}" == "network_id"

        # Test that .value works
        assert LabelName.SERIAL.value == "serial"


class TestMetricDefinition:
    """Test MetricDefinition dataclass."""

    def test_basic_metric_definition(self) -> None:
        """Test creating a basic metric definition."""
        metric = MetricDefinition(
            name="meraki_device_up",
            description="Device online status",
            metric_type="gauge",
            labels=["serial", "name"],
        )

        assert metric.name == "meraki_device_up"
        assert metric.description == "Device online status"
        assert metric.metric_type == "gauge"
        assert metric.labels == ["serial", "name"]
        assert metric.unit is None

    def test_metric_with_unit(self) -> None:
        """Test metric definition with unit."""
        metric = MetricDefinition(
            name="meraki_port_traffic",
            description="Port traffic",
            metric_type="counter",
            labels=["port_id"],
            unit="bytes",
        )

        assert metric.unit == "bytes"
        assert metric.full_name == "meraki_port_traffic_bytes"

    def test_metric_already_has_unit_suffix(self) -> None:
        """Test metric that already has unit in name."""
        metric = MetricDefinition(
            name="meraki_api_calls_total",
            description="Total API calls",
            metric_type="counter",
            labels=["org_id"],
            unit="total",
        )

        # Should not double-add the unit
        assert metric.full_name == "meraki_api_calls_total"

    def test_validate_labels_success(self) -> None:
        """Test successful label validation."""
        metric = MetricDefinition(
            name="test_metric",
            description="Test",
            metric_type="gauge",
            labels=["label1", "label2", "label3"],
        )

        # Should not raise
        metric.validate_labels(["label1", "label2", "label3"])

        # Order shouldn't matter
        metric.validate_labels(["label3", "label1", "label2"])

    def test_validate_labels_missing(self) -> None:
        """Test label validation with missing labels."""
        metric = MetricDefinition(
            name="test_metric",
            description="Test",
            metric_type="gauge",
            labels=["label1", "label2", "label3"],
        )

        with pytest.raises(ValueError) as exc_info:
            metric.validate_labels(["label1", "label2"])

        assert "Missing: {'label3'}" in str(exc_info.value)

    def test_validate_labels_extra(self) -> None:
        """Test label validation with extra labels."""
        metric = MetricDefinition(
            name="test_metric",
            description="Test",
            metric_type="gauge",
            labels=["label1", "label2"],
        )

        with pytest.raises(ValueError) as exc_info:
            metric.validate_labels(["label1", "label2", "label3"])

        assert "Extra: {'label3'}" in str(exc_info.value)

    def test_validate_labels_both_missing_and_extra(self) -> None:
        """Test label validation with both missing and extra labels."""
        metric = MetricDefinition(
            name="test_metric",
            description="Test",
            metric_type="gauge",
            labels=["label1", "label2"],
        )

        with pytest.raises(ValueError) as exc_info:
            metric.validate_labels(["label1", "label3"])

        assert "Missing: {'label2'}" in str(exc_info.value)
        assert "Extra: {'label3'}" in str(exc_info.value)


class TestMetricFactory:
    """Test MetricFactory methods."""

    def test_common_label_sets(self) -> None:
        """Test pre-defined common label sets."""
        assert MetricFactory.ORG_LABELS == [LabelName.ORG_ID, LabelName.ORG_NAME]
        assert MetricFactory.NETWORK_LABELS == [LabelName.NETWORK_ID, LabelName.NETWORK_NAME]
        assert MetricFactory.DEVICE_LABELS == [
            LabelName.SERIAL,
            LabelName.NAME,
            LabelName.MODEL,
            LabelName.NETWORK_ID,
        ]
        assert MetricFactory.DEVICE_TYPE_LABELS == MetricFactory.DEVICE_LABELS + [
            LabelName.DEVICE_TYPE
        ]
        assert MetricFactory.PORT_LABELS == [
            LabelName.SERIAL,
            LabelName.NAME,
            LabelName.PORT_ID,
            LabelName.PORT_NAME,
        ]

    def test_organization_metric(self) -> None:
        """Test creating organization-level metrics."""
        metric = MetricFactory.organization_metric(
            name="meraki_org_api_calls",
            description="API calls per organization",
            metric_type="counter",
        )

        assert metric.name == "meraki_org_api_calls"
        assert metric.labels == ["org_id", "org_name"]
        assert metric.metric_type == "counter"

    def test_organization_metric_with_extra_labels(self) -> None:
        """Test organization metric with extra labels."""
        metric = MetricFactory.organization_metric(
            name="meraki_org_licenses",
            description="Licenses per organization",
            extra_labels=["license_type", "status"],
        )

        assert metric.labels == ["org_id", "org_name", "license_type", "status"]

    def test_organization_metric_with_unit(self) -> None:
        """Test organization metric with unit."""
        metric = MetricFactory.organization_metric(
            name="meraki_org_api_response_time",
            description="API response time",
            unit="seconds",
        )

        assert metric.unit == "seconds"
        assert metric.full_name == "meraki_org_api_response_time_seconds"

    def test_network_metric(self) -> None:
        """Test creating network-level metrics."""
        metric = MetricFactory.network_metric(
            name="meraki_network_clients",
            description="Connected clients per network",
        )

        assert metric.name == "meraki_network_clients"
        assert metric.labels == ["network_id", "network_name"]

    def test_network_metric_with_extra_labels(self) -> None:
        """Test network metric with extra labels."""
        metric = MetricFactory.network_metric(
            name="meraki_network_alerts",
            description="Network alerts",
            extra_labels=["severity", "alert_type"],
        )

        assert metric.labels == ["network_id", "network_name", "severity", "alert_type"]

    def test_device_metric_with_type(self) -> None:
        """Test creating device metric with device type."""
        metric = MetricFactory.device_metric(
            name="meraki_device_uptime",
            description="Device uptime",
            include_device_type=True,
        )

        assert metric.labels == ["serial", "name", "model", "network_id", "device_type"]

    def test_device_metric_without_type(self) -> None:
        """Test creating device metric without device type."""
        metric = MetricFactory.device_metric(
            name="meraki_device_cpu",
            description="Device CPU usage",
            include_device_type=False,
        )

        assert metric.labels == ["serial", "name", "model", "network_id"]

    def test_device_metric_with_extra_labels(self) -> None:
        """Test device metric with extra labels."""
        metric = MetricFactory.device_metric(
            name="meraki_device_status",
            description="Device status",
            extra_labels=["status"],
        )

        assert "status" in metric.labels

    def test_port_metric(self) -> None:
        """Test creating port-level metrics."""
        metric = MetricFactory.port_metric(
            name="meraki_port_traffic",
            description="Port traffic",
            metric_type="counter",
            unit="bytes",
        )

        assert metric.name == "meraki_port_traffic"
        assert metric.labels == ["serial", "name", "port_id", "port_name"]
        assert metric.metric_type == "counter"
        assert metric.unit == "bytes"

    def test_port_metric_with_extra_labels(self) -> None:
        """Test port metric with extra labels."""
        metric = MetricFactory.port_metric(
            name="meraki_port_status",
            description="Port status",
            extra_labels=["status", "duplex", "speed"],
        )

        expected_labels = ["serial", "name", "port_id", "port_name", "status", "duplex", "speed"]
        assert metric.labels == expected_labels


class TestValidateMetricName:
    """Test metric name validation."""

    def test_valid_metric_names(self) -> None:
        """Test validation of valid metric names."""
        # These should not raise
        validate_metric_name("meraki_device_up")
        validate_metric_name("meraki_port_traffic_bytes")
        validate_metric_name("meraki_api_calls_total")
        validate_metric_name("meraki_temperature_celsius")
        validate_metric_name("meraki_response_time_seconds")
        validate_metric_name("meraki_usage_percent")

    def test_invalid_prefix(self) -> None:
        """Test validation fails without meraki_ prefix."""
        with pytest.raises(ValueError) as exc_info:
            validate_metric_name("device_up")

        assert "should start with 'meraki_'" in str(exc_info.value)

    @patch("logging.getLogger")
    def test_missing_unit_warning(self, mock_get_logger: Mock) -> None:
        """Test warning for metrics missing unit suffix."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        # Should warn but not raise
        validate_metric_name("meraki_device_temperature")

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0]
        assert "may be missing a unit suffix" in call_args[0]

    def test_unit_exempt_metrics(self) -> None:
        """Test metrics that are exempt from unit requirements."""
        # These should not warn
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            validate_metric_name("meraki_device_up")
            validate_metric_name("meraki_port_status")
            validate_metric_name("meraki_feature_enabled")
            validate_metric_name("meraki_device_info")

            # Should not have warned
            mock_logger.warning.assert_not_called()


class TestCreateInfoLabels:
    """Test info label creation."""

    def test_string_values(self) -> None:
        """Test creating info labels with string values."""
        data = {
            "version": "1.2.3",
            "model": "MR46",
            "firmware": "28.6",
        }

        labels = create_info_labels(data)
        assert labels == {
            "version": "1.2.3",
            "model": "MR46",
            "firmware": "28.6",
        }

    def test_numeric_values(self) -> None:
        """Test creating info labels with numeric values."""
        data = {
            "port_count": 48,
            "uptime_seconds": 86400,
            "cpu_percent": 45.5,
        }

        labels = create_info_labels(data)
        assert labels == {
            "port_count": "48",
            "uptime_seconds": "86400",
            "cpu_percent": "45.5",
        }

    def test_boolean_values(self) -> None:
        """Test creating info labels with boolean values."""
        data = {
            "enabled": True,
            "connected": False,
            "has_license": True,
        }

        labels = create_info_labels(data)
        assert labels == {
            "enabled": "True",
            "connected": "False",
            "has_license": "True",
        }

    def test_mixed_types(self) -> None:
        """Test creating info labels with mixed types."""
        data = {
            "name": "Test Device",
            "id": 12345,
            "temperature": 23.5,
            "online": True,
        }

        labels = create_info_labels(data)
        assert labels == {
            "name": "Test Device",
            "id": "12345",
            "temperature": "23.5",
            "online": "True",
        }

    def test_empty_data(self) -> None:
        """Test creating info labels with empty data."""
        labels = create_info_labels({})
        assert labels == {}


class TestMetricTypeAnnotations:
    """Test MetricType type annotations."""

    def test_valid_metric_types(self) -> None:
        """Test valid metric type values."""
        valid_types: list[MetricType] = ["gauge", "counter", "histogram", "info"]

        for metric_type in valid_types:
            metric = MetricDefinition(
                name="test",
                description="test",
                metric_type=metric_type,
                labels=[],
            )
            assert metric.metric_type == metric_type


class TestIntegrationScenarios:
    """Test integrated usage scenarios."""

    def test_create_device_availability_metric(self) -> None:
        """Test creating a device availability metric."""
        # Use factory to create metric definition
        metric_def = MetricFactory.device_metric(
            name="meraki_device_availability",
            description="Device availability percentage",
            metric_type="gauge",
            include_device_type=True,
            unit="percent",
        )

        # Validate the metric name
        validate_metric_name(metric_def.full_name)

        # Check all expected labels are present
        expected_labels = [
            str(LabelName.SERIAL),
            str(LabelName.NAME),
            str(LabelName.MODEL),
            str(LabelName.NETWORK_ID),
            str(LabelName.DEVICE_TYPE),
        ]
        assert metric_def.labels == expected_labels

    def test_create_api_usage_metric(self) -> None:
        """Test creating an API usage metric."""
        metric_def = MetricFactory.organization_metric(
            name="meraki_api_calls",
            description="Number of API calls",
            metric_type="counter",
            extra_labels=[str(LabelName.STATUS_CODE)],
            unit="total",
        )

        assert metric_def.full_name == "meraki_api_calls_total"
        assert str(LabelName.STATUS_CODE) in metric_def.labels

    def test_create_sensor_metric(self) -> None:
        """Test creating a sensor metric."""
        # Build labels list manually for a sensor metric
        labels = [
            str(LabelName.SENSOR_SERIAL),
            str(LabelName.SENSOR_NAME),
            str(LabelName.SENSOR_TYPE),
            str(LabelName.METRIC),
        ]

        metric_def = MetricDefinition(
            name="meraki_sensor_reading",
            description="Sensor reading value",
            metric_type="gauge",
            labels=labels,
        )

        # Should pass validation
        metric_def.validate_labels(labels)
