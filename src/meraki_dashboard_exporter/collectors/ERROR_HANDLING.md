# Error Handling Convention

## When to use `@with_error_handling()` decorator

- All methods that make API calls (directly or via `asyncio.to_thread`)
- All top-level `_collect_impl()` and `collect()` methods
- Parameters: `continue_on_error=True` for non-critical collectors, appropriate `ErrorCategory`

## When to use manual `try/except`

Only for specific recovery logic that cannot be expressed via decorator parameters:

- **404 fallback**: When an API returns 404 for a valid but empty state (e.g., org has no licenses)
- **Response format branching**: When different response shapes require different processing
- **Partial success**: When processing a batch where individual items can fail independently

In these cases, still use the decorator on the outer method and manual handling inside.

## Examples

### Decorator (standard):

```python
@with_error_handling(
    operation="Fetch devices",
    continue_on_error=True,
    error_category=ErrorCategory.API_CLIENT_ERROR,
)
async def _fetch_devices(self, org_id: str) -> list | None:
    ...
```

### Manual (404 recovery):

```python
@with_error_handling(operation="Collect licenses", continue_on_error=True)
async def collect(self, org_id: str, org_name: str) -> None:
    try:
        overview = await self._fetch_licenses(org_id)
        self._process(overview)
    except Exception as e:
        if "404" in str(e):
            logger.debug("No licensing info for org", org_id=org_id)
        else:
            raise  # Let decorator handle non-404 errors
```
