"""Tests for the OrganizationCollector using test helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from meraki_dashboard_exporter.collectors.organization import OrganizationCollector
from meraki_dashboard_exporter.core.constants import (
    NetworkMetricName,
    OrgMetricName,
)
from meraki_dashboard_exporter.core.error_handling import NothingCollectedError
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import (
    NetworkFactory,
    OrganizationFactory,
)


class TestOrganizationCollector(BaseCollectorTest):
    """Test OrganizationCollector functionality."""

    collector_class = OrganizationCollector

    async def test_device_count_gauges_participate_in_expiration(
        self, mock_api, settings, isolated_registry, inventory
    ):
        """Org device-count gauges must participate in expiration tracking.

        They must route through _set_metric so stale label combinations
        (device_type / model / status+product_type) can be removed by the
        expiration manager instead of freezing forever.
        """
        from meraki_dashboard_exporter.core.metric_expiration import MetricExpirationManager

        manager = MetricExpirationManager(settings=settings)
        collector = OrganizationCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            expiration_manager=manager,
        )

        org_id, org_name = "999", "Expiry Org"

        # Devices-by-type
        async def _devices(_org_id: str):
            return [{"model": "MS210-8"}, {"model": "MR36"}, {"model": "MS120-8"}]

        collector.api_helper.get_organization_devices = _devices  # type: ignore[method-assign]
        await collector._collect_device_metrics(org_id, org_name)

        # Devices-by-model
        collector.api.organizations.getOrganizationDevicesOverviewByModel.return_value = {
            "counts": [{"model": "MR36", "total": 4}, {"model": "MS210-8", "total": 2}]
        }
        await collector._collect_device_counts_by_model(org_id, org_name)

        # Devices availability (via inventory)
        async def _avail(_org_id: str):
            return [
                {"status": "online", "productType": "wireless"},
                {"status": "offline", "productType": "switch"},
            ]

        collector.inventory.get_device_availabilities = _avail  # type: ignore[method-assign]
        await collector._collect_device_availability_metrics(org_id, org_name)

        # Every one of the three gauge families must now be tracked WITH a Gauge
        # reference so the expiration manager can actually remove stale series.
        tracked_metric_names = {key[1] for key in manager._metric_series}
        assert OrgMetricName.ORG_DEVICES.value in tracked_metric_names
        assert OrgMetricName.ORG_DEVICES_BY_MODEL.value in tracked_metric_names
        assert OrgMetricName.ORG_DEVICES_AVAILABILITY.value in tracked_metric_names

    async def test_collect_packet_capture_metrics(self, collector, mock_api_builder, metrics):
        """Test collection of packet capture metrics."""
        # Set up test data
        org = OrganizationFactory.create(org_id="123", name="Test Org")

        # Create packet capture response data
        packet_capture_response = {
            "items": [
                {
                    "captureId": "676102894059307468",
                    "network": {"id": "L_676102894059017611", "name": "Mitchell Drive"},
                    "devices": [{"name": "LoungeAP", "serial": "Q3AB-VDGT-R59K"}],
                    "status": "completed",
                    "startTs": "2025-07-21T17:56:12Z",
                    "duration": 60,
                    "counts": {"packets": {"total": 3}},
                },
                {
                    "captureId": "676102894059307406",
                    "network": {"id": "L_676102894059017611", "name": "Mitchell Drive"},
                    "devices": [{"name": "LoungeAP", "serial": "Q3AB-VDGT-R59K"}],
                    "status": "completed",
                    "startTs": "2025-07-21T17:03:23Z",
                    "duration": 60,
                    "counts": {"packets": {"total": 3}},
                },
                {
                    "captureId": "676102894059307405",
                    "network": {"id": "L_676102894059017611", "name": "Mitchell Drive"},
                    "devices": [{"name": "OfficeAP", "serial": "Q3AB-QLZS-GCWH"}],
                    "status": "completed",
                    "startTs": "2025-07-21T17:03:13Z",
                    "duration": 60,
                    "counts": {"packets": {"total": 3}},
                },
            ],
            "meta": {"counts": {"items": {"total": 266, "remaining": 263}}},
        }

        # Configure mock API with all necessary endpoints
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([NetworkFactory.create(org_id=org["id"])])
            .with_devices([])
            .with_custom_response("getOrganizationDevicesOverviewByModel", {"counts": []})
            .with_custom_response("getOrganizationDevicesAvailabilities", [])
            .with_custom_response(
                "getOrganizationLicensesOverview",
                {"expirationDate": "2026-01-01", "licenseTypes": []},
            )
            .with_custom_response("getOrganizationClientsOverview", [])
            .with_custom_response(
                "getOrganizationDevicesPacketCaptureCaptures", packet_capture_response
            )
            .build()
        )
        collector.api = api

        # Initialize API helper with the same API
        collector.api_helper.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify success
        self.assert_collector_success(collector, metrics)

        # Verify packet capture metrics
        metrics.assert_gauge_value(
            OrgMetricName.ORG_PACKETCAPTURES,
            266,
            org_id="123",
        )

        metrics.assert_gauge_value(
            OrgMetricName.ORG_PACKETCAPTURES_REMAINING,
            263,
            org_id="123",
        )

    async def test_packet_capture_metrics_with_no_captures(
        self, collector, mock_api_builder, metrics
    ):
        """Test packet capture metrics when no captures exist."""
        # Set up test data
        org = OrganizationFactory.create(org_id="456", name="Empty Org")

        # Create empty packet capture response
        packet_capture_response = {
            "items": [],
            "meta": {"counts": {"items": {"total": 0, "remaining": 0}}},
        }

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([])
            .with_devices([])
            .with_custom_response("getOrganizationDevicesOverviewByModel", {"counts": []})
            .with_custom_response("getOrganizationDevicesAvailabilities", [])
            .with_custom_response(
                "getOrganizationLicensesOverview",
                {"expirationDate": "2026-01-01", "licenseTypes": []},
            )
            .with_custom_response("getOrganizationClientsOverview", [])
            .with_custom_response(
                "getOrganizationDevicesPacketCaptureCaptures", packet_capture_response
            )
            .build()
        )
        collector.api = api
        collector.api_helper.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify packet capture metrics are set to 0
        metrics.assert_gauge_value(
            OrgMetricName.ORG_PACKETCAPTURES,
            0,
            org_id="456",
        )

        metrics.assert_gauge_value(
            OrgMetricName.ORG_PACKETCAPTURES_REMAINING,
            0,
            org_id="456",
        )

    async def test_packet_capture_metrics_with_api_error(
        self, collector, mock_api_builder, metrics
    ):
        """Test packet capture metrics handle API errors gracefully."""
        # Set up test data
        org = OrganizationFactory.create(org_id="789", name="Error Org")

        # Configure mock API with error for packet captures
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([])
            .with_devices([])
            .with_custom_response("getOrganizationDevicesOverviewByModel", {"counts": []})
            .with_custom_response("getOrganizationDevicesAvailabilities", [])
            .with_custom_response(
                "getOrganizationLicensesOverview",
                {"expirationDate": "2026-01-01", "licenseTypes": []},
            )
            .with_custom_response("getOrganizationClientsOverview", [])
            .with_error("getOrganizationDevicesPacketCaptureCaptures", Exception("API Error"))
            .build()
        )
        collector.api = api
        collector.api_helper.api = api

        # Run collection - should not raise exception
        await self.run_collector(collector)

        # Verify metrics are not set (due to error)
        metrics.assert_metric_not_set(
            OrgMetricName.ORG_PACKETCAPTURES,
            org_id="789",
        )

        metrics.assert_metric_not_set(
            OrgMetricName.ORG_PACKETCAPTURES_REMAINING,
            org_id="789",
        )

    async def test_packet_capture_metrics_with_unexpected_response(
        self, collector, mock_api_builder, metrics
    ):
        """Test packet capture metrics handle unexpected response format."""
        # Set up test data
        org = OrganizationFactory.create(org_id="999", name="Weird Org")

        # Create unexpected response format (missing meta)
        packet_capture_response = {
            "items": [{"captureId": "123", "status": "completed"}],
            # Missing "meta" section
        }

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([])
            .with_devices([])
            .with_custom_response("getOrganizationDevicesOverviewByModel", {"counts": []})
            .with_custom_response("getOrganizationDevicesAvailabilities", [])
            .with_custom_response(
                "getOrganizationLicensesOverview",
                {"expirationDate": "2026-01-01", "licenseTypes": []},
            )
            .with_custom_response("getOrganizationClientsOverview", [])
            .with_custom_response(
                "getOrganizationDevicesPacketCaptureCaptures", packet_capture_response
            )
            .build()
        )
        collector.api = api
        collector.api_helper.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify metrics are not set (due to unexpected format)
        metrics.assert_metric_not_set(
            OrgMetricName.ORG_PACKETCAPTURES,
            org_id="999",
        )

        metrics.assert_metric_not_set(
            OrgMetricName.ORG_PACKETCAPTURES_REMAINING,
            org_id="999",
        )

    async def test_collect_application_usage_metrics(self, collector, mock_api_builder, metrics):
        """Test collection of application usage metrics."""
        # Set up test data
        org = OrganizationFactory.create(org_id="111", name="App Usage Org")

        # Create application usage response data
        app_usage_response = [
            {
                "category": "Other",
                "total": 579131.5472021103,
                "downstream": 364303.2155036926,
                "upstream": 0,
                "percentage": 97.1055882261812,
            },
            {
                "category": "Music",
                "total": 7156.00084400177,
                "downstream": 118.2261791229248,
                "upstream": 0,
                "percentage": 1.1998788093326456,
            },
            {
                "category": "VoIP & video conferencing",
                "total": 2.367426872253418,
                "downstream": 0.6752958297729492,
                "upstream": 0.5,
                "percentage": 0.0003969570991656017,
            },
            {
                "category": "Software & anti-virus updates",
                "total": 33.518364906311035,
                "downstream": 1.7500495910644531,
                "upstream": 5.0,
                "percentage": 0.0056201748226836394,
            },
        ]

        # Configure mock API
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([])
            .with_devices([])
            .with_custom_response("getOrganizationDevicesOverviewByModel", {"counts": []})
            .with_custom_response("getOrganizationDevicesAvailabilities", [])
            .with_custom_response(
                "getOrganizationLicensesOverview",
                {"expirationDate": "2026-01-01", "licenseTypes": []},
            )
            .with_custom_response("getOrganizationClientsOverview", [])
            .with_custom_response(
                "getOrganizationDevicesPacketCaptureCaptures",
                {"items": [], "meta": {"counts": {"items": {"total": 0, "remaining": 0}}}},
            )
            .with_custom_response(
                "getOrganizationSummaryTopApplicationsCategoriesByUsage", app_usage_response
            )
            .build()
        )
        collector.api = api
        collector.api_helper.api = api

        # Run collection
        await self.run_collector(collector)

        # Verify application usage metrics for "Other" category
        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_BYTES,
            579131547202.1103,
            org_id="111",
            category="other",
        )

        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_DOWNSTREAM_BYTES,
            364303215503.6926,
            org_id="111",
            category="other",
        )

        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_PERCENT,
            97.1055882261812,
            org_id="111",
            category="other",
        )

        # Verify VoIP & video conferencing category (tests sanitization)
        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_BYTES,
            2367426.872253418,
            org_id="111",
            category="voip_and_video_conferencing",
        )

        # Verify upstream metric
        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_UPSTREAM_BYTES,
            500000.0,
            org_id="111",
            category="voip_and_video_conferencing",
        )

        # Verify Software & anti-virus updates (tests sanitization)
        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_BYTES,
            33518364.906311035,
            org_id="111",
            category="software_and_anti_virus_updates",
        )

    async def test_category_name_sanitization(self, collector):
        """Test sanitization of various category names."""
        test_cases = [
            ("Other", "other"),
            ("Music", "music"),
            ("VoIP & video conferencing", "voip_and_video_conferencing"),
            ("Software & anti-virus updates", "software_and_anti_virus_updates"),
            ("P2P", "p2p"),
            ("File sharing", "file_sharing"),
            ("Social web", "social_web"),
            ("Online backup", "online_backup"),
            ("Cloud services", "cloud_services"),
            ("Blogging", "blogging"),
            ("Photo sharing", "photo_sharing"),
            ("Web payments", "web_payments"),
            ("Web file sharing", "web_file_sharing"),
            ("Remote monitoring & management", "remote_monitoring_and_management"),
            ("News", "news"),
            ("Gaming", "gaming"),
            ("Email", "email"),
            ("Security", "security"),
            ("Productivity", "productivity"),
            ("Advertising", "advertising"),
            ("Video", "video"),
            # Test edge cases
            ("", "unknown"),
            (None, "unknown"),
            ("Test/Slash\\Back", "test_slash_back"),
            ("Dots.And.Commas,Here", "dotsandcommashere"),
            ("Special:Chars;Here", "specialcharshere"),
            ("Parentheses(and)Quotes'\"", "parenthesesandquotes"),
            ("Multiple   Spaces", "multiple_spaces"),
            ("--Leading-Dashes--", "leading_dashes"),
        ]

        for input_name, expected_output in test_cases:
            result = collector._sanitize_category_name(input_name or "")
            assert result == expected_output, f"Failed for input: {input_name}"

    async def test_application_usage_with_empty_response(
        self, collector, mock_api_builder, metrics
    ):
        """Test application usage metrics with empty response."""
        # Set up test data
        org = OrganizationFactory.create(org_id="222", name="Empty Usage Org")

        # Configure mock API with empty response
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([])
            .with_devices([])
            .with_custom_response("getOrganizationDevicesOverviewByModel", {"counts": []})
            .with_custom_response("getOrganizationDevicesAvailabilities", [])
            .with_custom_response(
                "getOrganizationLicensesOverview",
                {"expirationDate": "2026-01-01", "licenseTypes": []},
            )
            .with_custom_response("getOrganizationClientsOverview", [])
            .with_custom_response(
                "getOrganizationDevicesPacketCaptureCaptures",
                {"items": [], "meta": {"counts": {"items": {"total": 0, "remaining": 0}}}},
            )
            .with_custom_response("getOrganizationSummaryTopApplicationsCategoriesByUsage", [])
            .build()
        )
        collector.api = api
        collector.api_helper.api = api

        # Run collection
        await self.run_collector(collector)

        # No specific metrics to assert, just ensure it doesn't crash

    async def test_application_usage_with_api_error(self, collector, mock_api_builder, metrics):
        """Test application usage metrics handle API errors gracefully."""
        # Set up test data
        org = OrganizationFactory.create(org_id="333", name="Error App Usage Org")

        # Configure mock API with error
        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([])
            .with_devices([])
            .with_custom_response("getOrganizationDevicesOverviewByModel", {"counts": []})
            .with_custom_response("getOrganizationDevicesAvailabilities", [])
            .with_custom_response(
                "getOrganizationLicensesOverview",
                {"expirationDate": "2026-01-01", "licenseTypes": []},
            )
            .with_custom_response("getOrganizationClientsOverview", [])
            .with_custom_response(
                "getOrganizationDevicesPacketCaptureCaptures",
                {"items": [], "meta": {"counts": {"items": {"total": 0, "remaining": 0}}}},
            )
            .with_error(
                "getOrganizationSummaryTopApplicationsCategoriesByUsage", Exception("API Error")
            )
            .build()
        )
        collector.api = api
        collector.api_helper.api = api

        # Run collection - should not raise exception
        await self.run_collector(collector)

        # Verify metrics are not set
        metrics.assert_metric_not_set(
            OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_BYTES,
            org_id="333",
            category="other",
        )

    # -- F-040: unreachable org-failure path ---------------------------------

    async def test_org_metrics_records_failure_when_subcollections_fail(self, collector, metrics):
        """A fully-broken org must record failure and set status=0.

        Previously every sub-collection swallowed its own exceptions, so
        OrgHealthTracker.record_failure and the status gauge could never
        reflect an org whose API access is completely broken (bug-bash
        F-040).
        """
        org = OrganizationFactory.create(org_id="777", name="Broken Org")

        async def _boom(*_args: object, **_kwargs: object) -> None:
            raise Exception("500 Internal Server Error")

        collector._collect_network_metrics = _boom  # type: ignore[method-assign]
        collector._collect_device_metrics = _boom  # type: ignore[method-assign]
        collector._collect_device_counts_by_model = _boom  # type: ignore[method-assign]
        collector._collect_device_availability_metrics = _boom  # type: ignore[method-assign]
        collector._collect_packet_capture_metrics = _boom  # type: ignore[method-assign]
        collector._collect_application_usage_metrics = _boom  # type: ignore[method-assign]

        await collector._collect_org_metrics(org)

        health = collector.org_health_tracker.get_health(org["id"])
        assert health is not None
        assert health.consecutive_failures == 1

        metrics.assert_gauge_value(
            "meraki_exporter_org_collection_status",
            0,
            org_id=org["id"],
        )

    async def test_org_metrics_resilient_to_partial_subcollection_failure(self, collector, metrics):
        """One failing sub-collection must not prevent the others from running.

        Guards the resilience property F-040's fix must preserve: a single
        broken endpoint should not abort the rest of the org's collection.
        """
        org = OrganizationFactory.create(org_id="780", name="Partially Broken Org")

        async def _boom(*_args: object, **_kwargs: object) -> None:
            raise Exception("500 Internal Server Error")

        network_calls: list[str] = []

        async def _tracked_license(org_id: str, org_name: str) -> None:
            network_calls.append("license_metrics")

        collector._collect_network_metrics = _boom  # type: ignore[method-assign]
        collector._collect_license_metrics = _tracked_license  # type: ignore[method-assign]

        await collector._collect_org_metrics(org)

        assert "license_metrics" in network_calls

    async def test_partial_subcollection_failure_increments_error_counter(self, collector, metrics):
        """RES-04/#511: a tolerated sub-collection failure increments the error counter.

        `meraki_exporter_collector_errors_total` must increment so the failure
        is visible in metrics even though the org cycle itself still succeeds
        (F-040's resilience property is preserved - see the sibling test above).
        """
        org = OrganizationFactory.create(org_id="781", name="Partially Broken Org 2")

        async def _boom(*_args: object, **_kwargs: object) -> None:
            raise Exception("500 Internal Server Error")

        collector._collect_network_metrics = _boom  # type: ignore[method-assign]

        # Must not raise - only one of several sub-collections failed.
        await collector._collect_org_metrics(org)

        self.assert_collector_error(collector, metrics, error_type="unknown")

    async def test_org_metrics_backoff_engages_after_consecutive_failures(self, collector, metrics):
        """Persistent per-cycle failures must eventually engage backoff.

        should_collect becomes False after max_consecutive_failures cycles,
        matching the bug-bash F-040 suggested test.
        """
        org = OrganizationFactory.create(org_id="778", name="Persistently Broken Org")

        async def _boom(*_args: object, **_kwargs: object) -> None:
            raise Exception("500 Internal Server Error")

        collector._collect_network_metrics = _boom  # type: ignore[method-assign]
        collector._collect_device_metrics = _boom  # type: ignore[method-assign]
        collector._collect_device_counts_by_model = _boom  # type: ignore[method-assign]
        collector._collect_device_availability_metrics = _boom  # type: ignore[method-assign]
        collector._collect_packet_capture_metrics = _boom  # type: ignore[method-assign]
        collector._collect_application_usage_metrics = _boom  # type: ignore[method-assign]

        for _ in range(collector.org_health_tracker.max_consecutive_failures):
            await collector._collect_org_metrics(org)

        assert collector.org_health_tracker.should_collect(org["id"]) is False
        metrics.assert_gauge_value(
            "meraki_exporter_org_collection_status",
            0,
            org_id=org["id"],
        )

    async def test_org_metrics_404_not_counted_as_failure(
        self, collector, mock_api_builder, metrics
    ):
        """A 404 (endpoint not available for this org) must not count as a failure.

        Many orgs legitimately lack e.g. packet capture data, and treating
        that as unhealthy would falsely trip OrgHealthTracker backoff for a
        perfectly healthy org.
        """
        org = OrganizationFactory.create(org_id="779", name="No Packet Capture Org")

        api = (
            mock_api_builder
            .with_organizations([org])
            .with_networks([], org_id=org["id"])
            .with_devices([], org_id=org["id"])
            .with_custom_response("getOrganizationDevicesOverviewByModel", {"counts": []})
            .with_custom_response("getOrganizationDevicesAvailabilities", [])
            .with_custom_response(
                "getOrganizationLicensesOverview",
                {"expirationDate": "2026-01-01", "licenseTypes": []},
            )
            .with_custom_response("getOrganizationClientsOverview", {"counts": {"total": 0}})
            .with_error("getOrganizationDevicesPacketCaptureCaptures", 404)
            .with_custom_response("getOrganizationSummaryTopApplicationsCategoriesByUsage", [])
            .build()
        )
        collector.api = api
        collector.api_helper.api = api
        # network_metrics/device_metrics/device_availability_metrics read
        # through the inventory cache (NetworkFilter enforcement point), not
        # collector.api directly, so it must be repointed at the same mock too.
        collector.inventory.api = api
        # The five delegating sub-collectors captured collector.api at __init__
        # and are not repointed here; this test exercises the *direct*
        # packet-capture 404 path, so stub them to success (True) rather than
        # let them spuriously fail against the unconfigured original mock and
        # muddy the 404-vs-real-failure signal (F-172).
        for sub in (
            collector.api_usage_collector,
            collector.license_collector,
            collector.client_overview_collector,
            collector.firmware_collector,
            collector.device_availability_history_collector,
            collector.top_usage_collector,
            collector.webhook_logs_collector,
            collector.early_access_collector,
        ):
            sub.collect = AsyncMock(return_value=True)  # type: ignore[method-assign]
        # Phase 4 (#618): stub the firmware compliance path + the two direct
        # coordinator sub-collections so they don't hit the unconfigured mock.
        collector.firmware_collector.collect_compliance = AsyncMock(  # type: ignore[method-assign]
            return_value=True
        )
        collector._collect_config_templates = AsyncMock(  # type: ignore[method-assign]
            return_value=None
        )
        collector._collect_adaptive_policy = AsyncMock(  # type: ignore[method-assign]
            return_value=None
        )

        await collector._collect_org_metrics(org)

        health = collector.org_health_tracker.get_health(org["id"])
        assert health is None or health.consecutive_failures == 0

        metrics.assert_gauge_value(
            "meraki_exporter_org_collection_status",
            1,
            org_id=org["id"],
        )

    # -- F-172: isolated failure in one of the 5 delegating sub-collectors ---

    def _neutralize_all_but(self, collector, keep: str) -> None:
        """Stub every org sub-collection to success except ``keep``.

        Lets a test exercise exactly one sub-collection's failure signalling
        without spurious failures from the others (which would otherwise hit
        the unconfigured mock).
        """

        async def _ok(*_args: object, **_kwargs: object) -> bool:
            return True

        names = [
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
            # Phase 4 (#618) additions.
            "_collect_config_templates",
            "_collect_adaptive_policy",
            "_collect_top_usage_metrics",
            "_collect_webhook_logs_metrics",
            "_collect_firmware_compliance_metrics",
            "_collect_early_access_metrics",
        ]
        for name in names:
            if name != keep:
                setattr(collector, name, _ok)

    async def test_delegating_subcollector_false_signal_records_failure(self, collector, metrics):
        """A False signal from a delegating sub-collector must record a failure.

        Previously each of the 5 sub-collectors (api_usage/firmware/
        device_availability_history/license/client_overview) swallowed its own
        exceptions and never surfaced an isolated failure to OrgHealthTracker,
        so backoff/export-suppression could not engage (bug-bash F-172).
        """
        org = OrganizationFactory.create(org_id="781", name="ApiUsage Broken Org")
        self._neutralize_all_but(collector, keep="_collect_api_metrics")
        # Sub-collector reports a real (non-404) failure via its bool signal.
        collector.api_usage_collector.collect = AsyncMock(  # type: ignore[method-assign]
            return_value=False
        )

        await collector._collect_org_metrics(org)

        health = collector.org_health_tracker.get_health(org["id"])
        assert health is not None
        assert health.consecutive_failures == 1
        metrics.assert_gauge_value(
            "meraki_exporter_org_collection_status",
            0,
            org_id=org["id"],
        )

    async def test_delegating_subcollector_non_404_error_records_failure(self, collector, metrics):
        """A non-404 error inside a real sub-collector must record a failure.

        End-to-end variant of F-172: the sub-collector catches the error
        itself (resilience) but now returns a False signal the parent counts.
        """
        org = OrganizationFactory.create(org_id="782", name="Firmware Broken Org")
        self._neutralize_all_but(collector, keep="_collect_firmware_metrics")
        collector.firmware_collector._fetch_firmware_upgrades = AsyncMock(  # type: ignore[method-assign]
            side_effect=Exception("500 Internal Server Error")
        )

        await collector._collect_org_metrics(org)

        health = collector.org_health_tracker.get_health(org["id"])
        assert health is not None
        assert health.consecutive_failures == 1
        metrics.assert_gauge_value(
            "meraki_exporter_org_collection_status",
            0,
            org_id=org["id"],
        )

    async def test_delegating_subcollector_404_not_counted_as_failure(self, collector, metrics):
        """A 404 inside a delegating sub-collector must NOT count as a failure.

        Many orgs legitimately lack e.g. firmware upgrade history; treating a
        404 as unhealthy would falsely trip backoff (companion to F-172).
        """
        org = OrganizationFactory.create(org_id="783", name="No Firmware Org")
        self._neutralize_all_but(collector, keep="_collect_firmware_metrics")
        collector.firmware_collector._fetch_firmware_upgrades = AsyncMock(  # type: ignore[method-assign]
            side_effect=Exception("404 Not Found")
        )

        await collector._collect_org_metrics(org)

        health = collector.org_health_tracker.get_health(org["id"])
        assert health is None or health.consecutive_failures == 0
        metrics.assert_gauge_value(
            "meraki_exporter_org_collection_status",
            1,
            org_id=org["id"],
        )

    # -- F-041: dead {"items": ...} branch in device-counts-by-model --------

    async def test_device_counts_by_model_processes_items_wrapped_response(
        self, collector, mock_api_builder, metrics
    ):
        """A response wrapped in {"items": [...]} must actually be processed.

        Instead of silently dropped, per bug-bash F-041.
        """
        org_id, org_name = "888", "Items Org"

        api = mock_api_builder.with_custom_response(
            "getOrganizationDevicesOverviewByModel",
            {"items": [{"model": "MS120-8", "total": 5}]},
        ).build()
        collector.api = api

        await collector._collect_device_counts_by_model(org_id, org_name)

        metrics.assert_gauge_value(
            OrgMetricName.ORG_DEVICES_BY_MODEL,
            5,
            org_id=org_id,
            model="MS120-8",
        )

    # -- F-042: clamp application-usage quantity to the documented max ------

    async def test_application_usage_clamps_quantity_to_documented_max(
        self, collector, mock_api_builder
    ):
        """quantity must be clamped to the documented API maximum.

        50, not the previous 1000 (bug-bash F-042).
        """
        org_id, org_name = "999", "Quantity Org"

        api = mock_api_builder.with_custom_response(
            "getOrganizationSummaryTopApplicationsCategoriesByUsage", []
        ).build()
        collector.api = api

        await collector._collect_application_usage_metrics(org_id, org_name)

        call = api.organizations.getOrganizationSummaryTopApplicationsCategoriesByUsage.call_args
        assert call.kwargs["quantity"] == 50

    # -- F-098: apply NetworkFilter to device-counts-by-model + packet capture --

    async def test_device_counts_by_model_applies_network_filter(self, collector, mock_api_builder):
        """Must scope by inventory.get_allowed_network_ids when a filter is active.

        Matches its inventory-filtered sibling meraki_org_devices
        (bug-bash F-098).
        """
        org_id, org_name = "555", "Filtered Org"
        collector.inventory.get_allowed_network_ids = AsyncMock(  # type: ignore[method-assign]
            return_value={"N_1", "N_2"}
        )

        api = mock_api_builder.with_custom_response(
            "getOrganizationDevicesOverviewByModel", {"counts": []}
        ).build()
        collector.api = api

        await collector._collect_device_counts_by_model(org_id, org_name)

        call = api.organizations.getOrganizationDevicesOverviewByModel.call_args
        assert sorted(call.kwargs["networkIds"]) == ["N_1", "N_2"]

    async def test_device_counts_by_model_omits_network_ids_when_filter_inactive(
        self, collector, mock_api_builder
    ):
        """No networkIds kwarg is sent when no NetworkFilter is configured."""
        org_id, org_name = "556", "Unfiltered Org"
        collector.inventory.get_allowed_network_ids = AsyncMock(  # type: ignore[method-assign]
            return_value=None
        )

        api = mock_api_builder.with_custom_response(
            "getOrganizationDevicesOverviewByModel", {"counts": []}
        ).build()
        collector.api = api

        await collector._collect_device_counts_by_model(org_id, org_name)

        call = api.organizations.getOrganizationDevicesOverviewByModel.call_args
        assert "networkIds" not in call.kwargs

    async def test_packet_capture_metrics_applies_network_filter(self, collector, mock_api_builder):
        """Must scope by inventory.get_allowed_network_ids when a filter is active.

        Bug-bash F-098.
        """
        org_id, org_name = "557", "Filtered Capture Org"
        collector.inventory.get_allowed_network_ids = AsyncMock(  # type: ignore[method-assign]
            return_value={"N_3"}
        )

        api = mock_api_builder.with_custom_response(
            "getOrganizationDevicesPacketCaptureCaptures",
            {"items": [], "meta": {"counts": {"items": {"total": 0, "remaining": 0}}}},
        ).build()
        collector.api = api

        await collector._collect_packet_capture_metrics(org_id, org_name)

        call = api.organizations.getOrganizationDevicesPacketCaptureCaptures.call_args
        assert call.kwargs["networkIds"] == ["N_3"]

    # -- #534 NI-1: meraki_network_info id->name join backbone ---------------

    @staticmethod
    def _network_info_samples(registry) -> list[tuple[frozenset[tuple[str, str]], float]]:
        """Collect (label-set, value) pairs for meraki_network_info from a registry."""
        samples: list[tuple[frozenset[tuple[str, str]], float]] = []
        for metric in registry.collect():
            for sample in metric.samples:
                if sample.name == NetworkMetricName.NETWORK_INFO.value:
                    samples.append((frozenset(sample.labels.items()), sample.value))
        return samples

    async def test_network_info_emitted_one_series_per_network(
        self, collector, metrics, isolated_registry
    ):
        """NI-1: meraki_network_info emits value 1, exactly one series per network.

        Labels are ID-only + the name carrier: {org_id, network_id,
        network_name}. This is the id->name join backbone every network_name
        join across the exporter depends on.
        """
        org_id, org_name = "org-1", "Org One"
        networks = [
            {"id": "N_1", "name": "HQ"},
            {"id": "N_2", "name": "Branch"},
        ]
        collector.api_helper.get_organization_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=networks
        )

        await collector._collect_network_metrics(org_id, org_name)

        # networks-total gauge is ID-only (org_name dropped) and counts both.
        metrics.assert_gauge_value(OrgMetricName.ORG_NETWORKS, 2, org_id=org_id)

        # Exactly one network_info series per network, each value 1, each with
        # the exact ID-only + name-carrier label set (no org_name leakage).
        samples = self._network_info_samples(isolated_registry)
        assert len(samples) == 2
        expected = {
            frozenset({"org_id": org_id, "network_id": "N_1", "network_name": "HQ"}.items()),
            frozenset({"org_id": org_id, "network_id": "N_2", "network_name": "Branch"}.items()),
        }
        assert {labelset for labelset, _ in samples} == expected
        assert all(value == 1 for _, value in samples)

    async def test_network_info_series_retired_when_network_removed(
        self, mock_api, settings, isolated_registry, inventory
    ):
        """NI-1: a deleted/filtered network's info series expires (not frozen).

        Emitting via _set_metric registers the series with the expiration
        manager; once the network stops being emitted its series is retired on
        the next cleanup, while surviving networks are refreshed and kept.
        """
        from unittest.mock import patch

        from meraki_dashboard_exporter.core.metric_expiration import MetricExpirationManager

        manager = MetricExpirationManager(settings=settings)
        collector = OrganizationCollector(
            api=mock_api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
            expiration_manager=manager,
        )

        org_id, org_name = "org-9", "Org Nine"

        # Cycle 1 at base_time: both networks present.
        collector.api_helper.get_organization_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"id": "N_1", "name": "HQ"}, {"id": "N_2", "name": "Branch"}]
        )
        base_time = 1_000_000.0
        with patch(
            "meraki_dashboard_exporter.core.metric_expiration.time.time",
            return_value=base_time,
        ):
            await collector._collect_network_metrics(org_id, org_name)

        assert len(self._network_info_samples(isolated_registry)) == 2

        # Cycle 2 much later: N_2 is gone, only N_1 refreshed to a recent time.
        collector.api_helper.get_organization_networks = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"id": "N_1", "name": "HQ"}]
        )
        refresh_time = base_time + 100_000
        with patch(
            "meraki_dashboard_exporter.core.metric_expiration.time.time",
            return_value=refresh_time,
        ):
            await collector._collect_network_metrics(org_id, org_name)

        # Cleanup just after the refresh: N_1 (age ~1s) is fresh and kept, while
        # N_2 (never refreshed, age ~100k s >> MEDIUM TTL) is retired.
        with patch(
            "meraki_dashboard_exporter.core.metric_expiration.time.time",
            return_value=refresh_time + 1,
        ):
            await manager._cleanup_expired_metrics()

        samples = self._network_info_samples(isolated_registry)
        assert samples == [
            (frozenset({"org_id": org_id, "network_id": "N_1", "network_name": "HQ"}.items()), 1.0)
        ]

    async def test_network_info_excluded_network_has_no_series(
        self, mock_api_builder, settings, isolated_registry, metrics
    ):
        """NI-1: a NetworkFilter-excluded network gets NO info series.

        Exercised end-to-end through the real inventory + NetworkFilter (per
        tests/CLAUDE.md) rather than by patching the filter out.
        """
        from meraki_dashboard_exporter.core.config_models import NetworkFilterSettings
        from meraki_dashboard_exporter.core.network_filter import NetworkFilter
        from meraki_dashboard_exporter.services.inventory import OrganizationInventory

        org_id, org_name = "org-f", "Filter Org"
        api = mock_api_builder.with_custom_response(
            "getOrganizationNetworks",
            [
                {"id": "N_keep", "name": "Prod", "tags": []},
                {"id": "N_drop", "name": "Lab", "tags": ["lab"]},
            ],
        ).build()

        network_filter = NetworkFilter(NetworkFilterSettings(exclude_tags=["lab"]))
        inventory = OrganizationInventory(api, settings, network_filter=network_filter)
        collector = OrganizationCollector(
            api=api,
            settings=settings,
            registry=isolated_registry,
            inventory=inventory,
        )
        collector.api_helper.api = api

        await collector._collect_network_metrics(org_id, org_name)

        # The allowed network is the only info series; the excluded one is absent.
        metrics.assert_gauge_value(
            NetworkMetricName.NETWORK_INFO,
            1,
            org_id=org_id,
            network_id="N_keep",
            network_name="Prod",
        )
        metrics.assert_metric_not_set(NetworkMetricName.NETWORK_INFO, network_id="N_drop")

        samples = self._network_info_samples(isolated_registry)
        assert len(samples) == 1
        assert samples[0][0] == frozenset(
            {"org_id": org_id, "network_id": "N_keep", "network_name": "Prod"}.items()
        )

    # -- #509: "collected nothing" must be treated as a collection failure --

    def _make_all_subcollections_fail(self, collector) -> None:
        """Stub every one of the 11 org sub-collections to signal failure.

        The six direct sub-collections (network/device/device-counts-by-model/
        device-availability/packet-capture/application-usage) signal failure
        by raising; the five delegating sub-collectors (api_usage/firmware/
        device-availability-history/license/client-overview) signal failure by
        their wrapped ``.collect()`` returning ``False`` (F-172 contract).
        """

        async def _boom(*_args: object, **_kwargs: object) -> None:
            raise Exception("Connection error")

        collector._collect_network_metrics = _boom  # type: ignore[method-assign]
        collector._collect_device_metrics = _boom  # type: ignore[method-assign]
        collector._collect_device_counts_by_model = _boom  # type: ignore[method-assign]
        collector._collect_device_availability_metrics = _boom  # type: ignore[method-assign]
        collector._collect_packet_capture_metrics = _boom  # type: ignore[method-assign]
        collector._collect_application_usage_metrics = _boom  # type: ignore[method-assign]

        for sub in (
            collector.api_usage_collector,
            collector.license_collector,
            collector.client_overview_collector,
            collector.firmware_collector,
            collector.device_availability_history_collector,
        ):
            sub.collect = AsyncMock(return_value=False)  # type: ignore[method-assign]

    async def test_org_fetch_failure_raises(self, collector, mock_api_builder):
        """A total failure to fetch organizations must raise out of collect().

        Multi-org mode's getOrganizations has no swallow in inventory.py, so
        the exception propagates all the way out with no coordinator
        try/except left to catch it (#509).
        """
        api = mock_api_builder.with_error("getOrganizations", Exception("Connection error")).build()
        collector.api = api
        collector.inventory.api = api

        with pytest.raises(Exception, match="Connection error"):
            await collector.collect()

    async def test_all_orgs_failed_raises_nothing_collected(
        self, collector, mock_api_builder, metrics
    ):
        """Every org sub-collection failing must raise NothingCollectedError.

        Previously the coordinator's blanket try/except swallowed this
        entirely, so the manager recorded a spurious success even though zero
        org-scope metrics were actually collected this cycle (#509 / RES-01).
        """
        org = OrganizationFactory.create(org_id="900", name="Totally Broken Org")
        api = mock_api_builder.with_organizations([org]).build()
        collector.api = api
        collector.inventory.api = api
        self._make_all_subcollections_fail(collector)

        with pytest.raises(NothingCollectedError) as exc_info:
            await collector.collect()

        assert exc_info.value.attempted == 1
        assert exc_info.value.failed == 1
        assert exc_info.value.skipped_backoff == 0

        metrics.assert_gauge_value(
            "meraki_exporter_org_collection_status",
            0,
            org_id="900",
        )

    async def test_partial_org_failure_does_not_raise(self, collector, mock_api_builder, metrics):
        """One totally-broken org among several healthy ones must not raise.

        Partial org success stays a SUCCESS at the coordinator level (#509);
        only an all-orgs-failed (or all-in-backoff) cycle raises.
        """
        broken_org = OrganizationFactory.create(org_id="901", name="Broken Org")
        healthy_org = OrganizationFactory.create(org_id="902", name="Healthy Org")
        api = (
            mock_api_builder
            .with_organizations([broken_org, healthy_org])
            .with_networks([], org_id=healthy_org["id"])
            .with_devices([], org_id=healthy_org["id"])
            .with_custom_response("getOrganizationDevicesOverviewByModel", {"counts": []})
            .with_custom_response("getOrganizationDevicesAvailabilities", [])
            .with_custom_response(
                "getOrganizationLicensesOverview",
                {"expirationDate": "2026-01-01", "licenseTypes": []},
            )
            .with_custom_response("getOrganizationClientsOverview", [])
            .with_custom_response(
                "getOrganizationDevicesPacketCaptureCaptures",
                {"items": [], "meta": {"counts": {"items": {"total": 0, "remaining": 0}}}},
            )
            .with_custom_response("getOrganizationSummaryTopApplicationsCategoriesByUsage", [])
            .build()
        )
        collector.api = api
        collector.inventory.api = api
        collector.api_helper.api = api
        for sub in (
            collector.api_usage_collector,
            collector.license_collector,
            collector.client_overview_collector,
            collector.firmware_collector,
            collector.device_availability_history_collector,
            collector.top_usage_collector,
            collector.webhook_logs_collector,
            collector.early_access_collector,
        ):
            sub.collect = AsyncMock(return_value=True)  # type: ignore[method-assign]
        # Phase 4 (#618): stub the firmware compliance path + the two direct
        # coordinator sub-collections so they don't hit the unconfigured mock.
        collector.firmware_collector.collect_compliance = AsyncMock(  # type: ignore[method-assign]
            return_value=True
        )
        collector._collect_config_templates = AsyncMock(  # type: ignore[method-assign]
            return_value=None
        )
        collector._collect_adaptive_policy = AsyncMock(  # type: ignore[method-assign]
            return_value=None
        )

        async def _boom(*_args: object, **_kwargs: object) -> None:
            raise Exception("Connection error")

        # Only the broken org's network fetch fails; everything else is
        # keyed by org_id in the mock so the healthy org sails through.
        original_get_networks = collector.inventory.get_networks

        async def _get_networks(org_id: str, *args: object, **kwargs: object):
            if org_id == broken_org["id"]:
                raise Exception("Connection error")
            return await original_get_networks(org_id, *args, **kwargs)

        collector.inventory.get_networks = _get_networks  # type: ignore[method-assign]

        # collect() must not raise even though one org is totally broken.
        await collector.collect()

        metrics.assert_gauge_value(
            "meraki_exporter_org_collection_status",
            0,
            org_id="901",
        )
        metrics.assert_gauge_value(
            "meraki_exporter_org_collection_status",
            1,
            org_id="902",
        )

    async def test_all_orgs_in_backoff_raises(self, collector, mock_api_builder, metrics):
        """Every org being in OrgHealthTracker backoff must raise NothingCollectedError.

        Without this, once every org has backed off (~5 consecutive failed
        MEDIUM cycles), skip-cycles would masquerade as a spurious success and
        re-poison failure_streak/last_success_time (#509).
        """
        org = OrganizationFactory.create(org_id="903", name="Backed Off Org")
        api = mock_api_builder.with_organizations([org]).build()
        collector.api = api
        collector.inventory.api = api

        for _ in range(collector.org_health_tracker.max_consecutive_failures):
            collector.org_health_tracker.record_failure(org["id"], org["name"])
        assert collector.org_health_tracker.should_collect(org["id"]) is False

        with pytest.raises(NothingCollectedError) as exc_info:
            await collector.collect()

        assert exc_info.value.attempted == 0
        assert exc_info.value.failed == 0
        assert exc_info.value.skipped_backoff == 1

        metrics.assert_gauge_value(
            "meraki_exporter_org_collection_status",
            0,
            org_id="903",
        )

    async def test_empty_org_list_is_success(self, collector, mock_api_builder, metrics):
        """An empty org list is a legitimate no-op, not a failure (#509)."""
        api = mock_api_builder.with_organizations([]).build()
        collector.api = api
        collector.inventory.api = api

        await collector.collect()

        self.assert_collector_success(collector, metrics)


class TestLicenseCollectorSubscription:
    """Subscription-licensing handling for LicenseCollector (#516).

    Subscription-licensing orgs carry no ``licensedDeviceCounts`` in the
    licenses overview and 400 (not 404) on ``getOrganizationLicenses`` ("does
    not support per-device licensing"). Previously this left them permanently
    red (``org_collection_status=0``) with zero license metrics. The collector
    must instead emit the overview's own ``states`` counts and soft-skip an
    unsupported per-device call.
    """

    @pytest.fixture
    def mock_api_builder(self):
        """Create a mock API builder."""
        from tests.helpers.mock_api import MockAPIBuilder

        return MockAPIBuilder()

    @pytest.fixture
    def license_collector(self, mock_api_builder):
        """Create a LicenseCollector with a minimal mock parent collector."""
        from pydantic import SecretStr

        from meraki_dashboard_exporter.collectors.organization_collectors.license import (
            LicenseCollector,
        )
        from meraki_dashboard_exporter.core.config import Settings
        from meraki_dashboard_exporter.core.config_models import MerakiSettings

        test_settings = Settings(
            meraki=MerakiSettings(
                api_key=SecretStr("6bec40cf957de430a6f1f2baa056b367d6172e1e"),
                org_id="test-org-id",
            )
        )

        class MockParentCollector:
            def __init__(self) -> None:
                self.api = mock_api_builder.build()
                self.settings = test_settings
                self._api_calls: dict[str, int] = {}
                self._metrics: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

            def _should_run_group(self, group: object) -> bool:
                return True

            def _mark_group_ran(self, group: object) -> None:
                pass

            def _group_ttl_seconds(self, group: object) -> float | None:
                return None

            def _track_api_call(self, method_name: str) -> None:
                self._api_calls[method_name] = self._api_calls.get(method_name, 0) + 1

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

        parent = MockParentCollector()
        return LicenseCollector(parent=parent)  # type: ignore[arg-type]

    async def test_subscription_licensing_uses_overview_states(
        self, license_collector, mock_api_builder
    ):
        """When licensedDeviceCounts is absent, emit overview `states` counts."""
        org_id = "sub-1"
        org_name = "Subscription Org"

        overview_response = {
            "status": "OK",
            "states": {
                "active": {"count": 12},
                "expiring": {"count": 3},
                "expired": {"count": 1},
                "unused": {"count": 5},
            },
        }

        api = mock_api_builder.with_custom_response(
            "getOrganizationLicensesOverview", overview_response
        ).build()
        license_collector.api = api

        result = await license_collector.collect(org_id, org_name)

        # Soft, healthy outcome.
        assert result is True

        # The unsupported per-device endpoint must NOT be called.
        assert not api.organizations.getOrganizationLicenses.called

        parent = license_collector.parent

        # A `_licenses_total` series per state, keyed by an aggregate license_type.
        for state, count in [("active", 12), ("expiring", 3), ("expired", 1), ("unused", 5)]:
            key = (
                "_licenses_total",
                (
                    ("license_type", "All"),
                    ("org_id", org_id),
                    ("status", state),
                ),
            )
            assert key in parent._metrics, f"missing {state}"
            assert parent._metrics[key] == count

        # Expiring gauge sourced from states.expiring.count.
        key_exp = (
            "_licenses_expiring",
            (("license_type", "All"), ("org_id", org_id)),
        )
        assert key_exp in parent._metrics
        assert parent._metrics[key_exp] == 3

    async def test_subscription_licensing_400_soft_skipped(
        self, license_collector, mock_api_builder
    ):
        """A 400 from getOrganizationLicenses is soft-skipped (no red health)."""
        org_id = "sub-2"
        org_name = "Subscription Org No States"

        # No licensedDeviceCounts and no states -> falls through to per-device
        # fetch, which 400s for a subscription org.
        api = (
            mock_api_builder
            .with_custom_response("getOrganizationLicensesOverview", {"status": "OK"})
            .with_error(
                "getOrganizationLicenses",
                Exception("400 Bad Request: organization does not support per-device licensing"),
            )
            .build()
        )
        license_collector.api = api

        result = await license_collector.collect(org_id, org_name)

        # Soft-skip: True (healthy), not a raised/failed collection.
        assert result is True
