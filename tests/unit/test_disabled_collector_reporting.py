"""A collector switched off by its own flag must report as disabled (MDE-0067).

`collectors.active_collectors` and the per-collector `collect_*` flags are two
different switches. Only the first fed `skipped_collectors`, so a collector that
an operator had explicitly turned off through its own flag was still counted as
enabled, listed in the startup summary, given a cadence and handed a loop task —
while `is_active` (already honoured by the web UI and the control API) said
otherwise. The runtime was correct and the reporting was not, which is the same
shape as MDE-0065/MDE-0066: a top-level surface contradicting its internals.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from meraki_dashboard_exporter.app import ExporterApp
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import MerakiSettings

INSIGHT = "InsightCollector"


def _settings(*, collect_insight: bool) -> Settings:
    """Settings whose only interesting axis is the Insight collector's own flag."""
    settings = Settings(
        meraki=MerakiSettings(
            api_key=SecretStr("test_api_key_at_least_30_characters_long"),
            org_id="123456",
        ),
    )
    settings.collectors.collect_insight = collect_insight
    return settings


def _manager(*, collect_insight: bool) -> Any:
    """A real CollectorManager with real collectors, built off the app graph."""
    return ExporterApp(_settings(collect_insight=collect_insight)).collector_manager


def _names(collectors: Any) -> list[str]:
    return [collector.__class__.__name__ for collector in collectors]


class TestDisabledCollectorReporting:
    """The flag-disabled collector is reported as skipped, not as enabled."""

    def test_a_flag_disabled_collector_is_not_counted_as_active(self) -> None:
        """It must not appear in the list every summary and loop iterates."""
        manager = _manager(collect_insight=False)

        assert INSIGHT not in _names(manager.collectors)

    def test_a_flag_disabled_collector_is_reported_as_skipped_with_its_reason(self) -> None:
        """`skipped_collectors: 0` next to an explicit opt-out was the whole defect."""
        manager = _manager(collect_insight=False)

        skipped = {entry["name"]: entry["reason"] for entry in manager.skipped_collectors}
        assert INSIGHT in skipped
        assert "collect_insight" in skipped[INSIGHT]

    def test_a_flag_disabled_collector_stays_addressable_for_the_control_api(self) -> None:
        """The trigger endpoint must still answer "disabled", never "not found"."""
        manager = _manager(collect_insight=False)

        collector = manager.get_collector_by_name("insight")
        assert collector is not None
        assert collector.is_active is False

    def test_scheduling_diagnostics_omit_a_flag_disabled_collector(self) -> None:
        """A disabled collector printed a cadence it would never honour."""
        manager = _manager(collect_insight=False)

        diagnostics = manager.get_scheduling_diagnostics()
        assert INSIGHT not in [entry["collector"] for entry in diagnostics["collectors"]]

    def test_an_enabled_collector_is_untouched(self) -> None:
        """The control: turning the flag back on restores every surface."""
        manager = _manager(collect_insight=True)

        assert INSIGHT in _names(manager.collectors)
        assert INSIGHT not in [entry["name"] for entry in manager.skipped_collectors]


class TestStartupSummaryCollectorNames:
    """The summary reports what is running, not what the name list configured."""

    def test_the_summary_separates_active_from_flag_disabled_collectors(self) -> None:
        """`Enabled Collectors` read the raw name set, which cannot see a flag."""
        exporter = ExporterApp(_settings(collect_insight=False))

        with patch("meraki_dashboard_exporter.app.log_startup_summary") as summary:
            exporter._log_startup_summary()

        kwargs = summary.call_args.kwargs
        assert "insight" not in kwargs["active_collector_names"]
        assert "insight" in kwargs["disabled_collector_names"]


class TestDisabledCollectorLoops:
    """No background loop is started for a collector that will never collect."""

    @pytest.mark.asyncio
    async def test_no_loop_task_is_started_for_a_flag_disabled_collector(self) -> None:
        """A no-op loop woke on the collector's cadence forever."""
        exporter = ExporterApp(_settings(collect_insight=False))
        exporter.collector_manager.collect_initial = AsyncMock()  # type: ignore[method-assign]
        exporter._collector_loop = AsyncMock()  # type: ignore[method-assign]
        exporter._scheduler_resolve_loop = AsyncMock()  # type: ignore[method-assign]
        exporter._wait_for_first_collection = AsyncMock()  # type: ignore[method-assign]

        with patch(
            "meraki_dashboard_exporter.app.DiscoveryService",
            lambda api, settings, rate_limiter=None: SimpleNamespace(
                run_discovery=AsyncMock(return_value={"orgs": 1})
            ),
        ):
            await exporter._startup_collections()

        assert INSIGHT not in exporter._collector_tasks
        assert len(exporter._collector_tasks) == len(exporter.collector_manager.collectors)
