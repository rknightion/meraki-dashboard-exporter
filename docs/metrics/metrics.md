# Metrics Reference

This page provides a reference of Prometheus metrics exposed by the Meraki Dashboard Exporter.
Some metrics are conditional (clients or webhooks); notes are shown where relevant.

## Summary

- **Total metrics:** 311
- **Gauges:** 288
- **Counters:** 19
- **Histograms:** 3
- **Info metrics:** 1

## Collector Metrics

### AirMarshalCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mr_air_marshal_bssids_by_threat_type_count` | gauge | `threat_type` | Number of Air Marshal BSSIDs observed by threat type, last hour (rogue/spoof/other; entries without a threat-type field are not counted) |  |
| `meraki_mr_air_marshal_bssids_count` | gauge | `org_id`, `network_id` | Total number of BSSIDs across all Air Marshal SSID entries, last hour |  |
| `meraki_mr_air_marshal_contained_bssids_count` | gauge | `org_id`, `network_id` | Number of Air Marshal BSSIDs currently contained, last hour |  |
| `meraki_mr_air_marshal_ssids_count` | gauge | `org_id`, `network_id` | Number of foreign SSID entries observed by Air Marshal over the last hour |  |
| `meraki_mr_air_marshal_wired_detected_count` | gauge | `org_id`, `network_id` | Number of Air Marshal SSID entries also detected on the wired network, last hour |  |

### AlertsCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_alerts_active` | gauge | `org_id`, `network_id`, `alert_type`, `category_type`, `severity`, `device_type` | Number of active Meraki assurance alerts |  |
| `meraki_alerts_by_network` | gauge | `org_id`, `network_id` | Number of active alerts per network |  |
| `meraki_alerts_by_severity` | gauge | `org_id`, `severity` | Number of active alerts by severity |  |
| `meraki_network_health_alerts` | gauge | `org_id`, `network_id`, `category`, `severity` | Number of active network health alerts by category and severity |  |
| `meraki_sensor_alerts_count` | gauge | `org_id`, `network_id`, `metric` | Number of sensor alerts in the last hour by metric type |  |

### ClientsCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_client_application_usage_recv_bytes` | gauge | `org_id`, `network_id`, `client_id`, `type` | Bytes received by client per application in the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_application_usage_sent_bytes` | gauge | `org_id`, `network_id`, `client_id`, `type` | Bytes sent by client per application in the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_application_usage_total_bytes` | gauge | `org_id`, `network_id`, `client_id`, `type` | Total bytes transferred by client per application in the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_info` | gauge | `org_id`, `network_id`, `client_id`, `mac`, `description`, `hostname`, `ssid` | Client information join metric (client_id -> mac/description/hostname/ssid); value is always 1. Labels churn (old series expire) when a client's hostname/description/SSID changes. | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_status` | gauge | `org_id`, `network_id`, `client_id` | Client online status (1 = online, 0 = offline) | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_usage_recv_bytes` | gauge | `org_id`, `network_id`, `client_id` | Bytes received by client in the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_usage_sent_bytes` | gauge | `org_id`, `network_id`, `client_id` | Bytes sent by client in the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_client_usage_total_bytes` | gauge | `org_id`, `network_id`, `client_id` | Total bytes transferred by client in the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_clients_per_ssid_count` | gauge | `org_id`, `network_id`, `ssid` | Count of clients per SSID, over the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_clients_per_vlan_count` | gauge | `org_id`, `network_id`, `vlan` | Count of clients per VLAN, over the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_cache_expired` | gauge | — | Number of expired entries in DNS cache | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_cache_hit_ratio` | gauge | — | Ratio of reverse-DNS lookups served from cache (0..1), cumulative over process lifetime | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_cache_total` | gauge | — | Total number of entries in DNS cache | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_cache_valid` | gauge | — | Number of valid entries in DNS cache | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_lookups_cached_total` | counter | — | Total number of DNS lookups served from cache | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_lookups_failed_total` | counter | — | Total number of failed DNS lookups | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_lookups_successful_total` | counter | — | Total number of successful DNS lookups | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_lookups_total` | counter | — | Total number of DNS lookups performed | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_dns_resolution_seconds_total` | counter | — | Cumulative seconds spent performing reverse-DNS lookups (excludes cache hits) | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_store_networks` | gauge | — | Total number of networks with clients | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_client_store_total` | gauge | — | Total number of clients in the store | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_exporter_clients_over_cap` | gauge | `org_id`, `network_id` | Clients excluded from metric emission in the most recent cycle because the per-network or global client cap was reached (0 = within caps) | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_wireless_client_capabilities_count` | gauge | `org_id`, `network_id`, `type` | Count of wireless clients by capability, over the last hour | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_wireless_client_rssi` | gauge | `org_id`, `network_id`, `client_id` | Wireless client RSSI (Received Signal Strength Indicator) in dBm, most recent 5-min sample; collected only when MERAKI_EXPORTER_CLIENTS__SIGNAL_QUALITY_ENABLED=true | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |
| `meraki_wireless_client_snr` | gauge | `org_id`, `network_id`, `client_id` | Wireless client SNR (Signal-to-Noise Ratio) in dB, most recent 5-min sample; collected only when MERAKI_EXPORTER_CLIENTS__SIGNAL_QUALITY_ENABLED=true | Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true |

### ConfigCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_org_admins` | gauge | `org_id`, `authentication_method`, `account_status` | Number of org dashboard admins by authentication method and account status |  |
| `meraki_org_admins_two_factor_enabled` | gauge | `org_id` | Number of org dashboard admins with two-factor auth enabled |  |
| `meraki_org_configuration_changes_count` | gauge | `org_id` | Number of configuration changes observed in the last 24 hours (fetch timespan=86400s) |  |
| `meraki_org_login_security_account_lockout_attempts` | gauge | `org_id` | Number of failed login attempts before lockout (0 if not set) |  |
| `meraki_org_login_security_account_lockout_enabled` | gauge | `org_id` | Whether account lockout is enforced (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_api_ip_restrictions_enabled` | gauge | `org_id` | Whether API key IP restrictions are enabled (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_different_passwords_count` | gauge | `org_id` | Number of different passwords required (0 if not set) |  |
| `meraki_org_login_security_different_passwords_enabled` | gauge | `org_id` | Whether different passwords are enforced (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_idle_timeout_enabled` | gauge | `org_id` | Whether idle timeout is enforced (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_idle_timeout_seconds` | gauge | `org_id` | Seconds before idle timeout (0 if not set) |  |
| `meraki_org_login_security_ip_ranges_enabled` | gauge | `org_id` | Whether login IP ranges are enforced (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_minimum_password_length` | gauge | `org_id` | Minimum password length required |  |
| `meraki_org_login_security_password_expiration_enabled` | gauge | `org_id` | Whether password expiration is enforced (1=enabled, 0=disabled) |  |
| `meraki_org_login_security_password_expiration_seconds` | gauge | `org_id` | Seconds before password expires (0 if not set) |  |
| `meraki_org_login_security_two_factor_enabled` | gauge | `org_id` | Whether two-factor authentication is enforced (1=enabled, 0=disabled) |  |
| `meraki_org_saml_enabled` | gauge | `org_id` | Whether SAML SSO is enabled for the organization (1=enabled, 0=disabled) |  |
| `meraki_org_saml_idps` | gauge | `org_id` | Number of SAML IdPs configured for the organization |  |

### DeviceCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_device_memory_free_bytes` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `stat` | Device memory free in bytes (derived from the API's binary KiB value x1024), 5-min window |  |
| `meraki_device_memory_total_bytes` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Device memory total provisioned in bytes (derived from the API's binary KiB value x1024) |  |
| `meraki_device_memory_usage_percent` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Device memory usage percentage (maximum from most recent interval) |  |
| `meraki_device_memory_used_bytes` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `stat` | Device memory used in bytes (derived from the API's binary KiB value x1024), 5-min window |  |
| `meraki_device_status_info` | gauge | `org_id`, `network_id`, `serial`, `name`, `model`, `device_type`, `status` | Device status information |  |
| `meraki_device_up` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Device online status (1 = online, 0 = offline) |  |

### LatencyStatsCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mr_device_latency_seconds` | gauge | `org_id`, `network_id`, `serial`, `traffic_class` | MR access point average wireless latency in seconds by traffic class, 1-h window |  |
| `meraki_mr_network_client_latency_seconds` | gauge | `org_id`, `network_id`, `traffic_class` | Network-wide average wireless client latency in seconds by traffic class, 1-h window |  |

### MGCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mg_cellular_bands` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `slot`, `connection_type`, `status` | Count of cellular bands in a given state, per SIM slot and radio access technology |  |
| `meraki_mg_serving_cell_info` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `cell_id`, `tac` | MG cellular gateway current serving cell tower info (1 = present) |  |
| `meraki_mg_uplink_roaming` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `interface` | MG cellular gateway uplink roaming status (1 = roaming, 0 = home) |  |
| `meraki_mg_uplink_signal_rsrp_dbm` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `interface` | MG cellular gateway uplink RSRP signal strength in dBm |  |
| `meraki_mg_uplink_signal_rsrq_db` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `interface` | MG cellular gateway uplink RSRQ signal quality in dB |  |
| `meraki_mg_uplink_status_info` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `interface`, `status`, `provider`, `connection_type`, `signal_type`, `roaming_status`, `apn`, `ip` | MG cellular gateway uplink status info (1 = present) |  |

### MRClientsCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mr_clients_connected` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Number of clients connected to access point |  |
| `meraki_mr_connection_stats_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `stat_type` | Wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success) |  |

### MRFirewallCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mr_ssid_allow_lan_access` | gauge | `org_id`, `network_id`, `ssid` | Whether wireless clients on this SSID may access the LAN (1 = allowed, 0 = blocked) |  |
| `meraki_mr_ssid_firewall_rules` | gauge | `org_id`, `network_id`, `ssid`, `rule_type` | Number of user-defined SSID firewall rules by type (excludes the implicit default rule) |  |

### MRPerformanceCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mr_aggregation_enabled` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Access point port aggregation enabled status (1 = enabled, 0 = disabled) |  |
| `meraki_mr_aggregation_speed_mbps` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Access point total aggregated port speed in Mbps |  |
| `meraki_mr_cpu_load_5min` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Access point CPU load percentage (5-minute average) |  |
| `meraki_mr_network_packet_loss_downstream_percent` | gauge | `org_id`, `network_id` | Downstream packet loss percentage for network (5-minute window) |  |
| `meraki_mr_network_packet_loss_total_percent` | gauge | `org_id`, `network_id` | Total packet loss percentage for network (5-minute window) |  |
| `meraki_mr_network_packet_loss_upstream_percent` | gauge | `org_id`, `network_id` | Upstream packet loss percentage for network (5-minute window) |  |
| `meraki_mr_network_packets_count` | gauge | `org_id`, `network_id` | Total packets (upstream + downstream) for network (5-minute window) |  |
| `meraki_mr_network_packets_downstream_count` | gauge | `org_id`, `network_id` | Total downstream packets for network (5-minute window) |  |
| `meraki_mr_network_packets_downstream_lost_count` | gauge | `org_id`, `network_id` | Downstream packets lost for network (5-minute window) |  |
| `meraki_mr_network_packets_lost_count` | gauge | `org_id`, `network_id` | Total packets lost (upstream + downstream) for network (5-minute window) |  |
| `meraki_mr_network_packets_upstream_count` | gauge | `org_id`, `network_id` | Total upstream packets for network (5-minute window) |  |
| `meraki_mr_network_packets_upstream_lost_count` | gauge | `org_id`, `network_id` | Upstream packets lost for network (5-minute window) |  |
| `meraki_mr_packet_loss_downstream_percent` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Downstream packet loss percentage for access point (5-minute window) |  |
| `meraki_mr_packet_loss_total_percent` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Total packet loss percentage for access point (5-minute window) |  |
| `meraki_mr_packet_loss_upstream_percent` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Upstream packet loss percentage for access point (5-minute window) |  |
| `meraki_mr_packets_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Total packets (upstream + downstream) for access point (5-minute window) |  |
| `meraki_mr_packets_downstream_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Total downstream packets transmitted by access point (5-minute window) |  |
| `meraki_mr_packets_downstream_lost_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Downstream packets lost by access point (5-minute window) |  |
| `meraki_mr_packets_lost_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Total packets lost (upstream + downstream) for access point (5-minute window) |  |
| `meraki_mr_packets_upstream_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Total upstream packets received by access point (5-minute window) |  |
| `meraki_mr_packets_upstream_lost_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Upstream packets lost by access point (5-minute window) |  |
| `meraki_mr_port_link_negotiation_info` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_name`, `duplex` | Access point port link negotiation information |  |
| `meraki_mr_port_link_negotiation_speed_mbps` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_name` | Access point port link negotiation speed in Mbps |  |
| `meraki_mr_port_poe_info` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_name`, `standard` | Access point port PoE information |  |
| `meraki_mr_power_ac_connected` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Access point AC power connection status (1 = connected, 0 = not connected) |  |
| `meraki_mr_power_info` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `mode` | Access point power information |  |
| `meraki_mr_power_poe_connected` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Access point PoE power connection status (1 = connected, 0 = not connected) |  |

### MRRfProfilesCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mr_rf_profile_info` | gauge | `org_id`, `network_id`, `serial`, `rf_profile_id`, `rf_profile_name`, `is_default` | AP RF profile assignment (join metric: serial -> rf_profile_id/name; value 1) |  |

### MRWirelessCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mr_radio_broadcasting` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `band`, `radio_index` | Access point radio broadcasting status (1 = broadcasting, 0 = not broadcasting) |  |
| `meraki_mr_radio_channel` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `band`, `radio_index` | Access point radio channel number |  |
| `meraki_mr_radio_channel_width_mhz` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `band`, `radio_index` | Access point radio channel width in MHz |  |
| `meraki_mr_radio_power_dbm` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `band`, `radio_index` | Access point radio transmit power in dBm |  |
| `meraki_mr_ssid_client_count` | gauge | `org_id`, `ssid` | Number of clients connected to SSID over the last day |  |
| `meraki_mr_ssid_usage_downstream_bytes` | gauge | `org_id`, `ssid` | Downstream data usage in bytes by SSID over the last day |  |
| `meraki_mr_ssid_usage_percent` | gauge | `org_id`, `ssid` | Percentage of total organization data usage by SSID over the last day |  |
| `meraki_mr_ssid_usage_total_bytes` | gauge | `org_id`, `ssid` | Total data usage in bytes by SSID over the last day |  |
| `meraki_mr_ssid_usage_upstream_bytes` | gauge | `org_id`, `ssid` | Upstream data usage in bytes by SSID over the last day |  |

### MSCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_ms_dai_supported` | gauge | `org_id`, `network_id`, `serial` | Switch supports Dynamic ARP Inspection (1 = supported, 0 = not supported) |  |
| `meraki_ms_dai_trusted_port_configured` | gauge | `org_id`, `network_id`, `serial` | Switch has at least one Dynamic ARP Inspection trusted port configured (1 = configured, 0 = not configured) |  |
| `meraki_ms_dhcp_servers_seen_count` | gauge | `org_id`, `network_id`, `is_allowed` | Number of DHCPv4 servers seen on the network by allow-list status (1-day window, resets each collection cycle) |  |
| `meraki_ms_link_aggregation_member` | gauge | `org_id`, `network_id`, `lag_id`, `serial`, `port_id` | Switch port is a member of a link aggregation group (value 1) |  |
| `meraki_ms_link_aggregations` | gauge | `org_id`, `network_id` | Number of link aggregation (LACP) groups configured in the network |  |
| `meraki_ms_org_poe_draw_watts` | gauge | `org_id` | Organization-wide switch PoE power draw in watts (most recent history bucket; lags real-time by ~20 minutes) |  |
| `meraki_ms_poe_budget_watts` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Total POE power budget for switch in watts |  |
| `meraki_ms_poe_network_total_energy_joules` | gauge | `org_id`, `network_id` | Total POE energy consumption for all switches in network in joules |  |
| `meraki_ms_poe_port_energy_joules` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id` | Per-port POE energy consumption in joules over the last 1 hour |  |
| `meraki_ms_poe_total_energy_joules` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Total POE energy consumption for switch in joules |  |
| `meraki_ms_port_8021x_active` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id` | Switch port secure-port (802.1X) active state (1 = active, 0 = inactive) |  |
| `meraki_ms_port_8021x_status` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `status` | Switch port 802.1X authentication status (1 = currently active for this status) |  |
| `meraki_ms_port_client_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id` | Number of clients connected to switch port |  |
| `meraki_ms_port_error_active` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `error_type` | Active switch port errors (1 = currently active for this error_type) |  |
| `meraki_ms_port_info` | gauge | `org_id`, `network_id`, `serial`, `port_id`, `port_name` | Switch port info (value 1); join port_name via on(serial, port_id) |  |
| `meraki_ms_port_neighbor_present` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `type` | Switch port has an advertised CDP/LLDP neighbor this cycle (value 1; series absent when no neighbor is advertised via this protocol) |  |
| `meraki_ms_port_packets_broadcast_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Broadcast packets on switch port (5-minute window) |  |
| `meraki_ms_port_packets_collisions_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Collision packets on switch port (5-minute window) |  |
| `meraki_ms_port_packets_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Total packets on switch port (5-minute window) |  |
| `meraki_ms_port_packets_crcerrors_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | CRC align error packets on switch port (5-minute window) |  |
| `meraki_ms_port_packets_fragments_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Fragment packets on switch port (5-minute window) |  |
| `meraki_ms_port_packets_multicast_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Multicast packets on switch port (5-minute window) |  |
| `meraki_ms_port_packets_rate` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Total packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_rate_broadcast` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Broadcast packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_rate_collisions` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Collision packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_rate_crcerrors` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | CRC align error packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_rate_fragments` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Fragment packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_rate_multicast` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Multicast packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_rate_topologychanges` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Topology change packet rate on switch port (packets per second, 5-minute average) |  |
| `meraki_ms_port_packets_topologychanges_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Topology change packets on switch port (5-minute window) |  |
| `meraki_ms_port_status` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `link_speed`, `duplex` | Switch port status (1 = connected, 0 = disconnected) |  |
| `meraki_ms_port_stp_state` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `state` | Switch port STP state (1 = currently active for this state) |  |
| `meraki_ms_port_traffic_bytes_per_second` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Switch port traffic rate in bytes per second (averaged over 1 hour) |  |
| `meraki_ms_port_usage_bytes` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `direction` | Switch port data usage in bytes (decimal KB x1000) over the last 1 hour |  |
| `meraki_ms_port_warning_active` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `port_id`, `warning_type` | Active switch port warnings (1 = currently active for this warning_type) |  |
| `meraki_ms_ports_active` | gauge | `org_id` | Number of active switch ports |  |
| `meraki_ms_ports_by_link_speed` | gauge | `org_id`, `media`, `link_speed` | Number of active switch ports by link speed |  |
| `meraki_ms_ports_by_media` | gauge | `org_id`, `media`, `status` | Number of switch ports by media type |  |
| `meraki_ms_ports_inactive` | gauge | `org_id` | Number of inactive switch ports |  |
| `meraki_ms_power_usage_watts` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Switch power usage in watts |  |
| `meraki_ms_stp_priority` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Switch STP (Spanning Tree Protocol) priority |  |

### MSPowerCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_ms_power_supply_status` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `slot`, `psu_serial`, `psu_model`, `status` | MS/rackmount power-supply module status (1 = reported this cycle) |  |

### MSStackCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_ms_stack_member_status` | gauge | `org_id`, `network_id`, `stack_id`, `serial`, `role` | Switch stack member status (1=present/online, 0=absent/offline) |  |
| `meraki_ms_stack_members` | gauge | `org_id`, `network_id`, `stack_id` | Number of members in switch stack |  |

### MTSensorAlertsCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mt_alert_profiles` | gauge | `org_id`, `network_id` | Count of configured MT sensor alert profiles per network |  |
| `meraki_mt_alerting_sensors_count` | gauge | `org_id`, `network_id`, `metric` | Count of currently-alerting MT sensors per network per metric |  |
| `meraki_mt_related_device_info` | gauge | `org_id`, `network_id`, `sensor_serial`, `related_serial`, `product_type` | MT sensor to related-device link info (1 = present) |  |

### MTSensorCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mt_apparent_power_va` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Apparent power in volt-amperes |  |
| `meraki_mt_battery_percent` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Battery level percentage |  |
| `meraki_mt_button_last_press_timestamp_seconds` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `press_type` | Unix timestamp (seconds) of the last observed press via polling; individual presses between polls are not guaranteed to be captured - webhook sensorAlert events are the reliable path |  |
| `meraki_mt_co2_ppm` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | CO2 level in parts per million |  |
| `meraki_mt_current_amps` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Current in amperes |  |
| `meraki_mt_door_status` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Door sensor status (1 = open, 0 = closed) |  |
| `meraki_mt_downstream_power_enabled` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Downstream power status (1 = enabled, 0 = disabled) |  |
| `meraki_mt_frequency_hz` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Frequency in hertz |  |
| `meraki_mt_gateway_last_connected_timestamp_seconds` | gauge | `org_id`, `network_id`, `serial`, `gateway_serial` | MT sensor-to-gateway last-connected Unix timestamp (seconds) |  |
| `meraki_mt_gateway_rssi` | gauge | `org_id`, `network_id`, `serial`, `gateway_serial` | MT sensor-to-gateway RSSI (dBm) |  |
| `meraki_mt_humidity_percent` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Humidity percentage |  |
| `meraki_mt_indoor_air_quality_score` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Indoor air quality score (0-100) |  |
| `meraki_mt_no2_ppb` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | NO2 (nitrogen dioxide) concentration in parts per billion |  |
| `meraki_mt_noise_db` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Noise level in decibels |  |
| `meraki_mt_o3_ppb` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | O3 (ozone) concentration in parts per billion |  |
| `meraki_mt_pm10_ug_m3` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | PM10 particulate matter in micrograms per cubic meter |  |
| `meraki_mt_pm25_ug_m3` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | PM2.5 particulate matter in micrograms per cubic meter |  |
| `meraki_mt_power_factor_percent` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Power factor percentage |  |
| `meraki_mt_real_power_watts` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Real power in watts |  |
| `meraki_mt_remote_lockout_status` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Remote lockout switch status (1 = locked, 0 = unlocked) |  |
| `meraki_mt_temperature_celsius` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Temperature reading in Celsius |  |
| `meraki_mt_tvoc_ppb` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Total volatile organic compounds in parts per billion |  |
| `meraki_mt_voltage_volts` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Voltage in volts |  |
| `meraki_mt_water_detected` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Water detection status (1 = detected, 0 = not detected) |  |

### MVCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mv_analytics_zones` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Number of configured analytics zones on the MV camera |  |
| `meraki_mv_audio_recording_enabled` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Whether audio recording is enabled (1 = enabled) |  |
| `meraki_mv_motion_based_retention_enabled` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Whether motion-based retention is enabled (1 = enabled) |  |
| `meraki_mv_onboarding_status` | gauge | `org_id`, `network_id`, `serial`, `status` | MV camera onboarding status (1 = current status; bounded enum, unknown values normalize to 'other') |  |
| `meraki_mv_people_count` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `zone_id` | Current person count reported by MV camera analytics zone |  |
| `meraki_mv_quality_retention_info` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `quality`, `resolution`, `profile_id` | MV camera quality and retention configuration info (1 = present) |  |
| `meraki_mv_restricted_bandwidth_mode_enabled` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Whether restricted bandwidth mode is enabled (1 = enabled) |  |
| `meraki_mv_sense_enabled` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Whether MV Sense is enabled on the camera (1 = enabled) |  |
| `meraki_mv_sense_mqtt_broker_configured` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | Whether an MQTT broker is configured for MV Sense (1 = configured) |  |
| `meraki_mv_zone_info` | gauge | `org_id`, `network_id`, `serial`, `zone_id`, `zone_name` | MV camera analytics zone ID to zone name mapping (1 = present) |  |

### MXCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mx_dhcp_subnet_free_ips` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `subnet`, `vlan` | Number of free IPs within a DHCP-served subnet on this MX |  |
| `meraki_mx_dhcp_subnet_used_ips` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `subnet`, `vlan` | Number of IPs in use within a DHCP-served subnet on this MX |  |
| `meraki_mx_performance_score` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type` | MX appliance performance score (0-100) |  |
| `meraki_mx_uplink_info` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `interface`, `status` | MX appliance uplink status info (1 = present) |  |

### MXFirewallCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mx_content_filtering_allowed_url_patterns` | gauge | `org_id`, `network_id` | Number of allowed URL patterns configured for content filtering |  |
| `meraki_mx_content_filtering_blocked_categories` | gauge | `org_id`, `network_id` | Number of blocked URL categories configured for content filtering |  |
| `meraki_mx_content_filtering_blocked_url_patterns` | gauge | `org_id`, `network_id` | Number of blocked URL patterns configured for content filtering |  |
| `meraki_mx_firewall_default_policy` | gauge | `org_id`, `network_id` | Firewall default policy for L3 rules (1=allow, 0=deny) |  |
| `meraki_mx_firewall_rules` | gauge | `org_id`, `network_id`, `rule_type` | Number of user-defined firewall rules by type (excludes default rule) |  |
| `meraki_mx_ids_mode` | gauge | `mode` | IDS/IPS mode one-hot indicator (1=active mode for this network) |  |
| `meraki_mx_ids_ruleset` | gauge | `ruleset` | IDS/IPS ruleset one-hot indicator (1=active ruleset for this network) |  |
| `meraki_mx_malware_allowed_files` | gauge | `org_id`, `network_id` | Number of files excluded from Advanced Malware Protection scanning |  |
| `meraki_mx_malware_allowed_urls` | gauge | `org_id`, `network_id` | Number of URLs excluded from Advanced Malware Protection scanning |  |
| `meraki_mx_malware_protection_enabled` | gauge | `org_id`, `network_id` | Advanced Malware Protection enablement (1=enabled, 0=disabled) |  |
| `meraki_mx_nat_rules` | gauge | `nat_type` | Number of NAT rules configured for a network by type |  |
| `meraki_mx_port_forwarding_rules` | gauge | `org_id`, `network_id` | Number of port forwarding rules configured for a network |  |
| `meraki_mx_security_events_count` | gauge | `org_id`, `event_type` | Security events by type in the current collection window (not a monotonic total) |  |
| `meraki_mx_static_routes` | gauge | `org_id`, `network_id` | Total number of static routes configured for a network |  |
| `meraki_mx_static_routes_enabled` | gauge | `org_id`, `network_id` | Number of enabled static routes configured for a network |  |
| `meraki_mx_vlans` | gauge | `org_id`, `network_id` | Number of VLANs configured for a network |  |

### MXHACollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mx_ha_enabled` | gauge | `org_id`, `network_id` | Whether MX warm spare high availability is enabled for a network (1 = enabled) |  |
| `meraki_mx_ha_mode` | gauge | `org_id`, `network_id`, `mode` | MX warm spare high availability mode info (1 = present) |  |
| `meraki_mx_ha_role` | gauge | `org_id`, `network_id`, `serial` | MX warm spare designation priority for a device |  |

### MXUplinkHealthCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mx_uplink_latency_seconds` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `interface` | MX per-uplink WAN latency in seconds (worst-case across monitored destinations, latest sample) |  |
| `meraki_mx_uplink_loss_percent` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `interface` | MX per-uplink WAN loss percent (worst-case across monitored destinations, latest sample) |  |

### MXUplinkUsageCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mx_uplink_recv_bytes` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `interface` | MX per-uplink WAN bytes received (last 5 minutes) |  |
| `meraki_mx_uplink_sent_bytes` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `interface` | MX per-uplink WAN bytes sent (last 5 minutes) |  |

### MXVpnCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mx_vpn_hubs` | gauge | `org_id`, `network_id` | Number of configured VPN hubs for a network (spoke mode) |  |
| `meraki_mx_vpn_peer_status` | gauge | `org_id`, `network_id`, `peer_network_id`, `peer_type` | VPN peer reachability status (1=reachable, 0=unreachable) |  |
| `meraki_mx_vpn_peers` | gauge | `org_id`, `network_id` | Number of VPN peers configured for a network |  |
| `meraki_mx_vpn_site_to_site_mode` | gauge | `org_id`, `network_id`, `mode` | Site-to-site VPN mode one-hot indicator (1=active mode for this network) |  |
| `meraki_mx_vpn_stats_avg_latency_seconds` | gauge | `org_id`, `network_id`, `peer_network_id` | Average VPN latency in seconds to a peer network (15-min avg), averaged across all sender/receiver uplink combinations |  |
| `meraki_mx_vpn_subnets_advertised` | gauge | `org_id`, `network_id` | Number of local subnets advertised to the site-to-site VPN |  |
| `meraki_mx_vpn_usage_recv_bytes` | gauge | `org_id`, `network_id`, `peer_network_id` | VPN usage received in bytes over the last 15 minutes, per peer network |  |
| `meraki_mx_vpn_usage_sent_bytes` | gauge | `org_id`, `network_id`, `peer_network_id` | VPN usage sent in bytes over the last 15 minutes, per peer network |  |

### MeshCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_mr_mesh_route_metric` | gauge | `org_id`, `network_id`, `serial` | Wireless mesh route quality metric from repeater to gateway AP, unitless, lower is better |  |
| `meraki_mr_mesh_throughput_bytes_per_second` | gauge | `org_id`, `network_id`, `serial` | Wireless mesh repeater link throughput in bytes per second (API Mbps x1e6/8) |  |
| `meraki_mr_mesh_usage_percent` | gauge | `org_id`, `network_id`, `serial` | Wireless mesh link utilization percentage (0-100) |  |

### NetworkHealthCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_ap_channel_utilization_2_4ghz_percent` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `utilization_type` | 2.4GHz channel utilization percentage per AP, 10-min bucket |  |
| `meraki_ap_channel_utilization_5ghz_percent` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `utilization_type` | 5GHz channel utilization percentage per AP, 10-min bucket |  |
| `meraki_mr_ssid_failed_connections_count` | gauge | `org_id`, `network_id`, `ssid`, `failure_step` | Failed wireless connections by SSID and failure step over the last hour |  |
| `meraki_network_bluetooth_clients_count` | gauge | `org_id`, `network_id` | Number of Bluetooth clients detected by MR devices in the last 5 minutes |  |
| `meraki_network_channel_utilization_2_4ghz_percent` | gauge | `org_id`, `network_id`, `utilization_type` | Network-wide average 2.4GHz channel utilization percentage, 10-min bucket |  |
| `meraki_network_channel_utilization_5ghz_percent` | gauge | `org_id`, `network_id`, `utilization_type` | Network-wide average 5GHz channel utilization percentage, 10-min bucket |  |
| `meraki_network_wireless_connection_stats_count` | gauge | `org_id`, `network_id`, `stat_type` | Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success) |  |
| `meraki_network_wireless_download_bytes_per_second` | gauge | `org_id`, `network_id` | Network-wide wireless download bandwidth in bytes per second, 5-min bucket |  |
| `meraki_network_wireless_upload_bytes_per_second` | gauge | `org_id`, `network_id` | Network-wide wireless upload bandwidth in bytes per second, 5-min bucket |  |

### OrganizationCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_device_firmware_info` | gauge | `org_id`, `network_id`, `serial`, `model`, `device_type`, `firmware` | Device firmware join metric (value 1): maps serial -> running firmware. Numeric device series join firmware via on(serial) group_left(firmware) |  |
| `meraki_exporter_org_collection_status` | gauge | `org_id` | Organization collection status (1=success, 0=failed or in backoff) |  |
| `meraki_network_firmware_up_to_date` | gauge | `org_id`, `network_id` | Whether every device in the network is on its latest firmware (1=all up to date / no pending upgrade, 0=at least one device has a pending or in-progress upgrade) |  |
| `meraki_network_info` | gauge | `org_id`, `network_id`, `network_name` | Network information (join metric: network_id -> network_name) |  |
| `meraki_org` | info | `org_id`, `org_name` | Organization information |  |
| `meraki_org_adaptive_policy_acls` | gauge | `org_id` | Number of adaptive policy custom ACLs in the organization |  |
| `meraki_org_adaptive_policy_groups` | gauge | `org_id` | Number of adaptive policy groups in the organization |  |
| `meraki_org_adaptive_policy_policies` | gauge | `org_id` | Number of adaptive policies in the organization |  |
| `meraki_org_api_requests_by_status` | gauge | `org_id`, `status_code` | API requests by HTTP status code in the last hour |  |
| `meraki_org_api_requests_count` | gauge | `org_id` | Meraki-reported total API requests made by ALL clients of this organization's Dashboard API (any app/integration, not just this exporter) in the trailing 1-hour window; a snapshot count, not a monotonic counter |  |
| `meraki_org_application_usage_downstream_bytes` | gauge | `org_id`, `category` | Downstream application usage in bytes by category over the trailing 1-day window |  |
| `meraki_org_application_usage_percent` | gauge | `org_id`, `category` | Application usage percent by category over the trailing 1-day window |  |
| `meraki_org_application_usage_total_bytes` | gauge | `org_id`, `category` | Total application usage in bytes by category over the trailing 1-day window |  |
| `meraki_org_application_usage_upstream_bytes` | gauge | `org_id`, `category` | Upstream application usage in bytes by category over the trailing 1-day window |  |
| `meraki_org_clients_count` | gauge | `org_id` | Number of active clients in the organization in the last hour |  |
| `meraki_org_config_templates` | gauge | `org_id` | Number of configuration templates defined in the organization |  |
| `meraki_org_devices` | gauge | `org_id`, `device_type` | Number of devices in the organization |  |
| `meraki_org_devices_availability` | gauge | `org_id`, `status`, `product_type` | Number of devices by availability status and product type |  |
| `meraki_org_devices_availability_changes_count` | gauge | `org_id`, `product_type`, `status` | Number of device availability transitions observed in the collection window (tied to the configured MEDIUM update interval, default 300s) by product type and new status |  |
| `meraki_org_devices_by_model` | gauge | `org_id`, `model` | Number of devices by specific model |  |
| `meraki_org_firmware_upgrades` | gauge | `org_id`, `product_type`, `status` | Number of firmware upgrade events by product type and status |  |
| `meraki_org_firmware_upgrades_pending` | gauge | `org_id`, `product_type` | Number of pending/in-flight firmware upgrade events by product type |  |
| `meraki_org_licenses` | gauge | `org_id`, `license_type`, `status` | Number of licenses |  |
| `meraki_org_licenses_expiring` | gauge | `org_id`, `license_type` | Number of licenses expiring within 30 days |  |
| `meraki_org_networks` | gauge | `org_id` | Number of networks in the organization |  |
| `meraki_org_networks_bound_to_template` | gauge | `org_id` | Number of NetworkFilter-visible networks bound to a configuration template (counts only networks within the configured NetworkFilter, not the whole org) |  |
| `meraki_org_packetcaptures` | gauge | `org_id` | Number of packet captures in the organization |  |
| `meraki_org_packetcaptures_remaining` | gauge | `org_id` | Number of remaining packet captures to process |  |
| `meraki_org_top_client_usage_total_bytes` | gauge | `org_id`, `client_id` | Total bytes used by each top-N client over the trailing 1-day window (labelled by client_id only per #533; join client_id -> name via meraki_client_info, which may miss clients on untracked networks) |  |
| `meraki_org_top_manufacturer_usage_total_bytes` | gauge | `org_id`, `manufacturer` | Total bytes used by each top-N client-device manufacturer over the trailing 1-day window |  |
| `meraki_org_top_ssid_usage_total_bytes` | gauge | `org_id`, `ssid` | Total bytes used by each top-N SSID over the trailing 1-day window |  |
| `meraki_org_usage_downstream_bytes` | gauge | `org_id` | Downstream data usage in bytes for the 1-hour window |  |
| `meraki_org_usage_total_bytes` | gauge | `org_id` | Total data usage in bytes for the 1-hour window |  |
| `meraki_org_usage_upstream_bytes` | gauge | `org_id` | Upstream data usage in bytes for the 1-hour window |  |
| `meraki_org_webhook_deliveries_count` | gauge | `org_id`, `status_code` | Number of Meraki webhook delivery attempts in the trailing 1-hour window by HTTP response status code (windowed count, resets each cycle; failures are status_code!~"2..") |  |

## Internal & Platform Metrics

### AsyncMerakiClient

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_exporter_api_requests_total` | counter | `endpoint`, `method`, `status_code` | Total number of outbound Meraki API requests made by THIS exporter process (monotonic counter), labeled by endpoint/method/status_code |  |
| `meraki_exporter_api_retry_total` | counter | `endpoint`, `retry_reason` | Total number of API retry attempts |  |

### CardinalityMonitor

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_exporter_cardinality_analyzed_metrics` | gauge | — | Number of metrics analyzed in last run |  |
| `meraki_exporter_cardinality_duration_seconds` | gauge | — | Time taken to complete cardinality analysis |  |
| `meraki_exporter_cardinality_warnings_total` | counter | `metric_name`, `severity` | Number of cardinality warnings triggered |  |
| `meraki_exporter_total_series` | gauge | — | Total number of time series across all metrics |  |

### CollectorManager

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_exporter_collection_errors_total` | counter | `collector`, `tier`, `error_type` | Total number of collection errors by collector and phase |  |
| `meraki_exporter_collection_utilization_ratio` | gauge | `collector`, `tier` | Fraction of the tier interval consumed by actual collection (0=instant, 1=full interval) |  |
| `meraki_exporter_collections_active` | gauge | `collector`, `tier` | Number of parallel organization collections currently active |  |
| `meraki_exporter_collector_failure_streak` | gauge | `collector`, `tier` | Consecutive failures for each collector since last success |  |

### EndpointScheduler

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_exporter_scheduler_budget_rps` | gauge | — | Configured API budget in requests/second (rate_limit_requests_per_second x rate_limit_shared_fraction; computed schedule input) |  |
| `meraki_exporter_scheduler_budget_utilization_ratio` | gauge | — | Total estimated demand divided by the effective budget (computed schedule output, refreshed on each solver resolve) |  |
| `meraki_exporter_scheduler_effective_budget_rps` | gauge | — | AIMD-adjusted effective API budget in requests/second (computed schedule input, lowered after 429 throttling and recovered additively) |  |
| `meraki_exporter_scheduler_estimated_demand_rps` | gauge | `group` | Estimated steady-state API demand per endpoint group in requests/second (computed schedule output, refreshed on each solver resolve; not a measured rate) |  |
| `meraki_exporter_scheduler_interval_seconds` | gauge | `group` | Solved collection interval per endpoint group in seconds (computed schedule output, refreshed on each solver resolve) |  |
| `meraki_exporter_scheduler_stretch_factor` | gauge | `group` | Solved interval divided by the group's natural cadence (max(floor, tier heartbeat)); 1.0 = unstretched (computed schedule output, refreshed on each solver resolve) |  |

### ExporterApp

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_exporter_cpu_usage_percent` | gauge | — | CPU utilization percent of the exporter process itself, sampled periodically (#277). |  |
| `meraki_exporter_memory_usage_bytes` | gauge | — | Resident memory (RSS) used by the exporter process itself, in bytes (#277). |  |

### MetricCollector

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_exporter_collection_smoothing_window_seconds` | gauge | `collector`, `tier` | Configured smoothing window for collector runs |  |
| `meraki_exporter_collector_api_calls_total` | counter | `collector`, `tier`, `endpoint` | Total number of API calls made by collectors |  |
| `meraki_exporter_collector_duration_seconds` | histogram | `collector`, `tier` | Time spent collecting metrics |  |
| `meraki_exporter_collector_errors_total` | counter | `collector`, `tier`, `error_type` | Total number of collector errors |  |
| `meraki_exporter_collector_start_offset_seconds` | gauge | `collector`, `tier` | Configured collector start offset within smoothing window |  |
| `meraki_exporter_collector_success_timestamp_seconds` | gauge | `collector`, `tier` | Unix timestamp of last successful collection |  |

### MetricExpirationManager

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_exporter_cardinality_limit_reached_total` | counter | `metric` | Number of times a metric family exceeded its cardinality budget (cardinality.max_series_per_family). With action=warn (default) series are kept; with action=drop the oldest series in the family are shed. |  |
| `meraki_exporter_collection_errors_expired_total` | counter | `collector`, `tier` | Total number of metrics expired due to TTL |  |
| `meraki_exporter_expiration_tracked_metrics` | gauge | `collector` | Number of metrics currently tracked for expiration |  |

### OrgRateLimiter

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_exporter_api_rate_limiter_throttled_total` | counter | `org_id`, `endpoint` | Total number of client-side rate limiter waits |  |
| `meraki_exporter_api_rate_limiter_tokens` | gauge | `org_id` | Estimated remaining tokens in client-side rate limiter bucket |  |
| `meraki_exporter_api_rate_limiter_wait_seconds` | histogram | `org_id`, `endpoint` | Seconds spent waiting for client-side rate limiter |  |
| `meraki_exporter_scheduler_throttle_backoffs_total` | counter | — | Total AIMD multiplicative-decrease backoff events (#617): each increment is one 429/Retry-After-driven halving of the effective client-side rate budget, at most one per 30s cooldown window. Computed feedback signal, not a Meraki API metric. |  |

### OrganizationInventory

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_exporter_inventory_cache_size` | gauge | — | Number of entries in inventory cache |  |
| `meraki_network_filter_match` | gauge | — | 1 if the network passes the configured network filter, 0 otherwise. |  |
| `meraki_network_filter_networks` | gauge | — | Number of networks discovered before filtering. |  |
| `meraki_network_filter_resolved` | gauge | — | Number of networks included by the configured network filter. |  |

### WebhookHandler

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_webhook_events_failed_total` | counter | — | Total webhook events that failed processing | Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true |
| `meraki_webhook_events_processed_total` | counter | — | Total webhook events successfully processed | Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true |
| `meraki_webhook_events_received_total` | counter | — | Total webhook events received by the active WebhookHandler request pipeline (POST /api/webhooks/meraki), labeled by org_id and alert_type | Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true |
| `meraki_webhook_processing_duration_seconds` | histogram | — | Time spent processing webhook events | Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true |
| `meraki_webhook_validation_failures_total` | counter | — | Total webhook validation failures | Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true |

### build_info

| Metric | Type | Labels | Description | Notes |
|--------|------|--------|-------------|-------|
| `meraki_exporter_build_info` | gauge | `version`, `commit` | Exporter build information as a constant gauge (value always 1); the version and commit labels identify the running build. Local/dev builds without the APP_VERSION and GIT_COMMIT build-args report version='0.0.0+dev' and commit='unknown'. |  |

## Metric Types

- **Gauge**: Current value that can go up or down
- **Counter**: Cumulative value that only increases
- **Histogram**: Distribution of observations across buckets
- **Info**: Metadata metric with labels and value 1

