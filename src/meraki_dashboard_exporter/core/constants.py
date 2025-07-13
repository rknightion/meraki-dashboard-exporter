"""Constants and enums for the Meraki Dashboard Exporter."""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class MetricName(StrEnum):
    """Prometheus metric names."""

    # Organization metrics
    ORG_API_REQUESTS_TOTAL = "meraki_org_api_requests_total"
    ORG_API_REQUESTS_RATE_LIMIT = "meraki_org_api_requests_rate_limit"
    ORG_NETWORKS_TOTAL = "meraki_org_networks_total"
    ORG_DEVICES_TOTAL = "meraki_org_devices_total"
    ORG_LICENSES_TOTAL = "meraki_org_licenses_total"
    ORG_LICENSES_EXPIRING = "meraki_org_licenses_expiring"

    # Network metrics
    NETWORK_CLIENTS_TOTAL = "meraki_network_clients_total"
    NETWORK_TRAFFIC_BYTES = "meraki_network_traffic_bytes"
    NETWORK_DEVICE_STATUS = "meraki_network_device_status"
    NETWORK_WIRELESS_CONNECTION_STATS = "meraki_network_wireless_connection_stats_total"

    # Device common metrics
    DEVICE_UP = "meraki_device_up"
    DEVICE_MEMORY_USAGE_PERCENT = "meraki_device_memory_usage_percent"

    # MS (Switch) specific metrics
    MS_PORT_STATUS = "meraki_ms_port_status"
    MS_PORT_TRAFFIC_BYTES = "meraki_ms_port_traffic_bytes"
    MS_PORT_ERRORS_TOTAL = "meraki_ms_port_errors_total"
    MS_POWER_USAGE_WATTS = "meraki_ms_power_usage_watts"
    MS_POE_PORT_POWER_WATTS = "meraki_ms_poe_port_power_watthours"  # Actually Wh not W
    MS_POE_TOTAL_POWER_WATTS = "meraki_ms_poe_total_power_watthours"  # Actually Wh not W
    MS_POE_BUDGET_WATTS = "meraki_ms_poe_budget_watts"
    MS_POE_NETWORK_TOTAL_WATTS = "meraki_ms_poe_network_total_watthours"  # Actually Wh not W

    # MR (Access Point) specific metrics
    MR_CLIENTS_CONNECTED = "meraki_mr_clients_connected"
    MR_SIGNAL_QUALITY = "meraki_mr_signal_quality"
    MR_CONNECTION_STATS = "meraki_mr_connection_stats_total"

    # MV (Camera) specific metrics
    MV_RECORDING_STATUS = "meraki_mv_recording_status"
    MV_ANALYTICS_ZONES = "meraki_mv_analytics_zones"
    MV_PEOPLE_COUNT = "meraki_mv_people_count"

    # MT (Sensor) specific metrics
    MT_TEMPERATURE_CELSIUS = "meraki_mt_temperature_celsius"
    MT_HUMIDITY_PERCENT = "meraki_mt_humidity_percent"
    MT_DOOR_STATUS = "meraki_mt_door_status"
    MT_WATER_DETECTED = "meraki_mt_water_detected"
    MT_CO2_PPM = "meraki_mt_co2_ppm"
    MT_TVOC_PPB = "meraki_mt_tvoc_ppb"
    MT_PM25_UG_M3 = "meraki_mt_pm25_ug_m3"
    MT_NOISE_DB = "meraki_mt_noise_db"
    MT_BATTERY_PERCENTAGE = "meraki_mt_battery_percentage"
    MT_INDOOR_AIR_QUALITY_SCORE = "meraki_mt_indoor_air_quality_score"
    MT_VOLTAGE_VOLTS = "meraki_mt_voltage_volts"
    MT_CURRENT_AMPS = "meraki_mt_current_amps"
    MT_REAL_POWER_WATTS = "meraki_mt_real_power_watts"
    MT_APPARENT_POWER_VA = "meraki_mt_apparent_power_va"
    MT_POWER_FACTOR_PERCENT = "meraki_mt_power_factor_percent"
    MT_FREQUENCY_HZ = "meraki_mt_frequency_hz"
    MT_DOWNSTREAM_POWER_ENABLED = "meraki_mt_downstream_power_enabled"
    MT_REMOTE_LOCKOUT_STATUS = "meraki_mt_remote_lockout_status"


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


class UpdateTier(StrEnum):
    """Update tier for metrics collection."""

    FAST = "fast"  # Sensor data, real-time metrics
    MEDIUM = "medium"  # Device metrics, org metrics, network health


# Default values
DEFAULT_SCRAPE_INTERVAL: Final[int] = 300  # 5 minutes
DEFAULT_API_TIMEOUT: Final[int] = 30  # seconds
DEFAULT_MAX_RETRIES: Final[int] = 3
DEFAULT_RATE_LIMIT_RETRY_WAIT: Final[int] = 60  # seconds

# Meraki API constants
MERAKI_API_BASE_URL: Final[str] = "https://api.meraki.com/api/v1"
MERAKI_API_MAX_REQUESTS_PER_SECOND: Final[int] = 10
