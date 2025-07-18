"""Type definitions for common data structures.

This module provides TypedDict and other type definitions for better type safety
throughout the codebase, especially for complex dictionary structures.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class DeviceStatusInfo(TypedDict):
    """Device status information from API."""

    serial: str
    status: Literal["online", "offline", "alerting", "dormant"]
    lastReportedAt: NotRequired[str]
    publicIp: NotRequired[str]
    lanIp: NotRequired[str]
    wan1Ip: NotRequired[str]
    wan2Ip: NotRequired[str]


class MemoryUsageData(TypedDict):
    """Memory usage data structure."""

    serial: str
    network: NotRequired[dict[str, str]]
    percentage: NotRequired[float]
    used: NotRequired[int]
    total: NotRequired[int]
    free: NotRequired[int]


class PortStatusData(TypedDict):
    """Switch port status data."""

    portId: str
    enabled: bool
    status: str
    isUplink: NotRequired[bool]
    errors: NotRequired[list[str]]
    warnings: NotRequired[list[str]]
    speed: NotRequired[str]
    duplex: NotRequired[str]
    usageInKb: NotRequired[dict[str, int]]
    clientCount: NotRequired[int]
    powerUsageInWh: NotRequired[float]


class WirelessStatusData(TypedDict):
    """Wireless device status data."""

    basicServiceSets: NotRequired[list[dict[str, str]]]
    clientCount: NotRequired[int]
    connectionStats: NotRequired[dict[str, dict[str, float]]]


class SensorReadingData(TypedDict):
    """Sensor reading data."""

    ts: str
    metric: str
    value: float


class AlertData(TypedDict):
    """Alert data structure."""

    id: str
    categoryType: str
    alertType: str
    severity: Literal["critical", "warning", "informational"]
    alertData: NotRequired[dict[str, str]]
    device: NotRequired[dict[str, str]]
    network: NotRequired[dict[str, str]]
    occurredAt: str
    dismissedAt: NotRequired[str]
    resolvedAt: NotRequired[str]


class LicenseData(TypedDict):
    """License data structure."""

    id: NotRequired[str]
    licenseType: str
    licenseKey: NotRequired[str]
    orderNumber: NotRequired[str]
    deviceSerial: NotRequired[str]
    networkId: NotRequired[str]
    state: str
    seatCount: NotRequired[int]
    totalDurationInDays: NotRequired[int]
    durationInDays: NotRequired[int]
    expirationDate: NotRequired[str]
    claimedAt: NotRequired[str]


class ClientOverviewData(TypedDict):
    """Client overview data structure."""

    counts: dict[str, int]
    usages: dict[str, dict[str, int]]


class NetworkHealthData(TypedDict):
    """Network health data structure."""

    networkId: str
    devices: list[dict[str, float]]  # Device utilization data
    averagePercentages: dict[str, float]


class ConnectionStatsData(TypedDict):
    """Connection stats data structure."""

    assoc: int
    auth: int
    dhcp: int
    dns: int
    success: int


# Type aliases for common patterns
type OrganizationId = str
type NetworkId = str
type DeviceSerial = str
type PortId = str
type Timespan = int  # Seconds
type Timestamp = str  # ISO format
type MetricValue = float | int


# Response type definitions
class APIRequestData(TypedDict):
    """API request/usage data."""

    method: str
    host: str
    path: str
    queryString: NotRequired[str]
    userAgent: str
    ts: str
    responseCode: int
    sourceIp: NotRequired[str]


class ConfigurationChangeData(TypedDict):
    """Configuration change data."""

    ts: str
    adminName: str
    adminEmail: str
    adminId: str
    networkId: NotRequired[str]
    networkName: NotRequired[str]
    page: str
    label: str
    oldValue: NotRequired[str]
    newValue: NotRequired[str]


# Batch response types
class BatchedResponse(TypedDict):
    """Generic batched API response."""

    items: list[dict[str, str]]
    meta: NotRequired[dict[str, str]]


# Settings types
class UpdateInterval(TypedDict):
    """Update interval configuration."""

    fast: int
    medium: int
    slow: int
