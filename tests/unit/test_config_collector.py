"""Tests for ConfigCollector _collect_impl concurrency and response validation.

Covers F-016 (bounded per-org concurrency instead of raw asyncio.gather) and
F-034 (login-security / configuration-changes fetchers reject the SDK
exhausted-retry error shape instead of emitting false zeros).
"""

from __future__ import annotations

import asyncio

import pytest

from meraki_dashboard_exporter.collectors.config import ConfigCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import OrganizationFactory


class TestConfigCollectorConcurrency(BaseCollectorTest):
    """F-016: per-org config collection must be bounded, not unbounded gather."""

    collector_class = ConfigCollector
    update_tier = UpdateTier.SLOW

    async def test_org_collection_is_concurrency_bounded(
        self, collector, mock_api_builder, metrics
    ):
        """No more than concurrency_limit orgs are processed at once (F-016)."""
        collector.settings.api.concurrency_limit = 2

        orgs = [OrganizationFactory.create(org_id=str(i), name=f"Org {i}") for i in range(6)]
        api = mock_api_builder.with_organizations(orgs).build()
        collector.api = api

        active = 0
        max_active = 0

        async def fake_collect(org: dict) -> None:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1

        collector._collect_org_config = fake_collect  # type: ignore[method-assign]

        await self.run_collector(collector)

        assert max_active <= 2
        assert max_active > 1  # actually ran concurrently within the bound

    async def test_per_org_errors_are_isolated(self, collector, mock_api_builder, metrics):
        """One org raising does not abort collection of the others (F-016)."""
        orgs = [OrganizationFactory.create(org_id=str(i), name=f"Org {i}") for i in range(4)]
        api = mock_api_builder.with_organizations(orgs).build()
        collector.api = api

        processed: list[str] = []

        async def fake_collect(org: dict) -> None:
            if org["id"] == "1":
                raise RuntimeError("boom")
            processed.append(org["id"])

        collector._collect_org_config = fake_collect  # type: ignore[method-assign]

        # Should not raise despite one org failing.
        await self.run_collector(collector)

        assert set(processed) == {"0", "2", "3"}


class TestConfigCollectorResponseValidation(BaseCollectorTest):
    """F-034: error-shaped dict responses must raise, not emit false zeros."""

    collector_class = ConfigCollector
    update_tier = UpdateTier.SLOW

    async def test_login_security_error_shape_does_not_emit_zeros(
        self, collector, mock_api_builder, metrics
    ):
        """An error-shaped login-security response must not set false-zero gauges (F-034)."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response(
                "getOrganizationLoginSecurity",
                {"errors": ["Something went wrong after retries"]},
            )
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        # No login-security metric should have been emitted (would be false zeros).
        self.verify_no_metrics_set(
            metrics,
            ["meraki_org_login_security_two_factor_enabled"],
        )

    def test_error_shape_rejected_by_validator(self):
        """The error shape used by the config fetchers raises (F-034 contract)."""
        from meraki_dashboard_exporter.core.error_handling import (
            DataValidationError,
            validate_response_format,
        )

        with pytest.raises(DataValidationError):
            validate_response_format(
                {"errors": ["retries exhausted"]},
                expected_type=dict,
                operation="getOrganizationLoginSecurity",
            )

    async def test_configuration_changes_error_shape_does_not_emit_zero(
        self, collector, mock_api_builder, metrics
    ):
        """An error-shaped config-changes response must not emit a 0 change count (F-034)."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response(
                "getOrganizationConfigurationChanges",
                {"errors": ["retries exhausted"]},
            )
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        self.verify_no_metrics_set(metrics, ["meraki_org_configuration_changes_total"])

    async def test_configuration_changes_valid_empty_list_emits_zero(
        self, collector, mock_api_builder, metrics
    ):
        """A genuinely empty change list still emits 0 (regression guard for F-034)."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationConfigurationChanges", [])
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        metrics.assert_gauge_value(
            "meraki_org_configuration_changes_total",
            0,
            org_id="123",
            org_name="Test Org",
        )
