"""Contracts for the Issue #707 deterministic fleet fixtures."""

from __future__ import annotations

import pytest

from tests.fixtures.fleet import (
    FleetCITier,
    FleetParameters,
    FleetPreset,
    build_fleet,
    presets_for_ci_tier,
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


@pytest.mark.slow
@pytest.mark.parametrize(
    ("preset", "networks", "devices", "ports"),
    [
        (FleetPreset.HOMELAB, 1, 19, 30),
        (FleetPreset.BRANCH_RETAIL, 750, 4500, 18000),
        pytest.param(
            FleetPreset.CAMPUS,
            20,
            5200,
            57600,
            marks=pytest.mark.fleet_scheduled,
        ),
        pytest.param(
            FleetPreset.DENSE_SWITCH,
            50,
            2000,
            96000,
            marks=pytest.mark.fleet_scheduled,
        ),
        pytest.param(
            FleetPreset.XL_MULTI_SITE,
            3500,
            21000,
            84000,
            marks=pytest.mark.fleet_scheduled,
        ),
        pytest.param(
            FleetPreset.MULTI_ORG_SHARD,
            750,
            4500,
            18000,
            marks=pytest.mark.fleet_on_demand,
        ),
        pytest.param(
            FleetPreset.CAMERA_HEAVY,
            30,
            24000,
            0,
            marks=pytest.mark.fleet_on_demand,
        ),
    ],
)
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


def test_ci_tiers_select_the_seven_presets_without_overlap() -> None:
    """Workflow wiring has one source of truth for PR, scheduled, and on-demand scale work."""
    selected = [preset for tier in FleetCITier for preset in presets_for_ci_tier(tier)]

    assert presets_for_ci_tier(FleetCITier.PR) == (
        FleetPreset.HOMELAB,
        FleetPreset.BRANCH_RETAIL,
    )
    assert presets_for_ci_tier(FleetCITier.SCHEDULED) == (
        FleetPreset.CAMPUS,
        FleetPreset.DENSE_SWITCH,
        FleetPreset.XL_MULTI_SITE,
    )
    assert presets_for_ci_tier(FleetCITier.ON_DEMAND) == (
        FleetPreset.MULTI_ORG_SHARD,
        FleetPreset.CAMERA_HEAVY,
    )
    assert set(selected) == set(FleetPreset)
    assert len(selected) == len(set(selected))
