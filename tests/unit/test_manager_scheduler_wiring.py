"""Tests for CollectorManager adaptive-scheduler wiring (#617, Lane M).

Covers BUILD SPEC §3 (`collectors/manager.py`):
- the scheduler is constructed right after the rate limiter and injected into
  every collector;
- `_register_endpoint_groups` funnels every collector's `get_endpoint_groups()`
  into `scheduler.register_groups`;
- `collect_initial` resolves the schedule from the org shape after the cache is
  warmed and emits the startup demand-vs-budget log line (plus an over-budget
  WARNING naming the priority-3/4 collectors to disable);
- `get_scheduling_diagnostics` exposes the scheduler diagnostics and no longer
  the retired `endpoint_intervals` block.

`inventory.get_org_shape` (Lane INV) is mocked throughout — this lane must not
depend on that lane being merged.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.collectors.manager import CollectorManager
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.core.scheduler import (
    EndpointGroup,
    EndpointGroupName,
    EndpointScheduler,
    OrgShape,
)


def _settings(**overrides: object) -> Settings:
    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )
    for key, value in overrides.items():
        setattr(settings.api, key, value)
    return settings


def _bare_manager(settings: Settings) -> CollectorManager:
    """Build a CollectorManager with real metrics/scheduler but no real collectors."""
    mock_client = MagicMock()
    mock_client.api = MagicMock()
    with (
        patch.object(CollectorManager, "_initialize_collectors"),
        patch.object(CollectorManager, "_validate_collector_configuration"),
    ):
        return CollectorManager(client=mock_client, settings=settings)


def _real_manager(settings: Settings) -> CollectorManager:
    """Build a CollectorManager with all real registered collectors (mock API)."""
    mock_client = MagicMock()
    mock_client.api = MagicMock()
    return CollectorManager(client=mock_client, settings=settings)


def _make_shape(**overrides: int) -> OrgShape:
    base: dict[str, object] = {
        "org_id": "123456",
        "network_count": 10,
        "wireless_network_count": 8,
        "switch_network_count": 6,
        "appliance_network_count": 5,
        "sensor_network_count": 2,
        "camera_network_count": 1,
        "cellular_network_count": 0,
        "device_count": 100,
        "ap_count": 40,
        "switch_count": 30,
        "appliance_count": 10,
        "physical_mx_count": 8,
        "camera_count": 5,
        "sensor_count": 15,
        "cellular_count": 0,
    }
    base.update(overrides)
    return OrgShape(**base)  # type: ignore[arg-type]


def _fake_collector(name: str, groups: tuple[EndpointGroup, ...]) -> Any:
    """Build a collector stub whose class name is ``name`` (drives short-name mapping)."""
    cls = type(
        name,
        (),
        {
            "get_endpoint_groups": lambda self: groups,
            "scheduler": None,
        },
    )
    return cls()


def _group(
    name: EndpointGroupName, priority: int, floor: float, gated: bool = True
) -> EndpointGroup:
    return EndpointGroup(
        name=name,
        priority=priority,
        floor_seconds=floor,
        cost_fn=lambda shape: 1.0,
        tier=UpdateTier.MEDIUM,
        gated=gated,
    )


# ---------------------------------------------------------------------------
# construction + injection
# ---------------------------------------------------------------------------


class TestSchedulerConstruction:
    """The scheduler is built once and injected into every collector."""

    def test_scheduler_constructed(self) -> None:
        """CollectorManager owns an EndpointScheduler after construction."""
        manager = _bare_manager(_settings())
        assert isinstance(manager.scheduler, EndpointScheduler)

    def test_scheduler_uses_manager_rate_limiter(self) -> None:
        """The scheduler reads the AIMD budget from the manager's own limiter."""
        manager = _bare_manager(_settings())
        assert manager.scheduler._rate_limiter is manager.rate_limiter

    def test_scheduler_injected_into_every_collector(self) -> None:
        """Every successfully-initialized collector receives the shared scheduler."""
        manager = _real_manager(_settings())
        all_collectors = [c for tier in manager.collectors.values() for c in tier]
        assert all_collectors, "expected real collectors to be initialized"
        for collector in all_collectors:
            assert collector.scheduler is manager.scheduler


# ---------------------------------------------------------------------------
# register_groups funnel
# ---------------------------------------------------------------------------


class TestRegisterEndpointGroups:
    """`_register_endpoint_groups` funnels collector groups into the scheduler."""

    def test_register_groups_called_on_construction(self) -> None:
        """register_groups runs exactly once during __init__ (empty is fine)."""
        with patch.object(EndpointScheduler, "register_groups") as mock_register:
            _real_manager(_settings())
        assert mock_register.call_count == 1

    def test_register_groups_funnels_collector_groups(self) -> None:
        """Groups declared by collectors become resolvable in the scheduler."""
        manager = _bare_manager(_settings())
        g1 = _group(EndpointGroupName.CONFIG_ORG, priority=4, floor=900)
        g2 = _group(EndpointGroupName.MX_UPLINK_STATUS, priority=1, floor=300)
        manager.collectors[UpdateTier.MEDIUM] = [_fake_collector("FooCollector", (g1, g2))]

        manager._register_endpoint_groups()

        # Both groups are now registered and resolvable to their floor cadence.
        assert manager.scheduler.interval_for(EndpointGroupName.CONFIG_ORG) == 900.0
        assert manager.scheduler.interval_for(EndpointGroupName.MX_UPLINK_STATUS) == 300.0


# ---------------------------------------------------------------------------
# collect_initial: resolve + startup log line
# ---------------------------------------------------------------------------


class TestCollectInitialResolve:
    """collect_initial resolves from the org shape and logs the startup summary."""

    @pytest.mark.asyncio
    async def test_resolve_and_log_reads_shape_and_resolves(self) -> None:
        """The helper fetches the org shape, resolves, and emits an INFO line."""
        manager = _bare_manager(_settings())
        shape = _make_shape()
        manager.inventory = MagicMock()
        manager.inventory.get_org_shape = AsyncMock(return_value=shape)

        with (
            patch.object(manager.scheduler, "resolve") as mock_resolve,
            patch("meraki_dashboard_exporter.collectors.manager.logger") as mock_logger,
        ):
            await manager._resolve_and_log_schedule()

        manager.inventory.get_org_shape.assert_awaited_once_with("123456")
        mock_resolve.assert_called_once_with(shape)
        assert mock_logger.info.called

    @pytest.mark.asyncio
    async def test_resolve_swallows_shape_errors(self) -> None:
        """A shape/resolve failure is logged and swallowed so startup continues."""
        manager = _bare_manager(_settings())
        manager.inventory = MagicMock()
        manager.inventory.get_org_shape = AsyncMock(side_effect=RuntimeError("boom"))
        await manager._resolve_and_log_schedule()

    @pytest.mark.asyncio
    async def test_collect_initial_calls_resolve_after_warm(self) -> None:
        """collect_initial resolves the schedule only after warming the cache."""
        manager = _bare_manager(_settings())
        manager.inventory = MagicMock()
        manager.inventory.warm_cache = AsyncMock()

        order: list[str] = []
        manager.inventory.warm_cache.side_effect = lambda: order.append("warm")

        async def _resolve() -> None:
            order.append("resolve")

        with patch.object(manager, "_resolve_and_log_schedule", side_effect=_resolve) as mock_res:
            await manager.collect_initial()

        mock_res.assert_awaited_once()
        assert order == ["warm", "resolve"]

    @pytest.mark.asyncio
    async def test_over_budget_logs_warning_naming_low_priority_collectors(self) -> None:
        """Over-budget resolve warns and names the priority-3/4 collectors to disable."""
        manager = _bare_manager(_settings())
        shape = _make_shape()
        manager.inventory = MagicMock()
        manager.inventory.get_org_shape = AsyncMock(return_value=shape)

        # A priority-3 collector (should be named) and a priority-1 collector (not).
        g_low = _group(EndpointGroupName.MS_PORT_STATUS, priority=3, floor=300)
        g_high = _group(EndpointGroupName.MX_UPLINK_STATUS, priority=1, floor=300)
        manager.collectors[UpdateTier.MEDIUM] = [
            _fake_collector("MSCollector", (g_low,)),
            _fake_collector("MXCollector", (g_high,)),
        ]

        over = {
            "total_demand_rps": 99.0,
            "budget_rps": 8.0,
            "target_utilization": 0.7,
            "over_budget": True,
            "groups": [],
        }
        with (
            patch.object(manager.scheduler, "resolve"),
            patch.object(manager.scheduler, "diagnostics", return_value=over),
            patch("meraki_dashboard_exporter.collectors.manager.logger") as mock_logger,
        ):
            await manager._resolve_and_log_schedule()

        assert mock_logger.warning.called
        warn_kwargs = mock_logger.warning.call_args.kwargs
        assert warn_kwargs["collectors_to_disable"] == ["ms"]

    def test_priority_shed_collectors_selects_priority_3_and_4(self) -> None:
        """Only collectors owning gated priority-3/4 groups are shed candidates."""
        manager = _bare_manager(_settings())
        manager.collectors[UpdateTier.MEDIUM] = [
            _fake_collector("MSCollector", (_group(EndpointGroupName.MS_PORT_STATUS, 3, 300),)),
            _fake_collector("ConfigCollector", (_group(EndpointGroupName.CONFIG_ORG, 4, 900),)),
            _fake_collector("MXCollector", (_group(EndpointGroupName.MX_UPLINK_STATUS, 1, 300),)),
        ]
        assert manager._priority_shed_collectors() == ["config", "ms"]

    def test_priority_shed_ignores_ungated_groups(self) -> None:
        """Ungated (demand-accounting-only) groups never nominate their collector."""
        manager = _bare_manager(_settings())
        manager.collectors[UpdateTier.MEDIUM] = [
            _fake_collector(
                "InvCollector",
                (_group(EndpointGroupName.INVENTORY_WARM, 4, 900, gated=False),),
            ),
        ]
        assert manager._priority_shed_collectors() == []


# ---------------------------------------------------------------------------
# diagnostics
# ---------------------------------------------------------------------------


class TestSchedulingDiagnostics:
    """get_scheduling_diagnostics surfaces the scheduler and retires the old block."""

    def test_diagnostics_includes_scheduler_section(self) -> None:
        """The diagnostics dict carries the scheduler diagnostics under 'scheduler'."""
        manager = _bare_manager(_settings())
        diag = manager.get_scheduling_diagnostics()
        assert "scheduler" in diag
        assert diag["scheduler"] == manager.scheduler.diagnostics()

    def test_diagnostics_retires_endpoint_intervals_block(self) -> None:
        """The legacy 'endpoint_intervals' block is removed (retired into scheduler)."""
        manager = _bare_manager(_settings())
        diag = manager.get_scheduling_diagnostics()
        assert "endpoint_intervals" not in diag

    def test_scheduler_diagnostics_has_expected_keys(self) -> None:
        """The scheduler section exposes the frozen §3 diagnostics keys."""
        manager = _bare_manager(_settings())
        sched = manager.get_scheduling_diagnostics()["scheduler"]
        for key in (
            "mode",
            "org_shape",
            "budget_rps",
            "effective_budget_rps",
            "target_utilization",
            "over_budget",
            "total_demand_rps",
            "groups",
        ):
            assert key in sched
