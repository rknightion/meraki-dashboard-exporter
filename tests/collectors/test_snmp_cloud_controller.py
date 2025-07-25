"""Tests for cloud controller SNMP collector."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meraki_dashboard_exporter.collectors.snmp.cloud_controller import CloudControllerSNMPCollector
from meraki_dashboard_exporter.collectors.snmp.snmp_coordinator import SNMPFastCoordinator


@pytest.fixture
def settings():
    """Create test settings."""
    settings = MagicMock()
    settings.snmp = MagicMock()
    settings.snmp.enabled = True
    settings.snmp.timeout = 5.0
    settings.snmp.retries = 3
    settings.snmp.bulk_max_repetitions = 25
    settings.snmp.org_v3_auth_password = None
    settings.snmp.org_v3_priv_password = None
    settings.snmp.concurrent_device_limit = 10
    settings.meraki = MagicMock()
    settings.meraki.org_id = None
    settings.update_intervals = MagicMock()
    settings.update_intervals.fast = 60
    settings.update_intervals.medium = 300
    settings.update_intervals.slow = 900
    return settings


@pytest.fixture
def api_client():
    """Create mock API client."""
    return MagicMock()


@pytest.fixture
def coordinator(api_client, settings):
    """Create SNMP coordinator."""
    with (
        patch("meraki_dashboard_exporter.collectors.snmp.snmp_coordinator.AsyncMerakiClient"),
        patch("asyncio.create_task"),
    ):
        coordinator = SNMPFastCoordinator(api_client, settings)
        coordinator.enabled = True
        coordinator._create_gauge = MagicMock()
        coordinator._create_counter = MagicMock()
        return coordinator


@pytest.fixture
def collector(coordinator, settings):
    """Create cloud controller SNMP collector."""
    return CloudControllerSNMPCollector(coordinator, settings)


@pytest.mark.asyncio
async def test_device_mapping_filters_unknown_devices(collector):
    """Test that unknown devices are filtered out from SNMP results."""
    # Create a target with device_map
    target = {
        "host": "snmp.meraki.com",
        "port": 16100,
        "org_id": "123456",
        "org_name": "Test Org",
        "version": "v2c",
        "community": "public",
        "device_map": {
            "001122334455": {  # Known device (normalized MAC)
                "device": {
                    "serial": "Q2AB-CDEF-GHIJ",
                    "name": "Test Device",
                    "mac": "00:11:22:33:44:55",
                },
                "network": {
                    "id": "L_12345",
                    "name": "Test Network",
                },
            }
        },
    }

    # Mock SNMP responses with both known and unknown devices
    device_status_results = [
        ("1.3.6.1.4.1.29671.1.1.4.1.3.0.17.34.51.68.85", 1),  # Known device
        ("1.3.6.1.4.1.29671.1.1.4.1.3.170.187.204.221.238.255", 1),  # Unknown device
    ]

    # Mock the collector's methods
    collector.snmp_bulk = AsyncMock(
        side_effect=[
            device_status_results,  # device_status
            [],  # device_name
            [],  # device_serial
        ]
    )

    # Mock metrics
    collector.device_status_metric = MagicMock()

    # Process the device table
    await collector._process_device_table(
        target, device_status_results, target["org_id"], target["org_name"]
    )

    # Verify only the known device was processed
    assert collector.device_status_metric.labels.call_count == 1

    # Verify the labels include network information
    labels_call = collector.device_status_metric.labels.call_args[1]
    assert labels_call["network_id"] == "L_12345"
    assert labels_call["network_name"] == "Test Network"
    assert labels_call["serial"] == "Q2AB-CDEF-GHIJ"
    assert labels_call["name"] == "Test Device"


@pytest.mark.asyncio
async def test_client_count_validates_numeric_values(collector):
    """Test that client count metric validates numeric values."""
    # Create a target with device_map
    target = {
        "host": "snmp.meraki.com",
        "port": 16100,
        "org_id": "123456",
        "org_name": "Test Org",
        "device_map": {
            "001122334455": {
                "device": {
                    "serial": "Q2AB-CDEF-GHIJ",
                    "name": "Test Device",
                },
                "network": {
                    "id": "L_12345",
                    "name": "Test Network",
                },
            }
        },
    }

    # Mock SNMP responses with various value types
    client_count_results = [
        ("1.3.6.1.4.1.29671.1.1.4.1.5.0.17.34.51.68.85", 42),  # Valid numeric
        ("1.3.6.1.4.1.29671.1.1.4.1.5.0.17.34.51.68.86", "10.1.1.1"),  # Invalid IP string
        ("1.3.6.1.4.1.29671.1.1.4.1.5.0.17.34.51.68.87", "Q2AB-CDEF"),  # Invalid serial string
    ]

    # Mock metric
    collector.client_count_metric = MagicMock()

    # Process client counts
    await collector._process_client_counts(
        client_count_results, target["org_id"], target["org_name"], target
    )

    # Verify only valid numeric value was set
    assert collector.client_count_metric.labels.call_count == 1
    collector.client_count_metric.labels().set.assert_called_once_with(42)


@pytest.mark.asyncio
async def test_interface_metrics_include_standard_labels(collector):
    """Test that interface metrics include all standard labels."""
    # Create a target with device_map
    target = {
        "host": "snmp.meraki.com",
        "port": 16100,
        "org_id": "123456",
        "org_name": "Test Org",
        "device_map": {
            "001122334455": {
                "device": {
                    "serial": "Q2AB-CDEF-GHIJ",
                    "name": "Test Device",
                },
                "network": {
                    "id": "L_12345",
                    "name": "Test Network",
                },
            }
        },
    }

    # Mock SNMP responses
    interface_name_results = [
        ("1.3.6.1.4.1.29671.1.1.5.1.3.0.17.34.51.68.85.1", "Port 1"),
    ]

    interface_metric_results = [
        ("1.3.6.1.4.1.29671.1.1.5.1.4.0.17.34.51.68.85.1", 1000),  # sent_pkts
    ]

    # Mock the collector's SNMP method
    collector.snmp_bulk = AsyncMock(
        side_effect=[
            interface_name_results,  # interface names
            interface_metric_results,  # sent_pkts
            [],  # recv_pkts
            [],  # sent_bytes
            [],  # recv_bytes
        ]
    )

    # Mock metrics
    collector.interface_packets_sent = MagicMock()
    collector.interface_packets_sent.labels()._value = MagicMock()

    # Collect interface metrics
    await collector._collect_interface_metrics(target, target["org_id"], target["org_name"])

    # Verify labels include all standard fields
    labels_call = collector.interface_packets_sent.labels.call_args[1]
    assert labels_call["org_id"] == "123456"
    assert labels_call["org_name"] == "Test Org"
    assert labels_call["network_id"] == "L_12345"
    assert labels_call["network_name"] == "Test Network"
    assert labels_call["serial"] == "Q2AB-CDEF-GHIJ"
    assert labels_call["name"] == "Test Device"
    assert labels_call["mac"] == "00:11:22:33:44:55"
    assert labels_call["port_name"] == "Port 1"
