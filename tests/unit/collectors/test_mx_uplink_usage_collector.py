"""Tests for MX per-uplink WAN usage collector."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.devices.mx_uplink_usage import (
    MXUplinkUsageCollector,
)

if TYPE_CHECKING:
    pass


class TestMXUplinkUsageCollector:
    """Test MX uplink usage collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.appliance = MagicMock()
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
    def collector(
        self,
        mock_parent: MagicMock,
    ) -> MXUplinkUsageCollector:
        """Create MX uplink usage collector instance."""
        return MXUplinkUsageCollector(mock_parent)

    def test_initialization(
        self,
        collector: MXUplinkUsageCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test collector initialization sets up parent/api/settings and gauges."""
        assert collector.parent == mock_parent
        assert collector.api == mock_parent.api
        assert collector.settings == mock_parent.settings

    def test_gauges_created(
        self,
        collector: MXUplinkUsageCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test that both sent and received gauges are created on init."""
        assert mock_parent._create_gauge.call_count == 2
        assert collector._mx_uplink_sent_bytes is not None
        assert collector._mx_uplink_recv_bytes is not None

    @staticmethod
    def _basic_usage_response() -> list[dict]:
        return [
            {
                "networkId": "N_111",
                "name": "Office Network",
                "byUplink": [
                    {
                        "serial": "Q2AB-1234-5678",
                        "interface": "wan1",
                        "sent": 12345,
                        "received": 67890,
                    }
                ],
            }
        ]

    async def test_usage_gate_closed_skips_fetch(
        self,
        collector: MXUplinkUsageCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A closed mx_uplink_usage gate skips the API call and emits nothing (#617)."""
        mock_parent._should_run_group = MagicMock(return_value=False)
        mock_api.appliance.getOrganizationApplianceUplinksUsageByNetwork = MagicMock(
            return_value=self._basic_usage_response()
        )

        await collector.collect_uplink_usage("org1", "Test Org", {})

        mock_api.appliance.getOrganizationApplianceUplinksUsageByNetwork.assert_not_called()
        mock_parent._set_metric.assert_not_called()
        mock_parent._mark_group_ran.assert_not_called()

    async def test_usage_marks_group_ran_and_threads_ttl(
        self,
        collector: MXUplinkUsageCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """A successful usage fetch marks mx_uplink_usage and threads its TTL (#617)."""
        mock_parent._should_run_group = MagicMock(return_value=True)
        mock_parent._group_ttl_seconds = MagicMock(return_value=600.0)
        mock_api.appliance.getOrganizationApplianceUplinksUsageByNetwork = MagicMock(
            return_value=self._basic_usage_response()
        )

        await collector.collect_uplink_usage("org1", "Test Org", {})

        from meraki_dashboard_exporter.core.scheduler import EndpointGroupName

        mock_parent._mark_group_ran.assert_called_once_with(EndpointGroupName.MX_UPLINK_USAGE)
        for call in mock_parent._set_metric.call_args_list:
            assert call.kwargs["ttl_seconds"] == 600.0

    async def test_basic_emission(
        self,
        collector: MXUplinkUsageCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that sent/received usage is emitted per uplink."""
        mock_api.appliance.getOrganizationApplianceUplinksUsageByNetwork = MagicMock(
            return_value=[
                {
                    "networkId": "N_111",
                    "name": "Office Network",
                    "byUplink": [
                        {
                            "serial": "Q2AB-1234-5678",
                            "interface": "wan1",
                            "sent": 12345,
                            "received": 67890,
                        }
                    ],
                }
            ]
        )

        device_lookup = {
            "Q2AB-1234-5678": {
                "name": "Office MX",
                "model": "MX68",
                "network_id": "N_111",
                "network_name": "Office Network",
                "device_type": "MX",
            }
        }

        await collector.collect_uplink_usage("org1", "Test Org", device_lookup)

        assert mock_parent._set_metric.call_count == 2

        gauge_0, labels_0, value_0, name_0 = mock_parent._set_metric.call_args_list[0][0]
        assert gauge_0 is collector._mx_uplink_sent_bytes
        assert labels_0["serial"] == "Q2AB-1234-5678"
        assert labels_0["network_id"] == "N_111"
        assert labels_0["interface"] == "wan1"
        assert "name" not in labels_0
        assert "network_name" not in labels_0
        assert "org_name" not in labels_0
        assert value_0 == 12345.0
        assert name_0 == "meraki_mx_uplink_sent_bytes"

        gauge_1, labels_1, value_1, name_1 = mock_parent._set_metric.call_args_list[1][0]
        assert gauge_1 is collector._mx_uplink_recv_bytes
        assert value_1 == 67890.0
        assert name_1 == "meraki_mx_uplink_recv_bytes"

    async def test_multiple_uplinks_per_network(
        self,
        collector: MXUplinkUsageCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test collection across multiple uplinks in one network row."""
        mock_api.appliance.getOrganizationApplianceUplinksUsageByNetwork = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "name": "Branch",
                    "byUplink": [
                        {
                            "serial": "Q2AB-0001",
                            "interface": "wan1",
                            "sent": 100,
                            "received": 200,
                        },
                        {
                            "serial": "Q2AB-0001",
                            "interface": "wan2",
                            "sent": 300,
                            "received": 400,
                        },
                    ],
                }
            ]
        )

        await collector.collect_uplink_usage("org1", "Test Org", {})

        # 2 uplinks * (sent + received) = 4 metric emissions
        assert mock_parent._set_metric.call_count == 4
        interfaces = {call[0][1]["interface"] for call in mock_parent._set_metric.call_args_list}
        assert interfaces == {"wan1", "wan2"}

    async def test_null_sent_and_received_skips_emission(
        self,
        collector: MXUplinkUsageCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that an uplink with null sent/received emits nothing."""
        mock_api.appliance.getOrganizationApplianceUplinksUsageByNetwork = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "name": "Branch",
                    "byUplink": [
                        {
                            "serial": "Q2AB-0001",
                            "interface": "wan1",
                            "sent": None,
                            "received": None,
                        }
                    ],
                }
            ]
        )

        await collector.collect_uplink_usage("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_sent_and_received_emitted_independently(
        self,
        collector: MXUplinkUsageCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that a null sent (but present received) only emits received."""
        mock_api.appliance.getOrganizationApplianceUplinksUsageByNetwork = MagicMock(
            return_value=[
                {
                    "networkId": "N_1",
                    "name": "Branch",
                    "byUplink": [
                        {
                            "serial": "Q2AB-0001",
                            "interface": "wan1",
                            "sent": None,
                            "received": 500,
                        }
                    ],
                }
            ]
        )

        await collector.collect_uplink_usage("org1", "Test Org", {})

        assert mock_parent._set_metric.call_count == 1
        gauge, _, value, _ = mock_parent._set_metric.call_args_list[0][0]
        assert gauge is collector._mx_uplink_recv_bytes
        assert value == 500.0

    async def test_empty_response(
        self,
        collector: MXUplinkUsageCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that an empty API response is handled gracefully."""
        mock_api.appliance.getOrganizationApplianceUplinksUsageByNetwork = MagicMock(
            return_value=[]
        )

        await collector.collect_uplink_usage("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_network_filter_exclusion(
        self,
        collector: MXUplinkUsageCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Uplinks in excluded networks must not emit usage metrics."""
        mock_api.appliance.getOrganizationApplianceUplinksUsageByNetwork = MagicMock(
            return_value=[
                {
                    "networkId": "N_INCLUDED",
                    "name": "Included",
                    "byUplink": [
                        {
                            "serial": "Q-IN",
                            "interface": "wan1",
                            "sent": 1,
                            "received": 2,
                        }
                    ],
                },
                {
                    "networkId": "N_EXCLUDED",
                    "name": "Excluded",
                    "byUplink": [
                        {
                            "serial": "Q-OUT",
                            "interface": "wan1",
                            "sent": 1,
                            "received": 2,
                        }
                    ],
                },
            ]
        )
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_INCLUDED"})

        await collector.collect_uplink_usage("org1", "Test Org", {})

        assert mock_parent._set_metric.call_count == 2
        for call in mock_parent._set_metric.call_args_list:
            assert call[0][1]["network_id"] == "N_INCLUDED"
            assert call[0][1]["serial"] == "Q-IN"

    async def test_api_error_handled_gracefully(
        self,
        collector: MXUplinkUsageCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test that API errors are handled gracefully by the error decorator."""
        mock_api.appliance.getOrganizationApplianceUplinksUsageByNetwork = MagicMock(
            side_effect=Exception("API connection failed")
        )

        await collector.collect_uplink_usage("org1", "Test Org", {})

        mock_parent._set_metric.assert_not_called()

    async def test_unknown_serial_falls_back_to_serial_as_name(
        self,
        collector: MXUplinkUsageCollector,
        mock_api: MagicMock,
        mock_parent: MagicMock,
    ) -> None:
        """Test collection when serial is not in the device lookup."""
        mock_api.appliance.getOrganizationApplianceUplinksUsageByNetwork = MagicMock(
            return_value=[
                {
                    "networkId": "N_999",
                    "name": "Unknown Network",
                    "byUplink": [
                        {
                            "serial": "Q2XX-UNKNOWN",
                            "interface": "wan1",
                            "sent": 1,
                            "received": 2,
                        }
                    ],
                }
            ]
        )

        await collector.collect_uplink_usage("org1", "Test Org", {})

        assert mock_parent._set_metric.call_count == 2
        _, labels, _, _ = mock_parent._set_metric.call_args_list[0][0]
        assert labels["serial"] == "Q2XX-UNKNOWN"
        assert labels["network_id"] == "N_999"
        assert "name" not in labels
        assert "network_name" not in labels


def test_uplink_usage_row_validates_via_domain_model() -> None:
    """F-023: the uplink-usage row is parsed via a typed Pydantic domain model."""
    from meraki_dashboard_exporter.core.domain_models import ApplianceUplinkUsage

    row = ApplianceUplinkUsage.model_validate({
        "networkId": "N_1",
        "name": "Office",
        "byUplink": [
            {"serial": "Q2AB-1234", "interface": "wan1", "sent": 12345, "received": None},
        ],
    })

    assert row.networkId == "N_1"
    entry = row.byUplink[0]
    assert entry.serial == "Q2AB-1234"
    assert entry.interface == "wan1"
    assert entry.sent == 12345.0
    assert entry.received is None
