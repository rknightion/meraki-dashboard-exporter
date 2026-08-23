"""Contracts for explicit endpoint-group outcomes (#733)."""
# ruff: noqa: D103

from __future__ import annotations

from collections.abc import Mapping
from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.core.collector import EndpointGroupVerdict, MetricCollector
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest


class _VerdictCollector(MetricCollector):
    outcomes: Mapping[EndpointGroupName, EndpointGroupVerdict] = {}

    def _initialize_metrics(self) -> None:
        pass

    async def _collect_impl(self) -> None:
        for group, outcome in self.outcomes.items():
            if not self._should_run_group(group):
                continue
            if outcome is EndpointGroupVerdict.SUCCEEDED:
                self._mark_group_ran(group)
            elif outcome is EndpointGroupVerdict.NOT_APPLICABLE:
                self._mark_group_not_applicable(group)
            elif outcome is EndpointGroupVerdict.FAILED:
                self._mark_group_failed(group)


def _collector(
    settings: Settings,
    registry: CollectorRegistry,
    outcomes: Mapping[EndpointGroupName, EndpointGroupVerdict],
) -> tuple[_VerdictCollector, MagicMock]:
    scheduler = MagicMock()
    scheduler.profile_allows.return_value = True
    scheduler.is_shed.return_value = False
    scheduler.should_run.return_value = True
    collector = _VerdictCollector(
        api=MagicMock(),
        settings=settings,
        registry=registry,
        scheduler=scheduler,
    )
    collector.outcomes = outcomes
    return collector, scheduler


class TestEndpointGroupVerdicts(BaseCollectorTest):
    """Explicit outcomes preserve scheduler group failure accounting."""

    @pytest.mark.asyncio
    async def test_not_applicable_group_never_records_a_failure(
        self, settings: Settings, isolated_registry: CollectorRegistry
    ) -> None:
        """An empty applicable scope closes without a failed endpoint attempt."""
        collector, scheduler = _collector(
            settings,
            isolated_registry,
            {EndpointGroupName.CLIENTS_LIST: EndpointGroupVerdict.NOT_APPLICABLE},
        )

        await collector.collect()

        group = EndpointGroupName.CLIENTS_LIST
        assert collector._endpoint_group_verdicts == {group: EndpointGroupVerdict.NOT_APPLICABLE}
        scheduler.mark_failed.assert_not_called()
        scheduler.mark_ran.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_success_only_completes_the_successful_group(
        self, settings: Settings, isolated_registry: CollectorRegistry
    ) -> None:
        """One successful group can coexist with an inapplicable sibling."""
        collector, scheduler = _collector(
            settings,
            isolated_registry,
            {
                EndpointGroupName.CLIENTS_LIST: EndpointGroupVerdict.SUCCEEDED,
                EndpointGroupName.CLIENTS_APP_USAGE: EndpointGroupVerdict.NOT_APPLICABLE,
            },
        )

        await collector.collect()

        group = EndpointGroupName.CLIENTS_LIST
        assert collector._endpoint_group_verdicts == {
            group: EndpointGroupVerdict.SUCCEEDED,
            EndpointGroupName.CLIENTS_APP_USAGE: EndpointGroupVerdict.NOT_APPLICABLE,
        }
        scheduler.mark_ran.assert_called_once_with(group)
        scheduler.mark_failed.assert_not_called()

    @pytest.mark.asyncio
    async def test_swallowed_group_failure_is_recorded_once(
        self, settings: Settings, isolated_registry: CollectorRegistry
    ) -> None:
        """A legacy tolerated failure keeps the prior one-failure accounting."""
        collector, scheduler = _collector(
            settings,
            isolated_registry,
            {EndpointGroupName.CLIENTS_LIST: EndpointGroupVerdict.ATTEMPTED},
        )

        await collector.collect()

        group = EndpointGroupName.CLIENTS_LIST
        assert collector._endpoint_group_verdicts == {group: EndpointGroupVerdict.FAILED}
        scheduler.mark_failed.assert_called_once_with(group)
