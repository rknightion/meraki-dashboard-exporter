<system_context>
Meraki API Client - Provides authenticated access to Cisco Meraki Dashboard API with rate limiting, error handling, and response validation. Wraps the official Meraki SDK with additional monitoring capabilities.
</system_context>

<critical_notes>
- **Use `asyncio.to_thread()`** for all API calls - Meraki SDK is synchronous
- **Rate limiting**: 5 calls per second per organization
- **Authentication**: API key stored securely, never logged
- **Error handling**: Network timeouts and API errors are common - always use decorators, and wrap responses with `validate_response_format` to normalize the SDK exhausted-retry error shape
- **Meraki SDK 3.1.0** (upgraded from 2.2.0): `MerakiClient` honors `APISettings.validate_kwargs` (default `False`); set to `True` in dev/CI to surface unrecognized kwargs warnings from the SDK.
- **Network fetches**: Collectors must NOT call the SDK's `getOrganizationNetworks` directly — go through `OrganizationInventory.get_networks(org_id)` so `NetworkFilter` is applied. The wrapper's `AsyncMerakiClient.get_networks` exists for inventory's own use.
</critical_notes>

<file_map>
## API COMPONENTS
- `client.py` - Main `MerakiClient` wrapper with authentication and monitoring
- Official Meraki SDK controllers accessed via client instance:
  - `wireless` - MR device operations
  - `switch` - MS device operations
  - `appliance` - MX device operations
  - `sensor` - MT sensor operations
  - `cellularGateway` - MG gateway operations
  - `camera` - MV camera operations
  - `organizations` - Organization-level operations
  - `networks` - Network-level operations
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


@with_error_handling("Fetch devices", continue_on_error=True)
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
