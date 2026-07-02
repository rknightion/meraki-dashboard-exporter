"""Tests for metric constant naming consistency."""

from __future__ import annotations

from enum import StrEnum

import pytest

from meraki_dashboard_exporter.core.constants.metrics_constants import (
    AlertMetricName,
    ClientMetricName,
    CollectorMetricName,
    DeviceMetricName,
    MGMetricName,
    MRMetricName,
    MSMetricName,
    MTMetricName,
    MVMetricName,
    MXMetricName,
    NetworkHealthMetricName,
    NetworkMetricName,
    OrgMetricName,
)


class TestMSMetricNaming:
    """Verify MS metric enum names match their string values."""

    @pytest.mark.parametrize(
        "enum_member,expected_unit",
        [
            ("MS_POE_PORT_ENERGY_JOULES", "joules"),
            ("MS_POE_TOTAL_ENERGY_JOULES", "joules"),
            ("MS_POE_NETWORK_TOTAL_ENERGY_JOULES", "joules"),
            ("MS_POE_BUDGET_WATTS", "watts"),
            ("MS_POWER_USAGE_WATTS", "watts"),
        ],
    )
    def test_poe_metric_unit_consistency(self, enum_member: str, expected_unit: str) -> None:
        """Verify POE/power metric enum names match their string value units."""
        member = MSMetricName[enum_member]
        assert expected_unit in member.value, (
            f"Enum {enum_member} value '{member.value}' does not contain expected unit '{expected_unit}'"
        )


class TestCollectorPerformanceMetricNames:
    """F-108: per-collector performance metric names are enum-backed and byte-identical.

    These 6 names were previously emitted as hardcoded string literals in
    core/collector.py and collectors/manager.py, violating the repo's
    no-hardcoded-metric-names rule. They must now exist on CollectorMetricName
    with exactly the same wire names.
    """

    @pytest.mark.parametrize(
        "enum_member,expected_value",
        [
            ("COLLECTOR_DURATION_SECONDS", "meraki_exporter_collector_duration_seconds"),
            ("COLLECTOR_ERRORS_TOTAL", "meraki_exporter_collector_errors_total"),
            (
                "COLLECTOR_SUCCESS_TIMESTAMP_SECONDS",
                "meraki_exporter_collector_success_timestamp_seconds",
            ),
            ("COLLECTOR_API_CALLS_TOTAL", "meraki_exporter_collector_api_calls_total"),
            ("COLLECTOR_FAILURE_STREAK", "meraki_exporter_collector_failure_streak"),
        ],
    )
    def test_enum_value_byte_identical(self, enum_member: str, expected_value: str) -> None:
        """Enum value must equal the previously-hardcoded metric name exactly."""
        assert CollectorMetricName[enum_member].value == expected_value

    def test_no_hardcoded_names_in_source(self) -> None:
        """The literal metric-name strings must no longer appear in the source files.

        They should be referenced via CollectorMetricName.<X>.value instead.
        """
        from pathlib import Path

        import meraki_dashboard_exporter as pkg

        root = Path(pkg.__file__).parent
        collector_src = (root / "core" / "collector.py").read_text()
        manager_src = (root / "collectors" / "manager.py").read_text()

        for literal in (
            '"meraki_exporter_collector_duration_seconds"',
            '"meraki_exporter_collector_errors_total"',
            '"meraki_exporter_collector_success_timestamp_seconds"',
            '"meraki_exporter_collector_api_calls_total"',
        ):
            assert literal not in collector_src, f"hardcoded {literal} still in collector.py"

        assert '"meraki_exporter_collector_failure_streak"' not in manager_src


# Issue #531 — the complete v1 rename table (spec §2a-2d). Each row is
# (enum class, OLD member identifier, NEW member identifier, NEW string value).
# This is the frozen seam contract: lanes update collector references against
# exactly these member names and wire strings.
V1_RENAME_TABLE: list[tuple[type[StrEnum], str, str, str]] = [
    # --- §2a MET-01: snapshot gauges drop `_total` ---
    (OrgMetricName, "ORG_NETWORKS_TOTAL", "ORG_NETWORKS", "meraki_org_networks"),
    (OrgMetricName, "ORG_DEVICES_TOTAL", "ORG_DEVICES", "meraki_org_devices"),
    (
        OrgMetricName,
        "ORG_DEVICES_BY_MODEL_TOTAL",
        "ORG_DEVICES_BY_MODEL",
        "meraki_org_devices_by_model",
    ),
    (
        OrgMetricName,
        "ORG_DEVICES_AVAILABILITY_TOTAL",
        "ORG_DEVICES_AVAILABILITY",
        "meraki_org_devices_availability",
    ),
    (OrgMetricName, "ORG_LICENSES_TOTAL", "ORG_LICENSES", "meraki_org_licenses"),
    (OrgMetricName, "ORG_PACKETCAPTURES_TOTAL", "ORG_PACKETCAPTURES", "meraki_org_packetcaptures"),
    (OrgMetricName, "ORG_ADMINS_TOTAL", "ORG_ADMINS", "meraki_org_admins"),
    (
        OrgMetricName,
        "ORG_ADMINS_TWO_FACTOR_ENABLED_TOTAL",
        "ORG_ADMINS_TWO_FACTOR_ENABLED",
        "meraki_org_admins_two_factor_enabled",
    ),
    (
        OrgMetricName,
        "ORG_FIRMWARE_UPGRADES_TOTAL",
        "ORG_FIRMWARE_UPGRADES",
        "meraki_org_firmware_upgrades",
    ),
    (
        OrgMetricName,
        "ORG_FIRMWARE_UPGRADES_PENDING_TOTAL",
        "ORG_FIRMWARE_UPGRADES_PENDING",
        "meraki_org_firmware_upgrades_pending",
    ),
    (MSMetricName, "MS_PORTS_ACTIVE_TOTAL", "MS_PORTS_ACTIVE", "meraki_ms_ports_active"),
    (MSMetricName, "MS_PORTS_INACTIVE_TOTAL", "MS_PORTS_INACTIVE", "meraki_ms_ports_inactive"),
    (MSMetricName, "MS_PORTS_BY_MEDIA_TOTAL", "MS_PORTS_BY_MEDIA", "meraki_ms_ports_by_media"),
    (
        MSMetricName,
        "MS_PORTS_BY_LINK_SPEED_TOTAL",
        "MS_PORTS_BY_LINK_SPEED",
        "meraki_ms_ports_by_link_speed",
    ),
    (MSMetricName, "MS_STACK_MEMBERS_TOTAL", "MS_STACK_MEMBERS", "meraki_ms_stack_members"),
    (MXMetricName, "MX_VPN_PEERS_TOTAL", "MX_VPN_PEERS", "meraki_mx_vpn_peers"),
    (MXMetricName, "MX_FIREWALL_RULES_TOTAL", "MX_FIREWALL_RULES", "meraki_mx_firewall_rules"),
    (
        AlertMetricName,
        "ALERTS_TOTAL_BY_SEVERITY",
        "ALERTS_BY_SEVERITY",
        "meraki_alerts_by_severity",
    ),
    (
        AlertMetricName,
        "ALERTS_TOTAL_BY_NETWORK",
        "ALERTS_BY_NETWORK",
        "meraki_alerts_by_network",
    ),
    (
        AlertMetricName,
        "NETWORK_HEALTH_ALERTS_TOTAL",
        "NETWORK_HEALTH_ALERTS",
        "meraki_network_health_alerts",
    ),
    (
        NetworkMetricName,
        "NETWORK_FILTER_TOTAL",
        "NETWORK_FILTER_NETWORKS",
        "meraki_network_filter_networks",
    ),
    # --- §2b MET-02/03: windowed gauges -> `_count` ---
    (
        OrgMetricName,
        "ORG_API_REQUESTS_TOTAL",
        "ORG_API_REQUESTS_COUNT",
        "meraki_org_api_requests_count",
    ),
    (OrgMetricName, "ORG_CLIENTS_TOTAL", "ORG_CLIENTS_COUNT", "meraki_org_clients_count"),
    (
        OrgMetricName,
        "ORG_CONFIGURATION_CHANGES_TOTAL",
        "ORG_CONFIGURATION_CHANGES_COUNT",
        "meraki_org_configuration_changes_count",
    ),
    (
        OrgMetricName,
        "ORG_DEVICES_AVAILABILITY_CHANGES_TOTAL",
        "ORG_DEVICES_AVAILABILITY_CHANGES_COUNT",
        "meraki_org_devices_availability_changes_count",
    ),
    (
        MSMetricName,
        "MS_PORT_PACKETS_TOTAL",
        "MS_PORT_PACKETS_COUNT",
        "meraki_ms_port_packets_count",
    ),
    (
        MSMetricName,
        "MS_PORT_PACKETS_BROADCAST",
        "MS_PORT_PACKETS_BROADCAST_COUNT",
        "meraki_ms_port_packets_broadcast_count",
    ),
    (
        MSMetricName,
        "MS_PORT_PACKETS_MULTICAST",
        "MS_PORT_PACKETS_MULTICAST_COUNT",
        "meraki_ms_port_packets_multicast_count",
    ),
    (
        MSMetricName,
        "MS_PORT_PACKETS_CRCERRORS",
        "MS_PORT_PACKETS_CRCERRORS_COUNT",
        "meraki_ms_port_packets_crcerrors_count",
    ),
    (
        MSMetricName,
        "MS_PORT_PACKETS_FRAGMENTS",
        "MS_PORT_PACKETS_FRAGMENTS_COUNT",
        "meraki_ms_port_packets_fragments_count",
    ),
    (
        MSMetricName,
        "MS_PORT_PACKETS_COLLISIONS",
        "MS_PORT_PACKETS_COLLISIONS_COUNT",
        "meraki_ms_port_packets_collisions_count",
    ),
    (
        MSMetricName,
        "MS_PORT_PACKETS_TOPOLOGYCHANGES",
        "MS_PORT_PACKETS_TOPOLOGYCHANGES_COUNT",
        "meraki_ms_port_packets_topologychanges_count",
    ),
    (
        MSMetricName,
        "MS_PORT_PACKETS_RATE_TOTAL",
        "MS_PORT_PACKETS_RATE",
        "meraki_ms_port_packets_rate",
    ),
    (
        MRMetricName,
        "MR_CONNECTION_STATS",
        "MR_CONNECTION_STATS_COUNT",
        "meraki_mr_connection_stats_count",
    ),
    (
        NetworkMetricName,
        "NETWORK_WIRELESS_CONNECTION_STATS",
        "NETWORK_WIRELESS_CONNECTION_STATS_COUNT",
        "meraki_network_wireless_connection_stats_count",
    ),
    (
        NetworkHealthMetricName,
        "MR_SSID_FAILED_CONNECTIONS_TOTAL",
        "MR_SSID_FAILED_CONNECTIONS_COUNT",
        "meraki_mr_ssid_failed_connections_count",
    ),
    (
        MRMetricName,
        "MR_PACKETS_DOWNSTREAM_TOTAL",
        "MR_PACKETS_DOWNSTREAM_COUNT",
        "meraki_mr_packets_downstream_count",
    ),
    (
        MRMetricName,
        "MR_PACKETS_DOWNSTREAM_LOST",
        "MR_PACKETS_DOWNSTREAM_LOST_COUNT",
        "meraki_mr_packets_downstream_lost_count",
    ),
    (
        MRMetricName,
        "MR_PACKETS_UPSTREAM_TOTAL",
        "MR_PACKETS_UPSTREAM_COUNT",
        "meraki_mr_packets_upstream_count",
    ),
    (
        MRMetricName,
        "MR_PACKETS_UPSTREAM_LOST",
        "MR_PACKETS_UPSTREAM_LOST_COUNT",
        "meraki_mr_packets_upstream_lost_count",
    ),
    (MRMetricName, "MR_PACKETS_TOTAL", "MR_PACKETS_COUNT", "meraki_mr_packets_count"),
    (
        MRMetricName,
        "MR_PACKETS_LOST_TOTAL",
        "MR_PACKETS_LOST_COUNT",
        "meraki_mr_packets_lost_count",
    ),
    (
        MRMetricName,
        "MR_NETWORK_PACKETS_DOWNSTREAM_TOTAL",
        "MR_NETWORK_PACKETS_DOWNSTREAM_COUNT",
        "meraki_mr_network_packets_downstream_count",
    ),
    (
        MRMetricName,
        "MR_NETWORK_PACKETS_DOWNSTREAM_LOST",
        "MR_NETWORK_PACKETS_DOWNSTREAM_LOST_COUNT",
        "meraki_mr_network_packets_downstream_lost_count",
    ),
    (
        MRMetricName,
        "MR_NETWORK_PACKETS_UPSTREAM_TOTAL",
        "MR_NETWORK_PACKETS_UPSTREAM_COUNT",
        "meraki_mr_network_packets_upstream_count",
    ),
    (
        MRMetricName,
        "MR_NETWORK_PACKETS_UPSTREAM_LOST",
        "MR_NETWORK_PACKETS_UPSTREAM_LOST_COUNT",
        "meraki_mr_network_packets_upstream_lost_count",
    ),
    (
        MRMetricName,
        "MR_NETWORK_PACKETS_TOTAL",
        "MR_NETWORK_PACKETS_COUNT",
        "meraki_mr_network_packets_count",
    ),
    (
        MRMetricName,
        "MR_NETWORK_PACKETS_LOST_TOTAL",
        "MR_NETWORK_PACKETS_LOST_COUNT",
        "meraki_mr_network_packets_lost_count",
    ),
    (
        NetworkHealthMetricName,
        "NETWORK_BLUETOOTH_CLIENTS_TOTAL",
        "NETWORK_BLUETOOTH_CLIENTS_COUNT",
        "meraki_network_bluetooth_clients_count",
    ),
    (AlertMetricName, "SENSOR_ALERTS_TOTAL", "SENSOR_ALERTS_COUNT", "meraki_sensor_alerts_count"),
    (
        NetworkHealthMetricName,
        "MR_AIR_MARSHAL_SSIDS_TOTAL",
        "MR_AIR_MARSHAL_SSIDS_COUNT",
        "meraki_mr_air_marshal_ssids_count",
    ),
    (
        NetworkHealthMetricName,
        "MR_AIR_MARSHAL_BSSIDS_TOTAL",
        "MR_AIR_MARSHAL_BSSIDS_COUNT",
        "meraki_mr_air_marshal_bssids_count",
    ),
    (
        NetworkHealthMetricName,
        "MR_AIR_MARSHAL_CONTAINED_BSSIDS_TOTAL",
        "MR_AIR_MARSHAL_CONTAINED_BSSIDS_COUNT",
        "meraki_mr_air_marshal_contained_bssids_count",
    ),
    (
        NetworkHealthMetricName,
        "MR_AIR_MARSHAL_WIRED_DETECTED_TOTAL",
        "MR_AIR_MARSHAL_WIRED_DETECTED_COUNT",
        "meraki_mr_air_marshal_wired_detected_count",
    ),
    # --- §2c MET-04 + APIDEV-03: unit renames (value conversion happens at emit sites) ---
    (OrgMetricName, "ORG_USAGE_TOTAL_KB", "ORG_USAGE_TOTAL_BYTES", "meraki_org_usage_total_bytes"),
    (
        OrgMetricName,
        "ORG_USAGE_DOWNSTREAM_KB",
        "ORG_USAGE_DOWNSTREAM_BYTES",
        "meraki_org_usage_downstream_bytes",
    ),
    (
        OrgMetricName,
        "ORG_USAGE_UPSTREAM_KB",
        "ORG_USAGE_UPSTREAM_BYTES",
        "meraki_org_usage_upstream_bytes",
    ),
    (
        OrgMetricName,
        "ORG_APPLICATION_USAGE_TOTAL_MB",
        "ORG_APPLICATION_USAGE_TOTAL_BYTES",
        "meraki_org_application_usage_total_bytes",
    ),
    (
        OrgMetricName,
        "ORG_APPLICATION_USAGE_DOWNSTREAM_MB",
        "ORG_APPLICATION_USAGE_DOWNSTREAM_BYTES",
        "meraki_org_application_usage_downstream_bytes",
    ),
    (
        OrgMetricName,
        "ORG_APPLICATION_USAGE_UPSTREAM_MB",
        "ORG_APPLICATION_USAGE_UPSTREAM_BYTES",
        "meraki_org_application_usage_upstream_bytes",
    ),
    (
        MRMetricName,
        "MR_SSID_USAGE_TOTAL_MB",
        "MR_SSID_USAGE_TOTAL_BYTES",
        "meraki_mr_ssid_usage_total_bytes",
    ),
    (
        MRMetricName,
        "MR_SSID_USAGE_DOWNSTREAM_MB",
        "MR_SSID_USAGE_DOWNSTREAM_BYTES",
        "meraki_mr_ssid_usage_downstream_bytes",
    ),
    (
        MRMetricName,
        "MR_SSID_USAGE_UPSTREAM_MB",
        "MR_SSID_USAGE_UPSTREAM_BYTES",
        "meraki_mr_ssid_usage_upstream_bytes",
    ),
    (
        MXMetricName,
        "MX_VPN_USAGE_SENT_KB",
        "MX_VPN_USAGE_SENT_BYTES",
        "meraki_mx_vpn_usage_sent_bytes",
    ),
    (
        MXMetricName,
        "MX_VPN_USAGE_RECV_KB",
        "MX_VPN_USAGE_RECV_BYTES",
        "meraki_mx_vpn_usage_recv_bytes",
    ),
    (
        ClientMetricName,
        "CLIENT_USAGE_SENT_KB",
        "CLIENT_USAGE_SENT_BYTES",
        "meraki_client_usage_sent_bytes",
    ),
    (
        ClientMetricName,
        "CLIENT_USAGE_RECV_KB",
        "CLIENT_USAGE_RECV_BYTES",
        "meraki_client_usage_recv_bytes",
    ),
    (
        ClientMetricName,
        "CLIENT_USAGE_TOTAL_KB",
        "CLIENT_USAGE_TOTAL_BYTES",
        "meraki_client_usage_total_bytes",
    ),
    (
        ClientMetricName,
        "CLIENT_APPLICATION_USAGE_SENT_KB",
        "CLIENT_APPLICATION_USAGE_SENT_BYTES",
        "meraki_client_application_usage_sent_bytes",
    ),
    (
        ClientMetricName,
        "CLIENT_APPLICATION_USAGE_RECV_KB",
        "CLIENT_APPLICATION_USAGE_RECV_BYTES",
        "meraki_client_application_usage_recv_bytes",
    ),
    (
        ClientMetricName,
        "CLIENT_APPLICATION_USAGE_TOTAL_KB",
        "CLIENT_APPLICATION_USAGE_TOTAL_BYTES",
        "meraki_client_application_usage_total_bytes",
    ),
    (
        NetworkHealthMetricName,
        "NETWORK_WIRELESS_DOWNLOAD_KBPS",
        "NETWORK_WIRELESS_DOWNLOAD_BYTES_PER_SECOND",
        "meraki_network_wireless_download_bytes_per_second",
    ),
    (
        NetworkHealthMetricName,
        "NETWORK_WIRELESS_UPLOAD_KBPS",
        "NETWORK_WIRELESS_UPLOAD_BYTES_PER_SECOND",
        "meraki_network_wireless_upload_bytes_per_second",
    ),
    (
        MXMetricName,
        "MX_UPLINK_LATENCY_MS",
        "MX_UPLINK_LATENCY_SECONDS",
        "meraki_mx_uplink_latency_seconds",
    ),
    (
        MXMetricName,
        "MX_VPN_STATS_AVG_LATENCY_MS",
        "MX_VPN_STATS_AVG_LATENCY_SECONDS",
        "meraki_mx_vpn_stats_avg_latency_seconds",
    ),
    (
        NetworkHealthMetricName,
        "MR_DEVICE_LATENCY_MS",
        "MR_DEVICE_LATENCY_SECONDS",
        "meraki_mr_device_latency_seconds",
    ),
    (
        NetworkHealthMetricName,
        "MR_NETWORK_CLIENT_LATENCY_MS",
        "MR_NETWORK_CLIENT_LATENCY_SECONDS",
        "meraki_mr_network_client_latency_seconds",
    ),
    (
        OrgMetricName,
        "ORG_LOGIN_SECURITY_IDLE_TIMEOUT_MINUTES",
        "ORG_LOGIN_SECURITY_IDLE_TIMEOUT_SECONDS",
        "meraki_org_login_security_idle_timeout_seconds",
    ),
    (
        OrgMetricName,
        "ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_DAYS",
        "ORG_LOGIN_SECURITY_PASSWORD_EXPIRATION_SECONDS",
        "meraki_org_login_security_password_expiration_seconds",
    ),
    (
        MSMetricName,
        "MS_POE_PORT_POWER_WATTHOURS",
        "MS_POE_PORT_ENERGY_JOULES",
        "meraki_ms_poe_port_energy_joules",
    ),
    (
        MSMetricName,
        "MS_POE_TOTAL_POWER_WATTHOURS",
        "MS_POE_TOTAL_ENERGY_JOULES",
        "meraki_ms_poe_total_energy_joules",
    ),
    (
        MSMetricName,
        "MS_POE_NETWORK_TOTAL_WATTHOURS",
        "MS_POE_NETWORK_TOTAL_ENERGY_JOULES",
        "meraki_ms_poe_network_total_energy_joules",
    ),
    (
        MSMetricName,
        "MS_PORT_TRAFFIC_BYTES",
        "MS_PORT_TRAFFIC_BYTES_PER_SECOND",
        "meraki_ms_port_traffic_bytes_per_second",
    ),
    # --- §2d MET-05: `_percentage` -> `_percent` ---
    (
        OrgMetricName,
        "ORG_APPLICATION_USAGE_PERCENTAGE",
        "ORG_APPLICATION_USAGE_PERCENT",
        "meraki_org_application_usage_percent",
    ),
    (
        MRMetricName,
        "MR_SSID_USAGE_PERCENTAGE",
        "MR_SSID_USAGE_PERCENT",
        "meraki_mr_ssid_usage_percent",
    ),
    (MTMetricName, "MT_BATTERY_PERCENTAGE", "MT_BATTERY_PERCENT", "meraki_mt_battery_percent"),
]

# Dead enums owned by #538 — #531 must NOT touch them (spec §3).
DEAD_ENUMS_UNTOUCHED: list[tuple[type[StrEnum], str, str]] = [
    (OrgMetricName, "ORG_LOGIN_SECURITY_ENABLED", "meraki_org_login_security_enabled"),
    (
        OrgMetricName,
        "ORG_LOGIN_SECURITY_IP_RESTRICTIONS_ENABLED",
        "meraki_org_login_security_ip_restrictions_enabled",
    ),
    (NetworkMetricName, "NETWORK_CLIENTS_TOTAL", "meraki_network_clients_total"),
    (NetworkMetricName, "NETWORK_TRAFFIC_BYTES", "meraki_network_traffic_bytes"),
    (NetworkMetricName, "NETWORK_DEVICE_STATUS", "meraki_network_device_status"),
    (
        AlertMetricName,
        "ORGANIZATION_HEALTH_ALERTS_TOTAL",
        "meraki_organization_health_alerts_total",
    ),
    (AlertMetricName, "HEALTH_ALERT_INFO", "meraki_health_alert_info"),
]

# All Meraki-network-data domain enums (excludes the exporter self-metric and
# webhook enums, whose true Counters legitimately carry `_total`).
DOMAIN_ENUMS: list[type[StrEnum]] = [
    OrgMetricName,
    NetworkMetricName,
    DeviceMetricName,
    MSMetricName,
    MRMetricName,
    MXMetricName,
    MGMetricName,
    MVMetricName,
    MTMetricName,
    AlertMetricName,
    NetworkHealthMetricName,
    ClientMetricName,
]

# Dead enums (deleted by #538) that still legitimately end in `_total` until then.
_TOTAL_SUFFIX_ALLOWLIST = {
    "meraki_network_clients_total",
    "meraki_organization_health_alerts_total",
}

# Suffixes banned by the v1 naming convention: non-base units, `_percentage`,
# and rate suffixes that misstate the value's unit (spec §1 D1-D5, D7).
_FORBIDDEN_SUFFIXES = (
    "_kb",
    "_mb",
    "_ms",
    "_kbps",
    "_percentage",
    "_watthours",
    "_minutes",
    "_days",
)


class TestV1MetricRenames:
    """Issue #531: the coordinated v1 metric naming & unit sweep (spec §2a-2d)."""

    @pytest.mark.parametrize(
        "enum_cls,old_member,new_member,new_value",
        V1_RENAME_TABLE,
        ids=[f"{cls.__name__}.{new}" for cls, _, new, _ in V1_RENAME_TABLE],
    )
    def test_new_member_has_expected_value(
        self,
        enum_cls: type[StrEnum],
        old_member: str,
        new_member: str,
        new_value: str,
    ) -> None:
        """Every renamed member exists under its new identifier with the new wire name."""
        assert new_member in enum_cls.__members__, (
            f"{enum_cls.__name__}.{new_member} is missing (rename of {old_member} not applied)"
        )
        assert enum_cls[new_member].value == new_value

    @pytest.mark.parametrize(
        "enum_cls,old_member,new_member,new_value",
        V1_RENAME_TABLE,
        ids=[f"{cls.__name__}.{old}" for cls, old, _, _ in V1_RENAME_TABLE],
    )
    def test_old_member_removed(
        self,
        enum_cls: type[StrEnum],
        old_member: str,
        new_member: str,
        new_value: str,
    ) -> None:
        """The old identifier must be gone so stale references fail loudly at import."""
        assert old_member not in enum_cls.__members__, (
            f"{enum_cls.__name__}.{old_member} still exists; it must be renamed to {new_member}"
        )

    @pytest.mark.parametrize(
        "enum_cls,member,value",
        DEAD_ENUMS_UNTOUCHED,
        ids=[f"{cls.__name__}.{member}" for cls, member, _ in DEAD_ENUMS_UNTOUCHED],
    )
    def test_dead_enums_left_for_538(
        self, enum_cls: type[StrEnum], member: str, value: str
    ) -> None:
        """Dead enums belong to #538 — #531 must leave them byte-identical."""
        assert enum_cls[member].value == value

    def test_no_domain_gauge_ends_in_total(self) -> None:
        """`_total` is reserved for monotonic Counters (D1/D2); domain gauges must not use it."""
        offenders = [
            f"{cls.__name__}.{m.name}={m.value}"
            for cls in DOMAIN_ENUMS
            for m in cls
            if m.value.endswith("_total") and m.value not in _TOTAL_SUFFIX_ALLOWLIST
        ]
        assert not offenders, f"gauges still using the `_total` suffix: {offenders}"

    def test_no_forbidden_unit_suffixes(self) -> None:
        """No domain metric may end in a non-base-unit or misspelled suffix (D3-D5, D7)."""
        offenders = [
            f"{cls.__name__}.{m.name}={m.value}"
            for cls in DOMAIN_ENUMS
            for m in cls
            if m.value.endswith(_FORBIDDEN_SUFFIXES)
        ]
        assert not offenders, f"metrics with forbidden unit suffixes: {offenders}"


class TestMet06ExporterSelfMetricRenames:
    """Issue #532 (MET-06): fix three exporter self-metric type/name mismatches.

    Pre-1.0 rename, no dual-emit — the old wire names must be gone entirely from
    source (not just superseded by a new enum member).

    1. `meraki_exporter_cardinality_analyzed_total` (core/cardinality.py) was a
       Gauge (per-cycle snapshot) wrongly suffixed `_total`.
    2. `meraki_exporter_collection_errors_total_expired` (core/metric_expiration.py)
       was a Counter with `_total` stuck mid-name instead of at the end.
    3. `meraki_exporter_cache_size_tracked_metrics` (core/metric_expiration.py) was
       named after the unrelated `INVENTORY_CACHE_SIZE` enum member it was
       string-concatenated from, and does not measure cache size at all — it
       measures the count of metric series tracked for expiration.
    """

    def test_cardinality_analyzed_metrics_is_enum_backed_gauge_without_total(self) -> None:
        """Gauge value must be enum-backed and must not carry a `_total` suffix."""
        assert (
            CollectorMetricName.CARDINALITY_ANALYZED_METRICS.value
            == "meraki_exporter_cardinality_analyzed_metrics"
        )
        assert not CollectorMetricName.CARDINALITY_ANALYZED_METRICS.value.endswith("_total")

    def test_expired_metrics_counter_ends_in_total(self) -> None:
        """Counter value must be enum-backed and must end (not have mid-name) `_total`."""
        assert (
            CollectorMetricName.EXPIRED_METRICS_TOTAL.value
            == "meraki_exporter_collection_errors_expired_total"
        )
        assert CollectorMetricName.EXPIRED_METRICS_TOTAL.value.endswith("_total")

    def test_expiration_tracked_metrics_name_describes_what_it_measures(self) -> None:
        """Gauge value must describe tracked-metric count, not the unrelated cache size."""
        assert (
            CollectorMetricName.EXPIRATION_TRACKED_METRICS.value
            == "meraki_exporter_expiration_tracked_metrics"
        )

    def test_old_names_gone_from_source(self) -> None:
        """The old, mismatched wire names must not survive anywhere in `src/`."""
        from pathlib import Path

        import meraki_dashboard_exporter as pkg

        root = Path(pkg.__file__).parent
        cardinality_src = (root / "core" / "cardinality.py").read_text()
        expiration_src = (root / "core" / "metric_expiration.py").read_text()

        assert "meraki_exporter_cardinality_analyzed_total" not in cardinality_src
        assert "meraki_exporter_collection_errors_total_expired" not in expiration_src
        assert "meraki_exporter_cache_size_tracked_metrics" not in expiration_src
        # No more deriving these names by string-concatenating unrelated enum members.
        assert 'CollectorMetricName.COLLECTION_ERRORS_TOTAL.value + "_expired"' not in (
            expiration_src
        )
        assert 'CollectorMetricName.INVENTORY_CACHE_SIZE.value + "_tracked_metrics"' not in (
            expiration_src
        )
