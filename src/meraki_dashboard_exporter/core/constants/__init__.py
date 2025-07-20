"""Domain-specific constants for the Meraki Dashboard Exporter.

This module provides organized constants split by domain for better maintainability
and LLM understanding. Constants are grouped into logical modules:

- device_constants: Device types, states, product types
- metrics_constants: Metric name enums organized by device type
- api_constants: API field names, response fields, time spans
- sensor_constants: Sensor-specific metric types and fields
- config_constants: Configuration dataclasses and defaults
"""

from __future__ import annotations

# Export all constants from domain-specific modules
from .api_constants import (
    DEFAULT_DEVICE_MODEL_MR,
    DEFAULT_DEVICE_MODEL_MT,
    DEFAULT_DEVICE_STATUS,
    APIField,
    APITimespan,
    LicenseState,
    PortState,
    RFBand,
)
from .config_constants import (
    DEFAULT_API_CONFIG,
    DEFAULT_API_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    MERAKI_API_BASE_URL,
    MERAKI_API_BASE_URL_CANADA,
    MERAKI_API_BASE_URL_CHINA,
    MERAKI_API_BASE_URL_INDIA,
    MERAKI_API_BASE_URL_US_FED,
    APIConfig,
    MerakiAPIConfig,
    RegionalURLs,
)
from .device_constants import (
    DeviceStatus,
    DeviceType,
    ProductType,
    UpdateTier,
)
from .metrics_constants import (
    AlertMetricName,
    ClientMetricName,
    ConfigMetricName,
    DeviceMetricName,
    MRMetricName,
    MSMetricName,
    MTMetricName,
    MVMetricName,
    NetworkHealthMetricName,
    NetworkMetricName,
    OrgMetricName,
)
from .sensor_constants import (
    SensorDataField,
    SensorMetricType,
)

__all__ = [
    # Device constants
    "DeviceType",
    "DeviceStatus",
    "ProductType",
    "UpdateTier",
    # Metric constants (domain-specific)
    "OrgMetricName",
    "NetworkMetricName",
    "DeviceMetricName",
    "MSMetricName",
    "MRMetricName",
    "MVMetricName",
    "MTMetricName",
    "AlertMetricName",
    "ConfigMetricName",
    "NetworkHealthMetricName",
    "ClientMetricName",
    # API constants
    "APIField",
    "APITimespan",
    "LicenseState",
    "PortState",
    "RFBand",
    "DEFAULT_DEVICE_STATUS",
    "DEFAULT_DEVICE_MODEL_MT",
    "DEFAULT_DEVICE_MODEL_MR",
    # Sensor constants
    "SensorMetricType",
    "SensorDataField",
    # Config constants
    "APIConfig",
    "MerakiAPIConfig",
    "RegionalURLs",
    "DEFAULT_API_CONFIG",
    "DEFAULT_API_TIMEOUT",
    "DEFAULT_MAX_RETRIES",
    "MERAKI_API_BASE_URL",
    "MERAKI_API_BASE_URL_CANADA",
    "MERAKI_API_BASE_URL_CHINA",
    "MERAKI_API_BASE_URL_INDIA",
    "MERAKI_API_BASE_URL_US_FED",
]
