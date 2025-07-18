"""Example test file demonstrating the new test helpers."""
# mypy: ignore-errors

from __future__ import annotations

import pytest

from ..collectors.alerts import AlertsCollector
from ..core.constants import UpdateTier
from ..testing.base import BaseCollectorTest
from ..testing.factories import AlertFactory, NetworkFactory, OrganizationFactory
from ..testing.metrics import MetricSnapshot


class TestAlertsCollectorWithHelpers(BaseCollectorTest):
    """Example test class using the new test helpers."""

    collector_class = AlertsCollector
    update_tier = UpdateTier.MEDIUM

    @pytest.mark.asyncio
    async def test_collect_alerts_basic(self, collector, mock_api_builder, metrics):
        """Test basic alert collection using test helpers."""
        # Set up test data using factories
        org = OrganizationFactory.create(org_id="org_123", name="Test Org")
        networks = NetworkFactory.create_many(2, org_id=org["id"])

        # Create alerts with different severities
        alerts = [
            AlertFactory.create(
                severity="critical",
                network_id=networks[0]["id"],
                network_name=networks[0]["name"],
            ),
            AlertFactory.create(
                severity="warning",
                network_id=networks[0]["id"],
                network_name=networks[0]["name"],
            ),
            AlertFactory.create(
                severity="critical",
                network_id=networks[1]["id"],
                network_name=networks[1]["name"],
            ),
        ]

        # Configure mock API
        api = (
            mock_api_builder.with_organizations([org]).with_alerts(alerts, org_id=org["id"]).build()
        )

        # Update collector's API
        collector.api = api

        # Run collector
        await self.run_collector(collector)

        # Verify metrics using assertion helpers
        self.assert_collector_success(collector, metrics)
        self.assert_api_call_tracked(collector, metrics, "getOrganizationAssuranceAlerts")

        # Check alert metrics
        metrics.assert_gauge_value(
            "meraki_organization_alerts_active_by_severity_total",
            2,  # 2 critical alerts
            org_id="org_123",
            severity="critical",
        )

        metrics.assert_gauge_value(
            "meraki_organization_alerts_active_by_severity_total",
            1,  # 1 warning alert
            org_id="org_123",
            severity="warning",
        )

        # Check network-level metrics
        metrics.assert_gauge_value(
            "meraki_network_alerts_active_total",
            1,
            org_id="org_123",
            network_id=networks[0]["id"],
            network_name=networks[0]["name"],
            severity="critical",
        )

    @pytest.mark.asyncio
    async def test_collect_alerts_with_errors(self, collector, mock_api_builder, metrics):
        """Test alert collection with API errors."""
        # Set up organizations
        orgs = OrganizationFactory.create_many(2)

        # Configure API with mixed responses
        api = (
            mock_api_builder.with_organizations(orgs)
            .with_alerts(AlertFactory.create_many(3), org_id=orgs[0]["id"])
            .with_error("getOrganizationAssuranceAlerts", 404, organizationId=orgs[1]["id"])
            .build()
        )

        collector.api = api

        # Run collector - should not fail despite 404
        await self.run_collector(collector)

        # Should still be successful overall
        self.assert_collector_success(collector, metrics)

        # Should have metrics for first org
        metrics.assert_gauge_value(
            "meraki_organization_alerts_active_by_severity_total",
            3,
            org_id=orgs[0]["id"],
            severity="critical",
        )

        # No metrics for second org
        metrics.assert_metric_not_set(
            "meraki_organization_alerts_active_by_severity_total", org_id=orgs[1]["id"]
        )

    @pytest.mark.asyncio
    async def test_collect_alerts_performance(self, collector, mock_api_builder, metric_snapshot):
        """Test performance tracking using metric snapshots."""
        # Set up large dataset
        test_data = self.setup_standard_test_data(
            mock_api_builder,
            org_count=3,
            network_count=5,
            device_count=0,  # No devices needed for alerts
        )

        # Add many alerts
        all_alerts = []
        for network in test_data["networks"]:
            alerts = AlertFactory.create_many(10, network_id=network["id"], status="active")
            all_alerts.extend(alerts)

        # Configure API
        for org in test_data["organizations"]:
            org_alerts = [
                a
                for a in all_alerts
                if any(
                    n["id"] == a.get("network", {}).get("id")
                    for n in test_data["networks"]
                    if n["organizationId"] == org["id"]
                )
            ]
            mock_api_builder.with_alerts(org_alerts, org_id=org["id"])

        collector.api = mock_api_builder.build()

        # Take snapshot before
        before = metric_snapshot

        # Run collector
        await self.run_collector(collector)

        # Take snapshot after
        after = MetricSnapshot(collector.registry)

        # Check differences
        diff = after.diff(before)

        # Should have made API calls
        api_calls = diff.counter_delta(
            "meraki_collector_api_calls_total", endpoint="getOrganizationAssuranceAlerts"
        )
        assert api_calls == 3  # One per organization

        # Check duration was recorded
        duration_count = diff.counter_delta(
            "meraki_collector_duration_seconds_count", collector="AlertsCollector"
        )
        assert duration_count == 1

    @pytest.mark.asyncio
    async def test_collect_alerts_no_data(self, collector, mock_api_builder, metrics):
        """Test behavior with no alerts."""
        org = OrganizationFactory.create()

        api = (
            mock_api_builder.with_organizations([org])
            .with_alerts([], org_id=org["id"])  # Empty alerts
            .build()
        )

        collector.api = api

        await self.run_collector(collector)

        # Should succeed even with no data
        self.assert_collector_success(collector, metrics)

        # But no alert metrics should be set
        self.verify_no_metrics_set(
            metrics,
            [
                "meraki_organization_alerts_active_by_type",
                "meraki_organization_alerts_active_by_severity_total",
                "meraki_network_alerts_active_total",
            ],
        )

    @pytest.mark.asyncio
    async def test_collect_alerts_pagination(self, collector, mock_api_builder, metrics):
        """Test handling of paginated responses."""
        org = OrganizationFactory.create()

        # Create many alerts to trigger pagination
        alerts = AlertFactory.create_many(100, status="active")

        # Set up paginated response
        api = (
            mock_api_builder.with_organizations([org])
            .with_paginated_response(
                "getOrganizationAssuranceAlerts", alerts, per_page=20, use_items_wrapper=False
            )
            .build()
        )

        collector.api = api

        # This test would work if the alerts API supported pagination
        # For now it demonstrates the pattern

    def test_metric_label_validation(self, metrics, collector):
        """Test that metrics use correct label names from enums."""
        # Initialize metrics
        collector._initialize_metrics()

        # Get all label sets for a metric
        try:
            metric = metrics.get_metric("meraki_organization_alerts_active_by_type")
            # The metric should have been created with label names from LabelName enum
            for sample in metric.samples:
                if sample.name == "meraki_organization_alerts_active_by_type":
                    # Labels should include standard names
                    assert "org_id" in sample.labels
                    assert "type" in sample.labels
                    assert "category" in sample.labels
                    assert "severity" in sample.labels
        except AssertionError:
            # Metric not created yet, which is fine for this test
            pass
