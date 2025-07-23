<system_context>
Meraki API Client - Provides authenticated access to Cisco Meraki Dashboard API with rate limiting, error handling, and response validation. Wraps the official Meraki SDK with additional monitoring capabilities.
</system_context>

<critical_notes>
- **Use asyncio.to_thread()** for all API calls - Meraki SDK is synchronous
- **Rate limiting**: API has strict rate limits - monitor with tracking decorators
- **Authentication**: API key stored securely, never logged
- **Error handling**: Network timeouts and API errors are common
</critical_notes>

<file_map>
## API COMPONENTS
- `client.py` - Main MerakiClient wrapper with authentication and monitoring
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
## API CLIENT USAGE PATTERN
```python
import asyncio
from ..core.logging_decorators import log_api_call

class SomeCollector(MetricCollector):
    @log_api_call("getOrganizationDevices")
    async def _fetch_devices(self, org_id: str) -> list[Device]:
        self._track_api_call("getOrganizationDevices")

        # Always use asyncio.to_thread for API calls
        devices_data = await asyncio.to_thread(
            self.api.organizations.getOrganizationDevices,
            org_id,
            total_pages="all"  # When supported
        )

        return [Device.model_validate(device) for device in devices_data]
```

## ERROR HANDLING WITH API CALLS
```python
from ..core.error_handling import with_error_handling, ErrorCategory

@with_error_handling(
    operation="Fetch organization data",
    continue_on_error=True,
    error_category=ErrorCategory.API_SERVER_ERROR
)
async def _fetch_organization_data(self, org_id: str) -> dict | None:
    try:
        return await asyncio.to_thread(
            self.api.organizations.getOrganization,
            org_id
        )
    except Exception as e:
        self.logger.error(f"API call failed: {e}")
        return None
```
</paved_path>

<patterns>
## COMMON API PATTERNS

### Pagination Handling
```python
# For endpoints that support total_pages
data = await asyncio.to_thread(
    self.api.organizations.getOrganizationDevices,
    org_id,
    total_pages="all"
)

# For endpoints without total_pages support
data = await asyncio.to_thread(
    self.api.organizations.getOrganizationDevicesSystemMemoryUsageHistoryByInterval,
    org_id,
    interval=3600,
    timespan=3600
    # NO total_pages parameter
)
```

### Response Format Variations
```python
# Some endpoints return arrays directly
devices = await asyncio.to_thread(
    self.api.organizations.getOrganizationDevices,
    org_id
)

# Others wrap in {"items": [...]}
response = await asyncio.to_thread(
    self.api.some_endpoint,
    org_id
)
items = response.get("items", []) if isinstance(response, dict) else response
```

### Timespan Parameters
```python
# Most endpoints use timespan in seconds
data = await asyncio.to_thread(
    self.api.wireless.getOrganizationWirelessDevicesChannelUtilization,
    org_id,
    timespan=3600  # 1 hour
)

# Client overview requires exactly 3600 seconds
client_data = await asyncio.to_thread(
    self.api.organizations.getOrganizationClientsOverview,
    org_id,
    timespan=3600  # Must be exactly 1 hour
)
```
</patterns>

<examples>
## Complete API Client Usage Example
```python
import asyncio
from typing import Optional
from ..core.logging_decorators import log_api_call
from ..core.error_handling import with_error_handling, ErrorCategory
from ..core.domain_models import Device, Organization

class ExampleCollector(MetricCollector):
    """Example showing proper API client usage patterns"""

    @with_error_handling("Fetch organizations", continue_on_error=False)
    @log_api_call("getOrganizations")
    async def _get_organizations(self) -> list[Organization]:
        """Get all organizations for the API key"""
        self._track_api_call("getOrganizations")

        try:
            orgs_data = await asyncio.to_thread(
                self.api.organizations.getOrganizations
            )

            return [Organization.model_validate(org) for org in orgs_data]

        except Exception as e:
            self.logger.error(f"Failed to fetch organizations: {e}")
            raise

    @with_error_handling("Fetch devices", continue_on_error=True)
    @log_api_call("getOrganizationDevices")
    async def _fetch_devices(self, org_id: str, product_types: Optional[list[str]] = None) -> list[Device]:
        """Fetch devices for organization, optionally filtered by product type"""
        self._track_api_call("getOrganizationDevices")

        try:
            params = {"total_pages": "all"}
            if product_types:
                params["product_types"] = product_types

            devices_data = await asyncio.to_thread(
                self.api.organizations.getOrganizationDevices,
                org_id,
                **params
            )

            return [Device.model_validate(device) for device in devices_data]

        except Exception as e:
            self.logger.error(f"Failed to fetch devices for org {org_id}: {e}")
            return []

    @log_api_call("getOrganizationWirelessDevicesChannelUtilization")
    async def _fetch_channel_utilization(self, org_id: str) -> dict:
        """Fetch wireless channel utilization data"""
        self._track_api_call("getOrganizationWirelessDevicesChannelUtilization")

        try:
            return await asyncio.to_thread(
                self.api.wireless.getOrganizationWirelessDevicesChannelUtilization,
                org_id,
                total_pages="all",
                timespan=3600
            )
        except Exception as e:
            self.logger.error(f"Failed to fetch channel utilization: {e}")
            return {}
```
</examples>

<api_quirks>
## MERAKI API LIMITATIONS & QUIRKS
- **Rate limits**: 5 calls per second per organization
- **Timeouts**: API calls can take 30+ seconds for large datasets
- **Pagination**: Not all endpoints support `total_pages` parameter
- **Response formats**: Some wrap in `{"items": [...]}`, others return arrays directly
- **Timespan constraints**: Client overview requires exactly 3600 second timespan
- **Product filtering**: Use `product_types` parameter to filter devices by type
- **Memory API**: `getOrganizationDevicesSystemMemoryUsageHistoryByInterval` doesn't support `total_pages`
</api_quirks>

<workflow>
## ADDING NEW API INTEGRATION
1. **Identify endpoint**: Check Meraki API documentation for endpoint details
2. **Test response format**: Check if response is array or wrapped object
3. **Add logging decorator**: Use `@log_api_call()` with endpoint name
4. **Add API tracking**: Use `self._track_api_call()` for monitoring
5. **Handle pagination**: Use `total_pages="all"` if supported
6. **Add error handling**: Use `@with_error_handling()` decorator
7. **Validate responses**: Use domain models for response validation
</workflow>

<fatal_implications>
- **NEVER call API synchronously** - always use `asyncio.to_thread()`
- **NEVER log API keys** or sensitive authentication data
- **NEVER skip error handling** - API calls frequently fail
- **NEVER assume response format** - validate structure before processing
- **NEVER ignore rate limits** - monitor API call frequency
</fatal_implications>
