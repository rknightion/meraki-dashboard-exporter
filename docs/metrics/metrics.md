# Metrics Reference

This page provides a comprehensive reference of all Prometheus metrics exposed by the Meraki Dashboard Exporter.

!!! summary "Metrics Summary"
    📊 **Total Metrics:** 157
    🏗️ **Collectors:** 11
    📈 **Gauges:** 152
    📊 **Counters:** 4
    ℹ️ **Info Metrics:** 1

## Overview

The exporter provides metrics across several categories:

| Collector | Metrics | Description |
|-----------|---------|-------------|
| [AlertsCollector](#alerts) | 5 | 🚨 Active alerts by severity, type, and category |
| [ClientsCollector](#clients) | 21 | 👥 Detailed client-level metrics including usage and status |
| [ConfigCollector](#config) | 14 | ⚙️ Organization security settings and configuration tracking |
| [DeviceCollector](#device) | 10 | 📱 Device status, performance, and uptime metrics |
| [MRClientsCollector](#mrclients) | 2 | Various metrics |
| [MRPerformanceCollector](#mrperformance) | 27 | Various metrics |
| [MRWirelessCollector](#mrwireless) | 9 | Various metrics |
| [MSCollector](#ms) | 24 | 🔀 Switch-specific metrics including port status, power, and PoE |
| [MTSensorCollector](#mtsensor) | 18 | 📊 Environmental monitoring from MT sensors |
| [NetworkHealthCollector](#networkhealth) | 8 | 🏥 Network-wide wireless health and performance |
| [OrganizationCollector](#organization) | 19 | 🏢 Organization-level metrics including API usage and licenses |

## 🧭 Quick Navigation

### By Metric Type

??? abstract "📊 **Counters** - Cumulative values that only increase (4 metrics)"

    <div class="grid cards" markdown>

    - [`meraki_exporter_client_dns_lookups_cached_total`](#meraki-exporter-client-dns-lookups-cached-total)
      ---
      ClientsCollector

    - [`meraki_exporter_client_dns_lookups_failed_total`](#meraki-exporter-client-dns-lookups-failed-total)
      ---
      ClientsCollector

    - [`meraki_exporter_client_dns_lookups_successful_total`](#meraki-exporter-client-dns-lookups-successful-total)
      ---
      ClientsCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_exporter_client_dns_lookups_total`](#meraki-exporter-client-dns-lookups-total)
      ---
      ClientsCollector

    </div>

??? abstract "📈 **Gauges** - Values that can increase or decrease (current state) (152 metrics)"

    <div class="grid cards" markdown>

    - [`OrgMetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ATTEMPTS`](#orgmetricname-org-login-security-account-lockout-attempts)
      ---
      ConfigCollector

    - [`OrgMetricName.ORG_LOGIN_SECURITY_API_IP_RESTRICTIONS_ENABLED`](#orgmetricname-org-login-security-api-ip-restrictions-enabled)
      ---
      ConfigCollector

    - [`OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_COUNT`](#orgmetricname-org-login-security-different-passwords-count)
      ---
      ConfigCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_ENABLED`](#orgmetricname-org-login-security-different-passwords-enabled)
      ---
      ConfigCollector

    - [`OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_DAYS`](#orgmetricname-org-login-security-password-expiration-days)
      ---
      ConfigCollector

    - [`OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_ENABLED`](#orgmetricname-org-login-security-password-expiration-enabled)
      ---
      ConfigCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`OrgMetricName.ORG_LOGIN_SECURITY_STRONG_PASSWORDS_ENABLED`](#orgmetricname-org-login-security-strong-passwords-enabled)
      ---
      ConfigCollector

    - [`meraki_alerts_active`](#meraki-alerts-active)
      ---
      AlertsCollector

    - [`meraki_alerts_total_by_network`](#meraki-alerts-total-by-network)
      ---
      AlertsCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_alerts_total_by_severity`](#meraki-alerts-total-by-severity)
      ---
      AlertsCollector

    - [`meraki_ap_channel_utilization_2_4ghz_percent`](#meraki-ap-channel-utilization-2-4ghz-percent)
      ---
      NetworkHealthCollector

    - [`meraki_ap_channel_utilization_5ghz_percent`](#meraki-ap-channel-utilization-5ghz-percent)
      ---
      NetworkHealthCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_client_application_usage_recv_kb`](#meraki-client-application-usage-recv-kb)
      ---
      ClientsCollector

    - [`meraki_client_application_usage_sent_kb`](#meraki-client-application-usage-sent-kb)
      ---
      ClientsCollector

    - [`meraki_client_application_usage_total_kb`](#meraki-client-application-usage-total-kb)
      ---
      ClientsCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_client_status`](#meraki-client-status)
      ---
      ClientsCollector

    - [`meraki_client_usage_recv_kb`](#meraki-client-usage-recv-kb)
      ---
      ClientsCollector

    - [`meraki_client_usage_sent_kb`](#meraki-client-usage-sent-kb)
      ---
      ClientsCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_client_usage_total_kb`](#meraki-client-usage-total-kb)
      ---
      ClientsCollector

    - [`meraki_clients_per_ssid_count`](#meraki-clients-per-ssid-count)
      ---
      ClientsCollector

    - [`meraki_clients_per_vlan_count`](#meraki-clients-per-vlan-count)
      ---
      ClientsCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_device_memory_free_bytes`](#meraki-device-memory-free-bytes)
      ---
      DeviceCollector

    - [`meraki_device_memory_total_bytes`](#meraki-device-memory-total-bytes)
      ---
      DeviceCollector

    - [`meraki_device_memory_usage_percent`](#meraki-device-memory-usage-percent)
      ---
      DeviceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_device_memory_used_bytes`](#meraki-device-memory-used-bytes)
      ---
      DeviceCollector

    - [`meraki_device_status_info`](#meraki-device-status-info)
      ---
      DeviceCollector

    - [`meraki_device_up`](#meraki-device-up)
      ---
      DeviceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_exporter_client_dns_cache_expired`](#meraki-exporter-client-dns-cache-expired)
      ---
      ClientsCollector

    - [`meraki_exporter_client_dns_cache_total`](#meraki-exporter-client-dns-cache-total)
      ---
      ClientsCollector

    - [`meraki_exporter_client_dns_cache_valid`](#meraki-exporter-client-dns-cache-valid)
      ---
      ClientsCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_exporter_client_store_networks`](#meraki-exporter-client-store-networks)
      ---
      ClientsCollector

    - [`meraki_exporter_client_store_total`](#meraki-exporter-client-store-total)
      ---
      ClientsCollector

    - [`meraki_mr_aggregation_enabled`](#meraki-mr-aggregation-enabled)
      ---
      MRPerformanceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_aggregation_speed_mbps`](#meraki-mr-aggregation-speed-mbps)
      ---
      MRPerformanceCollector

    - [`meraki_mr_clients_connected`](#meraki-mr-clients-connected)
      ---
      MRClientsCollector

    - [`meraki_mr_connection_stats_total`](#meraki-mr-connection-stats-total)
      ---
      MRClientsCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_cpu_load_5min`](#meraki-mr-cpu-load-5min)
      ---
      MRPerformanceCollector

    - [`meraki_mr_network_packet_loss_downstream_percent`](#meraki-mr-network-packet-loss-downstream-percent)
      ---
      MRPerformanceCollector

    - [`meraki_mr_network_packet_loss_total_percent`](#meraki-mr-network-packet-loss-total-percent)
      ---
      MRPerformanceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_network_packet_loss_upstream_percent`](#meraki-mr-network-packet-loss-upstream-percent)
      ---
      MRPerformanceCollector

    - [`meraki_mr_network_packets_downstream_lost`](#meraki-mr-network-packets-downstream-lost)
      ---
      MRPerformanceCollector

    - [`meraki_mr_network_packets_downstream_total`](#meraki-mr-network-packets-downstream-total)
      ---
      MRPerformanceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_network_packets_lost_total`](#meraki-mr-network-packets-lost-total)
      ---
      MRPerformanceCollector

    - [`meraki_mr_network_packets_total`](#meraki-mr-network-packets-total)
      ---
      MRPerformanceCollector

    - [`meraki_mr_network_packets_upstream_lost`](#meraki-mr-network-packets-upstream-lost)
      ---
      MRPerformanceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_network_packets_upstream_total`](#meraki-mr-network-packets-upstream-total)
      ---
      MRPerformanceCollector

    - [`meraki_mr_packet_loss_downstream_percent`](#meraki-mr-packet-loss-downstream-percent)
      ---
      MRPerformanceCollector

    - [`meraki_mr_packet_loss_total_percent`](#meraki-mr-packet-loss-total-percent)
      ---
      MRPerformanceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_packet_loss_upstream_percent`](#meraki-mr-packet-loss-upstream-percent)
      ---
      MRPerformanceCollector

    - [`meraki_mr_packets_downstream_lost`](#meraki-mr-packets-downstream-lost)
      ---
      MRPerformanceCollector

    - [`meraki_mr_packets_downstream_total`](#meraki-mr-packets-downstream-total)
      ---
      MRPerformanceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_packets_lost_total`](#meraki-mr-packets-lost-total)
      ---
      MRPerformanceCollector

    - [`meraki_mr_packets_total`](#meraki-mr-packets-total)
      ---
      MRPerformanceCollector

    - [`meraki_mr_packets_upstream_lost`](#meraki-mr-packets-upstream-lost)
      ---
      MRPerformanceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_packets_upstream_total`](#meraki-mr-packets-upstream-total)
      ---
      MRPerformanceCollector

    - [`meraki_mr_port_link_negotiation_info`](#meraki-mr-port-link-negotiation-info)
      ---
      MRPerformanceCollector

    - [`meraki_mr_port_link_negotiation_speed_mbps`](#meraki-mr-port-link-negotiation-speed-mbps)
      ---
      MRPerformanceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_port_poe_info`](#meraki-mr-port-poe-info)
      ---
      MRPerformanceCollector

    - [`meraki_mr_power_ac_connected`](#meraki-mr-power-ac-connected)
      ---
      MRPerformanceCollector

    - [`meraki_mr_power_info`](#meraki-mr-power-info)
      ---
      MRPerformanceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_power_poe_connected`](#meraki-mr-power-poe-connected)
      ---
      MRPerformanceCollector

    - [`meraki_mr_radio_broadcasting`](#meraki-mr-radio-broadcasting)
      ---
      MRWirelessCollector

    - [`meraki_mr_radio_channel`](#meraki-mr-radio-channel)
      ---
      MRWirelessCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_radio_channel_width_mhz`](#meraki-mr-radio-channel-width-mhz)
      ---
      MRWirelessCollector

    - [`meraki_mr_radio_power_dbm`](#meraki-mr-radio-power-dbm)
      ---
      MRWirelessCollector

    - [`meraki_mr_ssid_client_count`](#meraki-mr-ssid-client-count)
      ---
      MRWirelessCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_ssid_usage_downstream_mb`](#meraki-mr-ssid-usage-downstream-mb)
      ---
      MRWirelessCollector

    - [`meraki_mr_ssid_usage_percentage`](#meraki-mr-ssid-usage-percentage)
      ---
      MRWirelessCollector

    - [`meraki_mr_ssid_usage_total_mb`](#meraki-mr-ssid-usage-total-mb)
      ---
      MRWirelessCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mr_ssid_usage_upstream_mb`](#meraki-mr-ssid-usage-upstream-mb)
      ---
      MRWirelessCollector

    - [`meraki_ms_poe_budget_watts`](#meraki-ms-poe-budget-watts)
      ---
      MSCollector

    - [`meraki_ms_poe_network_total_watthours`](#meraki-ms-poe-network-total-watthours)
      ---
      MSCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_ms_poe_port_power_watthours`](#meraki-ms-poe-port-power-watthours)
      ---
      MSCollector

    - [`meraki_ms_poe_total_power_watthours`](#meraki-ms-poe-total-power-watthours)
      ---
      MSCollector

    - [`meraki_ms_port_client_count`](#meraki-ms-port-client-count)
      ---
      MSCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_ms_port_packets_broadcast`](#meraki-ms-port-packets-broadcast)
      ---
      MSCollector

    - [`meraki_ms_port_packets_collisions`](#meraki-ms-port-packets-collisions)
      ---
      MSCollector

    - [`meraki_ms_port_packets_crcerrors`](#meraki-ms-port-packets-crcerrors)
      ---
      MSCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_ms_port_packets_fragments`](#meraki-ms-port-packets-fragments)
      ---
      MSCollector

    - [`meraki_ms_port_packets_multicast`](#meraki-ms-port-packets-multicast)
      ---
      MSCollector

    - [`meraki_ms_port_packets_rate_broadcast`](#meraki-ms-port-packets-rate-broadcast)
      ---
      MSCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_ms_port_packets_rate_collisions`](#meraki-ms-port-packets-rate-collisions)
      ---
      MSCollector

    - [`meraki_ms_port_packets_rate_crcerrors`](#meraki-ms-port-packets-rate-crcerrors)
      ---
      MSCollector

    - [`meraki_ms_port_packets_rate_fragments`](#meraki-ms-port-packets-rate-fragments)
      ---
      MSCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_ms_port_packets_rate_multicast`](#meraki-ms-port-packets-rate-multicast)
      ---
      MSCollector

    - [`meraki_ms_port_packets_rate_topologychanges`](#meraki-ms-port-packets-rate-topologychanges)
      ---
      MSCollector

    - [`meraki_ms_port_packets_rate_total`](#meraki-ms-port-packets-rate-total)
      ---
      MSCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_ms_port_packets_topologychanges`](#meraki-ms-port-packets-topologychanges)
      ---
      MSCollector

    - [`meraki_ms_port_packets_total`](#meraki-ms-port-packets-total)
      ---
      MSCollector

    - [`meraki_ms_port_status`](#meraki-ms-port-status)
      ---
      MSCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_ms_port_traffic_bytes`](#meraki-ms-port-traffic-bytes)
      ---
      MSCollector

    - [`meraki_ms_port_usage_bytes`](#meraki-ms-port-usage-bytes)
      ---
      MSCollector

    - [`meraki_ms_ports_active_total`](#meraki-ms-ports-active-total)
      ---
      DeviceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_ms_ports_by_link_speed_total`](#meraki-ms-ports-by-link-speed-total)
      ---
      DeviceCollector

    - [`meraki_ms_ports_by_media_total`](#meraki-ms-ports-by-media-total)
      ---
      DeviceCollector

    - [`meraki_ms_ports_inactive_total`](#meraki-ms-ports-inactive-total)
      ---
      DeviceCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_ms_power_usage_watts`](#meraki-ms-power-usage-watts)
      ---
      MSCollector

    - [`meraki_ms_stp_priority`](#meraki-ms-stp-priority)
      ---
      MSCollector

    - [`meraki_mt_apparent_power_va`](#meraki-mt-apparent-power-va)
      ---
      MTSensorCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mt_battery_percentage`](#meraki-mt-battery-percentage)
      ---
      MTSensorCollector

    - [`meraki_mt_co2_ppm`](#meraki-mt-co2-ppm)
      ---
      MTSensorCollector

    - [`meraki_mt_current_amps`](#meraki-mt-current-amps)
      ---
      MTSensorCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mt_door_status`](#meraki-mt-door-status)
      ---
      MTSensorCollector

    - [`meraki_mt_downstream_power_enabled`](#meraki-mt-downstream-power-enabled)
      ---
      MTSensorCollector

    - [`meraki_mt_frequency_hz`](#meraki-mt-frequency-hz)
      ---
      MTSensorCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mt_humidity_percent`](#meraki-mt-humidity-percent)
      ---
      MTSensorCollector

    - [`meraki_mt_indoor_air_quality_score`](#meraki-mt-indoor-air-quality-score)
      ---
      MTSensorCollector

    - [`meraki_mt_noise_db`](#meraki-mt-noise-db)
      ---
      MTSensorCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mt_pm25_ug_m3`](#meraki-mt-pm25-ug-m3)
      ---
      MTSensorCollector

    - [`meraki_mt_power_factor_percent`](#meraki-mt-power-factor-percent)
      ---
      MTSensorCollector

    - [`meraki_mt_real_power_watts`](#meraki-mt-real-power-watts)
      ---
      MTSensorCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mt_remote_lockout_status`](#meraki-mt-remote-lockout-status)
      ---
      MTSensorCollector

    - [`meraki_mt_temperature_celsius`](#meraki-mt-temperature-celsius)
      ---
      MTSensorCollector

    - [`meraki_mt_tvoc_ppb`](#meraki-mt-tvoc-ppb)
      ---
      MTSensorCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_mt_voltage_volts`](#meraki-mt-voltage-volts)
      ---
      MTSensorCollector

    - [`meraki_mt_water_detected`](#meraki-mt-water-detected)
      ---
      MTSensorCollector

    - [`meraki_network_bluetooth_clients_total`](#meraki-network-bluetooth-clients-total)
      ---
      NetworkHealthCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_network_channel_utilization_2_4ghz_percent`](#meraki-network-channel-utilization-2-4ghz-percent)
      ---
      NetworkHealthCollector

    - [`meraki_network_channel_utilization_5ghz_percent`](#meraki-network-channel-utilization-5ghz-percent)
      ---
      NetworkHealthCollector

    - [`meraki_network_health_alerts_total`](#meraki-network-health-alerts-total)
      ---
      AlertsCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_network_wireless_connection_stats_total`](#meraki-network-wireless-connection-stats-total)
      ---
      NetworkHealthCollector

    - [`meraki_network_wireless_download_kbps`](#meraki-network-wireless-download-kbps)
      ---
      NetworkHealthCollector

    - [`meraki_network_wireless_upload_kbps`](#meraki-network-wireless-upload-kbps)
      ---
      NetworkHealthCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_org_api_requests_by_status`](#meraki-org-api-requests-by-status)
      ---
      OrganizationCollector

    - [`meraki_org_api_requests_total`](#meraki-org-api-requests-total)
      ---
      OrganizationCollector

    - [`meraki_org_application_usage_downstream_mb`](#meraki-org-application-usage-downstream-mb)
      ---
      OrganizationCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_org_application_usage_percentage`](#meraki-org-application-usage-percentage)
      ---
      OrganizationCollector

    - [`meraki_org_application_usage_total_mb`](#meraki-org-application-usage-total-mb)
      ---
      OrganizationCollector

    - [`meraki_org_application_usage_upstream_mb`](#meraki-org-application-usage-upstream-mb)
      ---
      OrganizationCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_org_clients_total`](#meraki-org-clients-total)
      ---
      OrganizationCollector

    - [`meraki_org_configuration_changes_total`](#meraki-org-configuration-changes-total)
      ---
      ConfigCollector

    - [`meraki_org_devices_availability_total`](#meraki-org-devices-availability-total)
      ---
      OrganizationCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_org_devices_by_model_total`](#meraki-org-devices-by-model-total)
      ---
      OrganizationCollector

    - [`meraki_org_devices_total`](#meraki-org-devices-total)
      ---
      OrganizationCollector

    - [`meraki_org_licenses_expiring`](#meraki-org-licenses-expiring)
      ---
      OrganizationCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_org_licenses_total`](#meraki-org-licenses-total)
      ---
      OrganizationCollector

    - [`meraki_org_login_security_account_lockout_enabled`](#meraki-org-login-security-account-lockout-enabled)
      ---
      ConfigCollector

    - [`meraki_org_login_security_idle_timeout_enabled`](#meraki-org-login-security-idle-timeout-enabled)
      ---
      ConfigCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_org_login_security_idle_timeout_minutes`](#meraki-org-login-security-idle-timeout-minutes)
      ---
      ConfigCollector

    - [`meraki_org_login_security_ip_ranges_enabled`](#meraki-org-login-security-ip-ranges-enabled)
      ---
      ConfigCollector

    - [`meraki_org_login_security_minimum_password_length`](#meraki-org-login-security-minimum-password-length)
      ---
      ConfigCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_org_login_security_two_factor_enabled`](#meraki-org-login-security-two-factor-enabled)
      ---
      ConfigCollector

    - [`meraki_org_networks_total`](#meraki-org-networks-total)
      ---
      OrganizationCollector

    - [`meraki_org_packetcaptures_remaining`](#meraki-org-packetcaptures-remaining)
      ---
      OrganizationCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_org_packetcaptures_total`](#meraki-org-packetcaptures-total)
      ---
      OrganizationCollector

    - [`meraki_org_usage_downstream_kb`](#meraki-org-usage-downstream-kb)
      ---
      OrganizationCollector

    - [`meraki_org_usage_total_kb`](#meraki-org-usage-total-kb)
      ---
      OrganizationCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_org_usage_upstream_kb`](#meraki-org-usage-upstream-kb)
      ---
      OrganizationCollector

    - [`meraki_sensor_alerts_total`](#meraki-sensor-alerts-total)
      ---
      AlertsCollector

    - [`meraki_wireless_client_capabilities_count`](#meraki-wireless-client-capabilities-count)
      ---
      ClientsCollector

    </div>
    
    <div class="grid cards" markdown>

    - [`meraki_wireless_client_rssi`](#meraki-wireless-client-rssi)
      ---
      ClientsCollector

    - [`meraki_wireless_client_snr`](#meraki-wireless-client-snr)
      ---
      ClientsCollector

    </div>

??? abstract "ℹ️ **Info Metrics** - Metadata and configuration information (1 metrics)"

    <div class="grid cards" markdown>

    - [`meraki_org`](#meraki-org)
      ---
      OrganizationCollector

    </div>

### By Collector

=== "Device & Infrastructure"

    - [DeviceCollector](#device) (10 metrics)
    - [MSCollector](#ms) (24 metrics)
    - [MTSensorCollector](#mtsensor) (18 metrics)

=== "Network & Health"

    - [NetworkHealthCollector](#networkhealth) (8 metrics)

=== "Organization & Management"

    - [AlertsCollector](#alerts) (5 metrics)
    - [ClientsCollector](#clients) (21 metrics)
    - [ConfigCollector](#config) (14 metrics)
    - [OrganizationCollector](#organization) (19 metrics)

## 📋 Metrics by Collector

### AlertsCollector { #alerts }

!!! info "Collector Information"
    **Description:** 🚨 Active alerts by severity, type, and category
    **Source File:** `src/meraki_dashboard_exporter/collectors/alerts.py`
    **Metrics Count:** 5

#### `meraki_alerts_active` { #meraki-alerts-active }

**Type:** 🔢 Gauge

**Description:** Number of active Meraki assurance alerts

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.ALERT_TYPE`
- `LabelName.CATEGORY_TYPE`
- `LabelName.SEVERITY`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `AlertMetricName.ALERTS_ACTIVE`

    **Variable:** `self._alerts_active`
    **Source Line:** 32

---

#### `meraki_alerts_total_by_network` { #meraki-alerts-total-by-network }

**Type:** 🔢 Gauge

**Description:** Total number of active alerts per network

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `AlertMetricName.ALERTS_TOTAL_BY_NETWORK`

    **Variable:** `self._alerts_by_network`
    **Source Line:** 55

---

#### `meraki_alerts_total_by_severity` { #meraki-alerts-total-by-severity }

**Type:** 🔢 Gauge

**Description:** Total number of active alerts by severity

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.SEVERITY`

??? example "Technical Details"

    **Constant:** `AlertMetricName.ALERTS_TOTAL_BY_SEVERITY`

    **Variable:** `self._alerts_by_severity`
    **Source Line:** 48

---

#### `meraki_network_health_alerts_total` { #meraki-network-health-alerts-total }

**Type:** 🔢 Gauge

**Description:** Total number of active network health alerts by category and severity

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.CATEGORY`
- `LabelName.SEVERITY`

??? example "Technical Details"

    **Constant:** `AlertMetricName.NETWORK_HEALTH_ALERTS_TOTAL`

    **Variable:** `self._network_health_alerts_total`
    **Source Line:** 80

---

#### `meraki_sensor_alerts_total` { #meraki-sensor-alerts-total }

**Type:** 🔢 Gauge

**Description:** Total number of sensor alerts in the last hour by metric type

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.METRIC`

??? example "Technical Details"

    **Constant:** `AlertMetricName.SENSOR_ALERTS_TOTAL`

    **Variable:** `self._sensor_alerts_total`
    **Source Line:** 67


### ClientsCollector { #clients }

!!! info "Collector Information"
    **Description:** 👥 Detailed client-level metrics including usage and status
    **Source File:** `src/meraki_dashboard_exporter/collectors/clients.py`
    **Metrics Count:** 21

#### `meraki_client_application_usage_recv_kb` { #meraki-client-application-usage-recv-kb }

**Type:** 🔢 Gauge

**Description:** Kilobytes received by client per application in the last hour

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.CLIENT_ID`
- `LabelName.MAC`
- `LabelName.DESCRIPTION`
- `LabelName.HOSTNAME`
- `LabelName.TYPE`

??? example "Technical Details"

    **Constant:** `ClientMetricName.CLIENT_APPLICATION_USAGE_RECV_KB`

    **Variable:** `self.client_app_usage_recv`
    **Source Line:** 238

---

#### `meraki_client_application_usage_sent_kb` { #meraki-client-application-usage-sent-kb }

**Type:** 🔢 Gauge

**Description:** Kilobytes sent by client per application in the last hour

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.CLIENT_ID`
- `LabelName.MAC`
- `LabelName.DESCRIPTION`
- `LabelName.HOSTNAME`
- `LabelName.TYPE`

??? example "Technical Details"

    **Constant:** `ClientMetricName.CLIENT_APPLICATION_USAGE_SENT_KB`

    **Variable:** `self.client_app_usage_sent`
    **Source Line:** 222

---

#### `meraki_client_application_usage_total_kb` { #meraki-client-application-usage-total-kb }

**Type:** 🔢 Gauge

**Description:** Total kilobytes transferred by client per application in the last hour

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.CLIENT_ID`
- `LabelName.MAC`
- `LabelName.DESCRIPTION`
- `LabelName.HOSTNAME`
- `LabelName.TYPE`

??? example "Technical Details"

    **Constant:** `ClientMetricName.CLIENT_APPLICATION_USAGE_TOTAL_KB`

    **Variable:** `self.client_app_usage_total`
    **Source Line:** 254

---

#### `meraki_client_status` { #meraki-client-status }

**Type:** 🔢 Gauge

**Description:** Client online status (1 = online, 0 = offline)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.CLIENT_ID`
- `LabelName.MAC`
- `LabelName.DESCRIPTION`
- `LabelName.HOSTNAME`
- `LabelName.SSID`

??? example "Technical Details"

    **Constant:** `ClientMetricName.CLIENT_STATUS`

    **Variable:** `self.client_status`
    **Source Line:** 70

---

#### `meraki_client_usage_recv_kb` { #meraki-client-usage-recv-kb }

**Type:** 🔢 Gauge

**Description:** Kilobytes received by client in the last hour

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.CLIENT_ID`
- `LabelName.MAC`
- `LabelName.DESCRIPTION`
- `LabelName.HOSTNAME`
- `LabelName.SSID`

??? example "Technical Details"

    **Constant:** `ClientMetricName.CLIENT_USAGE_RECV_KB`

    **Variable:** `self.client_usage_recv`
    **Source Line:** 104

---

#### `meraki_client_usage_sent_kb` { #meraki-client-usage-sent-kb }

**Type:** 🔢 Gauge

**Description:** Kilobytes sent by client in the last hour

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.CLIENT_ID`
- `LabelName.MAC`
- `LabelName.DESCRIPTION`
- `LabelName.HOSTNAME`
- `LabelName.SSID`

??? example "Technical Details"

    **Constant:** `ClientMetricName.CLIENT_USAGE_SENT_KB`

    **Variable:** `self.client_usage_sent`
    **Source Line:** 88

---

#### `meraki_client_usage_total_kb` { #meraki-client-usage-total-kb }

**Type:** 🔢 Gauge

**Description:** Total kilobytes transferred by client in the last hour

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.CLIENT_ID`
- `LabelName.MAC`
- `LabelName.DESCRIPTION`
- `LabelName.HOSTNAME`
- `LabelName.SSID`

??? example "Technical Details"

    **Constant:** `ClientMetricName.CLIENT_USAGE_TOTAL_KB`

    **Variable:** `self.client_usage_total`
    **Source Line:** 120

---

#### `meraki_clients_per_ssid_count` { #meraki-clients-per-ssid-count }

**Type:** 🔢 Gauge

**Description:** Count of clients per SSID

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SSID`

??? example "Technical Details"

    **Constant:** `ClientMetricName.CLIENTS_PER_SSID_COUNT`

    **Variable:** `self.clients_per_ssid`
    **Source Line:** 197

---

#### `meraki_clients_per_vlan_count` { #meraki-clients-per-vlan-count }

**Type:** 🔢 Gauge

**Description:** Count of clients per VLAN

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.VLAN`

??? example "Technical Details"

    **Constant:** `ClientMetricName.CLIENTS_PER_VLAN_COUNT`

    **Variable:** `self.clients_per_vlan`
    **Source Line:** 209

---

#### `meraki_exporter_client_dns_cache_expired` { #meraki-exporter-client-dns-cache-expired }

**Type:** 🔢 Gauge

**Description:** Number of expired entries in DNS cache

??? example "Technical Details"

    **Variable:** `self.dns_cache_expired`
    **Source Line:** 147

---

#### `meraki_exporter_client_dns_cache_total` { #meraki-exporter-client-dns-cache-total }

**Type:** 🔢 Gauge

**Description:** Total number of entries in DNS cache

??? example "Technical Details"

    **Variable:** `self.dns_cache_total`
    **Source Line:** 137

---

#### `meraki_exporter_client_dns_cache_valid` { #meraki-exporter-client-dns-cache-valid }

**Type:** 🔢 Gauge

**Description:** Number of valid entries in DNS cache

??? example "Technical Details"

    **Variable:** `self.dns_cache_valid`
    **Source Line:** 142

---

#### `meraki_exporter_client_dns_lookups_cached_total` { #meraki-exporter-client-dns-lookups-cached-total }

**Type:** 📈 Counter

**Description:** Total number of DNS lookups served from cache

??? example "Technical Details"

    **Variable:** `self.dns_lookups_cached`
    **Source Line:** 167

---

#### `meraki_exporter_client_dns_lookups_failed_total` { #meraki-exporter-client-dns-lookups-failed-total }

**Type:** 📈 Counter

**Description:** Total number of failed DNS lookups

??? example "Technical Details"

    **Variable:** `self.dns_lookups_failed`
    **Source Line:** 162

---

#### `meraki_exporter_client_dns_lookups_successful_total` { #meraki-exporter-client-dns-lookups-successful-total }

**Type:** 📈 Counter

**Description:** Total number of successful DNS lookups

??? example "Technical Details"

    **Variable:** `self.dns_lookups_successful`
    **Source Line:** 157

---

#### `meraki_exporter_client_dns_lookups_total` { #meraki-exporter-client-dns-lookups-total }

**Type:** 📈 Counter

**Description:** Total number of DNS lookups performed

??? example "Technical Details"

    **Variable:** `self.dns_lookups_total`
    **Source Line:** 152

---

#### `meraki_exporter_client_store_networks` { #meraki-exporter-client-store-networks }

**Type:** 🔢 Gauge

**Description:** Total number of networks with clients

??? example "Technical Details"

    **Variable:** `self.client_store_networks`
    **Source Line:** 178

---

#### `meraki_exporter_client_store_total` { #meraki-exporter-client-store-total }

**Type:** 🔢 Gauge

**Description:** Total number of clients in the store

??? example "Technical Details"

    **Variable:** `self.client_store_total`
    **Source Line:** 173

---

#### `meraki_wireless_client_capabilities_count` { #meraki-wireless-client-capabilities-count }

**Type:** 🔢 Gauge

**Description:** Count of wireless clients by capability

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.TYPE`

??? example "Technical Details"

    **Constant:** `ClientMetricName.WIRELESS_CLIENT_CAPABILITIES_COUNT`

    **Variable:** `self.client_capabilities_count`
    **Source Line:** 184

---

#### `meraki_wireless_client_rssi` { #meraki-wireless-client-rssi }

**Type:** 🔢 Gauge

**Description:** Wireless client RSSI (Received Signal Strength Indicator) in dBm

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.CLIENT_ID`
- `LabelName.MAC`
- `LabelName.DESCRIPTION`
- `LabelName.HOSTNAME`
- `LabelName.SSID`

??? example "Technical Details"

    **Constant:** `ClientMetricName.WIRELESS_CLIENT_RSSI`

    **Variable:** `self.wireless_client_rssi`
    **Source Line:** 271

---

#### `meraki_wireless_client_snr` { #meraki-wireless-client-snr }

**Type:** 🔢 Gauge

**Description:** Wireless client SNR (Signal-to-Noise Ratio) in dB

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.CLIENT_ID`
- `LabelName.MAC`
- `LabelName.DESCRIPTION`
- `LabelName.HOSTNAME`
- `LabelName.SSID`

??? example "Technical Details"

    **Constant:** `ClientMetricName.WIRELESS_CLIENT_SNR`

    **Variable:** `self.wireless_client_snr`
    **Source Line:** 287


### ConfigCollector { #config }

!!! info "Collector Information"
    **Description:** ⚙️ Organization security settings and configuration tracking
    **Source File:** `src/meraki_dashboard_exporter/collectors/config.py`
    **Metrics Count:** 14

#### `OrgMetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ATTEMPTS` { #orgmetricname-org-login-security-account-lockout-attempts }

**Type:** 🔢 Gauge

**Description:** Number of failed login attempts before lockout (0 if not set)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Variable:** `self._login_security_account_lockout_attempts`
    **Source Line:** 74

---

#### `OrgMetricName.ORG_LOGIN_SECURITY_API_IP_RESTRICTIONS_ENABLED` { #orgmetricname-org-login-security-api-ip-restrictions-enabled }

**Type:** 🔢 Gauge

**Description:** Whether API key IP restrictions are enabled (1=enabled, 0=disabled)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Variable:** `self._login_security_api_ip_restrictions_enabled`
    **Source Line:** 104

---

#### `OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_COUNT` { #orgmetricname-org-login-security-different-passwords-count }

**Type:** 🔢 Gauge

**Description:** Number of different passwords required (0 if not set)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Variable:** `self._login_security_different_passwords_count`
    **Source Line:** 50

---

#### `OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_ENABLED` { #orgmetricname-org-login-security-different-passwords-enabled }

**Type:** 🔢 Gauge

**Description:** Whether different passwords are enforced (1=enabled, 0=disabled)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Variable:** `self._login_security_different_passwords_enabled`
    **Source Line:** 44

---

#### `OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_DAYS` { #orgmetricname-org-login-security-password-expiration-days }

**Type:** 🔢 Gauge

**Description:** Number of days before password expires (0 if not set)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Variable:** `self._login_security_password_expiration_days`
    **Source Line:** 38

---

#### `OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_ENABLED` { #orgmetricname-org-login-security-password-expiration-enabled }

**Type:** 🔢 Gauge

**Description:** Whether password expiration is enforced (1=enabled, 0=disabled)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Variable:** `self._login_security_password_expiration_enabled`
    **Source Line:** 32

---

#### `OrgMetricName.ORG_LOGIN_SECURITY_STRONG_PASSWORDS_ENABLED` { #orgmetricname-org-login-security-strong-passwords-enabled }

**Type:** 🔢 Gauge

**Description:** Whether strong passwords are enforced (1=enabled, 0=disabled)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Variable:** `self._login_security_strong_passwords_enabled`
    **Source Line:** 56

---

#### `meraki_org_configuration_changes_total` { #meraki-org-configuration-changes-total }

**Type:** 🔢 Gauge

**Description:** Total number of configuration changes in the last 24 hours

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_CONFIGURATION_CHANGES_TOTAL`

    **Variable:** `self._configuration_changes_total`
    **Source Line:** 111

---

#### `meraki_org_login_security_account_lockout_enabled` { #meraki-org-login-security-account-lockout-enabled }

**Type:** 🔢 Gauge

**Description:** Whether account lockout is enforced (1=enabled, 0=disabled)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ENABLED`

    **Variable:** `self._login_security_account_lockout_enabled`
    **Source Line:** 68

---

#### `meraki_org_login_security_idle_timeout_enabled` { #meraki-org-login-security-idle-timeout-enabled }

**Type:** 🔢 Gauge

**Description:** Whether idle timeout is enforced (1=enabled, 0=disabled)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_LOGIN_SECURITY_IDLE_TIMEOUT_ENABLED`

    **Variable:** `self._login_security_idle_timeout_enabled`
    **Source Line:** 80

---

#### `meraki_org_login_security_idle_timeout_minutes` { #meraki-org-login-security-idle-timeout-minutes }

**Type:** 🔢 Gauge

**Description:** Minutes before idle timeout (0 if not set)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_LOGIN_SECURITY_IDLE_TIMEOUT_MINUTES`

    **Variable:** `self._login_security_idle_timeout_minutes`
    **Source Line:** 86

---

#### `meraki_org_login_security_ip_ranges_enabled` { #meraki-org-login-security-ip-ranges-enabled }

**Type:** 🔢 Gauge

**Description:** Whether login IP ranges are enforced (1=enabled, 0=disabled)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_LOGIN_SECURITY_IP_RANGES_ENABLED`

    **Variable:** `self._login_security_ip_ranges_enabled`
    **Source Line:** 98

---

#### `meraki_org_login_security_minimum_password_length` { #meraki-org-login-security-minimum-password-length }

**Type:** 🔢 Gauge

**Description:** Minimum password length required

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_LOGIN_SECURITY_MINIMUM_PASSWORD_LENGTH`

    **Variable:** `self._login_security_minimum_password_length`
    **Source Line:** 62

---

#### `meraki_org_login_security_two_factor_enabled` { #meraki-org-login-security-two-factor-enabled }

**Type:** 🔢 Gauge

**Description:** Whether two-factor authentication is enforced (1=enabled, 0=disabled)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_LOGIN_SECURITY_TWO_FACTOR_ENABLED`

    **Variable:** `self._login_security_two_factor_enabled`
    **Source Line:** 92


### DeviceCollector { #device }

!!! info "Collector Information"
    **Description:** 📱 Device status, performance, and uptime metrics
    **Source File:** `src/meraki_dashboard_exporter/collectors/device.py`
    **Metrics Count:** 10

#### `meraki_device_memory_free_bytes` { #meraki-device-memory-free-bytes }

**Type:** 🔢 Gauge

**Description:** Device memory free in bytes

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.STAT`

??? example "Technical Details"

    **Constant:** `DeviceMetricName.DEVICE_MEMORY_FREE_BYTES`

    **Variable:** `self._device_memory_free_bytes`
    **Source Line:** 255

---

#### `meraki_device_memory_total_bytes` { #meraki-device-memory-total-bytes }

**Type:** 🔢 Gauge

**Description:** Device memory total provisioned in bytes

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `DeviceMetricName.DEVICE_MEMORY_TOTAL_BYTES`

    **Variable:** `self._device_memory_total_bytes`
    **Source Line:** 271

---

#### `meraki_device_memory_usage_percent` { #meraki-device-memory-usage-percent }

**Type:** 🔢 Gauge

**Description:** Device memory usage percentage (maximum from most recent interval)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `DeviceMetricName.DEVICE_MEMORY_USAGE_PERCENT`

    **Variable:** `self._device_memory_usage_percent`
    **Source Line:** 286

---

#### `meraki_device_memory_used_bytes` { #meraki-device-memory-used-bytes }

**Type:** 🔢 Gauge

**Description:** Device memory used in bytes

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.STAT`

??? example "Technical Details"

    **Constant:** `DeviceMetricName.DEVICE_MEMORY_USED_BYTES`

    **Variable:** `self._device_memory_used_bytes`
    **Source Line:** 239

---

#### `meraki_device_status_info` { #meraki-device-status-info }

**Type:** 🔢 Gauge

**Description:** Device status information

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.STATUS`

??? example "Technical Details"

    **Constant:** `DeviceMetricName.DEVICE_STATUS_INFO`

    **Variable:** `self._device_status_info`
    **Source Line:** 222

---

#### `meraki_device_up` { #meraki-device-up }

**Type:** 🔢 Gauge

**Description:** Device online status (1 = online, 0 = offline)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `DeviceMetricName.DEVICE_UP`

    **Variable:** `self._device_up`
    **Source Line:** 207

---

#### `meraki_ms_ports_active_total` { #meraki-ms-ports-active-total }

**Type:** 🔢 Gauge

**Description:** Total number of active switch ports

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORTS_ACTIVE_TOTAL`

    **Variable:** `self._ms_ports_active_total`
    **Source Line:** 145

---

#### `meraki_ms_ports_by_link_speed_total` { #meraki-ms-ports-by-link-speed-total }

**Type:** 🔢 Gauge

**Description:** Total number of active switch ports by link speed

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.MEDIA`
- `LabelName.LINK_SPEED`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORTS_BY_LINK_SPEED_TOTAL`

    **Variable:** `self._ms_ports_by_link_speed_total`
    **Source Line:** 174

---

#### `meraki_ms_ports_by_media_total` { #meraki-ms-ports-by-media-total }

**Type:** 🔢 Gauge

**Description:** Total number of switch ports by media type

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.MEDIA`
- `LabelName.STATUS`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORTS_BY_MEDIA_TOTAL`

    **Variable:** `self._ms_ports_by_media_total`
    **Source Line:** 163

---

#### `meraki_ms_ports_inactive_total` { #meraki-ms-ports-inactive-total }

**Type:** 🔢 Gauge

**Description:** Total number of inactive switch ports

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORTS_INACTIVE_TOTAL`

    **Variable:** `self._ms_ports_inactive_total`
    **Source Line:** 154


### MRClientsCollector { #mrclients }

!!! info "Collector Information"
    **Description:** Various metrics
    **Source File:** `src/meraki_dashboard_exporter/collectors/devices/mr/clients.py`
    **Metrics Count:** 2

#### `meraki_mr_clients_connected` { #meraki-mr-clients-connected }

**Type:** 🔢 Gauge

**Description:** Number of clients connected to access point

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_CLIENTS_CONNECTED`

    **Variable:** `self._ap_clients`
    **Source Line:** 41

---

#### `meraki_mr_connection_stats_total` { #meraki-mr-connection-stats-total }

**Type:** 🔢 Gauge

**Description:** Wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.STAT_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_CONNECTION_STATS`

    **Variable:** `self._ap_connection_stats`
    **Source Line:** 56


### MRPerformanceCollector { #mrperformance }

!!! info "Collector Information"
    **Description:** Various metrics
    **Source File:** `src/meraki_dashboard_exporter/collectors/devices/mr/performance.py`
    **Metrics Count:** 27

#### `meraki_mr_aggregation_enabled` { #meraki-mr-aggregation-enabled }

**Type:** 🔢 Gauge

**Description:** Access point port aggregation enabled status (1 = enabled, 0 = disabled)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_AGGREGATION_ENABLED`

    **Variable:** `self._mr_aggregation_enabled`
    **Source Line:** 148

---

#### `meraki_mr_aggregation_speed_mbps` { #meraki-mr-aggregation-speed-mbps }

**Type:** 🔢 Gauge

**Description:** Access point total aggregated port speed in Mbps

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_AGGREGATION_SPEED_MBPS`

    **Variable:** `self._mr_aggregation_speed`
    **Source Line:** 163

---

#### `meraki_mr_cpu_load_5min` { #meraki-mr-cpu-load-5min }

**Type:** 🔢 Gauge

**Description:** Access point CPU load percentage (5-minute average)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_CPU_LOAD_5MIN`

    **Variable:** `self._mr_cpu_load_5min`
    **Source Line:** 416

---

#### `meraki_mr_network_packet_loss_downstream_percent` { #meraki-mr-network-packet-loss-downstream-percent }

**Type:** 🔢 Gauge

**Description:** Downstream packet loss percentage for network (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_NETWORK_PACKET_LOSS_DOWNSTREAM_PERCENT`

    **Variable:** `self._mr_network_packet_loss_downstream_percent`
    **Source Line:** 338

---

#### `meraki_mr_network_packet_loss_total_percent` { #meraki-mr-network-packet-loss-total-percent }

**Type:** 🔢 Gauge

**Description:** Total packet loss percentage for network (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_NETWORK_PACKET_LOSS_TOTAL_PERCENT`

    **Variable:** `self._mr_network_packet_loss_total_percent`
    **Source Line:** 404

---

#### `meraki_mr_network_packet_loss_upstream_percent` { #meraki-mr-network-packet-loss-upstream-percent }

**Type:** 🔢 Gauge

**Description:** Upstream packet loss percentage for network (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_NETWORK_PACKET_LOSS_UPSTREAM_PERCENT`

    **Variable:** `self._mr_network_packet_loss_upstream_percent`
    **Source Line:** 371

---

#### `meraki_mr_network_packets_downstream_lost` { #meraki-mr-network-packets-downstream-lost }

**Type:** 🔢 Gauge

**Description:** Downstream packets lost for network (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_NETWORK_PACKETS_DOWNSTREAM_LOST`

    **Variable:** `self._mr_network_packets_downstream_lost`
    **Source Line:** 327

---

#### `meraki_mr_network_packets_downstream_total` { #meraki-mr-network-packets-downstream-total }

**Type:** 🔢 Gauge

**Description:** Total downstream packets for network (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_NETWORK_PACKETS_DOWNSTREAM_TOTAL`

    **Variable:** `self._mr_network_packets_downstream_total`
    **Source Line:** 316

---

#### `meraki_mr_network_packets_lost_total` { #meraki-mr-network-packets-lost-total }

**Type:** 🔢 Gauge

**Description:** Total packets lost (upstream + downstream) for network (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_NETWORK_PACKETS_LOST_TOTAL`

    **Variable:** `self._mr_network_packets_lost_total`
    **Source Line:** 393

---

#### `meraki_mr_network_packets_total` { #meraki-mr-network-packets-total }

**Type:** 🔢 Gauge

**Description:** Total packets (upstream + downstream) for network (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_NETWORK_PACKETS_TOTAL`

    **Variable:** `self._mr_network_packets_total`
    **Source Line:** 382

---

#### `meraki_mr_network_packets_upstream_lost` { #meraki-mr-network-packets-upstream-lost }

**Type:** 🔢 Gauge

**Description:** Upstream packets lost for network (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_NETWORK_PACKETS_UPSTREAM_LOST`

    **Variable:** `self._mr_network_packets_upstream_lost`
    **Source Line:** 360

---

#### `meraki_mr_network_packets_upstream_total` { #meraki-mr-network-packets-upstream-total }

**Type:** 🔢 Gauge

**Description:** Total upstream packets for network (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_NETWORK_PACKETS_UPSTREAM_TOTAL`

    **Variable:** `self._mr_network_packets_upstream_total`
    **Source Line:** 349

---

#### `meraki_mr_packet_loss_downstream_percent` { #meraki-mr-packet-loss-downstream-percent }

**Type:** 🔢 Gauge

**Description:** Downstream packet loss percentage for access point (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_PACKET_LOSS_DOWNSTREAM_PERCENT`

    **Variable:** `self._mr_packet_loss_downstream_percent`
    **Source Line:** 209

---

#### `meraki_mr_packet_loss_total_percent` { #meraki-mr-packet-loss-total-percent }

**Type:** 🔢 Gauge

**Description:** Total packet loss percentage for access point (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_PACKET_LOSS_TOTAL_PERCENT`

    **Variable:** `self._mr_packet_loss_total_percent`
    **Source Line:** 300

---

#### `meraki_mr_packet_loss_upstream_percent` { #meraki-mr-packet-loss-upstream-percent }

**Type:** 🔢 Gauge

**Description:** Upstream packet loss percentage for access point (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_PACKET_LOSS_UPSTREAM_PERCENT`

    **Variable:** `self._mr_packet_loss_upstream_percent`
    **Source Line:** 254

---

#### `meraki_mr_packets_downstream_lost` { #meraki-mr-packets-downstream-lost }

**Type:** 🔢 Gauge

**Description:** Downstream packets lost by access point (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_PACKETS_DOWNSTREAM_LOST`

    **Variable:** `self._mr_packets_downstream_lost`
    **Source Line:** 194

---

#### `meraki_mr_packets_downstream_total` { #meraki-mr-packets-downstream-total }

**Type:** 🔢 Gauge

**Description:** Total downstream packets transmitted by access point (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_PACKETS_DOWNSTREAM_TOTAL`

    **Variable:** `self._mr_packets_downstream_total`
    **Source Line:** 179

---

#### `meraki_mr_packets_lost_total` { #meraki-mr-packets-lost-total }

**Type:** 🔢 Gauge

**Description:** Total packets lost (upstream + downstream) for access point (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_PACKETS_LOST_TOTAL`

    **Variable:** `self._mr_packets_lost_total`
    **Source Line:** 285

---

#### `meraki_mr_packets_total` { #meraki-mr-packets-total }

**Type:** 🔢 Gauge

**Description:** Total packets (upstream + downstream) for access point (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_PACKETS_TOTAL`

    **Variable:** `self._mr_packets_total`
    **Source Line:** 270

---

#### `meraki_mr_packets_upstream_lost` { #meraki-mr-packets-upstream-lost }

**Type:** 🔢 Gauge

**Description:** Upstream packets lost by access point (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_PACKETS_UPSTREAM_LOST`

    **Variable:** `self._mr_packets_upstream_lost`
    **Source Line:** 239

---

#### `meraki_mr_packets_upstream_total` { #meraki-mr-packets-upstream-total }

**Type:** 🔢 Gauge

**Description:** Total upstream packets received by access point (5-minute window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_PACKETS_UPSTREAM_TOTAL`

    **Variable:** `self._mr_packets_upstream_total`
    **Source Line:** 224

---

#### `meraki_mr_port_link_negotiation_info` { #meraki-mr-port-link-negotiation-info }

**Type:** 🔢 Gauge

**Description:** Access point port link negotiation information

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.PORT_NAME`
- `LabelName.DUPLEX`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_PORT_LINK_NEGOTIATION_INFO`

    **Variable:** `self._mr_port_link_negotiation_info`
    **Source Line:** 115

---

#### `meraki_mr_port_link_negotiation_speed_mbps` { #meraki-mr-port-link-negotiation-speed-mbps }

**Type:** 🔢 Gauge

**Description:** Access point port link negotiation speed in Mbps

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.PORT_NAME`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_PORT_LINK_NEGOTIATION_SPEED_MBPS`

    **Variable:** `self._mr_port_link_negotiation_speed`
    **Source Line:** 132

---

#### `meraki_mr_port_poe_info` { #meraki-mr-port-poe-info }

**Type:** 🔢 Gauge

**Description:** Access point port PoE information

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.PORT_NAME`
- `LabelName.STANDARD`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_PORT_POE_INFO`

    **Variable:** `self._mr_port_poe_info`
    **Source Line:** 98

---

#### `meraki_mr_power_ac_connected` { #meraki-mr-power-ac-connected }

**Type:** 🔢 Gauge

**Description:** Access point AC power connection status (1 = connected, 0 = not connected)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_POWER_AC_CONNECTED`

    **Variable:** `self._mr_power_ac_connected`
    **Source Line:** 68

---

#### `meraki_mr_power_info` { #meraki-mr-power-info }

**Type:** 🔢 Gauge

**Description:** Access point power information

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.MODE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_POWER_INFO`

    **Variable:** `self._mr_power_info`
    **Source Line:** 52

---

#### `meraki_mr_power_poe_connected` { #meraki-mr-power-poe-connected }

**Type:** 🔢 Gauge

**Description:** Access point PoE power connection status (1 = connected, 0 = not connected)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_POWER_POE_CONNECTED`

    **Variable:** `self._mr_power_poe_connected`
    **Source Line:** 83


### MRWirelessCollector { #mrwireless }

!!! info "Collector Information"
    **Description:** Various metrics
    **Source File:** `src/meraki_dashboard_exporter/collectors/devices/mr/wireless.py`
    **Metrics Count:** 9

#### `meraki_mr_radio_broadcasting` { #meraki-mr-radio-broadcasting }

**Type:** 🔢 Gauge

**Description:** Access point radio broadcasting status (1 = broadcasting, 0 = not broadcasting)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.BAND`
- `LabelName.RADIO_INDEX`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_RADIO_BROADCASTING`

    **Variable:** `self._mr_radio_broadcasting`
    **Source Line:** 49

---

#### `meraki_mr_radio_channel` { #meraki-mr-radio-channel }

**Type:** 🔢 Gauge

**Description:** Access point radio channel number

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.BAND`
- `LabelName.RADIO_INDEX`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_RADIO_CHANNEL`

    **Variable:** `self._mr_radio_channel`
    **Source Line:** 66

---

#### `meraki_mr_radio_channel_width_mhz` { #meraki-mr-radio-channel-width-mhz }

**Type:** 🔢 Gauge

**Description:** Access point radio channel width in MHz

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.BAND`
- `LabelName.RADIO_INDEX`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_RADIO_CHANNEL_WIDTH_MHZ`

    **Variable:** `self._mr_radio_channel_width`
    **Source Line:** 83

---

#### `meraki_mr_radio_power_dbm` { #meraki-mr-radio-power-dbm }

**Type:** 🔢 Gauge

**Description:** Access point radio transmit power in dBm

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.BAND`
- `LabelName.RADIO_INDEX`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_RADIO_POWER_DBM`

    **Variable:** `self._mr_radio_power`
    **Source Line:** 100

---

#### `meraki_mr_ssid_client_count` { #meraki-mr-ssid-client-count }

**Type:** 🔢 Gauge

**Description:** Number of clients connected to SSID over the last day

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SSID`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_SSID_CLIENT_COUNT`

    **Variable:** `self._ssid_client_count`
    **Source Line:** 166

---

#### `meraki_mr_ssid_usage_downstream_mb` { #meraki-mr-ssid-usage-downstream-mb }

**Type:** 🔢 Gauge

**Description:** Downstream data usage in MB by SSID over the last day

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SSID`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_SSID_USAGE_DOWNSTREAM_MB`

    **Variable:** `self._ssid_usage_downstream_mb`
    **Source Line:** 130

---

#### `meraki_mr_ssid_usage_percentage` { #meraki-mr-ssid-usage-percentage }

**Type:** 🔢 Gauge

**Description:** Percentage of total organization data usage by SSID over the last day

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SSID`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_SSID_USAGE_PERCENTAGE`

    **Variable:** `self._ssid_usage_percentage`
    **Source Line:** 154

---

#### `meraki_mr_ssid_usage_total_mb` { #meraki-mr-ssid-usage-total-mb }

**Type:** 🔢 Gauge

**Description:** Total data usage in MB by SSID over the last day

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SSID`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_SSID_USAGE_TOTAL_MB`

    **Variable:** `self._ssid_usage_total_mb`
    **Source Line:** 118

---

#### `meraki_mr_ssid_usage_upstream_mb` { #meraki-mr-ssid-usage-upstream-mb }

**Type:** 🔢 Gauge

**Description:** Upstream data usage in MB by SSID over the last day

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SSID`

??? example "Technical Details"

    **Constant:** `MRMetricName.MR_SSID_USAGE_UPSTREAM_MB`

    **Variable:** `self._ssid_usage_upstream_mb`
    **Source Line:** 142


### MSCollector { #ms }

!!! info "Collector Information"
    **Description:** 🔀 Switch-specific metrics including port status, power, and PoE
    **Source File:** `src/meraki_dashboard_exporter/collectors/devices/ms.py`
    **Metrics Count:** 24

#### `meraki_ms_poe_budget_watts` { #meraki-ms-poe-budget-watts }

**Type:** 🔢 Gauge

**Description:** Total POE power budget for switch in watts

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_POE_BUDGET_WATTS`

    **Variable:** `self._switch_poe_budget`
    **Source Line:** 150

---

#### `meraki_ms_poe_network_total_watthours` { #meraki-ms-poe-network-total-watthours }

**Type:** 🔢 Gauge

**Description:** Total POE power consumption for all switches in network in watt-hours (Wh)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_POE_NETWORK_TOTAL_WATTS`

    **Variable:** `self._switch_poe_network_total`
    **Source Line:** 165

---

#### `meraki_ms_poe_port_power_watthours` { #meraki-ms-poe-port-power-watthours }

**Type:** 🔢 Gauge

**Description:** Per-port POE power consumption in watt-hours (Wh) over the last 1 hour

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.PORT_ID`
- `LabelName.PORT_NAME`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_POE_PORT_POWER_WATTS`

    **Variable:** `self._switch_poe_port_power`
    **Source Line:** 118

---

#### `meraki_ms_poe_total_power_watthours` { #meraki-ms-poe-total-power-watthours }

**Type:** 🔢 Gauge

**Description:** Total POE power consumption for switch in watt-hours (Wh)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_POE_TOTAL_POWER_WATTS`

    **Variable:** `self._switch_poe_total_power`
    **Source Line:** 135

---

#### `meraki_ms_port_client_count` { #meraki-ms-port-client-count }

**Type:** 🔢 Gauge

**Description:** Number of clients connected to switch port

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.PORT_ID`
- `LabelName.PORT_NAME`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_CLIENT_COUNT`

    **Variable:** `self._switch_port_client_count`
    **Source Line:** 84

---

#### `meraki_ms_port_packets_broadcast` { #meraki-ms-port-packets-broadcast }

**Type:** 🔢 Gauge

**Description:** Broadcast packets on switch port (5-minute window)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_BROADCAST`

    **Variable:** `self._switch_port_packets_broadcast`
    **Source Line:** 213

---

#### `meraki_ms_port_packets_collisions` { #meraki-ms-port-packets-collisions }

**Type:** 🔢 Gauge

**Description:** Collision packets on switch port (5-minute window)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_COLLISIONS`

    **Variable:** `self._switch_port_packets_collisions`
    **Source Line:** 237

---

#### `meraki_ms_port_packets_crcerrors` { #meraki-ms-port-packets-crcerrors }

**Type:** 🔢 Gauge

**Description:** CRC align error packets on switch port (5-minute window)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_CRCERRORS`

    **Variable:** `self._switch_port_packets_crcerrors`
    **Source Line:** 225

---

#### `meraki_ms_port_packets_fragments` { #meraki-ms-port-packets-fragments }

**Type:** 🔢 Gauge

**Description:** Fragment packets on switch port (5-minute window)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_FRAGMENTS`

    **Variable:** `self._switch_port_packets_fragments`
    **Source Line:** 231

---

#### `meraki_ms_port_packets_multicast` { #meraki-ms-port-packets-multicast }

**Type:** 🔢 Gauge

**Description:** Multicast packets on switch port (5-minute window)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_MULTICAST`

    **Variable:** `self._switch_port_packets_multicast`
    **Source Line:** 219

---

#### `meraki_ms_port_packets_rate_broadcast` { #meraki-ms-port-packets-rate-broadcast }

**Type:** 🔢 Gauge

**Description:** Broadcast packet rate on switch port (packets per second, 5-minute average)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_RATE_BROADCAST`

    **Variable:** `self._switch_port_packets_rate_broadcast`
    **Source Line:** 256

---

#### `meraki_ms_port_packets_rate_collisions` { #meraki-ms-port-packets-rate-collisions }

**Type:** 🔢 Gauge

**Description:** Collision packet rate on switch port (packets per second, 5-minute average)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_RATE_COLLISIONS`

    **Variable:** `self._switch_port_packets_rate_collisions`
    **Source Line:** 280

---

#### `meraki_ms_port_packets_rate_crcerrors` { #meraki-ms-port-packets-rate-crcerrors }

**Type:** 🔢 Gauge

**Description:** CRC align error packet rate on switch port (packets per second, 5-minute average)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_RATE_CRCERRORS`

    **Variable:** `self._switch_port_packets_rate_crcerrors`
    **Source Line:** 268

---

#### `meraki_ms_port_packets_rate_fragments` { #meraki-ms-port-packets-rate-fragments }

**Type:** 🔢 Gauge

**Description:** Fragment packet rate on switch port (packets per second, 5-minute average)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_RATE_FRAGMENTS`

    **Variable:** `self._switch_port_packets_rate_fragments`
    **Source Line:** 274

---

#### `meraki_ms_port_packets_rate_multicast` { #meraki-ms-port-packets-rate-multicast }

**Type:** 🔢 Gauge

**Description:** Multicast packet rate on switch port (packets per second, 5-minute average)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_RATE_MULTICAST`

    **Variable:** `self._switch_port_packets_rate_multicast`
    **Source Line:** 262

---

#### `meraki_ms_port_packets_rate_topologychanges` { #meraki-ms-port-packets-rate-topologychanges }

**Type:** 🔢 Gauge

**Description:** Topology change packet rate on switch port (packets per second, 5-minute average)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_RATE_TOPOLOGYCHANGES`

    **Variable:** `self._switch_port_packets_rate_topologychanges`
    **Source Line:** 286

---

#### `meraki_ms_port_packets_rate_total` { #meraki-ms-port-packets-rate-total }

**Type:** 🔢 Gauge

**Description:** Total packet rate on switch port (packets per second, 5-minute average)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_RATE_TOTAL`

    **Variable:** `self._switch_port_packets_rate_total`
    **Source Line:** 250

---

#### `meraki_ms_port_packets_topologychanges` { #meraki-ms-port-packets-topologychanges }

**Type:** 🔢 Gauge

**Description:** Topology change packets on switch port (5-minute window)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_TOPOLOGYCHANGES`

    **Variable:** `self._switch_port_packets_topologychanges`
    **Source Line:** 243

---

#### `meraki_ms_port_packets_total` { #meraki-ms-port-packets-total }

**Type:** 🔢 Gauge

**Description:** Total packets on switch port (5-minute window)

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_PACKETS_TOTAL`

    **Variable:** `self._switch_port_packets_total`
    **Source Line:** 207

---

#### `meraki_ms_port_status` { #meraki-ms-port-status }

**Type:** 🔢 Gauge

**Description:** Switch port status (1 = connected, 0 = disconnected)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.PORT_ID`
- `LabelName.PORT_NAME`
- `LabelName.LINK_SPEED`
- `LabelName.DUPLEX`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_STATUS`

    **Variable:** `self._switch_port_status`
    **Source Line:** 29

---

#### `meraki_ms_port_traffic_bytes` { #meraki-ms-port-traffic-bytes }

**Type:** 🔢 Gauge

**Description:** Switch port traffic rate in bytes per second (averaged over 1 hour)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.PORT_ID`
- `LabelName.PORT_NAME`
- `LabelName.DIRECTION`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_TRAFFIC_BYTES`

    **Variable:** `self._switch_port_traffic`
    **Source Line:** 48

---

#### `meraki_ms_port_usage_bytes` { #meraki-ms-port-usage-bytes }

**Type:** 🔢 Gauge

**Description:** Switch port data usage in bytes over the last 1 hour

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.PORT_ID`
- `LabelName.PORT_NAME`
- `LabelName.DIRECTION`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_PORT_USAGE_BYTES`

    **Variable:** `self._switch_port_usage`
    **Source Line:** 66

---

#### `meraki_ms_power_usage_watts` { #meraki-ms-power-usage-watts }

**Type:** 🔢 Gauge

**Description:** Switch power usage in watts

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_POWER_USAGE_WATTS`

    **Variable:** `self._switch_power`
    **Source Line:** 102

---

#### `meraki_ms_stp_priority` { #meraki-ms-stp-priority }

**Type:** 🔢 Gauge

**Description:** Switch STP (Spanning Tree Protocol) priority

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MSMetricName.MS_STP_PRIORITY`

    **Variable:** `self._switch_stp_priority`
    **Source Line:** 177


### MTSensorCollector { #mtsensor }

!!! info "Collector Information"
    **Description:** 📊 Environmental monitoring from MT sensors
    **Source File:** `src/meraki_dashboard_exporter/collectors/mt_sensor.py`
    **Metrics Count:** 18

#### `meraki_mt_apparent_power_va` { #meraki-mt-apparent-power-va }

**Type:** 🔢 Gauge

**Description:** Apparent power in volt-amperes

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_APPARENT_POWER_VA`

    **Variable:** `self._sensor_apparent_power`
    **Source Line:** 252

---

#### `meraki_mt_battery_percentage` { #meraki-mt-battery-percentage }

**Type:** 🔢 Gauge

**Description:** Battery level percentage

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_BATTERY_PERCENTAGE`

    **Variable:** `self._sensor_battery`
    **Source Line:** 177

---

#### `meraki_mt_co2_ppm` { #meraki-mt-co2-ppm }

**Type:** 🔢 Gauge

**Description:** CO2 level in parts per million

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_CO2_PPM`

    **Variable:** `self._sensor_co2`
    **Source Line:** 117

---

#### `meraki_mt_current_amps` { #meraki-mt-current-amps }

**Type:** 🔢 Gauge

**Description:** Current in amperes

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_CURRENT_AMPS`

    **Variable:** `self._sensor_current`
    **Source Line:** 222

---

#### `meraki_mt_door_status` { #meraki-mt-door-status }

**Type:** 🔢 Gauge

**Description:** Door sensor status (1 = open, 0 = closed)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_DOOR_STATUS`

    **Variable:** `self._sensor_door`
    **Source Line:** 87

---

#### `meraki_mt_downstream_power_enabled` { #meraki-mt-downstream-power-enabled }

**Type:** 🔢 Gauge

**Description:** Downstream power status (1 = enabled, 0 = disabled)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_DOWNSTREAM_POWER_ENABLED`

    **Variable:** `self._sensor_downstream_power`
    **Source Line:** 297

---

#### `meraki_mt_frequency_hz` { #meraki-mt-frequency-hz }

**Type:** 🔢 Gauge

**Description:** Frequency in hertz

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_FREQUENCY_HZ`

    **Variable:** `self._sensor_frequency`
    **Source Line:** 282

---

#### `meraki_mt_humidity_percent` { #meraki-mt-humidity-percent }

**Type:** 🔢 Gauge

**Description:** Humidity percentage

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_HUMIDITY_PERCENT`

    **Variable:** `self._sensor_humidity`
    **Source Line:** 72

---

#### `meraki_mt_indoor_air_quality_score` { #meraki-mt-indoor-air-quality-score }

**Type:** 🔢 Gauge

**Description:** Indoor air quality score (0-100)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_INDOOR_AIR_QUALITY_SCORE`

    **Variable:** `self._sensor_air_quality`
    **Source Line:** 192

---

#### `meraki_mt_noise_db` { #meraki-mt-noise-db }

**Type:** 🔢 Gauge

**Description:** Noise level in decibels

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_NOISE_DB`

    **Variable:** `self._sensor_noise`
    **Source Line:** 162

---

#### `meraki_mt_pm25_ug_m3` { #meraki-mt-pm25-ug-m3 }

**Type:** 🔢 Gauge

**Description:** PM2.5 particulate matter in micrograms per cubic meter

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_PM25_UG_M3`

    **Variable:** `self._sensor_pm25`
    **Source Line:** 147

---

#### `meraki_mt_power_factor_percent` { #meraki-mt-power-factor-percent }

**Type:** 🔢 Gauge

**Description:** Power factor percentage

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_POWER_FACTOR_PERCENT`

    **Variable:** `self._sensor_power_factor`
    **Source Line:** 267

---

#### `meraki_mt_real_power_watts` { #meraki-mt-real-power-watts }

**Type:** 🔢 Gauge

**Description:** Real power in watts

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_REAL_POWER_WATTS`

    **Variable:** `self._sensor_real_power`
    **Source Line:** 237

---

#### `meraki_mt_remote_lockout_status` { #meraki-mt-remote-lockout-status }

**Type:** 🔢 Gauge

**Description:** Remote lockout switch status (1 = locked, 0 = unlocked)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_REMOTE_LOCKOUT_STATUS`

    **Variable:** `self._sensor_remote_lockout`
    **Source Line:** 312

---

#### `meraki_mt_temperature_celsius` { #meraki-mt-temperature-celsius }

**Type:** 🔢 Gauge

**Description:** Temperature reading in Celsius

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_TEMPERATURE_CELSIUS`

    **Variable:** `self._sensor_temperature`
    **Source Line:** 57

---

#### `meraki_mt_tvoc_ppb` { #meraki-mt-tvoc-ppb }

**Type:** 🔢 Gauge

**Description:** Total volatile organic compounds in parts per billion

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_TVOC_PPB`

    **Variable:** `self._sensor_tvoc`
    **Source Line:** 132

---

#### `meraki_mt_voltage_volts` { #meraki-mt-voltage-volts }

**Type:** 🔢 Gauge

**Description:** Voltage in volts

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_VOLTAGE_VOLTS`

    **Variable:** `self._sensor_voltage`
    **Source Line:** 207

---

#### `meraki_mt_water_detected` { #meraki-mt-water-detected }

**Type:** 🔢 Gauge

**Description:** Water detection status (1 = detected, 0 = not detected)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `MTMetricName.MT_WATER_DETECTED`

    **Variable:** `self._sensor_water`
    **Source Line:** 102


### NetworkHealthCollector { #networkhealth }

!!! info "Collector Information"
    **Description:** 🏥 Network-wide wireless health and performance
    **Source File:** `src/meraki_dashboard_exporter/collectors/network_health.py`
    **Metrics Count:** 8

#### `meraki_ap_channel_utilization_2_4ghz_percent` { #meraki-ap-channel-utilization-2-4ghz-percent }

**Type:** 🔢 Gauge

**Description:** 2.4GHz channel utilization percentage per AP

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.UTILIZATION_TYPE`

??? example "Technical Details"

    **Constant:** `NetworkHealthMetricName.AP_CHANNEL_UTILIZATION_2_4GHZ_PERCENT`

    **Variable:** `self._ap_utilization_2_4ghz`
    **Source Line:** 57

---

#### `meraki_ap_channel_utilization_5ghz_percent` { #meraki-ap-channel-utilization-5ghz-percent }

**Type:** 🔢 Gauge

**Description:** 5GHz channel utilization percentage per AP

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.SERIAL`
- `LabelName.NAME`
- `LabelName.MODEL`
- `LabelName.DEVICE_TYPE`
- `LabelName.UTILIZATION_TYPE`

??? example "Technical Details"

    **Constant:** `NetworkHealthMetricName.AP_CHANNEL_UTILIZATION_5GHZ_PERCENT`

    **Variable:** `self._ap_utilization_5ghz`
    **Source Line:** 73

---

#### `meraki_network_bluetooth_clients_total` { #meraki-network-bluetooth-clients-total }

**Type:** 🔢 Gauge

**Description:** Total number of Bluetooth clients detected by MR devices in the last 5 minutes

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `NetworkHealthMetricName.NETWORK_BLUETOOTH_CLIENTS_TOTAL`

    **Variable:** `self._network_bluetooth_clients_total`
    **Source Line:** 151

---

#### `meraki_network_channel_utilization_2_4ghz_percent` { #meraki-network-channel-utilization-2-4ghz-percent }

**Type:** 🔢 Gauge

**Description:** Network-wide average 2.4GHz channel utilization percentage

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.UTILIZATION_TYPE`

??? example "Technical Details"

    **Constant:** `NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_2_4GHZ_PERCENT`

    **Variable:** `self._network_utilization_2_4ghz`
    **Source Line:** 90

---

#### `meraki_network_channel_utilization_5ghz_percent` { #meraki-network-channel-utilization-5ghz-percent }

**Type:** 🔢 Gauge

**Description:** Network-wide average 5GHz channel utilization percentage

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.UTILIZATION_TYPE`

??? example "Technical Details"

    **Constant:** `NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_5GHZ_PERCENT`

    **Variable:** `self._network_utilization_5ghz`
    **Source Line:** 102

---

#### `meraki_network_wireless_connection_stats_total` { #meraki-network-wireless-connection-stats-total }

**Type:** 🔢 Gauge

**Description:** Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`
- `LabelName.STAT_TYPE`

??? example "Technical Details"

    **Constant:** `NetworkMetricName.NETWORK_WIRELESS_CONNECTION_STATS`

    **Variable:** `self._network_connection_stats`
    **Source Line:** 115

---

#### `meraki_network_wireless_download_kbps` { #meraki-network-wireless-download-kbps }

**Type:** 🔢 Gauge

**Description:** Network-wide wireless download bandwidth in kilobits per second

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `NetworkHealthMetricName.NETWORK_WIRELESS_DOWNLOAD_KBPS`

    **Variable:** `self._network_wireless_download_kbps`
    **Source Line:** 128

---

#### `meraki_network_wireless_upload_kbps` { #meraki-network-wireless-upload-kbps }

**Type:** 🔢 Gauge

**Description:** Network-wide wireless upload bandwidth in kilobits per second

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.NETWORK_ID`
- `LabelName.NETWORK_NAME`

??? example "Technical Details"

    **Constant:** `NetworkHealthMetricName.NETWORK_WIRELESS_UPLOAD_KBPS`

    **Variable:** `self._network_wireless_upload_kbps`
    **Source Line:** 139


### OrganizationCollector { #organization }

!!! info "Collector Information"
    **Description:** 🏢 Organization-level metrics including API usage and licenses
    **Source File:** `src/meraki_dashboard_exporter/collectors/organization.py`
    **Metrics Count:** 19

#### `meraki_org` { #meraki-org }

**Type:** ℹ️ Info

**Description:** Organization information

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_INFO`

    **Variable:** `self._org_info`
    **Source Line:** 58

---

#### `meraki_org_api_requests_by_status` { #meraki-org-api-requests-by-status }

**Type:** 🔢 Gauge

**Description:** API requests by HTTP status code in the last hour

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.STATUS_CODE`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_API_REQUESTS_BY_STATUS`

    **Variable:** `self._api_requests_by_status`
    **Source Line:** 71

---

#### `meraki_org_api_requests_total` { #meraki-org-api-requests-total }

**Type:** 🔢 Gauge

**Description:** Total API requests made by the organization in the last hour

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_API_REQUESTS_TOTAL`

    **Variable:** `self._api_requests_total`
    **Source Line:** 65

---

#### `meraki_org_application_usage_downstream_mb` { #meraki-org-application-usage-downstream-mb }

**Type:** 🔢 Gauge

**Description:** Downstream application usage in MB by category

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.CATEGORY`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_APPLICATION_USAGE_DOWNSTREAM_MB`

    **Variable:** `self._application_usage_downstream_mb`
    **Source Line:** 173

---

#### `meraki_org_application_usage_percentage` { #meraki-org-application-usage-percentage }

**Type:** 🔢 Gauge

**Description:** Application usage percentage by category

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.CATEGORY`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_APPLICATION_USAGE_PERCENTAGE`

    **Variable:** `self._application_usage_percentage`
    **Source Line:** 185

---

#### `meraki_org_application_usage_total_mb` { #meraki-org-application-usage-total-mb }

**Type:** 🔢 Gauge

**Description:** Total application usage in MB by category

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.CATEGORY`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_MB`

    **Variable:** `self._application_usage_total_mb`
    **Source Line:** 167

---

#### `meraki_org_application_usage_upstream_mb` { #meraki-org-application-usage-upstream-mb }

**Type:** 🔢 Gauge

**Description:** Upstream application usage in MB by category

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.CATEGORY`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_APPLICATION_USAGE_UPSTREAM_MB`

    **Variable:** `self._application_usage_upstream_mb`
    **Source Line:** 179

---

#### `meraki_org_clients_total` { #meraki-org-clients-total }

**Type:** 🔢 Gauge

**Description:** Total number of active clients in the organization (1-hour window)

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_CLIENTS_TOTAL`

    **Variable:** `self._clients_total`
    **Source Line:** 128

---

#### `meraki_org_devices_availability_total` { #meraki-org-devices-availability-total }

**Type:** 🔢 Gauge

**Description:** Total number of devices by availability status and product type

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.STATUS`
- `LabelName.PRODUCT_TYPE`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_DEVICES_AVAILABILITY_TOTAL`

    **Variable:** `self._devices_availability_total`
    **Source Line:** 98

---

#### `meraki_org_devices_by_model_total` { #meraki-org-devices-by-model-total }

**Type:** 🔢 Gauge

**Description:** Total number of devices by specific model

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.MODEL`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_DEVICES_BY_MODEL_TOTAL`

    **Variable:** `self._devices_by_model_total`
    **Source Line:** 91

---

#### `meraki_org_devices_total` { #meraki-org-devices-total }

**Type:** 🔢 Gauge

**Description:** Total number of devices in the organization

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.DEVICE_TYPE`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_DEVICES_TOTAL`

    **Variable:** `self._devices_total`
    **Source Line:** 85

---

#### `meraki_org_licenses_expiring` { #meraki-org-licenses-expiring }

**Type:** 🔢 Gauge

**Description:** Number of licenses expiring within 30 days

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.LICENSE_TYPE`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_LICENSES_EXPIRING`

    **Variable:** `self._licenses_expiring`
    **Source Line:** 121

---

#### `meraki_org_licenses_total` { #meraki-org-licenses-total }

**Type:** 🔢 Gauge

**Description:** Total number of licenses

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`
- `LabelName.LICENSE_TYPE`
- `LabelName.STATUS`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_LICENSES_TOTAL`

    **Variable:** `self._licenses_total`
    **Source Line:** 110

---

#### `meraki_org_networks_total` { #meraki-org-networks-total }

**Type:** 🔢 Gauge

**Description:** Total number of networks in the organization

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_NETWORKS_TOTAL`

    **Variable:** `self._networks_total`
    **Source Line:** 78

---

#### `meraki_org_packetcaptures_remaining` { #meraki-org-packetcaptures-remaining }

**Type:** 🔢 Gauge

**Description:** Number of remaining packet captures to process

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_PACKETCAPTURES_REMAINING`

    **Variable:** `self._packetcaptures_remaining`
    **Source Line:** 160

---

#### `meraki_org_packetcaptures_total` { #meraki-org-packetcaptures-total }

**Type:** 🔢 Gauge

**Description:** Total number of packet captures in the organization

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_PACKETCAPTURES_TOTAL`

    **Variable:** `self._packetcaptures_total`
    **Source Line:** 154

---

#### `meraki_org_usage_downstream_kb` { #meraki-org-usage-downstream-kb }

**Type:** 🔢 Gauge

**Description:** Downstream data usage in KB for the 1-hour window

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_USAGE_DOWNSTREAM_KB`

    **Variable:** `self._usage_downstream_kb`
    **Source Line:** 141

---

#### `meraki_org_usage_total_kb` { #meraki-org-usage-total-kb }

**Type:** 🔢 Gauge

**Description:** Total data usage in KB for the 1-hour window

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_USAGE_TOTAL_KB`

    **Variable:** `self._usage_total_kb`
    **Source Line:** 135

---

#### `meraki_org_usage_upstream_kb` { #meraki-org-usage-upstream-kb }

**Type:** 🔢 Gauge

**Description:** Upstream data usage in KB for the 1-hour window

**Labels:**

- `LabelName.ORG_ID`
- `LabelName.ORG_NAME`

??? example "Technical Details"

    **Constant:** `OrgMetricName.ORG_USAGE_UPSTREAM_KB`

    **Variable:** `self._usage_upstream_kb`
    **Source Line:** 147


## 📖 Complete Metrics Index

All metrics in alphabetical order with quick access:

| Metric Name | Type | Collector | Labels | Description |
|-------------|------|-----------|--------|-------------|
| [`OrgMetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ATTEMPTS`](#orgmetricname-org-login-security-account-lockout-attempts) | 🔢 gauge | ConfigCollector | 2 labels | Number of failed login attempts before lockout (0 if not set) |
| [`OrgMetricName.ORG_LOGIN_SECURITY_API_IP_RESTRICTIONS_ENABLED`](#orgmetricname-org-login-security-api-ip-restrictions-enabled) | 🔢 gauge | ConfigCollector | 2 labels | Whether API key IP restrictions are enabled (1=enabled, 0=disabled) |
| [`OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_COUNT`](#orgmetricname-org-login-security-different-passwords-count) | 🔢 gauge | ConfigCollector | 2 labels | Number of different passwords required (0 if not set) |
| [`OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_ENABLED`](#orgmetricname-org-login-security-different-passwords-enabled) | 🔢 gauge | ConfigCollector | 2 labels | Whether different passwords are enforced (1=enabled, 0=disabled) |
| [`OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_DAYS`](#orgmetricname-org-login-security-password-expiration-days) | 🔢 gauge | ConfigCollector | 2 labels | Number of days before password expires (0 if not set) |
| [`OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_ENABLED`](#orgmetricname-org-login-security-password-expiration-enabled) | 🔢 gauge | ConfigCollector | 2 labels | Whether password expiration is enforced (1=enabled, 0=disabled) |
| [`OrgMetricName.ORG_LOGIN_SECURITY_STRONG_PASSWORDS_ENABLED`](#orgmetricname-org-login-security-strong-passwords-enabled) | 🔢 gauge | ConfigCollector | 2 labels | Whether strong passwords are enforced (1=enabled, 0=disabled) |
| [`meraki_alerts_active`](#meraki-alerts-active) | 🔢 gauge | AlertsCollector | 8 labels | Number of active Meraki assurance alerts |
| [`meraki_alerts_total_by_network`](#meraki-alerts-total-by-network) | 🔢 gauge | AlertsCollector | 4 labels | Total number of active alerts per network |
| [`meraki_alerts_total_by_severity`](#meraki-alerts-total-by-severity) | 🔢 gauge | AlertsCollector | 3 labels | Total number of active alerts by severity |
| [`meraki_ap_channel_utilization_2_4ghz_percent`](#meraki-ap-channel-utilization-2-4ghz-percent) | 🔢 gauge | NetworkHealthCollector | 9 labels | 2.4GHz channel utilization percentage per AP |
| [`meraki_ap_channel_utilization_5ghz_percent`](#meraki-ap-channel-utilization-5ghz-percent) | 🔢 gauge | NetworkHealthCollector | 9 labels | 5GHz channel utilization percentage per AP |
| [`meraki_client_application_usage_recv_kb`](#meraki-client-application-usage-recv-kb) | 🔢 gauge | ClientsCollector | 9 labels | Kilobytes received by client per application in the last hour |
| [`meraki_client_application_usage_sent_kb`](#meraki-client-application-usage-sent-kb) | 🔢 gauge | ClientsCollector | 9 labels | Kilobytes sent by client per application in the last hour |
| [`meraki_client_application_usage_total_kb`](#meraki-client-application-usage-total-kb) | 🔢 gauge | ClientsCollector | 9 labels | Total kilobytes transferred by client per application in the last hour |
| [`meraki_client_status`](#meraki-client-status) | 🔢 gauge | ClientsCollector | 9 labels | Client online status (1 = online, 0 = offline) |
| [`meraki_client_usage_recv_kb`](#meraki-client-usage-recv-kb) | 🔢 gauge | ClientsCollector | 9 labels | Kilobytes received by client in the last hour |
| [`meraki_client_usage_sent_kb`](#meraki-client-usage-sent-kb) | 🔢 gauge | ClientsCollector | 9 labels | Kilobytes sent by client in the last hour |
| [`meraki_client_usage_total_kb`](#meraki-client-usage-total-kb) | 🔢 gauge | ClientsCollector | 9 labels | Total kilobytes transferred by client in the last hour |
| [`meraki_clients_per_ssid_count`](#meraki-clients-per-ssid-count) | 🔢 gauge | ClientsCollector | 5 labels | Count of clients per SSID |
| [`meraki_clients_per_vlan_count`](#meraki-clients-per-vlan-count) | 🔢 gauge | ClientsCollector | 5 labels | Count of clients per VLAN |
| [`meraki_device_memory_free_bytes`](#meraki-device-memory-free-bytes) | 🔢 gauge | DeviceCollector | 9 labels | Device memory free in bytes |
| [`meraki_device_memory_total_bytes`](#meraki-device-memory-total-bytes) | 🔢 gauge | DeviceCollector | 8 labels | Device memory total provisioned in bytes |
| [`meraki_device_memory_usage_percent`](#meraki-device-memory-usage-percent) | 🔢 gauge | DeviceCollector | 8 labels | Device memory usage percentage (maximum from most recent interval) |
| [`meraki_device_memory_used_bytes`](#meraki-device-memory-used-bytes) | 🔢 gauge | DeviceCollector | 9 labels | Device memory used in bytes |
| [`meraki_device_status_info`](#meraki-device-status-info) | 🔢 gauge | DeviceCollector | 9 labels | Device status information |
| [`meraki_device_up`](#meraki-device-up) | 🔢 gauge | DeviceCollector | 8 labels | Device online status (1 = online, 0 = offline) |
| [`meraki_exporter_client_dns_cache_expired`](#meraki-exporter-client-dns-cache-expired) | 🔢 gauge | ClientsCollector | No labels | Number of expired entries in DNS cache |
| [`meraki_exporter_client_dns_cache_total`](#meraki-exporter-client-dns-cache-total) | 🔢 gauge | ClientsCollector | No labels | Total number of entries in DNS cache |
| [`meraki_exporter_client_dns_cache_valid`](#meraki-exporter-client-dns-cache-valid) | 🔢 gauge | ClientsCollector | No labels | Number of valid entries in DNS cache |
| [`meraki_exporter_client_dns_lookups_cached_total`](#meraki-exporter-client-dns-lookups-cached-total) | 📈 counter | ClientsCollector | No labels | Total number of DNS lookups served from cache |
| [`meraki_exporter_client_dns_lookups_failed_total`](#meraki-exporter-client-dns-lookups-failed-total) | 📈 counter | ClientsCollector | No labels | Total number of failed DNS lookups |
| [`meraki_exporter_client_dns_lookups_successful_total`](#meraki-exporter-client-dns-lookups-successful-total) | 📈 counter | ClientsCollector | No labels | Total number of successful DNS lookups |
| [`meraki_exporter_client_dns_lookups_total`](#meraki-exporter-client-dns-lookups-total) | 📈 counter | ClientsCollector | No labels | Total number of DNS lookups performed |
| [`meraki_exporter_client_store_networks`](#meraki-exporter-client-store-networks) | 🔢 gauge | ClientsCollector | No labels | Total number of networks with clients |
| [`meraki_exporter_client_store_total`](#meraki-exporter-client-store-total) | 🔢 gauge | ClientsCollector | No labels | Total number of clients in the store |
| [`meraki_mr_aggregation_enabled`](#meraki-mr-aggregation-enabled) | 🔢 gauge | MRPerformanceCollector | 8 labels | Access point port aggregation enabled status (1 = enabled, 0 = disabled) |
| [`meraki_mr_aggregation_speed_mbps`](#meraki-mr-aggregation-speed-mbps) | 🔢 gauge | MRPerformanceCollector | 8 labels | Access point total aggregated port speed in Mbps |
| [`meraki_mr_clients_connected`](#meraki-mr-clients-connected) | 🔢 gauge | MRClientsCollector | 8 labels | Number of clients connected to access point |
| [`meraki_mr_connection_stats_total`](#meraki-mr-connection-stats-total) | 🔢 gauge | MRClientsCollector | 9 labels | Wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success) |
| [`meraki_mr_cpu_load_5min`](#meraki-mr-cpu-load-5min) | 🔢 gauge | MRPerformanceCollector | 8 labels | Access point CPU load percentage (5-minute average) |
| [`meraki_mr_network_packet_loss_downstream_percent`](#meraki-mr-network-packet-loss-downstream-percent) | 🔢 gauge | MRPerformanceCollector | 4 labels | Downstream packet loss percentage for network (5-minute window) |
| [`meraki_mr_network_packet_loss_total_percent`](#meraki-mr-network-packet-loss-total-percent) | 🔢 gauge | MRPerformanceCollector | 4 labels | Total packet loss percentage for network (5-minute window) |
| [`meraki_mr_network_packet_loss_upstream_percent`](#meraki-mr-network-packet-loss-upstream-percent) | 🔢 gauge | MRPerformanceCollector | 4 labels | Upstream packet loss percentage for network (5-minute window) |
| [`meraki_mr_network_packets_downstream_lost`](#meraki-mr-network-packets-downstream-lost) | 🔢 gauge | MRPerformanceCollector | 4 labels | Downstream packets lost for network (5-minute window) |
| [`meraki_mr_network_packets_downstream_total`](#meraki-mr-network-packets-downstream-total) | 🔢 gauge | MRPerformanceCollector | 4 labels | Total downstream packets for network (5-minute window) |
| [`meraki_mr_network_packets_lost_total`](#meraki-mr-network-packets-lost-total) | 🔢 gauge | MRPerformanceCollector | 4 labels | Total packets lost (upstream + downstream) for network (5-minute window) |
| [`meraki_mr_network_packets_total`](#meraki-mr-network-packets-total) | 🔢 gauge | MRPerformanceCollector | 4 labels | Total packets (upstream + downstream) for network (5-minute window) |
| [`meraki_mr_network_packets_upstream_lost`](#meraki-mr-network-packets-upstream-lost) | 🔢 gauge | MRPerformanceCollector | 4 labels | Upstream packets lost for network (5-minute window) |
| [`meraki_mr_network_packets_upstream_total`](#meraki-mr-network-packets-upstream-total) | 🔢 gauge | MRPerformanceCollector | 4 labels | Total upstream packets for network (5-minute window) |
| [`meraki_mr_packet_loss_downstream_percent`](#meraki-mr-packet-loss-downstream-percent) | 🔢 gauge | MRPerformanceCollector | 8 labels | Downstream packet loss percentage for access point (5-minute window) |
| [`meraki_mr_packet_loss_total_percent`](#meraki-mr-packet-loss-total-percent) | 🔢 gauge | MRPerformanceCollector | 8 labels | Total packet loss percentage for access point (5-minute window) |
| [`meraki_mr_packet_loss_upstream_percent`](#meraki-mr-packet-loss-upstream-percent) | 🔢 gauge | MRPerformanceCollector | 8 labels | Upstream packet loss percentage for access point (5-minute window) |
| [`meraki_mr_packets_downstream_lost`](#meraki-mr-packets-downstream-lost) | 🔢 gauge | MRPerformanceCollector | 8 labels | Downstream packets lost by access point (5-minute window) |
| [`meraki_mr_packets_downstream_total`](#meraki-mr-packets-downstream-total) | 🔢 gauge | MRPerformanceCollector | 8 labels | Total downstream packets transmitted by access point (5-minute window) |
| [`meraki_mr_packets_lost_total`](#meraki-mr-packets-lost-total) | 🔢 gauge | MRPerformanceCollector | 8 labels | Total packets lost (upstream + downstream) for access point (5-minute window) |
| [`meraki_mr_packets_total`](#meraki-mr-packets-total) | 🔢 gauge | MRPerformanceCollector | 8 labels | Total packets (upstream + downstream) for access point (5-minute window) |
| [`meraki_mr_packets_upstream_lost`](#meraki-mr-packets-upstream-lost) | 🔢 gauge | MRPerformanceCollector | 8 labels | Upstream packets lost by access point (5-minute window) |
| [`meraki_mr_packets_upstream_total`](#meraki-mr-packets-upstream-total) | 🔢 gauge | MRPerformanceCollector | 8 labels | Total upstream packets received by access point (5-minute window) |
| [`meraki_mr_port_link_negotiation_info`](#meraki-mr-port-link-negotiation-info) | 🔢 gauge | MRPerformanceCollector | 10 labels | Access point port link negotiation information |
| [`meraki_mr_port_link_negotiation_speed_mbps`](#meraki-mr-port-link-negotiation-speed-mbps) | 🔢 gauge | MRPerformanceCollector | 9 labels | Access point port link negotiation speed in Mbps |
| [`meraki_mr_port_poe_info`](#meraki-mr-port-poe-info) | 🔢 gauge | MRPerformanceCollector | 10 labels | Access point port PoE information |
| [`meraki_mr_power_ac_connected`](#meraki-mr-power-ac-connected) | 🔢 gauge | MRPerformanceCollector | 8 labels | Access point AC power connection status (1 = connected, 0 = not connected) |
| [`meraki_mr_power_info`](#meraki-mr-power-info) | 🔢 gauge | MRPerformanceCollector | 9 labels | Access point power information |
| [`meraki_mr_power_poe_connected`](#meraki-mr-power-poe-connected) | 🔢 gauge | MRPerformanceCollector | 8 labels | Access point PoE power connection status (1 = connected, 0 = not connected) |
| [`meraki_mr_radio_broadcasting`](#meraki-mr-radio-broadcasting) | 🔢 gauge | MRWirelessCollector | 10 labels | Access point radio broadcasting status (1 = broadcasting, 0 = not broadcasting) |
| [`meraki_mr_radio_channel`](#meraki-mr-radio-channel) | 🔢 gauge | MRWirelessCollector | 10 labels | Access point radio channel number |
| [`meraki_mr_radio_channel_width_mhz`](#meraki-mr-radio-channel-width-mhz) | 🔢 gauge | MRWirelessCollector | 10 labels | Access point radio channel width in MHz |
| [`meraki_mr_radio_power_dbm`](#meraki-mr-radio-power-dbm) | 🔢 gauge | MRWirelessCollector | 10 labels | Access point radio transmit power in dBm |
| [`meraki_mr_ssid_client_count`](#meraki-mr-ssid-client-count) | 🔢 gauge | MRWirelessCollector | 5 labels | Number of clients connected to SSID over the last day |
| [`meraki_mr_ssid_usage_downstream_mb`](#meraki-mr-ssid-usage-downstream-mb) | 🔢 gauge | MRWirelessCollector | 5 labels | Downstream data usage in MB by SSID over the last day |
| [`meraki_mr_ssid_usage_percentage`](#meraki-mr-ssid-usage-percentage) | 🔢 gauge | MRWirelessCollector | 5 labels | Percentage of total organization data usage by SSID over the last day |
| [`meraki_mr_ssid_usage_total_mb`](#meraki-mr-ssid-usage-total-mb) | 🔢 gauge | MRWirelessCollector | 5 labels | Total data usage in MB by SSID over the last day |
| [`meraki_mr_ssid_usage_upstream_mb`](#meraki-mr-ssid-usage-upstream-mb) | 🔢 gauge | MRWirelessCollector | 5 labels | Upstream data usage in MB by SSID over the last day |
| [`meraki_ms_poe_budget_watts`](#meraki-ms-poe-budget-watts) | 🔢 gauge | MSCollector | 8 labels | Total POE power budget for switch in watts |
| [`meraki_ms_poe_network_total_watthours`](#meraki-ms-poe-network-total-watthours) | 🔢 gauge | MSCollector | 4 labels | Total POE power consumption for all switches in network in watt-hours (Wh) |
| [`meraki_ms_poe_port_power_watthours`](#meraki-ms-poe-port-power-watthours) | 🔢 gauge | MSCollector | 10 labels | Per-port POE power consumption in watt-hours (Wh) over the last 1 hour |
| [`meraki_ms_poe_total_power_watthours`](#meraki-ms-poe-total-power-watthours) | 🔢 gauge | MSCollector | 8 labels | Total POE power consumption for switch in watt-hours (Wh) |
| [`meraki_ms_port_client_count`](#meraki-ms-port-client-count) | 🔢 gauge | MSCollector | 10 labels | Number of clients connected to switch port |
| [`meraki_ms_port_packets_broadcast`](#meraki-ms-port-packets-broadcast) | 🔢 gauge | MSCollector | No labels | Broadcast packets on switch port (5-minute window) |
| [`meraki_ms_port_packets_collisions`](#meraki-ms-port-packets-collisions) | 🔢 gauge | MSCollector | No labels | Collision packets on switch port (5-minute window) |
| [`meraki_ms_port_packets_crcerrors`](#meraki-ms-port-packets-crcerrors) | 🔢 gauge | MSCollector | No labels | CRC align error packets on switch port (5-minute window) |
| [`meraki_ms_port_packets_fragments`](#meraki-ms-port-packets-fragments) | 🔢 gauge | MSCollector | No labels | Fragment packets on switch port (5-minute window) |
| [`meraki_ms_port_packets_multicast`](#meraki-ms-port-packets-multicast) | 🔢 gauge | MSCollector | No labels | Multicast packets on switch port (5-minute window) |
| [`meraki_ms_port_packets_rate_broadcast`](#meraki-ms-port-packets-rate-broadcast) | 🔢 gauge | MSCollector | No labels | Broadcast packet rate on switch port (packets per second, 5-minute average) |
| [`meraki_ms_port_packets_rate_collisions`](#meraki-ms-port-packets-rate-collisions) | 🔢 gauge | MSCollector | No labels | Collision packet rate on switch port (packets per second, 5-minute average) |
| [`meraki_ms_port_packets_rate_crcerrors`](#meraki-ms-port-packets-rate-crcerrors) | 🔢 gauge | MSCollector | No labels | CRC align error packet rate on switch port (packets per second, 5-minute average) |
| [`meraki_ms_port_packets_rate_fragments`](#meraki-ms-port-packets-rate-fragments) | 🔢 gauge | MSCollector | No labels | Fragment packet rate on switch port (packets per second, 5-minute average) |
| [`meraki_ms_port_packets_rate_multicast`](#meraki-ms-port-packets-rate-multicast) | 🔢 gauge | MSCollector | No labels | Multicast packet rate on switch port (packets per second, 5-minute average) |
| [`meraki_ms_port_packets_rate_topologychanges`](#meraki-ms-port-packets-rate-topologychanges) | 🔢 gauge | MSCollector | No labels | Topology change packet rate on switch port (packets per second, 5-minute average) |
| [`meraki_ms_port_packets_rate_total`](#meraki-ms-port-packets-rate-total) | 🔢 gauge | MSCollector | No labels | Total packet rate on switch port (packets per second, 5-minute average) |
| [`meraki_ms_port_packets_topologychanges`](#meraki-ms-port-packets-topologychanges) | 🔢 gauge | MSCollector | No labels | Topology change packets on switch port (5-minute window) |
| [`meraki_ms_port_packets_total`](#meraki-ms-port-packets-total) | 🔢 gauge | MSCollector | No labels | Total packets on switch port (5-minute window) |
| [`meraki_ms_port_status`](#meraki-ms-port-status) | 🔢 gauge | MSCollector | 12 labels | Switch port status (1 = connected, 0 = disconnected) |
| [`meraki_ms_port_traffic_bytes`](#meraki-ms-port-traffic-bytes) | 🔢 gauge | MSCollector | 11 labels | Switch port traffic rate in bytes per second (averaged over 1 hour) |
| [`meraki_ms_port_usage_bytes`](#meraki-ms-port-usage-bytes) | 🔢 gauge | MSCollector | 11 labels | Switch port data usage in bytes over the last 1 hour |
| [`meraki_ms_ports_active_total`](#meraki-ms-ports-active-total) | 🔢 gauge | DeviceCollector | 2 labels | Total number of active switch ports |
| [`meraki_ms_ports_by_link_speed_total`](#meraki-ms-ports-by-link-speed-total) | 🔢 gauge | DeviceCollector | 4 labels | Total number of active switch ports by link speed |
| [`meraki_ms_ports_by_media_total`](#meraki-ms-ports-by-media-total) | 🔢 gauge | DeviceCollector | 4 labels | Total number of switch ports by media type |
| [`meraki_ms_ports_inactive_total`](#meraki-ms-ports-inactive-total) | 🔢 gauge | DeviceCollector | 2 labels | Total number of inactive switch ports |
| [`meraki_ms_power_usage_watts`](#meraki-ms-power-usage-watts) | 🔢 gauge | MSCollector | 8 labels | Switch power usage in watts |
| [`meraki_ms_stp_priority`](#meraki-ms-stp-priority) | 🔢 gauge | MSCollector | 8 labels | Switch STP (Spanning Tree Protocol) priority |
| [`meraki_mt_apparent_power_va`](#meraki-mt-apparent-power-va) | 🔢 gauge | MTSensorCollector | 8 labels | Apparent power in volt-amperes |
| [`meraki_mt_battery_percentage`](#meraki-mt-battery-percentage) | 🔢 gauge | MTSensorCollector | 8 labels | Battery level percentage |
| [`meraki_mt_co2_ppm`](#meraki-mt-co2-ppm) | 🔢 gauge | MTSensorCollector | 8 labels | CO2 level in parts per million |
| [`meraki_mt_current_amps`](#meraki-mt-current-amps) | 🔢 gauge | MTSensorCollector | 8 labels | Current in amperes |
| [`meraki_mt_door_status`](#meraki-mt-door-status) | 🔢 gauge | MTSensorCollector | 8 labels | Door sensor status (1 = open, 0 = closed) |
| [`meraki_mt_downstream_power_enabled`](#meraki-mt-downstream-power-enabled) | 🔢 gauge | MTSensorCollector | 8 labels | Downstream power status (1 = enabled, 0 = disabled) |
| [`meraki_mt_frequency_hz`](#meraki-mt-frequency-hz) | 🔢 gauge | MTSensorCollector | 8 labels | Frequency in hertz |
| [`meraki_mt_humidity_percent`](#meraki-mt-humidity-percent) | 🔢 gauge | MTSensorCollector | 8 labels | Humidity percentage |
| [`meraki_mt_indoor_air_quality_score`](#meraki-mt-indoor-air-quality-score) | 🔢 gauge | MTSensorCollector | 8 labels | Indoor air quality score (0-100) |
| [`meraki_mt_noise_db`](#meraki-mt-noise-db) | 🔢 gauge | MTSensorCollector | 8 labels | Noise level in decibels |
| [`meraki_mt_pm25_ug_m3`](#meraki-mt-pm25-ug-m3) | 🔢 gauge | MTSensorCollector | 8 labels | PM2.5 particulate matter in micrograms per cubic meter |
| [`meraki_mt_power_factor_percent`](#meraki-mt-power-factor-percent) | 🔢 gauge | MTSensorCollector | 8 labels | Power factor percentage |
| [`meraki_mt_real_power_watts`](#meraki-mt-real-power-watts) | 🔢 gauge | MTSensorCollector | 8 labels | Real power in watts |
| [`meraki_mt_remote_lockout_status`](#meraki-mt-remote-lockout-status) | 🔢 gauge | MTSensorCollector | 8 labels | Remote lockout switch status (1 = locked, 0 = unlocked) |
| [`meraki_mt_temperature_celsius`](#meraki-mt-temperature-celsius) | 🔢 gauge | MTSensorCollector | 8 labels | Temperature reading in Celsius |
| [`meraki_mt_tvoc_ppb`](#meraki-mt-tvoc-ppb) | 🔢 gauge | MTSensorCollector | 8 labels | Total volatile organic compounds in parts per billion |
| [`meraki_mt_voltage_volts`](#meraki-mt-voltage-volts) | 🔢 gauge | MTSensorCollector | 8 labels | Voltage in volts |
| [`meraki_mt_water_detected`](#meraki-mt-water-detected) | 🔢 gauge | MTSensorCollector | 8 labels | Water detection status (1 = detected, 0 = not detected) |
| [`meraki_network_bluetooth_clients_total`](#meraki-network-bluetooth-clients-total) | 🔢 gauge | NetworkHealthCollector | 4 labels | Total number of Bluetooth clients detected by MR devices in the last 5 minutes |
| [`meraki_network_channel_utilization_2_4ghz_percent`](#meraki-network-channel-utilization-2-4ghz-percent) | 🔢 gauge | NetworkHealthCollector | 5 labels | Network-wide average 2.4GHz channel utilization percentage |
| [`meraki_network_channel_utilization_5ghz_percent`](#meraki-network-channel-utilization-5ghz-percent) | 🔢 gauge | NetworkHealthCollector | 5 labels | Network-wide average 5GHz channel utilization percentage |
| [`meraki_network_health_alerts_total`](#meraki-network-health-alerts-total) | 🔢 gauge | AlertsCollector | 6 labels | Total number of active network health alerts by category and severity |
| [`meraki_network_wireless_connection_stats_total`](#meraki-network-wireless-connection-stats-total) | 🔢 gauge | NetworkHealthCollector | 5 labels | Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success) |
| [`meraki_network_wireless_download_kbps`](#meraki-network-wireless-download-kbps) | 🔢 gauge | NetworkHealthCollector | 4 labels | Network-wide wireless download bandwidth in kilobits per second |
| [`meraki_network_wireless_upload_kbps`](#meraki-network-wireless-upload-kbps) | 🔢 gauge | NetworkHealthCollector | 4 labels | Network-wide wireless upload bandwidth in kilobits per second |
| [`meraki_org`](#meraki-org) | ℹ️ info | OrganizationCollector | 2 labels | Organization information |
| [`meraki_org_api_requests_by_status`](#meraki-org-api-requests-by-status) | 🔢 gauge | OrganizationCollector | 3 labels | API requests by HTTP status code in the last hour |
| [`meraki_org_api_requests_total`](#meraki-org-api-requests-total) | 🔢 gauge | OrganizationCollector | 2 labels | Total API requests made by the organization in the last hour |
| [`meraki_org_application_usage_downstream_mb`](#meraki-org-application-usage-downstream-mb) | 🔢 gauge | OrganizationCollector | 3 labels | Downstream application usage in MB by category |
| [`meraki_org_application_usage_percentage`](#meraki-org-application-usage-percentage) | 🔢 gauge | OrganizationCollector | 3 labels | Application usage percentage by category |
| [`meraki_org_application_usage_total_mb`](#meraki-org-application-usage-total-mb) | 🔢 gauge | OrganizationCollector | 3 labels | Total application usage in MB by category |
| [`meraki_org_application_usage_upstream_mb`](#meraki-org-application-usage-upstream-mb) | 🔢 gauge | OrganizationCollector | 3 labels | Upstream application usage in MB by category |
| [`meraki_org_clients_total`](#meraki-org-clients-total) | 🔢 gauge | OrganizationCollector | 2 labels | Total number of active clients in the organization (1-hour window) |
| [`meraki_org_configuration_changes_total`](#meraki-org-configuration-changes-total) | 🔢 gauge | ConfigCollector | 2 labels | Total number of configuration changes in the last 24 hours |
| [`meraki_org_devices_availability_total`](#meraki-org-devices-availability-total) | 🔢 gauge | OrganizationCollector | 4 labels | Total number of devices by availability status and product type |
| [`meraki_org_devices_by_model_total`](#meraki-org-devices-by-model-total) | 🔢 gauge | OrganizationCollector | 3 labels | Total number of devices by specific model |
| [`meraki_org_devices_total`](#meraki-org-devices-total) | 🔢 gauge | OrganizationCollector | 3 labels | Total number of devices in the organization |
| [`meraki_org_licenses_expiring`](#meraki-org-licenses-expiring) | 🔢 gauge | OrganizationCollector | 3 labels | Number of licenses expiring within 30 days |
| [`meraki_org_licenses_total`](#meraki-org-licenses-total) | 🔢 gauge | OrganizationCollector | 4 labels | Total number of licenses |
| [`meraki_org_login_security_account_lockout_enabled`](#meraki-org-login-security-account-lockout-enabled) | 🔢 gauge | ConfigCollector | 2 labels | Whether account lockout is enforced (1=enabled, 0=disabled) |
| [`meraki_org_login_security_idle_timeout_enabled`](#meraki-org-login-security-idle-timeout-enabled) | 🔢 gauge | ConfigCollector | 2 labels | Whether idle timeout is enforced (1=enabled, 0=disabled) |
| [`meraki_org_login_security_idle_timeout_minutes`](#meraki-org-login-security-idle-timeout-minutes) | 🔢 gauge | ConfigCollector | 2 labels | Minutes before idle timeout (0 if not set) |
| [`meraki_org_login_security_ip_ranges_enabled`](#meraki-org-login-security-ip-ranges-enabled) | 🔢 gauge | ConfigCollector | 2 labels | Whether login IP ranges are enforced (1=enabled, 0=disabled) |
| [`meraki_org_login_security_minimum_password_length`](#meraki-org-login-security-minimum-password-length) | 🔢 gauge | ConfigCollector | 2 labels | Minimum password length required |
| [`meraki_org_login_security_two_factor_enabled`](#meraki-org-login-security-two-factor-enabled) | 🔢 gauge | ConfigCollector | 2 labels | Whether two-factor authentication is enforced (1=enabled, 0=disabled) |
| [`meraki_org_networks_total`](#meraki-org-networks-total) | 🔢 gauge | OrganizationCollector | 2 labels | Total number of networks in the organization |
| [`meraki_org_packetcaptures_remaining`](#meraki-org-packetcaptures-remaining) | 🔢 gauge | OrganizationCollector | 2 labels | Number of remaining packet captures to process |
| [`meraki_org_packetcaptures_total`](#meraki-org-packetcaptures-total) | 🔢 gauge | OrganizationCollector | 2 labels | Total number of packet captures in the organization |
| [`meraki_org_usage_downstream_kb`](#meraki-org-usage-downstream-kb) | 🔢 gauge | OrganizationCollector | 2 labels | Downstream data usage in KB for the 1-hour window |
| [`meraki_org_usage_total_kb`](#meraki-org-usage-total-kb) | 🔢 gauge | OrganizationCollector | 2 labels | Total data usage in KB for the 1-hour window |
| [`meraki_org_usage_upstream_kb`](#meraki-org-usage-upstream-kb) | 🔢 gauge | OrganizationCollector | 2 labels | Upstream data usage in KB for the 1-hour window |
| [`meraki_sensor_alerts_total`](#meraki-sensor-alerts-total) | 🔢 gauge | AlertsCollector | 5 labels | Total number of sensor alerts in the last hour by metric type |
| [`meraki_wireless_client_capabilities_count`](#meraki-wireless-client-capabilities-count) | 🔢 gauge | ClientsCollector | 5 labels | Count of wireless clients by capability |
| [`meraki_wireless_client_rssi`](#meraki-wireless-client-rssi) | 🔢 gauge | ClientsCollector | 9 labels | Wireless client RSSI (Received Signal Strength Indicator) in dBm |
| [`meraki_wireless_client_snr`](#meraki-wireless-client-snr) | 🔢 gauge | ClientsCollector | 9 labels | Wireless client SNR (Signal-to-Noise Ratio) in dB |

## 📚 Usage Guide

!!! info "Metric Types Explained"
    - 🔢 **Gauge**: Current value that can go up or down (e.g., current temperature, active connections)
    - 📈 **Counter**: Cumulative value that only increases (e.g., total requests, total bytes)
    - ℹ️ **Info**: Metadata with labels but value always 1 (e.g., device information, configuration)

!!! tip "Querying with Labels"
    All metrics include relevant labels for filtering and aggregation. Use label selectors in your queries:
    ```promql
    # Filter by organization
    meraki_device_up{org_name="Production"}

    # Filter by device type
    meraki_device_up{device_model=~"MS.*"}

    # Aggregate across multiple labels
    sum(meraki_device_up) by (org_name, device_model)
    ```

!!! example "Common Query Patterns"
    ```promql
    # Device health overview
    avg(meraki_device_up) by (org_name)

    # Network utilization
    rate(meraki_network_traffic_bytes_total[5m])

    # Alert summary
    sum(meraki_alerts_total) by (severity, type)
    ```

!!! warning "Performance Considerations"
    - Use appropriate time ranges for rate() and increase() functions
    - Consider cardinality when using high-cardinality labels
    - Monitor query performance in production environments

For more information on using these metrics, see the [Overview](overview.md) page.

