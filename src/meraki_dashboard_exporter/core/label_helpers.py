"""Helper functions for consistent label creation across collectors.

Numeric series carry **stable IDs only** (issue #534, Option B). The mutable
display-name labels (``org_name``/``network_name``/``name``/``port_name``) are
NOT emitted onto numeric series here; they live on id-keyed ``*_info`` join
metrics whose emission sites build their own label dicts. Consumers re-attach a
name via ``<numeric> * on(<id>) group_left(<name>) <..._info>``.

The name-carrying parameters (``org_name``, ``network_name``) are retained on
these signatures because callers still pass them for ``LogContext``/logging;
they are simply no longer written into the returned label dict.
"""

from __future__ import annotations

from typing import Any

from .metrics import create_labels


def create_device_labels(
    device: dict[str, Any],
    org_id: str | None = None,
    org_name: str | None = None,
    **extra_labels: str | None,
) -> dict[str, str]:
    """Create standard device labels (ID-only) from device data.

    The device display ``name`` and the ``org_name``/``network_name`` labels are
    deliberately omitted (issue #534); ``model``/``device_type`` are immutable
    per serial and are retained. The device name joins via
    ``meraki_device_status_info`` on ``serial``.

    Parameters
    ----------
    device : dict[str, Any]
        Device data from API.
    org_id : str | None
        Organization ID.
    org_name : str | None
        Organization name. Retained for logging compatibility; NOT emitted.
    **extra_labels : str | None
        Additional labels to include.

    Returns
    -------
    dict[str, str]
        Standard device labels: ``org_id``, ``network_id``, ``serial``,
        ``model``, ``device_type`` (+ any extras).

    """
    serial = device.get("serial", "")
    model = device.get("model", "")
    network_id = device.get("networkId", "")

    # Extract device type from model (first 2 characters)
    device_type = model[:2] if len(model) >= 2 else "Unknown"

    return create_labels(
        org_id=org_id,
        network_id=network_id,
        serial=serial,
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
    """Create standard network labels (ID-only) from network data.

    The ``network_name`` and ``org_name`` labels are deliberately omitted (issue
    #534); ``network_name`` joins via ``meraki_network_info`` on ``network_id``.

    Parameters
    ----------
    network : dict[str, Any]
        Network data from API.
    org_id : str | None
        Organization ID.
    org_name : str | None
        Organization name. Retained for logging compatibility; NOT emitted.
    **extra_labels : str | None
        Additional labels to include.

    Returns
    -------
    dict[str, str]
        Standard network labels: ``org_id``, ``network_id`` (+ any extras).

    """
    network_id = network.get("id", "")

    return create_labels(
        org_id=org_id,
        network_id=network_id,
        **extra_labels,
    )


def create_port_labels(
    device: dict[str, Any],
    port: dict[str, Any],
    org_id: str | None = None,
    org_name: str | None = None,
    **extra_labels: str | None,
) -> dict[str, str]:
    """Create standard port labels (ID-only) from device and port data.

    The ``port_name`` label is deliberately omitted (issue #534); for MS ports
    it joins via ``meraki_ms_port_info`` on ``serial``+``port_id``.

    Parameters
    ----------
    device : dict[str, Any]
        Device data from API.
    port : dict[str, Any]
        Port data from API.
    org_id : str | None
        Organization ID.
    org_name : str | None
        Organization name. Retained for logging compatibility; NOT emitted.
    **extra_labels : str | None
        Additional labels to include.

    Returns
    -------
    dict[str, str]
        Device labels + ``port_id`` (+ any extras). No ``port_name``.

    """
    # Get device labels first (already ID-only)
    device_labels = create_device_labels(device, org_id, org_name)

    # Add port-specific ID label
    port_id = str(port.get("portId", ""))

    return create_labels(
        **device_labels,
        port_id=port_id,
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
    """Create standard client labels (ID-only) from client data.

    Numeric client series are ID-only (issue #533): ``mac``/``description``/
    ``hostname``/``ssid`` are deliberately omitted here, alongside the already-
    dropped ``org_name``/``network_name`` (issue #534). Those descriptive/
    mutable fields live exclusively on the ``meraki_client_info`` join metric
    (``collectors/clients.py``), keyed on ``client_id``; consumers re-attach
    them via ``<numeric> * on(client_id) group_left(mac, description, hostname,
    ssid) meraki_client_info``.

    Parameters
    ----------
    client : dict[str, Any]
        Client data from API.
    org_id : str | None
        Organization ID.
    org_name : str | None
        Organization name. Retained for logging compatibility; NOT emitted.
    network_id : str | None
        Network ID (if not in client data).
    network_name : str | None
        Network name. Retained for logging compatibility; NOT emitted.
    **extra_labels : str | None
        Additional labels to include (e.g. ``type`` for application usage).

    Returns
    -------
    dict[str, str]
        Standard client labels: ``org_id``, ``network_id``, ``client_id``
        (+ any extras). No ``mac``/``description``/``hostname``/``ssid``.

    """
    # Client identification
    client_id = client.get("id", "")

    # Network id might be in client data
    if not network_id:
        network_id = client.get("networkId", "")

    return create_labels(
        org_id=org_id,
        network_id=network_id,
        client_id=client_id,
        **extra_labels,
    )


def create_org_labels(
    org: dict[str, Any],
    **extra_labels: str | None,
) -> dict[str, str]:
    """Create standard organization labels (ID-only) from org data.

    The ``org_name`` label is deliberately omitted (issue #534); it joins via
    ``meraki_org_info`` on ``org_id``.

    Parameters
    ----------
    org : dict[str, Any]
        Organization data from API.
    **extra_labels : str | None
        Additional labels to include.

    Returns
    -------
    dict[str, str]
        Standard organization labels: ``org_id`` (+ any extras).

    """
    org_id = org.get("id", "")

    return create_labels(
        org_id=org_id,
        **extra_labels,
    )
