"""Mock API builder for testing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock


class HTTPError(Exception):
    """Mock HTTP error mirroring ``meraki.exceptions.APIError`` semantics.

    Carries a top-level ``.status`` attribute (matching the real SDK's
    ``APIError.status``) so production rate-limit detection
    (``core.error_handling._is_rate_limit_error``, which reads
    ``getattr(error, "status", None)``) works against builder-generated
    errors. The legacy ``.response.status_code`` / ``.response.text`` shape
    is kept for any code that still inspects the httpx-style response.
    """

    def __init__(self, message: str, status_code: int) -> None:
        """Initialize HTTP error."""
        super().__init__(message)
        self.status = status_code
        self.response = MagicMock()
        self.response.status_code = status_code

        if status_code == 404:
            self.response.text = '{"errors": ["Not found"]}'
        elif status_code == 429:
            self.response.text = '{"errors": ["Too many requests"]}'
        else:
            self.response.text = f'{{"errors": ["HTTP {status_code} error"]}}'


class _MethodEntry:
    """Configured behavior for one method, scoped to one set of match values."""

    __slots__ = ("call_count", "kind", "payload")

    def __init__(self) -> None:
        """Initialize an empty entry."""
        self.kind: str = "unset"  # "response" | "error" | "side_effect"
        self.payload: Any = None
        self.call_count = 0


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

    Scoping
    -------
    Methods that accept ``org_id``/``network_id``/``serial`` (or arbitrary
    ``**kwargs`` on `with_custom_response`/`with_error`/`with_side_effect`)
    register a *scoped* response: at call time, the mock dispatches based on
    the actual positional args and keyword values passed to the API method,
    matching whichever registered scope's values all appear in that call.
    This means two organizations configured with different data via
    ``org_id=`` really do return different data - the scoping is not
    decorative.

    """

    def __init__(self) -> None:
        """Initialize the mock API builder."""
        # method_name -> {match_values tuple -> entry}. An empty tuple key
        # is the "default"/unscoped entry, used when no scoped entry matches
        # (or when no scoping was requested at all).
        self._configs: dict[str, dict[tuple[str, ...], _MethodEntry]] = {}

    def _entry(self, method_name: str, match_values: tuple[str, ...]) -> _MethodEntry:
        """Get (creating if needed) the entry for a method + scope."""
        scoped = self._configs.setdefault(method_name, {})
        entry = scoped.get(match_values)
        if entry is None:
            entry = _MethodEntry()
            scoped[match_values] = entry
        return entry

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
        self._entry("getOrganizations", ()).kind = "response"
        self._entry("getOrganizations", ()).payload = organizations
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
        match = (str(org_id),) if org_id else ()
        entry = self._entry("getOrganizationNetworks", match)
        entry.kind = "response"
        entry.payload = networks
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
            entry = self._entry("getOrganizationDevices", (str(org_id),))
            entry.kind = "response"
            entry.payload = devices
        if network_id:
            entry = self._entry("getNetworkDevices", (str(network_id),))
            entry.kind = "response"
            entry.payload = devices
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
        for method_name in (
            "getOrganizationDevicesStatuses",
            "getOrganizationDevicesAvailabilities",
        ):
            entry = self._entry(method_name, ())
            entry.kind = "response"
            entry.payload = statuses
        if org_id:
            entry = self._entry("getOrganizationDevicesAvailabilities", (str(org_id),))
            entry.kind = "response"
            entry.payload = statuses
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
        entry = self._entry("getOrganizationAssuranceAlerts", ())
        entry.kind = "response"
        entry.payload = alerts
        if org_id:
            entry = self._entry("getOrganizationAssuranceAlerts", (str(org_id),))
            entry.kind = "response"
            entry.payload = alerts
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
        entry = self._entry("getOrganizationSensorReadingsHistory", ())
        entry.kind = "response"
        entry.payload = sensor_data
        if serial:
            entry = self._entry("getDeviceSensorReadings", (str(serial),))
            entry.kind = "response"
            entry.payload = sensor_data
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
            Optional parameters to scope this response to. At call time the
            mock matches a scope whose values all appear among the actual
            call's positional args / keyword values.

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        match = tuple(str(v) for v in kwargs.values())
        entry = self._entry(method_name, match)
        entry.kind = "response"
        entry.payload = response
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
            Optional parameters to scope this error to (see
            `with_custom_response`)

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        match = tuple(str(v) for v in kwargs.values())

        if isinstance(error, int):
            # Create HTTP error
            error = self._create_http_error(error)

        entry = self._entry(method_name, match)
        entry.kind = "error"
        entry.payload = error
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
            Optional parameters to scope this sequence to (see
            `with_custom_response`)

        Returns
        -------
        MockAPIBuilder
            Self for chaining

        """
        match = tuple(str(v) for v in kwargs.values())

        # Convert status codes to exceptions
        processed_effects = [
            self._create_http_error(effect) if isinstance(effect, int) else effect
            for effect in side_effects
        ]

        entry = self._entry(method_name, match)
        entry.kind = "side_effect"
        entry.payload = processed_effects
        entry.call_count = 0
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

        entry = self._entry(method_name, ())
        entry.kind = "side_effect"
        entry.payload = pages
        entry.call_count = 0
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
        """Configure methods on API modules from the registered configs."""
        for method_name, scoped_entries in self._configs.items():
            module_name = self._resolve_module(method_name)
            module = getattr(api, module_name)

            # Reset per-entry call counters so a builder can be `.build()`-ed
            # more than once and each build gets a fresh side_effect sequence.
            for entry in scoped_entries.values():
                entry.call_count = 0

            handler = self._make_handler(scoped_entries)
            setattr(module, method_name, MagicMock(side_effect=handler))

    def _make_handler(
        self, scoped_entries: dict[tuple[str, ...], _MethodEntry]
    ) -> Callable[..., Any]:
        """Build a side_effect callable that dispatches on call args.

        Specific (non-empty) scopes are checked first, in registration
        order; a scope matches when every one of its match values appears
        (as a string) among the call's positional args or keyword values.
        Falls back to the unscoped ("()") entry, if any.
        """
        specific = [
            (match_values, entry) for match_values, entry in scoped_entries.items() if match_values
        ]
        default_entry = scoped_entries.get(())

        def handler(*args: Any, **kwargs: Any) -> Any:
            call_values = [str(a) for a in args] + [str(v) for v in kwargs.values()]

            entry = None
            for match_values, candidate in specific:
                if all(match_value in call_values for match_value in match_values):
                    entry = candidate
                    break
            if entry is None:
                entry = default_entry

            if entry is None or entry.kind == "unset":
                return None

            if entry.kind == "error":
                raise entry.payload

            if entry.kind == "side_effect":
                index = entry.call_count
                entry.call_count += 1
                if index >= len(entry.payload):
                    raise StopIteration
                outcome = entry.payload[index]
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome

            return entry.payload

        return handler

    def _resolve_module(self, method_name: str) -> str:
        """Resolve the SDK controller module a method belongs to.

        Single source of truth used for both responses and errors (unlike
        the historical implementation, which routed `with_custom_response`
        and `with_error` through two different, inconsistent lookups).
        Checked in an order that matches the real SDK layout: sensor and
        wireless and switch methods are named with an "Organization"/
        "Network" prefix too (e.g. `getOrganizationWirelessDevices...`,
        `getOrganizationSensorReadingsLatest`, `getNetworkSwitchStacks`),
        so those more specific families must be matched before the generic
        Organization/Network/Device fallbacks.
        """
        if "Sensor" in method_name:
            return "sensor"
        if "Wireless" in method_name:
            return "wireless"
        if "Switch" in method_name:
            return "switch"
        if "Organization" in method_name:
            return "organizations"
        if "Network" in method_name:
            return "networks"
        if "Device" in method_name:
            return "devices"
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
