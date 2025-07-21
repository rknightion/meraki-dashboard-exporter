"""Tests for the OrganizationCollector using test helpers."""

from __future__ import annotations

from meraki_dashboard_exporter.collectors.organization import OrganizationCollector
from meraki_dashboard_exporter.core.constants import OrgMetricName, UpdateTier
from tests.helpers.base import BaseCollectorTest
from tests.helpers.factories import (
    NetworkFactory,
    OrganizationFactory,
)


class TestOrganizationCollector(BaseCollectorTest):
    """Test OrganizationCollector functionality."""

    collector_class = OrganizationCollector
    update_tier = UpdateTier.MEDIUM

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
            mock_api_builder.with_organizations([org])
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
            OrgMetricName.ORG_PACKETCAPTURES_TOTAL,
            266,
            org_id="123",
            org_name="Test Org",
        )

        metrics.assert_gauge_value(
            OrgMetricName.ORG_PACKETCAPTURES_REMAINING,
            263,
            org_id="123",
            org_name="Test Org",
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
            mock_api_builder.with_organizations([org])
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
            OrgMetricName.ORG_PACKETCAPTURES_TOTAL,
            0,
            org_id="456",
            org_name="Empty Org",
        )

        metrics.assert_gauge_value(
            OrgMetricName.ORG_PACKETCAPTURES_REMAINING,
            0,
            org_id="456",
            org_name="Empty Org",
        )

    async def test_packet_capture_metrics_with_api_error(
        self, collector, mock_api_builder, metrics
    ):
        """Test packet capture metrics handle API errors gracefully."""
        # Set up test data
        org = OrganizationFactory.create(org_id="789", name="Error Org")

        # Configure mock API with error for packet captures
        api = (
            mock_api_builder.with_organizations([org])
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
            OrgMetricName.ORG_PACKETCAPTURES_TOTAL,
            org_id="789",
            org_name="Error Org",
        )

        metrics.assert_metric_not_set(
            OrgMetricName.ORG_PACKETCAPTURES_REMAINING,
            org_id="789",
            org_name="Error Org",
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
            mock_api_builder.with_organizations([org])
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
            OrgMetricName.ORG_PACKETCAPTURES_TOTAL,
            org_id="999",
            org_name="Weird Org",
        )

        metrics.assert_metric_not_set(
            OrgMetricName.ORG_PACKETCAPTURES_REMAINING,
            org_id="999",
            org_name="Weird Org",
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
            mock_api_builder.with_organizations([org])
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
            OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_MB,
            579131.5472021103,
            org_id="111",
            org_name="App Usage Org",
            category="other",
        )

        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_DOWNSTREAM_MB,
            364303.2155036926,
            org_id="111",
            org_name="App Usage Org",
            category="other",
        )

        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_PERCENTAGE,
            97.1055882261812,
            org_id="111",
            org_name="App Usage Org",
            category="other",
        )

        # Verify VoIP & video conferencing category (tests sanitization)
        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_MB,
            2.367426872253418,
            org_id="111",
            org_name="App Usage Org",
            category="voip_and_video_conferencing",
        )

        # Verify upstream metric
        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_UPSTREAM_MB,
            0.5,
            org_id="111",
            org_name="App Usage Org",
            category="voip_and_video_conferencing",
        )

        # Verify Software & anti-virus updates (tests sanitization)
        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_MB,
            33.518364906311035,
            org_id="111",
            org_name="App Usage Org",
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
            mock_api_builder.with_organizations([org])
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
            mock_api_builder.with_organizations([org])
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
            OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_MB,
            org_id="333",
            org_name="Error App Usage Org",
            category="other",
        )
