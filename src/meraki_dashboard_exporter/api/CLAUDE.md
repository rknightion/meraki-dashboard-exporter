<system_context>
Meraki API Client - Provides authenticated access to Cisco Meraki Dashboard API with rate limiting, error handling, and response validation. Wraps the official Meraki SDK with additional monitoring capabilities.
</system_context>

<critical_notes>
- **Route every Dashboard SDK operation through `core.api_facade.facade_for(owner).call(...)`.**
  The SDK is synchronous, and `MerakiApiFacade` is the only production seam that may cross into it:
  it acquires the inherited per-org limiter, runs the call on the bounded executor, applies the
  per-fetch deadline, meters attempts, and owns bounded 429 retries. Direct `asyncio.to_thread()` or
  `run_in_executor()` SDK calls bypass that contract and are forbidden.
- **Rate limiting is two independent layers**, neither hardcoded to "5/s":
  1. **429 retry: single owner is the facade, not the SDK (#545).** `_create_api_client()` passes
     `wait_on_rate_limit=False`; `MerakiApiFacade.call()` honours capped `Retry-After`, otherwise
     uses jittered exponential backoff, and bounds attempts to `1 + max_retries`. SDK connection/5xx
     retries remain bounded by `maximum_retries`. Calls use `AsyncMerakiClient.executor`, installed
     as the loop default executor, and every logical fetch is bounded by
     `APISettings.per_fetch_deadline_seconds`.
  2. **Client-side pre-throttle**: `core/rate_limiter.py::OrgRateLimiter`, a per-org token bucket
     acquired by `MerakiApiFacade` for every attempt. Defaults are 10 requests/s, burst 10, shared
     fraction 0.8, and jitter ratio 0.1; toggle via `APISettings.rate_limit_enabled`.
- **Authentication**: `MerakiSettings.api_key` is a Pydantic `SecretStr`; `.get_secret_value()` is only ever called once, inside `_create_api_client()`. Never log it. `api_base_url` defaults to `https://api.meraki.com/api/v1` but supports regional endpoints.
- **Error handling**: Network timeouts and API errors are common - always use decorators, and wrap responses with `validate_response_format` to normalize the SDK exhausted-retry error shape
- **Meraki SDK 4.5.0** is exactly pinned in `pyproject.toml` (Renovate owns bumps):
  `_create_api_client()` passes `validate_kwargs=settings.api.validate_kwargs`
  (`APISettings.validate_kwargs`, default `False`); set it `True` in dev/CI to surface warnings.
- **Network fetches**: Collectors must NOT call the SDK's `getOrganizationNetworks` directly — go
  through `OrganizationInventory.get_networks(org_id)` so `NetworkFilter` is applied. Inventory and
  the two inventory-unavailable filtered fallbacks still route their sanctioned SDK operations
  through the facade; only `DiscoveryService` deliberately requests the unfiltered inventory.
</critical_notes>

<file_map>
## API COMPONENTS
- `client.py` - `AsyncMerakiClient` (there is no `MerakiClient` class): thread-safe lazy
  construction of `meraki.DashboardAPI`, the Meraki-owned redirect-auth boundary, the dedicated SDK
  executor, compatibility metrics, and bounded shutdown. `app.py` creates one per process and passes
  its raw `.api` handle to collectors; collectors pass SDK method objects to `MerakiApiFacade`, which
  is responsible for executing them.
- Official Meraki SDK controllers actually exercised via `self.api.<controller>...` in collectors today: `organizations`, `networks`, `wireless` (MR), `switch` (MS), `appliance` (MX), `sensor` (MT), `cellularGateway` (MG, via `mg.py::collect_uplink_statuses`), `camera` (MV, via `mv.py`'s zones/live-analytics/quality-retention calls), and `insight` (the disabled-by-default `InsightCollector`). MG/MV are fully implemented, not stubs — see `collectors/devices/CLAUDE.md`.
</file_map>

<paved_path>
## API USAGE PATTERN
```python
from ..core.api_facade import facade_for
from ..core.logging_decorators import log_api_call
from ..core.error_handling import (
    validate_response_format,
    with_error_handling,
)


@with_error_handling(operation="Fetch devices", continue_on_error=True)
@log_api_call("getOrganizationDevices")
async def _fetch_devices(self, org_id: str) -> list[Device]:
    self._track_api_call("getOrganizationDevices")
    raw = await facade_for(self).call(
        "getOrganizationDevices",
        self.api.organizations.getOrganizationDevices,
        org_id,
        org_id=org_id,
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
- **NEVER call a Dashboard SDK operation directly** - pass it through `facade_for(self).call(...)`
- **NEVER log API keys** or sensitive authentication data
- **NEVER skip error handling** - API calls frequently fail
- **NEVER assume response format** - validate with `validate_response_format` before processing
- **NEVER call `getOrganizationNetworks` from a collector** - go through `OrganizationInventory.get_networks(org_id)` so `NetworkFilter` is enforced
</fatal_implications>
