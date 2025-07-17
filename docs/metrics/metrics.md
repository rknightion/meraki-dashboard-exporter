# Metrics Reference

This page provides a comprehensive reference of all Prometheus metrics exposed by the Meraki Dashboard Exporter.

## Overview

The exporter provides metrics across several categories:

| Collector | Metrics | Description |
|-----------|---------|-------------|
| AlertsCollector | 3 | Active alerts by severity, type, and category |
| AlertsCollectorRefactored | 3 | Various metrics |
| ConfigCollector | 14 | Organization security settings and configuration tracking |
| DeviceCollector | 6 | Device status, performance, and uptime metrics |
| MTSensorCollector | 18 | Environmental monitoring from MT sensors |
| NetworkHealthCollector | 8 | Network-wide wireless health and performance |
| OrganizationCollector | 12 | Organization-level metrics including API usage and licenses |
| OrganizationCollectorRefactored | 12 | Various metrics |

## Metrics by Collector

### AlertsCollector

**Source:** `src/meraki_dashboard_exporter/collectors/alerts.py`

#### `meraki_alerts_active`

**Description:** Number of active Meraki assurance alerts

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ALERTS_ACTIVE`

**Variable:** `self._alerts_active` (line 28)

#### `meraki_alerts_total_by_network`

**Description:** Total number of active alerts per network

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ALERTS_TOTAL_BY_NETWORK`

**Variable:** `self._alerts_by_network` (line 51)

#### `meraki_alerts_total_by_severity`

**Description:** Total number of active alerts by severity

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ALERTS_TOTAL_BY_SEVERITY`

**Variable:** `self._alerts_by_severity` (line 44)

### AlertsCollectorRefactored

**Source:** `src/meraki_dashboard_exporter/collectors/alerts_refactored.py`

#### `meraki_alerts_active`

**Description:** Number of active Meraki assurance alerts

**Type:** gauge

**Labels:** `org_id`, `org_name`, `network_id`, `network_name`, `alert_type`, `category_type`, `severity`, `device_type`

**Constant:** `MetricName.ALERTS_ACTIVE`

**Variable:** `self._alerts_active` (line 36)

#### `meraki_alerts_total_by_network`

**Description:** Total number of active alerts per network

**Type:** gauge

**Labels:** `org_id`, `org_name`, `network_id`, `network_name`

**Constant:** `MetricName.ALERTS_TOTAL_BY_NETWORK`

**Variable:** `self._alerts_by_network` (line 59)

#### `meraki_alerts_total_by_severity`

**Description:** Total number of active alerts by severity

**Type:** gauge

**Labels:** `org_id`, `org_name`, `severity`

**Constant:** `MetricName.ALERTS_TOTAL_BY_SEVERITY`

**Variable:** `self._alerts_by_severity` (line 52)

### ConfigCollector

**Source:** `src/meraki_dashboard_exporter/collectors/config.py`

#### `meraki_org_configuration_changes_total`

**Description:** Total number of configuration changes in the last 24 hours

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_CONFIGURATION_CHANGES_TOTAL`

**Variable:** `self._configuration_changes_total` (line 107)

#### `meraki_org_login_security_account_lockout_attempts`

**Description:** Number of failed login attempts before lockout (0 if not set)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ATTEMPTS`

**Variable:** `self._login_security_account_lockout_attempts` (line 70)

#### `meraki_org_login_security_account_lockout_enabled`

**Description:** Whether account lockout is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ENABLED`

**Variable:** `self._login_security_account_lockout_enabled` (line 64)

#### `meraki_org_login_security_api_ip_restrictions_enabled`

**Description:** Whether API key IP restrictions are enabled (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_API_IP_RESTRICTIONS_ENABLED`

**Variable:** `self._login_security_api_ip_restrictions_enabled` (line 100)

#### `meraki_org_login_security_different_passwords_count`

**Description:** Number of different passwords required (0 if not set)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_COUNT`

**Variable:** `self._login_security_different_passwords_count` (line 46)

#### `meraki_org_login_security_different_passwords_enabled`

**Description:** Whether different passwords are enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_ENABLED`

**Variable:** `self._login_security_different_passwords_enabled` (line 40)

#### `meraki_org_login_security_idle_timeout_enabled`

**Description:** Whether idle timeout is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_IDLE_TIMEOUT_ENABLED`

**Variable:** `self._login_security_idle_timeout_enabled` (line 76)

#### `meraki_org_login_security_idle_timeout_minutes`

**Description:** Minutes before idle timeout (0 if not set)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_IDLE_TIMEOUT_MINUTES`

**Variable:** `self._login_security_idle_timeout_minutes` (line 82)

#### `meraki_org_login_security_ip_ranges_enabled`

**Description:** Whether login IP ranges are enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_IP_RANGES_ENABLED`

**Variable:** `self._login_security_ip_ranges_enabled` (line 94)

#### `meraki_org_login_security_minimum_password_length`

**Description:** Minimum password length required

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_MINIMUM_PASSWORD_LENGTH`

**Variable:** `self._login_security_minimum_password_length` (line 58)

#### `meraki_org_login_security_password_expiration_days`

**Description:** Number of days before password expires (0 if not set)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_DAYS`

**Variable:** `self._login_security_password_expiration_days` (line 34)

#### `meraki_org_login_security_password_expiration_enabled`

**Description:** Whether password expiration is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_ENABLED`

**Variable:** `self._login_security_password_expiration_enabled` (line 28)

#### `meraki_org_login_security_strong_passwords_enabled`

**Description:** Whether strong passwords are enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_STRONG_PASSWORDS_ENABLED`

**Variable:** `self._login_security_strong_passwords_enabled` (line 52)

#### `meraki_org_login_security_two_factor_enabled`

**Description:** Whether two-factor authentication is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LOGIN_SECURITY_TWO_FACTOR_ENABLED`

**Variable:** `self._login_security_two_factor_enabled` (line 88)

### DeviceCollector

**Source:** `src/meraki_dashboard_exporter/collectors/device.py`

#### `meraki_device_memory_free_bytes`

**Description:** Device memory free in bytes

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.DEVICE_MEMORY_FREE_BYTES`

**Variable:** `self._device_memory_free_bytes` (line 186)

#### `meraki_device_memory_total_bytes`

**Description:** Device memory total provisioned in bytes

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.DEVICE_MEMORY_TOTAL_BYTES`

**Variable:** `self._device_memory_total_bytes` (line 192)

#### `meraki_device_memory_usage_percent`

**Description:** Device memory usage percentage (maximum from most recent interval)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.DEVICE_MEMORY_USAGE_PERCENT`

**Variable:** `self._device_memory_usage_percent` (line 198)

#### `meraki_device_memory_used_bytes`

**Description:** Device memory used in bytes

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.DEVICE_MEMORY_USED_BYTES`

**Variable:** `self._device_memory_used_bytes` (line 180)

#### `meraki_device_status_info`

**Description:** Device status information

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.DEVICE_STATUS_INFO`

**Variable:** `self._device_status_info` (line 173)

#### `meraki_device_up`

**Description:** Device online status (1 = online, 0 = offline)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.DEVICE_UP`

**Variable:** `self._device_up` (line 167)

### MTSensorCollector

**Source:** `src/meraki_dashboard_exporter/collectors/mt_sensor.py`

#### `meraki_mt_apparent_power_va`

**Description:** Apparent power in volt-amperes

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_APPARENT_POWER_VA`

**Variable:** `self._sensor_apparent_power` (line 126)

#### `meraki_mt_battery_percentage`

**Description:** Battery level percentage

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_BATTERY_PERCENTAGE`

**Variable:** `self._sensor_battery` (line 96)

#### `meraki_mt_co2_ppm`

**Description:** CO2 level in parts per million

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_CO2_PPM`

**Variable:** `self._sensor_co2` (line 72)

#### `meraki_mt_current_amps`

**Description:** Current in amperes

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_CURRENT_AMPS`

**Variable:** `self._sensor_current` (line 114)

#### `meraki_mt_door_status`

**Description:** Door sensor status (1 = open, 0 = closed)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_DOOR_STATUS`

**Variable:** `self._sensor_door` (line 60)

#### `meraki_mt_downstream_power_enabled`

**Description:** Downstream power status (1 = enabled, 0 = disabled)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_DOWNSTREAM_POWER_ENABLED`

**Variable:** `self._sensor_downstream_power` (line 144)

#### `meraki_mt_frequency_hz`

**Description:** Frequency in hertz

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_FREQUENCY_HZ`

**Variable:** `self._sensor_frequency` (line 138)

#### `meraki_mt_humidity_percent`

**Description:** Humidity percentage

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_HUMIDITY_PERCENT`

**Variable:** `self._sensor_humidity` (line 54)

#### `meraki_mt_indoor_air_quality_score`

**Description:** Indoor air quality score (0-100)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_INDOOR_AIR_QUALITY_SCORE`

**Variable:** `self._sensor_air_quality` (line 102)

#### `meraki_mt_noise_db`

**Description:** Noise level in decibels

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_NOISE_DB`

**Variable:** `self._sensor_noise` (line 90)

#### `meraki_mt_pm25_ug_m3`

**Description:** PM2.5 particulate matter in micrograms per cubic meter

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_PM25_UG_M3`

**Variable:** `self._sensor_pm25` (line 84)

#### `meraki_mt_power_factor_percent`

**Description:** Power factor percentage

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_POWER_FACTOR_PERCENT`

**Variable:** `self._sensor_power_factor` (line 132)

#### `meraki_mt_real_power_watts`

**Description:** Real power in watts

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_REAL_POWER_WATTS`

**Variable:** `self._sensor_real_power` (line 120)

#### `meraki_mt_remote_lockout_status`

**Description:** Remote lockout switch status (1 = locked, 0 = unlocked)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_REMOTE_LOCKOUT_STATUS`

**Variable:** `self._sensor_remote_lockout` (line 150)

#### `meraki_mt_temperature_celsius`

**Description:** Temperature reading in Celsius

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_TEMPERATURE_CELSIUS`

**Variable:** `self._sensor_temperature` (line 48)

#### `meraki_mt_tvoc_ppb`

**Description:** Total volatile organic compounds in parts per billion

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_TVOC_PPB`

**Variable:** `self._sensor_tvoc` (line 78)

#### `meraki_mt_voltage_volts`

**Description:** Voltage in volts

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_VOLTAGE_VOLTS`

**Variable:** `self._sensor_voltage` (line 108)

#### `meraki_mt_water_detected`

**Description:** Water detection status (1 = detected, 0 = not detected)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.MT_WATER_DETECTED`

**Variable:** `self._sensor_water` (line 66)

### NetworkHealthCollector

**Source:** `src/meraki_dashboard_exporter/collectors/network_health.py`

#### `meraki_ap_channel_utilization_2_4ghz_percent`

**Description:** 2.4GHz channel utilization percentage per AP

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.AP_CHANNEL_UTILIZATION_2_4GHZ_PERCENT`

**Variable:** `self._ap_utilization_2_4ghz` (line 98)

#### `meraki_ap_channel_utilization_5ghz_percent`

**Description:** 5GHz channel utilization percentage per AP

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.AP_CHANNEL_UTILIZATION_5GHZ_PERCENT`

**Variable:** `self._ap_utilization_5ghz` (line 104)

#### `meraki_network_bluetooth_clients_total`

**Description:** Total number of Bluetooth clients detected by MR devices in the last 5 minutes

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.NETWORK_BLUETOOTH_CLIENTS_TOTAL`

**Variable:** `self._network_bluetooth_clients_total` (line 144)

#### `meraki_network_channel_utilization_2_4ghz_percent`

**Description:** Network-wide average 2.4GHz channel utilization percentage

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.NETWORK_CHANNEL_UTILIZATION_2_4GHZ_PERCENT`

**Variable:** `self._network_utilization_2_4ghz` (line 111)

#### `meraki_network_channel_utilization_5ghz_percent`

**Description:** Network-wide average 5GHz channel utilization percentage

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.NETWORK_CHANNEL_UTILIZATION_5GHZ_PERCENT`

**Variable:** `self._network_utilization_5ghz` (line 117)

#### `meraki_network_wireless_connection_stats_total`

**Description:** Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.NETWORK_WIRELESS_CONNECTION_STATS`

**Variable:** `self._network_connection_stats` (line 124)

#### `meraki_network_wireless_download_kbps`

**Description:** Network-wide wireless download bandwidth in kilobits per second

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.NETWORK_WIRELESS_DOWNLOAD_KBPS`

**Variable:** `self._network_wireless_download_kbps` (line 131)

#### `meraki_network_wireless_upload_kbps`

**Description:** Network-wide wireless upload bandwidth in kilobits per second

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.NETWORK_WIRELESS_UPLOAD_KBPS`

**Variable:** `self._network_wireless_upload_kbps` (line 137)

### OrganizationCollector

**Source:** `src/meraki_dashboard_exporter/collectors/organization.py`

#### `meraki_org_api_requests_rate_limit`

**Description:** API rate limit for the organization

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_API_REQUESTS_RATE_LIMIT`

**Variable:** `self._api_rate_limit` (line 59)

#### `meraki_org_api_requests_total`

**Description:** Total API requests made by the organization

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_API_REQUESTS_TOTAL`

**Variable:** `self._api_requests_total` (line 53)

#### `meraki_org_clients_total`

**Description:** Total number of active clients in the organization (5-minute window from last complete interval)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_CLIENTS_TOTAL`

**Variable:** `self._clients_total` (line 99)

#### `meraki_org_devices_by_model_total`

**Description:** Total number of devices by specific model

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_DEVICES_BY_MODEL_TOTAL`

**Variable:** `self._devices_by_model_total` (line 79)

#### `meraki_org_devices_total`

**Description:** Total number of devices in the organization

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_DEVICES_TOTAL`

**Variable:** `self._devices_total` (line 73)

#### `meraki_org_info`

**Description:** Organization information

**Type:** info

**Labels:** 

**Constant:** `MetricName.ORG_INFO`

**Variable:** `self._org_info` (line 46)

#### `meraki_org_licenses_expiring`

**Description:** Number of licenses expiring within 30 days

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LICENSES_EXPIRING`

**Variable:** `self._licenses_expiring` (line 92)

#### `meraki_org_licenses_total`

**Description:** Total number of licenses

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_LICENSES_TOTAL`

**Variable:** `self._licenses_total` (line 86)

#### `meraki_org_networks_total`

**Description:** Total number of networks in the organization

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_NETWORKS_TOTAL`

**Variable:** `self._networks_total` (line 66)

#### `meraki_org_usage_downstream_kb`

**Description:** Downstream data usage in KB for the 5-minute window (last complete 5-min interval)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_USAGE_DOWNSTREAM_KB`

**Variable:** `self._usage_downstream_kb` (line 112)

#### `meraki_org_usage_total_kb`

**Description:** Total data usage in KB for the 5-minute window (last complete 5-min interval, e.g., 11:04 call returns 10:55-11:00)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_USAGE_TOTAL_KB`

**Variable:** `self._usage_total_kb` (line 106)

#### `meraki_org_usage_upstream_kb`

**Description:** Upstream data usage in KB for the 5-minute window (last complete 5-min interval)

**Type:** gauge

**Labels:** 

**Constant:** `MetricName.ORG_USAGE_UPSTREAM_KB`

**Variable:** `self._usage_upstream_kb` (line 118)

### OrganizationCollectorRefactored

**Source:** `src/meraki_dashboard_exporter/collectors/organization_refactored.py`

#### ``

**Type:** gauge

**Variable:** `self._api_requests_total` (line 61)

#### ``

**Type:** gauge

**Variable:** `self._api_rate_limit` (line 72)

#### ``

**Type:** gauge

**Variable:** `self._networks_total` (line 85)

#### ``

**Type:** gauge

**Variable:** `self._devices_total` (line 99)

#### ``

**Type:** gauge

**Variable:** `self._devices_by_model_total` (line 112)

#### ``

**Type:** gauge

**Variable:** `self._licenses_total` (line 126)

#### ``

**Type:** gauge

**Variable:** `self._licenses_expiring` (line 138)

#### ``

**Type:** gauge

**Variable:** `self._clients_total` (line 151)

#### ``

**Type:** gauge

**Variable:** `self._usage_total_kb` (line 164)

#### ``

**Type:** gauge

**Variable:** `self._usage_downstream_kb` (line 176)

#### ``

**Type:** gauge

**Variable:** `self._usage_upstream_kb` (line 188)

#### `meraki_org_info`

**Description:** Organization information

**Type:** info

**Labels:** 

**Variable:** `self._org_info` (line 48)

## Complete Metrics Index

All metrics in alphabetical order:

| Metric Name | Type | Collector | Description |
|-------------|------|-----------|-------------|
| `` | gauge | OrganizationCollectorRefactored |  |
| `` | gauge | OrganizationCollectorRefactored |  |
| `` | gauge | OrganizationCollectorRefactored |  |
| `` | gauge | OrganizationCollectorRefactored |  |
| `` | gauge | OrganizationCollectorRefactored |  |
| `` | gauge | OrganizationCollectorRefactored |  |
| `` | gauge | OrganizationCollectorRefactored |  |
| `` | gauge | OrganizationCollectorRefactored |  |
| `` | gauge | OrganizationCollectorRefactored |  |
| `` | gauge | OrganizationCollectorRefactored |  |
| `` | gauge | OrganizationCollectorRefactored |  |
| `meraki_alerts_active` | gauge | AlertsCollector | Number of active Meraki assurance alerts |
| `meraki_alerts_active` | gauge | AlertsCollectorRefactored | Number of active Meraki assurance alerts |
| `meraki_alerts_total_by_network` | gauge | AlertsCollector | Total number of active alerts per network |
| `meraki_alerts_total_by_network` | gauge | AlertsCollectorRefactored | Total number of active alerts per network |
| `meraki_alerts_total_by_severity` | gauge | AlertsCollector | Total number of active alerts by severity |
| `meraki_alerts_total_by_severity` | gauge | AlertsCollectorRefactored | Total number of active alerts by severity |
| `meraki_ap_channel_utilization_2_4ghz_percent` | gauge | NetworkHealthCollector | 2.4GHz channel utilization percentage per AP |
| `meraki_ap_channel_utilization_5ghz_percent` | gauge | NetworkHealthCollector | 5GHz channel utilization percentage per AP |
| `meraki_device_memory_free_bytes` | gauge | DeviceCollector | Device memory free in bytes |
| `meraki_device_memory_total_bytes` | gauge | DeviceCollector | Device memory total provisioned in bytes |
| `meraki_device_memory_usage_percent` | gauge | DeviceCollector | Device memory usage percentage (maximum from most recent interval) |
| `meraki_device_memory_used_bytes` | gauge | DeviceCollector | Device memory used in bytes |
| `meraki_device_status_info` | gauge | DeviceCollector | Device status information |
| `meraki_device_up` | gauge | DeviceCollector | Device online status (1 = online, 0 = offline) |
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
| `meraki_org_clients_total` | gauge | OrganizationCollector | Total number of active clients in the organization (5-minute window from last complete interval) |
| `meraki_org_configuration_changes_total` | gauge | ConfigCollector | Total number of configuration changes in the last 24 hours |
| `meraki_org_devices_by_model_total` | gauge | OrganizationCollector | Total number of devices by specific model |
| `meraki_org_devices_total` | gauge | OrganizationCollector | Total number of devices in the organization |
| `meraki_org_info` | info | OrganizationCollectorRefactored | Organization information |
| `meraki_org_info` | info | OrganizationCollector | Organization information |
| `meraki_org_licenses_expiring` | gauge | OrganizationCollector | Number of licenses expiring within 30 days |
| `meraki_org_licenses_total` | gauge | OrganizationCollector | Total number of licenses |
| `meraki_org_login_security_account_lockout_attempts` | gauge | ConfigCollector | Number of failed login attempts before lockout (0 if not set) |
| `meraki_org_login_security_account_lockout_enabled` | gauge | ConfigCollector | Whether account lockout is enforced (1=enabled, 0=disabled) |
| `meraki_org_login_security_api_ip_restrictions_enabled` | gauge | ConfigCollector | Whether API key IP restrictions are enabled (1=enabled, 0=disabled) |
| `meraki_org_login_security_different_passwords_count` | gauge | ConfigCollector | Number of different passwords required (0 if not set) |
| `meraki_org_login_security_different_passwords_enabled` | gauge | ConfigCollector | Whether different passwords are enforced (1=enabled, 0=disabled) |
| `meraki_org_login_security_idle_timeout_enabled` | gauge | ConfigCollector | Whether idle timeout is enforced (1=enabled, 0=disabled) |
| `meraki_org_login_security_idle_timeout_minutes` | gauge | ConfigCollector | Minutes before idle timeout (0 if not set) |
| `meraki_org_login_security_ip_ranges_enabled` | gauge | ConfigCollector | Whether login IP ranges are enforced (1=enabled, 0=disabled) |
| `meraki_org_login_security_minimum_password_length` | gauge | ConfigCollector | Minimum password length required |
| `meraki_org_login_security_password_expiration_days` | gauge | ConfigCollector | Number of days before password expires (0 if not set) |
| `meraki_org_login_security_password_expiration_enabled` | gauge | ConfigCollector | Whether password expiration is enforced (1=enabled, 0=disabled) |
| `meraki_org_login_security_strong_passwords_enabled` | gauge | ConfigCollector | Whether strong passwords are enforced (1=enabled, 0=disabled) |
| `meraki_org_login_security_two_factor_enabled` | gauge | ConfigCollector | Whether two-factor authentication is enforced (1=enabled, 0=disabled) |
| `meraki_org_networks_total` | gauge | OrganizationCollector | Total number of networks in the organization |
| `meraki_org_usage_downstream_kb` | gauge | OrganizationCollector | Downstream data usage in KB for the 5-minute window (last complete 5-min interval) |
| `meraki_org_usage_total_kb` | gauge | OrganizationCollector | Total data usage in KB for the 5-minute window (last complete 5-min interval, e.g., 11:04 call returns 10:55-11:00) |
| `meraki_org_usage_upstream_kb` | gauge | OrganizationCollector | Upstream data usage in KB for the 5-minute window (last complete 5-min interval) |

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