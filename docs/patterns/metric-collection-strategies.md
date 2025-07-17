# Metric Collection Strategies

## Overview

This document explains the different strategies used for collecting metrics efficiently while respecting API limits and data freshness requirements.

## Update Tiers

### FAST Tier (60 seconds)
**Purpose**: Real-time or near real-time metrics that change frequently.

**Metrics**:
- MT sensor readings (temperature, humidity, CO2, etc.)
- Environmental conditions that need quick alerting

**Strategy**:
```python
@register_collector(UpdateTier.FAST)
class MTSensorCollector(MetricCollector):
    """Collects frequently-changing sensor data."""
```

**Rationale**:
- Sensor data can trigger alerts (e.g., temperature threshold)
- 60s aligns with typical monitoring dashboards
- API can handle this frequency for sensor endpoints

### MEDIUM Tier (300 seconds / 5 minutes)
**Purpose**: Operational metrics aligned with Meraki's data aggregation.

**Metrics**:
- Device status and availability
- Client counts and usage
- Network health metrics
- Wireless performance data
- Alert states

**Strategy**:
```python
@register_collector(UpdateTier.MEDIUM)
class DeviceCollector(MetricCollector):
    """Collects device operational metrics."""
```

**Rationale**:
- Meraki aggregates data in 5-minute windows
- Balances freshness with API efficiency
- Most operational decisions work with 5-minute granularity

### SLOW Tier (900 seconds / 15 minutes)
**Purpose**: Configuration and slowly-changing administrative data.

**Metrics**:
- License information
- Configuration change tracking
- API usage statistics
- Organization settings

**Strategy**:
```python
@register_collector(UpdateTier.SLOW)
class ConfigCollector(MetricCollector):
    """Collects configuration metrics."""
```

**Rationale**:
- Configuration rarely changes
- Reduces unnecessary API calls
- Still fresh enough for compliance monitoring

## Collection Patterns

### 1. Batch Collection Pattern
Used when collecting metrics for multiple items of the same type.

```python
async def _collect_impl(self) -> None:
    """Batch collection example."""
    organizations = await self._fetch_organizations()

    # Process in batches to avoid overwhelming API
    for i in range(0, len(devices), self.settings.api.batch_size):
        batch = devices[i:i + self.settings.api.batch_size]

        # Process batch concurrently
        async with ManagedTaskGroup("device_batch") as group:
            for device in batch:
                await group.create_task(
                    self._collect_device_metrics(device)
                )

        # Delay between batches
        if i + self.settings.api.batch_size < len(devices):
            await asyncio.sleep(self.settings.api.batch_delay)
```

### 2. Hierarchical Collection Pattern
Used when data has parent-child relationships.

```python
async def _collect_impl(self) -> None:
    """Hierarchical collection example."""
    # Level 1: Organizations
    for org in organizations:
        # Level 2: Networks
        networks = await self._fetch_networks(org["id"])

        for network in networks:
            # Level 3: Devices
            devices = await self._fetch_devices(network["id"])

            # Collect metrics at appropriate level
            self._set_network_metrics(network, len(devices))
```

### 3. Aggregation Pattern
Used when API provides pre-aggregated data.

```python
async def collect_client_overview(self, org_id: str) -> None:
    """Use pre-aggregated data from API."""
    # API returns aggregated client counts
    overview = await self.api.organizations.getOrganizationClientsOverview(
        org_id,
        timespan=300  # Last 5 minutes
    )

    # Direct mapping to metrics
    self._clients_count.labels(
        org_id=org_id,
        client_type="wireless"
    ).set(overview["counts"]["wireless"])
```

### 4. Time-Series Collection Pattern
Used for historical data with time windows.

```python
async def collect_usage_history(self, serial: str) -> None:
    """Collect time-series data."""
    # Get last 5 minutes of data
    usage = await self.api.devices.getDeviceUsageHistory(
        serial,
        timespan=300
    )

    # Process latest data point
    if usage:
        latest = usage[-1]  # Most recent
        self._set_usage_metrics(serial, latest)
```

## Optimization Strategies

### 1. Caching for Slowly-Changing Data
```python
class DeviceCollector:
    def __init__(self):
        self._device_cache: dict[str, Device] = {}
        self._cache_timestamp = 0

    async def _get_devices(self, org_id: str) -> list[Device]:
        # Cache for 5 minutes
        if time.time() - self._cache_timestamp < 300:
            return list(self._device_cache.values())

        devices = await self._fetch_devices(org_id)
        self._update_cache(devices)
        return devices
```

### 2. Conditional Collection
Skip collection when data won't have changed:

```python
async def collect_licenses(self, org_id: str) -> None:
    """Only collect if sufficient time has passed."""
    last_check = self._last_license_check.get(org_id, 0)

    # Skip if checked recently (within 1 hour)
    if time.time() - last_check < 3600:
        logger.debug("Skipping license check", org_id=org_id)
        return

    # Proceed with collection
    licenses = await self._fetch_licenses(org_id)
    self._last_license_check[org_id] = time.time()
```

### 3. Partial Failure Handling
Continue collection even if some items fail:

```python
async def collect_all_devices(self) -> None:
    """Collect with partial failure tolerance."""
    success_count = 0
    error_count = 0

    for device in devices:
        try:
            await self._collect_device_metrics(device)
            success_count += 1
        except Exception as e:
            error_count += 1
            logger.warning(
                "Failed to collect device metrics",
                serial=device["serial"],
                error=str(e)
            )

    logger.info(
        "Device collection complete",
        success=success_count,
        errors=error_count
    )
```

## Choosing the Right Strategy

### Use FAST Tier When:
- Data changes rapidly (< 5 minutes)
- Real-time alerting is needed
- API endpoint supports high frequency

### Use MEDIUM Tier When:
- Data aligns with 5-minute aggregation
- Operational monitoring use case
- Balance between freshness and efficiency

### Use SLOW Tier When:
- Data rarely changes
- Configuration or administrative data
- API calls are expensive

### Use Batch Collection When:
- Many similar items to process
- Independent operations
- Need to manage API rate limits

### Use Hierarchical Collection When:
- Data has natural parent-child relationships
- Need organizational context
- Metrics aggregate up the hierarchy

## Performance Considerations

1. **API Rate Limits**: Meraki allows 10 requests/second per org
2. **Memory Usage**: Large batches consume more memory
3. **Timeout Risk**: Long-running collections may timeout
4. **Error Propagation**: Partial failures shouldn't stop all collection

## Best Practices

1. **Always use error handling decorators**
2. **Log collection summaries at INFO level**
3. **Track API calls for rate limit monitoring**
4. **Validate API responses before processing**
5. **Use appropriate batch sizes (10-50 items)**
6. **Add delays between batches**
7. **Consider caching for expensive operations**
8. **Monitor collector performance metrics**
