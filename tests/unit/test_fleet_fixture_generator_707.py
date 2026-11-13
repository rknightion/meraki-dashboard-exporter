"""Contracts for the Issue #707 deterministic fleet fixtures."""

from __future__ import annotations

import pytest

from tests.fixtures.fleet import (
    MEDIUM_FLEET_PRESET,
    FleetParameters,
    FleetPreset,
    build_fleet,
)


def test_homelab_reproduces_the_frozen_live_baseline() -> None:
    """The only measured estate remains a stable fixture contract."""
    fleet = build_fleet(FleetPreset.HOMELAB)
    assert fleet.baseline is not None

    assert fleet.network_count == 1
    assert fleet.device_count == 19
    assert fleet.device_models == {
        "MR56": 1,
        "MS120-8LP": 1,
        "MS250-24P": 1,
        "MT14": 6,
        "MT15": 2,
        "MT20": 2,
        "MT40": 6,
    }
    assert fleet.switch_port_count == 30
    assert fleet.client_count == 104
    assert fleet.application_row_count == 205
    assert fleet.baseline.non_comment_lines == 4677
    assert fleet.baseline.samples == 4627
    assert fleet.baseline.payload_bytes == 738423
    assert fleet.baseline.scrape_render_seconds == 0.223904
    assert fleet.baseline.solved_rps == 0.5341667
    assert fleet.baseline.meraki_ms_samples == 2225
    assert fleet.baseline.demand_formula == (1141, 1176)


def test_branch_retail_is_the_frozen_literal_medium_topology() -> None:
    """D11's MEDIUM class is the representative many-network fleet, not a size label."""
    assert MEDIUM_FLEET_PRESET is FleetPreset.BRANCH_RETAIL

    fleet = build_fleet(MEDIUM_FLEET_PRESET)
    assert fleet.parameters.networks_per_org == 750
    assert fleet.parameters.devices_per_network == {"MX": 2, "MS": 1, "MR": 3}
    assert fleet.parameters.ports_per_switch == 24
    assert fleet.parameters.ssids_per_network == 4
    assert fleet.parameters.clients_per_network == 10


_EXPECTED_TOPOLOGY = [
    (FleetPreset.HOMELAB, 1, 19, 30),
    (FleetPreset.BRANCH_RETAIL, 750, 4500, 18000),
    (FleetPreset.CAMPUS, 20, 5200, 57600),
    (FleetPreset.DENSE_SWITCH, 50, 2000, 96000),
    (FleetPreset.XL_MULTI_SITE, 3500, 21000, 84000),
    (FleetPreset.MULTI_ORG_SHARD, 750, 4500, 18000),
    (FleetPreset.CAMERA_HEAVY, 30, 24000, 0),
]


@pytest.mark.slow
@pytest.mark.parametrize(("preset", "networks", "devices", "ports"), _EXPECTED_TOPOLOGY)
def test_every_named_preset_materializes_a_vendor_valid_topology(
    preset: FleetPreset, networks: int, devices: int, ports: int
) -> None:
    """CI consumes only named, executable preset definitions."""
    fleet = build_fleet(preset)

    assert fleet.network_count == networks
    assert fleet.device_count == devices
    assert fleet.switch_port_count == ports
    print(
        f"{preset.value}: networks={fleet.network_count} devices={fleet.device_count} "
        f"ports={fleet.switch_port_count} assumptions={fleet.shape_assumptions or ('none',)}"
    )
    for org_devices in fleet.devices_by_org.values():
        assert len(org_devices) <= 50000
        per_network = {}
        for device in org_devices:
            network_id = str(device["networkId"])
            per_network[network_id] = per_network.get(network_id, 0) + 1
        assert max(per_network.values(), default=0) <= 5000


@pytest.mark.parametrize(
    ("preset", "assumptions"),
    [
        (FleetPreset.HOMELAB, ()),
        (FleetPreset.BRANCH_RETAIL, ("SHAPE-ASSUMED:MX",)),
        (FleetPreset.CAMPUS, ()),
        (FleetPreset.DENSE_SWITCH, ()),
        (FleetPreset.XL_MULTI_SITE, ()),
        (FleetPreset.MULTI_ORG_SHARD, ("SHAPE-ASSUMED:MX",)),
        (FleetPreset.CAMERA_HEAVY, ("SHAPE-ASSUMED:MV",)),
    ],
)
def test_shape_assumptions_are_explicit_for_absent_hardware(
    preset: FleetPreset, assumptions: tuple[str, ...]
) -> None:
    """A green synthetic fixture must not imply unowned-family verification."""
    assert build_fleet(preset).shape_assumptions == assumptions


def test_vendor_cap_overflow_is_rejected_before_materializing_data() -> None:
    """The generator cannot silently recreate the invalid fleet mixes from F-L9-07."""
    invalid = FleetParameters(
        networks_per_org=1,
        devices_per_network={"MX": 3},
        ports_per_switch=0,
        ssids_per_network=0,
        clients_per_network=0,
    )

    with pytest.raises(ValueError, match="at most 2 MX"):
        invalid.validate()


def test_topology_rows_cover_every_preset() -> None:
    """Every named preset has exactly one topology assertion row."""
    selected = [row[0] for row in _EXPECTED_TOPOLOGY]
    assert set(selected) == set(FleetPreset)
    assert len(selected) == len(set(selected))
