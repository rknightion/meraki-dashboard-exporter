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
from meraki_dashboard_exporter.core.error_handling import NothingCollectedError
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
            # Keep the other two sub-collections healthy so this is a partial
            # (1-of-3) sub-collection failure, not a total org failure (#509).
            .with_custom_response("getOrganizationAdmins", [])
            .with_custom_response("getOrganizationConfigurationChanges", [])
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
            # Keep the other two sub-collections healthy so this is a partial
            # (1-of-3) sub-collection failure, not a total org failure (#509).
            .with_custom_response("getOrganizationLoginSecurity", {})
            .with_custom_response("getOrganizationAdmins", [])
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        self.verify_no_metrics_set(metrics, ["meraki_org_configuration_changes_count"])

    async def test_configuration_changes_valid_empty_list_emits_zero(
        self, collector, mock_api_builder, metrics
    ):
        """A genuinely empty change list still emits 0 (regression guard for F-034)."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationConfigurationChanges", [])
            .with_custom_response("getOrganizationLoginSecurity", {})
            .with_custom_response("getOrganizationAdmins", [])
            .build()
        )
        collector.api = api

        await self.run_collector(collector)

        metrics.assert_gauge_value(
            "meraki_org_configuration_changes_count",
            0,
            org_id="123",
        )


class TestConfigCollectorNothingCollected(BaseCollectorTest):
    """#509: total collection failure must raise instead of being swallowed."""

    collector_class = ConfigCollector
    update_tier = UpdateTier.SLOW

    async def test_org_fetch_failure_raises(self, collector, mock_api_builder, metrics):
        """Org fetch itself failing must propagate out of _collect_impl (#509)."""
        api = mock_api_builder.with_error("getOrganizations", Exception("Connection error")).build()
        collector.api = api
        collector.inventory.api = api

        with pytest.raises(Exception, match="Connection error"):  # noqa: B017,PT011
            await collector.collect()

    async def test_all_orgs_failed_raises_nothing_collected(
        self, collector, mock_api_builder, metrics
    ):
        """All 3 config sub-collections erroring for the only org raises NothingCollectedError."""
        org = OrganizationFactory.create(org_id="123", name="Test Org")
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_error("getOrganizationLoginSecurity", Exception("Connection error"))
            .with_error("getOrganizationAdmins", Exception("Connection error"))
            .with_error("getOrganizationConfigurationChanges", Exception("Connection error"))
            .build()
        )
        collector.api = api
        collector.inventory.api = api

        with pytest.raises(NothingCollectedError):
            await collector.collect()

    async def test_partial_org_failure_does_not_raise(self, collector, mock_api_builder, metrics):
        """One org's total failure among several must not fail the whole cycle (#509)."""
        healthy_org = OrganizationFactory.create(org_id="0", name="Healthy Org")
        broken_org = OrganizationFactory.create(org_id="1", name="Broken Org")
        api = (
            mock_api_builder
            .with_organizations([healthy_org, broken_org])
            .with_custom_response("getOrganizationLoginSecurity", {}, org_id="0")
            .with_custom_response("getOrganizationAdmins", [], org_id="0")
            .with_custom_response("getOrganizationConfigurationChanges", [], org_id="0")
            .with_error("getOrganizationLoginSecurity", Exception("Connection error"), org_id="1")
            .with_error("getOrganizationAdmins", Exception("Connection error"), org_id="1")
            .with_error(
                "getOrganizationConfigurationChanges", Exception("Connection error"), org_id="1"
            )
            .build()
        )
        collector.api = api
        collector.inventory.api = api

        await collector.collect()

        metrics.assert_gauge_value(
            "meraki_org_configuration_changes_count",
            0,
            org_id="0",
        )

    async def test_empty_org_list_is_success(self, collector, mock_api_builder, metrics):
        """An empty org list is a legitimate no-op, not a failure (#509)."""
        api = mock_api_builder.with_organizations([]).build()
        collector.api = api
        collector.inventory.api = api

        await collector.collect()
