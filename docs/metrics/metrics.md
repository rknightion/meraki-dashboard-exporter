# Metrics Reference

This page provides a comprehensive reference of all Prometheus metrics exposed by the Meraki Dashboard Exporter.

## Overview

The exporter provides metrics across several categories:

| Collector | Metrics | Description |
|-----------|---------|-------------|
| AlertsCollector | 3 | Active alerts by severity, type, and category |
| ConfigCollector | 14 | Organization security settings and configuration tracking |
| DeviceCollector | 6 | Device status, performance, and uptime metrics |
| MRCollector | 33 | Access point metrics including clients, power, and performance |
| MSCollector | 8 | Switch-specific metrics including port status, power, and PoE |
| MTSensorCollector | 18 | Environmental monitoring from MT sensors |
| NetworkHealthCollector | 8 | Network-wide wireless health and performance |
| OrganizationCollector | 13 | Organization-level metrics including API usage and licenses |

## Metrics by Collector

### AlertsCollector

**Source:** `src/meraki_dashboard_exporter/collectors/alerts.py`

#### `meraki_alerts_active`

**Description:** Number of active Meraki assurance alerts

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`, `LabelName.ALERT_TYPE`, `LabelName.CATEGORY_TYPE`, `LabelName.SEVERITY`, `LabelName.DEVICE_TYPE`

**Constant:** `AlertMetricName.ALERTS_ACTIVE`

**Variable:** `self._alerts_active` (line 31)

#### `meraki_alerts_total_by_network`

**Description:** Total number of active alerts per network

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `AlertMetricName.ALERTS_TOTAL_BY_NETWORK`

**Variable:** `self._alerts_by_network` (line 54)

#### `meraki_alerts_total_by_severity`

**Description:** Total number of active alerts by severity

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`, `LabelName.SEVERITY`

**Constant:** `AlertMetricName.ALERTS_TOTAL_BY_SEVERITY`

**Variable:** `self._alerts_by_severity` (line 47)

### ConfigCollector

**Source:** `src/meraki_dashboard_exporter/collectors/config.py`

#### `OrgMetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ATTEMPTS`

**Description:** Number of failed login attempts before lockout (0 if not set)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Variable:** `self._login_security_account_lockout_attempts` (line 74)

#### `OrgMetricName.ORG_LOGIN_SECURITY_API_IP_RESTRICTIONS_ENABLED`

**Description:** Whether API key IP restrictions are enabled (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Variable:** `self._login_security_api_ip_restrictions_enabled` (line 104)

#### `OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_COUNT`

**Description:** Number of different passwords required (0 if not set)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Variable:** `self._login_security_different_passwords_count` (line 50)

#### `OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_ENABLED`

**Description:** Whether different passwords are enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Variable:** `self._login_security_different_passwords_enabled` (line 44)

#### `OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_DAYS`

**Description:** Number of days before password expires (0 if not set)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Variable:** `self._login_security_password_expiration_days` (line 38)

#### `OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_ENABLED`

**Description:** Whether password expiration is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Variable:** `self._login_security_password_expiration_enabled` (line 32)

#### `OrgMetricName.ORG_LOGIN_SECURITY_STRONG_PASSWORDS_ENABLED`

**Description:** Whether strong passwords are enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Variable:** `self._login_security_strong_passwords_enabled` (line 56)

#### `meraki_org_configuration_changes_total`

**Description:** Total number of configuration changes in the last 24 hours

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_CONFIGURATION_CHANGES_TOTAL`

**Variable:** `self._configuration_changes_total` (line 111)

#### `meraki_org_login_security_account_lockout_enabled`

**Description:** Whether account lockout is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ENABLED`

**Variable:** `self._login_security_account_lockout_enabled` (line 68)

#### `meraki_org_login_security_idle_timeout_enabled`

**Description:** Whether idle timeout is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_LOGIN_SECURITY_IDLE_TIMEOUT_ENABLED`

**Variable:** `self._login_security_idle_timeout_enabled` (line 80)

#### `meraki_org_login_security_idle_timeout_minutes`

**Description:** Minutes before idle timeout (0 if not set)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_LOGIN_SECURITY_IDLE_TIMEOUT_MINUTES`

**Variable:** `self._login_security_idle_timeout_minutes` (line 86)

#### `meraki_org_login_security_ip_ranges_enabled`

**Description:** Whether login IP ranges are enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_LOGIN_SECURITY_IP_RANGES_ENABLED`

**Variable:** `self._login_security_ip_ranges_enabled` (line 98)

#### `meraki_org_login_security_minimum_password_length`

**Description:** Minimum password length required

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_LOGIN_SECURITY_MINIMUM_PASSWORD_LENGTH`

**Variable:** `self._login_security_minimum_password_length` (line 62)

#### `meraki_org_login_security_two_factor_enabled`

**Description:** Whether two-factor authentication is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_LOGIN_SECURITY_TWO_FACTOR_ENABLED`

**Variable:** `self._login_security_two_factor_enabled` (line 92)

### DeviceCollector

**Source:** `src/meraki_dashboard_exporter/collectors/device.py`

#### `meraki_device_memory_free_bytes`

**Description:** Device memory free in bytes

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.NETWORK_ID`, `LabelName.DEVICE_TYPE`, `LabelName.STAT`

**Constant:** `DeviceMetricName.DEVICE_MEMORY_FREE_BYTES`

**Variable:** `self._device_memory_free_bytes` (line 166)

#### `meraki_device_memory_total_bytes`

**Description:** Device memory total provisioned in bytes

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.NETWORK_ID`, `LabelName.DEVICE_TYPE`

**Constant:** `DeviceMetricName.DEVICE_MEMORY_TOTAL_BYTES`

**Variable:** `self._device_memory_total_bytes` (line 179)

#### `meraki_device_memory_usage_percent`

**Description:** Device memory usage percentage (maximum from most recent interval)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.NETWORK_ID`, `LabelName.DEVICE_TYPE`

**Constant:** `DeviceMetricName.DEVICE_MEMORY_USAGE_PERCENT`

**Variable:** `self._device_memory_usage_percent` (line 191)

#### `meraki_device_memory_used_bytes`

**Description:** Device memory used in bytes

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.NETWORK_ID`, `LabelName.DEVICE_TYPE`, `LabelName.STAT`

**Constant:** `DeviceMetricName.DEVICE_MEMORY_USED_BYTES`

**Variable:** `self._device_memory_used_bytes` (line 153)

#### `meraki_device_status_info`

**Description:** Device status information

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.NETWORK_ID`, `LabelName.DEVICE_TYPE`, `LabelName.STATUS`

**Constant:** `DeviceMetricName.DEVICE_STATUS_INFO`

**Variable:** `self._device_status_info` (line 139)

#### `meraki_device_up`

**Description:** Device online status (1 = online, 0 = offline)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.NETWORK_ID`, `LabelName.DEVICE_TYPE`

**Constant:** `DeviceMetricName.DEVICE_UP`

**Variable:** `self._device_up` (line 127)

### MRCollector

**Source:** `src/meraki_dashboard_exporter/collectors/devices/mr.py`

#### `meraki_mr_aggregation_enabled`

**Description:** Access point port aggregation enabled status (1 = enabled, 0 = disabled)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`

**Constant:** `MRMetricName.MR_AGGREGATION_ENABLED`

**Variable:** `self._mr_aggregation_enabled` (line 115)

#### `meraki_mr_aggregation_speed_mbps`

**Description:** Access point total aggregated port speed in Mbps

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`

**Constant:** `MRMetricName.MR_AGGREGATION_SPEED_MBPS`

**Variable:** `self._mr_aggregation_speed` (line 121)

#### `meraki_mr_clients_connected`

**Description:** Number of clients connected to access point

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.NETWORK_ID`

**Constant:** `MRMetricName.MR_CLIENTS_CONNECTED`

**Variable:** `self._ap_clients` (line 43)

#### `meraki_mr_connection_stats_total`

**Description:** Wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.NETWORK_ID`, `LabelName.STAT_TYPE`

**Constant:** `MRMetricName.MR_CONNECTION_STATS`

**Variable:** `self._ap_connection_stats` (line 49)

#### `meraki_mr_cpu_load_5min`

**Description:** Access point CPU load average over 5 minutes (normalized to 0-100 per core)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_CPU_LOAD_5MIN`

**Variable:** `self._mr_cpu_load_5min` (line 285)

#### `meraki_mr_network_packet_loss_downstream_percent`

**Description:** Downstream packet loss percentage for all access points in network (5-minute window)

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_NETWORK_PACKET_LOSS_DOWNSTREAM_PERCENT`

**Variable:** `self._mr_network_packet_loss_downstream_percent` (line 241)

#### `meraki_mr_network_packet_loss_total_percent`

**Description:** Total packet loss percentage (upstream + downstream) for all access points in network (5-minute window)

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_NETWORK_PACKET_LOSS_TOTAL_PERCENT`

**Variable:** `self._mr_network_packet_loss_total_percent` (line 278)

#### `meraki_mr_network_packet_loss_upstream_percent`

**Description:** Upstream packet loss percentage for all access points in network (5-minute window)

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_NETWORK_PACKET_LOSS_UPSTREAM_PERCENT`

**Variable:** `self._mr_network_packet_loss_upstream_percent` (line 259)

#### `meraki_mr_network_packets_downstream_lost`

**Description:** Downstream packets lost for all access points in network (5-minute window)

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_NETWORK_PACKETS_DOWNSTREAM_LOST`

**Variable:** `self._mr_network_packets_downstream_lost` (line 235)

#### `meraki_mr_network_packets_downstream_total`

**Description:** Total downstream packets for all access points in network (5-minute window)

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_NETWORK_PACKETS_DOWNSTREAM_TOTAL`

**Variable:** `self._mr_network_packets_downstream_total` (line 229)

#### `meraki_mr_network_packets_lost_total`

**Description:** Total packets lost (upstream + downstream) for all access points in network (5-minute window)

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_NETWORK_PACKETS_LOST_TOTAL`

**Variable:** `self._mr_network_packets_lost_total` (line 272)

#### `meraki_mr_network_packets_total`

**Description:** Total packets (upstream + downstream) for all access points in network (5-minute window)

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_NETWORK_PACKETS_TOTAL`

**Variable:** `self._mr_network_packets_total` (line 266)

#### `meraki_mr_network_packets_upstream_lost`

**Description:** Upstream packets lost for all access points in network (5-minute window)

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_NETWORK_PACKETS_UPSTREAM_LOST`

**Variable:** `self._mr_network_packets_upstream_lost` (line 253)

#### `meraki_mr_network_packets_upstream_total`

**Description:** Total upstream packets for all access points in network (5-minute window)

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_NETWORK_PACKETS_UPSTREAM_TOTAL`

**Variable:** `self._mr_network_packets_upstream_total` (line 247)

#### `meraki_mr_packet_loss_downstream_percent`

**Description:** Downstream packet loss percentage for access point (5-minute window)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_PACKET_LOSS_DOWNSTREAM_PERCENT`

**Variable:** `self._mr_packet_loss_downstream_percent` (line 150)

#### `meraki_mr_packet_loss_total_percent`

**Description:** Total packet loss percentage (upstream + downstream) for access point (5-minute window)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_PACKET_LOSS_TOTAL_PERCENT`

**Variable:** `self._mr_packet_loss_total_percent` (line 217)

#### `meraki_mr_packet_loss_upstream_percent`

**Description:** Upstream packet loss percentage for access point (5-minute window)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_PACKET_LOSS_UPSTREAM_PERCENT`

**Variable:** `self._mr_packet_loss_upstream_percent` (line 183)

#### `meraki_mr_packets_downstream_lost`

**Description:** Downstream packets lost by access point (5-minute window)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_PACKETS_DOWNSTREAM_LOST`

**Variable:** `self._mr_packets_downstream_lost` (line 139)

#### `meraki_mr_packets_downstream_total`

**Description:** Total downstream packets transmitted by access point (5-minute window)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_PACKETS_DOWNSTREAM_TOTAL`

**Variable:** `self._mr_packets_downstream_total` (line 128)

#### `meraki_mr_packets_lost_total`

**Description:** Total packets lost (upstream + downstream) for access point (5-minute window)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_PACKETS_LOST_TOTAL`

**Variable:** `self._mr_packets_lost_total` (line 206)

#### `meraki_mr_packets_total`

**Description:** Total packets (upstream + downstream) for access point (5-minute window)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_PACKETS_TOTAL`

**Variable:** `self._mr_packets_total` (line 195)

#### `meraki_mr_packets_upstream_lost`

**Description:** Upstream packets lost by access point (5-minute window)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_PACKETS_UPSTREAM_LOST`

**Variable:** `self._mr_packets_upstream_lost` (line 172)

#### `meraki_mr_packets_upstream_total`

**Description:** Total upstream packets received by access point (5-minute window)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MRMetricName.MR_PACKETS_UPSTREAM_TOTAL`

**Variable:** `self._mr_packets_upstream_total` (line 161)

#### `meraki_mr_port_link_negotiation_info`

**Description:** Access point port link negotiation information

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.PORT_NAME`, `LabelName.DUPLEX`

**Constant:** `MRMetricName.MR_PORT_LINK_NEGOTIATION_INFO`

**Variable:** `self._mr_port_link_negotiation_info` (line 92)

#### `meraki_mr_port_link_negotiation_speed_mbps`

**Description:** Access point port link negotiation speed in Mbps

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.PORT_NAME`

**Constant:** `MRMetricName.MR_PORT_LINK_NEGOTIATION_SPEED_MBPS`

**Variable:** `self._mr_port_link_negotiation_speed` (line 104)

#### `meraki_mr_port_poe_info`

**Description:** Access point port PoE information

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.PORT_NAME`, `LabelName.STANDARD`

**Constant:** `MRMetricName.MR_PORT_POE_INFO`

**Variable:** `self._mr_port_poe_info` (line 80)

#### `meraki_mr_power_ac_connected`

**Description:** Access point AC power connection status (1 = connected, 0 = not connected)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`

**Constant:** `MRMetricName.MR_POWER_AC_CONNECTED`

**Variable:** `self._mr_power_ac_connected` (line 68)

#### `meraki_mr_power_info`

**Description:** Access point power information

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.MODE`

**Constant:** `MRMetricName.MR_POWER_INFO`

**Variable:** `self._mr_power_info` (line 62)

#### `meraki_mr_power_poe_connected`

**Description:** Access point PoE power connection status (1 = connected, 0 = not connected)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`

**Constant:** `MRMetricName.MR_POWER_POE_CONNECTED`

**Variable:** `self._mr_power_poe_connected` (line 74)

#### `meraki_mr_radio_broadcasting`

**Description:** Access point radio broadcasting status (1 = broadcasting, 0 = not broadcasting)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`, `LabelName.BAND`, `LabelName.RADIO_INDEX`

**Constant:** `MRMetricName.MR_RADIO_BROADCASTING`

**Variable:** `self._mr_radio_broadcasting` (line 298)

#### `meraki_mr_radio_channel`

**Description:** Access point radio channel number

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`, `LabelName.BAND`, `LabelName.RADIO_INDEX`

**Constant:** `MRMetricName.MR_RADIO_CHANNEL`

**Variable:** `self._mr_radio_channel` (line 311)

#### `meraki_mr_radio_channel_width_mhz`

**Description:** Access point radio channel width in MHz

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`, `LabelName.BAND`, `LabelName.RADIO_INDEX`

**Constant:** `MRMetricName.MR_RADIO_CHANNEL_WIDTH_MHZ`

**Variable:** `self._mr_radio_channel_width` (line 324)

#### `meraki_mr_radio_power_dbm`

**Description:** Access point radio transmit power in dBm

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`, `LabelName.BAND`, `LabelName.RADIO_INDEX`

**Constant:** `MRMetricName.MR_RADIO_POWER_DBM`

**Variable:** `self._mr_radio_power` (line 337)

### MSCollector

**Source:** `src/meraki_dashboard_exporter/collectors/devices/ms.py`

#### `meraki_ms_poe_budget_watts`

**Description:** Total POE power budget for switch in watts

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.NETWORK_ID`

**Constant:** `MSMetricName.MS_POE_BUDGET_WATTS`

**Variable:** `self._switch_poe_budget` (line 78)

#### `meraki_ms_poe_network_total_watthours`

**Description:** Total POE power consumption for all switches in network in watt-hours (Wh)

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `MSMetricName.MS_POE_NETWORK_TOTAL_WATTS`

**Variable:** `self._switch_poe_network_total` (line 84)

#### `meraki_ms_poe_port_power_watthours`

**Description:** Per-port POE power consumption in watt-hours (Wh)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.PORT_ID`, `LabelName.PORT_NAME`

**Constant:** `MSMetricName.MS_POE_PORT_POWER_WATTS`

**Variable:** `self._switch_poe_port_power` (line 66)

#### `meraki_ms_poe_total_power_watthours`

**Description:** Total POE power consumption for switch in watt-hours (Wh)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.NETWORK_ID`

**Constant:** `MSMetricName.MS_POE_TOTAL_POWER_WATTS`

**Variable:** `self._switch_poe_total_power` (line 72)

#### `meraki_ms_port_errors_total`

**Description:** Switch port error count

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.PORT_ID`, `LabelName.PORT_NAME`, `LabelName.ERROR_TYPE`

**Constant:** `MSMetricName.MS_PORT_ERRORS_TOTAL`

**Variable:** `self._switch_port_errors` (line 46)

#### `meraki_ms_port_status`

**Description:** Switch port status (1 = connected, 0 = disconnected)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.PORT_ID`, `LabelName.PORT_NAME`

**Constant:** `MSMetricName.MS_PORT_STATUS`

**Variable:** `self._switch_port_status` (line 28)

#### `meraki_ms_port_traffic_bytes`

**Description:** Switch port traffic in bytes

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.PORT_ID`, `LabelName.PORT_NAME`, `LabelName.DIRECTION`

**Constant:** `MSMetricName.MS_PORT_TRAFFIC_BYTES`

**Variable:** `self._switch_port_traffic` (line 34)

#### `meraki_ms_power_usage_watts`

**Description:** Switch power usage in watts

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`

**Constant:** `MSMetricName.MS_POWER_USAGE_WATTS`

**Variable:** `self._switch_power` (line 59)

### MTSensorCollector

**Source:** `src/meraki_dashboard_exporter/collectors/mt_sensor.py`

#### `meraki_mt_apparent_power_va`

**Description:** Apparent power in volt-amperes

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_APPARENT_POWER_VA`

**Variable:** `self._sensor_apparent_power` (line 131)

#### `meraki_mt_battery_percentage`

**Description:** Battery level percentage

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_BATTERY_PERCENTAGE`

**Variable:** `self._sensor_battery` (line 101)

#### `meraki_mt_co2_ppm`

**Description:** CO2 level in parts per million

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_CO2_PPM`

**Variable:** `self._sensor_co2` (line 77)

#### `meraki_mt_current_amps`

**Description:** Current in amperes

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_CURRENT_AMPS`

**Variable:** `self._sensor_current` (line 119)

#### `meraki_mt_door_status`

**Description:** Door sensor status (1 = open, 0 = closed)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_DOOR_STATUS`

**Variable:** `self._sensor_door` (line 65)

#### `meraki_mt_downstream_power_enabled`

**Description:** Downstream power status (1 = enabled, 0 = disabled)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_DOWNSTREAM_POWER_ENABLED`

**Variable:** `self._sensor_downstream_power` (line 149)

#### `meraki_mt_frequency_hz`

**Description:** Frequency in hertz

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_FREQUENCY_HZ`

**Variable:** `self._sensor_frequency` (line 143)

#### `meraki_mt_humidity_percent`

**Description:** Humidity percentage

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_HUMIDITY_PERCENT`

**Variable:** `self._sensor_humidity` (line 59)

#### `meraki_mt_indoor_air_quality_score`

**Description:** Indoor air quality score (0-100)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_INDOOR_AIR_QUALITY_SCORE`

**Variable:** `self._sensor_air_quality` (line 107)

#### `meraki_mt_noise_db`

**Description:** Noise level in decibels

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_NOISE_DB`

**Variable:** `self._sensor_noise` (line 95)

#### `meraki_mt_pm25_ug_m3`

**Description:** PM2.5 particulate matter in micrograms per cubic meter

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_PM25_UG_M3`

**Variable:** `self._sensor_pm25` (line 89)

#### `meraki_mt_power_factor_percent`

**Description:** Power factor percentage

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_POWER_FACTOR_PERCENT`

**Variable:** `self._sensor_power_factor` (line 137)

#### `meraki_mt_real_power_watts`

**Description:** Real power in watts

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_REAL_POWER_WATTS`

**Variable:** `self._sensor_real_power` (line 125)

#### `meraki_mt_remote_lockout_status`

**Description:** Remote lockout switch status (1 = locked, 0 = unlocked)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_REMOTE_LOCKOUT_STATUS`

**Variable:** `self._sensor_remote_lockout` (line 155)

#### `meraki_mt_temperature_celsius`

**Description:** Temperature reading in Celsius

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_TEMPERATURE_CELSIUS`

**Variable:** `self._sensor_temperature` (line 53)

#### `meraki_mt_tvoc_ppb`

**Description:** Total volatile organic compounds in parts per billion

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_TVOC_PPB`

**Variable:** `self._sensor_tvoc` (line 83)

#### `meraki_mt_voltage_volts`

**Description:** Voltage in volts

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_VOLTAGE_VOLTS`

**Variable:** `self._sensor_voltage` (line 113)

#### `meraki_mt_water_detected`

**Description:** Water detection status (1 = detected, 0 = not detected)

**Type:** gauge

**Labels:** `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.SENSOR_TYPE`

**Constant:** `MTMetricName.MT_WATER_DETECTED`

**Variable:** `self._sensor_water` (line 71)

### NetworkHealthCollector

**Source:** `src/meraki_dashboard_exporter/collectors/network_health.py`

#### `meraki_ap_channel_utilization_2_4ghz_percent`

**Description:** 2.4GHz channel utilization percentage per AP

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`, `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.TYPE`

**Constant:** `NetworkHealthMetricName.AP_CHANNEL_UTILIZATION_2_4GHZ_PERCENT`

**Variable:** `self._ap_utilization_2_4ghz` (line 52)

#### `meraki_ap_channel_utilization_5ghz_percent`

**Description:** 5GHz channel utilization percentage per AP

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`, `LabelName.SERIAL`, `LabelName.NAME`, `LabelName.MODEL`, `LabelName.TYPE`

**Constant:** `NetworkHealthMetricName.AP_CHANNEL_UTILIZATION_5GHZ_PERCENT`

**Variable:** `self._ap_utilization_5ghz` (line 65)

#### `meraki_network_bluetooth_clients_total`

**Description:** Total number of Bluetooth clients detected by MR devices in the last 5 minutes

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `NetworkHealthMetricName.NETWORK_BLUETOOTH_CLIENTS_TOTAL`

**Variable:** `self._network_bluetooth_clients_total` (line 112)

#### `meraki_network_channel_utilization_2_4ghz_percent`

**Description:** Network-wide average 2.4GHz channel utilization percentage

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`, `LabelName.TYPE`

**Constant:** `NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_2_4GHZ_PERCENT`

**Variable:** `self._network_utilization_2_4ghz` (line 79)

#### `meraki_network_channel_utilization_5ghz_percent`

**Description:** Network-wide average 5GHz channel utilization percentage

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`, `LabelName.TYPE`

**Constant:** `NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_5GHZ_PERCENT`

**Variable:** `self._network_utilization_5ghz` (line 85)

#### `meraki_network_wireless_connection_stats_total`

**Description:** Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`, `LabelName.STAT_TYPE`

**Constant:** `NetworkMetricName.NETWORK_WIRELESS_CONNECTION_STATS`

**Variable:** `self._network_connection_stats` (line 92)

#### `meraki_network_wireless_download_kbps`

**Description:** Network-wide wireless download bandwidth in kilobits per second

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `NetworkHealthMetricName.NETWORK_WIRELESS_DOWNLOAD_KBPS`

**Variable:** `self._network_wireless_download_kbps` (line 99)

#### `meraki_network_wireless_upload_kbps`

**Description:** Network-wide wireless upload bandwidth in kilobits per second

**Type:** gauge

**Labels:** `LabelName.NETWORK_ID`, `LabelName.NETWORK_NAME`

**Constant:** `NetworkHealthMetricName.NETWORK_WIRELESS_UPLOAD_KBPS`

**Variable:** `self._network_wireless_upload_kbps` (line 105)

### OrganizationCollector

**Source:** `src/meraki_dashboard_exporter/collectors/organization.py`

#### `meraki_org_api_requests_rate_limit`

**Description:** API rate limit for the organization

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_API_REQUESTS_RATE_LIMIT`

**Variable:** `self._api_rate_limit` (line 65)

#### `meraki_org_api_requests_total`

**Description:** Total API requests made by the organization

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_API_REQUESTS_TOTAL`

**Variable:** `self._api_requests_total` (line 59)

#### `meraki_org_clients_total`

**Description:** Total number of active clients in the organization (30-minute window)

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_CLIENTS_TOTAL`

**Variable:** `self._clients_total` (line 122)

#### `meraki_org_devices_availability_total`

**Description:** Total number of devices by availability status and product type

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`, `LabelName.STATUS`, `LabelName.PRODUCT_TYPE`

**Constant:** `OrgMetricName.ORG_DEVICES_AVAILABILITY_TOTAL`

**Variable:** `self._devices_availability_total` (line 92)

#### `meraki_org_devices_by_model_total`

**Description:** Total number of devices by specific model

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`, `LabelName.MODEL`

**Constant:** `OrgMetricName.ORG_DEVICES_BY_MODEL_TOTAL`

**Variable:** `self._devices_by_model_total` (line 85)

#### `meraki_org_devices_total`

**Description:** Total number of devices in the organization

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`, `LabelName.DEVICE_TYPE`

**Constant:** `OrgMetricName.ORG_DEVICES_TOTAL`

**Variable:** `self._devices_total` (line 79)

#### `meraki_org_info`

**Description:** Organization information

**Type:** info

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_INFO`

**Variable:** `self._org_info` (line 52)

#### `meraki_org_licenses_expiring`

**Description:** Number of licenses expiring within 30 days

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`, `LabelName.LICENSE_TYPE`

**Constant:** `OrgMetricName.ORG_LICENSES_EXPIRING`

**Variable:** `self._licenses_expiring` (line 115)

#### `meraki_org_licenses_total`

**Description:** Total number of licenses

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`, `LabelName.LICENSE_TYPE`, `LabelName.STATUS`

**Constant:** `OrgMetricName.ORG_LICENSES_TOTAL`

**Variable:** `self._licenses_total` (line 104)

#### `meraki_org_networks_total`

**Description:** Total number of networks in the organization

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_NETWORKS_TOTAL`

**Variable:** `self._networks_total` (line 72)

#### `meraki_org_usage_downstream_kb`

**Description:** Downstream data usage in KB for the 30-minute window

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_USAGE_DOWNSTREAM_KB`

**Variable:** `self._usage_downstream_kb` (line 135)

#### `meraki_org_usage_total_kb`

**Description:** Total data usage in KB for the 30-minute window

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_USAGE_TOTAL_KB`

**Variable:** `self._usage_total_kb` (line 129)

#### `meraki_org_usage_upstream_kb`

**Description:** Upstream data usage in KB for the 30-minute window

**Type:** gauge

**Labels:** `LabelName.ORG_ID`, `LabelName.ORG_NAME`

**Constant:** `OrgMetricName.ORG_USAGE_UPSTREAM_KB`

**Variable:** `self._usage_upstream_kb` (line 141)

## Complete Metrics Index

All metrics in alphabetical order:

| Metric Name | Type | Collector | Description |
|-------------|------|-----------|-------------|
| `OrgMetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ATTEMPTS` | gauge | ConfigCollector | Number of failed login attempts before lockout (0 if not set) |
| `OrgMetricName.ORG_LOGIN_SECURITY_API_IP_RESTRICTIONS_ENABLED` | gauge | ConfigCollector | Whether API key IP restrictions are enabled (1=enabled, 0=disabled) |
| `OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_COUNT` | gauge | ConfigCollector | Number of different passwords required (0 if not set) |
| `OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_ENABLED` | gauge | ConfigCollector | Whether different passwords are enforced (1=enabled, 0=disabled) |
| `OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_DAYS` | gauge | ConfigCollector | Number of days before password expires (0 if not set) |
| `OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_ENABLED` | gauge | ConfigCollector | Whether password expiration is enforced (1=enabled, 0=disabled) |
| `OrgMetricName.ORG_LOGIN_SECURITY_STRONG_PASSWORDS_ENABLED` | gauge | ConfigCollector | Whether strong passwords are enforced (1=enabled, 0=disabled) |
| `meraki_alerts_active` | gauge | AlertsCollector | Number of active Meraki assurance alerts |
| `meraki_alerts_total_by_network` | gauge | AlertsCollector | Total number of active alerts per network |
| `meraki_alerts_total_by_severity` | gauge | AlertsCollector | Total number of active alerts by severity |
| `meraki_ap_channel_utilization_2_4ghz_percent` | gauge | NetworkHealthCollector | 2.4GHz channel utilization percentage per AP |
| `meraki_ap_channel_utilization_5ghz_percent` | gauge | NetworkHealthCollector | 5GHz channel utilization percentage per AP |
| `meraki_device_memory_free_bytes` | gauge | DeviceCollector | Device memory free in bytes |
| `meraki_device_memory_total_bytes` | gauge | DeviceCollector | Device memory total provisioned in bytes |
| `meraki_device_memory_usage_percent` | gauge | DeviceCollector | Device memory usage percentage (maximum from most recent interval) |
| `meraki_device_memory_used_bytes` | gauge | DeviceCollector | Device memory used in bytes |
| `meraki_device_status_info` | gauge | DeviceCollector | Device status information |
| `meraki_device_up` | gauge | DeviceCollector | Device online status (1 = online, 0 = offline) |
| `meraki_mr_aggregation_enabled` | gauge | MRCollector | Access point port aggregation enabled status (1 = enabled, 0 = disabled) |
| `meraki_mr_aggregation_speed_mbps` | gauge | MRCollector | Access point total aggregated port speed in Mbps |
| `meraki_mr_clients_connected` | gauge | MRCollector | Number of clients connected to access point |
| `meraki_mr_connection_stats_total` | gauge | MRCollector | Wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success) |
| `meraki_mr_cpu_load_5min` | gauge | MRCollector | Access point CPU load average over 5 minutes (normalized to 0-100 per core) |
| `meraki_mr_network_packet_loss_downstream_percent` | gauge | MRCollector | Downstream packet loss percentage for all access points in network (5-minute window) |
| `meraki_mr_network_packet_loss_total_percent` | gauge | MRCollector | Total packet loss percentage (upstream + downstream) for all access points in network (5-minute window) |
| `meraki_mr_network_packet_loss_upstream_percent` | gauge | MRCollector | Upstream packet loss percentage for all access points in network (5-minute window) |
| `meraki_mr_network_packets_downstream_lost` | gauge | MRCollector | Downstream packets lost for all access points in network (5-minute window) |
| `meraki_mr_network_packets_downstream_total` | gauge | MRCollector | Total downstream packets for all access points in network (5-minute window) |
| `meraki_mr_network_packets_lost_total` | gauge | MRCollector | Total packets lost (upstream + downstream) for all access points in network (5-minute window) |
| `meraki_mr_network_packets_total` | gauge | MRCollector | Total packets (upstream + downstream) for all access points in network (5-minute window) |
| `meraki_mr_network_packets_upstream_lost` | gauge | MRCollector | Upstream packets lost for all access points in network (5-minute window) |
| `meraki_mr_network_packets_upstream_total` | gauge | MRCollector | Total upstream packets for all access points in network (5-minute window) |
| `meraki_mr_packet_loss_downstream_percent` | gauge | MRCollector | Downstream packet loss percentage for access point (5-minute window) |
| `meraki_mr_packet_loss_total_percent` | gauge | MRCollector | Total packet loss percentage (upstream + downstream) for access point (5-minute window) |
| `meraki_mr_packet_loss_upstream_percent` | gauge | MRCollector | Upstream packet loss percentage for access point (5-minute window) |
| `meraki_mr_packets_downstream_lost` | gauge | MRCollector | Downstream packets lost by access point (5-minute window) |
| `meraki_mr_packets_downstream_total` | gauge | MRCollector | Total downstream packets transmitted by access point (5-minute window) |
| `meraki_mr_packets_lost_total` | gauge | MRCollector | Total packets lost (upstream + downstream) for access point (5-minute window) |
| `meraki_mr_packets_total` | gauge | MRCollector | Total packets (upstream + downstream) for access point (5-minute window) |
| `meraki_mr_packets_upstream_lost` | gauge | MRCollector | Upstream packets lost by access point (5-minute window) |
| `meraki_mr_packets_upstream_total` | gauge | MRCollector | Total upstream packets received by access point (5-minute window) |
| `meraki_mr_port_link_negotiation_info` | gauge | MRCollector | Access point port link negotiation information |
| `meraki_mr_port_link_negotiation_speed_mbps` | gauge | MRCollector | Access point port link negotiation speed in Mbps |
| `meraki_mr_port_poe_info` | gauge | MRCollector | Access point port PoE information |
| `meraki_mr_power_ac_connected` | gauge | MRCollector | Access point AC power connection status (1 = connected, 0 = not connected) |
| `meraki_mr_power_info` | gauge | MRCollector | Access point power information |
| `meraki_mr_power_poe_connected` | gauge | MRCollector | Access point PoE power connection status (1 = connected, 0 = not connected) |
| `meraki_mr_radio_broadcasting` | gauge | MRCollector | Access point radio broadcasting status (1 = broadcasting, 0 = not broadcasting) |
| `meraki_mr_radio_channel` | gauge | MRCollector | Access point radio channel number |
| `meraki_mr_radio_channel_width_mhz` | gauge | MRCollector | Access point radio channel width in MHz |
| `meraki_mr_radio_power_dbm` | gauge | MRCollector | Access point radio transmit power in dBm |
| `meraki_ms_poe_budget_watts` | gauge | MSCollector | Total POE power budget for switch in watts |
| `meraki_ms_poe_network_total_watthours` | gauge | MSCollector | Total POE power consumption for all switches in network in watt-hours (Wh) |
| `meraki_ms_poe_port_power_watthours` | gauge | MSCollector | Per-port POE power consumption in watt-hours (Wh) |
| `meraki_ms_poe_total_power_watthours` | gauge | MSCollector | Total POE power consumption for switch in watt-hours (Wh) |
| `meraki_ms_port_errors_total` | gauge | MSCollector | Switch port error count |
| `meraki_ms_port_status` | gauge | MSCollector | Switch port status (1 = connected, 0 = disconnected) |
| `meraki_ms_port_traffic_bytes` | gauge | MSCollector | Switch port traffic in bytes |
| `meraki_ms_power_usage_watts` | gauge | MSCollector | Switch power usage in watts |
| `meraki_mt_apparent_power_va` | gauge | MTSensorCollector | Apparent power in volt-amperes |
| `meraki_mt_battery_percentage` | gauge | MTSensorCollector | Battery level percentage |
| `meraki_mt_co2_ppm` | gauge | MTSensorCollector | CO2 level in parts per million |
| `meraki_mt_current_amps` | gauge | MTSensorCollector | Current in amperes |
| `meraki_mt_door_status` | gauge | MTSensorCollector | Door sensor status (1 = open, 0 = closed) |
| `meraki_mt_downstream_power_enabled` | gauge | MTSensorCollector | Downstream power status (1 = enabled, 0 = disabled) |
| `meraki_mt_frequency_hz` | gauge | MTSensorCollector | Frequency in hertz |
| `meraki_mt_humidity_percent` | gauge | MTSensorCollector | Humidity percentage |
| `meraki_mt_indoor_air_quality_score` | gauge | MTSensorCollector | Indoor air quality score (0-100) |
| `meraki_mt_noise_db` | gauge | MTSensorCollector | Noise level in decibels |
| `meraki_mt_pm25_ug_m3` | gauge | MTSensorCollector | PM2.5 particulate matter in micrograms per cubic meter |
| `meraki_mt_power_factor_percent` | gauge | MTSensorCollector | Power factor percentage |
| `meraki_mt_real_power_watts` | gauge | MTSensorCollector | Real power in watts |
| `meraki_mt_remote_lockout_status` | gauge | MTSensorCollector | Remote lockout switch status (1 = locked, 0 = unlocked) |
| `meraki_mt_temperature_celsius` | gauge | MTSensorCollector | Temperature reading in Celsius |
| `meraki_mt_tvoc_ppb` | gauge | MTSensorCollector | Total volatile organic compounds in parts per billion |
| `meraki_mt_voltage_volts` | gauge | MTSensorCollector | Voltage in volts |
| `meraki_mt_water_detected` | gauge | MTSensorCollector | Water detection status (1 = detected, 0 = not detected) |
| `meraki_network_bluetooth_clients_total` | gauge | NetworkHealthCollector | Total number of Bluetooth clients detected by MR devices in the last 5 minutes |
| `meraki_network_channel_utilization_2_4ghz_percent` | gauge | NetworkHealthCollector | Network-wide average 2.4GHz channel utilization percentage |
| `meraki_network_channel_utilization_5ghz_percent` | gauge | NetworkHealthCollector | Network-wide average 5GHz channel utilization percentage |
| `meraki_network_wireless_connection_stats_total` | gauge | NetworkHealthCollector | Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success) |
| `meraki_network_wireless_download_kbps` | gauge | NetworkHealthCollector | Network-wide wireless download bandwidth in kilobits per second |
| `meraki_network_wireless_upload_kbps` | gauge | NetworkHealthCollector | Network-wide wireless upload bandwidth in kilobits per second |
| `meraki_org_api_requests_rate_limit` | gauge | OrganizationCollector | API rate limit for the organization |
| `meraki_org_api_requests_total` | gauge | OrganizationCollector | Total API requests made by the organization |
| `meraki_org_clients_total` | gauge | OrganizationCollector | Total number of active clients in the organization (30-minute window) |
| `meraki_org_configuration_changes_total` | gauge | ConfigCollector | Total number of configuration changes in the last 24 hours |
| `meraki_org_devices_availability_total` | gauge | OrganizationCollector | Total number of devices by availability status and product type |
| `meraki_org_devices_by_model_total` | gauge | OrganizationCollector | Total number of devices by specific model |
| `meraki_org_devices_total` | gauge | OrganizationCollector | Total number of devices in the organization |
| `meraki_org_info` | info | OrganizationCollector | Organization information |
| `meraki_org_licenses_expiring` | gauge | OrganizationCollector | Number of licenses expiring within 30 days |
| `meraki_org_licenses_total` | gauge | OrganizationCollector | Total number of licenses |
| `meraki_org_login_security_account_lockout_enabled` | gauge | ConfigCollector | Whether account lockout is enforced (1=enabled, 0=disabled) |
| `meraki_org_login_security_idle_timeout_enabled` | gauge | ConfigCollector | Whether idle timeout is enforced (1=enabled, 0=disabled) |
| `meraki_org_login_security_idle_timeout_minutes` | gauge | ConfigCollector | Minutes before idle timeout (0 if not set) |
| `meraki_org_login_security_ip_ranges_enabled` | gauge | ConfigCollector | Whether login IP ranges are enforced (1=enabled, 0=disabled) |
| `meraki_org_login_security_minimum_password_length` | gauge | ConfigCollector | Minimum password length required |
| `meraki_org_login_security_two_factor_enabled` | gauge | ConfigCollector | Whether two-factor authentication is enforced (1=enabled, 0=disabled) |
| `meraki_org_networks_total` | gauge | OrganizationCollector | Total number of networks in the organization |
| `meraki_org_usage_downstream_kb` | gauge | OrganizationCollector | Downstream data usage in KB for the 30-minute window |
| `meraki_org_usage_total_kb` | gauge | OrganizationCollector | Total data usage in KB for the 30-minute window |
| `meraki_org_usage_upstream_kb` | gauge | OrganizationCollector | Upstream data usage in KB for the 30-minute window |

## Notes

!!! info "Metric Types"
    - **Gauge**: Current value that can go up or down
    - **Counter**: Cumulative value that only increases
    - **Info**: Metadata with labels but value always 1

!!! tip "Label Usage"
    All metrics include relevant labels for filtering and aggregation. Use label selectors in your queries:
    ```promql
    # Filter by organization
    meraki_device_up{org_name="Production"}

    # Filter by device type
    meraki_device_up{device_model=~"MS.*"}
    ```

For more information on using these metrics, see the [Overview](overview.md) page.
