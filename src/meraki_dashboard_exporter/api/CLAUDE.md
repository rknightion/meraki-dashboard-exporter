<system_context>
Meraki API Client - Provides authenticated access to Cisco Meraki Dashboard API with rate limiting, error handling, and response validation. Wraps the official Meraki SDK with additional monitoring capabilities.
</system_context>

<critical_notes>
- **Use `asyncio.to_thread()`** for all API calls - Meraki SDK is synchronous. `AsyncMerakiClient` no longer wraps individual endpoints itself — its higher-level convenience methods and `_request()` retry/metrics wrapper were removed as dead code (commit `836a6f3`, "remove dead AsyncMerakiClient._request wrapper"; no production code path called them, only `tests/test_api_client.py` did). Every collector, including `collectors/devices/mt.py`, calls the raw `meraki.DashboardAPI` directly (via the shared `AsyncMerakiClient.api` property) with `asyncio.to_thread()` — the paved path below is now the *only* path.
- **Rate limiting is two independent layers**, neither hardcoded to "5/s":
  1. **429-retry: single owner is the exporter, not the SDK (#545).** `_create_api_client()` passes `wait_on_rate_limit=False`, so the synchronous SDK call raises `APIError(status=429)` immediately (no unbounded in-thread `Retry-After` sleep). `core/error_handling.py::with_error_handling` is the sole 429-retry owner — it awaits a cancellable `asyncio.sleep`, honours `Retry-After` capped at `APISettings.retry_after_max_seconds` (default 60), and bounds total attempts to `1 + max_retries` (was ~12). `maximum_retries` still governs the SDK's short bounded connection-error/5xx retries. SDK calls run on `AsyncMerakiClient.executor` (a dedicated `ThreadPoolExecutor` of `APISettings.executor_workers`, installed as the loop default executor) so `/metrics` serving never queues behind blocked SDK threads; each logical fetch is bounded by `APISettings.per_fetch_deadline_seconds` (#544/#546).
  2. **This project's client-side pre-throttle**: `core/rate_limiter.py::OrgRateLimiter`, a per-org token bucket gated via `APIHelper`/`collector.rate_limiter.acquire(org_id, endpoint)` (see `core/api_helpers.py`) — **not** part of this module. Defaults come from `APISettings`: `rate_limit_requests_per_second=10.0`, `rate_limit_burst=20`, `rate_limit_shared_fraction=0.8`, `rate_limit_jitter_ratio=0.1`; toggle via `rate_limit_enabled`.
- **Authentication**: `MerakiSettings.api_key` is a Pydantic `SecretStr`; `.get_secret_value()` is only ever called once, inside `_create_api_client()`. Never log it. `api_base_url` defaults to `https://api.meraki.com/api/v1` but supports regional endpoints.
- **Error handling**: Network timeouts and API errors are common - always use decorators, and wrap responses with `validate_response_format` to normalize the SDK exhausted-retry error shape
- **Meraki SDK 3.2.0** (`pyproject.toml`; upgraded 2.2.0 -> 3.1.0 -> 3.2.0): `_create_api_client()` passes `validate_kwargs=settings.api.validate_kwargs` (`APISettings.validate_kwargs`, default `False`); set `True` in dev/CI to surface SDK warnings about unrecognized kwargs.
- **Network fetches**: Collectors must NOT call the SDK's `getOrganizationNetworks` directly — go through `OrganizationInventory.get_networks(org_id)` so `NetworkFilter` is applied. `AsyncMerakiClient` has no network-fetching convenience methods (removed along with the rest of its higher-level API, see file_map); `services/inventory.py` calls the raw `self.api.organizations.getOrganizationNetworks` under its own decorators, and `core/api_helpers.py::APIHelper._fetch_networks_direct` is a third sanctioned direct-call site (fallback used only when `self.collector.inventory` is `None`; it manually reapplies `NetworkFilter`).
</critical_notes>

<file_map>
## API COMPONENTS
- `client.py` - `AsyncMerakiClient` (not `MerakiClient` - there is no class by that name). Today it does exactly one thing: **thread-safe lazy construction** of the real `meraki.DashboardAPI` instance (`_get_api_client()`/`_create_api_client()`, exposed via the `.api` property). `app.py` creates one `AsyncMerakiClient` per process and hands its `.api` (the raw SDK client) to every collector as `MetricCollector.api` - this is what *every* collector and `services/inventory.py` call through, directly, via `asyncio.to_thread()` (see paved path below). It previously also exposed higher-level convenience methods (`get_organizations`, `get_networks`, `get_devices`, `get_sensor_readings_latest`, etc.) routed through an internal `_request()` retry wrapper, but those were unused by any production code path and were deleted (commit `836a6f3`); `tests/test_api_client.py` now only covers initialization, the `.api` property, and `close()`.
- Official Meraki SDK controllers actually exercised via `self.api.<controller>...` in collectors today: `organizations`, `networks`, `wireless` (MR), `switch` (MS), `appliance` (MX), `sensor` (MT), `cellularGateway` (MG, via `mg.py::collect_uplink_statuses`), `camera` (MV, via `mv.py`'s zones/live-analytics/quality-retention calls). MG/MV are fully implemented, not stubs — see `collectors/devices/CLAUDE.md`.
</file_map>

<paved_path>
## API USAGE PATTERN
```python
import asyncio
from ..core.logging_decorators import log_api_call
from ..core.error_handling import (
    validate_response_format,
    with_error_handling,
)


@with_error_handling(operation="Fetch devices", continue_on_error=True)
@log_api_call("getOrganizationDevices")
async def _fetch_devices(self, org_id: str) -> list[Device]:
    self._track_api_call("getOrganizationDevices")
    raw = await asyncio.to_thread(
        self.api.organizations.getOrganizationDevices,
        org_id,
        total_pages="all",
    )
    devices_data = validate_response_format(
        raw, expected_type=list, operation="getOrganizationDevices"
    )
    return [Device.model_validate(device) for device in devices_data]
```
</paved_path>

<api_quirks>
- **Pagination**: Not all endpoints support `total_pages` parameter (e.g., memory usage history doesn't)
- **Response formats**: Some wrap in `{"items": [...]}`, others return arrays directly
- **Timespan constraints**: Client overview requires exactly 3600 second timespan
- **Timeouts**: API calls can take 30+ seconds for large datasets
- **Product filtering**: Use `product_types` parameter to filter devices by type
</api_quirks>

<workflow>
## ADDING NEW API INTEGRATION
1. **Identify endpoint** in Meraki API docs
2. **Test response format**: Array or wrapped object?
3. **Add decorators**: `@log_api_call()` and `@with_error_handling()`
4. **Add tracking**: `self._track_api_call()`
5. **Handle pagination**: Use `total_pages="all"` if supported
6. **Normalize responses**: Wrap with `validate_response_format(...)` before parsing — handles `{"items": [...]}` and surfaces SDK retry-exhausted errors as `RetryableAPIError`/`DataValidationError`.
7. **Validate responses**: Use domain models with `model_validate()`
8. **For network-scoped fetches**: Get the network list from `OrganizationInventory.get_networks(org_id)` — never call `getOrganizationNetworks` directly.
</workflow>

<fatal_implications>
- **NEVER call API synchronously** - always use `asyncio.to_thread()`
- **NEVER log API keys** or sensitive authentication data
- **NEVER skip error handling** - API calls frequently fail
- **NEVER assume response format** - validate with `validate_response_format` before processing
- **NEVER call `getOrganizationNetworks` from a collector** - go through `OrganizationInventory.get_networks(org_id)` so `NetworkFilter` is enforced
</fatal_implications>
