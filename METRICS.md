# Meraki Dashboard Exporter Metrics

This document lists all Prometheus metrics exposed by the Meraki Dashboard Exporter.

## Metrics by Collector

### AlertsCollector

**File:** `src/meraki_dashboard_exporter/collectors/alerts.py`

#### `meraki_alerts_active`

**Description:** Number of active Meraki assurance alerts

**Type:** gauge

**Labels:** `org_id`, `org_name`, `network_id`, `network_name`, `alert_type`, `category_type`, `severity`, `device_type`

**Variable:** `self._alerts_active` (line 27)

#### `meraki_alerts_total_by_network`

**Description:** Total number of active alerts per network

**Type:** gauge

**Labels:** `org_id`, `org_name`, `network_id`, `network_name`

**Variable:** `self._alerts_by_network` (line 50)

#### `meraki_alerts_total_by_severity`

**Description:** Total number of active alerts by severity

**Type:** gauge

**Labels:** `org_id`, `org_name`, `severity`

**Variable:** `self._alerts_by_severity` (line 43)

### ConfigCollector

**File:** `src/meraki_dashboard_exporter/collectors/config.py`

#### `meraki_org_configuration_changes_total`

**Description:** Total number of configuration changes in the last 24 hours

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._configuration_changes_total` (line 106)

#### `meraki_org_login_security_account_lockout_attempts`

**Description:** Number of failed login attempts before lockout (0 if not set)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_account_lockout_attempts` (line 69)

#### `meraki_org_login_security_account_lockout_enabled`

**Description:** Whether account lockout is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_account_lockout_enabled` (line 63)

#### `meraki_org_login_security_api_ip_restrictions_enabled`

**Description:** Whether API key IP restrictions are enabled (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_api_ip_restrictions_enabled` (line 99)

#### `meraki_org_login_security_different_passwords_count`

**Description:** Number of different passwords required (0 if not set)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_different_passwords_count` (line 45)

#### `meraki_org_login_security_different_passwords_enabled`

**Description:** Whether different passwords are enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_different_passwords_enabled` (line 39)

#### `meraki_org_login_security_idle_timeout_enabled`

**Description:** Whether idle timeout is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_idle_timeout_enabled` (line 75)

#### `meraki_org_login_security_idle_timeout_minutes`

**Description:** Minutes before idle timeout (0 if not set)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_idle_timeout_minutes` (line 81)

#### `meraki_org_login_security_ip_ranges_enabled`

**Description:** Whether login IP ranges are enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_ip_ranges_enabled` (line 93)

#### `meraki_org_login_security_minimum_password_length`

**Description:** Minimum password length required

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_minimum_password_length` (line 57)

#### `meraki_org_login_security_password_expiration_days`

**Description:** Number of days before password expires (0 if not set)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_password_expiration_days` (line 33)

#### `meraki_org_login_security_password_expiration_enabled`

**Description:** Whether password expiration is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_password_expiration_enabled` (line 27)

#### `meraki_org_login_security_strong_passwords_enabled`

**Description:** Whether strong passwords are enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_strong_passwords_enabled` (line 51)

#### `meraki_org_login_security_two_factor_enabled`

**Description:** Whether two-factor authentication is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._login_security_two_factor_enabled` (line 87)

### DeviceCollector

**File:** `src/meraki_dashboard_exporter/collectors/device.py`

#### `meraki_device_memory_free_bytes`

**Description:** Device memory free in bytes

**Type:** gauge

**Labels:** `serial`, `name`, `model`, `network_id`, `device_type`, `stat`

**Variable:** `self._device_memory_free_bytes` (line 185)

#### `meraki_device_memory_total_bytes`

**Description:** Device memory total provisioned in bytes

**Type:** gauge

**Labels:** `serial`, `name`, `model`, `network_id`, `device_type`

**Variable:** `self._device_memory_total_bytes` (line 191)

#### `meraki_device_memory_usage_percent`

**Description:** Device memory usage percentage (maximum from most recent interval)

**Type:** gauge

**Labels:** `serial`, `name`, `model`, `network_id`, `device_type`

**Constant:** `MetricName.DEVICE_MEMORY_USAGE_PERCENT`

**Variable:** `self._device_memory_usage_percent` (line 197)

#### `meraki_device_memory_used_bytes`

**Description:** Device memory used in bytes

**Type:** gauge

**Labels:** `serial`, `name`, `model`, `network_id`, `device_type`, `stat`

**Variable:** `self._device_memory_used_bytes` (line 179)

#### `meraki_device_status_info`

**Description:** Device status information

**Type:** gauge

**Labels:** `serial`, `name`, `model`, `network_id`, `device_type`, `status`

**Variable:** `self._device_status_info` (line 172)

#### `meraki_device_up`

**Description:** Device online status (1 = online, 0 = offline)

**Type:** gauge

**Labels:** `serial`, `name`, `model`, `network_id`, `device_type`

**Constant:** `MetricName.DEVICE_UP`

**Variable:** `self._device_up` (line 166)

### MTSensorCollector

**File:** `src/meraki_dashboard_exporter/collectors/mt_sensor.py`

#### `meraki_mt_apparent_power_va`

**Description:** Apparent power in volt-amperes

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_APPARENT_POWER_VA`

**Variable:** `self._sensor_apparent_power` (line 125)

#### `meraki_mt_battery_percentage`

**Description:** Battery level percentage

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_BATTERY_PERCENTAGE`

**Variable:** `self._sensor_battery` (line 95)

#### `meraki_mt_co2_ppm`

**Description:** CO2 level in parts per million

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_CO2_PPM`

**Variable:** `self._sensor_co2` (line 71)

#### `meraki_mt_current_amps`

**Description:** Current in amperes

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_CURRENT_AMPS`

**Variable:** `self._sensor_current` (line 113)

#### `meraki_mt_door_status`

**Description:** Door sensor status (1 = open, 0 = closed)

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_DOOR_STATUS`

**Variable:** `self._sensor_door` (line 59)

#### `meraki_mt_downstream_power_enabled`

**Description:** Downstream power status (1 = enabled, 0 = disabled)

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_DOWNSTREAM_POWER_ENABLED`

**Variable:** `self._sensor_downstream_power` (line 143)

#### `meraki_mt_frequency_hz`

**Description:** Frequency in hertz

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_FREQUENCY_HZ`

**Variable:** `self._sensor_frequency` (line 137)

#### `meraki_mt_humidity_percent`

**Description:** Humidity percentage

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_HUMIDITY_PERCENT`

**Variable:** `self._sensor_humidity` (line 53)

#### `meraki_mt_indoor_air_quality_score`

**Description:** Indoor air quality score (0-100)

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_INDOOR_AIR_QUALITY_SCORE`

**Variable:** `self._sensor_air_quality` (line 101)

#### `meraki_mt_noise_db`

**Description:** Noise level in decibels

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_NOISE_DB`

**Variable:** `self._sensor_noise` (line 89)

#### `meraki_mt_pm25_ug_m3`

**Description:** PM2.5 particulate matter in micrograms per cubic meter

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_PM25_UG_M3`

**Variable:** `self._sensor_pm25` (line 83)

#### `meraki_mt_power_factor_percent`

**Description:** Power factor percentage

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_POWER_FACTOR_PERCENT`

**Variable:** `self._sensor_power_factor` (line 131)

#### `meraki_mt_real_power_watts`

**Description:** Real power in watts

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_REAL_POWER_WATTS`

**Variable:** `self._sensor_real_power` (line 119)

#### `meraki_mt_remote_lockout_status`

**Description:** Remote lockout switch status (1 = locked, 0 = unlocked)

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_REMOTE_LOCKOUT_STATUS`

**Variable:** `self._sensor_remote_lockout` (line 149)

#### `meraki_mt_temperature_celsius`

**Description:** Temperature reading in Celsius

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_TEMPERATURE_CELSIUS`

**Variable:** `self._sensor_temperature` (line 47)

#### `meraki_mt_tvoc_ppb`

**Description:** Total volatile organic compounds in parts per billion

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_TVOC_PPB`

**Variable:** `self._sensor_tvoc` (line 77)

#### `meraki_mt_voltage_volts`

**Description:** Voltage in volts

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_VOLTAGE_VOLTS`

**Variable:** `self._sensor_voltage` (line 107)

#### `meraki_mt_water_detected`

**Description:** Water detection status (1 = detected, 0 = not detected)

**Type:** gauge

**Labels:** `serial`, `name`, `sensor_type`

**Constant:** `MetricName.MT_WATER_DETECTED`

**Variable:** `self._sensor_water` (line 65)

### NetworkHealthCollector

**File:** `src/meraki_dashboard_exporter/collectors/network_health.py`

#### `meraki_ap_channel_utilization_2_4ghz_percent`

**Description:** 2.4GHz channel utilization percentage per AP

**Type:** gauge

**Labels:** `network_id`, `network_name`, `serial`, `name`, `model`, `type`

**Variable:** `self._ap_utilization_2_4ghz` (line 97)

#### `meraki_ap_channel_utilization_5ghz_percent`

**Description:** 5GHz channel utilization percentage per AP

**Type:** gauge

**Labels:** `network_id`, `network_name`, `serial`, `name`, `model`, `type`

**Variable:** `self._ap_utilization_5ghz` (line 103)

#### `meraki_network_bluetooth_clients_total`

**Description:** Total number of Bluetooth clients detected by MR devices in the last 5 minutes

**Type:** gauge

**Labels:** `network_id`, `network_name`

**Variable:** `self._network_bluetooth_clients_total` (line 143)

#### `meraki_network_channel_utilization_2_4ghz_percent`

**Description:** Network-wide average 2.4GHz channel utilization percentage

**Type:** gauge

**Labels:** `network_id`, `network_name`, `type`

**Variable:** `self._network_utilization_2_4ghz` (line 110)

#### `meraki_network_channel_utilization_5ghz_percent`

**Description:** Network-wide average 5GHz channel utilization percentage

**Type:** gauge

**Labels:** `network_id`, `network_name`, `type`

**Variable:** `self._network_utilization_5ghz` (line 116)

#### `meraki_network_wireless_connection_stats_total`

**Description:** Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)

**Type:** gauge

**Labels:** `network_id`, `network_name`, `stat_type`

**Constant:** `MetricName.NETWORK_WIRELESS_CONNECTION_STATS`

**Variable:** `self._network_connection_stats` (line 123)

#### `meraki_network_wireless_download_kbps`

**Description:** Network-wide wireless download bandwidth in kilobits per second

**Type:** gauge

**Labels:** `network_id`, `network_name`

**Variable:** `self._network_wireless_download_kbps` (line 130)

#### `meraki_network_wireless_upload_kbps`

**Description:** Network-wide wireless upload bandwidth in kilobits per second

**Type:** gauge

**Labels:** `network_id`, `network_name`

**Variable:** `self._network_wireless_upload_kbps` (line 136)

### OrganizationCollector

**File:** `src/meraki_dashboard_exporter/collectors/organization.py`

#### `meraki_org_api_requests_rate_limit`

**Description:** API rate limit for the organization

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Constant:** `MetricName.ORG_API_REQUESTS_RATE_LIMIT`

**Variable:** `self._api_rate_limit` (line 58)

#### `meraki_org_api_requests_total`

**Description:** Total API requests made by the organization

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Constant:** `MetricName.ORG_API_REQUESTS_TOTAL`

**Variable:** `self._api_requests_total` (line 52)

#### `meraki_org_clients_total`

**Description:** Total number of active clients in the organization (5-minute window from last complete interval)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._clients_total` (line 98)

#### `meraki_org_devices_by_model_total`

**Description:** Total number of devices by specific model

**Type:** gauge

**Labels:** `org_id`, `org_name`, `model`

**Variable:** `self._devices_by_model_total` (line 78)

#### `meraki_org_devices_total`

**Description:** Total number of devices in the organization

**Type:** gauge

**Labels:** `org_id`, `org_name`, `device_type`

**Constant:** `MetricName.ORG_DEVICES_TOTAL`

**Variable:** `self._devices_total` (line 72)

#### `meraki_org_info`

**Description:** Organization information

**Type:** info

**Labels:** `org_id`, `org_name`

**Variable:** `self._org_info` (line 45)

#### `meraki_org_licenses_expiring`

**Description:** Number of licenses expiring within 30 days

**Type:** gauge

**Labels:** `org_id`, `org_name`, `license_type`

**Constant:** `MetricName.ORG_LICENSES_EXPIRING`

**Variable:** `self._licenses_expiring` (line 91)

#### `meraki_org_licenses_total`

**Description:** Total number of licenses

**Type:** gauge

**Labels:** `org_id`, `org_name`, `license_type`, `status`

**Constant:** `MetricName.ORG_LICENSES_TOTAL`

**Variable:** `self._licenses_total` (line 85)

#### `meraki_org_networks_total`

**Description:** Total number of networks in the organization

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Constant:** `MetricName.ORG_NETWORKS_TOTAL`

**Variable:** `self._networks_total` (line 65)

#### `meraki_org_usage_downstream_kb`

**Description:** Downstream data usage in KB for the 5-minute window (last complete 5-min interval)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._usage_downstream_kb` (line 111)

#### `meraki_org_usage_total_kb`

**Description:** Total data usage in KB for the 5-minute window (last complete 5-min interval, e.g., 11:04 call returns 10:55-11:00)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._usage_total_kb` (line 105)

#### `meraki_org_usage_upstream_kb`

**Description:** Upstream data usage in KB for the 5-minute window (last complete 5-min interval)

**Type:** gauge

**Labels:** `org_id`, `org_name`

**Variable:** `self._usage_upstream_kb` (line 117)

## All Metrics (Alphabetical)

| Metric Name | Type | Collector | Description |
|-------------|------|-----------|-------------|
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