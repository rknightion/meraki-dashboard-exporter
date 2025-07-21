"""Factory functions for creating test data."""

from __future__ import annotations

import random
import string
from datetime import UTC, datetime, timedelta
from typing import Any

from meraki_dashboard_exporter.core.constants import DeviceStatus, DeviceType, ProductType
from meraki_dashboard_exporter.core.constants.sensor_constants import SensorMetricType


class DataFactory:
    """Factory for creating test data with sensible defaults."""

    @staticmethod
    def generate_id(prefix: str = "") -> str:
        """Generate a random ID with optional prefix."""
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
        return f"{prefix}{suffix}" if prefix else suffix

    @staticmethod
    def generate_serial() -> str:
        """Generate a device serial number."""
        prefix = random.choice(["Q2KD", "Q2LW", "Q2MX", "Q2SW", "Q2MT"])
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return f"{prefix}-{suffix}"

    @staticmethod
    def generate_mac() -> str:
        """Generate a MAC address."""
        octets = [f"{random.randint(0, 255):02x}" for _ in range(6)]
        return ":".join(octets)

    @staticmethod
    def generate_ip() -> str:
        """Generate an IP address."""
        return f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"


class OrganizationFactory:
    """Factory for creating organization data."""

    @staticmethod
    def create(org_id: str | None = None, name: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Create organization data.

        Parameters
        ----------
        org_id : str, optional
            Organization ID
        name : str, optional
            Organization name
        **kwargs : Any
            Additional fields to include

        Returns
        -------
        dict[str, Any]
            Organization data

        """
        org_data = {
            "id": org_id or DataFactory.generate_id("org_"),
            "name": name or f"Test Organization {random.randint(1, 100)}",
            "url": "https://dashboard.meraki.com/o/XXXXX/manage/organization/overview",
        }
        org_data.update(kwargs)
        return org_data

    @staticmethod
    def create_many(count: int = 3) -> list[dict[str, Any]]:
        """Create multiple organizations."""
        return [OrganizationFactory.create() for _ in range(count)]


class NetworkFactory:
    """Factory for creating network data."""

    @staticmethod
    def create(
        network_id: str | None = None,
        name: str | None = None,
        org_id: str | None = None,
        product_types: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create network data.

        Parameters
        ----------
        network_id : str, optional
            Network ID
        name : str, optional
            Network name
        org_id : str, optional
            Organization ID
        product_types : list[str], optional
            Product types (defaults to ["wireless", "switch"])
        **kwargs : Any
            Additional fields

        Returns
        -------
        dict[str, Any]
            Network data

        """
        network_data = {
            "id": network_id or DataFactory.generate_id("N_"),
            "organizationId": org_id or DataFactory.generate_id("org_"),
            "name": name or f"Test Network {random.randint(1, 100)}",
            "productTypes": product_types or ["wireless", "switch"],
            "timeZone": "America/Los_Angeles",
            "tags": [],
            "enrollmentString": None,
        }
        network_data.update(kwargs)
        return network_data

    @staticmethod
    def create_many(
        count: int = 3, org_id: str | None = None, product_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Create multiple networks."""
        return [
            NetworkFactory.create(org_id=org_id, product_types=product_types) for _ in range(count)
        ]


class DeviceFactory:
    """Factory for creating device data."""

    @staticmethod
    def create(
        serial: str | None = None,
        name: str | None = None,
        model: str | None = None,
        network_id: str | None = None,
        device_type: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create device data.

        Parameters
        ----------
        serial : str, optional
            Device serial
        name : str, optional
            Device name
        model : str, optional
            Device model
        network_id : str, optional
            Network ID
        device_type : str, optional
            Device type (MR, MS, MX, etc.)
        **kwargs : Any
            Additional fields

        Returns
        -------
        dict[str, Any]
            Device data

        """
        # Auto-determine model from device type if not provided
        if not model and device_type:
            model_map = {
                DeviceType.MR: "MR36",
                DeviceType.MS: "MS250-48",
                DeviceType.MX: "MX64",
                DeviceType.MG: "MG21",
                DeviceType.MV: "MV12",
                DeviceType.MT: "MT10",
            }
            # Cast device_type to DeviceType if it's a valid enum value
            if device_type in DeviceType.__members__.values():
                # Cast to DeviceType for type safety
                device_type_enum = DeviceType(device_type)
                model = model_map.get(device_type_enum, "MR36")
            else:
                model = "MR36"
        elif not model:
            model = "MR36"

        # Infer device type from model if not provided
        if not device_type:
            device_type = model[:2] if model else DeviceType.MR

        device_data = {
            "serial": serial or DataFactory.generate_serial(),
            "name": name or f"{device_type} Device {random.randint(1, 100)}",
            "model": model,
            "networkId": network_id or DataFactory.generate_id("N_"),
            "mac": DataFactory.generate_mac(),
            "lanIp": DataFactory.generate_ip(),
            "tags": [],
            "lat": 37.7749 + random.uniform(-0.1, 0.1),
            "lng": -122.4194 + random.uniform(-0.1, 0.1),
            "address": f"{random.randint(100, 999)} Test St, San Francisco, CA",
            "firmware": f"{device_type.lower()}-{random.randint(28, 30)}.{random.randint(1, 9)}",
            "url": f"https://dashboard.meraki.com/manage/nodes/show/{serial}",
        }
        device_data.update(kwargs)
        return device_data

    @staticmethod
    def create_mr(serial: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Create MR (access point) device."""
        return DeviceFactory.create(
            serial=serial, device_type=DeviceType.MR, model=kwargs.pop("model", "MR36"), **kwargs
        )

    @staticmethod
    def create_ms(serial: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Create MS (switch) device."""
        return DeviceFactory.create(
            serial=serial,
            device_type=DeviceType.MS,
            model=kwargs.pop("model", "MS250-48"),
            **kwargs,
        )

    @staticmethod
    def create_mx(serial: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Create MX (security appliance) device."""
        return DeviceFactory.create(
            serial=serial, device_type=DeviceType.MX, model=kwargs.pop("model", "MX64"), **kwargs
        )

    @staticmethod
    def create_mt(serial: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Create MT (sensor) device."""
        return DeviceFactory.create(
            serial=serial, device_type=DeviceType.MT, model=kwargs.pop("model", "MT10"), **kwargs
        )

    @staticmethod
    def create_mixed(count: int = 6, network_id: str | None = None) -> list[dict[str, Any]]:
        """Create a mix of different device types."""
        devices = []
        device_types = [
            (DeviceFactory.create_mr, 2),
            (DeviceFactory.create_ms, 2),
            (DeviceFactory.create_mx, 1),
            (DeviceFactory.create_mt, 1),
        ]

        for factory_func, type_count in device_types:
            for _ in range(min(type_count, count - len(devices))):
                devices.append(factory_func(network_id=network_id))
                if len(devices) >= count:
                    break

        return devices


class DeviceStatusFactory:
    """Factory for creating device status/availability data."""

    @staticmethod
    def create(
        serial: str | None = None, status: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """Create device status data.

        Parameters
        ----------
        serial : str, optional
            Device serial
        status : str, optional
            Device status
        **kwargs : Any
            Additional fields

        Returns
        -------
        dict[str, Any]
            Device status data

        """
        status_data = {
            "serial": serial or DataFactory.generate_serial(),
            "status": status or DeviceStatus.ONLINE,
            "lastReportedAt": datetime.now(UTC).isoformat() + "Z",
            "publicIp": DataFactory.generate_ip(),
            "gateway": DataFactory.generate_ip(),
            "ipType": "dhcp",
            "primaryDns": "8.8.8.8",
            "secondaryDns": "8.8.4.4",
        }
        status_data.update(kwargs)
        return status_data

    @staticmethod
    def create_availability(
        serial: str | None = None,
        status: str | None = None,
        product_type: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create device availability data (new API format)."""
        avail_data = {
            "serial": serial or DataFactory.generate_serial(),
            "status": status or DeviceStatus.ONLINE,
            "productType": product_type or ProductType.WIRELESS,
            "lastReportedAt": datetime.now(UTC).isoformat() + "Z",
        }
        avail_data.update(kwargs)
        return avail_data


class AlertFactory:
    """Factory for creating alert data."""

    @staticmethod
    def create(
        alert_id: str | None = None,
        alert_type: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create alert data.

        Parameters
        ----------
        alert_id : str, optional
            Alert ID
        alert_type : str, optional
            Alert type
        severity : str, optional
            Alert severity
        status : str, optional
            Alert status
        **kwargs : Any
            Additional fields

        Returns
        -------
        dict[str, Any]
            Alert data

        """
        alert_types = ["connectivity", "performance", "security", "configuration"]
        severities = ["critical", "warning", "informational"]

        alert_data = {
            "id": alert_id or DataFactory.generate_id("alert_"),
            "type": alert_type or random.choice(alert_types),
            "category": kwargs.pop("category", "network"),
            "severity": severity or random.choice(severities),
            "status": status or "active",
            "deviceType": kwargs.pop("device_type", random.choice(["MR", "MS", "MX"])),
            "occurredAt": (
                datetime.now(UTC) - timedelta(minutes=random.randint(1, 60))
            ).isoformat(),
            "dismissedAt": None if status == "active" else datetime.now(UTC).isoformat(),
            "resolvedAt": None,
            "suppressedAt": None,
            "title": kwargs.pop("title", "Test Alert"),
            "description": kwargs.pop("description", "This is a test alert"),
        }

        # Add network info if provided
        if "network_id" in kwargs:
            alert_data["network"] = {
                "id": kwargs.pop("network_id"),
                "name": kwargs.pop("network_name", "Test Network"),
            }

        alert_data.update(kwargs)
        return alert_data

    @staticmethod
    def create_many(
        count: int = 5, network_id: str | None = None, status: str = "active"
    ) -> list[dict[str, Any]]:
        """Create multiple alerts."""
        alerts = []
        for _ in range(count):
            alert = AlertFactory.create(status=status)
            if network_id:
                alert["network"] = {
                    "id": network_id,
                    "name": f"Network {random.randint(1, 10)}",
                }
            alerts.append(alert)
        return alerts


class SensorDataFactory:
    """Factory for creating sensor data."""

    @staticmethod
    def create_reading(
        metric: str | None = None, value: float | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """Create a sensor reading.

        Parameters
        ----------
        metric : str, optional
            Metric type
        value : float, optional
            Metric value
        **kwargs : Any
            Additional fields

        Returns
        -------
        dict[str, Any]
            Sensor reading data

        """
        if not metric:
            metric = random.choice([
                SensorMetricType.TEMPERATURE,
                SensorMetricType.HUMIDITY,
                SensorMetricType.CO2,
                SensorMetricType.TVOC,
            ])

        if value is None:
            # Generate realistic values based on metric type
            value_ranges = {
                SensorMetricType.TEMPERATURE: (18.0, 26.0),
                SensorMetricType.HUMIDITY: (30.0, 70.0),
                SensorMetricType.CO2: (400.0, 1000.0),
                SensorMetricType.TVOC: (0.0, 500.0),
                SensorMetricType.PM25: (0.0, 50.0),
                SensorMetricType.NOISE: (30.0, 70.0),
                SensorMetricType.WATER: (0.0, 1.0),
                SensorMetricType.DOOR: (0.0, 1.0),
                SensorMetricType.BATTERY: (0.0, 100.0),
            }
            # Handle metric that might be a string
            if isinstance(metric, str) and metric in SensorMetricType.__members__.values():
                metric_enum = SensorMetricType(metric)
                min_val, max_val = value_ranges.get(metric_enum, (0.0, 100.0))
            else:
                min_val, max_val = (0.0, 100.0)
            value = round(random.uniform(min_val, max_val), 2)

        reading = {
            "metric": metric,
            "value": value,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        reading.update(kwargs)
        return reading

    @staticmethod
    def create_sensor_data(
        serial: str | None = None,
        network_id: str | None = None,
        readings: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create complete sensor data response.

        Parameters
        ----------
        serial : str, optional
            Device serial
        network_id : str, optional
            Network ID
        readings : list[dict], optional
            Sensor readings
        **kwargs : Any
            Additional fields

        Returns
        -------
        dict[str, Any]
            Sensor data

        """
        if not readings:
            # Create a few random readings
            num_readings = random.randint(1, 4)
            metrics = random.sample(
                [
                    SensorMetricType.TEMPERATURE,
                    SensorMetricType.HUMIDITY,
                    SensorMetricType.CO2,
                    SensorMetricType.BATTERY,
                ],
                num_readings,
            )
            readings = [SensorDataFactory.create_reading(metric=m) for m in metrics]

        sensor_data = {
            "serial": serial or DataFactory.generate_serial(),
            "networkId": network_id or DataFactory.generate_id("N_"),
            "readings": readings,
        }
        sensor_data.update(kwargs)
        return sensor_data


class TimeSeriesFactory:
    """Factory for creating time series data."""

    @staticmethod
    def create_data_points(
        count: int = 10,
        interval: int = 300,
        base_value: float = 50.0,
        variance: float = 10.0,
        trend: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Create time series data points.

        Parameters
        ----------
        count : int
            Number of data points
        interval : int
            Seconds between points
        base_value : float
            Base value for the series
        variance : float
            Random variance to add
        trend : float
            Trend per interval

        Returns
        -------
        list[dict[str, Any]]
            Time series data points

        """
        points = []
        current_time = datetime.now(UTC) - timedelta(seconds=interval * count)

        for i in range(count):
            value = base_value + (trend * i) + random.uniform(-variance, variance)
            points.append({
                "timestamp": current_time.isoformat() + "Z",
                "value": round(max(0, value), 2),
            })
            current_time += timedelta(seconds=interval)

        return points

    @staticmethod
    def create_memory_usage(
        serial: str | None = None, count: int = 10, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Create memory usage history data."""
        usage_data = []
        base_time = datetime.now(UTC) - timedelta(minutes=count * 5)

        for i in range(count):
            timestamp = base_time + timedelta(minutes=i * 5)
            usage_data.append({
                "serial": serial or DataFactory.generate_serial(),
                "ts": timestamp.isoformat() + "Z",
                "usage": {
                    "percentage": round(random.uniform(40, 80), 2),
                },
            })

        return usage_data


class ResponseFactory:
    """Factory for creating API response formats."""

    @staticmethod
    def paginated_response(
        items: list[Any],
        page: int = 1,
        per_page: int = 10,
        total: int | None = None,
    ) -> dict[str, Any]:
        """Create a paginated response.

        Parameters
        ----------
        items : list[Any]
            Items for this page
        page : int
            Current page number
        per_page : int
            Items per page
        total : int, optional
            Total items (defaults to items count)

        Returns
        -------
        dict[str, Any]
            Paginated response

        """
        if total is None:
            total = len(items)

        return {
            "items": items,
            "meta": {
                "page": page,
                "perPage": per_page,
                "total": total,
                "totalPages": (total + per_page - 1) // per_page,
            },
        }

    @staticmethod
    def error_response(
        status_code: int = 404,
        message: str | None = None,
        errors: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create an error response.

        Parameters
        ----------
        status_code : int
            HTTP status code
        message : str, optional
            Error message
        errors : list[str], optional
            Detailed errors

        Returns
        -------
        dict[str, Any]
            Error response

        """
        default_messages = {
            404: "Not found",
            429: "Too many requests",
            500: "Internal server error",
            503: "Service unavailable",
        }

        return {
            "errors": errors or [message or default_messages.get(status_code, "Error")],
        }


class ClientFactory:
    """Factory for creating client data."""

    @staticmethod
    def create(
        client_id: str | None = None,
        mac: str | None = None,
        ip: str | None = None,
        description: str | None = None,
        status: str | None = None,
        ssid: str | None = None,
        vlan: int | None = None,
        usage: dict[str, int] | None = None,
        recentDeviceConnection: str | None = None,  # noqa: N803
        wirelessCapabilities: str | None = None,  # noqa: N803
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create client data.

        Parameters
        ----------
        client_id : str, optional
            Client ID
        mac : str, optional
            MAC address
        ip : str, optional
            IP address
        description : str, optional
            Client description/name
        status : str, optional
            Client status (Online/Offline)
        ssid : str, optional
            SSID for wireless clients
        vlan : int, optional
            VLAN ID
        usage : dict[str, int], optional
            Usage data with sent/recv/total
        recentDeviceConnection : str, optional
            Connection type (Wireless/Wired)
        wirelessCapabilities : str, optional
            Wireless capabilities string
        **kwargs : Any
            Additional fields

        Returns
        -------
        dict[str, Any]
            Client data

        """
        client_data = {
            "id": client_id or DataFactory.generate_id("c_"),
            "mac": mac or DataFactory.generate_mac(),
            "ip": ip or DataFactory.generate_ip(),
            "description": description or f"Client {random.randint(1, 100)}",
            "status": status or "Online",
            "lastSeen": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "firstSeen": (datetime.now(UTC) - timedelta(days=random.randint(1, 30)))
            .isoformat()
            .replace("+00:00", "Z"),
            "manufacturer": random.choice(["Apple", "Samsung", "Dell", "HP", "Cisco"]),
            "os": random.choice(["Mac OS X", "Windows 10", "iOS", "Android", "Linux"]),
            "recentDeviceSerial": DataFactory.generate_serial(),
            "recentDeviceName": f"Device {random.randint(1, 10)}",
            "recentDeviceConnection": recentDeviceConnection or "Wireless",
            "ssid": ssid,
            "vlan": vlan,
            "usage": usage
            or {
                "sent": random.randint(100, 10000),
                "recv": random.randint(100, 10000),
                "total": random.randint(200, 20000),
            },
        }

        # Add wireless capabilities only for wireless clients
        if client_data["recentDeviceConnection"] == "Wireless" and wirelessCapabilities:
            client_data["wirelessCapabilities"] = wirelessCapabilities
        elif client_data["recentDeviceConnection"] == "Wireless":
            client_data["wirelessCapabilities"] = random.choice([
                "802.11ac - 2.4 and 5 GHz",
                "802.11n - 2.4 GHz",
                "802.11n - 2.4 and 5 GHz",
                "802.11ax - 5 GHz",
            ])

        client_data.update(kwargs)
        return client_data

    @staticmethod
    def create_many(
        count: int = 5,
        network_id: str | None = None,
        mix_wired_wireless: bool = True,
    ) -> list[dict[str, Any]]:
        """Create multiple clients.

        Parameters
        ----------
        count : int
            Number of clients to create
        network_id : str, optional
            Network ID for all clients
        mix_wired_wireless : bool
            Whether to create a mix of wired and wireless clients

        Returns
        -------
        list[dict[str, Any]]
            List of client data

        """
        clients = []
        for i in range(count):
            if mix_wired_wireless and i % 4 == 0:  # 25% wired
                client = ClientFactory.create(
                    recentDeviceConnection="Wired",
                    ssid=None,
                    vlan=random.choice([None, 100, 200]),
                )
            else:
                client = ClientFactory.create(
                    recentDeviceConnection="Wireless",
                    ssid=random.choice(["Corporate", "Guest", "IoT"]),
                    vlan=random.choice([100, 200, 300]),
                )

            if network_id:
                client["networkId"] = network_id

            clients.append(client)

        return clients
