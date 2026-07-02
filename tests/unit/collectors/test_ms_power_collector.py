"""Tests for MS power module (PSU) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.ms_power import MSPowerCollector

if TYPE_CHECKING:
    pass


class TestMSPowerCollector:
    """Test MS power module collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.organizations = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent DeviceCollector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.rate_limiter = None
        # No inventory means no NetworkFilter — collectors emit all rows.
        parent.inventory = None

        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        parent._set_metric = MagicMock()
        return parent

    @pytest.fixture
    def ms_power_collector(
        self,
        mock_parent: MagicMock,
    ) -> MSPowerCollector:
        """Create MS power collector instance."""
        return MSPowerCollector(mock_parent)

    def test_initialization_creates_gauge(
        self,
        ms_power_collector: MSPowerCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test that the collector creates its gauge on init."""
        assert ms_power_collector.parent == mock_parent
        assert ms_power_collector.api == mock_parent.api
        assert ms_power_collector.settings == mock_parent.settings
        mock_parent._create_gauge.assert_called()
        assert ms_power_collector._ms_power_supply_status is not None

    async def test_collect_power_modules_basic_emission(
        self,
        ms_power_collector: MSPowerCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test basic emission with device serial vs PSU serial distinct in labels."""
        mock_api.organizations.getOrganizationDevicesPowerModulesStatusesByDevice = MagicMock(
            return_value=[
                {
                    "name": "Switch 1",
                    "serial": "Q2SW-1111-2222",
                    "mac": "00:11:22:33:44:55",
                    "network": {"id": "N_111"},
                    "productType": "switch",
                    "model": "MS250-48",
                    "slots": [
                        {
                            "number": 1,
                            "serial": "PSU-SERIAL-1",
                            "model": "PWR-350WAC",
                            "status": "powering",
                        }
                    ],
                }
            ]
        )

        device_lookup = {
            "Q2SW-1111-2222": {
                "name": "Switch 1",
                "model": "MS250-48",
                "network_id": "N_111",
                "network_name": "Office Network",
            }
        }

        await ms_power_collector.collect_power_modules("org1", "Test Org", device_lookup)

        assert mock_parent._set_metric.call_count == 1
        gauge, labels, value, *_ = mock_parent._set_metric.call_args_list[0][0]
        assert gauge is ms_power_collector._ms_power_supply_status
        assert value == 1
        assert labels["serial"] == "Q2SW-1111-2222"
        assert labels["psu_serial"] == "PSU-SERIAL-1"
        assert labels["serial"] != labels["psu_serial"]
        assert labels["slot"] == "1"
        assert labels["status"] == "powering"
        assert labels["network_id"] == "N_111"
        assert labels["network_name"] == "Office Network"
        assert labels["model"] == "MS250-48"

    async def test_collect_power_modules_multiple_slots(
        self,
        ms_power_collector: MSPowerCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that multiple PSU slots on one device each emit a metric."""
        mock_api.organizations.getOrganizationDevicesPowerModulesStatusesByDevice = MagicMock(
            return_value=[
                {
                    "name": "Switch 1",
                    "serial": "Q2SW-1111-2222",
                    "network": {"id": "N_111"},
                    "productType": "switch",
                    "model": "MS250-48",
                    "slots": [
                        {
                            "number": 1,
                            "serial": "PSU-SERIAL-1",
                            "model": "PWR-350WAC",
                            "status": "powering",
                        },
                        {
                            "number": 2,
                            "serial": "PSU-SERIAL-2",
                            "model": "PWR-350WAC",
                            "status": "not powering",
                        },
                    ],
                }
            ]
        )

        await ms_power_collector.collect_power_modules("org1", "Test Org", {})

        assert mock_parent._set_metric.call_count == 2
        _, labels_0, _, *_ = mock_parent._set_metric.call_args_list[0][0]
        _, labels_1, _, *_ = mock_parent._set_metric.call_args_list[1][0]
        assert labels_0["slot"] == "1"
        assert labels_0["status"] == "powering"
        assert labels_1["slot"] == "2"
        assert labels_1["status"] == "not powering"

    async def test_collect_power_modules_empty_slot_serial(
        self,
        ms_power_collector: MSPowerCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """An empty PSU slot (serial None) must still emit with psu_serial=''."""
        mock_api.organizations.getOrganizationDevicesPowerModulesStatusesByDevice = MagicMock(
            return_value=[
                {
                    "name": "Switch 1",
                    "serial": "Q2SW-1111-2222",
                    "network": {"id": "N_111"},
                    "productType": "switch",
                    "model": "MS250-48",
                    "slots": [
                        {
                            "number": 2,
                            "serial": None,
                            "model": None,
                            "status": "not connected",
                        }
                    ],
                }
            ]
        )

        await ms_power_collector.collect_power_modules("org1", "Test Org", {})

        assert mock_parent._set_metric.call_count == 1
        _, labels, _, *_ = mock_parent._set_metric.call_args_list[0][0]
        assert not labels["psu_serial"]
        assert labels["slot"] == "2"
        assert labels["status"] == "not connected"

    async def test_collect_power_modules_empty_response(
        self,
        ms_power_collector: MSPowerCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Empty API response should not emit any metrics."""
        mock_api.organizations.getOrganizationDevicesPowerModulesStatusesByDevice = MagicMock(
            return_value=[]
        )

        await ms_power_collector.collect_power_modules("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_collect_power_modules_respects_network_filter(
        self,
        ms_power_collector: MSPowerCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Devices in excluded networks must not emit power module metrics."""
        mock_api.organizations.getOrganizationDevicesPowerModulesStatusesByDevice = MagicMock(
            return_value=[
                {
                    "name": "Switch In",
                    "serial": "Q-IN",
                    "network": {"id": "N_INCLUDED"},
                    "model": "MS250-48",
                    "slots": [
                        {"number": 1, "serial": "PSU-IN", "status": "powering"},
                    ],
                },
                {
                    "name": "Switch Out",
                    "serial": "Q-OUT",
                    "network": {"id": "N_EXCLUDED"},
                    "model": "MS250-48",
                    "slots": [
                        {"number": 1, "serial": "PSU-OUT", "status": "powering"},
                    ],
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await ms_power_collector.collect_power_modules("org1", "Test Org", {})

        assert mock_parent._set_metric.call_count == 1
        _, labels, _, *_ = mock_parent._set_metric.call_args_list[0][0]
        assert labels["network_id"] == "N_INCLUDED"
        assert labels["serial"] == "Q-IN"

    async def test_collect_power_modules_api_error(
        self,
        ms_power_collector: MSPowerCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that API errors are handled gracefully by the error decorator."""
        mock_api.organizations.getOrganizationDevicesPowerModulesStatusesByDevice = MagicMock(
            side_effect=Exception("API connection failed")
        )

        # Should not raise - @with_error_handling(continue_on_error=True) catches it
        await ms_power_collector.collect_power_modules("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_collect_power_modules_does_not_wipe_other_orgs(
        self,
        ms_power_collector: MSPowerCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """collect_power_modules must NOT clear the whole gauge.

        The gauge instance is shared across concurrently-collected orgs, so a
        global _metrics.clear() would wipe every other org's series mid-cycle
        (the F-001 multi-org wipe bug). Stale status-label churn is delegated to
        the metric expiration manager instead. Seed a series for a *different* org
        and confirm org1's collection leaves it intact.
        """
        gauge = ms_power_collector._ms_power_supply_status

        # Series belonging to another org (would be wiped by a global clear()).
        gauge.labels(
            org_id="org2",
            org_name="Other Org",
            network_id="N_222",
            network_name="Other Network",
            serial="Q2SW-OTHER",
            name="Switch 9",
            model="MS250-48",
            device_type="MS",
            slot="1",
            psu_serial="PSU-OTHER",
            status="powering",
        ).set(1)

        assert len(gauge._metrics) == 1

        mock_api.organizations.getOrganizationDevicesPowerModulesStatusesByDevice = MagicMock(
            return_value=[
                {
                    "name": "Switch 1",
                    "serial": "Q2SW-1111-2222",
                    "network": {"id": "N_111"},
                    "model": "MS250-48",
                    "slots": [
                        {
                            "number": 1,
                            "serial": "PSU-SERIAL-1",
                            "status": "not powering",
                        }
                    ],
                }
            ]
        )

        await ms_power_collector.collect_power_modules("org1", "Test Org", {})

        # org2's series must survive — org1's collection must not wipe the shared gauge.
        assert len(gauge._metrics) == 1
        assert mock_parent._set_metric.call_count == 1
