"""Metric name constants organized by domain for the Meraki Dashboard Exporter."""

from __future__ import annotations

from enum import StrEnum


class OrgMetricName(StrEnum):
    """Organization-level metric names."""

    # Basic organization metrics
    ORG_INFO = "meraki_org"
    ORG_API_REQUESTS_TOTAL = "meraki_org_api_requests_total"
    ORG_API_REQUESTS_BY_STATUS = "meraki_org_api_requests_by_status"
    ORG_NETWORKS_TOTAL = "meraki_org_networks_total"
    ORG_DEVICES_TOTAL = "meraki_org_devices_total"
    ORG_DEVICES_BY_MODEL_TOTAL = "meraki_org_devices_by_model_total"
    ORG_DEVICES_AVAILABILITY_TOTAL = "meraki_org_devices_availability_total"

    # License metrics
    ORG_LICENSES_TOTAL = "meraki_org_licenses_total"
    ORG_LICENSES_EXPIRING = "meraki_org_licenses_expiring"

    # Client and usage metrics
    ORG_CLIENTS_TOTAL = "meraki_org_clients_total"
    ORG_USAGE_TOTAL_KB = "meraki_org_usage_total_kb"
    ORG_USAGE_DOWNSTREAM_KB = "meraki_org_usage_downstream_kb"
    ORG_USAGE_UPSTREAM_KB = "meraki_org_usage_upstream_kb"

    # Configuration and security metrics
    ORG_CONFIGURATION_CHANGES_TOTAL = "meraki_org_configuration_changes_total"
    ORG_LOGIN_SECURITY_ENABLED = "meraki_org_login_security_enabled"

    # Packet capture metrics
    ORG_PACKETCAPTURES_TOTAL = "meraki_org_packetcaptures_total"
    ORG_PACKETCAPTURES_REMAINING = "meraki_org_packetcaptures_remaining"

    # Application usage metrics
    ORG_APPLICATION_USAGE_TOTAL_MB = "meraki_org_application_usage_total_mb"
    ORG_APPLICATION_USAGE_DOWNSTREAM_MB = "meraki_org_application_usage_downstream_mb"
    ORG_APPLICATION_USAGE_UPSTREAM_MB = "meraki_org_application_usage_upstream_mb"
    ORG_APPLICATION_USAGE_PERCENTAGE = "meraki_org_application_usage_percentage"
    ORG_LOGIN_SECURITY_STRONG_PASSWORDS_ENABLED = (
        "meraki_org_login_security_strong_passwords_enabled"
    )
    ORG_LOGIN_SECURITY_TWO_FACTOR_ENABLED = "meraki_org_login_security_two_factor_enabled"
    ORG_LOGIN_SECURITY_IP_RESTRICTIONS_ENABLED = "meraki_org_login_security_ip_restrictions_enabled"
    ORG_LOGIN_SECURITY_IP_RANGES_ENABLED = "meraki_org_login_security_ip_ranges_enabled"
    ORG_LOGIN_SECURITY_IDLE_TIMEOUT_ENABLED = "meraki_org_login_security_idle_timeout_enabled"
    ORG_LOGIN_SECURITY_IDLE_TIMEOUT_MINUTES = "meraki_org_login_security_idle_timeout_minutes"
    ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_ENABLED = (
        "meraki_org_login_security_password_expiration_enabled"
    )
    ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_DAYS = (
        "meraki_org_login_security_password_expiration_days"
    )
    ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_ENABLED = (
        "meraki_org_login_security_different_passwords_enabled"
    )
    ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_COUNT = (
        "meraki_org_login_security_different_passwords_count"
    )
    ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ENABLED = "meraki_org_login_security_account_lockout_enabled"
    ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ATTEMPTS = (
        "meraki_org_login_security_account_lockout_attempts"
    )
    ORG_LOGIN_SECURITY_API_IP_RESTRICTIONS_ENABLED = (
        "meraki_org_login_security_api_ip_restrictions_enabled"
    )
    ORG_LOGIN_SECURITY_MINIMUM_PASSWORD_LENGTH = "meraki_org_login_security_minimum_password_length"


class NetworkMetricName(StrEnum):
    """Network-level metric names."""

    NETWORK_CLIENTS_TOTAL = "meraki_network_clients_total"
    NETWORK_TRAFFIC_BYTES = "meraki_network_traffic_bytes"
    NETWORK_DEVICE_STATUS = "meraki_network_device_status"
    NETWORK_WIRELESS_CONNECTION_STATS = "meraki_network_wireless_connection_stats_total"


class DeviceMetricName(StrEnum):
    """Common device metric names."""

    DEVICE_UP = "meraki_device_up"
    DEVICE_STATUS_INFO = "meraki_device_status_info"
    DEVICE_MEMORY_USAGE_PERCENT = "meraki_device_memory_usage_percent"
    DEVICE_MEMORY_USED_BYTES = "meraki_device_memory_used_bytes"
    DEVICE_MEMORY_FREE_BYTES = "meraki_device_memory_free_bytes"
    DEVICE_MEMORY_TOTAL_BYTES = "meraki_device_memory_total_bytes"


class MSMetricName(StrEnum):
    """MS (Switch) specific metric names."""

    MS_PORT_STATUS = "meraki_ms_port_status"
    MS_PORT_TRAFFIC_BYTES = "meraki_ms_port_traffic_bytes"
    MS_POWER_USAGE_WATTS = "meraki_ms_power_usage_watts"
    MS_POE_PORT_POWER_WATTS = "meraki_ms_poe_port_power_watthours"  # Actually Wh not W
    MS_POE_TOTAL_POWER_WATTS = "meraki_ms_poe_total_power_watthours"  # Actually Wh not W
    MS_POE_BUDGET_WATTS = "meraki_ms_poe_budget_watts"
    MS_POE_NETWORK_TOTAL_WATTS = "meraki_ms_poe_network_total_watthours"  # Actually Wh not W

    # Port overview metrics
    MS_PORTS_ACTIVE_TOTAL = "meraki_ms_ports_active_total"
    MS_PORTS_INACTIVE_TOTAL = "meraki_ms_ports_inactive_total"
    MS_PORTS_BY_MEDIA_TOTAL = "meraki_ms_ports_by_media_total"
    MS_PORTS_BY_LINK_SPEED_TOTAL = "meraki_ms_ports_by_link_speed_total"

    # STP metrics
    MS_STP_PRIORITY = "meraki_ms_stp_priority"

    # Additional port metrics
    MS_PORT_USAGE_BYTES = "meraki_ms_port_usage_bytes"
    MS_PORT_CLIENT_COUNT = "meraki_ms_port_client_count"

    # Packet metrics (with 5-minute window)
    MS_PORT_PACKETS_TOTAL = "meraki_ms_port_packets_total"
    MS_PORT_PACKETS_BROADCAST = "meraki_ms_port_packets_broadcast"
    MS_PORT_PACKETS_MULTICAST = "meraki_ms_port_packets_multicast"
    MS_PORT_PACKETS_CRCERRORS = "meraki_ms_port_packets_crcerrors"
    MS_PORT_PACKETS_FRAGMENTS = "meraki_ms_port_packets_fragments"
    MS_PORT_PACKETS_COLLISIONS = "meraki_ms_port_packets_collisions"
    MS_PORT_PACKETS_TOPOLOGYCHANGES = "meraki_ms_port_packets_topologychanges"

    # Packet rate metrics (packets per second)
    MS_PORT_PACKETS_RATE_TOTAL = "meraki_ms_port_packets_rate_total"
    MS_PORT_PACKETS_RATE_BROADCAST = "meraki_ms_port_packets_rate_broadcast"
    MS_PORT_PACKETS_RATE_MULTICAST = "meraki_ms_port_packets_rate_multicast"
    MS_PORT_PACKETS_RATE_CRCERRORS = "meraki_ms_port_packets_rate_crcerrors"
    MS_PORT_PACKETS_RATE_FRAGMENTS = "meraki_ms_port_packets_rate_fragments"
    MS_PORT_PACKETS_RATE_COLLISIONS = "meraki_ms_port_packets_rate_collisions"
    MS_PORT_PACKETS_RATE_TOPOLOGYCHANGES = "meraki_ms_port_packets_rate_topologychanges"


class MRMetricName(StrEnum):
    """MR (Access Point) specific metric names."""

    # Basic metrics
    MR_CLIENTS_CONNECTED = "meraki_mr_clients_connected"
    MR_SIGNAL_QUALITY = "meraki_mr_signal_quality"
    MR_CONNECTION_STATS = "meraki_mr_connection_stats_total"

    # Power and port metrics
    MR_POWER_INFO = "meraki_mr_power_info"
    MR_POWER_AC_CONNECTED = "meraki_mr_power_ac_connected"
    MR_POWER_POE_CONNECTED = "meraki_mr_power_poe_connected"
    MR_PORT_POE_INFO = "meraki_mr_port_poe_info"
    MR_PORT_LINK_NEGOTIATION_INFO = "meraki_mr_port_link_negotiation_info"
    MR_PORT_LINK_NEGOTIATION_SPEED_MBPS = "meraki_mr_port_link_negotiation_speed_mbps"
    MR_CABLE_LENGTH_METERS = "meraki_mr_cable_length_meters"

    # Aggregation metrics
    MR_AGGREGATION_SPEED_MBPS = "meraki_mr_aggregation_speed_mbps"
    MR_AGGREGATION_FULL_DUPLEX = "meraki_mr_aggregation_full_duplex"
    MR_AGGREGATION_ENABLED = "meraki_mr_aggregation_enabled"

    # Uplink and signal metrics
    MR_UPLINK_INFO = "meraki_mr_uplink_info"
    MR_SIGNAL_QUALITY_PERCENT = "meraki_mr_signal_quality_percent"
    MR_SIGNAL_NOISE_RATIO_DB = "meraki_mr_signal_noise_ratio_db"

    # Packet loss metrics - Device level
    MR_PACKETS_DOWNSTREAM_TOTAL = "meraki_mr_packets_downstream_total"
    MR_PACKETS_DOWNSTREAM_LOST = "meraki_mr_packets_downstream_lost"
    MR_PACKET_LOSS_DOWNSTREAM_PERCENT = "meraki_mr_packet_loss_downstream_percent"
    MR_PACKETS_UPSTREAM_TOTAL = "meraki_mr_packets_upstream_total"
    MR_PACKETS_UPSTREAM_LOST = "meraki_mr_packets_upstream_lost"
    MR_PACKET_LOSS_UPSTREAM_PERCENT = "meraki_mr_packet_loss_upstream_percent"
    MR_PACKETS_TOTAL = "meraki_mr_packets_total"
    MR_PACKETS_LOST_TOTAL = "meraki_mr_packets_lost_total"
    MR_PACKET_LOSS_TOTAL_PERCENT = "meraki_mr_packet_loss_total_percent"

    # Packet loss metrics - Network level
    MR_NETWORK_PACKETS_DOWNSTREAM_TOTAL = "meraki_mr_network_packets_downstream_total"
    MR_NETWORK_PACKETS_DOWNSTREAM_LOST = "meraki_mr_network_packets_downstream_lost"
    MR_NETWORK_PACKET_LOSS_DOWNSTREAM_PERCENT = "meraki_mr_network_packet_loss_downstream_percent"
    MR_NETWORK_PACKETS_UPSTREAM_TOTAL = "meraki_mr_network_packets_upstream_total"
    MR_NETWORK_PACKETS_UPSTREAM_LOST = "meraki_mr_network_packets_upstream_lost"
    MR_NETWORK_PACKET_LOSS_UPSTREAM_PERCENT = "meraki_mr_network_packet_loss_upstream_percent"
    MR_NETWORK_PACKETS_TOTAL = "meraki_mr_network_packets_total"
    MR_NETWORK_PACKETS_LOST_TOTAL = "meraki_mr_network_packets_lost_total"
    MR_NETWORK_PACKET_LOSS_TOTAL_PERCENT = "meraki_mr_network_packet_loss_total_percent"

    # Other metrics
    MR_NETWORK_TRAFFIC_KBPS = "meraki_mr_network_traffic_kbps"
    MR_CPU_LOAD_5MIN = "meraki_mr_cpu_load_5min"
    MR_RADIO_BROADCASTING = "meraki_mr_radio_broadcasting"
    MR_RADIO_CHANNEL = "meraki_mr_radio_channel"
    MR_RADIO_CHANNEL_WIDTH_MHZ = "meraki_mr_radio_channel_width_mhz"
    MR_RADIO_POWER_DBM = "meraki_mr_radio_power_dbm"

    # SSID usage metrics
    MR_SSID_USAGE_TOTAL_MB = "meraki_mr_ssid_usage_total_mb"
    MR_SSID_USAGE_DOWNSTREAM_MB = "meraki_mr_ssid_usage_downstream_mb"
    MR_SSID_USAGE_UPSTREAM_MB = "meraki_mr_ssid_usage_upstream_mb"
    MR_SSID_USAGE_PERCENTAGE = "meraki_mr_ssid_usage_percentage"
    MR_SSID_CLIENT_COUNT = "meraki_mr_ssid_client_count"


class MVMetricName(StrEnum):
    """MV (Camera) specific metric names."""

    MV_RECORDING_STATUS = "meraki_mv_recording_status"
    MV_ANALYTICS_ZONES = "meraki_mv_analytics_zones"
    MV_PEOPLE_COUNT = "meraki_mv_people_count"


class MTMetricName(StrEnum):
    """MT (Sensor) specific metric names."""

    # Environmental metrics
    MT_TEMPERATURE_CELSIUS = "meraki_mt_temperature_celsius"
    MT_HUMIDITY_PERCENT = "meraki_mt_humidity_percent"
    MT_DOOR_STATUS = "meraki_mt_door_status"
    MT_WATER_DETECTED = "meraki_mt_water_detected"
    MT_CO2_PPM = "meraki_mt_co2_ppm"
    MT_TVOC_PPB = "meraki_mt_tvoc_ppb"
    MT_PM25_UG_M3 = "meraki_mt_pm25_ug_m3"
    MT_NOISE_DB = "meraki_mt_noise_db"
    MT_INDOOR_AIR_QUALITY_SCORE = "meraki_mt_indoor_air_quality_score"

    # Power metrics
    MT_BATTERY_PERCENTAGE = "meraki_mt_battery_percentage"
    MT_VOLTAGE_VOLTS = "meraki_mt_voltage_volts"
    MT_CURRENT_AMPS = "meraki_mt_current_amps"
    MT_REAL_POWER_WATTS = "meraki_mt_real_power_watts"
    MT_APPARENT_POWER_VA = "meraki_mt_apparent_power_va"
    MT_POWER_FACTOR_PERCENT = "meraki_mt_power_factor_percent"
    MT_FREQUENCY_HZ = "meraki_mt_frequency_hz"
    MT_DOWNSTREAM_POWER_ENABLED = "meraki_mt_downstream_power_enabled"
    MT_REMOTE_LOCKOUT_STATUS = "meraki_mt_remote_lockout_status"


class AlertMetricName(StrEnum):
    """Alert metric names."""

    ALERTS_ACTIVE = "meraki_alerts_active"
    ALERTS_TOTAL_BY_SEVERITY = "meraki_alerts_total_by_severity"
    ALERTS_TOTAL_BY_NETWORK = "meraki_alerts_total_by_network"
    SENSOR_ALERTS_TOTAL = "meraki_sensor_alerts_total"


class ConfigMetricName(StrEnum):
    """Configuration metric names."""

    # Currently no separate config metrics - configuration changes are tracked under OrgMetricName
    pass


class NetworkHealthMetricName(StrEnum):
    """Network health metric names."""

    # Channel utilization metrics
    AP_CHANNEL_UTILIZATION_2_4GHZ_PERCENT = "meraki_ap_channel_utilization_2_4ghz_percent"
    AP_CHANNEL_UTILIZATION_5GHZ_PERCENT = "meraki_ap_channel_utilization_5ghz_percent"
    NETWORK_CHANNEL_UTILIZATION_2_4GHZ_PERCENT = "meraki_network_channel_utilization_2_4ghz_percent"
    NETWORK_CHANNEL_UTILIZATION_5GHZ_PERCENT = "meraki_network_channel_utilization_5ghz_percent"

    # Data rate metrics
    NETWORK_WIRELESS_DOWNLOAD_KBPS = "meraki_network_wireless_download_kbps"
    NETWORK_WIRELESS_UPLOAD_KBPS = "meraki_network_wireless_upload_kbps"

    # Bluetooth metrics
    NETWORK_BLUETOOTH_CLIENTS_TOTAL = "meraki_network_bluetooth_clients_total"


class ClientMetricName(StrEnum):
    """Client-level metric names."""

    # Client status metrics
    CLIENT_STATUS = "meraki_client_status"

    # Client usage metrics (gauges for point-in-time hourly measurements)
    CLIENT_USAGE_SENT_KB = "meraki_client_usage_sent_kb"
    CLIENT_USAGE_RECV_KB = "meraki_client_usage_recv_kb"
    CLIENT_USAGE_TOTAL_KB = "meraki_client_usage_total_kb"

    # Wireless client capability metrics
    WIRELESS_CLIENT_CAPABILITIES_COUNT = "meraki_wireless_client_capabilities_count"

    # Client distribution metrics
    CLIENTS_PER_SSID_COUNT = "meraki_clients_per_ssid_count"
    CLIENTS_PER_VLAN_COUNT = "meraki_clients_per_vlan_count"

    # Client application usage metrics
    CLIENT_APPLICATION_USAGE_SENT_KB = "meraki_client_application_usage_sent_kb"
    CLIENT_APPLICATION_USAGE_RECV_KB = "meraki_client_application_usage_recv_kb"
    CLIENT_APPLICATION_USAGE_TOTAL_KB = "meraki_client_application_usage_total_kb"

    # Wireless client signal quality metrics
    WIRELESS_CLIENT_RSSI = "meraki_wireless_client_rssi"
    WIRELESS_CLIENT_SNR = "meraki_wireless_client_snr"
