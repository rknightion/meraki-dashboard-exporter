# Metric Collection Strategies

## Overview

These patterns reflect the current collection architecture after the refactor. They balance freshness, bounded concurrency, caching, and metric lifecycle management.

## Update Tiers

### FAST Tier (60 seconds)
**Purpose**: Real-time metrics that must stay fresh (e.g., MT sensors).  
**Collector**: `MTSensorCollector`  
**Notes**: Uses cached inventory lookups but minimal batching to keep latency low.

### MEDIUM Tier (300 seconds / 5 minutes)
**Purpose**: Operational metrics aligned with Meraki 5-minute aggregation windows.  
**Collectors**: `DeviceCollector`, `NetworkHealthCollector`, `OrganizationCollector`, `AlertsCollector`, `ClientsCollector` (when enabled).  
**Notes**: Runs with bounded parallelism across orgs using `ManagedTaskGroup`.

### SLOW Tier (900 seconds / 15 minutes)
**Purpose**: Configuration and slowly changing administrative data.  
**Collector**: `ConfigCollector`.

## Core Patterns

### Managed Concurrency
Use `ManagedTaskGroup` to bound concurrency to `settings.api.concurrency_limit` rather than raw `asyncio.gather`:

```python
async def _collect_impl(self) -> None:
    organizations = await self.inventory.get_organizations()
    async with ManagedTaskGroup(max_concurrency=self.settings.api.concurrency_limit) as group:
        for org in organizations:
            await group.create_task(self._process_org(org.id), name=f"org-{org.id}")
```

### Cached Inventory
Always fetch organizations/networks/devices via the shared inventory service to avoid redundant API calls:

```python
organizations = await self.inventory.get_organizations()
networks = await self.inventory.get_networks(org.id)
devices = await self.inventory.get_devices(org.id, network_id=network.id)
```

### Batch Processing
When iterating large lists, batch with the configured sizes and delays (`settings.api.*_batch_size`, `settings.api.batch_delay`):

```python
for i in range(0, len(devices), self.settings.api.device_batch_size):
    batch = devices[i : i + self.settings.api.device_batch_size]
    async with ManagedTaskGroup(max_concurrency=self.settings.api.concurrency_limit) as group:
        for device in batch:
            await group.create_task(self._collect_device(device))
    await asyncio.sleep(self.settings.api.batch_delay)
```

### Safe Metric Writes
Use `_set_metric()` (or `_set_metric_value`) so metric expiration tracking can remove stale series automatically:

```python
labels = {LabelName.ORG_ID.value: org_id, LabelName.SERIAL.value: device.serial}
status = 1.0 if device.status == "online" else 0.0
self._set_metric(self.device_up, labels, status, DeviceMetricName.DEVICE_UP)
```

## Optimization Strategies

1. **Reuse inventory first**: It is already populated per tier; avoid direct API calls for org/network/device lists.
2. **Respect batching knobs**: `*_BATCH_SIZE` and `BATCH_DELAY` keep rate limits healthy.
3. **Timeouts and retries**: Collector runs are capped by `MERAKI_EXPORTER_COLLECTORS__COLLECTOR_TIMEOUT`; the API client retries 429s with backoff.
4. **Continue on error**: Wrap expensive calls with `with_error_handling(..., continue_on_error=True)` to isolate failures.
5. **Validate responses**: Use `validate_response_format` or Pydantic models to avoid processing malformed data.
6. **Mind cardinality**: Prefer stable label sets and leverage `/cardinality` when introducing new labels.

## Best Practices

- Use MetricName/LabelName enums—never hardcode strings.
- Keep MEDIUM a multiple of FAST and adjust SLOW only when necessary.
- Log collection summaries at INFO and progress at DEBUG using existing decorators.
- Prefer early returns over deep nesting in collectors.
- Add tests for new metrics and keep `docs/metrics/metrics.md` in sync via the generator script.
