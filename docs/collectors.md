# Collector Reference

This page provides a comprehensive reference of all metric collectors in the Meraki Dashboard Exporter.

!!! summary "Collector Overview"
    🏗️ **Total Collectors:** 35
    📋 **Registered Collectors:** 10
    🔗 **Coordinators with Sub-collectors:** 4

## 🏛️ Architecture Overview

The collector system is organized in a hierarchical pattern:

### Update Tiers

Collectors are organized into three update tiers based on data volatility:

| Tier | Interval | Purpose | Examples |
|------|----------|---------|----------|
| 🚀 **FAST** | 60s | Real-time status, critical metrics | Device status, alerts, sensor readings |
| ⚡ **MEDIUM** | 300s | Regular metrics, performance data | Device metrics, network health, client data |
| 🐌 **SLOW** | 900s | Infrequent data, configuration | License usage, organization summaries |

### Collector Types

| Type | Description | Registration |
|------|-------------|--------------|
| **Main Collectors** | Top-level collectors with `@register_collector` | Automatic |
| **Coordinator Collectors** | Manage multiple sub-collectors | Automatic |
| **Sub-collectors** | Specialized collectors for specific metrics | Manual |
| **Device Collectors** | Device-type specific (MR, MS, MX, etc.) | Manual |

## 🧭 Quick Navigation

### By Update Tier

??? abstract "🚀 FAST Tier (1 collectors)"

    - [`MTSensorCollector`](#mtsensor): Collector for fast-moving sensor metrics (MT devices).

??? abstract "⚡ MEDIUM Tier (5 collectors)"

    - [`AlertsCollector`](#alerts): Collector for Meraki assurance alerts.
    - [`ClientsCollector`](#clients): Collector for client-level metrics across all networks.
    - [`DeviceCollector`](#device): Collector for device-level metrics.
    - [`NetworkHealthCollector`](#networkhealth): Collector for medium-moving network health metrics.
    - [`OrganizationCollector`](#organization): Collector for organization-level metrics.

??? abstract "🐌 SLOW Tier (1 collectors)"

    - [`ConfigCollector`](#config): Collector for configuration and security settings.

??? abstract "❓ Not specified Tier (28 collectors)"

    - [`APINotAvailableError`](#apinotavailableerror): Raised when an API endpoint is not available (404).
    - [`APIUsageCollector`](#apiusage): Collector for organization API usage metrics.
    - [`BaseDeviceCollector`](#basedevice): Base class for device-specific collectors.
    - [`BaseNetworkHealthCollector`](#basenetworkhealth): Base class for network health sub-collectors.
    - [`BaseOrganizationCollector`](#baseorganization): Base class for organization sub-collectors.
    - [`BaseSNMPCollector`](#basesnmp): Base class for SNMP collectors.
    - [`BaseSNMPCoordinator`](#basesnmpcoordinator): Base coordinator for SNMP collectors.
    - [`BluetoothCollector`](#bluetooth): Collector for Bluetooth clients detected by MR devices in a network.
    - [`ClientOverviewCollector`](#clientoverview): Collector for organization client overview metrics.
    - [`CloudControllerSNMPCollector`](#cloudcontrollersnmp): Collector for Meraki Cloud Controller SNMP metrics.
    - [`ConnectionStatsCollector`](#connectionstats): Collector for network-wide wireless connection statistics.
    - [`DataRatesCollector`](#datarates): Collector for network-wide wireless data rate metrics.
    - [`DataValidationError`](#datavalidationerror): Raised when API response data doesn't match expected format.
    - [`ExemplarCollector`](#exemplar): Collects exemplars for metrics during collection cycles.
    - [`LicenseCollector`](#license): Collector for organization license metrics.
    - [`MGCollector`](#mg): Collector for MG cellular gateway metrics.
    - [`MRCollector`](#mr): Collector for Meraki MR (Wireless AP) devices.
    - [`MRDeviceSNMPCollector`](#mrdevicesnmp): SNMP collector for Meraki MR (wireless) devices.
    - [`MSCollector`](#ms): Collector for Meraki MS (Switch) devices.
    - [`MSDeviceSNMPCollector`](#msdevicesnmp): SNMP collector for Meraki MS (switch) devices.
    - [`MTCollector`](#mt): Collector for Meraki MT (Sensor) devices.
    - [`MVCollector`](#mv): Collector for MV security camera metrics.
    - [`MXCollector`](#mx): Collector for MX security appliance metrics.
    - [`MetricCollector`](#metric): Abstract base class for metric collectors.
    - [`RFHealthCollector`](#rfhealth): Collector for wireless RF health metrics including channel utilization.
    - [`SNMPFastCoordinator`](#snmpfastcoordinator): SNMP coordinator for fast-updating metrics (60s default).
    - [`SNMPMediumCoordinator`](#snmpmediumcoordinator): SNMP coordinator for medium-updating metrics (300s default).
    - [`SNMPSlowCoordinator`](#snmpslowcoordinator): SNMP coordinator for slow-updating metrics (900s default).

### By Type

=== "Main Collectors"

    Auto-registered collectors that run on scheduled intervals:

    - [`AlertsCollector`](#alerts) - MEDIUM (300s)
    - [`ClientsCollector`](#clients) - MEDIUM (300s)
    - [`ConfigCollector`](#config) - SLOW (900s)
    - [`DeviceCollector`](#device) - MEDIUM (300s)
    - [`MTSensorCollector`](#mtsensor) - FAST (60s)
    - [`NetworkHealthCollector`](#networkhealth) - MEDIUM (300s)
    - [`OrganizationCollector`](#organization) - MEDIUM (300s)
    - [`SNMPFastCoordinator`](#snmpfastcoordinator) - Not specified
    - [`SNMPMediumCoordinator`](#snmpmediumcoordinator) - Not specified
    - [`SNMPSlowCoordinator`](#snmpslowcoordinator) - Not specified

=== "Device Collectors"

    Device-type specific collectors (MR, MS, MX, MT, MG, MV):

    - [`MGCollector`](#mg): Collector for MG cellular gateway metrics.
    - [`MRCollector`](#mr): Collector for Meraki MR (Wireless AP) devices.
    - [`MSCollector`](#ms): Collector for Meraki MS (Switch) devices.
    - [`MTCollector`](#mt): Collector for Meraki MT (Sensor) devices.
    - [`MVCollector`](#mv): Collector for MV security camera metrics.
    - [`MXCollector`](#mx): Collector for MX security appliance metrics.

=== "Sub-collectors"

    Specialized collectors managed by coordinator collectors:

    - [`APINotAvailableError`](#apinotavailableerror): Raised when an API endpoint is not available (404).
    - [`APIUsageCollector`](#apiusage): Collector for organization API usage metrics.
    - [`BaseDeviceCollector`](#basedevice): Base class for device-specific collectors.
    - [`BaseNetworkHealthCollector`](#basenetworkhealth): Base class for network health sub-collectors.
    - [`BaseOrganizationCollector`](#baseorganization): Base class for organization sub-collectors.
    - [`BaseSNMPCollector`](#basesnmp): Base class for SNMP collectors.
    - [`BaseSNMPCoordinator`](#basesnmpcoordinator): Base coordinator for SNMP collectors.
    - [`BluetoothCollector`](#bluetooth): Collector for Bluetooth clients detected by MR devices in a network.
    - [`ClientOverviewCollector`](#clientoverview): Collector for organization client overview metrics.
    - [`CloudControllerSNMPCollector`](#cloudcontrollersnmp): Collector for Meraki Cloud Controller SNMP metrics.
    - [`ConnectionStatsCollector`](#connectionstats): Collector for network-wide wireless connection statistics.
    - [`DataRatesCollector`](#datarates): Collector for network-wide wireless data rate metrics.
    - [`DataValidationError`](#datavalidationerror): Raised when API response data doesn't match expected format.
    - [`ExemplarCollector`](#exemplar): Collects exemplars for metrics during collection cycles.
    - [`LicenseCollector`](#license): Collector for organization license metrics.
    - [`MRDeviceSNMPCollector`](#mrdevicesnmp): SNMP collector for Meraki MR (wireless) devices.
    - [`MSDeviceSNMPCollector`](#msdevicesnmp): SNMP collector for Meraki MS (switch) devices.
    - [`MetricCollector`](#metric): Abstract base class for metric collectors.
    - [`RFHealthCollector`](#rfhealth): Collector for wireless RF health metrics including channel utilization.

## 📋 Collector Details

### APINotAvailableError { #apinotavailableerror }

!!! info "Collector Information"
    **Purpose:** Raised when an API endpoint is not available (404).
    **Source File:** `src/meraki_dashboard_exporter/core/error_handling.py`
    **Update Tier:** Not specified
    **Inherits From:** CollectorError

??? example "Technical Details"

    **Defined at:** Line 66

---

### APIUsageCollector { #apiusage }

!!! info "Collector Information"
    **Purpose:** Collector for organization API usage metrics.
    **Source File:** `src/meraki_dashboard_exporter/collectors/organization_collectors/api_usage.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseOrganizationCollector

??? example "Technical Details"

    **Defined at:** Line 20

---

### AlertsCollector { #alerts }

!!! info "Collector Information"
    **Purpose:** Collector for Meraki assurance alerts.
    **Source File:** `src/meraki_dashboard_exporter/collectors/alerts.py`
    **Update Tier:** MEDIUM (300s)
    **Inherits From:** MetricCollector

#### 📊 Metrics Collected

| Metric Variable | Type | Name | Description |
|-----------------|------|------|-------------|
| `_alerts_active` | gauge | `AlertMetricName.ALERTS_ACTIVE` | Number of active Meraki assurance alerts |
| `_alerts_by_severity` | gauge | `AlertMetricName.ALERTS_TOTAL_BY_SEVERITY` | Total number of active alerts by severity |
| `_alerts_by_network` | gauge | `AlertMetricName.ALERTS_TOTAL_BY_NETWORK` | Total number of active alerts per network |
| `_sensor_alerts_total` | gauge | `AlertMetricName.SENSOR_ALERTS_TOTAL` | Total number of sensor alerts in the last hour by metric type |

??? example "Technical Details"

    **Decorators:**
    - `@register_collector(UpdateTier.MEDIUM)`

    **Defined at:** Line 26
    **Metrics Count:** 4

---

### BaseDeviceCollector { #basedevice }

!!! info "Collector Information"
    **Purpose:** Base class for device-specific collectors.
    **Source File:** `src/meraki_dashboard_exporter/collectors/devices/base.py`
    **Update Tier:** Not specified
    **Inherits From:** ABC

??? example "Technical Details"

    **Defined at:** Line 25

---

### BaseNetworkHealthCollector { #basenetworkhealth }

!!! info "Collector Information"
    **Purpose:** Base class for network health sub-collectors.
    **Source File:** `src/meraki_dashboard_exporter/collectors/network_health_collectors/base.py`
    **Update Tier:** Not specified

??? example "Technical Details"

    **Defined at:** Line 18

---

### BaseOrganizationCollector { #baseorganization }

!!! info "Collector Information"
    **Purpose:** Base class for organization sub-collectors.
    **Source File:** `src/meraki_dashboard_exporter/collectors/organization_collectors/base.py`
    **Update Tier:** Not specified

??? example "Technical Details"

    **Defined at:** Line 18

---

### BaseSNMPCollector { #basesnmp }

!!! info "Collector Information"
    **Purpose:** Base class for SNMP collectors.
    **Source File:** `src/meraki_dashboard_exporter/collectors/snmp/base.py`
    **Update Tier:** Not specified
    **Inherits From:** ABC

??? example "Technical Details"

    **Defined at:** Line 56

---

### BaseSNMPCoordinator { #basesnmpcoordinator }

!!! info "Collector Information"
    **Purpose:** Base coordinator for SNMP collectors.
    **Source File:** `src/meraki_dashboard_exporter/collectors/snmp/snmp_coordinator.py`
    **Update Tier:** Not specified
    **Inherits From:** MetricCollector

??? example "Technical Details"

    **Defined at:** Line 36

---

### BluetoothCollector { #bluetooth }

!!! info "Collector Information"
    **Purpose:** Collector for Bluetooth clients detected by MR devices in a network.
    **Source File:** `src/meraki_dashboard_exporter/collectors/network_health_collectors/bluetooth.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseNetworkHealthCollector

??? example "Technical Details"

    **Defined at:** Line 20

---

### ClientOverviewCollector { #clientoverview }

!!! info "Collector Information"
    **Purpose:** Collector for organization client overview metrics.
    **Source File:** `src/meraki_dashboard_exporter/collectors/organization_collectors/client_overview.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseOrganizationCollector

??? example "Technical Details"

    **Defined at:** Line 20

---

### ClientsCollector { #clients }

!!! info "Collector Information"
    **Purpose:** Collector for client-level metrics across all networks.
    **Source File:** `src/meraki_dashboard_exporter/collectors/clients.py`
    **Update Tier:** MEDIUM (300s)
    **Inherits From:** MetricCollector

#### 📊 Metrics Collected

| Metric Variable | Type | Name | Description |
|-----------------|------|------|-------------|
| `client_status` | gauge | `ClientMetricName.CLIENT_STATUS` | Client online status (1 = online, 0 = offline) |
| `client_usage_sent` | gauge | `ClientMetricName.CLIENT_USAGE_SENT_KB` | Kilobytes sent by client in the last hour |
| `client_usage_recv` | gauge | `ClientMetricName.CLIENT_USAGE_RECV_KB` | Kilobytes received by client in the last hour |
| `client_usage_total` | gauge | `ClientMetricName.CLIENT_USAGE_TOTAL_KB` | Total kilobytes transferred by client in the last hour |
| `dns_cache_total` | gauge | `meraki_exporter_client_dns_cache_total` | Total number of entries in DNS cache |
| `dns_cache_valid` | gauge | `meraki_exporter_client_dns_cache_valid` | Number of valid entries in DNS cache |
| `dns_cache_expired` | gauge | `meraki_exporter_client_dns_cache_expired` | Number of expired entries in DNS cache |
| `dns_lookups_total` | counter | `meraki_exporter_client_dns_lookups_total` | Total number of DNS lookups performed |
| `dns_lookups_successful` | counter | `meraki_exporter_client_dns_lookups_successful_total` | Total number of successful DNS lookups |
| `dns_lookups_failed` | counter | `meraki_exporter_client_dns_lookups_failed_total` | Total number of failed DNS lookups |
| `dns_lookups_cached` | counter | `meraki_exporter_client_dns_lookups_cached_total` | Total number of DNS lookups served from cache |
| `client_store_total` | gauge | `meraki_exporter_client_store_total` | Total number of clients in the store |
| `client_store_networks` | gauge | `meraki_exporter_client_store_networks` | Total number of networks with clients |
| `client_capabilities_count` | gauge | `ClientMetricName.WIRELESS_CLIENT_CAPABILITIES_COUNT` | Count of wireless clients by capability |
| `clients_per_ssid` | gauge | `ClientMetricName.CLIENTS_PER_SSID_COUNT` | Count of clients per SSID |
| `clients_per_vlan` | gauge | `ClientMetricName.CLIENTS_PER_VLAN_COUNT` | Count of clients per VLAN |
| `client_app_usage_sent` | gauge | `ClientMetricName.CLIENT_APPLICATION_USAGE_SENT_KB` | Kilobytes sent by client per application in the last hour |
| `client_app_usage_recv` | gauge | `ClientMetricName.CLIENT_APPLICATION_USAGE_RECV_KB` | Kilobytes received by client per application in the last hour |
| `client_app_usage_total` | gauge | `ClientMetricName.CLIENT_APPLICATION_USAGE_TOTAL_KB` | Total kilobytes transferred by client per application in the last hour |
| `wireless_client_rssi` | gauge | `ClientMetricName.WIRELESS_CLIENT_RSSI` | Wireless client RSSI (Received Signal Strength Indicator) in dBm |
| `wireless_client_snr` | gauge | `ClientMetricName.WIRELESS_CLIENT_SNR` | Wireless client SNR (Signal-to-Noise Ratio) in dB |

??? example "Technical Details"

    **Decorators:**
    - `@register_collector(UpdateTier.MEDIUM)`

    **Defined at:** Line 26
    **Metrics Count:** 21

---

### CloudControllerSNMPCollector { #cloudcontrollersnmp }

!!! info "Collector Information"
    **Purpose:** Collector for Meraki Cloud Controller SNMP metrics.
    **Source File:** `src/meraki_dashboard_exporter/collectors/snmp/cloud_controller.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseSNMPCollector

#### 📊 Metrics Collected

| Metric Variable | Type | Name | Description |
|-----------------|------|------|-------------|
| `device_status_metric` | gauge | `meraki_snmp_organization_device_status` | Device online/offline status from cloud SNMP (1=online, 0=offline) |
| `client_count_metric` | gauge | `meraki_snmp_organization_device_client_count` | Number of clients connected to device from cloud SNMP |
| `interface_packets_sent` | counter | `meraki_snmp_organization_interface_packets_sent_total` | Total packets sent on interface from cloud SNMP |
| `interface_packets_received` | counter | `meraki_snmp_organization_interface_packets_received_total` | Total packets received on interface from cloud SNMP |
| `interface_bytes_sent` | counter | `meraki_snmp_organization_interface_bytes_sent_total` | Total bytes sent on interface from cloud SNMP |
| `interface_bytes_received` | counter | `meraki_snmp_organization_interface_bytes_received_total` | Total bytes received on interface from cloud SNMP |
| `snmp_up_metric` | gauge | `meraki_snmp_organization_up` | Whether cloud controller SNMP is responding (1=up, 0=down) |

??? example "Technical Details"

    **Defined at:** Line 43
    **Metrics Count:** 7

---

### ConfigCollector { #config }

!!! info "Collector Information"
    **Purpose:** Collector for configuration and security settings.
    **Source File:** `src/meraki_dashboard_exporter/collectors/config.py`
    **Update Tier:** SLOW (900s)
    **Inherits From:** MetricCollector

#### 📊 Metrics Collected

| Metric Variable | Type | Name | Description |
|-----------------|------|------|-------------|
| `_login_security_password_expiration_enabled` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_ENABLED` | Whether password expiration is enforced (1=enabled, 0=disabled) |
| `_login_security_password_expiration_days` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_DAYS` | Number of days before password expires (0 if not set) |
| `_login_security_different_passwords_enabled` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_ENABLED` | Whether different passwords are enforced (1=enabled, 0=disabled) |
| `_login_security_different_passwords_count` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_DIFFERENT_PASSWORDS_COUNT` | Number of different passwords required (0 if not set) |
| `_login_security_strong_passwords_enabled` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_STRONG_PASSWORDS_ENABLED` | Whether strong passwords are enforced (1=enabled, 0=disabled) |
| `_login_security_minimum_password_length` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_MINIMUM_PASSWORD_LENGTH` | Minimum password length required |
| `_login_security_account_lockout_enabled` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ENABLED` | Whether account lockout is enforced (1=enabled, 0=disabled) |
| `_login_security_account_lockout_attempts` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_ACCOUNT_LOCKOUT_ATTEMPTS` | Number of failed login attempts before lockout (0 if not set) |
| `_login_security_idle_timeout_enabled` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_IDLE_TIMEOUT_ENABLED` | Whether idle timeout is enforced (1=enabled, 0=disabled) |
| `_login_security_idle_timeout_minutes` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_IDLE_TIMEOUT_MINUTES` | Minutes before idle timeout (0 if not set) |
| `_login_security_two_factor_enabled` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_TWO_FACTOR_ENABLED` | Whether two-factor authentication is enforced (1=enabled, 0=disabled) |
| `_login_security_ip_ranges_enabled` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_IP_RANGES_ENABLED` | Whether login IP ranges are enforced (1=enabled, 0=disabled) |
| `_login_security_api_ip_restrictions_enabled` | gauge | `OrgMetricName.ORG_LOGIN_SECURITY_API_IP_RESTRICTIONS_ENABLED` | Whether API key IP restrictions are enabled (1=enabled, 0=disabled) |
| `_configuration_changes_total` | gauge | `OrgMetricName.ORG_CONFIGURATION_CHANGES_TOTAL` | Total number of configuration changes in the last 24 hours |

??? example "Technical Details"

    **Decorators:**
    - `@register_collector(UpdateTier.SLOW)`

    **Defined at:** Line 26
    **Metrics Count:** 14

---

### ConnectionStatsCollector { #connectionstats }

!!! info "Collector Information"
    **Purpose:** Collector for network-wide wireless connection statistics.
    **Source File:** `src/meraki_dashboard_exporter/collectors/network_health_collectors/connection_stats.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseNetworkHealthCollector

??? example "Technical Details"

    **Defined at:** Line 21

---

### DataRatesCollector { #datarates }

!!! info "Collector Information"
    **Purpose:** Collector for network-wide wireless data rate metrics.
    **Source File:** `src/meraki_dashboard_exporter/collectors/network_health_collectors/data_rates.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseNetworkHealthCollector

??? example "Technical Details"

    **Defined at:** Line 20

---

### DataValidationError { #datavalidationerror }

!!! info "Collector Information"
    **Purpose:** Raised when API response data doesn't match expected format.
    **Source File:** `src/meraki_dashboard_exporter/core/error_handling.py`
    **Update Tier:** Not specified
    **Inherits From:** CollectorError

??? example "Technical Details"

    **Defined at:** Line 78

---

### DeviceCollector { #device }

!!! info "Collector Information"
    **Purpose:** Collector for device-level metrics.
    **Source File:** `src/meraki_dashboard_exporter/collectors/device.py`
    **Update Tier:** MEDIUM (300s)
    **Inherits From:** MetricCollector

#### 📊 Metrics Collected

| Metric Variable | Type | Name | Description |
|-----------------|------|------|-------------|
| `_device_up` | gauge | `DeviceMetricName.DEVICE_UP` | Device online status (1 = online, 0 = offline) |
| `_device_status_info` | gauge | `DeviceMetricName.DEVICE_STATUS_INFO` | Device status information |
| `_device_memory_used_bytes` | gauge | `DeviceMetricName.DEVICE_MEMORY_USED_BYTES` | Device memory used in bytes |
| `_device_memory_free_bytes` | gauge | `DeviceMetricName.DEVICE_MEMORY_FREE_BYTES` | Device memory free in bytes |
| `_device_memory_total_bytes` | gauge | `DeviceMetricName.DEVICE_MEMORY_TOTAL_BYTES` | Device memory total provisioned in bytes |
| `_device_memory_usage_percent` | gauge | `DeviceMetricName.DEVICE_MEMORY_USAGE_PERCENT` | Device memory usage percentage (maximum from most recent interval) |

#### 🔗 Sub-collectors

This coordinator manages the following sub-collectors:

- [`MGCollector`](#mg) (as `self.mg_collector`)
- [`MRCollector`](#mr) (as `self.mr_collector`)
- [`MSCollector`](#ms) (as `self.ms_collector`)
- [`MTCollector`](#mt) (as `self.mt_collector`)
- [`MVCollector`](#mv) (as `self.mv_collector`)
- [`MXCollector`](#mx) (as `self.mx_collector`)

??? example "Technical Details"

    **Decorators:**
    - `@register_collector(UpdateTier.MEDIUM)`

    **Defined at:** Line 37
    **Metrics Count:** 6

---

### ExemplarCollector { #exemplar }

!!! info "Collector Information"
    **Purpose:** Collects exemplars for metrics during collection cycles.
    **Source File:** `src/meraki_dashboard_exporter/core/exemplars.py`
    **Update Tier:** Not specified

??? example "Technical Details"

    **Defined at:** Line 152

---

### LicenseCollector { #license }

!!! info "Collector Information"
    **Purpose:** Collector for organization license metrics.
    **Source File:** `src/meraki_dashboard_exporter/collectors/organization_collectors/license.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseOrganizationCollector

??? example "Technical Details"

    **Defined at:** Line 21

---

### MGCollector { #mg }

!!! info "Collector Information"
    **Purpose:** Collector for MG cellular gateway metrics.
    **Source File:** `src/meraki_dashboard_exporter/collectors/devices/mg.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseDeviceCollector

??? example "Technical Details"

    **Defined at:** Line 16

---

### MRCollector { #mr }

!!! info "Collector Information"
    **Purpose:** Collector for Meraki MR (Wireless AP) devices.
    **Source File:** `src/meraki_dashboard_exporter/collectors/devices/mr.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseDeviceCollector

#### 📊 Metrics Collected

| Metric Variable | Type | Name | Description |
|-----------------|------|------|-------------|
| `_ap_clients` | gauge | `MRMetricName.MR_CLIENTS_CONNECTED` | Number of clients connected to access point |
| `_ap_connection_stats` | gauge | `MRMetricName.MR_CONNECTION_STATS` | Wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success) |
| `_mr_power_info` | gauge | `MRMetricName.MR_POWER_INFO` | Access point power information |
| `_mr_power_ac_connected` | gauge | `MRMetricName.MR_POWER_AC_CONNECTED` | Access point AC power connection status (1 = connected, 0 = not connected) |
| `_mr_power_poe_connected` | gauge | `MRMetricName.MR_POWER_POE_CONNECTED` | Access point PoE power connection status (1 = connected, 0 = not connected) |
| `_mr_port_poe_info` | gauge | `MRMetricName.MR_PORT_POE_INFO` | Access point port PoE information |
| `_mr_port_link_negotiation_info` | gauge | `MRMetricName.MR_PORT_LINK_NEGOTIATION_INFO` | Access point port link negotiation information |
| `_mr_port_link_negotiation_speed` | gauge | `MRMetricName.MR_PORT_LINK_NEGOTIATION_SPEED_MBPS` | Access point port link negotiation speed in Mbps |
| `_mr_aggregation_enabled` | gauge | `MRMetricName.MR_AGGREGATION_ENABLED` | Access point port aggregation enabled status (1 = enabled, 0 = disabled) |
| `_mr_aggregation_speed` | gauge | `MRMetricName.MR_AGGREGATION_SPEED_MBPS` | Access point total aggregated port speed in Mbps |
| `_mr_packets_downstream_total` | gauge | `MRMetricName.MR_PACKETS_DOWNSTREAM_TOTAL` | Total downstream packets transmitted by access point (5-minute window) |
| `_mr_packets_downstream_lost` | gauge | `MRMetricName.MR_PACKETS_DOWNSTREAM_LOST` | Downstream packets lost by access point (5-minute window) |
| `_mr_packet_loss_downstream_percent` | gauge | `MRMetricName.MR_PACKET_LOSS_DOWNSTREAM_PERCENT` | Downstream packet loss percentage for access point (5-minute window) |
| `_mr_packets_upstream_total` | gauge | `MRMetricName.MR_PACKETS_UPSTREAM_TOTAL` | Total upstream packets received by access point (5-minute window) |
| `_mr_packets_upstream_lost` | gauge | `MRMetricName.MR_PACKETS_UPSTREAM_LOST` | Upstream packets lost by access point (5-minute window) |
| `_mr_packet_loss_upstream_percent` | gauge | `MRMetricName.MR_PACKET_LOSS_UPSTREAM_PERCENT` | Upstream packet loss percentage for access point (5-minute window) |
| `_mr_packets_total` | gauge | `MRMetricName.MR_PACKETS_TOTAL` | Total packets (upstream + downstream) for access point (5-minute window) |
| `_mr_packets_lost_total` | gauge | `MRMetricName.MR_PACKETS_LOST_TOTAL` | Total packets lost (upstream + downstream) for access point (5-minute window) |
| `_mr_packet_loss_total_percent` | gauge | `MRMetricName.MR_PACKET_LOSS_TOTAL_PERCENT` | Total packet loss percentage (upstream + downstream) for access point (5-minute window) |
| `_mr_network_packets_downstream_total` | gauge | `MRMetricName.MR_NETWORK_PACKETS_DOWNSTREAM_TOTAL` | Total downstream packets for all access points in network (5-minute window) |
| `_mr_network_packets_downstream_lost` | gauge | `MRMetricName.MR_NETWORK_PACKETS_DOWNSTREAM_LOST` | Downstream packets lost for all access points in network (5-minute window) |
| `_mr_network_packet_loss_downstream_percent` | gauge | `MRMetricName.MR_NETWORK_PACKET_LOSS_DOWNSTREAM_PERCENT` | Downstream packet loss percentage for all access points in network (5-minute window) |
| `_mr_network_packets_upstream_total` | gauge | `MRMetricName.MR_NETWORK_PACKETS_UPSTREAM_TOTAL` | Total upstream packets for all access points in network (5-minute window) |
| `_mr_network_packets_upstream_lost` | gauge | `MRMetricName.MR_NETWORK_PACKETS_UPSTREAM_LOST` | Upstream packets lost for all access points in network (5-minute window) |
| `_mr_network_packet_loss_upstream_percent` | gauge | `MRMetricName.MR_NETWORK_PACKET_LOSS_UPSTREAM_PERCENT` | Upstream packet loss percentage for all access points in network (5-minute window) |
| `_mr_network_packets_total` | gauge | `MRMetricName.MR_NETWORK_PACKETS_TOTAL` | Total packets (upstream + downstream) for all access points in network (5-minute window) |
| `_mr_network_packets_lost_total` | gauge | `MRMetricName.MR_NETWORK_PACKETS_LOST_TOTAL` | Total packets lost (upstream + downstream) for all access points in network (5-minute window) |
| `_mr_network_packet_loss_total_percent` | gauge | `MRMetricName.MR_NETWORK_PACKET_LOSS_TOTAL_PERCENT` | Total packet loss percentage (upstream + downstream) for all access points in network (5-minute window) |
| `_mr_cpu_load_5min` | gauge | `MRMetricName.MR_CPU_LOAD_5MIN` | Access point CPU load average over 5 minutes (normalized to 0-100 per core) |
| `_mr_radio_broadcasting` | gauge | `MRMetricName.MR_RADIO_BROADCASTING` | Access point radio broadcasting status (1 = broadcasting, 0 = not broadcasting) |
| `_mr_radio_channel` | gauge | `MRMetricName.MR_RADIO_CHANNEL` | Access point radio channel number |
| `_mr_radio_channel_width` | gauge | `MRMetricName.MR_RADIO_CHANNEL_WIDTH_MHZ` | Access point radio channel width in MHz |
| `_mr_radio_power` | gauge | `MRMetricName.MR_RADIO_POWER_DBM` | Access point radio transmit power in dBm |
| `_ssid_usage_total_mb` | gauge | `MRMetricName.MR_SSID_USAGE_TOTAL_MB` | Total data usage in MB by SSID over the last day |
| `_ssid_usage_downstream_mb` | gauge | `MRMetricName.MR_SSID_USAGE_DOWNSTREAM_MB` | Downstream data usage in MB by SSID over the last day |
| `_ssid_usage_upstream_mb` | gauge | `MRMetricName.MR_SSID_USAGE_UPSTREAM_MB` | Upstream data usage in MB by SSID over the last day |
| `_ssid_usage_percentage` | gauge | `MRMetricName.MR_SSID_USAGE_PERCENTAGE` | Percentage of total organization data usage by SSID over the last day |
| `_ssid_client_count` | gauge | `MRMetricName.MR_SSID_CLIENT_COUNT` | Number of clients connected to SSID over the last day |

??? example "Technical Details"

    **Defined at:** Line 23
    **Metrics Count:** 38

---

### MRDeviceSNMPCollector { #mrdevicesnmp }

!!! info "Collector Information"
    **Purpose:** SNMP collector for Meraki MR (wireless) devices.
    **Source File:** `src/meraki_dashboard_exporter/collectors/snmp/device_snmp.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseSNMPCollector

#### 📊 Metrics Collected

| Metric Variable | Type | Name | Description |
|-----------------|------|------|-------------|
| `snmp_up_metric` | gauge | `meraki_snmp_mr_up` | Whether MR device SNMP is responding (1=up, 0=down) |
| `uptime_metric` | gauge | `meraki_snmp_mr_uptime_seconds` | Device uptime in seconds from SNMP |

??? example "Technical Details"

    **Defined at:** Line 34
    **Metrics Count:** 2

---

### MSCollector { #ms }

!!! info "Collector Information"
    **Purpose:** Collector for Meraki MS (Switch) devices.
    **Source File:** `src/meraki_dashboard_exporter/collectors/devices/ms.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseDeviceCollector

#### 📊 Metrics Collected

| Metric Variable | Type | Name | Description |
|-----------------|------|------|-------------|
| `_switch_port_status` | gauge | `MSMetricName.MS_PORT_STATUS` | Switch port status (1 = connected, 0 = disconnected) |
| `_switch_port_traffic` | gauge | `MSMetricName.MS_PORT_TRAFFIC_BYTES` | Switch port traffic rate in bytes per second (averaged over 1 hour) |
| `_switch_port_usage` | gauge | `MSMetricName.MS_PORT_USAGE_BYTES` | Switch port data usage in bytes over the last 1 hour |
| `_switch_port_client_count` | gauge | `MSMetricName.MS_PORT_CLIENT_COUNT` | Number of clients connected to switch port |
| `_switch_power` | gauge | `MSMetricName.MS_POWER_USAGE_WATTS` | Switch power usage in watts |
| `_switch_poe_port_power` | gauge | `MSMetricName.MS_POE_PORT_POWER_WATTS` | Per-port POE power consumption in watt-hours (Wh) over the last 1 hour |
| `_switch_poe_total_power` | gauge | `MSMetricName.MS_POE_TOTAL_POWER_WATTS` | Total POE power consumption for switch in watt-hours (Wh) |
| `_switch_poe_budget` | gauge | `MSMetricName.MS_POE_BUDGET_WATTS` | Total POE power budget for switch in watts |
| `_switch_poe_network_total` | gauge | `MSMetricName.MS_POE_NETWORK_TOTAL_WATTS` | Total POE power consumption for all switches in network in watt-hours (Wh) |
| `_switch_stp_priority` | gauge | `MSMetricName.MS_STP_PRIORITY` | Switch STP (Spanning Tree Protocol) priority |
| `_switch_port_packets_total` | gauge | `MSMetricName.MS_PORT_PACKETS_TOTAL` | Total packets on switch port (5-minute window) |
| `_switch_port_packets_broadcast` | gauge | `MSMetricName.MS_PORT_PACKETS_BROADCAST` | Broadcast packets on switch port (5-minute window) |
| `_switch_port_packets_multicast` | gauge | `MSMetricName.MS_PORT_PACKETS_MULTICAST` | Multicast packets on switch port (5-minute window) |
| `_switch_port_packets_crcerrors` | gauge | `MSMetricName.MS_PORT_PACKETS_CRCERRORS` | CRC align error packets on switch port (5-minute window) |
| `_switch_port_packets_fragments` | gauge | `MSMetricName.MS_PORT_PACKETS_FRAGMENTS` | Fragment packets on switch port (5-minute window) |
| `_switch_port_packets_collisions` | gauge | `MSMetricName.MS_PORT_PACKETS_COLLISIONS` | Collision packets on switch port (5-minute window) |
| `_switch_port_packets_topologychanges` | gauge | `MSMetricName.MS_PORT_PACKETS_TOPOLOGYCHANGES` | Topology change packets on switch port (5-minute window) |
| `_switch_port_packets_rate_total` | gauge | `MSMetricName.MS_PORT_PACKETS_RATE_TOTAL` | Total packet rate on switch port (packets per second, 5-minute average) |
| `_switch_port_packets_rate_broadcast` | gauge | `MSMetricName.MS_PORT_PACKETS_RATE_BROADCAST` | Broadcast packet rate on switch port (packets per second, 5-minute average) |
| `_switch_port_packets_rate_multicast` | gauge | `MSMetricName.MS_PORT_PACKETS_RATE_MULTICAST` | Multicast packet rate on switch port (packets per second, 5-minute average) |
| `_switch_port_packets_rate_crcerrors` | gauge | `MSMetricName.MS_PORT_PACKETS_RATE_CRCERRORS` | CRC align error packet rate on switch port (packets per second, 5-minute average) |
| `_switch_port_packets_rate_fragments` | gauge | `MSMetricName.MS_PORT_PACKETS_RATE_FRAGMENTS` | Fragment packet rate on switch port (packets per second, 5-minute average) |
| `_switch_port_packets_rate_collisions` | gauge | `MSMetricName.MS_PORT_PACKETS_RATE_COLLISIONS` | Collision packet rate on switch port (packets per second, 5-minute average) |
| `_switch_port_packets_rate_topologychanges` | gauge | `MSMetricName.MS_PORT_PACKETS_RATE_TOPOLOGYCHANGES` | Topology change packet rate on switch port (packets per second, 5-minute average) |

??? example "Technical Details"

    **Defined at:** Line 23
    **Metrics Count:** 24

---

### MSDeviceSNMPCollector { #msdevicesnmp }

!!! info "Collector Information"
    **Purpose:** SNMP collector for Meraki MS (switch) devices.
    **Source File:** `src/meraki_dashboard_exporter/collectors/snmp/device_snmp.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseSNMPCollector

#### 📊 Metrics Collected

| Metric Variable | Type | Name | Description |
|-----------------|------|------|-------------|
| `snmp_up_metric` | gauge | `meraki_snmp_ms_up` | Whether MS device SNMP is responding (1=up, 0=down) |
| `uptime_metric` | gauge | `meraki_snmp_ms_uptime_seconds` | Device uptime in seconds from SNMP |
| `mac_table_size_metric` | gauge | `meraki_snmp_ms_mac_table_size` | Number of MAC addresses in forwarding table |
| `bridge_num_ports_metric` | gauge | `meraki_snmp_ms_bridge_num_ports` | Number of bridge ports from SNMP |

??? example "Technical Details"

    **Defined at:** Line 125
    **Metrics Count:** 4

---

### MTCollector { #mt }

!!! info "Collector Information"
    **Purpose:** Collector for Meraki MT (Sensor) devices.
    **Source File:** `src/meraki_dashboard_exporter/collectors/devices/mt.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseDeviceCollector

??? example "Technical Details"

    **Defined at:** Line 32

---

### MTSensorCollector { #mtsensor }

!!! info "Collector Information"
    **Purpose:** Collector for fast-moving sensor metrics (MT devices).
    **Source File:** `src/meraki_dashboard_exporter/collectors/mt_sensor.py`
    **Update Tier:** FAST (60s)
    **Inherits From:** MetricCollector

#### 📊 Metrics Collected

| Metric Variable | Type | Name | Description |
|-----------------|------|------|-------------|
| `_sensor_temperature` | gauge | `MTMetricName.MT_TEMPERATURE_CELSIUS` | Temperature reading in Celsius |
| `_sensor_humidity` | gauge | `MTMetricName.MT_HUMIDITY_PERCENT` | Humidity percentage |
| `_sensor_door` | gauge | `MTMetricName.MT_DOOR_STATUS` | Door sensor status (1 = open, 0 = closed) |
| `_sensor_water` | gauge | `MTMetricName.MT_WATER_DETECTED` | Water detection status (1 = detected, 0 = not detected) |
| `_sensor_co2` | gauge | `MTMetricName.MT_CO2_PPM` | CO2 level in parts per million |
| `_sensor_tvoc` | gauge | `MTMetricName.MT_TVOC_PPB` | Total volatile organic compounds in parts per billion |
| `_sensor_pm25` | gauge | `MTMetricName.MT_PM25_UG_M3` | PM2.5 particulate matter in micrograms per cubic meter |
| `_sensor_noise` | gauge | `MTMetricName.MT_NOISE_DB` | Noise level in decibels |
| `_sensor_battery` | gauge | `MTMetricName.MT_BATTERY_PERCENTAGE` | Battery level percentage |
| `_sensor_air_quality` | gauge | `MTMetricName.MT_INDOOR_AIR_QUALITY_SCORE` | Indoor air quality score (0-100) |
| `_sensor_voltage` | gauge | `MTMetricName.MT_VOLTAGE_VOLTS` | Voltage in volts |
| `_sensor_current` | gauge | `MTMetricName.MT_CURRENT_AMPS` | Current in amperes |
| `_sensor_real_power` | gauge | `MTMetricName.MT_REAL_POWER_WATTS` | Real power in watts |
| `_sensor_apparent_power` | gauge | `MTMetricName.MT_APPARENT_POWER_VA` | Apparent power in volt-amperes |
| `_sensor_power_factor` | gauge | `MTMetricName.MT_POWER_FACTOR_PERCENT` | Power factor percentage |
| `_sensor_frequency` | gauge | `MTMetricName.MT_FREQUENCY_HZ` | Frequency in hertz |
| `_sensor_downstream_power` | gauge | `MTMetricName.MT_DOWNSTREAM_POWER_ENABLED` | Downstream power status (1 = enabled, 0 = disabled) |
| `_sensor_remote_lockout` | gauge | `MTMetricName.MT_REMOTE_LOCKOUT_STATUS` | Remote lockout switch status (1 = locked, 0 = unlocked) |

#### 🔗 Sub-collectors

This coordinator manages the following sub-collectors:

- [`MTCollector`](#mt) (as `self.mt_collector`)

??? example "Technical Details"

    **Decorators:**
    - `@register_collector(UpdateTier.FAST)`

    **Defined at:** Line 30
    **Metrics Count:** 18

---

### MVCollector { #mv }

!!! info "Collector Information"
    **Purpose:** Collector for MV security camera metrics.
    **Source File:** `src/meraki_dashboard_exporter/collectors/devices/mv.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseDeviceCollector

??? example "Technical Details"

    **Defined at:** Line 16

---

### MXCollector { #mx }

!!! info "Collector Information"
    **Purpose:** Collector for MX security appliance metrics.
    **Source File:** `src/meraki_dashboard_exporter/collectors/devices/mx.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseDeviceCollector

??? example "Technical Details"

    **Defined at:** Line 16

---

### MetricCollector { #metric }

!!! info "Collector Information"
    **Purpose:** Abstract base class for metric collectors.
    **Source File:** `src/meraki_dashboard_exporter/core/collector.py`
    **Update Tier:** Not specified
    **Inherits From:** ABC

??? example "Technical Details"

    **Defined at:** Line 25

---

### NetworkHealthCollector { #networkhealth }

!!! info "Collector Information"
    **Purpose:** Collector for medium-moving network health metrics.
    **Source File:** `src/meraki_dashboard_exporter/collectors/network_health.py`
    **Update Tier:** MEDIUM (300s)
    **Inherits From:** MetricCollector

#### 📊 Metrics Collected

| Metric Variable | Type | Name | Description |
|-----------------|------|------|-------------|
| `_ap_utilization_2_4ghz` | gauge | `NetworkHealthMetricName.AP_CHANNEL_UTILIZATION_2_4GHZ_PERCENT` | 2.4GHz channel utilization percentage per AP |
| `_ap_utilization_5ghz` | gauge | `NetworkHealthMetricName.AP_CHANNEL_UTILIZATION_5GHZ_PERCENT` | 5GHz channel utilization percentage per AP |
| `_network_utilization_2_4ghz` | gauge | `NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_2_4GHZ_PERCENT` | Network-wide average 2.4GHz channel utilization percentage |
| `_network_utilization_5ghz` | gauge | `NetworkHealthMetricName.NETWORK_CHANNEL_UTILIZATION_5GHZ_PERCENT` | Network-wide average 5GHz channel utilization percentage |
| `_network_connection_stats` | gauge | `NetworkMetricName.NETWORK_WIRELESS_CONNECTION_STATS` | Network-wide wireless connection statistics over the last 30 minutes (assoc/auth/dhcp/dns/success) |
| `_network_wireless_download_kbps` | gauge | `NetworkHealthMetricName.NETWORK_WIRELESS_DOWNLOAD_KBPS` | Network-wide wireless download bandwidth in kilobits per second |
| `_network_wireless_upload_kbps` | gauge | `NetworkHealthMetricName.NETWORK_WIRELESS_UPLOAD_KBPS` | Network-wide wireless upload bandwidth in kilobits per second |
| `_network_bluetooth_clients_total` | gauge | `NetworkHealthMetricName.NETWORK_BLUETOOTH_CLIENTS_TOTAL` | Total number of Bluetooth clients detected by MR devices in the last 5 minutes |

#### 🔗 Sub-collectors

This coordinator manages the following sub-collectors:

- [`RFHealthCollector`](#rfhealth) (as `self.rf_health_collector`)
- [`ConnectionStatsCollector`](#connectionstats) (as `self.connection_stats_collector`)
- [`DataRatesCollector`](#datarates) (as `self.data_rates_collector`)
- [`BluetoothCollector`](#bluetooth) (as `self.bluetooth_collector`)

??? example "Technical Details"

    **Decorators:**
    - `@register_collector(UpdateTier.MEDIUM)`

    **Defined at:** Line 31
    **Metrics Count:** 8

---

### OrganizationCollector { #organization }

!!! info "Collector Information"
    **Purpose:** Collector for organization-level metrics.
    **Source File:** `src/meraki_dashboard_exporter/collectors/organization.py`
    **Update Tier:** MEDIUM (300s)
    **Inherits From:** MetricCollector

#### 📊 Metrics Collected

| Metric Variable | Type | Name | Description |
|-----------------|------|------|-------------|
| `_org_info` | info | `OrgMetricName.ORG_INFO` | Organization information |
| `_api_requests_total` | gauge | `OrgMetricName.ORG_API_REQUESTS_TOTAL` | Total API requests made by the organization in the last hour |
| `_api_requests_by_status` | gauge | `OrgMetricName.ORG_API_REQUESTS_BY_STATUS` | API requests by HTTP status code in the last hour |
| `_networks_total` | gauge | `OrgMetricName.ORG_NETWORKS_TOTAL` | Total number of networks in the organization |
| `_devices_total` | gauge | `OrgMetricName.ORG_DEVICES_TOTAL` | Total number of devices in the organization |
| `_devices_by_model_total` | gauge | `OrgMetricName.ORG_DEVICES_BY_MODEL_TOTAL` | Total number of devices by specific model |
| `_devices_availability_total` | gauge | `OrgMetricName.ORG_DEVICES_AVAILABILITY_TOTAL` | Total number of devices by availability status and product type |
| `_licenses_total` | gauge | `OrgMetricName.ORG_LICENSES_TOTAL` | Total number of licenses |
| `_licenses_expiring` | gauge | `OrgMetricName.ORG_LICENSES_EXPIRING` | Number of licenses expiring within 30 days |
| `_clients_total` | gauge | `OrgMetricName.ORG_CLIENTS_TOTAL` | Total number of active clients in the organization (1-hour window) |
| `_usage_total_kb` | gauge | `OrgMetricName.ORG_USAGE_TOTAL_KB` | Total data usage in KB for the 1-hour window |
| `_usage_downstream_kb` | gauge | `OrgMetricName.ORG_USAGE_DOWNSTREAM_KB` | Downstream data usage in KB for the 1-hour window |
| `_usage_upstream_kb` | gauge | `OrgMetricName.ORG_USAGE_UPSTREAM_KB` | Upstream data usage in KB for the 1-hour window |
| `_packetcaptures_total` | gauge | `OrgMetricName.ORG_PACKETCAPTURES_TOTAL` | Total number of packet captures in the organization |
| `_packetcaptures_remaining` | gauge | `OrgMetricName.ORG_PACKETCAPTURES_REMAINING` | Number of remaining packet captures to process |
| `_application_usage_total_mb` | gauge | `OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_MB` | Total application usage in MB by category |
| `_application_usage_downstream_mb` | gauge | `OrgMetricName.ORG_APPLICATION_USAGE_DOWNSTREAM_MB` | Downstream application usage in MB by category |
| `_application_usage_upstream_mb` | gauge | `OrgMetricName.ORG_APPLICATION_USAGE_UPSTREAM_MB` | Upstream application usage in MB by category |
| `_application_usage_percentage` | gauge | `OrgMetricName.ORG_APPLICATION_USAGE_PERCENTAGE` | Application usage percentage by category |

#### 🔗 Sub-collectors

This coordinator manages the following sub-collectors:

- [`APIUsageCollector`](#apiusage) (as `self.api_usage_collector`)
- [`LicenseCollector`](#license) (as `self.license_collector`)
- [`ClientOverviewCollector`](#clientoverview) (as `self.client_overview_collector`)

??? example "Technical Details"

    **Decorators:**
    - `@register_collector(UpdateTier.MEDIUM)`

    **Defined at:** Line 30
    **Metrics Count:** 19

---

### RFHealthCollector { #rfhealth }

!!! info "Collector Information"
    **Purpose:** Collector for wireless RF health metrics including channel utilization.
    **Source File:** `src/meraki_dashboard_exporter/collectors/network_health_collectors/rf_health.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseNetworkHealthCollector

??? example "Technical Details"

    **Defined at:** Line 22

---

### SNMPFastCoordinator { #snmpfastcoordinator }

!!! info "Collector Information"
    **Purpose:** SNMP coordinator for fast-updating metrics (60s default).
    **Source File:** `src/meraki_dashboard_exporter/collectors/snmp/snmp_coordinator.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseSNMPCoordinator

??? example "Technical Details"

    **Decorators:**
    - `@register_collector`

    **Defined at:** Line 829

---

### SNMPMediumCoordinator { #snmpmediumcoordinator }

!!! info "Collector Information"
    **Purpose:** SNMP coordinator for medium-updating metrics (300s default).
    **Source File:** `src/meraki_dashboard_exporter/collectors/snmp/snmp_coordinator.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseSNMPCoordinator

??? example "Technical Details"

    **Decorators:**
    - `@register_collector`

    **Defined at:** Line 891

---

### SNMPSlowCoordinator { #snmpslowcoordinator }

!!! info "Collector Information"
    **Purpose:** SNMP coordinator for slow-updating metrics (900s default).
    **Source File:** `src/meraki_dashboard_exporter/collectors/snmp/snmp_coordinator.py`
    **Update Tier:** Not specified
    **Inherits From:** BaseSNMPCoordinator

??? example "Technical Details"

    **Decorators:**
    - `@register_collector`

    **Defined at:** Line 910

---

## 📚 Usage Guide

!!! tip "Understanding Collector Hierarchy"
    - **Main Collectors** are registered with `@register_collector()` and run automatically
    - **Coordinator Collectors** manage multiple sub-collectors for related metrics
    - **Device Collectors** are specific to device types (MR, MS, MX, etc.)
    - **Sub-collectors** are manually registered and called by their parent coordinators

!!! info "Update Tier Strategy"
    - **FAST (60s):** Critical metrics that change frequently (device status, alerts)
    - **MEDIUM (300s):** Regular metrics with moderate change frequency (performance data)
    - **SLOW (900s):** Stable metrics that change infrequently (configuration, licenses)

!!! example "Adding a New Collector"
    ```python
    from ..core.collector import register_collector, MetricCollector, UpdateTier
    from ..core.constants.metrics_constants import MetricName
    from ..core.error_handling import with_error_handling

    @register_collector(UpdateTier.MEDIUM)
    class MyCollector(MetricCollector):
        """My custom collector for specific metrics."""

        def _initialize_metrics(self) -> None:
            self.my_metric = self._create_gauge(
                MetricName.MY_METRIC,
                "Description of my metric"
            )

        @with_error_handling('Collect my data')
        async def _collect_impl(self) -> None:
            # Collection logic here
            pass
    ```

For more information on metrics, see the [Metrics Reference](metrics/metrics.md).

