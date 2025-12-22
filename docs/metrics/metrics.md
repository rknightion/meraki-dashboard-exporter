# Metrics Reference

This page provides a reference of Prometheus metrics exposed by the Meraki Dashboard Exporter.
Some metrics are conditional (clients, webhooks, or OTEL tracing); notes are shown where relevant.

## Summary

- **Total metrics:** 185
- **Gauges:** 162
- **Counters:** 17
- **Histograms:** 5
- **Info metrics:** 1

## Collector Metrics

### AlertsCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_alerts_active` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `alert_type`, `category_type`, `severity`, `device_type` | Number of active Meraki assurance alerts |  |
| `meraki_alerts_total_by_network` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Total number of active alerts per network |  |
| `meraki_alerts_total_by_severity` | gauge | `org_id`, `org_name`, `severity` | Total number of active alerts by severity |  |
| `meraki_network_health_alerts_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `category`, `severity` | Total number of active network health alerts by category and severity |  |
| `meraki_sensor_alerts_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `metric` | Total number of sensor alerts in the last hour by metric type |  |

### ClientsCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_client_application_usage_recv_kb` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `client_id`, `mac`, `description`, `hostname`, `type` | Kilobytes received by client per application in the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_application_usage_sent_kb` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `client_id`, `mac`, `description`, `hostname`, `type` | Kilobytes sent by client per application in the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_application_usage_total_kb` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `client_id`, `mac`, `description`, `hostname`, `type` | Total kilobytes transferred by client per application in the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_status` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `client_id`, `mac`, `description`, `hostname`, `ssid` | Client online status (1 = online, 0 = offline) | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_usage_recv_kb` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `client_id`, `mac`, `description`, `hostname`, `ssid` | Kilobytes received by client in the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_usage_sent_kb` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `client_id`, `mac`, `description`, `hostname`, `ssid` | Kilobytes sent by client in the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_usage_total_kb` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `client_id`, `mac`, `description`, `hostname`, `ssid` | Total kilobytes transferred by client in the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_clients_per_ssid_count` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `ssid` | Count of clients per SSID | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_clients_per_vlan_count` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `vlan` | Count of clients per VLAN | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_cache_expired` | gauge | — | Number of expired entries in DNS cache | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_cache_total` | gauge | — | Total number of entries in DNS cache | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_cache_valid` | gauge | — | Number of valid entries in DNS cache | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_lookups_cached_total` | counter | — | Total number of DNS lookups served from cache | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_lookups_failed_total` | counter | — | Total number of failed DNS lookups | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_lookups_successful_total` | counter | — | Total number of successful DNS lookups | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_lookups_total` | counter | — | Total number of DNS lookups performed | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_store_networks` | gauge | — | Total number of networks with clients | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_store_total` | gauge | — | Total number of clients in the store | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_wireless_client_capabilities_count` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `type` | Count of wireless clients by capability | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_wireless_client_rssi` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `client_id`, `mac`, `description`, `hostname`, `ssid` | Wireless client RSSI (Received Signal Strength Indicator) in dBm | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_wireless_client_snr` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `client_id`, `mac`, `description`, `hostname`, `ssid` | Wireless client SNR (Signal-to-Noise Ratio) in dB | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |

### ConfigCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_org_configuration_changes_total` | gauge | `org_id`, `org_name` | Total number of configuration changes in the last 24 hours |  |
| `meraki_org_login_security_account_lockout_attempts` | gauge | `org_id`, `org_name` | Number of failed login attempts before lockout (0 if not set) |  |
| `meraki_org_login_security_account_lockout_enabled` | gauge | `org_id`, `org_name` | Whether account lockout is enforced (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_api_ip_restrictions_enabled` | gauge | `org_id`, `org_name` | Whether API key IP restrictions are enabled (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_different_passwords_count` | gauge | `org_id`, `org_name` | Number of different passwords required (0 if not set) |  |
| `meraki_org_login_security_different_passwords_enabled` | gauge | `org_id`, `org_name` | Whether different passwords are enforced (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_idle_timeout_enabled` | gauge | `org_id`, `org_name` | Whether idle timeout is enforced (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_idle_timeout_minutes` | gauge | `org_id`, `org_name` | Minutes before idle timeout (0 if not set) |  |
| `meraki_org_login_security_ip_ranges_enabled` | gauge | `org_id`, `org_name` | Whether login IP ranges are enforced (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_minimum_password_length` | gauge | `org_id`, `org_name` | Minimum password length required |  |
| `meraki_org_login_security_password_expiration_days` | gauge | `org_id`, `org_name` | Number of days before password expires (0 if not set) |  |
| `meraki_org_login_security_password_expiration_enabled` | gauge | `org_id`, `org_name` | Whether password expiration is enforced (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_strong_passwords_enabled` | gauge | `org_id`, `org_name` | Whether strong passwords are enforced (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_two_factor_enabled` | gauge | `org_id`, `org_name` | Whether two-factor authentication is enforced (1=enabled, 0=disabled) |  |

### DeviceCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_device_memory_free_bytes` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `stat` | Device memory free in bytes |  |
| `meraki_device_memory_total_bytes` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Device memory total provisioned in bytes |  |
| `meraki_device_memory_usage_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Device memory usage percentage (maximum from most recent interval) |  |
| `meraki_device_memory_used_bytes` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `stat` | Device memory used in bytes |  |
| `meraki_device_status_info` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `status` | Device status information |  |
| `meraki_device_up` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Device online status (1 = online, 0 = offline) |  |
| `meraki_ms_ports_active_total` | gauge | `org_id`, `org_name` | Total number of active switch ports |  |
| `meraki_ms_ports_by_link_speed_total` | gauge | `org_id`, `org_name`, `media`, `link_speed` | Total number of active switch ports by link speed |  |
| `meraki_ms_ports_by_media_total` | gauge | `org_id`, `org_name`, `media`, `status` | Total number of switch ports by media type |  |
| `meraki_ms_ports_inactive_total` | gauge | `org_id`, `org_name` | Total number of inactive switch ports |  |

### MRClientsCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mr_clients_connected` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Number of clients connected to access point |  |
| `meraki_mr_connection_stats_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `stat_type` | Wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success) |  |

### MRPerformanceCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mr_aggregation_enabled` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Access point port aggregation enabled status (1 = enabled, 0 = disabled) |  |
| `meraki_mr_aggregation_speed_mbps` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Access point total aggregated port speed in Mbps |  |
| `meraki_mr_cpu_load_5min` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Access point CPU load percentage (5-minute average) |  |
| `meraki_mr_network_packet_loss_downstream_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Downstream packet loss percentage for network (5-minute window) |  |
| `meraki_mr_network_packet_loss_total_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Total packet loss percentage for network (5-minute window) |  |
| `meraki_mr_network_packet_loss_upstream_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Upstream packet loss percentage for network (5-minute window) |  |
| `meraki_mr_network_packets_downstream_lost` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Downstream packets lost for network (5-minute window) |  |
| `meraki_mr_network_packets_downstream_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Total downstream packets for network (5-minute window) |  |
| `meraki_mr_network_packets_lost_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Total packets lost (upstream + downstream) for network (5-minute window) |  |
| `meraki_mr_network_packets_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Total packets (upstream + downstream) for network (5-minute window) |  |
| `meraki_mr_network_packets_upstream_lost` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Upstream packets lost for network (5-minute window) |  |
| `meraki_mr_network_packets_upstream_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Total upstream packets for network (5-minute window) |  |
| `meraki_mr_packet_loss_downstream_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Downstream packet loss percentage for access point (5-minute window) |  |
| `meraki_mr_packet_loss_total_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Total packet loss percentage for access point (5-minute window) |  |
| `meraki_mr_packet_loss_upstream_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Upstream packet loss percentage for access point (5-minute window) |  |
| `meraki_mr_packets_downstream_lost` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Downstream packets lost by access point (5-minute window) |  |
| `meraki_mr_packets_downstream_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Total downstream packets transmitted by access point (5-minute window) |  |
| `meraki_mr_packets_lost_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Total packets lost (upstream + downstream) for access point (5-minute window) |  |
| `meraki_mr_packets_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Total packets (upstream + downstream) for access point (5-minute window) |  |
| `meraki_mr_packets_upstream_lost` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Upstream packets lost by access point (5-minute window) |  |
| `meraki_mr_packets_upstream_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Total upstream packets received by access point (5-minute window) |  |
| `meraki_mr_port_link_negotiation_info` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_name`, `duplex` | Access point port link negotiation information |  |
| `meraki_mr_port_link_negotiation_speed_mbps` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_name` | Access point port link negotiation speed in Mbps |  |
| `meraki_mr_port_poe_info` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_name`, `standard` | Access point port PoE information |  |
| `meraki_mr_power_ac_connected` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Access point AC power connection status (1 = connected, 0 = not connected) |  |
| `meraki_mr_power_info` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `mode` | Access point power information |  |
| `meraki_mr_power_poe_connected` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Access point PoE power connection status (1 = connected, 0 = not connected) |  |

### MRWirelessCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mr_radio_broadcasting` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `band`, `radio_index` | Access point radio broadcasting status (1 = broadcasting, 0 = not broadcasting) |  |
| `meraki_mr_radio_channel` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `band`, `radio_index` | Access point radio channel number |  |
| `meraki_mr_radio_channel_width_mhz` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `band`, `radio_index` | Access point radio channel width in MHz |  |
| `meraki_mr_radio_power_dbm` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `band`, `radio_index` | Access point radio transmit power in dBm |  |
| `meraki_mr_ssid_client_count` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `ssid` | Number of clients connected to SSID over the last day |  |
| `meraki_mr_ssid_usage_downstream_mb` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `ssid` | Downstream data usage in MB by SSID over the last day |  |
| `meraki_mr_ssid_usage_percentage` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `ssid` | Percentage of total organization data usage by SSID over the last day |  |
| `meraki_mr_ssid_usage_total_mb` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `ssid` | Total data usage in MB by SSID over the last day |  |
| `meraki_mr_ssid_usage_upstream_mb` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `ssid` | Upstream data usage in MB by SSID over the last day |  |

### MSCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_ms_poe_budget_watts` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Total POE power budget for switch in watts |  |
| `meraki_ms_poe_network_total_watthours` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Total POE power consumption for all switches in network in watt-hours (Wh) |  |
| `meraki_ms_poe_port_power_watthours` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name` | Per-port POE power consumption in watt-hours (Wh) over the last 1 hour |  |
| `meraki_ms_poe_total_power_watthours` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Total POE power consumption for switch in watt-hours (Wh) |  |
| `meraki_ms_port_client_count` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name` | Number of clients connected to switch port |  |
| `meraki_ms_port_packets_broadcast` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Broadcast packets on switch port (5-minute window) |  |
| `meraki_ms_port_packets_collisions` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Collision packets on switch port (5-minute window) |  |
| `meraki_ms_port_packets_crcerrors` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | CRC align error packets on switch port (5-minute window) |  |
| `meraki_ms_port_packets_fragments` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Fragment packets on switch port (5-minute window) |  |
| `meraki_ms_port_packets_multicast` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Multicast packets on switch port (5-minute window) |  |
| `meraki_ms_port_packets_rate_broadcast` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Broadcast packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_rate_collisions` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Collision packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_rate_crcerrors` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | CRC align error packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_rate_fragments` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Fragment packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_rate_multicast` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Multicast packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_rate_topologychanges` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Topology change packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_rate_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Total packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_topologychanges` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Topology change packets on switch port (5-minute window) |  |
| `meraki_ms_port_packets_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Total packets on switch port (5-minute window) |  |
| `meraki_ms_port_status` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `link_speed`, `duplex` | Switch port status (1 = connected, 0 = disconnected) |  |
| `meraki_ms_port_traffic_bytes` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Switch port traffic rate in bytes per second (averaged over 1 hour) |  |
| `meraki_ms_port_usage_bytes` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `port_id`, `port_name`, `direction` | Switch port data usage in bytes over the last 1 hour |  |
| `meraki_ms_power_usage_watts` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Switch power usage in watts |  |
| `meraki_ms_stp_priority` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Switch STP (Spanning Tree Protocol) priority |  |

### MTSensorCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mt_apparent_power_va` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Apparent power in volt-amperes |  |
| `meraki_mt_battery_percentage` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Battery level percentage |  |
| `meraki_mt_co2_ppm` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | CO2 level in parts per million |  |
| `meraki_mt_current_amps` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Current in amperes |  |
| `meraki_mt_door_status` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Door sensor status (1 = open, 0 = closed) |  |
| `meraki_mt_downstream_power_enabled` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Downstream power status (1 = enabled, 0 = disabled) |  |
| `meraki_mt_frequency_hz` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Frequency in hertz |  |
| `meraki_mt_humidity_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Humidity percentage |  |
| `meraki_mt_indoor_air_quality_score` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Indoor air quality score (0-100) |  |
| `meraki_mt_noise_db` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Noise level in decibels |  |
| `meraki_mt_pm25_ug_m3` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | PM2.5 particulate matter in micrograms per cubic meter |  |
| `meraki_mt_power_factor_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Power factor percentage |  |
| `meraki_mt_real_power_watts` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Real power in watts |  |
| `meraki_mt_remote_lockout_status` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Remote lockout switch status (1 = locked, 0 = unlocked) |  |
| `meraki_mt_temperature_celsius` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Temperature reading in Celsius |  |
| `meraki_mt_tvoc_ppb` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Total volatile organic compounds in parts per billion |  |
| `meraki_mt_voltage_volts` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Voltage in volts |  |
| `meraki_mt_water_detected` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type` | Water detection status (1 = detected, 0 = not detected) |  |

### NetworkHealthCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_ap_channel_utilization_2_4ghz_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `utilization_type` | 2.4GHz channel utilization percentage per AP |  |
| `meraki_ap_channel_utilization_5ghz_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `serial`, `name`, `model`, `device_type`, `utilization_type` | 5GHz channel utilization percentage per AP |  |
| `meraki_network_bluetooth_clients_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Total number of Bluetooth clients detected by MR devices in the last 5 minutes |  |
| `meraki_network_channel_utilization_2_4ghz_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `utilization_type` | Network-wide average 2.4GHz channel utilization percentage |  |
| `meraki_network_channel_utilization_5ghz_percent` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `utilization_type` | Network-wide average 5GHz channel utilization percentage |  |
| `meraki_network_wireless_connection_stats_total` | gauge | `org_id`, `org_name`, `network_id`, `network_name`, `stat_type` | Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success) |  |
| `meraki_network_wireless_download_kbps` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Network-wide wireless download bandwidth in kilobits per second |  |
| `meraki_network_wireless_upload_kbps` | gauge | `org_id`, `org_name`, `network_id`, `network_name` | Network-wide wireless upload bandwidth in kilobits per second |  |

### OrganizationCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_org` | info | `org_id`, `org_name` | Organization information |  |
| `meraki_org_api_requests_by_status` | gauge | `org_id`, `org_name`, `status_code` | API requests by HTTP status code in the last hour |  |
| `meraki_org_api_requests_total` | gauge | `org_id`, `org_name` | Total API requests made by the organization in the last hour |  |
| `meraki_org_application_usage_downstream_mb` | gauge | `org_id`, `org_name`, `category` | Downstream application usage in MB by category |  |
| `meraki_org_application_usage_percentage` | gauge | `org_id`, `org_name`, `category` | Application usage percentage by category |  |
| `meraki_org_application_usage_total_mb` | gauge | `org_id`, `org_name`, `category` | Total application usage in MB by category |  |
| `meraki_org_application_usage_upstream_mb` | gauge | `org_id`, `org_name`, `category` | Upstream application usage in MB by category |  |
| `meraki_org_clients_total` | gauge | `org_id`, `org_name` | Total number of active clients in the organization (1-hour window) |  |
| `meraki_org_devices_availability_total` | gauge | `org_id`, `org_name`, `status`, `product_type` | Total number of devices by availability status and product type |  |
| `meraki_org_devices_by_model_total` | gauge | `org_id`, `org_name`, `model` | Total number of devices by specific model |  |
| `meraki_org_devices_total` | gauge | `org_id`, `org_name`, `device_type` | Total number of devices in the organization |  |
| `meraki_org_licenses_expiring` | gauge | `org_id`, `org_name`, `license_type` | Number of licenses expiring within 30 days |  |
| `meraki_org_licenses_total` | gauge | `org_id`, `org_name`, `license_type`, `status` | Total number of licenses |  |
| `meraki_org_networks_total` | gauge | `org_id`, `org_name` | Total number of networks in the organization |  |
| `meraki_org_packetcaptures_remaining` | gauge | `org_id`, `org_name` | Number of remaining packet captures to process |  |
| `meraki_org_packetcaptures_total` | gauge | `org_id`, `org_name` | Total number of packet captures in the organization |  |
| `meraki_org_usage_downstream_kb` | gauge | `org_id`, `org_name` | Downstream data usage in KB for the 1-hour window |  |
| `meraki_org_usage_total_kb` | gauge | `org_id`, `org_name` | Total data usage in KB for the 1-hour window |  |
| `meraki_org_usage_upstream_kb` | gauge | `org_id`, `org_name` | Upstream data usage in KB for the 1-hour window |  |

## Internal & Platform Metrics

### AsyncMerakiClient

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_api_rate_limit_remaining` | gauge | `org_id` | Remaining rate limit for Meraki API |  |
| `meraki_api_rate_limit_total` | gauge | `org_id` | Total rate limit for Meraki API |  |
| `meraki_api_request_duration_seconds` | histogram | `endpoint`, `method`, `status_code` | Duration of Meraki API requests in seconds |  |
| `meraki_api_requests_total` | counter | `endpoint`, `method`, `status_code` | Total number of Meraki API requests |  |
| `meraki_api_retry_attempts_total` | counter | `endpoint`, `retry_reason` | Total number of API retry attempts |  |

### CardinalityMonitor

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_cardinality_analysis_duration_seconds` | gauge | — | Time taken to complete cardinality analysis |  |
| `meraki_cardinality_analyzed_metrics_total` | gauge | — | Total number of metrics analyzed in last run |  |
| `meraki_cardinality_warnings_total` | counter | `metric_name`, `severity` | Number of cardinality warnings triggered |  |
| `meraki_total_series` | gauge | — | Total number of time series across all metrics |  |

### CollectorManager

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_collection_errors_total` | counter | `collector`, `tier`, `error_type` | Total number of collection errors by collector and phase |  |
| `meraki_collector_failure_streak` | gauge | `collector`, `tier` | Consecutive failures for each collector since last success |  |
| `meraki_collector_last_success_age_seconds` | gauge | `collector`, `tier` | Seconds since the last successful collection for each collector |  |
| `meraki_org_collection_wait_time_seconds` | histogram | `collector`, `org_id` | Time an organization spends waiting for semaphore slot before collection starts |  |
| `meraki_parallel_collections_active` | gauge | `collector`, `tier` | Number of parallel organization collections currently active |  |

### MetricCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_collector_api_calls_total` | counter | `collector`, `tier`, `endpoint` | Total number of API calls made by collectors |  |
| `meraki_collector_duration_seconds` | histogram | `collector`, `tier` | Time spent collecting metrics |  |
| `meraki_collector_errors_total` | counter | `collector`, `tier`, `error_type` | Total number of collector errors |  |
| `meraki_collector_last_success_timestamp_seconds` | gauge | `collector`, `tier` | Unix timestamp of last successful collection |  |

### MetricExpirationManager

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_collection_errors_total_expired` | counter | `collector`, `tier` | Total number of metrics expired due to TTL |  |
| `meraki_inventory_cache_size_tracked_metrics` | gauge | `collector` | Number of metrics currently tracked for expiration |  |

### SpanMetricsProcessor

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_span_duration_seconds` | histogram | `operation`, `collector`, `endpoint` | Request duration tracked via spans | Requires OTEL tracing enabled |
| `meraki_span_errors_total` | counter | `operation`, `collector`, `endpoint`, `error_type` | Total number of errors tracked via spans | Requires OTEL tracing enabled |
| `meraki_span_requests_total` | counter | `operation`, `collector`, `endpoint`, `status` | Total number of requests tracked via spans | Requires OTEL tracing enabled |

### WebhookHandler

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_webhook_events_failed_total` | counter | — | Total webhook events that failed processing | Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true |
| `meraki_webhook_events_processed_total` | counter | — | Total webhook events successfully processed | Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true |
| `meraki_webhook_events_received_total` | counter | — | Total webhook events received | Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true |
| `meraki_webhook_processing_duration_seconds` | histogram | — | Time spent processing webhook events | Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true |
| `meraki_webhook_validation_failures_total` | counter | — | Total webhook validation failures | Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true |

## Metric Types

- **Gauge**: Current value that can go up or down
- **Counter**: Cumulative value that only increases
- **Histogram**: Distribution of observations across buckets
- **Info**: Metadata metric with labels and value 1

