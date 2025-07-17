# API Response Format Handling

## Overview

The Meraki API returns data in different formats depending on the endpoint. This document explains the patterns used to handle these variations consistently.

## Response Formats

### 1. Direct Array Response
Most endpoints return arrays directly:
```python
# Response: [{"id": "123", "name": "Device1"}, ...]
devices = await api.devices.getOrganizationDevices(org_id)
```

### 2. Wrapped Response
Some endpoints wrap data in an object:
```python
# Response: {"items": [{"id": "123", "name": "Device1"}, ...]}
response = await api.some.getEndpointWithPagination(org_id)
devices = response["items"]
```

### 3. Paginated Response
Endpoints supporting pagination may return metadata:
```python
# Response: {
#   "items": [...],
#   "meta": {"page": 1, "total": 100}
# }
```

## Standard Handling Pattern

Use this pattern to handle both formats:

```python
# Generic pattern
if isinstance(response, dict) and "items" in response:
    data = response["items"]
elif isinstance(response, list):
    data = response
else:
    logger.warning(
        "Unexpected response format",
        response_type=type(response).__name__,
    )
    data = []
```

## Helper Function Example

```python
def extract_items(response: Any) -> list[dict[str, Any]]:
    """Extract items from API response regardless of format.

    Parameters
    ----------
    response : Any
        API response (list or dict with 'items')

    Returns
    -------
    list[dict[str, Any]]
        Extracted items

    Examples
    --------
    >>> # Direct array
    >>> extract_items([{"id": "1"}, {"id": "2"}])
    [{"id": "1"}, {"id": "2"}]

    >>> # Wrapped response
    >>> extract_items({"items": [{"id": "1"}]})
    [{"id": "1"}]
    """
    if isinstance(response, dict) and "items" in response:
        return response["items"]
    elif isinstance(response, list):
        return response
    else:
        logger.warning(f"Unexpected format: {type(response)}")
        return []
```

## Specific Endpoints

### Known Wrapped Endpoints
- Some paginated endpoints when using `total_pages='all'`
- Future endpoints may adopt this pattern

### Always Direct Array
- `getOrganizations`
- `getOrganizationNetworks`
- `getOrganizationDevices`
- Most device-specific endpoints

## Best Practices

1. **Always validate response format** - Don't assume format
2. **Log unexpected formats** - Helps identify API changes
3. **Use type annotations** - Clarify expected types
4. **Consider using Pydantic models** - Automatic validation

## Integration with Error Handling

```python
from ..core.error_handling import validate_response_format

# Validates and logs if format is unexpected
devices = validate_response_format(
    response,
    expected_type=list,
    operation="getOrganizationDevices"
)
```

## Why This Pattern Exists

1. **API Evolution** - Meraki API has evolved over time
2. **Pagination Support** - Wrapped format supports metadata
3. **Backward Compatibility** - Must support both formats
4. **Future Proofing** - New endpoints may use either format
