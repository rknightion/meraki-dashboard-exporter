"""Mock API builder for testing."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


class HTTPError(Exception):
    """Mock HTTP error with response attribute."""

    def __init__(self, message: str, status_code: int) -> None:
        """Initialize HTTP error."""
        super().__init__(message)
        self.response = MagicMock()
        self.response.status_code = status_code

        if status_code == 404:
            self.response.text = '{"errors": ["Not found"]}'
        elif status_code == 429:
            self.response.text = '{"errors": ["Too many requests"]}'
        else:
            self.response.text = f'{{"errors": ["HTTP {status_code} error"]}}'


class MockAPIBuilder:
    """Fluent builder for creating mock Meraki API instances.

    Examples
    --------
    api = (MockAPIBuilder()
        .with_organizations([org1, org2])
        .with_networks([network1, network2])
        .with_devices([device1, device2])
        .with_error("getOrganizationAlerts", 404)
        .build())

    """

    def __init__(self) -> None:
        """Initialize the mock API builder."""
        self._responses: dict[str, Any] = {}
        self._errors: dict[str, Exception] = {}
        self._side_effects: dict[str, list[Any]] = {}

    def with_organizations(self, organizations: list[dict[str, Any]]) -> MockAPIBuilder:
        """Set organizations response.

        Parameters
        ----------
        organizations : list[dict[str, Any]]
            Organization data

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        self._responses["getOrganizations"] = organizations
        return self

    def with_networks(
        self, networks: list[dict[str, Any]], org_id: str | None = None
    ) -> MockAPIBuilder:
        """Set networks response.

        Parameters
        ----------
        networks : list[dict[str, Any]]
            Network data
        org_id : str, optional
            Organization ID for filtering

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        if org_id:
            self._responses[f"getOrganizationNetworks_{org_id}"] = networks
        else:
            self._responses["getOrganizationNetworks"] = networks
        return self

    def with_devices(
        self,
        devices: list[dict[str, Any]],
        org_id: str | None = None,
        network_id: str | None = None,
    ) -> MockAPIBuilder:
        """Set devices response.

        Parameters
        ----------
        devices : list[dict[str, Any]]
            Device data
        org_id : str, optional
            Organization ID for org-level endpoint
        network_id : str, optional
            Network ID for network-level endpoint

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        if org_id:
            self._responses[f"getOrganizationDevices_{org_id}"] = devices
            self._responses["getOrganizationDevices"] = devices
        if network_id:
            self._responses[f"getNetworkDevices_{network_id}"] = devices
        return self

    def with_device_statuses(
        self, statuses: list[dict[str, Any]], org_id: str | None = None
    ) -> MockAPIBuilder:
        """Set device statuses/availabilities response.

        Parameters
        ----------
        statuses : list[dict[str, Any]]
            Device status data
        org_id : str, optional
            Organization ID

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        # Support both old and new API names
        self._responses["getOrganizationDevicesStatuses"] = statuses
        self._responses["getOrganizationDevicesAvailabilities"] = statuses
        if org_id:
            self._responses[f"getOrganizationDevicesAvailabilities_{org_id}"] = statuses
        return self

    def with_alerts(
        self, alerts: list[dict[str, Any]], org_id: str | None = None
    ) -> MockAPIBuilder:
        """Set alerts response.

        Parameters
        ----------
        alerts : list[dict[str, Any]]
            Alert data
        org_id : str, optional
            Organization ID

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        self._responses["getOrganizationAssuranceAlerts"] = alerts
        if org_id:
            self._responses[f"getOrganizationAssuranceAlerts_{org_id}"] = alerts
        return self

    def with_sensor_data(
        self, sensor_data: list[dict[str, Any]], serial: str | None = None
    ) -> MockAPIBuilder:
        """Set sensor data response.

        Parameters
        ----------
        sensor_data : list[dict[str, Any]]
            Sensor data
        serial : str, optional
            Device serial

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        self._responses["getOrganizationSensorReadingsHistory"] = sensor_data
        if serial:
            self._responses[f"getDeviceSensorReadings_{serial}"] = sensor_data
        return self

    def with_custom_response(
        self, method_name: str, response: Any, **kwargs: Any
    ) -> MockAPIBuilder:
        """Set a custom API response.

        Parameters
        ----------
        method_name : str
            API method name
        response : Any
            Response data
        **kwargs : Any
            Optional parameters to match

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        key = method_name
        if kwargs:
            # Create a key with parameters for specific responses
            param_str = "_".join(str(v) for v in kwargs.values())
            key = f"{method_name}_{param_str}"
        self._responses[key] = response
        return self

    def with_error(self, method_name: str, error: Exception | int, **kwargs: Any) -> MockAPIBuilder:
        """Set an error response for a method.

        Parameters
        ----------
        method_name : str
            API method name
        error : Exception | int
            Exception to raise or HTTP status code
        **kwargs : Any
            Optional parameters to match

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        key = method_name
        if kwargs:
            param_str = "_".join(str(v) for v in kwargs.values())
            key = f"{method_name}_{param_str}"

        if isinstance(error, int):
            # Create HTTP error
            error = self._create_http_error(error)

        self._errors[key] = error
        return self

    def with_side_effect(
        self, method_name: str, side_effects: list[Any], **kwargs: Any
    ) -> MockAPIBuilder:
        """Set multiple responses/errors for sequential calls.

        Parameters
        ----------
        method_name : str
            API method name
        side_effects : list[Any]
            List of responses or exceptions
        **kwargs : Any
            Optional parameters to match

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        key = method_name
        if kwargs:
            param_str = "_".join(str(v) for v in kwargs.values())
            key = f"{method_name}_{param_str}"

        # Convert status codes to exceptions
        processed_effects = []
        for effect in side_effects:
            if isinstance(effect, int):
                processed_effects.append(self._create_http_error(effect))
            else:
                processed_effects.append(effect)

        self._side_effects[key] = processed_effects
        return self

    def with_paginated_response(
        self,
        method_name: str,
        items: list[Any],
        per_page: int = 10,
        use_items_wrapper: bool = True,
    ) -> MockAPIBuilder:
        """Set up paginated responses.

        Parameters
        ----------
        method_name : str
            API method name
        items : list[Any]
            All items to paginate
        per_page : int
            Items per page
        use_items_wrapper : bool
            Whether to wrap in {"items": [...]} format

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        pages: list[dict[str, list[Any]] | list[Any]] = []
        for i in range(0, len(items), per_page):
            page_items = items[i : i + per_page]
            if use_items_wrapper:
                pages.append({"items": page_items})
            else:
                pages.append(page_items)

        self._side_effects[method_name] = pages
        return self

    def build(self) -> MagicMock:
        """Build the mock API instance.

        Returns
        -------
        MagicMock
            Configured mock API

        """
        api = MagicMock()

        # Set up API modules
        modules = [
            "organizations",
            "networks",
            "devices",
            "wireless",
            "switch",
            "appliance",
            "cellularGateway",
            "camera",
            "sensor",
        ]

        for module in modules:
            setattr(api, module, MagicMock())

        # Configure responses
        self._configure_module_methods(api)

        return api

    def _configure_module_methods(self, api: MagicMock) -> None:
        """Configure methods on API modules."""
        # Map method patterns to modules
        method_module_map = {
            "getOrganization": "organizations",
            "getNetworkDevices": "networks",
            "getDeviceSwitchPortsStatuses": "switch",
            "getNetworkWireless": "wireless",
            "getOrganizationWireless": "wireless",  # Add organization wireless methods
            "getOrganizationSensorReadingsHistory": "sensor",
            "getDeviceSensorReadings": "sensor",
        }

        # Configure each response
        for key, response in self._responses.items():
            method_name = key.split("_")[0]  # Get base method name

            # Find the module
            module_name = None
            for pattern, module in method_module_map.items():
                if method_name.startswith(pattern):
                    module_name = module
                    break

            if not module_name:
                # Default module based on method name
                if "Organization" in method_name:
                    module_name = "organizations"
                elif "Network" in method_name:
                    module_name = "networks"
                elif "Device" in method_name:
                    module_name = "devices"
                else:
                    module_name = "organizations"  # fallback

            # Set up the method
            module = getattr(api, module_name)
            # Check if method already exists as a MagicMock
            if hasattr(module, method_name):
                method = getattr(module, method_name)
                method.return_value = response
            else:
                method = MagicMock(return_value=response)
                setattr(module, method_name, method)

        # Configure errors
        for key, error in self._errors.items():
            method_name = key.split("_")[0]

            # Find module (same logic as above)
            module_name = self._find_module_for_method(method_name)
            module = getattr(api, module_name)

            method = MagicMock(side_effect=error)
            setattr(module, method_name, method)

        # Configure side effects
        for key, effects in self._side_effects.items():
            method_name = key.split("_")[0]

            module_name = self._find_module_for_method(method_name)
            module = getattr(api, module_name)

            method = MagicMock(side_effect=effects)
            setattr(module, method_name, method)

    def _find_module_for_method(self, method_name: str) -> str:
        """Find the module for a method name."""
        # Check for wireless methods first (can be Organization or Network)
        if "Wireless" in method_name:
            return "wireless"
        elif "Organization" in method_name:
            return "organizations"
        elif "Network" in method_name:
            return "networks"
        elif "Device" in method_name and "Switch" in method_name:
            return "switch"
        elif "Device" in method_name:
            return "devices"
        elif "Sensor" in method_name:
            return "sensor"
        else:
            return "organizations"

    def _create_http_error(self, status_code: int) -> Exception:
        """Create an HTTP error exception."""
        return HTTPError(f"HTTP {status_code}", status_code)


class MockAsyncIterator:
    """Mock async iterator for paginated responses."""

    def __init__(self, items: list[Any]) -> None:
        """Initialize with items to iterate."""
        self.items = items
        self.index = 0

    def __aiter__(self) -> MockAsyncIterator:
        """Return self as async iterator."""
        return self

    async def __anext__(self) -> Any:
        """Get next item."""
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item
