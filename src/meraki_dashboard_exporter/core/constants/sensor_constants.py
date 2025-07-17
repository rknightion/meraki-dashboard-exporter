"""Sensor-specific constants for the Meraki Dashboard Exporter."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

# Type alias for sensor metric types
SensorMetricTypeStr = Literal[
    "temperature",
    "humidity",
    "door",
    "water",
    "co2",
    "tvoc",
    "pm25",
    "noise",
    "battery",
    "indoorAirQuality",
    "voltage",
    "current",
    "realPower",
    "apparentPower",
    "powerFactor",
    "frequency",
    "downstreamPower",
    "remoteLockout",
]


class SensorMetricType(StrEnum):
    """Sensor metric types as returned by the API."""

    # Environmental sensors
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    DOOR = "door"
    WATER = "water"
    CO2 = "co2"
    TVOC = "tvoc"
    PM25 = "pm25"
    NOISE = "noise"
    INDOOR_AIR_QUALITY = "indoorAirQuality"

    # Power sensors
    BATTERY = "battery"
    VOLTAGE = "voltage"
    CURRENT = "current"
    REAL_POWER = "realPower"
    APPARENT_POWER = "apparentPower"
    POWER_FACTOR = "powerFactor"
    FREQUENCY = "frequency"
    DOWNSTREAM_POWER = "downstreamPower"
    REMOTE_LOCKOUT = "remoteLockout"


class SensorDataField(StrEnum):
    """Sensor data field names in API responses."""

    # Value fields
    CELSIUS = "celsius"
    RELATIVE_PERCENTAGE = "relativePercentage"
    CONCENTRATION = "concentration"
    AMBIENT = "ambient"
    LEVEL = "level"
    PERCENTAGE = "percentage"
    SCORE = "score"
    DRAW = "draw"

    # Boolean fields
    OPEN = "open"
    PRESENT = "present"
    ENABLED = "enabled"
