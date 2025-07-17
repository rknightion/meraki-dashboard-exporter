"""API-related constants for the Meraki Dashboard Exporter."""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Final, Literal

from .device_constants import DeviceStatus

# Type aliases for small closed sets
LicenseStateStr = Literal["active", "expired", "expiring", "unused", "unusedActive"]
PortStateStr = Literal["enabled", "disabled", "connected", "disconnected"]
RFBandStr = Literal["2.4Ghz", "5Ghz"]
STPGuardStr = Literal["disabled", "root guard", "bpdu guard", "loop guard"]


class APIField(StrEnum):
    """Common API response field names."""

    # Device fields
    SERIAL = "serial"
    MODEL = "model"
    NAME = "name"
    NETWORK_ID = "networkId"
    ORGANIZATION_ID = "organizationId"
    PRODUCT_TYPE = "productType"
    TAGS = "tags"
    FIRMWARE = "firmware"
    MAC = "mac"
    ADDRESS = "address"
    LAN_IP = "lanIp"
    PUBLIC_IP = "publicIp"
    STATUS = "status"

    # Response structure
    ITEMS = "items"

    # Error fields
    ERROR = "error"
    ERRORS = "errors"
    MESSAGE = "message"
    CODE = "code"

    # Usage fields
    SENT = "sent"
    RECEIVED = "received"
    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"
    TOTAL = "total"
    COUNT = "count"
    USED = "used"
    FREE = "free"

    # Port fields
    PORT_ID = "portId"
    ENABLED = "enabled"
    POE_ENABLED = "poeEnabled"
    LINK_NEGOTIATION = "linkNegotiation"
    DUPLEX = "duplex"
    SPEED = "speed"

    # Sensor fields
    METRIC = "metric"
    READING = "reading"
    TS = "ts"
    READINGS = "readings"

    # Time fields
    TIMESPAN = "timespan"
    INTERVAL = "interval"

    # Organization fields
    ID = "id"
    URL = "url"

    # Network health fields
    DEVICE = "device"
    NETWORK = "network"
    CHANNEL_UTILIZATION = "channelUtilization"
    WIFI = "wifi"
    NON_WIFI = "non_wifi"


class APITimespan(IntEnum):
    """Common timespan values in seconds."""

    FIVE_MINUTES = 300
    THIRTY_MINUTES = 1800
    ONE_HOUR = 3600
    TWENTY_FOUR_HOURS = 86400
    SEVEN_DAYS = 604800
    THIRTY_DAYS = 2592000


class LicenseState(StrEnum):
    """License states from API responses."""

    ACTIVE = "active"
    EXPIRED = "expired"
    EXPIRING = "expiring"
    UNUSED = "unused"
    UNUSED_ACTIVE = "unusedActive"


class PortState(StrEnum):
    """Port and connection states."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class RFBand(StrEnum):
    """RF band identifiers."""

    BAND_2_4_GHZ = "2.4Ghz"
    BAND_5_GHZ = "5Ghz"


# Default values - keeping as constants for clarity
DEFAULT_DEVICE_STATUS: Final[str] = DeviceStatus.OFFLINE
DEFAULT_DEVICE_MODEL_MT: Final[str] = "MT"
DEFAULT_DEVICE_MODEL_MR: Final[str] = "MR"
