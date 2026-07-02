"""Tests for metrics creation and management."""

from __future__ import annotations

import pytest

from meraki_dashboard_exporter.core.metrics import (
    LabelName,
    create_labels,
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


class TestCreateLabels:
    """Test create_labels validation and None handling (F-019)."""

    def test_none_value_coalesced_to_empty_string_not_dropped(self) -> None:
        """A None-valued label must be kept as "" so the labelname is never missing.

        Regression for F-019: dropping the key produced an incomplete label set,
        which later made Gauge.labels() raise ValueError (missing labelname) and a
        bare except silently lost the metric series.
        """
        labels = create_labels(
            org_id="123",
            org_name="Test Org",
            network_id=None,
        )
        # Key present (not dropped) and stringified to empty.
        assert "network_id" in labels
        assert labels["network_id"] == ""  # noqa: PLC1901  (must be "", not merely falsey/None)
        assert labels == {"org_id": "123", "org_name": "Test Org", "network_id": ""}

    def test_non_none_values_stringified(self) -> None:
        """Non-None values are stringified as before."""
        labels = create_labels(org_id="123", org_name="Org")
        assert labels == {"org_id": "123", "org_name": "Org"}

    def test_invalid_key_raises(self) -> None:
        """Unknown label keys still raise ValueError."""
        with pytest.raises(ValueError, match="Invalid label key"):
            create_labels(not_a_real_label="x")
