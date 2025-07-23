"""Helper functions for consistent label creation across collectors."""

from __future__ import annotations

from typing import Any

from .metrics import create_labels


def create_device_labels(
    device: dict[str, Any],
    org_id: str | None = None,
    org_name: str | None = None,
    **extra_labels: str | None,
) -> dict[str, str]:
    """Create standard device labels from device data.

    Parameters
    ----------
    device : dict[str, Any]
        Device data from API.
    org_id : str | None
        Organization ID.
    org_name : str | None
        Organization name.
    **extra_labels : str | None
        Additional labels to include.

    Returns
    -------
    dict[str, str]
        Standard device labels.

    """
    serial = device.get("serial", "")
    name = device.get("name", serial)
    model = device.get("model", "")
    network_id = device.get("networkId", "")
    network_name = device.get("networkName", network_id)

    # Extract device type from model (first 2 characters)
    device_type = model[:2] if len(model) >= 2 else "Unknown"

    return create_labels(
        org_id=org_id,
        org_name=org_name,
        network_id=network_id,
        network_name=network_name,
        serial=serial,
        name=name,
        model=model,
        device_type=device_type,
        **extra_labels,
    )


def create_network_labels(
    network: dict[str, Any],
    org_id: str | None = None,
    org_name: str | None = None,
    **extra_labels: str | None,
) -> dict[str, str]:
    """Create standard network labels from network data.

    Parameters
    ----------
    network : dict[str, Any]
        Network data from API.
    org_id : str | None
        Organization ID.
    org_name : str | None
        Organization name.
    **extra_labels : str | None
        Additional labels to include.

    Returns
    -------
    dict[str, str]
        Standard network labels.

    """
    network_id = network.get("id", "")
    network_name = network.get("name", network_id)

    return create_labels(
        org_id=org_id,
        org_name=org_name,
        network_id=network_id,
        network_name=network_name,
        **extra_labels,
    )


def create_port_labels(
    device: dict[str, Any],
    port: dict[str, Any],
    org_id: str | None = None,
    org_name: str | None = None,
    **extra_labels: str | None,
) -> dict[str, str]:
    """Create standard port labels from device and port data.

    Parameters
    ----------
    device : dict[str, Any]
        Device data from API.
    port : dict[str, Any]
        Port data from API.
    org_id : str | None
        Organization ID.
    org_name : str | None
        Organization name.
    **extra_labels : str | None
        Additional labels to include.

    Returns
    -------
    dict[str, str]
        Standard port labels.

    """
    # Get device labels first
    device_labels = create_device_labels(device, org_id, org_name)

    # Add port-specific labels
    port_id = str(port.get("portId", ""))
    port_name = port.get("name", f"Port {port_id}")

    return create_labels(
        **device_labels,
        port_id=port_id,
        port_name=port_name,
        **extra_labels,
    )


def create_client_labels(
    client: dict[str, Any],
    org_id: str | None = None,
    org_name: str | None = None,
    network_id: str | None = None,
    network_name: str | None = None,
    **extra_labels: str | None,
) -> dict[str, str]:
    """Create standard client labels from client data.

    Parameters
    ----------
    client : dict[str, Any]
        Client data from API.
    org_id : str | None
        Organization ID.
    org_name : str | None
        Organization name.
    network_id : str | None
        Network ID (if not in client data).
    network_name : str | None
        Network name (if not in client data).
    **extra_labels : str | None
        Additional labels to include.

    Returns
    -------
    dict[str, str]
        Standard client labels.

    """
    # Client identification
    client_id = client.get("id", "")
    mac = client.get("mac", "")
    description = client.get("description", "")
    hostname = client.get("hostname", "")

    # Network info might be in client data
    if not network_id:
        network_id = client.get("networkId", "")
    if not network_name:
        network_name = client.get("networkName", network_id)

    return create_labels(
        org_id=org_id,
        org_name=org_name,
        network_id=network_id,
        network_name=network_name,
        client_id=client_id,
        mac=mac,
        description=description,
        hostname=hostname,
        **extra_labels,
    )


def create_org_labels(
    org: dict[str, Any],
    **extra_labels: str | None,
) -> dict[str, str]:
    """Create standard organization labels from org data.

    Parameters
    ----------
    org : dict[str, Any]
        Organization data from API.
    **extra_labels : str | None
        Additional labels to include.

    Returns
    -------
    dict[str, str]
        Standard organization labels.

    """
    org_id = org.get("id", "")
    org_name = org.get("name", org_id)

    return create_labels(
        org_id=org_id,
        org_name=org_name,
        **extra_labels,
    )
