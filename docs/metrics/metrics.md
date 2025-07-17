# Metrics Reference

This page provides a comprehensive reference of all Prometheus metrics exposed by the Meraki Dashboard Exporter.

## Overview

The exporter provides metrics across several categories:

| Collector | Metrics | Description |
|-----------|---------|-------------|
| AlertsCollector | 3 | Active alerts by severity, type, and category |
| ConfigCollector | 14 | Organization security settings and configuration tracking |
| DeviceCollector | 6 | Device status, performance, and uptime metrics |
| MTSensorCollector | 18 | Environmental monitoring from MT sensors |
| NetworkHealthCollector | 8 | Network-wide wireless health and performance |
| OrganizationCollector | 13 | Organization-level metrics including API usage and licenses |

## Metrics by Collector

### AlertsCollector

**Source:** `src/meraki_dashboard_exporter/collectors/alerts.py`

#### `Unknown`

**Description:** Number of active Meraki assurance alerts

**Type:** gauge

**Labels:** 

**Variable:** `self._alerts_active` (line 28)

#### `Unknown`

**Description:** Total number of active alerts by severity

**Type:** gauge

**Labels:** 

**Variable:** `self._alerts_by_severity` (line 44)

#### `Unknown`

**Description:** Total number of active alerts per network

**Type:** gauge

**Labels:** 

**Variable:** `self._alerts_by_network` (line 51)

### ConfigCollector

**Source:** `src/meraki_dashboard_exporter/collectors/config.py`

#### `Unknown`

**Description:** Whether password expiration is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_password_expiration_enabled` (line 29)

#### `Unknown`

**Description:** Number of days before password expires (0 if not set)

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_password_expiration_days` (line 35)

#### `Unknown`

**Description:** Whether different passwords are enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_different_passwords_enabled` (line 41)

#### `Unknown`

**Description:** Number of different passwords required (0 if not set)

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_different_passwords_count` (line 47)

#### `Unknown`

**Description:** Whether strong passwords are enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_strong_passwords_enabled` (line 53)

#### `Unknown`

**Description:** Minimum password length required

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_minimum_password_length` (line 59)

#### `Unknown`

**Description:** Whether account lockout is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_account_lockout_enabled` (line 65)

#### `Unknown`

**Description:** Number of failed login attempts before lockout (0 if not set)

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_account_lockout_attempts` (line 71)

#### `Unknown`

**Description:** Whether idle timeout is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_idle_timeout_enabled` (line 77)

#### `Unknown`

**Description:** Minutes before idle timeout (0 if not set)

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_idle_timeout_minutes` (line 83)

#### `Unknown`

**Description:** Whether two-factor authentication is enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_two_factor_enabled` (line 89)

#### `Unknown`

**Description:** Whether login IP ranges are enforced (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_ip_ranges_enabled` (line 95)

#### `Unknown`

**Description:** Whether API key IP restrictions are enabled (1=enabled, 0=disabled)

**Type:** gauge

**Labels:** 

**Variable:** `self._login_security_api_ip_restrictions_enabled` (line 101)

#### `Unknown`

**Description:** Total number of configuration changes in the last 24 hours

**Type:** gauge

**Labels:** 

**Variable:** `self._configuration_changes_total` (line 108)

### DeviceCollector

**Source:** `src/meraki_dashboard_exporter/collectors/device.py`

#### `Unknown`

**Description:** Device online status (1 = online, 0 = offline)

**Type:** gauge

**Labels:** 

**Variable:** `self._device_up` (line 125)

#### `Unknown`

**Description:** Device status information

**Type:** gauge

**Labels:** 

**Variable:** `self._device_status_info` (line 131)

#### `Unknown`

**Description:** Device memory used in bytes

**Type:** gauge

**Labels:** 

**Variable:** `self._device_memory_used_bytes` (line 138)

#### `Unknown`

**Description:** Device memory free in bytes

**Type:** gauge

**Labels:** 

**Variable:** `self._device_memory_free_bytes` (line 144)

#### `Unknown`

**Description:** Device memory total provisioned in bytes

**Type:** gauge

**Labels:** 

**Variable:** `self._device_memory_total_bytes` (line 150)

#### `Unknown`

**Description:** Device memory usage percentage (maximum from most recent interval)

**Type:** gauge

**Labels:** 

**Variable:** `self._device_memory_usage_percent` (line 156)

### MTSensorCollector

**Source:** `src/meraki_dashboard_exporter/collectors/mt_sensor.py`

#### `Unknown`

**Description:** Temperature reading in Celsius

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_temperature` (line 51)

#### `Unknown`

**Description:** Humidity percentage

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_humidity` (line 57)

#### `Unknown`

**Description:** Door sensor status (1 = open, 0 = closed)

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_door` (line 63)

#### `Unknown`

**Description:** Water detection status (1 = detected, 0 = not detected)

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_water` (line 69)

#### `Unknown`

**Description:** CO2 level in parts per million

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_co2` (line 75)

#### `Unknown`

**Description:** Total volatile organic compounds in parts per billion

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_tvoc` (line 81)

#### `Unknown`

**Description:** PM2.5 particulate matter in micrograms per cubic meter

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_pm25` (line 87)

#### `Unknown`

**Description:** Noise level in decibels

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_noise` (line 93)

#### `Unknown`

**Description:** Battery level percentage

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_battery` (line 99)

#### `Unknown`

**Description:** Indoor air quality score (0-100)

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_air_quality` (line 105)

#### `Unknown`

**Description:** Voltage in volts

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_voltage` (line 111)

#### `Unknown`

**Description:** Current in amperes

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_current` (line 117)

#### `Unknown`

**Description:** Real power in watts

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_real_power` (line 123)

#### `Unknown`

**Description:** Apparent power in volt-amperes

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_apparent_power` (line 129)

#### `Unknown`

**Description:** Power factor percentage

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_power_factor` (line 135)

#### `Unknown`

**Description:** Frequency in hertz

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_frequency` (line 141)

#### `Unknown`

**Description:** Downstream power status (1 = enabled, 0 = disabled)

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_downstream_power` (line 147)

#### `Unknown`

**Description:** Remote lockout switch status (1 = locked, 0 = unlocked)

**Type:** gauge

**Labels:** 

**Variable:** `self._sensor_remote_lockout` (line 153)

### NetworkHealthCollector

**Source:** `src/meraki_dashboard_exporter/collectors/network_health.py`

#### `Unknown`

**Description:** 2.4GHz channel utilization percentage per AP

**Type:** gauge

**Labels:** 

**Variable:** `self._ap_utilization_2_4ghz` (line 50)

#### `Unknown`

**Description:** 5GHz channel utilization percentage per AP

**Type:** gauge

**Labels:** 

**Variable:** `self._ap_utilization_5ghz` (line 56)

#### `Unknown`

**Description:** Network-wide average 2.4GHz channel utilization percentage

**Type:** gauge

**Labels:** 

**Variable:** `self._network_utilization_2_4ghz` (line 63)

#### `Unknown`

**Description:** Network-wide average 5GHz channel utilization percentage

**Type:** gauge

**Labels:** 

**Variable:** `self._network_utilization_5ghz` (line 69)

#### `Unknown`

**Description:** Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success)

**Type:** gauge

**Labels:** 

**Variable:** `self._network_connection_stats` (line 76)

#### `Unknown`

**Description:** Network-wide wireless download bandwidth in kilobits per second

**Type:** gauge

**Labels:** 

**Variable:** `self._network_wireless_download_kbps` (line 83)

#### `Unknown`

**Description:** Network-wide wireless upload bandwidth in kilobits per second

**Type:** gauge

**Labels:** 

**Variable:** `self._network_wireless_upload_kbps` (line 89)

#### `Unknown`

**Description:** Total number of Bluetooth clients detected by MR devices in the last 5 minutes

**Type:** gauge

**Labels:** 

**Variable:** `self._network_bluetooth_clients_total` (line 96)

### OrganizationCollector

**Source:** `src/meraki_dashboard_exporter/collectors/organization.py`

#### `Unknown`

**Description:** Organization information

**Type:** info

**Labels:** 

**Variable:** `self._org_info` (line 50)

#### `Unknown`

**Description:** Total API requests made by the organization

**Type:** gauge

**Labels:** 

**Variable:** `self._api_requests_total` (line 57)

#### `Unknown`

**Description:** API rate limit for the organization

**Type:** gauge

**Labels:** 

**Variable:** `self._api_rate_limit` (line 63)

#### `Unknown`

**Description:** Total number of networks in the organization

**Type:** gauge

**Labels:** 

**Variable:** `self._networks_total` (line 70)

#### `Unknown`

**Description:** Total number of devices in the organization

**Type:** gauge

**Labels:** 

**Variable:** `self._devices_total` (line 77)

#### `Unknown`

**Description:** Total number of devices by specific model

**Type:** gauge

**Labels:** 

**Variable:** `self._devices_by_model_total` (line 83)

#### `Unknown`

**Description:** Total number of devices by availability status and product type

**Type:** gauge

**Labels:** 

**Variable:** `self._devices_availability_total` (line 90)

#### `Unknown`

**Description:** Total number of licenses

**Type:** gauge

**Labels:** 

**Variable:** `self._licenses_total` (line 97)

#### `Unknown`

**Description:** Number of licenses expiring within 30 days

**Type:** gauge

**Labels:** 

**Variable:** `self._licenses_expiring` (line 103)

#### `Unknown`

**Description:** Total number of active clients in the organization (5-minute window from last complete interval)

**Type:** gauge

**Labels:** 

**Variable:** `self._clients_total` (line 110)

#### `Unknown`

**Description:** Total data usage in KB for the 5-minute window (last complete 5-min interval, e.g., 11:04 call returns 10:55-11:00)

**Type:** gauge

**Labels:** 

**Variable:** `self._usage_total_kb` (line 117)

#### `Unknown`

**Description:** Downstream data usage in KB for the 5-minute window (last complete 5-min interval)

**Type:** gauge

**Labels:** 

**Variable:** `self._usage_downstream_kb` (line 123)

#### `Unknown`

**Description:** Upstream data usage in KB for the 5-minute window (last complete 5-min interval)

**Type:** gauge

**Labels:** 

**Variable:** `self._usage_upstream_kb` (line 129)

## Complete Metrics Index

All metrics in alphabetical order:

| Metric Name | Type | Collector | Description |
|-------------|------|-----------|-------------|
| `Unknown` | gauge | AlertsCollector | Number of active Meraki assurance alerts |
| `Unknown` | gauge | AlertsCollector | Total number of active alerts by severity |
| `Unknown` | gauge | AlertsCollector | Total number of active alerts per network |
| `Unknown` | gauge | ConfigCollector | Whether password expiration is enforced (1=enabled, 0=disabled) |
| `Unknown` | gauge | ConfigCollector | Number of days before password expires (0 if not set) |
| `Unknown` | gauge | ConfigCollector | Whether different passwords are enforced (1=enabled, 0=disabled) |
| `Unknown` | gauge | ConfigCollector | Number of different passwords required (0 if not set) |
| `Unknown` | gauge | ConfigCollector | Whether strong passwords are enforced (1=enabled, 0=disabled) |
| `Unknown` | gauge | ConfigCollector | Minimum password length required |
| `Unknown` | gauge | ConfigCollector | Whether account lockout is enforced (1=enabled, 0=disabled) |
| `Unknown` | gauge | ConfigCollector | Number of failed login attempts before lockout (0 if not set) |
| `Unknown` | gauge | ConfigCollector | Whether idle timeout is enforced (1=enabled, 0=disabled) |
| `Unknown` | gauge | ConfigCollector | Minutes before idle timeout (0 if not set) |
| `Unknown` | gauge | ConfigCollector | Whether two-factor authentication is enforced (1=enabled, 0=disabled) |
| `Unknown` | gauge | ConfigCollector | Whether login IP ranges are enforced (1=enabled, 0=disabled) |
| `Unknown` | gauge | ConfigCollector | Whether API key IP restrictions are enabled (1=enabled, 0=disabled) |
| `Unknown` | gauge | ConfigCollector | Total number of configuration changes in the last 24 hours |
| `Unknown` | gauge | DeviceCollector | Device online status (1 = online, 0 = offline) |
| `Unknown` | gauge | DeviceCollector | Device status information |
| `Unknown` | gauge | DeviceCollector | Device memory used in bytes |
| `Unknown` | gauge | DeviceCollector | Device memory free in bytes |
| `Unknown` | gauge | DeviceCollector | Device memory total provisioned in bytes |
| `Unknown` | gauge | DeviceCollector | Device memory usage percentage (maximum from most recent interval) |
| `Unknown` | info | OrganizationCollector | Organization information |
| `Unknown` | gauge | OrganizationCollector | Total API requests made by the organization |
| `Unknown` | gauge | OrganizationCollector | API rate limit for the organization |
| `Unknown` | gauge | OrganizationCollector | Total number of networks in the organization |
| `Unknown` | gauge | OrganizationCollector | Total number of devices in the organization |
| `Unknown` | gauge | OrganizationCollector | Total number of devices by specific model |
| `Unknown` | gauge | OrganizationCollector | Total number of devices by availability status and product type |
| `Unknown` | gauge | OrganizationCollector | Total number of licenses |
| `Unknown` | gauge | OrganizationCollector | Number of licenses expiring within 30 days |
| `Unknown` | gauge | OrganizationCollector | Total number of active clients in the organization (5-minute window from last complete interval) |
| `Unknown` | gauge | OrganizationCollector | Total data usage in KB for the 5-minute window (last complete 5-min interval, e.g., 11:04 call returns 10:55-11:00) |
| `Unknown` | gauge | OrganizationCollector | Downstream data usage in KB for the 5-minute window (last complete 5-min interval) |
| `Unknown` | gauge | OrganizationCollector | Upstream data usage in KB for the 5-minute window (last complete 5-min interval) |
| `Unknown` | gauge | MTSensorCollector | Temperature reading in Celsius |
| `Unknown` | gauge | MTSensorCollector | Humidity percentage |
| `Unknown` | gauge | MTSensorCollector | Door sensor status (1 = open, 0 = closed) |
| `Unknown` | gauge | MTSensorCollector | Water detection status (1 = detected, 0 = not detected) |
| `Unknown` | gauge | MTSensorCollector | CO2 level in parts per million |
| `Unknown` | gauge | MTSensorCollector | Total volatile organic compounds in parts per billion |
| `Unknown` | gauge | MTSensorCollector | PM2.5 particulate matter in micrograms per cubic meter |
| `Unknown` | gauge | MTSensorCollector | Noise level in decibels |
| `Unknown` | gauge | MTSensorCollector | Battery level percentage |
| `Unknown` | gauge | MTSensorCollector | Indoor air quality score (0-100) |
| `Unknown` | gauge | MTSensorCollector | Voltage in volts |
| `Unknown` | gauge | MTSensorCollector | Current in amperes |
| `Unknown` | gauge | MTSensorCollector | Real power in watts |
| `Unknown` | gauge | MTSensorCollector | Apparent power in volt-amperes |
| `Unknown` | gauge | MTSensorCollector | Power factor percentage |
| `Unknown` | gauge | MTSensorCollector | Frequency in hertz |
| `Unknown` | gauge | MTSensorCollector | Downstream power status (1 = enabled, 0 = disabled) |
| `Unknown` | gauge | MTSensorCollector | Remote lockout switch status (1 = locked, 0 = unlocked) |
| `Unknown` | gauge | NetworkHealthCollector | 2.4GHz channel utilization percentage per AP |
| `Unknown` | gauge | NetworkHealthCollector | 5GHz channel utilization percentage per AP |
| `Unknown` | gauge | NetworkHealthCollector | Network-wide average 2.4GHz channel utilization percentage |
| `Unknown` | gauge | NetworkHealthCollector | Network-wide average 5GHz channel utilization percentage |
| `Unknown` | gauge | NetworkHealthCollector | Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success) |
| `Unknown` | gauge | NetworkHealthCollector | Network-wide wireless download bandwidth in kilobits per second |
| `Unknown` | gauge | NetworkHealthCollector | Network-wide wireless upload bandwidth in kilobits per second |
| `Unknown` | gauge | NetworkHealthCollector | Total number of Bluetooth clients detected by MR devices in the last 5 minutes |

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