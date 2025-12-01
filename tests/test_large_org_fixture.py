"""Tests for large organization fixture generation (P5.1.1)."""

from __future__ import annotations

import pytest

from tests.helpers.large_org_fixture import LargeOrgFixture, LargeOrgScenario


class TestLargeOrgFixture:
    """Test suite for large organization fixture generation."""

    def test_small_enterprise_fixture(self, small_enterprise_fixture: LargeOrgFixture) -> None:
        """Test small enterprise fixture meets specifications."""
        fixture = small_enterprise_fixture
        stats = fixture.get_stats()

        # Verify counts match scenario
        assert stats["total_organizations"] == 1
        assert stats["total_networks"] == 10
        # Allow ±20% variance due to randomization
        assert 200 <= stats["total_devices"] <= 300

        # Verify device distribution
        assert len(fixture.devices_by_org) == 1
        assert all(len(devices) > 0 for devices in fixture.devices_by_org.values())

    def test_medium_enterprise_fixture(self, medium_enterprise_fixture: LargeOrgFixture) -> None:
        """Test medium enterprise fixture meets specifications."""
        fixture = medium_enterprise_fixture
        stats = fixture.get_stats()

        # Verify counts match scenario
        assert stats["total_organizations"] == 1
        assert stats["total_networks"] == 25
        # Allow ±20% variance due to randomization
        assert 800 <= stats["total_devices"] <= 1200

        # Verify realistic device type distribution
        devices_by_type = stats["devices_by_type"]
        total_devices = stats["total_devices"]

        # Switches should be ~40% (±15%)
        if "MS" in devices_by_type:
            ms_percentage = (devices_by_type["MS"] / total_devices) * 100
            assert 25 <= ms_percentage <= 55, f"MS devices: {ms_percentage}%"

        # APs should be ~35% (±15%)
        if "MR" in devices_by_type:
            mr_percentage = (devices_by_type["MR"] / total_devices) * 100
            assert 20 <= mr_percentage <= 50, f"MR devices: {mr_percentage}%"

    def test_large_enterprise_fixture(self, large_enterprise_fixture: LargeOrgFixture) -> None:
        """Test large enterprise fixture meets specifications."""
        fixture = large_enterprise_fixture
        stats = fixture.get_stats()

        # Verify counts match scenario
        assert stats["total_organizations"] == 1
        assert stats["total_networks"] == 50
        # Allow ±20% variance due to randomization
        assert 2000 <= stats["total_devices"] <= 3000

        # Verify all device types are represented
        devices_by_type = stats["devices_by_type"]
        # Should have at least 3 different device types
        assert len(devices_by_type) >= 3

    def test_multi_org_small_fixture(self, multi_org_small_fixture: LargeOrgFixture) -> None:
        """Test multi-org small fixture meets specifications."""
        fixture = multi_org_small_fixture
        stats = fixture.get_stats()

        # Verify multi-org setup
        assert stats["total_organizations"] == 5
        assert stats["total_networks"] == 50  # 10 per org
        # Allow ±20% variance due to randomization
        assert 800 <= stats["total_devices"] <= 1200

        # Verify devices are distributed across orgs
        devices_per_org = stats["devices_per_org"]
        assert len(devices_per_org) == 5
        assert all(count > 0 for count in devices_per_org.values())

        # Each org should have roughly equal distribution (±40%)
        avg_devices = stats["total_devices"] / 5
        for org_id, count in devices_per_org.items():
            assert 0.6 * avg_devices <= count <= 1.4 * avg_devices, (
                f"Org {org_id}: {count} devices (expected ~{avg_devices})"
            )

    def test_custom_large_org(self, custom_large_org: type[LargeOrgFixture]) -> None:
        """Test custom large organization fixture creation."""
        fixture = custom_large_org(org_count=2, networks_per_org=15, devices_per_network=30)

        stats = fixture.get_stats()

        assert stats["total_organizations"] == 2
        assert stats["total_networks"] == 30  # 15 per org
        # 2 orgs × 15 networks × 30 devices × (0.8 to 1.2 variance)
        assert 720 <= stats["total_devices"] <= 1080

    def test_device_type_distribution(self, medium_enterprise_fixture: LargeOrgFixture) -> None:
        """Test that device type distribution is realistic."""
        fixture = medium_enterprise_fixture

        # Get counts for each device type
        ms_count = len(fixture.get_devices_by_type("MS"))
        mr_count = len(fixture.get_devices_by_type("MR"))
        mx_count = len(fixture.get_devices_by_type("MX"))
        mt_count = len(fixture.get_devices_by_type("MT"))
        mv_count = len(fixture.get_devices_by_type("MV"))
        mg_count = len(fixture.get_devices_by_type("MG"))

        total = fixture.total_devices

        # MS (switches) should be most common (30-50%)
        assert ms_count > 0
        assert 0.25 <= (ms_count / total) <= 0.55

        # MR (APs) should be second most common (25-45%)
        assert mr_count > 0
        assert 0.20 <= (mr_count / total) <= 0.50

        # Other types should exist but be less common
        assert mx_count >= 0  # May be 0 in small fixtures
        assert mt_count >= 0
        assert mv_count >= 0
        assert mg_count >= 0

    def test_network_product_types_variety(
        self, medium_enterprise_fixture: LargeOrgFixture
    ) -> None:
        """Test that networks have varied product types."""
        fixture = medium_enterprise_fixture

        product_type_combos = set()
        for network in fixture.all_networks:
            product_types = tuple(sorted(network.get("productTypes", [])))
            product_type_combos.add(product_types)

        # Should have at least 3 different product type combinations
        assert len(product_type_combos) >= 3

    def test_device_metadata_completeness(self, small_enterprise_fixture: LargeOrgFixture) -> None:
        """Test that generated devices have complete metadata."""
        fixture = small_enterprise_fixture

        for device in fixture.all_devices:
            # Required fields
            assert "serial" in device
            assert "name" in device
            assert "model" in device
            assert "networkId" in device
            assert "mac" in device
            assert "lanIp" in device

            # Context fields added by fixture
            assert "orgId" in device
            assert "orgName" in device
            assert "networkName" in device

            # Validate serial format (QXXX-XXXXXXXX)
            assert len(device["serial"]) >= 13
            assert "-" in device["serial"]

            # Validate MAC format
            assert device["mac"].count(":") == 5

    def test_get_devices_by_type(self, medium_enterprise_fixture: LargeOrgFixture) -> None:
        """Test filtering devices by type."""
        fixture = medium_enterprise_fixture

        ms_devices = fixture.get_devices_by_type("MS")
        mr_devices = fixture.get_devices_by_type("MR")

        # All returned devices should match the requested type
        for device in ms_devices:
            assert device["model"].startswith("MS")

        for device in mr_devices:
            assert device["model"].startswith("MR")

        # Total should match
        assert len(ms_devices) + len(mr_devices) <= fixture.total_devices

    def test_fixture_stats_accuracy(self, medium_enterprise_fixture: LargeOrgFixture) -> None:
        """Test that fixture statistics are accurate."""
        fixture = medium_enterprise_fixture
        stats = fixture.get_stats()

        # Verify stats match actual counts
        assert stats["total_organizations"] == len(fixture.organizations)
        assert stats["total_networks"] == len(fixture.all_networks)
        assert stats["total_devices"] == len(fixture.all_devices)

        # Verify averages are calculated correctly
        expected_avg_networks = stats["total_networks"] / stats["total_organizations"]
        assert stats["avg_networks_per_org"] == expected_avg_networks

        expected_avg_devices = stats["total_devices"] / stats["total_networks"]
        assert stats["avg_devices_per_network"] == pytest.approx(expected_avg_devices, rel=0.01)

        # Verify device counts by type add up
        total_counted = sum(stats["devices_by_type"].values())
        assert total_counted == stats["total_devices"]

    def test_organizations_have_unique_ids(self, multi_org_small_fixture: LargeOrgFixture) -> None:
        """Test that all organizations have unique IDs."""
        fixture = multi_org_small_fixture

        org_ids = [org["id"] for org in fixture.organizations]
        assert len(org_ids) == len(set(org_ids)), "Duplicate organization IDs found"

    def test_networks_have_unique_ids(self, medium_enterprise_fixture: LargeOrgFixture) -> None:
        """Test that all networks have unique IDs."""
        fixture = medium_enterprise_fixture

        network_ids = [net["id"] for net in fixture.all_networks]
        assert len(network_ids) == len(set(network_ids)), "Duplicate network IDs found"

    def test_devices_have_unique_serials(self, medium_enterprise_fixture: LargeOrgFixture) -> None:
        """Test that all devices have unique serial numbers."""
        fixture = medium_enterprise_fixture

        serials = [dev["serial"] for dev in fixture.all_devices]
        assert len(serials) == len(set(serials)), "Duplicate device serials found"

    def test_devices_belong_to_networks(self, medium_enterprise_fixture: LargeOrgFixture) -> None:
        """Test that all devices belong to valid networks."""
        fixture = medium_enterprise_fixture

        network_ids = {net["id"] for net in fixture.all_networks}

        for device in fixture.all_devices:
            assert device["networkId"] in network_ids, (
                f"Device {device['serial']} references unknown network {device['networkId']}"
            )

    def test_print_summary(
        self, medium_enterprise_fixture: LargeOrgFixture, capsys: pytest.CaptureFixture
    ) -> None:
        """Test that print_summary produces output."""
        fixture = medium_enterprise_fixture

        fixture.print_summary()
        captured = capsys.readouterr()

        # Verify output contains key information
        assert "Large Organization Fixture Summary" in captured.out
        assert "Organizations:" in captured.out
        assert "Networks:" in captured.out
        assert "Total Devices:" in captured.out
        assert "Devices by Type:" in captured.out

    @pytest.mark.parametrize(
        "scenario,expected_orgs,expected_min_devices",
        [
            (LargeOrgScenario.SMALL_ENTERPRISE, 1, 200),
            (LargeOrgScenario.MEDIUM_ENTERPRISE, 1, 800),
            (LargeOrgScenario.LARGE_ENTERPRISE, 1, 2000),
            (LargeOrgScenario.MULTI_ORG_SMALL, 5, 800),
        ],
    )
    def test_scenarios(
        self,
        scenario: dict,
        expected_orgs: int,
        expected_min_devices: int,
    ) -> None:
        """Test various predefined scenarios."""
        fixture = LargeOrgFixture.from_scenario(scenario)
        stats = fixture.get_stats()

        assert stats["total_organizations"] == expected_orgs
        assert stats["total_devices"] >= expected_min_devices


@pytest.mark.slow
class TestLargeOrgPerformance:
    """Performance tests for large organization fixtures.

    These tests are marked as 'slow' and should be run separately.
    """

    def test_medium_enterprise_generation_time(self) -> None:
        """Test medium enterprise fixture generation time.

        This test verifies that fixture generation completes in reasonable time.
        For benchmarking, install pytest-benchmark and use the benchmark fixture.
        """
        import time

        start_time = time.time()
        fixture = LargeOrgFixture.from_scenario(LargeOrgScenario.MEDIUM_ENTERPRISE)
        elapsed_time = time.time() - start_time

        # Should generate 1000 devices in under 1 second
        assert fixture.total_devices >= 800
        assert elapsed_time < 1.0, f"Generation took {elapsed_time:.3f}s (expected < 1.0s)"

    @pytest.mark.skipif(True, reason="Very large fixture - only run when specifically needed")
    def test_multi_org_large_fixture_generation(self) -> None:
        """Test generation of very large multi-org fixture (10000 devices)."""
        fixture = LargeOrgFixture.from_scenario(LargeOrgScenario.MULTI_ORG_LARGE)
        stats = fixture.get_stats()

        assert stats["total_organizations"] == 10
        assert stats["total_devices"] >= 8000  # Allow for variance

        # Should have good distribution across orgs
        devices_per_org = stats["devices_per_org"]
        avg_devices = stats["total_devices"] / 10
        for count in devices_per_org.values():
            # Each org should be within ±50% of average
            assert 0.5 * avg_devices <= count <= 1.5 * avg_devices
