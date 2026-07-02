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

    # Admin accounts & 2FA/SSO posture (getOrganizationAdmins; aggregated, no per-admin PII)
    ORG_ADMINS_TOTAL = "meraki_org_admins_total"
    ORG_ADMINS_TWO_FACTOR_ENABLED_TOTAL = "meraki_org_admins_two_factor_enabled_total"

    # Firmware upgrade status & staged rollout tracking (getOrganizationFirmwareUpgrades)
    ORG_FIRMWARE_UPGRADES_TOTAL = "meraki_org_firmware_upgrades_total"
    ORG_FIRMWARE_UPGRADES_PENDING_TOTAL = "meraki_org_firmware_upgrades_pending_total"

    # Device availability change history (getOrganizationDevicesAvailabilitiesChangeHistory)
    ORG_DEVICES_AVAILABILITY_CHANGES_TOTAL = "meraki_org_devices_availability_changes_total"


class NetworkMetricName(StrEnum):
    """Network-level metric names."""

    NETWORK_CLIENTS_TOTAL = "meraki_network_clients_total"
    NETWORK_TRAFFIC_BYTES = "meraki_network_traffic_bytes"
    NETWORK_DEVICE_STATUS = "meraki_network_device_status"
    NETWORK_WIRELESS_CONNECTION_STATS = "meraki_network_wireless_connection_stats_total"
    # Network-filter observability (emitted by services/inventory.py)
    NETWORK_FILTER_MATCH = "meraki_network_filter_match"
    NETWORK_FILTER_RESOLVED = "meraki_network_filter_resolved"
    NETWORK_FILTER_TOTAL = "meraki_network_filter_total"


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
    MS_POE_PORT_POWER_WATTHOURS = "meraki_ms_poe_port_power_watthours"
    MS_POE_TOTAL_POWER_WATTHOURS = "meraki_ms_poe_total_power_watthours"
    MS_POE_BUDGET_WATTS = "meraki_ms_poe_budget_watts"
    MS_POE_NETWORK_TOTAL_WATTHOURS = "meraki_ms_poe_network_total_watthours"

    # Port overview metrics
    MS_PORTS_ACTIVE_TOTAL = "meraki_ms_ports_active_total"
    MS_PORTS_INACTIVE_TOTAL = "meraki_ms_ports_inactive_total"
    MS_PORTS_BY_MEDIA_TOTAL = "meraki_ms_ports_by_media_total"
    MS_PORTS_BY_LINK_SPEED_TOTAL = "meraki_ms_ports_by_link_speed_total"

    # STP metrics
    MS_STP_PRIORITY = "meraki_ms_stp_priority"
    MS_PORT_STP_STATE = "meraki_ms_port_stp_state"

    # 802.1X / secure-port authentication (from securePort object in port status)
    MS_PORT_8021X_STATUS = "meraki_ms_port_8021x_status"
    MS_PORT_8021X_ACTIVE = "meraki_ms_port_8021x_active"

    # Power supply / power module status (org-wide powerModules endpoint)
    MS_POWER_SUPPLY_STATUS = "meraki_ms_power_supply_status"

    # Additional port metrics
    MS_PORT_USAGE_BYTES = "meraki_ms_port_usage_bytes"
    MS_PORT_CLIENT_COUNT = "meraki_ms_port_client_count"

    # Port error/warning metrics (from the errors/warnings arrays in port status).
    # These are presence-flag Gauges (always 1 when active), not Counters, so they
    # deliberately do NOT carry a `_total` suffix (reserved by Prometheus convention
    # for counters safe under rate()/increase()) - see bug-bash finding F-091.
    MS_PORT_ERROR_ACTIVE = "meraki_ms_port_error_active"
    MS_PORT_WARNING_ACTIVE = "meraki_ms_port_warning_active"

    # Packet metrics (with 5-minute window)
    MS_PORT_PACKETS_TOTAL = "meraki_ms_port_packets_total"
    MS_PORT_PACKETS_BROADCAST = "meraki_ms_port_packets_broadcast"
    MS_PORT_PACKETS_MULTICAST = "meraki_ms_port_packets_multicast"
    MS_PORT_PACKETS_CRCERRORS = "meraki_ms_port_packets_crcerrors"
    MS_PORT_PACKETS_FRAGMENTS = "meraki_ms_port_packets_fragments"
    MS_PORT_PACKETS_COLLISIONS = "meraki_ms_port_packets_collisions"
    MS_PORT_PACKETS_TOPOLOGYCHANGES = "meraki_ms_port_packets_topologychanges"

    # Stack metrics
    MS_STACK_MEMBER_STATUS = "meraki_ms_stack_member_status"
    MS_STACK_MEMBERS_TOTAL = "meraki_ms_stack_members_total"

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
    MR_CONNECTION_STATS = "meraki_mr_connection_stats_total"

    # Power and port metrics
    MR_POWER_INFO = "meraki_mr_power_info"
    MR_POWER_AC_CONNECTED = "meraki_mr_power_ac_connected"
    MR_POWER_POE_CONNECTED = "meraki_mr_power_poe_connected"
    MR_PORT_POE_INFO = "meraki_mr_port_poe_info"
    MR_PORT_LINK_NEGOTIATION_INFO = "meraki_mr_port_link_negotiation_info"
    MR_PORT_LINK_NEGOTIATION_SPEED_MBPS = "meraki_mr_port_link_negotiation_speed_mbps"

    # Aggregation metrics
    MR_AGGREGATION_SPEED_MBPS = "meraki_mr_aggregation_speed_mbps"
    MR_AGGREGATION_ENABLED = "meraki_mr_aggregation_enabled"

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


class MXMetricName(StrEnum):
    """MX (Security Appliance) specific metric names."""

    MX_UPLINK_INFO = "meraki_mx_uplink_info"

    # Per-uplink WAN-link quality (org-wide uplinksLossAndLatency endpoint)
    MX_UPLINK_LOSS_PERCENT = "meraki_mx_uplink_loss_percent"
    MX_UPLINK_LATENCY_MS = "meraki_mx_uplink_latency_ms"

    # VPN health metrics
    MX_VPN_PEER_STATUS = "meraki_mx_vpn_peer_status"
    MX_VPN_PEERS_TOTAL = "meraki_mx_vpn_peers_total"

    # Firewall metrics
    MX_FIREWALL_RULES_TOTAL = "meraki_mx_firewall_rules_total"
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
    MX_VPN_USAGE_SENT_KB = "meraki_mx_vpn_usage_sent_kb"
    MX_VPN_USAGE_RECV_KB = "meraki_mx_vpn_usage_recv_kb"
    MX_VPN_STATS_AVG_LATENCY_MS = "meraki_mx_vpn_stats_avg_latency_ms"


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
    MT_BATTERY_PERCENTAGE = "meraki_mt_battery_percentage"
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
    ALERTS_TOTAL_BY_SEVERITY = "meraki_alerts_total_by_severity"
    ALERTS_TOTAL_BY_NETWORK = "meraki_alerts_total_by_network"
    SENSOR_ALERTS_TOTAL = "meraki_sensor_alerts_total"

    # Health alert metrics (Phase 4.1)
    ORGANIZATION_HEALTH_ALERTS_TOTAL = "meraki_organization_health_alerts_total"
    NETWORK_HEALTH_ALERTS_TOTAL = "meraki_network_health_alerts_total"
    HEALTH_ALERT_INFO = "meraki_health_alert_info"


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

    # Per-SSID performance metrics (Phase 4.4)
    MR_SSID_FAILED_CONNECTIONS_TOTAL = "meraki_mr_ssid_failed_connections_total"

    # Wireless latency stats (per-AP + network-aggregate client), by traffic class
    MR_DEVICE_LATENCY_MS = "meraki_mr_device_latency_ms"
    MR_NETWORK_CLIENT_LATENCY_MS = "meraki_mr_network_client_latency_ms"

    # Air Marshal rogue AP / SSID-spoofing detection (network-level bounded counts)
    MR_AIR_MARSHAL_SSIDS_TOTAL = "meraki_mr_air_marshal_ssids_total"
    MR_AIR_MARSHAL_BSSIDS_TOTAL = "meraki_mr_air_marshal_bssids_total"
    MR_AIR_MARSHAL_CONTAINED_BSSIDS_TOTAL = "meraki_mr_air_marshal_contained_bssids_total"
    MR_AIR_MARSHAL_WIRED_DETECTED_TOTAL = "meraki_mr_air_marshal_wired_detected_total"


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


class CollectorMetricName(StrEnum):
    """Collector infrastructure metric names for monitoring exporter performance.

    Note: These metrics use the 'meraki_exporter_' prefix to distinguish them
    from Meraki network data metrics (which use 'meraki_' prefix).
    """

    # Parallel collection metrics
    PARALLEL_COLLECTIONS_ACTIVE = "meraki_exporter_collections_active"
    COLLECTION_ERRORS_TOTAL = "meraki_exporter_collection_errors_total"

    # Inventory cache metrics
    # NB: INVENTORY_CACHE_SIZE is consumed by core/metric_expiration.py to build the
    # separate "meraki_exporter_cache_size_tracked_metrics" gauge — it does NOT name the
    # inventory cache-size gauge. The actual inventory cache-size gauge uses
    # INVENTORY_CACHE_ENTRIES below (F-080). The former hit/miss counter enums were
    # declared but never registered as Counters and have been removed.
    INVENTORY_CACHE_SIZE = "meraki_exporter_cache_size"
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
    EXPORTER_CARDINALITY_LIMIT_REACHED = "meraki_exporter_cardinality_limit_reached"

    # Collection utilization metrics
    EXPORTER_COLLECTION_UTILIZATION_RATIO = "meraki_exporter_collection_utilization_ratio"

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

    # Metric sink metrics (Phase 4.5) - event-driven, not polled
    WEBHOOK_EVENTS_TOTAL = "meraki_webhook_events_total"
    WEBHOOK_LAST_EVENT_TIMESTAMP = "meraki_webhook_last_event_timestamp"
    WEBHOOK_PROCESSING_ERRORS_TOTAL = "meraki_webhook_processing_errors_total"
