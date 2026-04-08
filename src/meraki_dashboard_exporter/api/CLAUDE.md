<system_context>
Meraki API Client - Provides authenticated access to Cisco Meraki Dashboard API with rate limiting, error handling, and response validation. Wraps the official Meraki SDK with additional monitoring capabilities.
</system_context>

<critical_notes>
- **Use `asyncio.to_thread()`** for all API calls - Meraki SDK is synchronous
- **Rate limiting**: 5 calls per second per organization
- **Authentication**: API key stored securely, never logged
- **Error handling**: Network timeouts and API errors are common - always use decorators
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
from ..core.error_handling import with_error_handling

@with_error_handling("Fetch devices", continue_on_error=True)
@log_api_call("getOrganizationDevices")
async def _fetch_devices(self, org_id: str) -> list[Device]:
    self._track_api_call("getOrganizationDevices")
    devices_data = await asyncio.to_thread(
        self.api.organizations.getOrganizationDevices,
        org_id,
        total_pages="all",
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
6. **Validate responses**: Use domain models with `model_validate()`
</workflow>

<fatal_implications>
- **NEVER call API synchronously** - always use `asyncio.to_thread()`
- **NEVER log API keys** or sensitive authentication data
- **NEVER skip error handling** - API calls frequently fail
- **NEVER assume response format** - validate structure before processing
</fatal_implications>
