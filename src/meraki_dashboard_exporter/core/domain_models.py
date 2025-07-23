"""Domain models for internal data structures and API responses.

This module extends api_models.py with additional domain models for
specific device types and metric collections.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

# Network Health Models


class RFHealthData(BaseModel):
    """RF health data for wireless networks."""

    serial: str
    apName: str | None = None
    model: str
    band2_4GhzUtilization: float | None = Field(None, alias="2.4GhzUtilization")
    band5GhzUtilization: float | None = Field(None, alias="5GhzUtilization")
    timestamp: datetime | None = None

    @field_validator("band2_4GhzUtilization", "band5GhzUtilization", mode="before")
    @classmethod
    def validate_utilization(cls, v: Any) -> float | None:
        """Ensure utilization is a float between 0 and 100."""
        if v is None:
            return None
        val = float(v)
        return max(0.0, min(100.0, val))

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ConnectionStats(BaseModel):
    """Wireless connection statistics."""

    assoc: int = 0
    auth: int = 0
    dhcp: int = 0
    dns: int = 0
    success: int = 0

    @field_validator("*", mode="before")
    @classmethod
    def validate_counts(cls, v: Any) -> int:
        """Ensure counts are non-negative integers."""
        if v is None:
            return 0
        return max(0, int(v))


class NetworkConnectionStats(BaseModel):
    """Network-wide connection statistics response."""

    networkId: str
    connectionStats: ConnectionStats

    model_config = ConfigDict(extra="allow")


class DataRate(BaseModel):
    """Wireless data rate information."""

    total: int = 0
    sent: int = 0
    received: int = 0

    @field_validator("*", mode="before")
    @classmethod
    def validate_bytes(cls, v: Any) -> int:
        """Ensure byte counts are non-negative integers."""
        if v is None:
            return 0
        return max(0, int(v))

    @computed_field
    def download_kbps(self) -> float:
        """Calculate download rate in kbps."""
        # Assuming this is bytes over last 5 minutes (300 seconds)
        return (self.received * 8) / 1000 / 300 if self.received > 0 else 0.0

    @computed_field
    def upload_kbps(self) -> float:
        """Calculate upload rate in kbps."""
        # Assuming this is bytes over last 5 minutes (300 seconds)
        return (self.sent * 8) / 1000 / 300 if self.sent > 0 else 0.0


# Device-specific Models


class SwitchPort(BaseModel):
    """Enhanced switch port model with POE and traffic data."""

    portId: str
    name: str | None = None
    enabled: bool = True
    poeEnabled: bool = False
    type: str = "trunk"
    vlan: int | None = None
    voiceVlan: int | None = None
    allowedVlans: str = "all"
    isolationEnabled: bool = False
    rstpEnabled: bool = True
    stpGuard: Literal["disabled", "root guard", "bpdu guard", "loop guard"] = "disabled"
    linkNegotiation: str = "Auto negotiate"
    accessPolicyType: Literal[
        "Open", "Custom access policy", "MAC allow list", "Sticky MAC allow list"
    ] = "Open"
    tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class SwitchPortPOE(BaseModel):
    """Switch port POE status and configuration."""

    portId: str
    isAllocated: bool = False
    allocatedInWatts: float = 0.0
    drawInWatts: float = 0.0

    @field_validator("allocatedInWatts", "drawInWatts", mode="before")
    @classmethod
    def validate_watts(cls, v: Any) -> float:
        """Ensure wattage is non-negative float."""
        if v is None:
            return 0.0
        return max(0.0, float(v))

    @computed_field
    def utilization_percent(self) -> float:
        """Calculate POE utilization percentage."""
        if self.allocatedInWatts <= 0:
            return 0.0
        return min(100.0, (self.drawInWatts / self.allocatedInWatts) * 100)


class STPConfiguration(BaseModel):
    """Spanning Tree Protocol configuration for switches."""

    rstpEnabled: bool = True
    stpBridgePriority: list[dict[str, Any]] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def switch_priorities(self) -> dict[str, int]:
        """Get a mapping of switch serial to STP priority."""
        result = {}
        for priority_group in self.stpBridgePriority:
            priority = priority_group.get("stpPriority", 32768)  # Default STP priority
            switches = priority_group.get("switches", [])
            for switch_serial in switches:
                result[switch_serial] = priority
        return result

    model_config = ConfigDict(extra="allow")


class MRDeviceStats(BaseModel):
    """MR (Access Point) specific statistics."""

    serial: str
    clientCount: int = 0
    meshNeighbors: int = 0
    repeaterClients: int = 0
    cpuUsagePercent: float | None = None
    memoryUsagePercent: float | None = None

    # Packet loss metrics
    backgroundTrafficLossPercent: float | None = None
    bestEffortTrafficLossPercent: float | None = None
    videoTrafficLossPercent: float | None = None
    voiceTrafficLossPercent: float | None = None

    @field_validator("cpuUsagePercent", "memoryUsagePercent", mode="before")
    @classmethod
    def validate_percentage(cls, v: Any) -> float | None:
        """Ensure percentage is between 0 and 100."""
        if v is None:
            return None
        val = float(v)
        return max(0.0, min(100.0, val))

    @field_validator("clientCount", "meshNeighbors", "repeaterClients", mode="before")
    @classmethod
    def validate_counts(cls, v: Any) -> int:
        """Ensure counts are non-negative integers."""
        if v is None:
            return 0
        return max(0, int(v))

    model_config = ConfigDict(extra="allow")


class MRRadioStatus(BaseModel):
    """MR radio status information."""

    serial: str
    radioIndex: int
    operatingChannel: int | None = None
    transmitPower: float | None = None
    standard: str | None = None
    enabled: bool = True

    @field_validator("radioIndex", mode="before")
    @classmethod
    def validate_radio_index(cls, v: Any) -> int:
        """Ensure radio index is valid."""
        val = int(v)
        if val not in {0, 1, 2}:  # 0=2.4GHz, 1=5GHz, 2=6GHz
            raise ValueError(f"Invalid radio index: {val}")
        return val

    model_config = ConfigDict(extra="allow")


# Configuration and Management Models


class ConfigurationChange(BaseModel):
    """Configuration change event."""

    ts: datetime
    adminId: str | None = None
    adminName: str | None = None
    adminEmail: str | None = None
    networkId: str | None = None
    networkName: str | None = None
    page: str | None = None
    label: str | None = None
    oldValue: Any = None
    newValue: Any = None

    model_config = ConfigDict(extra="allow")


# Sensor Models


class SensorMeasurement(BaseModel):
    """Individual sensor measurement."""

    metric: Literal[
        "temperature",
        "humidity",
        "water",
        "door",
        "tvoc",
        "co2",
        "noise",
        "pm25",
        "indoorAirQuality",
        "battery",
        "voltage",
        "current",
        "realPower",
        "apparentPower",
        "powerFactor",
        "frequency",
        "downstreamPower",
        "remoteLockout",
        "remoteLockoutSwitch",
    ]
    value: float
    unit: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, v: Any) -> float:
        """Ensure value is a float."""
        if v is None:
            raise ValueError("Sensor value cannot be None")
        return float(v)

    @computed_field
    def normalized_unit(self) -> str:
        """Get normalized unit based on metric type."""
        unit_map = {
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
        return unit_map.get(self.metric, self.unit or "unknown")


class MTSensorReading(BaseModel):
    """MT sensor reading with all measurements."""

    serial: str
    networkId: str
    timestamp: datetime
    measurements: list[SensorMeasurement]

    model_config = ConfigDict(extra="allow")


# Organization Models


class OrganizationSummary(BaseModel):
    """Organization summary with device and network counts."""

    id: str
    name: str
    deviceCounts: dict[str, int] = Field(default_factory=dict)
    networkCount: int = 0
    wirelessNetworkCount: int = 0
    switchNetworkCount: int = 0
    applianceNetworkCount: int = 0
    cameraNetworkCount: int = 0
    sensorNetworkCount: int = 0

    @computed_field
    def total_devices(self) -> int:
        """Calculate total device count."""
        return sum(self.deviceCounts.values())

    @field_validator("deviceCounts", mode="before")
    @classmethod
    def validate_device_counts(cls, v: Any) -> dict[str, int]:
        """Ensure device counts are valid."""
        if not isinstance(v, dict):
            return {}
        return {k: max(0, int(val)) for k, val in v.items() if val is not None}


# Client Models


class ClientData(BaseModel):
    """Enhanced client data with resolved hostname."""

    id: str
    mac: str
    description: str | None = None
    hostname: str | None = None  # Resolved via reverse DNS
    calculatedHostname: str | None = None  # The actual hostname used in metrics
    ip: str | None = None
    ip6: str | None = None
    ip6Local: str | None = None
    user: str | None = None
    firstSeen: datetime
    lastSeen: datetime
    manufacturer: str | None = None
    os: str | None = None
    deviceTypePrediction: str | None = None
    recentDeviceSerial: str | None = None
    recentDeviceName: str | None = None
    recentDeviceMac: str | None = None
    recentDeviceConnection: Literal["Wired", "Wireless"] | str | None = None
    ssid: str | None = None
    vlan: str | None = None
    switchport: str | None = None
    status: Literal["Online", "Offline"] | str = "Offline"
    usage: dict[str, int] | None = None
    notes: str | None = None
    groupPolicy8021x: str | None = None
    adaptivePolicyGroup: str | None = None
    smInstalled: bool = False
    namedVlan: str | None = None
    pskGroup: str | None = None
    wirelessCapabilities: str | None = None
    networkId: str | None = None
    networkName: str | None = None
    organizationId: str | None = None

    @computed_field
    def effective_ssid(self) -> str:
        """Get effective SSID (use 'Wired' for wired connections)."""
        if self.recentDeviceConnection == "Wired":
            return "Wired"
        return self.ssid or "Unknown"

    @computed_field
    def display_name(self) -> str:
        """Get best available display name."""
        return self.description or self.hostname or self.mac

    model_config = ConfigDict(extra="allow")


# Helper function to convert raw API responses to domain models


def parse_rf_health_response(data: dict[str, Any]) -> RFHealthData | None:
    """Parse RF health API response to domain model.

    Parameters
    ----------
    data : dict[str, Any]
        Raw API response data.

    Returns
    -------
    RFHealthData | None
        Parsed RF health data or None if parsing fails.

    """
    try:
        return RFHealthData(**data)
    except Exception:
        return None


def parse_connection_stats(data: dict[str, Any]) -> ConnectionStats:
    """Parse connection stats from API response.

    Parameters
    ----------
    data : dict[str, Any]
        Raw connection stats data.

    Returns
    -------
    ConnectionStats
        Parsed connection statistics with defaults for missing values.

    """
    return ConnectionStats(**data)
