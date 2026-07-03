"""Standardized metric creation and management.

This module provides factories and utilities for consistent metric creation
across all collectors, enforcing naming conventions and type safety.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class LabelName(StrEnum):
    """Standard label names used across all metrics."""

    # Organization labels
    ORG_ID = "org_id"
    ORG_NAME = "org_name"

    # Network labels
    NETWORK_ID = "network_id"
    NETWORK_NAME = "network_name"

    # Device labels
    SERIAL = "serial"
    NAME = "name"  # Device name
    MODEL = "model"
    DEVICE_TYPE = "device_type"

    # Port/Interface labels
    PORT_ID = "port_id"
    PORT_NAME = "port_name"

    # Status/State labels
    STATUS = "status"
    STATE = "state"
    STATUS_CODE = "status_code"  # HTTP status code

    # Direction labels
    DIRECTION = "direction"  # rx/tx, upstream/downstream

    # Metric type labels
    STAT = "stat"  # min/max/avg
    STAT_TYPE = "stat_type"

    # Alert/Error labels
    SEVERITY = "severity"
    ALERT_TYPE = "alert_type"
    CATEGORY = "category"
    CATEGORY_TYPE = "category_type"
    ERROR_TYPE = "error_type"
    WARNING_TYPE = "warning_type"

    # License labels
    LICENSE_TYPE = "license_type"

    # Interface labels
    INTERFACE = "interface"

    # Wireless specific
    SSID = "ssid"
    BAND = "band"
    RADIO = "radio"
    TYPE = "type"  # Generic type label
    FAILURE_STEP = "failure_step"  # Wireless connection failure step (assoc/auth/dhcp/dns)

    # Sensor specific
    METRIC = "metric"
    SENSOR_SERIAL = "sensor_serial"
    SENSOR_TYPE = "sensor_type"

    # Additional labels found in codebase
    MODE = "mode"  # Wireless mode
    DUPLEX = "duplex"  # Port duplex status
    STANDARD = "standard"  # Port standard
    RADIO_INDEX = "radio_index"  # Radio index for MR devices
    PRODUCT_TYPE = "product_type"  # Product type from device availability API
    UTILIZATION_TYPE = "utilization_type"  # Type of utilization (total/wifi/non_wifi)

    # Client specific labels
    CLIENT_ID = "client_id"
    MAC = "mac"
    DESCRIPTION = "description"
    HOSTNAME = "hostname"
    MANUFACTURER = "manufacturer"
    OS = "os"
    IP = "ip"
    VLAN = "vlan"
    FIRST_SEEN = "first_seen"
    LAST_SEEN = "last_seen"

    # Switch port specific
    MEDIA = "media"  # rj45, sfp
    LINK_SPEED = "link_speed"  # 10, 100, 1000, etc in Mbps

    # Collector infrastructure labels
    COLLECTOR = "collector"  # Collector name
    TIER = "tier"  # Collection tier (fast/medium/slow)
    GROUP = "group"  # Adaptive-scheduler endpoint group (#617); bounded, ~40 static values

    # API client labels (Phase 2.1)
    ENDPOINT = "endpoint"  # API endpoint name
    METHOD = "method"  # HTTP method (GET, POST, etc)
    RETRY_REASON = "retry_reason"  # Reason for retry (rate_limit, timeout, etc)

    # Webhook labels (Phase 4.2)
    VALIDATION_ERROR = "validation_error"  # Webhook validation error reason

    # VPN labels
    PEER_NETWORK_ID = "peer_network_id"
    PEER_TYPE = "peer_type"

    # Switch stack labels
    STACK_ID = "stack_id"
    ROLE = "role"

    # Firewall labels
    RULE_TYPE = "rule_type"
    EVENT_TYPE = "event_type"
    DEFAULT_POLICY = "default_policy"

    # MG cellular gateway labels
    PROVIDER = "provider"  # Cellular carrier/provider name
    ROAMING_STATUS = "roaming_status"  # home/roaming/unknown
    CONNECTION_TYPE = "connection_type"  # Radio access type (LTE/5G/etc)
    SIGNAL_TYPE = "signal_type"  # Cellular signal type
    APN = "apn"  # Access point name

    # MV camera labels
    ZONE_ID = "zone_id"  # Camera analytics zone ID
    ZONE_NAME = "zone_name"  # Camera analytics zone label/name
    QUALITY = "quality"  # Camera video quality (Standard/Enhanced/High)
    RESOLUTION = "resolution"  # Camera video resolution
    PROFILE_ID = "profile_id"  # Camera quality-and-retention profile ID

    # Power supply / power module labels
    SLOT = "slot"  # PSU/power-module slot number
    PSU_SERIAL = "psu_serial"  # Power supply's own serial (distinct from device serial)
    PSU_MODEL = "psu_model"  # Power supply's own model/SKU (distinct from parent device model)

    # Wireless latency labels
    TRAFFIC_CLASS = "traffic_class"  # background/best_effort/video/voice traffic class

    # Admin / security-posture labels
    AUTHENTICATION_METHOD = (
        "authentication_method"  # Admin auth method (Email/Cisco SecureX Sign-On)
    )
    ACCOUNT_STATUS = "account_status"  # Admin account status (ok/locked/pending/unverified)

    # Sensor-gateway connectivity labels
    GATEWAY_SERIAL = "gateway_serial"  # MT sensor's paired gateway serial

    # Exporter build-info labels
    VERSION = "version"  # Exporter build version (get_version())
    COMMIT = "commit"  # Git commit SHA the build was produced from (get_commit())

    # Phase 4 (#618)
    RULESET = "ruleset"
    SUBNET = "subnet"
    NAT_TYPE = "nat_type"
    RF_PROFILE_ID = "rf_profile_id"
    RF_PROFILE_NAME = "rf_profile_name"
    IS_DEFAULT = "is_default"
    IS_ALLOWED = "is_allowed"
    LAG_ID = "lag_id"
    FIRMWARE = "firmware"
    PRESS_TYPE = "press_type"
    CELL_ID = "cell_id"
    TAC = "tac"
    RELATED_SERIAL = "related_serial"
    THREAT_TYPE = "threat_type"


def create_labels(**kwargs: str | None) -> dict[str, str]:
    """Create a label dictionary with validation.

    This function ensures that all label keys are valid LabelName enum values.
    A ``None`` value is coalesced to an empty string (``""``) rather than
    dropped, so the label is always present in the returned set — dropping a
    key would later make ``Gauge.labels()`` raise ``ValueError`` for a missing
    labelname and silently lose the metric series (F-019).

    Parameters
    ----------
    **kwargs : str | None
        Label key-value pairs. Keys must match LabelName enum values.

    Returns
    -------
    dict[str, str]
        Validated label dictionary; ``None`` values become ``""``.

    Raises
    ------
    ValueError
        If any key is not a valid LabelName enum value.

    Examples
    --------
    >>> create_labels(org_id="123", org_name="Test Org", network_id=None)
    {"org_id": "123", "org_name": "Test Org", "network_id": ""}

    """
    valid_keys = {label.value for label in LabelName}
    result = {}

    for key, value in kwargs.items():
        if key not in valid_keys:
            raise ValueError(
                f"Invalid label key: '{key}'. Must be one of: {', '.join(sorted(valid_keys))}"
            )
        # Coalesce None to an empty string rather than dropping the key (F-019).
        # Dropping a None-valued label leaves a hole in the labelname set, which
        # later makes Gauge.labels() raise ValueError (missing labelname) — a
        # bare except then swallows it, silently losing the whole metric series.
        result[key] = "" if value is None else str(value)

    return result
