"""Tests for BaseDeviceCollector.collect_memory_metrics pagination (F-007, #548).

The org-wide ``getOrganizationDevicesSystemMemoryUsageHistoryByInterval`` fetch
must pass ``total_pages="all"`` — otherwise the SDK's default ``perPage`` (10)
silently truncates memory metrics to the first 10 devices per organization.

It must also request ``perPage=20`` — the documented endpoint maximum (spec:
"Acceptable range is 3 - 20. Default is 10.") — so each page carries as many
devices as possible, minimizing the number of pages fetched per cycle (#548).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from prometheus_client import Gauge

from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.collectors.devices.mg import MGCollector
from meraki_dashboard_exporter.core.metric_expiration import MetricExpirationManager
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest


class TestCollectMemoryMetricsPagination:
    """Verify the org-wide memory-history fetch pages through every device."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Mock API whose memory-history call returns an empty list."""
        api = MagicMock()
        api.organizations = MagicMock()
        # SDK call returns an empty list — we only assert how it is invoked.
        api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval = MagicMock(
            return_value=[]
        )
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Mock parent DeviceCollector wiring the API + a gauge factory."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.rate_limiter = None
        parent.inventory = None  # no NetworkFilter resolution

        def create_gauge(name, description, labelnames):
            return Gauge(name.value, description, labelnames)

        parent._create_gauge = MagicMock(side_effect=create_gauge)
        return parent

    async def test_memory_fetch_requests_all_pages(self, mock_parent: MagicMock) -> None:
        """The memory-history fetch must page through every device, not just 10."""
        collector = MGCollector(mock_parent)

        await collector.collect_memory_metrics("org-1", "Org One")

        fetch = (
            mock_parent.api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval
        )
        fetch.assert_called_once()
        _, kwargs = fetch.call_args
        assert kwargs.get("total_pages") == "all", (
            "memory fetch must pass total_pages='all' to avoid the default perPage=10 truncation"
        )
        assert kwargs.get("perPage") == 20, (
            "memory fetch must request perPage=20 (the endpoint maximum) to minimize "
            "page count per cycle (#548)"
        )


class TestCollectMemoryMetricsRows(BaseCollectorTest):
    """Exercise memory rows through the device collector."""

    collector_class = DeviceCollector

    @pytest.fixture
    def mock_parent(self) -> MagicMock:
        """Build a parent with a fixed metric TTL."""
        parent = MagicMock()
        parent.rate_limiter = None
        parent.inventory = None
        parent._create_gauge = MagicMock()
        parent._group_ttl_seconds.return_value = 600
        return parent

    @staticmethod
    def row(serial: str = "S1", network_id: str = "N_1") -> dict:
        """Build a synthetic memory response row."""
        return {
            "serial": serial,
            "model": "MR56",
            "network": {"id": network_id, "name": "One"},
            "provisioned": 4096,
            "intervals": [
                {
                    "memory": {
                        "used": {"maximum": 2048, "percentages": {"maximum": 50.0}},
                        "free": {"minimum": 1024},
                    }
                }
            ],
        }

    @staticmethod
    def expected(serial: str, network_id: str = "N_1") -> list:
        """Build expected metric calls for a complete row."""
        labels = {
            "org_id": "org-1",
            "network_id": network_id,
            "serial": serial,
            "model": "MR56",
            "device_type": "MR",
        }
        return [
            call("_device_memory_total_bytes", labels, 4194304, ttl_seconds=600),
            call("_device_memory_used_bytes", {**labels, "stat": "max"}, 2097152, ttl_seconds=600),
            call("_device_memory_usage_percent", labels, 50.0, ttl_seconds=600),
            call("_device_memory_free_bytes", {**labels, "stat": "min"}, 1048576, ttl_seconds=600),
        ]

    async def collect(self, parent: MagicMock, rows: list[dict]) -> None:
        """Feed rows through the collector."""
        parent.api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval.return_value = rows
        await MGCollector(parent).collect_memory_metrics("org-1", "Org One")

    @pytest.mark.parametrize("memory_ttl", [600.0, 1200.0], ids=["short", "long"])
    async def test_memory_row_expires_on_device_memory_ttl(
        self, collector, mock_api, settings, isolated_registry, memory_ttl
    ) -> None:
        """A complete row stays exposed for the memory group's TTL, not availability's."""
        group_ttls = {
            EndpointGroupName.DEVICE_AVAILABILITY: 150.0,
            EndpointGroupName.DEVICE_MEMORY: memory_ttl,
        }
        scheduler = MagicMock()
        scheduler.should_run.return_value = True
        scheduler.ttl_seconds_for.side_effect = lambda group: group_ttls.get(group, 60.0)
        expiration = MetricExpirationManager(settings)
        expiration.set_ttl_resolver(lambda _: 45.0)
        collector.scheduler = scheduler
        collector.expiration_manager = expiration
        memory_fetch = (
            mock_api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval
        )
        memory_fetch.return_value = [self.row()]

        labels = {
            "org_id": "org-1",
            "network_id": "N_1",
            "serial": "S1",
            "model": "MR56",
            "device_type": "MR",
        }
        expected = [
            ("meraki_device_memory_free_bytes", {**labels, "stat": "min"}, 1048576),
            ("meraki_device_memory_total_bytes", labels, 4194304),
            ("meraki_device_memory_usage_percent", labels, 50.0),
            ("meraki_device_memory_used_bytes", {**labels, "stat": "max"}, 2097152),
        ]

        def samples() -> list[tuple[str, dict[str, str], float]]:
            return sorted(
                (
                    (sample.name, sample.labels, sample.value)
                    for family in isolated_registry.collect()
                    for sample in family.samples
                    if sample.name.startswith("meraki_device_memory_")
                ),
                key=lambda sample: sample[0],
            )

        with patch("meraki_dashboard_exporter.core.metric_expiration.time") as clock:
            clock.time.return_value = 5_000.0
            await collector.ms_collector.collect_memory_metrics("org-1", "Org One")
            assert samples() == expected
            clock.time.return_value += memory_ttl - 1
            await expiration._cleanup_expired_metrics()
            assert samples() == expected
            clock.time.return_value += 2.0
            await expiration._cleanup_expired_metrics()
            assert samples() == []

    async def test_row_outside_network_filter_emits_nothing(self, mock_parent: MagicMock) -> None:
        """Filter both disallowed and absent network IDs."""
        mock_parent.inventory = MagicMock()
        mock_parent.inventory.get_allowed_network_ids = AsyncMock(return_value={"N_1"})
        await self.collect(
            mock_parent, [self.row(), self.row("S2", "N_2"), {**self.row("S3"), "network": None}]
        )
        assert mock_parent._set_metric_value.call_args_list == self.expected("S1")

    @pytest.mark.parametrize(
        ("path", "missing"),
        [
            (("network",), set()),
            (("intervals", 0), {1, 2, 3}),
            (("intervals", 0, "memory"), {1, 2, 3}),
            (("intervals", 0, "memory", "used", "maximum"), {1}),
            (("intervals", 0, "memory", "used", "percentages"), {2}),
            (("intervals", 0, "memory", "used", "percentages", "maximum"), {2}),
            (("intervals", 0, "memory", "free", "minimum"), {3}),
        ],
    )
    async def test_null_field_skips_the_value_and_keeps_later_devices(
        self, mock_parent: MagicMock, path: tuple, missing: set[int]
    ) -> None:
        """Keep unaffected metrics and continue after each null field."""
        first = self.row()
        target = first
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = None
        await self.collect(mock_parent, [first, self.row("S2")])
        first_calls = self.expected("S1", "" if path == ("network",) else "N_1")
        expected = [item for index, item in enumerate(first_calls) if index not in missing]
        assert mock_parent._set_metric_value.call_args_list == expected + self.expected("S2")
        assert all(
            args.args[2] is not None for args in mock_parent._set_metric_value.call_args_list
        )
