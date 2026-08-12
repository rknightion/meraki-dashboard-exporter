"""Failure-domain backoff and entitlement outcomes are isolated (#704)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from meraki_dashboard_exporter.collectors.organization import OrganizationCollector
from meraki_dashboard_exporter.core.error_handling import ErrorCategory
from meraki_dashboard_exporter.core.org_health import (
    SOURCE_DEVICE,
    SOURCE_NETWORK_HEALTH,
    SOURCE_ORGANIZATION,
    OrgHealthTracker,
)


def test_backoff_suppresses_only_the_failing_domain() -> None:
    """A device-domain outage leaves the network-health domain collecting."""
    tracker = OrgHealthTracker(max_consecutive_failures=2)
    tracker.record_failure("org-1", "Org", source=SOURCE_DEVICE)
    tracker.record_failure("org-1", "Org", source=SOURCE_DEVICE)

    assert tracker.should_collect("org-1", source=SOURCE_DEVICE) is False
    assert tracker.should_collect("org-1", source=SOURCE_NETWORK_HEALTH) is True


def test_not_available_outcome_does_not_increment_a_failure_streak() -> None:
    """402/404 entitlement outcomes are permanent state, not health failures."""
    tracker = OrgHealthTracker(max_consecutive_failures=1)
    tracker.record_failure(
        "org-1",
        "Org",
        source=SOURCE_DEVICE,
        category=ErrorCategory.API_NOT_AVAILABLE,
    )

    health = tracker.get_health("org-1")
    assert health is not None
    assert health.source_failures.get(SOURCE_DEVICE, 0) == 0
    assert tracker.should_collect("org-1", source=SOURCE_DEVICE) is True


def test_auth_failure_suppresses_every_domain() -> None:
    """A 401/403 classification is organization-wide evidence."""
    tracker = OrgHealthTracker(max_consecutive_failures=1)
    tracker.record_failure(
        "org-1",
        "Org",
        source=SOURCE_DEVICE,
        category=ErrorCategory.API_AUTH_ERROR,
    )

    assert tracker.should_collect("org-1", source=SOURCE_DEVICE) is False
    assert tracker.should_collect("org-1", source=SOURCE_NETWORK_HEALTH) is False
    assert tracker.should_collect("org-1", source=SOURCE_ORGANIZATION) is False


def test_connectivity_failure_spanning_domains_suppresses_every_domain() -> None:
    """Two independently failing connectivity domains establish org-wide evidence."""
    tracker = OrgHealthTracker(max_consecutive_failures=2)
    for source in (SOURCE_DEVICE, SOURCE_NETWORK_HEALTH):
        tracker.record_failure("org-1", "Org", source=source, category=ErrorCategory.CONNECTIVITY)
        tracker.record_failure("org-1", "Org", source=source, category=ErrorCategory.CONNECTIVITY)

    assert tracker.should_collect("org-1", source=SOURCE_DEVICE) is False
    assert tracker.should_collect("org-1", source=SOURCE_NETWORK_HEALTH) is False
    assert tracker.should_collect("org-1", source=SOURCE_ORGANIZATION) is False


class _HTTPError(Exception):
    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"HTTP {status}")


@pytest.mark.asyncio
async def test_api_usage_auth_error_reaches_the_organization_coordinator() -> None:
    """A delegated 401 retains its category instead of becoming a False/unknown result."""
    collector = object.__new__(OrganizationCollector)
    attempted = [
        "_collect_api_metrics",
        "_collect_network_metrics",
        "_collect_device_metrics",
        "_collect_device_counts_by_model",
        "_collect_device_availability_metrics",
        "_collect_device_availability_changes_metrics",
        "_collect_firmware_metrics",
        "_collect_license_metrics",
        "_collect_client_overview",
        "_collect_packet_capture_metrics",
        "_collect_application_usage_metrics",
        "_collect_config_templates",
        "_collect_adaptive_policy",
        "_collect_top_usage_metrics",
        "_collect_webhook_logs_metrics",
        "_collect_firmware_compliance_metrics",
        "_collect_early_access_metrics",
    ]
    for name in attempted:
        setattr(collector, name, AsyncMock(return_value=True))
    collector._collect_api_metrics.side_effect = _HTTPError(401)
    collector._track_error = MagicMock()  # type: ignore[method-assign]

    failed, succeeded, categories = await collector._run_org_sub_collections("org-1", "Org")

    assert "api_metrics" in failed
    assert succeeded == len(attempted) - 1
    assert categories == [ErrorCategory.API_AUTH_ERROR]


@pytest.mark.asyncio
async def test_organization_coordinator_applies_auth_suppression_globally() -> None:
    """A classified delegated 401 reaches the real domain-backoff write path."""
    collector = object.__new__(OrganizationCollector)
    collector._org_info = None
    collector._org_collection_status = MagicMock()
    collector.org_health_tracker = OrgHealthTracker(max_consecutive_failures=1)
    collector._run_org_sub_collections = AsyncMock(  # type: ignore[method-assign]
        return_value=(["api_metrics"], 1, [ErrorCategory.API_AUTH_ERROR])
    )

    await collector._collect_org_metrics({"id": "org-1", "name": "Org"})

    assert collector.org_health_tracker.should_collect("org-1", source=SOURCE_DEVICE) is False
    assert (
        collector.org_health_tracker.should_collect("org-1", source=SOURCE_NETWORK_HEALTH) is False
    )


@pytest.mark.asyncio
async def test_organization_coordinator_does_not_streak_entitlement_outcomes() -> None:
    """A delegated synthetic 402 is an unavailable endpoint, not an org failure."""
    collector = object.__new__(OrganizationCollector)
    collector._org_info = None
    collector._org_collection_status = MagicMock()
    collector.org_health_tracker = OrgHealthTracker(max_consecutive_failures=1)
    collector._run_org_sub_collections = AsyncMock(  # type: ignore[method-assign]
        return_value=([], 0, [])
    )

    await collector._collect_org_metrics({"id": "org-1", "name": "Org"})

    health = collector.org_health_tracker.get_health("org-1")
    assert health is not None
    assert health.source_failures.get(SOURCE_ORGANIZATION, 0) == 0
    assert collector.org_health_tracker.should_collect("org-1", source=SOURCE_ORGANIZATION) is True
