"""Deterministic, bounded fleet fixtures for scale and CI tests (#707).

The fixtures deliberately separate a topology from an API capture.  Only MR,
MS, and MT exist in the maintainer's homelab; MX, MG, and MV payloads are
synthetic stand-ins and are surfaced as ``SHAPE-ASSUMED`` by every caller.
Nothing in this module contacts the Meraki API.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from resource import RUSAGE_SELF, getrusage
from typing import Final, cast

from prometheus_client import CollectorRegistry, generate_latest


class FleetPreset(StrEnum):
    """Named, stable topologies used by the Issue #707 CI tiers."""

    HOMELAB = "HOMELAB"
    BRANCH_RETAIL = "BRANCH-RETAIL"
    CAMPUS = "CAMPUS"
    DENSE_SWITCH = "DENSE-SWITCH"
    XL_MULTI_SITE = "XL-MULTI-SITE"
    MULTI_ORG_SHARD = "MULTI-ORG-SHARD"
    CAMERA_HEAVY = "CAMERA-HEAVY"


class FleetCITier(StrEnum):
    """CI selection classes; workflow wiring maps these to pytest markers."""

    PR = "pr"
    SCHEDULED = "scheduled"
    ON_DEMAND = "on-demand"


_FAMILY_MODELS: Final[dict[str, str]] = {
    "MR": "MR56",
    "MS": "MS250-48",
    "MT": "MT14",
    "MX": "MX95",
    "MG": "MG41",
    "MV": "MV72",
}
_PRODUCT_TYPES: Final[dict[str, str]] = {
    "MR": "wireless",
    "MS": "switch",
    "MT": "sensor",
    "MX": "appliance",
    "MG": "cellularGateway",
    "MV": "camera",
}
_VENDOR_CAPS: Final[dict[str, int]] = {
    "MX": 2,
    "MG": 4,
    "MV": 1000,
    "MT": 1700,
    "MR": 5000,
    "MS": 5000,
}
_SHAPE_ASSUMED_FAMILIES: Final[frozenset[str]] = frozenset({"MX", "MG", "MV"})


@dataclass(frozen=True)
class HomelabBaseline:
    """Measured target metadata, retained without claiming synthetic reruns measured it."""

    non_comment_lines: int = 4677
    samples: int = 4627
    payload_bytes: int = 738423
    scrape_render_seconds: float = 0.223904
    solved_rps: float = 0.5341667
    meraki_ms_samples: int = 2225
    demand_formula: tuple[int, int] = (1141, 1176)


@dataclass(frozen=True)
class FleetParameters:
    """Topology controls shared by every named preset.

    ``devices_per_network`` is intentionally family-keyed rather than a
    homogeneous device total: it makes the Meraki per-family limits executable
    assertions instead of prose beside a made-up fleet.
    """

    networks_per_org: int
    devices_per_network: dict[str, int]
    ports_per_switch: int
    ssids_per_network: int
    clients_per_network: int
    organizations: int = 1
    exporter_instances: int = 1
    application_rows_per_client: int = 1
    final_network_application_rows: int | None = None
    models: dict[str, tuple[str, ...]] | None = None
    switch_port_counts: tuple[int, ...] | None = None

    def validate(self) -> None:
        """Reject a preset that violates a published Meraki estate limit."""
        if self.networks_per_org < 1 or self.organizations < 1:
            raise ValueError("A fleet must have at least one organization and network")
        if self.exporter_instances < 1:
            raise ValueError("exporter_instances must be positive")
        if self.ports_per_switch < 0 or self.ssids_per_network < 0 or self.clients_per_network < 0:
            raise ValueError("ports, SSIDs, and clients cannot be negative")
        if self.application_rows_per_client < 0:
            raise ValueError("application rows per client cannot be negative")

        unknown_families = set(self.devices_per_network) - set(_VENDOR_CAPS)
        if unknown_families:
            raise ValueError(f"Unknown Meraki device families: {sorted(unknown_families)}")
        if any(count < 0 for count in self.devices_per_network.values()):
            raise ValueError("per-family device counts cannot be negative")

        per_network = sum(self.devices_per_network.values())
        if per_network > 5000:
            raise ValueError("Meraki permits at most 5,000 devices per network")
        for family, count in self.devices_per_network.items():
            if count > _VENDOR_CAPS[family]:
                raise ValueError(
                    f"Meraki permits at most {_VENDOR_CAPS[family]} {family} devices/network"
                )

        devices_per_org = per_network * self.networks_per_org
        if devices_per_org > 50000:
            raise ValueError("Meraki permits at most 50,000 devices per organization")
        if self.switch_port_counts is not None and len(
            self.switch_port_counts
        ) != self.devices_per_network.get("MS", 0):
            raise ValueError("switch_port_counts must provide one count per switch")


@dataclass(frozen=True)
class FleetFixture:
    """Generated SDK-shaped responses plus provenance and topology statistics."""

    preset: FleetPreset
    parameters: FleetParameters
    organizations: list[dict[str, object]]
    networks_by_org: dict[str, list[dict[str, object]]]
    devices_by_org: dict[str, list[dict[str, object]]]
    switch_ports_by_serial: dict[str, list[dict[str, object]]]
    ssids_by_network: dict[str, list[dict[str, object]]]
    clients_by_network: dict[str, list[dict[str, object]]]
    application_usage_by_network: dict[str, list[dict[str, object]]]
    assumed_families: frozenset[str]
    baseline: HomelabBaseline | None = None

    @property
    def network_count(self) -> int:
        """Number of generated networks across all organizations."""
        return sum(len(networks) for networks in self.networks_by_org.values())

    @property
    def device_count(self) -> int:
        """Number of generated devices across all organizations."""
        return sum(len(devices) for devices in self.devices_by_org.values())

    @property
    def device_models(self) -> dict[str, int]:
        """Model inventory suitable for exact topology assertions."""
        return dict(
            sorted(
                Counter(
                    str(device["model"])
                    for devices in self.devices_by_org.values()
                    for device in devices
                ).items()
            )
        )

    @property
    def switch_port_count(self) -> int:
        """Generated switch port response rows."""
        return sum(len(ports) for ports in self.switch_ports_by_serial.values())

    @property
    def client_count(self) -> int:
        """Generated client response rows."""
        return sum(len(clients) for clients in self.clients_by_network.values())

    @property
    def application_row_count(self) -> int:
        """Flattened client-application rows, not client response envelopes."""
        return sum(
            len(cast(list[object], entry["applicationUsage"]))
            for entries in self.application_usage_by_network.values()
            for entry in entries
        )

    @property
    def shape_assumptions(self) -> tuple[str, ...]:
        """Stable output labels that CI reports must print verbatim."""
        return tuple(f"SHAPE-ASSUMED:{family}" for family in sorted(self.assumed_families))

    def measured_report(
        self,
        registry: CollectorRegistry,
        *,
        api_calls: int,
        rss_bytes: int,
        scrape_render_seconds: float,
    ) -> FleetMeasuredReport:
        """Create one truthful report from a completed collection's registry and measurements."""
        payload = generate_latest(registry)
        samples = sum(len(metric.samples) for metric in registry.collect())
        return FleetMeasuredReport(
            preset=self.preset,
            series_count=samples,
            rss_bytes=rss_bytes,
            calls_per_cycle=api_calls,
            scrape_render_seconds=scrape_render_seconds,
            payload_bytes=len(payload),
            shape_assumptions=self.shape_assumptions,
        )


@dataclass(frozen=True)
class FleetMeasuredReport:
    """Measured output for a single completed fixture collection, never a forecast."""

    preset: FleetPreset
    series_count: int
    rss_bytes: int
    calls_per_cycle: int
    scrape_render_seconds: float
    payload_bytes: int
    shape_assumptions: tuple[str, ...]


HOMELAB_BASELINE: Final[HomelabBaseline] = HomelabBaseline()

PRESET_PARAMETERS: Final[dict[FleetPreset, FleetParameters]] = {
    FleetPreset.HOMELAB: FleetParameters(
        networks_per_org=1,
        devices_per_network={"MR": 1, "MS": 2, "MT": 16},
        ports_per_switch=0,
        ssids_per_network=8,
        clients_per_network=104,
        application_rows_per_client=2,
        final_network_application_rows=205,
        models={
            "MR": ("MR56",),
            "MS": ("MS120-8LP", "MS250-24P"),
            "MT": ("MT14",) * 6 + ("MT15",) * 2 + ("MT20",) * 2 + ("MT40",) * 6,
        },
        switch_port_counts=(8, 22),
    ),
    FleetPreset.BRANCH_RETAIL: FleetParameters(
        networks_per_org=750,
        devices_per_network={"MX": 2, "MS": 1, "MR": 3},
        ports_per_switch=24,
        ssids_per_network=4,
        clients_per_network=10,
    ),
    FleetPreset.CAMPUS: FleetParameters(
        networks_per_org=20,
        devices_per_network={"MR": 200, "MS": 60},
        ports_per_switch=48,
        ssids_per_network=15,
        clients_per_network=100,
    ),
    FleetPreset.DENSE_SWITCH: FleetParameters(
        networks_per_org=50,
        devices_per_network={"MS": 40},
        ports_per_switch=48,
        ssids_per_network=0,
        clients_per_network=0,
    ),
    FleetPreset.XL_MULTI_SITE: FleetParameters(
        networks_per_org=3500,
        devices_per_network={"MR": 4, "MS": 1, "MT": 1},
        ports_per_switch=24,
        ssids_per_network=4,
        clients_per_network=0,
    ),
    FleetPreset.MULTI_ORG_SHARD: FleetParameters(
        networks_per_org=75,
        devices_per_network={"MX": 2, "MS": 1, "MR": 3},
        ports_per_switch=24,
        ssids_per_network=4,
        clients_per_network=0,
        organizations=10,
        exporter_instances=10,
    ),
    FleetPreset.CAMERA_HEAVY: FleetParameters(
        networks_per_org=30,
        devices_per_network={"MV": 800},
        ports_per_switch=0,
        ssids_per_network=0,
        clients_per_network=0,
    ),
}

PRESETS_BY_CI_TIER: Final[dict[FleetCITier, tuple[FleetPreset, ...]]] = {
    FleetCITier.PR: (FleetPreset.HOMELAB, FleetPreset.BRANCH_RETAIL),
    FleetCITier.SCHEDULED: (
        FleetPreset.CAMPUS,
        FleetPreset.DENSE_SWITCH,
        FleetPreset.XL_MULTI_SITE,
    ),
    FleetCITier.ON_DEMAND: (FleetPreset.MULTI_ORG_SHARD, FleetPreset.CAMERA_HEAVY),
}


def presets_for_ci_tier(tier: FleetCITier | str) -> tuple[FleetPreset, ...]:
    """Return the exact named presets selected by one CI tier."""
    return PRESETS_BY_CI_TIER[FleetCITier(tier)]


def peak_rss_bytes() -> int:
    """Return this process's peak RSS in bytes on macOS and Linux runners."""
    rss = getrusage(RUSAGE_SELF).ru_maxrss
    return rss if sys.platform == "darwin" else rss * 1024


def build_fleet(preset: FleetPreset | str) -> FleetFixture:
    """Build one deterministic named fleet without any API access."""
    selected = FleetPreset(preset)
    parameters = PRESET_PARAMETERS[selected]
    parameters.validate()

    organizations: list[dict[str, object]] = []
    networks_by_org: dict[str, list[dict[str, object]]] = {}
    devices_by_org: dict[str, list[dict[str, object]]] = {}
    switch_ports_by_serial: dict[str, list[dict[str, object]]] = {}
    ssids_by_network: dict[str, list[dict[str, object]]] = {}
    clients_by_network: dict[str, list[dict[str, object]]] = {}
    application_usage_by_network: dict[str, list[dict[str, object]]] = {}

    for org_index in range(parameters.organizations):
        org_id = f"fleet-{selected.value.lower()}-org-{org_index:02d}"
        organizations.append({
            "id": org_id,
            "name": f"{selected.value} Organization {org_index + 1}",
        })
        org_networks: list[dict[str, object]] = []
        org_devices: list[dict[str, object]] = []

        for network_index in range(parameters.networks_per_org):
            network_id = f"{org_id}-network-{network_index:04d}"
            product_types = [
                _PRODUCT_TYPES[family]
                for family, count in parameters.devices_per_network.items()
                if count > 0
            ]
            network: dict[str, object] = {
                "id": network_id,
                "organizationId": org_id,
                "name": f"{selected.value} Network {network_index + 1}",
                "productTypes": product_types,
                "timeZone": "Europe/London",
                "tags": [],
                "enrollmentString": None,
            }
            org_networks.append(network)
            ssids_by_network[network_id] = _build_ssids(parameters.ssids_per_network)
            clients = _build_clients(network_id, parameters.clients_per_network)
            clients_by_network[network_id] = clients
            row_cap = (
                parameters.final_network_application_rows
                if network_index == parameters.networks_per_org - 1
                and parameters.final_network_application_rows is not None
                else None
            )
            application_usage_by_network[network_id] = _build_application_usage(
                clients, parameters.application_rows_per_client, row_cap
            )

            for family, count in parameters.devices_per_network.items():
                family_models = (parameters.models or {}).get(family, (_FAMILY_MODELS[family],))
                for family_index in range(count):
                    model = family_models[family_index % len(family_models)]
                    serial = f"F{family}-{org_index:02d}{network_index:04d}{family_index:04d}"
                    device = _build_device(serial, model, network_id, family, family_index)
                    org_devices.append(device)
                    if family == "MS":
                        port_count = _switch_port_count(parameters, family_index)
                        switch_ports_by_serial[serial] = _build_switch_ports(port_count)

        networks_by_org[org_id] = org_networks
        devices_by_org[org_id] = org_devices

    assumed_families = frozenset(
        family
        for family, count in parameters.devices_per_network.items()
        if count and family in _SHAPE_ASSUMED_FAMILIES
    )
    return FleetFixture(
        preset=selected,
        parameters=parameters,
        organizations=organizations,
        networks_by_org=networks_by_org,
        devices_by_org=devices_by_org,
        switch_ports_by_serial=switch_ports_by_serial,
        ssids_by_network=ssids_by_network,
        clients_by_network=clients_by_network,
        application_usage_by_network=application_usage_by_network,
        assumed_families=assumed_families,
        baseline=HOMELAB_BASELINE if selected is FleetPreset.HOMELAB else None,
    )


def _build_device(
    serial: str, model: str, network_id: str, family: str, family_index: int
) -> dict[str, object]:
    """Return the existing SDK device-list response shape deterministically."""
    return {
        "serial": serial,
        "name": f"{model} {family_index + 1}",
        "model": model,
        "networkId": network_id,
        "mac": f"02:00:{family_index // 256:02x}:{family_index % 256:02x}:00:01",
        "lanIp": f"10.{family_index // 254}.{family_index % 254 + 1}.1",
        "tags": [],
        "lat": 51.5074,
        "lng": -0.1278,
        "address": "Fleet Fixture",
        "firmware": f"{family.lower()}-fixture",
        "url": f"https://dashboard.meraki.com/manage/nodes/show/{serial}",
    }


def _build_switch_ports(count: int) -> list[dict[str, object]]:
    """Return the existing switch-port status response shape."""
    return [
        {"portId": str(port), "name": f"Port {port}", "status": "Connected", "enabled": True}
        for port in range(1, count + 1)
    ]


def _build_ssids(count: int) -> list[dict[str, object]]:
    """Return a bounded SDK-shaped SSID list."""
    return [
        {"number": number, "name": f"SSID {number}", "enabled": True, "authMode": "psk"}
        for number in range(count)
    ]


def _build_clients(network_id: str, count: int) -> list[dict[str, object]]:
    """Return deterministic clients in the existing client-list response shape."""
    return [
        {
            "id": f"{network_id}-client-{index:04d}",
            "mac": f"02:01:{index // 256:02x}:{index % 256:02x}:00:01",
            "ip": f"192.0.2.{index % 254 + 1}",
            "description": f"Fleet client {index + 1}",
            "status": "Online",
            "lastSeen": "2026-08-12T00:00:00Z",
            "firstSeen": "2026-08-01T00:00:00Z",
            "manufacturer": "Fixture",
            "os": "Fixture OS",
            "recentDeviceSerial": "fixture-device",
            "recentDeviceName": "Fixture Device",
            "recentDeviceConnection": "Wireless",
            "ssid": "SSID 0",
            "vlan": 1,
            "usage": {"sent": 100, "recv": 200, "total": 300},
            "wirelessCapabilities": "802.11ax - 5 GHz",
        }
        for index in range(count)
    ]


def _build_application_usage(
    clients: list[dict[str, object]], rows_per_client: int, total_rows: int | None
) -> list[dict[str, object]]:
    """Return client-application usage envelopes using the collector's actual keys."""
    remaining = total_rows
    response: list[dict[str, object]] = []
    for client in clients:
        row_count = rows_per_client if remaining is None else min(rows_per_client, remaining)
        response.append({
            "clientId": client["id"],
            "applicationUsage": [
                {
                    "application": f"Fixture Application {row_index + 1}",
                    "received": 200 + row_index,
                    "sent": 100 + row_index,
                }
                for row_index in range(row_count)
            ],
        })
        if remaining is not None:
            remaining -= row_count
    return response


def _switch_port_count(parameters: FleetParameters, switch_index: int) -> int:
    """Resolve per-switch captured counts when a known topology supplies them."""
    if parameters.switch_port_counts is not None:
        return parameters.switch_port_counts[switch_index]
    return parameters.ports_per_switch
