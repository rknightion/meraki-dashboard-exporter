"""Device-related constants for the Meraki Dashboard Exporter."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

# Type aliases for better LLM understanding
DeviceTypeStr = Literal["MS", "MR", "MV", "MT", "MX", "MG"]
DeviceStatusStr = Literal["online", "offline", "alerting", "dormant"]
ProductTypeStr = Literal["switch", "wireless", "camera", "sensor", "appliance", "cellularGateway"]


class DeviceType(StrEnum):
    """Meraki device types."""

    MS = "MS"  # Switches
    MR = "MR"  # Wireless APs
    MV = "MV"  # Cameras
    MT = "MT"  # Sensors
    MX = "MX"  # Security appliances
    MG = "MG"  # Cellular gateways


class DeviceStatus(StrEnum):
    """Device status values."""

    ONLINE = "online"
    OFFLINE = "offline"
    ALERTING = "alerting"
    DORMANT = "dormant"


class ProductType(StrEnum):
    """Meraki product types as used in API responses."""

    SWITCH = "switch"
    WIRELESS = "wireless"
    CAMERA = "camera"
    SENSOR = "sensor"
    APPLIANCE = "appliance"
    CELLULAR_GATEWAY = "cellularGateway"
