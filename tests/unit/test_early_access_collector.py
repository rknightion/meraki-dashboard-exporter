"""Tests for the EarlyAccessCollector (#278, #279)."""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from meraki_dashboard_exporter.collectors.organization_collectors.early_access import (
    EarlyAccessCollector,
)

_METHOD = "getOrganizationEarlyAccessFeaturesOptIns"


class _MockParent:
    """Minimal parent recording metric values by (attr_name, sorted-labels)."""

    def __init__(self, api) -> None:
        self.api = api
        self.settings = None
        self._metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    def _track_api_call(self, method_name: str) -> None:
        pass

    def _set_metric_value(
        self,
        metric_name: str,
        labels: dict[str, str],
        value: float | None,
        ttl_seconds: float | None = None,
    ) -> None:
        if value is not None:
            key = (metric_name, tuple(sorted(labels.items())))
            self._metrics[key] = value


class TestEarlyAccessCollector:
    """Test EarlyAccessCollector functionality."""

    @pytest.fixture
    def mock_api_builder(self):
        """Create a mock API builder."""
        from tests.helpers.mock_api import MockAPIBuilder

        return MockAPIBuilder()

    def _collector(self, mock_api_builder) -> EarlyAccessCollector:
        parent = _MockParent(mock_api_builder.build())
        return EarlyAccessCollector(parent=parent)  # type: ignore[arg-type]

    async def test_info_series_and_scoped_networks_emitted(self, mock_api_builder):
        """Two opt-ins (incl. has_beta_api) emit info + scoped-network series."""
        org_id = "org1"
        opt_ins = [
            {
                "id": "opt_abc",
                "shortName": "has_beta_api",
                "longName": "Beta API spec",
                "createdAt": "2026-01-01T00:00:00Z",
                "limitScopeToNetworks": [],
            },
            {
                "id": "opt_def",
                "shortName": "wireless_health",
                "limitScopeToNetworks": [
                    {"id": "N_1", "name": "one"},
                    {"id": "N_2", "name": "two"},
                ],
            },
        ]
        api = mock_api_builder.with_custom_response(_METHOD, opt_ins).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        result = await collector.collect(org_id, "Org One")
        assert result is True

        m = collector.parent._metrics
        # Info carrier (value 1) per opt-in, keyed by feature + opt_in_id.
        assert (
            m[
                (
                    "_org_early_access_opt_in_info",
                    (("feature", "has_beta_api"), ("opt_in_id", "opt_abc"), ("org_id", org_id)),
                )
            ]
            == 1
        )
        assert (
            m[
                (
                    "_org_early_access_opt_in_info",
                    (("feature", "wireless_health"), ("opt_in_id", "opt_def"), ("org_id", org_id)),
                )
            ]
            == 1
        )
        # Scoped-network COUNT by feature (0 for org-wide, 2 for the scoped one).
        assert (
            m[
                (
                    "_org_early_access_opt_in_scoped_networks",
                    (("feature", "has_beta_api"), ("org_id", org_id)),
                )
            ]
            == 0
        )
        assert (
            m[
                (
                    "_org_early_access_opt_in_scoped_networks",
                    (("feature", "wireless_health"), ("org_id", org_id)),
                )
            ]
            == 2
        )

    async def test_has_beta_api_gauge_one_when_present(self, mock_api_builder):
        """ORG_HAS_BETA_API == 1 when a has_beta_api opt-in is present."""
        org_id = "org2"
        opt_ins = [{"id": "x", "shortName": "has_beta_api", "limitScopeToNetworks": []}]
        api = mock_api_builder.with_custom_response(_METHOD, opt_ins).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        await collector.collect(org_id, "Org Two")
        m = collector.parent._metrics
        assert m[("_org_has_beta_api", (("org_id", org_id),))] == 1

    async def test_has_beta_api_gauge_zero_when_absent(self, mock_api_builder):
        """ORG_HAS_BETA_API == 0 (emitted, not missing) when no beta opt-in."""
        org_id = "org3"
        opt_ins = [{"id": "y", "shortName": "wireless_health", "limitScopeToNetworks": []}]
        api = mock_api_builder.with_custom_response(_METHOD, opt_ins).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        await collector.collect(org_id, "Org Three")
        m = collector.parent._metrics
        assert m[("_org_has_beta_api", (("org_id", org_id),))] == 0

    async def test_has_beta_api_gauge_zero_for_empty_org(self, mock_api_builder):
        """No opt-ins at all still emits has_beta_api == 0."""
        org_id = "org4"
        api = mock_api_builder.with_custom_response(_METHOD, []).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        result = await collector.collect(org_id, "Org Four")
        assert result is True
        m = collector.parent._metrics
        assert m[("_org_has_beta_api", (("org_id", org_id),))] == 0

    async def test_warn_log_fires_when_beta_api_present(
        self, mock_api_builder, force_debug_log_capture
    ):
        """A WARN is emitted exactly when has_beta_api is present."""
        opt_ins = [{"id": "x", "shortName": "has_beta_api", "limitScopeToNetworks": []}]
        api = mock_api_builder.with_custom_response(_METHOD, opt_ins).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        with capture_logs() as caps:
            await collector.collect("org5", "Org Five")

        warns = [
            e
            for e in caps
            if e.get("log_level") == "warning" and "beta API spec" in e.get("event", "")
        ]
        assert len(warns) == 1
        assert warns[0]["org_id"] == "org5"
        assert warns[0]["org_name"] == "Org Five"

    async def test_no_warn_log_when_beta_api_absent(
        self, mock_api_builder, force_debug_log_capture
    ):
        """No WARN when there is no has_beta_api opt-in."""
        opt_ins = [{"id": "y", "shortName": "wireless_health", "limitScopeToNetworks": []}]
        api = mock_api_builder.with_custom_response(_METHOD, opt_ins).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        with capture_logs() as caps:
            await collector.collect("org6", "Org Six")

        warns = [e for e in caps if e.get("log_level") == "warning"]
        assert warns == []

    async def test_collect_swallows_404(self, mock_api_builder, force_debug_log_capture):
        """A 404 is swallowed by the collector: returns True, no metrics, no raise.

        The collector's own handling is a debug-level skip (the framework's
        ``@log_api_call`` decorator separately logs the raw API failure, as it
        does for every collector's 404 path — that is not the collector's doing).
        """
        api = mock_api_builder.with_error(_METHOD, Exception("404 Not Found")).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        with capture_logs() as caps:
            result = await collector.collect("org7", "Org Seven")
        assert result is True
        assert len(collector.parent._metrics) == 0
        # The collector's own skip is a debug event (it did not re-raise).
        skips = [
            e
            for e in caps
            if e.get("log_level") == "debug"
            and "not available for organization" in e.get("event", "")
        ]
        assert len(skips) == 1

    async def test_malformed_row_skipped_without_failing_run(self, mock_api_builder):
        """A malformed opt-in row is skipped; valid rows still emit; run succeeds."""
        org_id = "org8"
        opt_ins = [
            # Not a dict at all.
            "not-an-object",
            # limitScopeToNetworks is not a list -> ValidationError.
            {"id": "bad", "shortName": "broken", "limitScopeToNetworks": 123},
            # An opt-in with no shortName is skipped for the inventory series.
            {"id": "noname", "limitScopeToNetworks": []},
            # Valid, and the beta signal.
            {"id": "good", "shortName": "has_beta_api", "limitScopeToNetworks": []},
        ]
        api = mock_api_builder.with_custom_response(_METHOD, opt_ins).build()
        collector = self._collector(mock_api_builder)
        collector.api = api

        result = await collector.collect(org_id, "Org Eight")
        assert result is True

        m = collector.parent._metrics
        # The valid opt-in still emitted its info series.
        assert (
            m[
                (
                    "_org_early_access_opt_in_info",
                    (("feature", "has_beta_api"), ("opt_in_id", "good"), ("org_id", org_id)),
                )
            ]
            == 1
        )
        # The malformed rows produced no info series.
        info_features = {key[1][0][1] for key in m if key[0] == "_org_early_access_opt_in_info"}
        assert info_features == {"has_beta_api"}
        # has_beta_api still detected despite the malformed rows.
        assert m[("_org_has_beta_api", (("org_id", org_id),))] == 1
