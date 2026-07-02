"""Regression tests for MockAPIBuilder scoping, routing, and error semantics.

Covers bug-bash findings F-050 (org_id/param scoping was a silent no-op),
F-161 (wrong module routing for org-wireless/sensor-latest methods, and
`with_error` routing differently than `with_custom_response`), and F-165
(HTTP errors didn't carry `.status`, so the production 429-retry branch was
unreachable from builder-driven tests).
"""

from __future__ import annotations

import pytest

from tests.helpers.mock_api import HTTPError, MockAPIBuilder


class TestScopedResponses:
    """F-050: org_id/param-scoped responses must not collapse to last-write-wins."""

    def test_devices_scoped_by_org_id_return_different_data(self) -> None:
        """Two orgs configured with different devices must each see their own."""
        devices_a = [{"serial": "A1"}]
        devices_b = [{"serial": "B1"}]

        api = (
            MockAPIBuilder()
            .with_devices(devices_a, org_id="org_a")
            .with_devices(devices_b, org_id="org_b")
            .build()
        )

        result_a = api.organizations.getOrganizationDevices("org_a", total_pages="all")
        result_b = api.organizations.getOrganizationDevices("org_b", total_pages="all")

        assert result_a == devices_a
        assert result_b == devices_b
        assert result_a != result_b

    def test_networks_scoped_by_org_id_return_different_data(self) -> None:
        """Networks scoped per org_id must not collapse either."""
        networks_a = [{"id": "N_a"}]
        networks_b = [{"id": "N_b"}]

        api = (
            MockAPIBuilder()
            .with_networks(networks_a, org_id="org_a")
            .with_networks(networks_b, org_id="org_b")
            .build()
        )

        assert api.organizations.getOrganizationNetworks("org_a") == networks_a
        assert api.organizations.getOrganizationNetworks("org_b") == networks_b

    def test_custom_response_scoped_by_kwargs_return_different_data(self) -> None:
        """with_custom_response's kwargs scoping must dispatch on real call args."""
        api = (
            MockAPIBuilder()
            .with_custom_response(
                "getNetworkWirelessConnectionStats", {"assoc": 1}, network_id="N_1"
            )
            .with_custom_response(
                "getNetworkWirelessConnectionStats", {"assoc": 2}, network_id="N_2"
            )
            .build()
        )

        assert api.wireless.getNetworkWirelessConnectionStats("N_1") == {"assoc": 1}
        assert api.wireless.getNetworkWirelessConnectionStats("N_2") == {"assoc": 2}

    def test_unscoped_default_still_works(self) -> None:
        """A plain, unscoped with_organizations response is unaffected."""
        orgs = [{"id": "123"}]
        api = MockAPIBuilder().with_organizations(orgs).build()
        assert api.organizations.getOrganizations() == orgs


class TestModuleRouting:
    """F-161: routing must match production `self.api.<module>.<method>` usage."""

    def test_org_wireless_response_lands_on_wireless_module(self) -> None:
        """getOrganizationWireless* must be configured on api.wireless, not api.organizations."""
        data = [{"utilization": 42}]
        api = (
            MockAPIBuilder()
            .with_custom_response("getOrganizationWirelessDevicesChannelUtilization", data)
            .build()
        )

        assert api.wireless.getOrganizationWirelessDevicesChannelUtilization() == data

    def test_sensor_latest_response_lands_on_sensor_module(self) -> None:
        """getOrganizationSensorReadingsLatest must be configured on api.sensor."""
        data = [{"serial": "Q2MT-1"}]
        api = (
            MockAPIBuilder()
            .with_custom_response("getOrganizationSensorReadingsLatest", data)
            .build()
        )

        assert api.sensor.getOrganizationSensorReadingsLatest() == data

    def test_device_sensor_readings_lands_on_sensor_module(self) -> None:
        """getDeviceSensorReadings* must route to sensor, not devices (Device substring trap)."""
        data = [{"reading": 1}]
        api = MockAPIBuilder().with_custom_response("getDeviceSensorReadings", data).build()

        assert api.sensor.getDeviceSensorReadings() == data

    def test_error_and_custom_response_route_to_the_same_module(self) -> None:
        """with_error must use the same routing as with_custom_response for a given method."""
        configured = [{"utilization": 1}]
        response_api = (
            MockAPIBuilder()
            .with_custom_response("getOrganizationWirelessDevicesChannelUtilization", configured)
            .build()
        )

        error_api = (
            MockAPIBuilder()
            .with_error("getOrganizationWirelessDevicesChannelUtilization", 500)
            .build()
        )

        # The configured response must actually land on api.wireless (production
        # calls self.api.wireless.getOrganizationWirelessDevices...), not on an
        # unconfigured api.organizations mock.
        assert (
            response_api.wireless.getOrganizationWirelessDevicesChannelUtilization() == configured
        )
        with pytest.raises(HTTPError):
            error_api.wireless.getOrganizationWirelessDevicesChannelUtilization()


class TestHTTPErrorStatus:
    """F-165: builder-generated HTTP errors must carry `.status` like meraki APIError."""

    @pytest.mark.parametrize("status_code", [404, 429, 500])
    def test_http_error_carries_status_attribute(self, status_code: int) -> None:
        """The mock error's `.status` must match what production rate-limit checks read."""
        api = MockAPIBuilder().with_error("getOrganizationDevices", status_code).build()

        with pytest.raises(HTTPError) as exc_info:
            api.organizations.getOrganizationDevices("123")

        assert exc_info.value.status == status_code
        # Legacy shape is preserved too.
        assert exc_info.value.response.status_code == status_code

    def test_429_is_recognized_as_rate_limit_by_production_helper(self) -> None:
        """The exact predicate production code uses to detect a 429 must see it."""
        api = MockAPIBuilder().with_error("getOrganizationDevices", 429).build()

        with pytest.raises(HTTPError) as exc_info:
            api.organizations.getOrganizationDevices("123")

        error = exc_info.value
        assert getattr(error, "status", None) == 429
