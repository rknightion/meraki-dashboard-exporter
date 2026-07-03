"""Tests for InsightCollector - Meraki Insight application health (#613)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from meraki_dashboard_exporter.collectors.insight import (
    _MAX_INSIGHT_APPS,  # noqa: PLC2701 - test asserts the cap value directly
    InsightCollector,
)
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.error_handling import (
    DataValidationError,
    validate_response_format,
)
from meraki_dashboard_exporter.core.scheduler import EndpointGroupName
from tests.helpers.base import BaseCollectorTest


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    collect_insight: bool = True,
    app_health: bool = True,
) -> Settings:
    """Build Settings with the Insight flags set via env."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    monkeypatch.setenv(
        "MERAKI_EXPORTER_COLLECTORS__COLLECT_INSIGHT",
        "true" if collect_insight else "false",
    )
    monkeypatch.setenv(
        "MERAKI_EXPORTER_COLLECTORS__INSIGHT_APP_HEALTH_ENABLED",
        "true" if app_health else "false",
    )
    return Settings()


def _app(app_id: str, name: str | None = None) -> dict:
    return {"applicationId": app_id, "name": name or f"App {app_id}"}


_FULL_BUCKET = {
    "startTs": "2026-07-03T00:00:00Z",
    "endTs": "2026-07-03T00:05:00Z",
    "wanLatencyMs": 50,
    "lanLatencyMs": 10,
    "wanLossPercent": 1.5,
    "lanLossPercent": 0.5,
    "responseDuration": 200,  # ms
    "sent": 100,  # KB/s
    "recv": 250,  # KB/s
    "numClients": 7,
    "wanGoodput": 999,  # excluded
    "lanGoodput": 888,  # excluded
}

_EMPTY_BUCKET = {
    "startTs": "2026-07-03T00:05:00Z",
    "endTs": "2026-07-03T00:10:00Z",
    "wanLatencyMs": None,
    "lanLatencyMs": None,
    "wanLossPercent": None,
    "lanLossPercent": None,
    "responseDuration": None,
    "sent": None,
    "recv": None,
    "numClients": None,
}


class TestInsightCollectorRegistration(BaseCollectorTest):
    """Registration / tier / config-gating of endpoint groups."""

    collector_class = InsightCollector

    def test_short_name_is_insight(self) -> None:
        """The manager short-name resolves to 'insight'."""
        short = InsightCollector.__name__.replace("Collector", "").lower()
        assert short == "insight"

    def test_groups_empty_when_disabled(
        self, mock_api, isolated_registry, inventory, monkeypatch
    ) -> None:
        """No endpoint groups enter the solver when collect_insight is off."""
        settings = _settings(monkeypatch, collect_insight=False)
        collector = InsightCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
        )
        assert collector.get_endpoint_groups() == ()
        assert collector.is_active is False

    def test_groups_drop_app_health_when_health_disabled(
        self, mock_api, isolated_registry, inventory, monkeypatch
    ) -> None:
        """The app-health group is dropped when insight_app_health_enabled is off."""
        settings = _settings(monkeypatch, collect_insight=True, app_health=False)
        collector = InsightCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
        )
        names = {g.name for g in collector.get_endpoint_groups()}
        assert names == {EndpointGroupName.INSIGHT_APPLICATIONS}

    def test_groups_include_both_when_enabled(
        self, mock_api, isolated_registry, inventory, monkeypatch
    ) -> None:
        """Both groups are active when fully enabled."""
        settings = _settings(monkeypatch, collect_insight=True, app_health=True)
        collector = InsightCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
        )
        names = {g.name for g in collector.get_endpoint_groups()}
        assert names == {
            EndpointGroupName.INSIGHT_APPLICATIONS,
            EndpointGroupName.INSIGHT_APP_HEALTH,
        }


class TestInsightCollectorBehaviour(BaseCollectorTest):
    """End-to-end collection behaviour with a mocked Insight API."""

    collector_class = InsightCollector

    def _build(
        self,
        mock_api,
        isolated_registry,
        inventory,
        settings: Settings,
        *,
        apps: list[dict] | Exception | None,
        health: list[dict] | Exception | None,
        networks: list[dict] | None = None,
    ) -> InsightCollector:
        collector = InsightCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
        )
        collector.inventory.get_organizations = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"id": "O1", "name": "Org One"}]
        )
        collector.inventory.get_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=networks if networks is not None else [{"id": "N1", "name": "Net One"}]
        )
        apps_mock = (
            MagicMock(side_effect=apps)
            if isinstance(apps, Exception)
            else MagicMock(return_value=apps)
        )
        health_mock = (
            MagicMock(side_effect=health)
            if isinstance(health, Exception)
            else MagicMock(return_value=health)
        )
        collector.api.insight.getOrganizationInsightApplications = apps_mock
        collector.api.insight.getNetworkInsightApplicationHealthByTime = health_mock
        return collector

    async def test_disabled_makes_no_api_calls(
        self, mock_api, isolated_registry, inventory, monkeypatch, metrics
    ) -> None:
        """A disabled collector short-circuits before any Insight API call."""
        settings = _settings(monkeypatch, collect_insight=False)
        collector = self._build(
            mock_api, isolated_registry, inventory, settings, apps=[_app("a")], health=[]
        )
        await collector._collect_impl()
        assert collector.api.insight.getOrganizationInsightApplications.call_count == 0
        metrics.assert_metric_not_set("meraki_insight_applications", org_id="O1")

    async def test_applications_count_and_info_emitted(
        self, mock_api, isolated_registry, inventory, monkeypatch, metrics
    ) -> None:
        """The count gauge and per-app info join carrier are emitted."""
        settings = _settings(monkeypatch)
        collector = self._build(
            mock_api,
            isolated_registry,
            inventory,
            settings,
            apps=[_app("webex", "Webex"), _app("zoom", "Zoom")],
            health=[_FULL_BUCKET],
        )
        await collector._collect_impl()

        metrics.assert_gauge_value("meraki_insight_applications", 2, org_id="O1")
        metrics.assert_gauge_value(
            "meraki_insight_application_info",
            1,
            org_id="O1",
            application_id="webex",
            name="Webex",
        )

    async def test_health_series_conversions(
        self, mock_api, isolated_registry, inventory, monkeypatch, metrics
    ) -> None:
        """Health-bucket values are converted to the correct units."""
        settings = _settings(monkeypatch)
        collector = self._build(
            mock_api,
            isolated_registry,
            inventory,
            settings,
            apps=[_app("webex", "Webex")],
            health=[_FULL_BUCKET],
        )
        await collector._collect_impl()

        common = {"org_id": "O1", "network_id": "N1", "application_id": "webex"}
        metrics.assert_gauge_value("meraki_insight_application_wan_latency_seconds", 0.05, **common)
        metrics.assert_gauge_value("meraki_insight_application_lan_latency_seconds", 0.01, **common)
        metrics.assert_gauge_value("meraki_insight_application_wan_loss_percent", 1.5, **common)
        metrics.assert_gauge_value("meraki_insight_application_lan_loss_percent", 0.5, **common)
        metrics.assert_gauge_value(
            "meraki_insight_application_response_duration_seconds", 0.2, **common
        )
        metrics.assert_gauge_value(
            "meraki_insight_application_sent_bytes_per_second", 100000, **common
        )
        metrics.assert_gauge_value(
            "meraki_insight_application_recv_bytes_per_second", 250000, **common
        )
        metrics.assert_gauge_value("meraki_insight_application_clients_count", 7, **common)

    async def test_goodput_not_emitted(self, isolated_registry) -> None:
        """No goodput metric family is ever created."""
        names = set(isolated_registry._names_to_collectors)
        assert not any("goodput" in n for n in names)

    async def test_newest_complete_bucket_skips_trailing_empty(
        self, mock_api, isolated_registry, inventory, monkeypatch, metrics
    ) -> None:
        """A trailing all-null bucket is skipped in favour of the newest with data."""
        settings = _settings(monkeypatch)
        collector = self._build(
            mock_api,
            isolated_registry,
            inventory,
            settings,
            apps=[_app("webex")],
            health=[_FULL_BUCKET, _EMPTY_BUCKET],
        )
        await collector._collect_impl()
        # The trailing empty bucket must be skipped; values come from _FULL_BUCKET.
        metrics.assert_gauge_value(
            "meraki_insight_application_wan_latency_seconds",
            0.05,
            org_id="O1",
            network_id="N1",
            application_id="webex",
        )

    async def test_all_empty_buckets_emit_nothing(
        self, mock_api, isolated_registry, inventory, monkeypatch, metrics
    ) -> None:
        """When every bucket is empty, no health series is emitted."""
        settings = _settings(monkeypatch)
        collector = self._build(
            mock_api,
            isolated_registry,
            inventory,
            settings,
            apps=[_app("webex")],
            health=[_EMPTY_BUCKET],
        )
        await collector._collect_impl()
        metrics.assert_metric_not_set(
            "meraki_insight_application_wan_latency_seconds",
            org_id="O1",
            network_id="N1",
            application_id="webex",
        )

    async def test_app_cap_enforced(
        self, mock_api, isolated_registry, inventory, monkeypatch, metrics
    ) -> None:
        """Applications are capped at _MAX_INSIGHT_APPS; the count stays truthful."""
        settings = _settings(monkeypatch, app_health=False)
        many = [_app(f"app{i:02d}") for i in range(_MAX_INSIGHT_APPS + 5)]
        collector = self._build(
            mock_api, isolated_registry, inventory, settings, apps=many, health=[]
        )
        await collector._collect_impl()

        # True total on the count metric.
        metrics.assert_gauge_value(
            "meraki_insight_applications", float(_MAX_INSIGHT_APPS + 5), org_id="O1"
        )
        # First (sorted) app kept; an over-cap app dropped from the info carrier.
        metrics.assert_gauge_value(
            "meraki_insight_application_info",
            1,
            org_id="O1",
            application_id="app00",
            name="App app00",
        )
        metrics.assert_metric_not_set(
            "meraki_insight_application_info",
            org_id="O1",
            application_id=f"app{_MAX_INSIGHT_APPS + 4:02d}",
            name=f"App app{_MAX_INSIGHT_APPS + 4:02d}",
        )

    async def test_app_health_disabled_skips_health_calls(
        self, mock_api, isolated_registry, inventory, monkeypatch, metrics
    ) -> None:
        """With app-health disabled, only the applications call runs."""
        settings = _settings(monkeypatch, app_health=False)
        collector = self._build(
            mock_api,
            isolated_registry,
            inventory,
            settings,
            apps=[_app("webex")],
            health=[_FULL_BUCKET],
        )
        await collector._collect_impl()
        assert collector.api.insight.getNetworkInsightApplicationHealthByTime.call_count == 0
        metrics.assert_gauge_value("meraki_insight_applications", 1, org_id="O1")

    async def test_license_absent_404_is_debug_skip(
        self, mock_api, isolated_registry, inventory, monkeypatch, metrics
    ) -> None:
        """A 404 from the applications endpoint is a debug-skip, not a failure."""
        settings = _settings(monkeypatch)
        collector = self._build(
            mock_api,
            isolated_registry,
            inventory,
            settings,
            apps=Exception("HTTP 404 not found"),
            health=[],
        )
        # Must not raise; no metrics emitted.
        await collector._collect_impl()
        metrics.assert_metric_not_set("meraki_insight_applications", org_id="O1")

    async def test_license_absent_400_is_debug_skip(
        self, mock_api, isolated_registry, inventory, monkeypatch, metrics
    ) -> None:
        """A 400 from the applications endpoint is a debug-skip, not a failure."""
        settings = _settings(monkeypatch)
        collector = self._build(
            mock_api,
            isolated_registry,
            inventory,
            settings,
            apps=Exception("400 Bad Request"),
            health=[],
        )
        await collector._collect_impl()
        metrics.assert_metric_not_set("meraki_insight_applications", org_id="O1")

    async def test_error_shaped_applications_response_emits_nothing(
        self, mock_api, isolated_registry, inventory, monkeypatch, metrics
    ) -> None:
        """An SDK exhausted-retry error shape is swallowed, not crashed."""
        settings = _settings(monkeypatch)
        collector = self._build(
            mock_api,
            isolated_registry,
            inventory,
            settings,
            apps={"errors": ["Something broke"]},
            health=[],
        )
        await collector._collect_impl()
        metrics.assert_metric_not_set("meraki_insight_applications", org_id="O1")


def test_validate_response_format_raises_on_error_shape() -> None:
    """validate_response_format rejects the SDK exhausted-retry error shape."""
    with pytest.raises(DataValidationError):
        validate_response_format(
            {"errors": ["boom"]},
            expected_type=list,
            operation="getOrganizationInsightApplications",
        )
