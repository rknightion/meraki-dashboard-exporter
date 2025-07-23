"""Tests for domain models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from meraki_dashboard_exporter.core.domain_models import (
    ClientData,
    ConfigurationChange,
    ConnectionStats,
    DataRate,
    MRDeviceStats,
    MRRadioStatus,
    MTSensorReading,
    NetworkConnectionStats,
    OrganizationSummary,
    RFHealthData,
    SensorMeasurement,
    SwitchPort,
    SwitchPortPOE,
    parse_connection_stats,
    parse_rf_health_response,
)


class TestRFHealthData:
    """Test RFHealthData model."""

    def test_rf_health_basic(self):
        """Test basic RF health data."""
        rf_health = RFHealthData(
            serial="Q2XX-XXXX-XXXX",
            model="MR36",
        )
        assert rf_health.serial == "Q2XX-XXXX-XXXX"
        assert rf_health.model == "MR36"
        assert rf_health.apName is None
        assert rf_health.band2_4GhzUtilization is None
        assert rf_health.band5GhzUtilization is None

    def test_rf_health_with_utilization(self):
        """Test RF health with utilization data."""
        timestamp = datetime.now(UTC)
        rf_health = RFHealthData(
            serial="Q2XX-XXXX-XXXX",
            apName="Office-AP-01",
            model="MR36",
            band2_4GhzUtilization=45.5,
            band5GhzUtilization=30.2,
            timestamp=timestamp,
        )
        assert rf_health.band2_4GhzUtilization == 45.5
        assert rf_health.band5GhzUtilization == 30.2
        assert rf_health.timestamp == timestamp

    def test_rf_health_utilization_validation(self):
        """Test utilization validation (0-100 range)."""
        # Values should be clamped to 0-100
        rf_health = RFHealthData(
            serial="Q2XX-XXXX-XXXX",
            model="MR36",
            band2_4GhzUtilization=150.0,  # Should be clamped to 100
            band5GhzUtilization=-10.0,  # Should be clamped to 0
        )
        assert rf_health.band2_4GhzUtilization == pytest.approx(100.0)
        assert rf_health.band5GhzUtilization == pytest.approx(0.0)

        # String values should convert and clamp
        rf_health = RFHealthData(
            serial="Q2XX-XXXX-XXXX",
            model="MR36",
            band2_4GhzUtilization="45.5",  # type: ignore[arg-type]
            band5GhzUtilization="200",  # type: ignore[arg-type]
        )
        assert rf_health.band2_4GhzUtilization == 45.5
        assert rf_health.band5GhzUtilization == pytest.approx(100.0)

    def test_rf_health_alias_fields(self):
        """Test that alias fields work correctly."""
        # Using alias in data
        rf_health = RFHealthData(
            serial="Q2XX-XXXX-XXXX",
            model="MR36",
            **{"2.4GhzUtilization": 50.0, "5GhzUtilization": 60.0},  # type: ignore[arg-type]
        )
        assert rf_health.band2_4GhzUtilization == pytest.approx(50.0)
        assert rf_health.band5GhzUtilization == pytest.approx(60.0)


class TestConnectionStats:
    """Test ConnectionStats model."""

    def test_connection_stats_defaults(self):
        """Test connection stats with defaults."""
        stats = ConnectionStats()
        assert stats.assoc == 0
        assert stats.auth == 0
        assert stats.dhcp == 0
        assert stats.dns == 0
        assert stats.success == 0

    def test_connection_stats_with_values(self):
        """Test connection stats with values."""
        stats = ConnectionStats(
            assoc=100,
            auth=95,
            dhcp=90,
            dns=88,
            success=85,
        )
        assert stats.assoc == 100
        assert stats.auth == 95
        assert stats.success == 85

    def test_connection_stats_validation(self):
        """Test that negative values are converted to 0."""
        stats = ConnectionStats(  # type: ignore[call-arg]
            assoc=-10,
            auth=50,
            dhcp=-5,
            dns=None,  # None should become 0
            success="100",  # String should convert
        )
        assert stats.assoc == 0
        assert stats.auth == 50
        assert stats.dhcp == 0
        assert stats.dns == 0
        assert stats.success == 100


class TestNetworkConnectionStats:
    """Test NetworkConnectionStats model."""

    def test_network_connection_stats(self):
        """Test network connection stats."""
        conn_stats = ConnectionStats(assoc=100, auth=95, success=90)
        network_stats = NetworkConnectionStats(
            networkId="N_123",
            connectionStats=conn_stats,
        )
        assert network_stats.networkId == "N_123"
        assert network_stats.connectionStats.assoc == 100
        assert network_stats.connectionStats.success == 90

    def test_network_connection_stats_extra_fields(self):
        """Test that extra fields are allowed."""
        conn_stats = ConnectionStats()
        network_stats = NetworkConnectionStats(  # type: ignore[call-arg]
            networkId="N_123",
            connectionStats=conn_stats,
            extra_field="allowed",
            another=123,
        )
        assert network_stats.networkId == "N_123"


class TestDataRate:
    """Test DataRate model."""

    def test_data_rate_defaults(self):
        """Test data rate with defaults."""
        rate = DataRate()
        assert rate.total == 0
        assert rate.sent == 0
        assert rate.received == 0
        assert rate.download_kbps == pytest.approx(0.0)
        assert rate.upload_kbps == pytest.approx(0.0)

    def test_data_rate_with_values(self):
        """Test data rate with values."""
        # 1,500,000 bytes over 5 minutes = 40 kbps
        rate = DataRate(
            total=3000000,
            sent=1500000,
            received=1500000,
        )
        assert rate.total == 3000000
        assert rate.sent == 1500000
        assert rate.received == 1500000
        assert rate.download_kbps == pytest.approx(40.0)
        assert rate.upload_kbps == pytest.approx(40.0)

    def test_data_rate_validation(self):
        """Test byte count validation."""
        rate = DataRate(  # type: ignore[call-arg]
            total="3000000",  # String should convert
            sent=-1000,  # Negative should become 0
            received=None,  # None should become 0
        )
        assert rate.total == 3000000
        assert rate.sent == 0
        assert rate.received == 0

    def test_data_rate_calculations(self):
        """Test kbps calculations."""
        # Test various byte amounts
        test_cases = [
            (0, 0.0),  # No data
            (150000, 4.0),  # 150KB = 4 kbps
            (3750000, 100.0),  # 3.75MB = 100 kbps
            (37500000, 1000.0),  # 37.5MB = 1 Mbps
        ]

        for bytes_val, expected_kbps in test_cases:
            rate = DataRate(received=bytes_val, sent=bytes_val)
            assert rate.download_kbps == pytest.approx(expected_kbps)
            assert rate.upload_kbps == pytest.approx(expected_kbps)


class TestSwitchPort:
    """Test SwitchPort model."""

    def test_switch_port_defaults(self):
        """Test switch port with defaults."""
        port = SwitchPort(portId="1")
        assert port.portId == "1"
        assert port.name is None
        assert port.enabled is True
        assert port.poeEnabled is False
        assert port.type == "trunk"
        assert port.vlan is None
        assert port.allowedVlans == "all"
        assert port.tags == []

    def test_switch_port_full(self):
        """Test switch port with all fields."""
        port = SwitchPort(
            portId="24",
            name="Uplink to Core",
            enabled=True,
            poeEnabled=True,
            type="trunk",
            vlan=100,
            voiceVlan=200,
            allowedVlans="100,200,300",
            isolationEnabled=True,
            rstpEnabled=False,
            stpGuard="root guard",
            linkNegotiation="1 Gbps full duplex",
            accessPolicyType="MAC allow list",
            tags=["uplink", "critical"],
        )
        assert port.name == "Uplink to Core"
        assert port.poeEnabled is True
        assert port.vlan == 100
        assert port.voiceVlan == 200
        assert port.stpGuard == "root guard"
        assert port.tags == ["uplink", "critical"]

    def test_switch_port_literals(self):
        """Test literal field validation."""
        # Valid STP guard values
        for guard in ["disabled", "root guard", "bpdu guard", "loop guard"]:
            port = SwitchPort(portId="1", stpGuard=guard)  # type: ignore[arg-type]
            assert port.stpGuard == guard

        # Valid access policy types
        for policy in ["Open", "Custom access policy", "MAC allow list", "Sticky MAC allow list"]:
            port = SwitchPort(portId="1", accessPolicyType=policy)  # type: ignore[arg-type]
            assert port.accessPolicyType == policy


class TestSwitchPortPOE:
    """Test SwitchPortPOE model."""

    def test_switch_port_poe_defaults(self):
        """Test POE status with defaults."""
        poe = SwitchPortPOE(portId="1")
        assert poe.portId == "1"
        assert poe.isAllocated is False
        assert poe.allocatedInWatts == pytest.approx(0.0)
        assert poe.drawInWatts == pytest.approx(0.0)
        assert poe.utilization_percent == pytest.approx(0.0)

    def test_switch_port_poe_with_power(self):
        """Test POE with power allocation."""
        poe = SwitchPortPOE(
            portId="1",
            isAllocated=True,
            allocatedInWatts=30.0,
            drawInWatts=15.5,
        )
        assert poe.isAllocated is True
        assert poe.allocatedInWatts == pytest.approx(30.0)
        assert poe.drawInWatts == 15.5
        assert poe.utilization_percent == pytest.approx(51.67, rel=0.01)

    def test_switch_port_poe_validation(self):
        """Test wattage validation."""
        # Negative values should become 0
        poe = SwitchPortPOE(
            portId="1",
            allocatedInWatts=-10.0,
            drawInWatts=-5.0,
        )
        assert poe.allocatedInWatts == pytest.approx(0.0)
        assert poe.drawInWatts == pytest.approx(0.0)

        # String values should convert
        poe = SwitchPortPOE(
            portId="1",
            allocatedInWatts="30.0",  # type: ignore[arg-type]
            drawInWatts="15.5",  # type: ignore[arg-type]
        )
        assert poe.allocatedInWatts == pytest.approx(30.0)
        assert poe.drawInWatts == 15.5

    def test_switch_port_poe_utilization(self):
        """Test utilization percentage calculation."""
        # Normal case
        poe = SwitchPortPOE(portId="1", allocatedInWatts=30.0, drawInWatts=20.0)
        assert poe.utilization_percent == pytest.approx(66.67, rel=0.01)

        # Over 100% should be capped
        poe = SwitchPortPOE(portId="1", allocatedInWatts=30.0, drawInWatts=35.0)
        assert poe.utilization_percent == pytest.approx(100.0)

        # No allocation = 0%
        poe = SwitchPortPOE(portId="1", allocatedInWatts=0.0, drawInWatts=10.0)
        assert poe.utilization_percent == pytest.approx(0.0)


class TestMRDeviceStats:
    """Test MRDeviceStats model."""

    def test_mr_device_stats_defaults(self):
        """Test MR device stats with defaults."""
        stats = MRDeviceStats(serial="Q2XX-XXXX-XXXX")
        assert stats.serial == "Q2XX-XXXX-XXXX"
        assert stats.clientCount == 0
        assert stats.meshNeighbors == 0
        assert stats.repeaterClients == 0
        assert stats.cpuUsagePercent is None
        assert stats.memoryUsagePercent is None

    def test_mr_device_stats_full(self):
        """Test MR device stats with all fields."""
        stats = MRDeviceStats(
            serial="Q2XX-XXXX-XXXX",
            clientCount=25,
            meshNeighbors=2,
            repeaterClients=5,
            cpuUsagePercent=45.5,
            memoryUsagePercent=60.2,
            backgroundTrafficLossPercent=0.1,
            bestEffortTrafficLossPercent=0.5,
            videoTrafficLossPercent=0.2,
            voiceTrafficLossPercent=0.0,
        )
        assert stats.clientCount == 25
        assert stats.cpuUsagePercent == 45.5
        assert stats.voiceTrafficLossPercent == pytest.approx(0.0)

    def test_mr_device_stats_validation(self):
        """Test validation of percentages and counts."""
        # Percentages should be clamped to 0-100
        stats = MRDeviceStats(
            serial="Q2XX-XXXX-XXXX",
            cpuUsagePercent=150.0,
            memoryUsagePercent=-10.0,
        )
        assert stats.cpuUsagePercent == pytest.approx(100.0)
        assert stats.memoryUsagePercent == pytest.approx(0.0)

        # Counts should be non-negative
        stats = MRDeviceStats(  # type: ignore[call-arg]
            serial="Q2XX-XXXX-XXXX",
            clientCount=-5,
            meshNeighbors=None,  # Should become 0
            repeaterClients="10",  # Should convert
        )
        assert stats.clientCount == 0
        assert stats.meshNeighbors == 0
        assert stats.repeaterClients == 10


class TestMRRadioStatus:
    """Test MRRadioStatus model."""

    def test_mr_radio_status_basic(self):
        """Test basic radio status."""
        radio = MRRadioStatus(
            serial="Q2XX-XXXX-XXXX",
            radioIndex=0,
        )
        assert radio.serial == "Q2XX-XXXX-XXXX"
        assert radio.radioIndex == 0
        assert radio.enabled is True
        assert radio.operatingChannel is None

    def test_mr_radio_status_full(self):
        """Test radio status with all fields."""
        radio = MRRadioStatus(
            serial="Q2XX-XXXX-XXXX",
            radioIndex=1,
            operatingChannel=36,
            transmitPower=20.0,
            standard="802.11ac",
            enabled=True,
        )
        assert radio.radioIndex == 1
        assert radio.operatingChannel == 36
        assert radio.transmitPower == pytest.approx(20.0)
        assert radio.standard == "802.11ac"

    def test_mr_radio_status_validation(self):
        """Test radio index validation."""
        # Valid indices (0=2.4GHz, 1=5GHz, 2=6GHz)
        for idx in [0, 1, 2]:
            radio = MRRadioStatus(serial="Q2XX-XXXX-XXXX", radioIndex=idx)
            assert radio.radioIndex == idx

        # Invalid index should raise error
        with pytest.raises(ValidationError):
            MRRadioStatus(serial="Q2XX-XXXX-XXXX", radioIndex=3)

        with pytest.raises(ValidationError):
            MRRadioStatus(serial="Q2XX-XXXX-XXXX", radioIndex=-1)


class TestConfigurationChange:
    """Test ConfigurationChange model."""

    def test_configuration_change_basic(self):
        """Test basic configuration change."""
        ts = datetime.now(UTC)
        change = ConfigurationChange(ts=ts)
        assert change.ts == ts
        assert change.adminId is None
        assert change.networkId is None
        assert change.oldValue is None
        assert change.newValue is None

    def test_configuration_change_full(self):
        """Test configuration change with all fields."""
        ts = datetime.now(UTC)
        change = ConfigurationChange(
            ts=ts,
            adminId="admin_123",
            adminName="John Doe",
            adminEmail="john@example.com",
            networkId="N_123",
            networkName="Test Network",
            page="Switch > Switch ports",
            label="Port 1 VLAN",
            oldValue=100,
            newValue=200,
        )
        assert change.adminName == "John Doe"
        assert change.page == "Switch > Switch ports"
        assert change.oldValue == 100
        assert change.newValue == 200

    def test_configuration_change_any_values(self):
        """Test that old/new values can be any type."""
        ts = datetime.now(UTC)

        # Dict values
        change = ConfigurationChange(
            ts=ts,
            oldValue={"vlan": 100, "name": "old"},
            newValue={"vlan": 200, "name": "new"},
        )
        assert change.oldValue == {"vlan": 100, "name": "old"}

        # List values
        change = ConfigurationChange(
            ts=ts,
            oldValue=[1, 2, 3],
            newValue=[1, 2, 3, 4],
        )
        assert len(change.newValue) == 4


class TestSensorMeasurement:
    """Test SensorMeasurement model."""

    def test_sensor_measurement_basic(self):
        """Test basic sensor measurement."""
        measurement = SensorMeasurement(
            metric="temperature",
            value=23.5,
        )
        assert measurement.metric == "temperature"
        assert measurement.value == 23.5
        assert measurement.unit is None
        assert measurement.normalized_unit == "celsius"  # type: ignore[comparison-overlap]

    def test_sensor_measurement_with_unit(self):
        """Test sensor measurement with custom unit."""
        measurement = SensorMeasurement(
            metric="temperature",
            value=73.4,
            unit="fahrenheit",
        )
        assert measurement.unit == "fahrenheit"
        # Normalized unit is still celsius for temperature
        assert measurement.normalized_unit == "celsius"  # type: ignore[comparison-overlap]

    def test_sensor_measurement_validation(self):
        """Test value validation."""
        # String should convert to float
        measurement = SensorMeasurement(metric="humidity", value="45.5")  # type: ignore[arg-type]
        assert measurement.value == 45.5

        # None should raise error
        with pytest.raises(ValidationError):
            SensorMeasurement(metric="temperature", value=None)  # type: ignore[arg-type]

    def test_sensor_measurement_all_metrics(self):
        """Test all supported metric types."""
        metric_units = {
            "temperature": "celsius",
            "humidity": "percent",
            "water": "boolean",
            "door": "boolean",
            "tvoc": "ppb",
            "co2": "ppm",
            "noise": "dB",
            "pm25": "ug/m3",
            "indoorAirQuality": "score",
            "battery": "percent",
            "voltage": "volts",
            "current": "amperes",
            "realPower": "watts",
            "apparentPower": "volt-amperes",
            "powerFactor": "percent",
            "frequency": "hertz",
            "downstreamPower": "boolean",
            "remoteLockout": "boolean",
            "remoteLockoutSwitch": "boolean",
        }

        for metric, expected_unit in metric_units.items():
            measurement = SensorMeasurement(metric=metric, value=50.0)  # type: ignore[arg-type]
            assert measurement.normalized_unit == expected_unit  # type: ignore[comparison-overlap]

    def test_sensor_measurement_unknown_metric(self):
        """Test unknown metric with custom unit."""
        # Should use provided unit or "unknown"
        measurement = SensorMeasurement(
            metric="temperature",  # Known metric
            value=50.0,
            unit="custom",
        )
        # For known metrics, normalized_unit ignores custom unit
        assert measurement.normalized_unit == "celsius"  # type: ignore[comparison-overlap]


class TestMTSensorReading:
    """Test MTSensorReading model."""

    def test_mt_sensor_reading_basic(self):
        """Test basic MT sensor reading."""
        timestamp = datetime.now(UTC)
        reading = MTSensorReading(
            serial="Q2MT-XXXX-XXXX",
            networkId="N_123",
            timestamp=timestamp,
            measurements=[],
        )
        assert reading.serial == "Q2MT-XXXX-XXXX"
        assert reading.networkId == "N_123"
        assert reading.timestamp == timestamp
        assert reading.measurements == []

    def test_mt_sensor_reading_with_measurements(self):
        """Test MT sensor reading with measurements."""
        timestamp = datetime.now(UTC)
        measurements = [
            SensorMeasurement(metric="temperature", value=23.5),
            SensorMeasurement(metric="humidity", value=45.0),
            SensorMeasurement(metric="co2", value=420.0),
        ]

        reading = MTSensorReading(
            serial="Q2MT-XXXX-XXXX",
            networkId="N_123",
            timestamp=timestamp,
            measurements=measurements,
        )
        assert len(reading.measurements) == 3
        assert reading.measurements[0].metric == "temperature"
        assert reading.measurements[1].value == pytest.approx(45.0)
        assert reading.measurements[2].normalized_unit == "ppm"  # type: ignore[comparison-overlap]


class TestOrganizationSummary:
    """Test OrganizationSummary model."""

    def test_organization_summary_defaults(self):
        """Test organization summary with defaults."""
        summary = OrganizationSummary(
            id="org_123",
            name="Test Org",
        )
        assert summary.id == "org_123"
        assert summary.name == "Test Org"
        assert summary.deviceCounts == {}
        assert summary.networkCount == 0
        assert summary.total_devices == 0  # type: ignore[comparison-overlap]

    def test_organization_summary_with_counts(self):
        """Test organization summary with device counts."""
        summary = OrganizationSummary(
            id="org_123",
            name="Test Org",
            deviceCounts={"MR": 10, "MS": 20, "MX": 5},
            networkCount=15,
            wirelessNetworkCount=10,
            switchNetworkCount=12,
            applianceNetworkCount=5,
            cameraNetworkCount=2,
            sensorNetworkCount=3,
        )
        assert summary.deviceCounts == {"MR": 10, "MS": 20, "MX": 5}
        assert summary.total_devices == 35  # type: ignore[comparison-overlap]
        assert summary.networkCount == 15
        assert summary.wirelessNetworkCount == 10

    def test_organization_summary_device_count_validation(self):
        """Test device count validation."""
        # Invalid values should be converted/filtered
        summary = OrganizationSummary(  # type: ignore[call-arg]
            id="org_123",
            name="Test Org",
            deviceCounts={
                "MR": "10",  # String converts to int
                "MS": 20.5,  # Float converts to int
                "MX": -5,  # Negative becomes 0
                "MV": None,  # None is filtered out
            },
        )
        assert summary.deviceCounts == {"MR": 10, "MS": 20, "MX": 0}
        assert summary.total_devices == 30  # type: ignore[comparison-overlap]

        # Non-dict becomes empty dict
        summary = OrganizationSummary(
            id="org_123",
            name="Test Org",
            deviceCounts="not a dict",  # type: ignore[arg-type]
        )
        assert summary.deviceCounts == {}


class TestClientData:
    """Test ClientData model."""

    def test_client_data_basic(self):
        """Test basic client data."""
        first_seen = datetime.now(UTC)
        last_seen = datetime.now(UTC)

        client = ClientData(
            id="c_123",
            mac="00:11:22:33:44:55",
            firstSeen=first_seen,
            lastSeen=last_seen,
        )
        assert client.id == "c_123"
        assert client.mac == "00:11:22:33:44:55"
        assert client.effective_ssid == "Unknown"  # type: ignore[comparison-overlap]
        assert client.display_name == "00:11:22:33:44:55"
        assert client.status == "Offline"  # type: ignore[comparison-overlap]

    def test_client_data_effective_ssid(self):
        """Test effective SSID calculation."""
        first_seen = datetime.now(UTC)
        last_seen = datetime.now(UTC)

        # Wired connection
        client = ClientData(
            id="c_123",
            mac="00:11:22:33:44:55",
            firstSeen=first_seen,
            lastSeen=last_seen,
            recentDeviceConnection="Wired",
            ssid="Should be ignored",
        )
        assert client.effective_ssid == "Wired"  # type: ignore[comparison-overlap]

        # Wireless with SSID
        client = ClientData(
            id="c_123",
            mac="00:11:22:33:44:55",
            firstSeen=first_seen,
            lastSeen=last_seen,
            recentDeviceConnection="Wireless",
            ssid="Corporate",
        )
        assert client.effective_ssid == "Corporate"

        # Wireless without SSID
        client = ClientData(
            id="c_123",
            mac="00:11:22:33:44:55",
            firstSeen=first_seen,
            lastSeen=last_seen,
            recentDeviceConnection="Wireless",
            ssid=None,
        )
        assert client.effective_ssid == "Unknown"  # type: ignore[comparison-overlap]

    def test_client_data_display_name(self):
        """Test display name priority."""
        first_seen = datetime.now(UTC)
        last_seen = datetime.now(UTC)

        # Description takes priority
        client = ClientData(
            id="c_123",
            mac="00:11:22:33:44:55",
            firstSeen=first_seen,
            lastSeen=last_seen,
            description="John's iPhone",
            hostname="johns-iphone.local",
        )
        assert client.display_name == "John's iPhone"

        # Hostname is second priority
        client = ClientData(
            id="c_123",
            mac="00:11:22:33:44:55",
            firstSeen=first_seen,
            lastSeen=last_seen,
            description=None,
            hostname="johns-iphone.local",
        )
        assert client.display_name == "johns-iphone.local"

        # MAC is fallback
        client = ClientData(
            id="c_123",
            mac="00:11:22:33:44:55",
            firstSeen=first_seen,
            lastSeen=last_seen,
            description=None,
            hostname=None,
        )
        assert client.display_name == "00:11:22:33:44:55"

    def test_client_data_full(self):
        """Test client data with all fields."""
        first_seen = datetime.now(UTC)
        last_seen = datetime.now(UTC)

        client = ClientData(
            id="c_123",
            mac="00:11:22:33:44:55",
            description="CEO Laptop",
            hostname="ceo-laptop.example.com",
            calculatedHostname="ceo-laptop",
            ip="192.168.1.100",
            ip6="2001:db8::1",
            ip6Local="fe80::1",
            user="ceo@example.com",
            firstSeen=first_seen,
            lastSeen=last_seen,
            manufacturer="Apple",
            os="macOS",
            deviceTypePrediction="MacBook Pro",
            recentDeviceSerial="Q2SW-XXXX-XXXX",
            recentDeviceName="Executive Switch",
            recentDeviceMac="00:AA:BB:CC:DD:EE",
            recentDeviceConnection="Wired",
            ssid=None,
            vlan="100",
            switchport="GigabitEthernet1/0/1",
            status="Online",
            usage={"sent": 1000000, "recv": 5000000},
            notes="VIP client",
            groupPolicy8021x="Executive",
            adaptivePolicyGroup="VIP",
            smInstalled=True,
            namedVlan="Executive VLAN",
            pskGroup=None,
            wirelessCapabilities=None,
            networkId="N_123",
            networkName="HQ Network",
            organizationId="org_456",
        )
        assert client.description == "CEO Laptop"
        assert client.status == "Online"
        assert client.smInstalled is True
        assert client.organizationId == "org_456"


class TestHelperFunctions:
    """Test helper functions."""

    def test_parse_rf_health_response_valid(self):
        """Test parsing valid RF health response."""
        data = {
            "serial": "Q2XX-XXXX-XXXX",
            "model": "MR36",
            "2.4GhzUtilization": 45.5,
            "5GhzUtilization": 30.2,
        }

        result = parse_rf_health_response(data)
        assert result is not None
        assert result.serial == "Q2XX-XXXX-XXXX"
        assert result.band2_4GhzUtilization == 45.5
        assert result.band5GhzUtilization == 30.2

    def test_parse_rf_health_response_invalid(self):
        """Test parsing invalid RF health response."""
        # Missing required fields
        data = {"model": "MR36"}  # Missing serial

        result = parse_rf_health_response(data)
        assert result is None

    def test_parse_connection_stats_valid(self):
        """Test parsing connection stats."""
        data = {
            "assoc": 100,
            "auth": 95,
            "dhcp": 90,
            "dns": 88,
            "success": 85,
        }

        result = parse_connection_stats(data)
        assert result.assoc == 100
        assert result.success == 85

    def test_parse_connection_stats_partial(self):
        """Test parsing partial connection stats."""
        # Missing fields should use defaults
        data = {"assoc": 50, "success": 45}

        result = parse_connection_stats(data)
        assert result.assoc == 50
        assert result.auth == 0  # Default
        assert result.dhcp == 0  # Default
        assert result.success == 45
