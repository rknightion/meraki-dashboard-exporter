"""Standardized metric creation and management.

This module provides factories and utilities for consistent metric creation
across all collectors, enforcing naming conventions and type safety.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

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

    # License labels
    LICENSE_TYPE = "license_type"

    # Wireless specific
    SSID = "ssid"
    BAND = "band"
    RADIO = "radio"
    TYPE = "type"  # Generic type label

    # Sensor specific
    METRIC = "metric"
    SENSOR_SERIAL = "sensor_serial"
    SENSOR_NAME = "sensor_name"
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
    RECENT_DEVICE_NAME = "recent_device_name"
    IP = "ip"
    VLAN = "vlan"
    FIRST_SEEN = "first_seen"
    LAST_SEEN = "last_seen"

    # Switch port specific
    MEDIA = "media"  # rj45, sfp
    LINK_SPEED = "link_speed"  # 10, 100, 1000, etc in Mbps


MetricType = Literal["gauge", "counter", "histogram", "info"]


@dataclass
class MetricDefinition:
    """Definition for a Prometheus metric."""

    name: str
    description: str
    metric_type: MetricType
    labels: list[str]
    unit: str | None = None

    @property
    def full_name(self) -> str:
        """Get the full metric name with unit suffix if applicable."""
        if self.unit and not self.name.endswith(f"_{self.unit}"):
            return f"{self.name}_{self.unit}"
        return self.name

    def validate_labels(self, provided_labels: list[str]) -> None:
        """Validate that provided labels match the definition."""
        expected_set = set(self.labels)
        provided_set = set(provided_labels)

        if expected_set != provided_set:
            missing = expected_set - provided_set
            extra = provided_set - expected_set
            msg = f"Label mismatch for metric {self.name}."
            if missing:
                msg += f" Missing: {missing}."
            if extra:
                msg += f" Extra: {extra}."
            raise ValueError(msg)


class MetricFactory:
    """Factory for creating standardized metrics with consistent labeling."""

    @staticmethod
    def organization_metric(
        name: str,
        description: str,
        metric_type: MetricType = "gauge",
        extra_labels: list[str] | None = None,
        unit: str | None = None,
    ) -> MetricDefinition:
        """Create a metric definition for organization-level metrics.

        Includes: org_id, org_name
        """
        labels = LabelSet.get_labels_list(LabelSet.ORG_METRIC, extra_labels)
        return MetricDefinition(
            name=name,
            description=description,
            metric_type=metric_type,
            labels=labels,
            unit=unit,
        )

    @staticmethod
    def network_metric(
        name: str,
        description: str,
        metric_type: MetricType = "gauge",
        extra_labels: list[str] | None = None,
        unit: str | None = None,
    ) -> MetricDefinition:
        """Create a metric definition for network-level metrics.

        Includes: org_id, org_name, network_id, network_name
        """
        labels = LabelSet.get_labels_list(LabelSet.NETWORK_METRIC, extra_labels)
        return MetricDefinition(
            name=name,
            description=description,
            metric_type=metric_type,
            labels=labels,
            unit=unit,
        )

    @staticmethod
    def device_metric(
        name: str,
        description: str,
        metric_type: MetricType = "gauge",
        include_device_type: bool = True,
        extra_labels: list[str] | None = None,
        unit: str | None = None,
    ) -> MetricDefinition:
        """Create a metric definition for device-level metrics.

        Includes: org_id, org_name, network_id, network_name, serial, name, model
        Optional: device_type
        """
        labels = LabelSet.get_labels_list(LabelSet.DEVICE_METRIC, extra_labels)
        if include_device_type:
            labels.append(LabelName.DEVICE_TYPE.value)
        return MetricDefinition(
            name=name,
            description=description,
            metric_type=metric_type,
            labels=sorted(set(labels)),  # Ensure unique and sorted
            unit=unit,
        )

    @staticmethod
    def port_metric(
        name: str,
        description: str,
        metric_type: MetricType = "gauge",
        extra_labels: list[str] | None = None,
        unit: str | None = None,
    ) -> MetricDefinition:
        """Create a metric definition for port-level metrics.

        Includes: org_id, org_name, network_id, network_name, serial, name, model, port_id, port_name
        """
        labels = LabelSet.get_labels_list(LabelSet.PORT_METRIC, extra_labels)
        return MetricDefinition(
            name=name,
            description=description,
            metric_type=metric_type,
            labels=labels,
            unit=unit,
        )

    @staticmethod
    def client_metric(
        name: str,
        description: str,
        metric_type: MetricType = "gauge",
        extra_labels: list[str] | None = None,
        unit: str | None = None,
    ) -> MetricDefinition:
        """Create a metric definition for client-level metrics.

        Includes: org_id, org_name, network_id, network_name, client_id, mac, description, hostname
        """
        labels = LabelSet.get_labels_list(LabelSet.CLIENT_METRIC, extra_labels)
        return MetricDefinition(
            name=name,
            description=description,
            metric_type=metric_type,
            labels=labels,
            unit=unit,
        )


def validate_metric_name(name: str) -> None:
    """Validate that a metric name follows Prometheus best practices.

    Parameters
    ----------
    name : str
        The metric name to validate.

    Raises
    ------
    ValueError
        If the metric name doesn't follow conventions.

    """
    if not name.startswith("meraki_"):
        raise ValueError(f"Metric name '{name}' should start with 'meraki_'")

    # Check for unit suffixes if applicable
    unit_suffixes = [
        "_total",
        "_bytes",
        "_seconds",
        "_percent",
        "_celsius",
        "_watts",
        "_kbps",
        "_mbps",
        "_count",
        "_info",
    ]

    # Some metrics don't need units (like status, up/down)
    unit_exempt = ["_up", "_status", "_enabled", "_info"]

    has_unit = any(name.endswith(suffix) for suffix in unit_suffixes)
    is_exempt = any(name.endswith(suffix) for suffix in unit_exempt)

    if not has_unit and not is_exempt:
        # Warning only - some metrics legitimately don't have units
        import logging

        logging.getLogger(__name__).warning(
            "Metric '%s' may be missing a unit suffix (e.g., _total, _bytes, _seconds)", name
        )


def create_info_labels(data: dict[str, str | int | float | bool]) -> dict[str, str]:
    """Create labels dictionary for info metrics.

    Parameters
    ----------
    data : dict[str, str | int | float | bool]
        Data to convert to info labels.

    Returns
    -------
    dict[str, str]
        Labels with all values converted to strings.

    """
    return {k: str(v) for k, v in data.items()}


def create_labels(**kwargs: str | None) -> dict[str, str]:
    """Create a label dictionary with validation.

    This function ensures that all label keys are valid LabelName enum values
    and filters out None values.

    Parameters
    ----------
    **kwargs : str | None
        Label key-value pairs. Keys must match LabelName enum values.

    Returns
    -------
    dict[str, str]
        Validated label dictionary with None values filtered out.

    Raises
    ------
    ValueError
        If any key is not a valid LabelName enum value.

    Examples
    --------
    >>> create_labels(org_id="123", org_name="Test Org", network_id=None)
    {"org_id": "123", "org_name": "Test Org"}

    """
    valid_keys = {label.value for label in LabelName}
    result = {}

    for key, value in kwargs.items():
        if key not in valid_keys:
            raise ValueError(
                f"Invalid label key: '{key}'. Must be one of: {', '.join(sorted(valid_keys))}"
            )
        if value is not None:
            result[key] = str(value)

    return result


class LabelSet:
    """Predefined sets of labels for consistent metric labeling."""

    # Base label sets
    ORG = {LabelName.ORG_ID.value, LabelName.ORG_NAME.value}
    NETWORK = {LabelName.NETWORK_ID.value, LabelName.NETWORK_NAME.value}
    DEVICE = {LabelName.SERIAL.value, LabelName.NAME.value, LabelName.MODEL.value}
    PORT = {LabelName.PORT_ID.value, LabelName.PORT_NAME.value}
    CLIENT = {
        LabelName.CLIENT_ID.value,
        LabelName.MAC.value,
        LabelName.DESCRIPTION.value,
        LabelName.HOSTNAME.value,
    }

    # Combined label sets for different metric types
    ORG_METRIC = ORG
    NETWORK_METRIC = ORG | NETWORK
    DEVICE_METRIC = ORG | NETWORK | DEVICE
    PORT_METRIC = ORG | NETWORK | DEVICE | PORT
    CLIENT_METRIC = ORG | NETWORK | CLIENT

    @classmethod
    def get_labels_list(
        cls, label_set: set[str], extra_labels: list[str] | None = None
    ) -> list[str]:
        """Convert a label set to a sorted list with optional extra labels.

        Parameters
        ----------
        label_set : set[str]
            Base set of labels.
        extra_labels : list[str] | None
            Additional labels to include.

        Returns
        -------
        list[str]
            Sorted list of all labels.

        """
        labels = list(label_set)
        if extra_labels:
            labels.extend(extra_labels)
        return sorted(set(labels))  # Sort for consistent ordering
