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
    """Factory for creating standardized metrics."""
    
    # Common label sets for reuse
    ORG_LABELS = [LabelName.ORG_ID, LabelName.ORG_NAME]
    NETWORK_LABELS = [LabelName.NETWORK_ID, LabelName.NETWORK_NAME]
    DEVICE_LABELS = [LabelName.SERIAL, LabelName.NAME, LabelName.MODEL, LabelName.NETWORK_ID]
    DEVICE_TYPE_LABELS = DEVICE_LABELS + [LabelName.DEVICE_TYPE]
    PORT_LABELS = [LabelName.SERIAL, LabelName.NAME, LabelName.PORT_ID, LabelName.PORT_NAME]
    
    @staticmethod
    def organization_metric(
        name: str,
        description: str,
        metric_type: MetricType = "gauge",
        extra_labels: list[str] | None = None,
        unit: str | None = None,
    ) -> MetricDefinition:
        """Create a metric definition for organization-level metrics."""
        labels = list(MetricFactory.ORG_LABELS)
        if extra_labels:
            labels.extend(extra_labels)
        
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
        """Create a metric definition for network-level metrics."""
        labels = list(MetricFactory.NETWORK_LABELS)
        if extra_labels:
            labels.extend(extra_labels)
        
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
        """Create a metric definition for device-level metrics."""
        labels = list(
            MetricFactory.DEVICE_TYPE_LABELS if include_device_type
            else MetricFactory.DEVICE_LABELS
        )
        if extra_labels:
            labels.extend(extra_labels)
        
        return MetricDefinition(
            name=name,
            description=description,
            metric_type=metric_type,
            labels=labels,
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
        """Create a metric definition for port-level metrics."""
        labels = list(MetricFactory.PORT_LABELS)
        if extra_labels:
            labels.extend(extra_labels)
        
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
        "_total", "_bytes", "_seconds", "_percent", "_celsius",
        "_watts", "_kbps", "_mbps", "_count", "_info"
    ]
    
    # Some metrics don't need units (like status, up/down)
    unit_exempt = ["_up", "_status", "_enabled", "_info"]
    
    has_unit = any(name.endswith(suffix) for suffix in unit_suffixes)
    is_exempt = any(name.endswith(suffix) for suffix in unit_exempt)
    
    if not has_unit and not is_exempt:
        # Warning only - some metrics legitimately don't have units
        import logging
        logging.getLogger(__name__).warning(
            "Metric '%s' may be missing a unit suffix (e.g., _total, _bytes, _seconds)",
            name
        )
