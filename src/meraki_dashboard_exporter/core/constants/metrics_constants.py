"""Metric name constants organized by domain for the Meraki Dashboard Exporter."""

from __future__ import annotations

from enum import StrEnum


class OrgMetricName(StrEnum):
    """Organization-level metric names."""

    # Basic organization metrics
    ORG_INFO = "meraki_org"
    # Windowed count (1-hour window, resets each cycle) - not a monotonic Counter (#531)
    ORG_API_REQUESTS_COUNT = "meraki_org_api_requests_count"
    ORG_API_REQUESTS_BY_STATUS = "meraki_org_api_requests_by_status"
    # Per-operation breakdown of API requests in the trailing 1-hour window
    # (windowed snapshot gauge, NOT a monotonic counter). Bounded by top-N
    # operation ids with the tail bucketed as "other"; labelled by endpoint
    # (Meraki operationId, never a URL with IDs) + status_code only - no
    # adminId/sourceIp/path (PII + unbounded). See #274.
    ORG_API_REQUESTS_BY_OPERATION = "meraki_org_api_requests_by_operation"
    ORG_NETWORKS = "meraki_org_networks"
    ORG_DEVICES = "meraki_org_devices"
    ORG_DEVICES_BY_MODEL = "meraki_org_devices_by_model"
    ORG_DEVICES_AVAILABILITY = "meraki_org_devices_availability"

    # License metrics
    ORG_LICENSES = "meraki_org_licenses"
    ORG_LICENSES_EXPIRING = "meraki_org_licenses_expiring"

    # Client and usage metrics (usage values emitted in bytes, decimal KB x1000)
    ORG_CLIENTS_COUNT = "meraki_org_clients_count"
    ORG_USAGE_TOTAL_BYTES = "meraki_org_usage_total_bytes"
    ORG_USAGE_DOWNSTREAM_BYTES = "meraki_org_usage_downstream_bytes"
    ORG_USAGE_UPSTREAM_BYTES = "meraki_org_usage_upstream_bytes"

    # Configuration and security metrics
    ORG_CONFIGURATION_CHANGES_COUNT = "meraki_org_configuration_changes_count"

    # Packet capture metrics
    ORG_PACKETCAPTURES = "meraki_org_packetcaptures"
    ORG_PACKETCAPTURES_REMAINING = "meraki_org_packetcaptures_remaining"

    # Application usage metrics (values emitted in bytes, decimal MB x1_000_000)
    ORG_APPLICATION_USAGE_TOTAL_BYTES = "meraki_org_application_usage_total_bytes"
    ORG_APPLICATION_USAGE_DOWNSTREAM_BYTES = "meraki_org_application_usage_downstream_bytes"
    ORG_APPLICATION_USAGE_UPSTREAM_BYTES = "meraki_org_application_usage_upstream_bytes"
    ORG_APPLICATION_USAGE_PERCENT = "meraki_org_application_usage_percent"
    # NOTE (#523): meraki_org_login_security_strong_passwords_enabled was
    # removed - it derived from a deprecated Meraki field (strongPasswordsEnabled
    # / enforceStrongPasswords) that is now always-true, so the gauge conveyed no
    # information. The emission in collectors/config.py must be dropped in lockstep.
    ORG_LOGIN_SECURITY_TWO_FACTOR_ENABLED = "meraki_org_login_security_two_factor_enabled"
    ORG_LOGIN_SECURITY_IP_RANGES_ENABLED = "meraki_org_login_security_ip_ranges_enabled"
    ORG_LOGIN_SECURITY_IDLE_TIMEOUT_ENABLED = "meraki_org_login_security_idle_timeout_enabled"
    ORG_LOGIN_SECURITY_IDLE_TIMEOUT_SECONDS = "meraki_org_login_security_idle_timeout_seconds"
    ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_ENABLED = (
        "meraki_org_login_security_password_expiration_enabled"
    )
    ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_SECONDS = (
        "meraki_org_login_security_password_expiration_seconds"
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

    # Admin accounts & 2FA/SSO posture (getOrganizationAdmins; aggregated, no per-admin PII)
    ORG_ADMINS = "meraki_org_admins"
    ORG_ADMINS_TWO_FACTOR_ENABLED = "meraki_org_admins_two_factor_enabled"

    # Firmware upgrade status & staged rollout tracking (getOrganizationFirmwareUpgrades)
    ORG_FIRMWARE_UPGRADES = "meraki_org_firmware_upgrades"
    ORG_FIRMWARE_UPGRADES_PENDING = "meraki_org_firmware_upgrades_pending"

    # Device availability change history (getOrganizationDevicesAvailabilitiesChangeHistory)
    ORG_DEVICES_AVAILABILITY_CHANGES_COUNT = "meraki_org_devices_availability_changes_count"


class NetworkMetricName(StrEnum):
    """Network-level metric names."""

    NETWORK_WIRELESS_CONNECTION_STATS_COUNT = "meraki_network_wireless_connection_stats_count"
    # id-keyed join carrier: maps network_id -> network_name (issue #534, Option B)
    NETWORK_INFO = "meraki_network_info"
    # Network-filter observability (emitted by services/inventory.py)
    NETWORK_FILTER_MATCH = "meraki_network_filter_match"
    NETWORK_FILTER_RESOLVED = "meraki_network_filter_resolved"
    # Pre-filter network count (networks discovered before filtering)
    NETWORK_FILTER_NETWORKS = "meraki_network_filter_networks"


class DeviceMetricName(StrEnum):
    """Common device metric names."""

    DEVICE_UP = "meraki_device_up"
    DEVICE_STATUS_INFO = "meraki_device_status_info"
    DEVICE_MEMORY_USAGE_PERCENT = "meraki_device_memory_usage_percent"
    # Memory values are genuinely binary: API reports KiB, emitted as bytes (KiB x1024)
    DEVICE_MEMORY_USED_BYTES = "meraki_device_memory_used_bytes"
    DEVICE_MEMORY_FREE_BYTES = "meraki_device_memory_free_bytes"
    DEVICE_MEMORY_TOTAL_BYTES = "meraki_device_memory_total_bytes"


class MSMetricName(StrEnum):
    """MS (Switch) specific metric names."""

    MS_PORT_STATUS = "meraki_ms_port_status"
    # id-keyed join carrier: maps serial+port_id -> port_name (issue #534, Option B)
    MS_PORT_INFO = "meraki_ms_port_info"
    # Rate, not a volume: API kbps converted x1000/8 to bytes/second (#531 D7)
    MS_PORT_TRAFFIC_BYTES_PER_SECOND = "meraki_ms_port_traffic_bytes_per_second"
    MS_POWER_USAGE_WATTS = "meraki_ms_power_usage_watts"
    # Energy over the reporting window: API watt-hours converted x3600 to joules (#531 D3)
    MS_POE_PORT_ENERGY_JOULES = "meraki_ms_poe_port_energy_joules"
    MS_POE_TOTAL_ENERGY_JOULES = "meraki_ms_poe_total_energy_joules"
    MS_POE_BUDGET_WATTS = "meraki_ms_poe_budget_watts"
    MS_POE_NETWORK_TOTAL_ENERGY_JOULES = "meraki_ms_poe_network_total_energy_joules"

    # Port overview metrics (point-in-time snapshot gauges)
    MS_PORTS_ACTIVE = "meraki_ms_ports_active"
    MS_PORTS_INACTIVE = "meraki_ms_ports_inactive"
    MS_PORTS_BY_MEDIA = "meraki_ms_ports_by_media"
    MS_PORTS_BY_LINK_SPEED = "meraki_ms_ports_by_link_speed"

    # STP metrics
    MS_STP_PRIORITY = "meraki_ms_stp_priority"
    MS_PORT_STP_STATE = "meraki_ms_port_stp_state"

    # 802.1X / secure-port authentication (from securePort object in port status)
    MS_PORT_8021X_STATUS = "meraki_ms_port_8021x_status"
    MS_PORT_8021X_ACTIVE = "meraki_ms_port_8021x_active"

    # Power supply / power module status (org-wide powerModules endpoint)
    MS_POWER_SUPPLY_STATUS = "meraki_ms_power_supply_status"

    # Additional port metrics (usage emitted in bytes, decimal KB x1000)
    MS_PORT_USAGE_BYTES = "meraki_ms_port_usage_bytes"
    MS_PORT_CLIENT_COUNT = "meraki_ms_port_client_count"

    # Port error/warning metrics (from the errors/warnings arrays in port status).
    # These are presence-flag Gauges (always 1 when active), not Counters, so they
    # deliberately do NOT carry a `_total` suffix (reserved by Prometheus convention
    # for counters safe under rate()/increase()) - see bug-bash finding F-091.
    MS_PORT_ERROR_ACTIVE = "meraki_ms_port_error_active"
    MS_PORT_WARNING_ACTIVE = "meraki_ms_port_warning_active"

    # Packet metrics: windowed counts over a 5-minute window (reset each cycle),
    # hence `_count` rather than the Counter-reserved `_total` suffix (#531 D1)
    MS_PORT_PACKETS_COUNT = "meraki_ms_port_packets_count"
    MS_PORT_PACKETS_BROADCAST_COUNT = "meraki_ms_port_packets_broadcast_count"
    MS_PORT_PACKETS_MULTICAST_COUNT = "meraki_ms_port_packets_multicast_count"
    MS_PORT_PACKETS_CRCERRORS_COUNT = "meraki_ms_port_packets_crcerrors_count"
    MS_PORT_PACKETS_FRAGMENTS_COUNT = "meraki_ms_port_packets_fragments_count"
    MS_PORT_PACKETS_COLLISIONS_COUNT = "meraki_ms_port_packets_collisions_count"
    MS_PORT_PACKETS_TOPOLOGYCHANGES_COUNT = "meraki_ms_port_packets_topologychanges_count"

    # Stack metrics
    MS_STACK_MEMBER_STATUS = "meraki_ms_stack_member_status"
    MS_STACK_MEMBERS = "meraki_ms_stack_members"

    # Packet rate metrics (packets per second, averaged over the 5-minute window)
    MS_PORT_PACKETS_RATE = "meraki_ms_port_packets_rate"
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
    # Windowed count (30-minute window, resets each cycle) - not a Counter (#531)
    MR_CONNECTION_STATS_COUNT = "meraki_mr_connection_stats_count"

    # Power and port metrics
    MR_POWER_INFO = "meraki_mr_power_info"
    MR_POWER_AC_CONNECTED = "meraki_mr_power_ac_connected"
    MR_POWER_POE_CONNECTED = "meraki_mr_power_poe_connected"
    MR_PORT_POE_INFO = "meraki_mr_port_poe_info"
    MR_PORT_LINK_NEGOTIATION_INFO = "meraki_mr_port_link_negotiation_info"
    # Nominal link capacity - deliberately kept in Mbps (#531 D6 documented exception)
    MR_PORT_LINK_NEGOTIATION_SPEED_MBPS = "meraki_mr_port_link_negotiation_speed_mbps"

    # Aggregation metrics
    MR_AGGREGATION_SPEED_MBPS = "meraki_mr_aggregation_speed_mbps"
    MR_AGGREGATION_ENABLED = "meraki_mr_aggregation_enabled"

    # Packet loss metrics - Device level (windowed 5-minute counts, `_count` per #531 D1)
    MR_PACKETS_DOWNSTREAM_COUNT = "meraki_mr_packets_downstream_count"
    MR_PACKETS_DOWNSTREAM_LOST_COUNT = "meraki_mr_packets_downstream_lost_count"
    MR_PACKET_LOSS_DOWNSTREAM_PERCENT = "meraki_mr_packet_loss_downstream_percent"
    MR_PACKETS_UPSTREAM_COUNT = "meraki_mr_packets_upstream_count"
    MR_PACKETS_UPSTREAM_LOST_COUNT = "meraki_mr_packets_upstream_lost_count"
    MR_PACKET_LOSS_UPSTREAM_PERCENT = "meraki_mr_packet_loss_upstream_percent"
    MR_PACKETS_COUNT = "meraki_mr_packets_count"
    MR_PACKETS_LOST_COUNT = "meraki_mr_packets_lost_count"
    MR_PACKET_LOSS_TOTAL_PERCENT = "meraki_mr_packet_loss_total_percent"

    # Packet loss metrics - Network level (windowed 5-minute counts)
    MR_NETWORK_PACKETS_DOWNSTREAM_COUNT = "meraki_mr_network_packets_downstream_count"
    MR_NETWORK_PACKETS_DOWNSTREAM_LOST_COUNT = "meraki_mr_network_packets_downstream_lost_count"
    MR_NETWORK_PACKET_LOSS_DOWNSTREAM_PERCENT = "meraki_mr_network_packet_loss_downstream_percent"
    MR_NETWORK_PACKETS_UPSTREAM_COUNT = "meraki_mr_network_packets_upstream_count"
    MR_NETWORK_PACKETS_UPSTREAM_LOST_COUNT = "meraki_mr_network_packets_upstream_lost_count"
    MR_NETWORK_PACKET_LOSS_UPSTREAM_PERCENT = "meraki_mr_network_packet_loss_upstream_percent"
    MR_NETWORK_PACKETS_COUNT = "meraki_mr_network_packets_count"
    MR_NETWORK_PACKETS_LOST_COUNT = "meraki_mr_network_packets_lost_count"
    MR_NETWORK_PACKET_LOSS_TOTAL_PERCENT = "meraki_mr_network_packet_loss_total_percent"

    # Other metrics
    MR_CPU_LOAD_5MIN = "meraki_mr_cpu_load_5min"
    MR_RADIO_BROADCASTING = "meraki_mr_radio_broadcasting"
    MR_RADIO_CHANNEL = "meraki_mr_radio_channel"
    MR_RADIO_CHANNEL_WIDTH_MHZ = "meraki_mr_radio_channel_width_mhz"
    MR_RADIO_POWER_DBM = "meraki_mr_radio_power_dbm"

    # SSID usage metrics (values emitted in bytes, decimal MB x1_000_000)
    MR_SSID_USAGE_TOTAL_BYTES = "meraki_mr_ssid_usage_total_bytes"
    MR_SSID_USAGE_DOWNSTREAM_BYTES = "meraki_mr_ssid_usage_downstream_bytes"
    MR_SSID_USAGE_UPSTREAM_BYTES = "meraki_mr_ssid_usage_upstream_bytes"
    MR_SSID_USAGE_PERCENT = "meraki_mr_ssid_usage_percent"
    MR_SSID_CLIENT_COUNT = "meraki_mr_ssid_client_count"


class MXMetricName(StrEnum):
    """MX (Security Appliance) specific metric names."""

    MX_UPLINK_INFO = "meraki_mx_uplink_info"

    # Per-uplink WAN-link quality (org-wide uplinksLossAndLatency endpoint)
    MX_UPLINK_LOSS_PERCENT = "meraki_mx_uplink_loss_percent"
    # Latency emitted in seconds (API milliseconds / 1000)
    MX_UPLINK_LATENCY_SECONDS = "meraki_mx_uplink_latency_seconds"

    # VPN health metrics
    MX_VPN_PEER_STATUS = "meraki_mx_vpn_peer_status"
    MX_VPN_PEERS = "meraki_mx_vpn_peers"

    # Firewall metrics
    MX_FIREWALL_RULES = "meraki_mx_firewall_rules"
    MX_FIREWALL_DEFAULT_POLICY = "meraki_mx_firewall_default_policy"
    # Windowed event count (resets each collection cycle), not a monotonic
    # Counter, so it deliberately does NOT carry a `_total` suffix - see
    # bug-bash finding F-091.
    MX_SECURITY_EVENTS_COUNT = "meraki_mx_security_events_count"

    # Per-uplink WAN bandwidth usage (org-wide uplinks usage byNetwork endpoint; windowed totals)
    MX_UPLINK_SENT_BYTES = "meraki_mx_uplink_sent_bytes"
    MX_UPLINK_RECV_BYTES = "meraki_mx_uplink_recv_bytes"

    # Appliance performance score (per-device getDeviceAppliancePerformance; 0-100)
    MX_PERFORMANCE_SCORE = "meraki_mx_performance_score"

    # HA / warm-spare redundancy (org-wide devices redundancy byNetwork endpoint)
    MX_HA_ENABLED = "meraki_mx_ha_enabled"
    MX_HA_MODE = "meraki_mx_ha_mode"
    MX_HA_ROLE = "meraki_mx_ha_role"

    # VPN history stats (org-wide vpn/stats endpoint; complements point-in-time vpn statuses)
    # Usage emitted in bytes (decimal KB x1000); latency in seconds (ms / 1000)
    MX_VPN_USAGE_SENT_BYTES = "meraki_mx_vpn_usage_sent_bytes"
    MX_VPN_USAGE_RECV_BYTES = "meraki_mx_vpn_usage_recv_bytes"
    MX_VPN_STATS_AVG_LATENCY_SECONDS = "meraki_mx_vpn_stats_avg_latency_seconds"


class MGMetricName(StrEnum):
    """MG (Cellular Gateway) specific metric names."""

    # Per-uplink cellular status (org-wide cellularGateway uplink statuses endpoint)
    MG_UPLINK_STATUS_INFO = "meraki_mg_uplink_status_info"
    MG_UPLINK_SIGNAL_RSRP_DBM = "meraki_mg_uplink_signal_rsrp_dbm"
    MG_UPLINK_SIGNAL_RSRQ_DB = "meraki_mg_uplink_signal_rsrq_db"
    MG_UPLINK_ROAMING = "meraki_mg_uplink_roaming"


class MVMetricName(StrEnum):
    """MV (Camera) specific metric names."""

    MV_ANALYTICS_ZONES = "meraki_mv_analytics_zones"
    MV_PEOPLE_COUNT = "meraki_mv_people_count"
    # id-keyed join carrier: maps serial+zone_id -> zone_name (issue #534, Option B)
    MV_ZONE_INFO = "meraki_mv_zone_info"

    # Quality & retention config (info + boolean gauges)
    MV_MOTION_BASED_RETENTION_ENABLED = "meraki_mv_motion_based_retention_enabled"
    MV_AUDIO_RECORDING_ENABLED = "meraki_mv_audio_recording_enabled"
    MV_RESTRICTED_BANDWIDTH_MODE_ENABLED = "meraki_mv_restricted_bandwidth_mode_enabled"
    MV_QUALITY_RETENTION_INFO = "meraki_mv_quality_retention_info"


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
    MT_NO2_PPB = "meraki_mt_no2_ppb"
    MT_O3_PPB = "meraki_mt_o3_ppb"
    MT_PM10_UG_M3 = "meraki_mt_pm10_ug_m3"
    MT_NOISE_DB = "meraki_mt_noise_db"
    MT_INDOOR_AIR_QUALITY_SCORE = "meraki_mt_indoor_air_quality_score"

    # Power metrics
    MT_BATTERY_PERCENT = "meraki_mt_battery_percent"
    MT_VOLTAGE_VOLTS = "meraki_mt_voltage_volts"
    MT_CURRENT_AMPS = "meraki_mt_current_amps"
    MT_REAL_POWER_WATTS = "meraki_mt_real_power_watts"
    MT_APPARENT_POWER_VA = "meraki_mt_apparent_power_va"
    MT_POWER_FACTOR_PERCENT = "meraki_mt_power_factor_percent"
    MT_FREQUENCY_HZ = "meraki_mt_frequency_hz"
    MT_DOWNSTREAM_POWER_ENABLED = "meraki_mt_downstream_power_enabled"
    MT_REMOTE_LOCKOUT_STATUS = "meraki_mt_remote_lockout_status"

    # Network-wide currently-alerting sensors (getNetworkSensorAlertsCurrentOverviewByMetric)
    MT_ALERTING_SENSORS_COUNT = "meraki_mt_alerting_sensors_count"

    # Sensor-to-gateway connectivity (getOrganizationSensorGatewaysConnectionsLatest)
    MT_GATEWAY_RSSI = "meraki_mt_gateway_rssi"
    MT_GATEWAY_LAST_CONNECTED_TIMESTAMP = "meraki_mt_gateway_last_connected_timestamp_seconds"


class AlertMetricName(StrEnum):
    """Alert metric names."""

    ALERTS_ACTIVE = "meraki_alerts_active"
    # Point-in-time snapshot gauges of active alerts (#531 D2)
    ALERTS_BY_SEVERITY = "meraki_alerts_by_severity"
    ALERTS_BY_NETWORK = "meraki_alerts_by_network"
    # Windowed count (resets each cycle) - not a Counter (#531 D1)
    SENSOR_ALERTS_COUNT = "meraki_sensor_alerts_count"

    # Health alert metrics (Phase 4.1)
    NETWORK_HEALTH_ALERTS = "meraki_network_health_alerts"


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

    # Data rate metrics (API kiloBYTES/s converted x1000 to bytes/s - see F-065)
    NETWORK_WIRELESS_DOWNLOAD_BYTES_PER_SECOND = "meraki_network_wireless_download_bytes_per_second"
    NETWORK_WIRELESS_UPLOAD_BYTES_PER_SECOND = "meraki_network_wireless_upload_bytes_per_second"

    # Bluetooth metrics (windowed 5-minute count, resets each cycle - #531 D1)
    NETWORK_BLUETOOTH_CLIENTS_COUNT = "meraki_network_bluetooth_clients_count"

    # Per-SSID performance metrics (Phase 4.4; windowed count)
    MR_SSID_FAILED_CONNECTIONS_COUNT = "meraki_mr_ssid_failed_connections_count"

    # Wireless latency stats (per-AP + network-aggregate client), by traffic class
    # Emitted in seconds (API milliseconds / 1000)
    MR_DEVICE_LATENCY_SECONDS = "meraki_mr_device_latency_seconds"
    MR_NETWORK_CLIENT_LATENCY_SECONDS = "meraki_mr_network_client_latency_seconds"

    # Air Marshal rogue AP / SSID-spoofing detection (network-level bounded counts,
    # windowed over 1 hour - #531 D1)
    MR_AIR_MARSHAL_SSIDS_COUNT = "meraki_mr_air_marshal_ssids_count"
    MR_AIR_MARSHAL_BSSIDS_COUNT = "meraki_mr_air_marshal_bssids_count"
    MR_AIR_MARSHAL_CONTAINED_BSSIDS_COUNT = "meraki_mr_air_marshal_contained_bssids_count"
    MR_AIR_MARSHAL_WIRED_DETECTED_COUNT = "meraki_mr_air_marshal_wired_detected_count"


class ClientMetricName(StrEnum):
    """Client-level metric names."""

    # Client status metrics
    CLIENT_STATUS = "meraki_client_status"

    # id-keyed join carrier (issue #533): the ONLY client metric allowed to carry
    # descriptive/PII-ish labels (mac/description/hostname/ssid). Numeric client
    # series are ID-only and join via
    # `<numeric> * on(client_id) group_left(mac, hostname, ...) meraki_client_info`.
    CLIENT_INFO = "meraki_client_info"

    # Client usage metrics (gauges for point-in-time hourly measurements;
    # values emitted in bytes, decimal KB x1000)
    CLIENT_USAGE_SENT_BYTES = "meraki_client_usage_sent_bytes"
    CLIENT_USAGE_RECV_BYTES = "meraki_client_usage_recv_bytes"
    CLIENT_USAGE_TOTAL_BYTES = "meraki_client_usage_total_bytes"

    # Wireless client capability metrics
    WIRELESS_CLIENT_CAPABILITIES_COUNT = "meraki_wireless_client_capabilities_count"

    # Client distribution metrics
    CLIENTS_PER_SSID_COUNT = "meraki_clients_per_ssid_count"
    CLIENTS_PER_VLAN_COUNT = "meraki_clients_per_vlan_count"

    # Client application usage metrics (values emitted in bytes, decimal KB x1000)
    CLIENT_APPLICATION_USAGE_SENT_BYTES = "meraki_client_application_usage_sent_bytes"
    CLIENT_APPLICATION_USAGE_RECV_BYTES = "meraki_client_application_usage_recv_bytes"
    CLIENT_APPLICATION_USAGE_TOTAL_BYTES = "meraki_client_application_usage_total_bytes"

    # Wireless client signal quality metrics
    WIRELESS_CLIENT_RSSI = "meraki_wireless_client_rssi"
    WIRELESS_CLIENT_SNR = "meraki_wireless_client_snr"


class CollectorMetricName(StrEnum):
    """Collector infrastructure metric names for monitoring exporter performance.

    Note: These metrics use the 'meraki_exporter_' prefix to distinguish them
    from Meraki network data metrics (which use 'meraki_' prefix).
    """

    # Build information (constant info-gauge, value 1; version/commit labels)
    BUILD_INFO = "meraki_exporter_build_info"

    # Parallel collection metrics
    PARALLEL_COLLECTIONS_ACTIVE = "meraki_exporter_collections_active"
    COLLECTION_ERRORS_TOTAL = "meraki_exporter_collection_errors_total"

    # Inventory cache metrics
    INVENTORY_CACHE_ENTRIES = "meraki_exporter_inventory_cache_size"

    # API client metrics
    API_REQUESTS_TOTAL = "meraki_exporter_api_requests_total"
    API_RETRY_ATTEMPTS_TOTAL = "meraki_exporter_api_retry_total"
    API_RATE_LIMITER_WAIT_SECONDS = "meraki_exporter_api_rate_limiter_wait_seconds"
    API_RATE_LIMITER_THROTTLED_TOTAL = "meraki_exporter_api_rate_limiter_throttled_total"
    API_RATE_LIMITER_TOKENS = "meraki_exporter_api_rate_limiter_tokens"
    COLLECTOR_START_OFFSET_SECONDS = "meraki_exporter_collector_start_offset_seconds"
    COLLECTION_SMOOTHING_WINDOW_SECONDS = "meraki_exporter_collection_smoothing_window_seconds"

    # Per-org health metrics
    EXPORTER_ORG_COLLECTION_STATUS = "meraki_exporter_org_collection_status"

    # Cardinality control metrics
    # Counter, labelled by metric family: increments each cleanup cycle a family
    # exceeds cardinality.max_series_per_family (#540). Replaces the pre-v1
    # per-collector shedding gauge `meraki_exporter_cardinality_limit_reached`
    # (same base name — a registered gauge would collide with this counter).
    EXPORTER_CARDINALITY_LIMIT_REACHED_TOTAL = "meraki_exporter_cardinality_limit_reached_total"
    # Gauge (per-cycle snapshot, not a monotonic counter) — must not end in `_total`.
    CARDINALITY_ANALYZED_METRICS = "meraki_exporter_cardinality_analyzed_metrics"

    # Clients dropped from metric emission by the per-network/global client cap
    # (#533). Per-cycle snapshot gauge (0 = within caps), not a Counter.
    CLIENTS_OVER_CAP = "meraki_exporter_clients_over_cap"

    # DNS resolver + client-store instrumentation (#319). Exporter self-metrics
    # (`meraki_exporter_client_*`), owned/emitted by
    # ClientsCollector._update_cache_metrics. Global singletons -- no labels.
    # DNS_CACHE_TOTAL / CLIENT_STORE_TOTAL are pre-1.0 Gauges carrying a legacy
    # `_total` name (kept as-is; renaming them is a separate breaking change).
    CLIENT_DNS_CACHE_TOTAL = "meraki_exporter_client_dns_cache_total"
    CLIENT_DNS_CACHE_VALID = "meraki_exporter_client_dns_cache_valid"
    CLIENT_DNS_CACHE_EXPIRED = "meraki_exporter_client_dns_cache_expired"
    CLIENT_DNS_CACHE_HIT_RATIO = "meraki_exporter_client_dns_cache_hit_ratio"
    CLIENT_DNS_LOOKUPS_TOTAL = "meraki_exporter_client_dns_lookups_total"
    CLIENT_DNS_LOOKUPS_SUCCESSFUL_TOTAL = "meraki_exporter_client_dns_lookups_successful_total"
    CLIENT_DNS_LOOKUPS_FAILED_TOTAL = "meraki_exporter_client_dns_lookups_failed_total"
    CLIENT_DNS_LOOKUPS_CACHED_TOTAL = "meraki_exporter_client_dns_lookups_cached_total"
    CLIENT_DNS_RESOLUTION_SECONDS_TOTAL = "meraki_exporter_client_dns_resolution_seconds_total"
    CLIENT_STORE_TOTAL = "meraki_exporter_client_store_total"
    CLIENT_STORE_NETWORKS = "meraki_exporter_client_store_networks"

    # Collection utilization metrics
    EXPORTER_COLLECTION_UTILIZATION_RATIO = "meraki_exporter_collection_utilization_ratio"

    # Exporter process self-resource metrics (#277). Gauges sampled from
    # psutil.Process() by a lightweight periodic task in app.py lifespan.
    EXPORTER_MEMORY_USAGE_BYTES = "meraki_exporter_memory_usage_bytes"
    EXPORTER_CPU_USAGE_PERCENT = "meraki_exporter_cpu_usage_percent"

    # Metric expiration metrics (core/metric_expiration.py) — #532/MET-06
    EXPIRED_METRICS_TOTAL = "meraki_exporter_collection_errors_expired_total"
    EXPIRATION_TRACKED_METRICS = "meraki_exporter_expiration_tracked_metrics"

    # Per-collector performance metrics (owned by core/collector.py's
    # MetricCollector._initialize_performance_metrics and collectors/manager.py).
    COLLECTOR_DURATION_SECONDS = "meraki_exporter_collector_duration_seconds"
    COLLECTOR_ERRORS_TOTAL = "meraki_exporter_collector_errors_total"
    COLLECTOR_SUCCESS_TIMESTAMP_SECONDS = "meraki_exporter_collector_success_timestamp_seconds"
    COLLECTOR_API_CALLS_TOTAL = "meraki_exporter_collector_api_calls_total"
    COLLECTOR_FAILURE_STREAK = "meraki_exporter_collector_failure_streak"


class WebhookMetricName(StrEnum):
    """Webhook receiver metric names for monitoring webhook events (Phase 4.2)."""

    # Event processing metrics
    WEBHOOK_EVENTS_RECEIVED_TOTAL = "meraki_webhook_events_received_total"
    WEBHOOK_EVENTS_PROCESSED_TOTAL = "meraki_webhook_events_processed_total"
    WEBHOOK_EVENTS_FAILED_TOTAL = "meraki_webhook_events_failed_total"

    # Processing latency
    WEBHOOK_PROCESSING_DURATION_SECONDS = "meraki_webhook_processing_duration_seconds"

    # Validation metrics
    WEBHOOK_VALIDATION_FAILURES_TOTAL = "meraki_webhook_validation_failures_total"
