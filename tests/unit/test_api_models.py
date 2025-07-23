"""Tests for API models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from meraki_dashboard_exporter.core.api_models import (
    Alert,
    APIUsage,
    ClientOverview,
    Device,
    DeviceStatus,
    License,
    MemoryUsage,
    Network,
    NetworkClient,
    Organization,
    PaginatedResponse,
    PortStatus,
    SensorData,
    SensorReading,
    WirelessClient,
)


class TestOrganization:
    """Test Organization model."""

    def test_organization_basic(self):
        """Test basic organization creation."""
        org = Organization(id="123", name="Test Org")
        assert org.id == "123"
        assert org.name == "Test Org"
        assert org.url is None
        assert org.api is None
        assert org.licensing is None

    def test_organization_full(self):
        """Test organization with all fields."""
        org = Organization(
            id="123",
            name="Test Org",
            url="https://dashboard.meraki.com",
            api={"enabled": True},
            licensing={"model": "per-device"},
            cloud={"region": {"name": "North America"}},
        )
        assert org.id == "123"
        assert org.url == "https://dashboard.meraki.com"
        assert org.api == {"enabled": True}
        assert org.cloud == {"region": {"name": "North America"}}

    def test_organization_extra_fields_allowed(self):
        """Test that extra fields are allowed."""
        org = Organization(id="123", name="Test Org", extra_field="extra", another_field=123)
        assert org.id == "123"
        assert org.name == "Test Org"


class TestNetwork:
    """Test Network model."""

    def test_network_basic(self):
        """Test basic network creation."""
        network = Network(id="N_123", organizationId="org_456", name="Test Network")
        assert network.id == "N_123"
        assert network.organizationId == "org_456"
        assert network.name == "Test Network"
        assert network.productTypes == []
        assert network.tags == []
        assert network.isBoundToConfigTemplate is False

    def test_network_full(self):
        """Test network with all fields."""
        network = Network(
            id="N_123",
            organizationId="org_456",
            name="Test Network",
            productTypes=["wireless", "switch", "appliance"],
            timeZone="America/New_York",
            tags=["production", "east-coast"],
            enrollmentString="my-enrollment",
            url="https://n123.meraki.com",
            notes="Production network",
            isBoundToConfigTemplate=True,
        )
        assert network.productTypes == ["wireless", "switch", "appliance"]
        assert network.tags == ["production", "east-coast"]
        assert network.isBoundToConfigTemplate is True
        assert network.notes == "Production network"


class TestDevice:
    """Test Device model."""

    def test_device_basic(self):
        """Test basic device creation."""
        device = Device(serial="Q2XX-XXXX-XXXX", model="MR36")
        assert device.serial == "Q2XX-XXXX-XXXX"
        assert device.model == "MR36"
        assert device.name is None
        assert device.networkId is None
        assert device.tags == []

    def test_device_full(self):
        """Test device with all fields."""
        config_time = datetime.now(UTC)
        device = Device(
            serial="Q2XX-XXXX-XXXX",
            name="Office AP",
            model="MR36",
            networkId="N_123",
            mac="00:11:22:33:44:55",
            lanIp="192.168.1.10",
            wan1Ip="10.0.0.1",
            wan2Ip="10.0.0.2",
            tags=["office", "floor-2"],
            lat=37.7749,
            lng=-122.4194,
            address="123 Main St",
            notes="Near conference room",
            url="https://device.url",
            productType="wireless",
            configurationUpdatedAt=config_time,
            firmware="mr-28.6",
            floorPlanId="fp_123",
        )
        assert device.name == "Office AP"
        assert device.mac == "00:11:22:33:44:55"
        assert device.tags == ["office", "floor-2"]
        assert device.lat == 37.7749
        assert device.configurationUpdatedAt == config_time


class TestDeviceStatus:
    """Test DeviceStatus model."""

    def test_device_status_basic(self):
        """Test basic device status."""
        status = DeviceStatus(serial="Q2XX-XXXX-XXXX", status="online")
        assert status.serial == "Q2XX-XXXX-XXXX"
        assert status.status == "online"
        assert status.usingCellularFailover is False

    def test_device_status_full(self):
        """Test device status with all fields."""
        last_reported = datetime.now(UTC)
        status = DeviceStatus(
            serial="Q2XX-XXXX-XXXX",
            status="online",
            lastReportedAt=last_reported,
            publicIp="1.2.3.4",
            lanIp="192.168.1.10",
            wan1Ip="10.0.0.1",
            wan2Ip="10.0.0.2",
            gateway="192.168.1.1",
            ipType="dhcp",
            primaryDns="8.8.8.8",
            secondaryDns="8.8.4.4",
            usingCellularFailover=True,
            wan1IpType="static",
            wan2IpType="dhcp",
        )
        assert status.lastReportedAt == last_reported
        assert status.usingCellularFailover is True
        assert status.primaryDns == "8.8.8.8"

    def test_device_status_literals(self):
        """Test device status literal validation."""
        # Valid statuses
        for status_val in ["online", "offline", "alerting", "dormant"]:
            status = DeviceStatus(serial="Q2XX-XXXX-XXXX", status=status_val)
            assert status.status == status_val


class TestPortStatus:
    """Test PortStatus model."""

    def test_port_status_basic(self):
        """Test basic port status."""
        port = PortStatus(portId="1", enabled=True, status="Connected")
        assert port.portId == "1"
        assert port.enabled is True
        assert port.status == "Connected"
        assert port.isUplink is False
        assert port.clientCount == 0
        assert port.powerUsageInWh == 0.0

    def test_port_status_full(self):
        """Test port status with all fields."""
        port = PortStatus(
            portId="1",
            enabled=True,
            status="Connected",
            isUplink=True,
            errors=["CRC errors"],
            warnings=["High utilization"],
            speed="1 Gbps",
            duplex="full",
            usageInKb={"sent": 1000, "recv": 2000},
            cdp={"deviceId": "switch.local"},
            lldp={"systemName": "switch"},
            clientCount=5,
            powerUsageInWh=15.5,
            trafficInKbps={"sent": 100.5, "recv": 200.3},
            securePort={"enabled": True},
        )
        assert port.isUplink is True
        assert port.errors == ["CRC errors"]
        assert port.clientCount == 5
        assert port.powerUsageInWh == 15.5

    def test_port_status_power_validation(self):
        """Test power usage validation."""
        # None should convert to 0.0
        port = PortStatus(portId="1", enabled=True, status="Connected", powerUsageInWh=None)
        assert port.powerUsageInWh == 0.0

        # String should convert to float
        port = PortStatus(portId="1", enabled=True, status="Connected", powerUsageInWh="12.5")
        assert port.powerUsageInWh == 12.5


class TestWirelessClient:
    """Test WirelessClient model."""

    def test_wireless_client_basic(self):
        """Test basic wireless client."""
        first_seen = datetime.now(UTC)
        last_seen = datetime.now(UTC)

        client = WirelessClient(
            id="c_123",
            mac="00:11:22:33:44:55",
            firstSeen=first_seen,
            lastSeen=last_seen,
        )
        assert client.id == "c_123"
        assert client.mac == "00:11:22:33:44:55"
        assert client.status == "Offline"  # Default
        assert client.firstSeen == first_seen
        assert client.lastSeen == last_seen

    def test_wireless_client_full(self):
        """Test wireless client with all fields."""
        first_seen = datetime.now(UTC)
        last_seen = datetime.now(UTC)

        client = WirelessClient(
            id="c_123",
            mac="00:11:22:33:44:55",
            description="John's iPhone",
            ip="192.168.1.100",
            ip6="2001:db8::1",
            ip6Local="fe80::1",
            user="john@example.com",
            firstSeen=first_seen,
            lastSeen=last_seen,
            manufacturer="Apple",
            os="iOS",
            deviceTypePrediction="iPhone",
            recentDeviceSerial="Q2XX-XXXX-XXXX",
            recentDeviceName="Office AP",
            recentDeviceMac="00:AA:BB:CC:DD:EE",
            recentDeviceConnection="802.11ac",
            ssid="Corporate",
            vlan=100,
            switchport="GigabitEthernet1/0/1",
            status="Online",
            notes="Executive device",
            usage={"sent": 1000000, "recv": 5000000},
            namedVlan="Corporate VLAN",
            adaptivePolicyGroup="Executives",
            wirelessCapabilities="802.11ac - 2.4 and 5 GHz",
        )
        assert client.description == "John's iPhone"
        assert client.ssid == "Corporate"
        assert client.vlan == 100
        assert client.status == "Online"
        assert client.usage == {"sent": 1000000, "recv": 5000000}


class TestSensorReading:
    """Test SensorReading model."""

    def test_sensor_reading_basic(self):
        """Test basic sensor reading."""
        ts = datetime.now(UTC)
        reading = SensorReading(ts=ts, metric="temperature", value=23.5)
        assert reading.ts == ts
        assert reading.metric == "temperature"
        assert reading.value == 23.5

    def test_sensor_reading_value_validation(self):
        """Test value validation."""
        ts = datetime.now(UTC)

        # String should convert to float
        reading = SensorReading(ts=ts, metric="temperature", value="23.5")
        assert reading.value == 23.5

        # Int should convert to float
        reading = SensorReading(ts=ts, metric="temperature", value=23)
        assert reading.value == 23.0

        # None should raise error
        with pytest.raises(ValidationError):
            SensorReading(ts=ts, metric="temperature", value=None)


class TestSensorData:
    """Test SensorData model."""

    def test_sensor_data_basic(self):
        """Test basic sensor data."""
        data = SensorData(serial="Q2MT-XXXX-XXXX")
        assert data.serial == "Q2MT-XXXX-XXXX"
        assert data.network is None
        assert data.readings == []

    def test_sensor_data_with_readings(self):
        """Test sensor data with readings."""
        ts = datetime.now(UTC)
        readings = [
            SensorReading(ts=ts, metric="temperature", value=23.5),
            SensorReading(ts=ts, metric="humidity", value=45.0),
        ]

        data = SensorData(
            serial="Q2MT-XXXX-XXXX",
            network={"id": "N_123", "name": "Test Network"},
            readings=readings,
        )
        assert len(data.readings) == 2
        assert data.readings[0].metric == "temperature"
        assert data.readings[1].value == 45.0
        assert data.network == {"id": "N_123", "name": "Test Network"}


class TestAPIUsage:
    """Test APIUsage model."""

    def test_api_usage_basic(self):
        """Test basic API usage."""
        ts = datetime.now(UTC)
        usage = APIUsage(
            method="GET",
            host="api.meraki.com",
            path="/api/v1/organizations",
            userAgent="python-meraki",
            ts=ts,
            responseCode=200,
        )
        assert usage.method == "GET"
        assert usage.path == "/api/v1/organizations"
        assert usage.responseCode == 200
        assert usage.queryString is None
        assert usage.sourceIp is None

    def test_api_usage_full(self):
        """Test API usage with all fields."""
        ts = datetime.now(UTC)
        usage = APIUsage(
            method="GET",
            host="api.meraki.com",
            path="/api/v1/organizations/123/devices",
            queryString="perPage=100&startingAfter=Q2XX-XXXX-XXXX",
            userAgent="python-meraki/1.0",
            ts=ts,
            responseCode=429,
            sourceIp="1.2.3.4",
        )
        assert usage.queryString == "perPage=100&startingAfter=Q2XX-XXXX-XXXX"
        assert usage.responseCode == 429
        assert usage.sourceIp == "1.2.3.4"


class TestLicense:
    """Test License model."""

    def test_license_basic(self):
        """Test basic license."""
        license = License(licenseType="MR", state="active")
        assert license.licenseType == "MR"
        assert license.state == "active"
        assert license.id is None
        assert license.seatCount is None

    def test_license_full(self):
        """Test license with all fields."""
        expiration = datetime.now(UTC)
        claimed = datetime.now(UTC)

        license = License(
            id="lic_123",
            licenseType="MR",
            licenseKey="XXXX-XXXX-XXXX",
            orderNumber="ORD-123456",
            deviceSerial="Q2XX-XXXX-XXXX",
            networkId="N_123",
            state="expiring",
            seatCount=100,
            totalDurationInDays=365,
            durationInDays=30,
            permanentlyQueuedLicenses=[{"id": "lic_456"}],
            expirationDate=expiration,
            claimedAt=claimed,
            invalidAt=None,
            invalidReason=None,
        )
        assert license.seatCount == 100
        assert license.totalDurationInDays == 365
        assert license.expirationDate == expiration


class TestClientOverview:
    """Test ClientOverview model."""

    def test_client_overview_basic(self):
        """Test basic client overview."""
        overview = ClientOverview(counts={}, usages={})
        assert overview.counts == {}
        assert overview.usages == {}

    def test_client_overview_validation(self):
        """Test client overview validation."""
        # Counts validation - converts to int
        overview = ClientOverview(
            counts={"wireless": "100", "wired": 50.5, "total": None}, usages={}
        )
        assert overview.counts == {"wireless": 100, "wired": 50, "total": 0}

        # Usages validation - nested dict
        overview = ClientOverview(
            counts={},
            usages={
                "wireless": {"sent": "1000", "recv": 2000.5, "total": None},
                "wired": {"sent": 500, "recv": 1000},
            },
        )
        assert overview.usages["wireless"] == {"sent": 1000, "recv": 2000, "total": 0}
        assert overview.usages["wired"] == {"sent": 500, "recv": 1000}

    def test_client_overview_malformed_data(self):
        """Test handling of malformed data."""
        # Non-dict counts becomes empty dict
        overview = ClientOverview(counts="not a dict", usages={})
        assert overview.counts == {}

        # Non-dict usages becomes empty dict
        overview = ClientOverview(counts={}, usages="not a dict")
        assert overview.usages == {}


class TestAlert:
    """Test Alert model."""

    def test_alert_basic(self):
        """Test basic alert."""
        occurred = datetime.now(UTC)
        alert = Alert(
            id="alert_123",
            categoryType="network",
            alertType="connectivity",
            severity="critical",
            occurredAt=occurred,
        )
        assert alert.id == "alert_123"
        assert alert.severity == "critical"
        assert alert.occurredAt == occurred
        assert alert.dismissedAt is None

    def test_alert_full(self):
        """Test alert with all fields."""
        occurred = datetime.now(UTC)
        dismissed = datetime.now(UTC)

        alert = Alert(
            id="alert_123",
            categoryType="network",
            alertType="connectivity",
            severity="warning",
            alertData={"reason": "High packet loss"},
            device={"serial": "Q2XX-XXXX-XXXX", "name": "Office AP"},
            network={"id": "N_123", "name": "Test Network"},
            occurredAt=occurred,
            dismissedAt=dismissed,
        )
        assert alert.alertData == {"reason": "High packet loss"}
        assert alert.device == {"serial": "Q2XX-XXXX-XXXX", "name": "Office AP"}
        assert alert.dismissedAt == dismissed


class TestMemoryUsage:
    """Test MemoryUsage model."""

    def test_memory_usage_basic(self):
        """Test basic memory usage."""
        ts = datetime.now(UTC)
        memory = MemoryUsage(ts=ts)
        assert memory.ts == ts
        assert memory.percentage is None
        assert memory.used is None
        assert memory.total is None
        assert memory.free is None

    def test_memory_usage_full(self):
        """Test memory usage with all fields."""
        ts = datetime.now(UTC)
        memory = MemoryUsage(
            ts=ts,
            percentage=75.5,
            used=768000,
            total=1024000,
            free=256000,
        )
        assert memory.percentage == 75.5
        assert memory.used == 768000
        assert memory.total == 1024000

    def test_memory_usage_validation(self):
        """Test numeric validation."""
        ts = datetime.now(UTC)

        # String with decimal becomes float
        memory = MemoryUsage(ts=ts, percentage="75.5")
        assert memory.percentage == 75.5

        # String without decimal becomes int
        memory = MemoryUsage(ts=ts, used="768000", total="1024000")
        assert memory.used == 768000
        assert isinstance(memory.used, int)


class TestNetworkClient:
    """Test NetworkClient model."""

    def test_network_client_basic(self):
        """Test basic network client."""
        first_seen = datetime.now(UTC)
        last_seen = datetime.now(UTC)

        client = NetworkClient(
            id="c_123",
            mac="00:11:22:33:44:55",
            firstSeen=first_seen,
            lastSeen=last_seen,
        )
        assert client.id == "c_123"
        assert client.mac == "00:11:22:33:44:55"
        assert client.status == "Offline"
        assert client.smInstalled is False
        assert client.vlan is None

    def test_network_client_vlan_conversion(self):
        """Test VLAN conversion to string."""
        first_seen = datetime.now(UTC)
        last_seen = datetime.now(UTC)

        # Integer VLAN converts to string
        client = NetworkClient(
            id="c_123",
            mac="00:11:22:33:44:55",
            firstSeen=first_seen,
            lastSeen=last_seen,
            vlan=100,  # type: ignore[arg-type]
        )
        assert client.vlan == "100"

        # String VLAN stays string
        client = NetworkClient(
            id="c_123",
            mac="00:11:22:33:44:55",
            firstSeen=first_seen,
            lastSeen=last_seen,
            vlan="200",
        )
        assert client.vlan == "200"

        # None stays None
        client = NetworkClient(
            id="c_123",
            mac="00:11:22:33:44:55",
            firstSeen=first_seen,
            lastSeen=last_seen,
            vlan=None,
        )
        assert client.vlan is None

    def test_network_client_full(self):
        """Test network client with all fields."""
        first_seen = datetime.now(UTC)
        last_seen = datetime.now(UTC)

        client = NetworkClient(
            id="c_123",
            mac="00:11:22:33:44:55",
            description="Test Client",
            ip="192.168.1.100",
            ip6="2001:db8::1",
            ip6Local="fe80::1",
            user="test@example.com",
            firstSeen=first_seen,
            lastSeen=last_seen,
            manufacturer="Apple",
            os="macOS",
            deviceTypePrediction="MacBook",
            recentDeviceSerial="Q2XX-XXXX-XXXX",
            recentDeviceName="Office Switch",
            recentDeviceMac="00:AA:BB:CC:DD:EE",
            recentDeviceConnection="Wired",
            ssid=None,
            vlan="100",
            switchport="GigabitEthernet1/0/1",
            usage={"sent": 1000, "recv": 2000},
            status="Online",
            notes="Test notes",
            groupPolicy8021x="Employee",
            adaptivePolicyGroup="Standard",
            smInstalled=True,
            namedVlan="Corporate",
            pskGroup="Guest",
            wirelessCapabilities="802.11ax",
            is11beCapable=True,
            mcgSerial="Q2MG-XXXX-XXXX",
            mcgNodeName="Node1",
            mcgNodeMac="00:11:22:33:44:66",
            mcgNetworkId="N_456",
        )
        assert client.recentDeviceConnection == "Wired"
        assert client.is11beCapable is True
        assert client.mcgSerial == "Q2MG-XXXX-XXXX"


class TestPaginatedResponse:
    """Test PaginatedResponse model."""

    def test_paginated_response_basic(self):
        """Test basic paginated response."""
        response = PaginatedResponse(items=[{"id": "1"}, {"id": "2"}])
        assert len(response.items) == 2
        assert response.meta is None

    def test_paginated_response_with_meta(self):
        """Test paginated response with metadata."""
        response = PaginatedResponse(
            items=[{"id": "1"}, {"id": "2"}, {"id": "3"}],
            meta={
                "page": 1,
                "perPage": 10,
                "total": 3,
                "totalPages": 1,
            },
        )
        assert len(response.items) == 3
        assert response.meta["page"] == 1
        assert response.meta["total"] == 3

    def test_paginated_response_extra_fields(self):
        """Test that extra fields are allowed."""
        response = PaginatedResponse(
            items=[],
            meta={"custom": "field"},
            extra_field="allowed",
        )
        assert response.items == []
        assert response.meta == {"custom": "field"}
