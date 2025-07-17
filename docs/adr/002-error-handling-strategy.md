# ADR-002: Error Handling Strategy

**Status**: Accepted
**Date**: 2024-01-15
**Decision Makers**: Development Team

## Context

The exporter needs to handle various types of errors gracefully:
- API rate limits (429 errors)
- Temporary API unavailability (503 errors)
- Missing API endpoints (404 errors)
- Network timeouts
- Invalid data formats

Errors should not crash the exporter, and we need visibility into error patterns.

## Decision

We will use a decorator-based error handling strategy with error categorization:

### Error Categories
```python
class ErrorCategory(Enum):
    API_RATE_LIMIT = "rate_limit"      # 429 errors
    API_CLIENT_ERROR = "client_error"   # 4xx errors
    API_SERVER_ERROR = "server_error"   # 5xx errors
    API_NOT_AVAILABLE = "not_available" # 404 (endpoint doesn't exist)
    TIMEOUT = "timeout"                 # Operation timeouts
    PARSING = "parsing"                 # Data format errors
    VALIDATION = "validation"           # Data validation failures
```

### Error Handling Decorator
```python
@with_error_handling(
    operation="Fetch devices",
    continue_on_error=True,  # Return None instead of raising
    error_category=ErrorCategory.API_SERVER_ERROR,
)
async def _fetch_devices(self, org_id: str) -> list[Device] | None:
    # Implementation
```

### When to Use Each Pattern

#### continue_on_error=True
Use when:
- Partial data collection is acceptable
- Error affects only one organization/network
- 404 errors for optional endpoints

Example scenarios:
- Alerts API not available for some organizations
- Single device failing shouldn't stop all collection

#### continue_on_error=False
Use when:
- Data is critical for subsequent operations
- Error indicates system-wide problem
- Initial setup/discovery phase

Example scenarios:
- Cannot fetch organizations list
- Authentication failures

## Consequences

### Positive
- Consistent error handling across collectors
- Automatic error metrics via `_track_error()`
- Clear error categorization for monitoring
- Graceful degradation

### Negative
- Decorator adds slight overhead
- Must remember to validate responses
- Silent failures possible if not monitored

## Implementation Guidelines

1. **Always validate API responses**:
```python
devices = validate_response_format(
    devices,
    expected_type=list,
    operation="getOrganizationDevices"
)
```

2. **Use specific error categories**:
- Don't default to PARSING for all errors
- 404 → API_NOT_AVAILABLE
- Timeout → TIMEOUT
- JSON errors → PARSING

3. **Log context in errors**:
- Include org_id, network_id, device serial
- Use structured logging fields

4. **Monitor error metrics**:
- Set alerts on `meraki_collector_errors_total`
- Group by error_type label
