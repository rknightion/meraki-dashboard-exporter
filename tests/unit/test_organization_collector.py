"""Tests for the OrganizationCollector using test helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

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
            org_name="App Usage Org",
            category="other",
        )

        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_DOWNSTREAM_BYTES,
            364303215503.6926,
            org_id="111",
            org_name="App Usage Org",
            category="other",
        )

        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_PERCENT,
            97.1055882261812,
            org_id="111",
            org_name="App Usage Org",
            category="other",
        )

        # Verify VoIP & video conferencing category (tests sanitization)
        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_BYTES,
            2367426.872253418,
            org_id="111",
            org_name="App Usage Org",
            category="voip_and_video_conferencing",
        )

        # Verify upstream metric
        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_UPSTREAM_BYTES,
            500000.0,
            org_id="111",
            org_name="App Usage Org",
            category="voip_and_video_conferencing",
        )

        # Verify Software & anti-virus updates (tests sanitization)
        metrics.assert_gauge_value(
            OrgMetricName.ORG_APPLICATION_USAGE_TOTAL_BYTES,
            33518364.906311035,
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
            org_name="Error App Usage Org",
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
            org_name=org["name"],
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
            org_name=org["name"],
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
        ):
            sub.collect = AsyncMock(return_value=True)  # type: ignore[method-assign]

        await collector._collect_org_metrics(org)

        health = collector.org_health_tracker.get_health(org["id"])
        assert health is None or health.consecutive_failures == 0

        metrics.assert_gauge_value(
            "meraki_exporter_org_collection_status",
            1,
            org_id=org["id"],
            org_name=org["name"],
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
            org_name=org["name"],
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
            org_name=org["name"],
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
            org_name=org["name"],
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
            org_name=org_name,
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
