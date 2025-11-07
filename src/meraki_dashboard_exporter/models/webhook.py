"""Domain models for Meraki webhook payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WebhookPayload(BaseModel):
    """Meraki webhook payload model.

    Parameters
    ----------
    version : str
        Webhook payload version (typically "1.0").
    shared_secret : str | None
        Shared secret for validation (if configured).
    sent_at : datetime
        Timestamp when the webhook was sent.
    organization_id : str
        Meraki organization ID.
    organization_name : str
        Meraki organization name.
    organization_url : str
        URL to the organization in Meraki Dashboard.
    network_id : str | None
        Network ID if the event is network-specific.
    network_name : str | None
        Network name if the event is network-specific.
    network_url : str | None
        URL to the network in Meraki Dashboard.
    device_serial : str | None
        Device serial number if the event is device-specific.
    device_mac : str | None
        Device MAC address if the event is device-specific.
    device_name : str | None
        Device name if the event is device-specific.
    device_url : str | None
        URL to the device in Meraki Dashboard.
    alert_id : str | None
        Alert ID for alert-type events.
    alert_type : str | None
        Type of alert (e.g., "settings_changed", "client_connectivity").
    alert_type_id : str | None
        Alert type identifier.
    alert_level : str | None
        Alert severity level (e.g., "warning", "critical").
    occurred_at : datetime | None
        Timestamp when the alert occurred.
    alert_data : dict[str, Any]
        Additional alert-specific data.

    """

    version: str = Field(..., description="Webhook payload version")
    shared_secret: str | None = Field(
        None,
        alias="sharedSecret",
        description="Shared secret for validation",
    )
    sent_at: datetime = Field(..., alias="sentAt", description="Webhook sent timestamp")

    # Organization info
    organization_id: str = Field(..., alias="organizationId", description="Organization ID")
    organization_name: str = Field(..., alias="organizationName", description="Organization name")
    organization_url: str = Field(..., alias="organizationUrl", description="Organization URL")

    # Network info (optional)
    network_id: str | None = Field(None, alias="networkId", description="Network ID")
    network_name: str | None = Field(None, alias="networkName", description="Network name")
    network_url: str | None = Field(None, alias="networkUrl", description="Network URL")

    # Device info (optional)
    device_serial: str | None = Field(None, alias="deviceSerial", description="Device serial")
    device_mac: str | None = Field(None, alias="deviceMac", description="Device MAC")
    device_name: str | None = Field(None, alias="deviceName", description="Device name")
    device_url: str | None = Field(None, alias="deviceUrl", description="Device URL")

    # Alert info (optional)
    alert_id: str | None = Field(None, alias="alertId", description="Alert ID")
    alert_type: str | None = Field(None, alias="alertType", description="Alert type")
    alert_type_id: str | None = Field(None, alias="alertTypeId", description="Alert type ID")
    alert_level: str | None = Field(None, alias="alertLevel", description="Alert severity level")
    occurred_at: datetime | None = Field(
        None, alias="occurredAt", description="Alert occurred timestamp"
    )

    # Alert-specific data
    alert_data: dict[str, Any] = Field(
        default_factory=dict,
        alias="alertData",
        description="Alert-specific data",
    )

    model_config = {"populate_by_name": True}
