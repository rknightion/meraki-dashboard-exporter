# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a prometheus exporter that connects to the Cisco Meraki Dashboard API and exposes various metrics as a prometheus exporter. It also acts as an opentelemetry collector pushing metrics and logs to an OTEL endpoint.

## Development Patterns

We use the Meraki Dashboard Python API from https://github.com/meraki/dashboard-api-python
Meraki Dashboard API Docs are available at https://developer.cisco.com/meraki/api-v1/api-index/
We use uv for all python project management. New dependencies can be added with `uv add requests`
We use ruff for all python linting
We use mypy for all python type checking
We do all builds via docker and ensure first class docker support for running

## Domain Models

We use Pydantic models for API responses and internal data structures:
- **API Models** (`core/api_models.py`): Core models like Organization, Network, Device, DeviceStatus, etc.
- **Domain Models** (`core/domain_models.py`): Specific models for network health, device stats, sensor data, etc.
- **Always use domain models** instead of raw dictionaries when processing API responses
- Models include validation, computed fields, and type conversion
- Example: Use `ConnectionStats` instead of `dict[str, int]` for connection statistics


## Code Style

- **Formatting**: Black formatter with 88-char line length
- **Type hints**: from __future__ import annotations, TypeAlias, ParamSpec, Self, typing.NamedTuple(slots=True), typing.Annotated for units / constraints
- **Type definitions**: Use TypedDict from `core/type_definitions.py` for complex dictionary structures instead of dict[str, Any]
- **Pydantic models**: Use models from `core/api_models.py` and `core/domain_models.py` for API responses to ensure validation
- **Docstrings**: NumPy-docstrings + type hints
- **Constants**: Literal & Enum / StrEnum (Keep StrEnum for metric / label names; use Literal for tiny closed sets.)
- **Imports**: Group logically (stdlib, third-party, local)
- **Early returns**: Reduce nesting where possible
- **Metric Names**: ALWAYS use `MetricName` enum from constants.py instead of hardcoded strings
- **Label Names**: ALWAYS use `LabelName` enum from core/metrics.py for consistent label naming

## API Guidelines

- Use Meraki Python SDK (never direct HTTP)
- Use `total_pages='all'` for pagination when appropriate (not all endpoints support it)
- You are responsible for timekeeping and keeping data about the Meraki API up to date in our internal state (we do not wait for users to hit the exporter to update data)
- Be aware of API module organization - endpoints like `getOrganizationWirelessClientsOverviewByDevice` are in the `wireless` module, not `organizations`
- Memory metrics use the `getOrganizationDevicesSystemMemoryUsageHistoryByInterval` endpoint without `total_pages` parameter
- **Deprecated API Updates**:
  - Use `getOrganizationDevices` instead of deprecated `getNetworkDevices` - filter by networkIds and productTypes
  - Use `getOrganizationDevicesAvailabilities` instead of deprecated `getOrganizationDevicesStatuses`
  - The new APIs provide productType information which is exposed in metrics

## Metrics Guidelines
- Use asyncio + anyio; expose /metrics via a Starlette or FastAPI app; Prometheus client supports async.
- Early returns: Keep; combines neatly with match (PEP 636) for dispatching OTel signals.
- Logging: structlog configured with an OTLP JSON processor so logs and traces share context.
- Constants: class MetricName(StrEnum): HTTP_REQUESTS_TOTAL = "http_requests_total", avoiding scattered strings.
- **ALWAYS use MetricName enum**: All metric names must use the MetricName enum from constants.py
- **ALWAYS use LabelName enum**: All label names must use the LabelName enum from core/metrics.py
- Use MetricFactory from core/metrics.py for creating standardized metrics when appropriate

## Update Rings

The system uses three update tiers:
- **FAST** (60s): Sensor metrics (MT devices) - real-time environmental data
- **MEDIUM** (300s): Organization metrics (including client overview), Device metrics (including port traffic), Network health, Assurance alerts, Bluetooth clients - aligned with Meraki API 5-minute data blocks
- **SLOW** (900s/15 minutes): Configuration data, Login security settings - infrequently changing configuration data

## Known API Limitations

- CPU usage metrics are available for MR devices only (via getOrganizationWirelessDevicesSystemCpuLoadHistory)
- Uptime metrics are not available via API for any device types
- Channel utilization metrics are collected via network health collector, not per-device
- POE budget information is not available via API (would require model lookup tables)
- Switch power usage is approximated by summing POE port consumption

## API Quirks

- The sensor readings API may return both `temperature` and `rawTemperature` metric types for the same sensor
- We only process the documented `temperature` metric type and skip `rawTemperature` to avoid duplicate data
- All temperature values are collected in Celsius only (users can convert in Grafana if needed)

## Assurance Alerts

The alerts collector uses the `getOrganizationAssuranceAlerts` API to fetch active alerts:
- Only collects active alerts (not dismissed or resolved)
- Groups alerts by type, category, severity, device type, and network
- Provides summary metrics by severity and network for easier dashboarding
- Runs in MEDIUM tier (5 minutes) as alerts don't change frequently
- The API may not be available for all organizations (will log at DEBUG level if 404)

## Response Format Handling

Many Meraki API responses can return data in different formats:
- Some endpoints wrap data in `{"items": [...]}` format
- Others return arrays directly
- Always check response type and handle both cases

## Client Overview Metrics

The `getOrganizationClientsOverview` API returns usage data for the last complete 5-minute window:
- When called at 11:04, it returns data from 10:55-11:00 (not 10:59-11:04)
- Usage data is provided in KB (kilobytes), not Kbps or MB
- The metrics are suitable for Prometheus rate/increase functions to calculate data transfer rates

## Configuration Changes Metric

The `getOrganizationConfigurationChanges` API is used to track configuration changes:
- Uses `timespan=86400` to get changes from the last 24 hours
- Returns a count of all configuration changes made by administrators
- Runs in the SLOW tier (15 minutes) as configuration changes are infrequent
- Useful for compliance monitoring and change management

## Collector Architecture

The exporter uses a modular collector architecture where large collectors are split into focused sub-collectors:

### Device Collectors (`src/meraki_dashboard_exporter/collectors/`)
- **Main**: `device.py` - Coordinates all device-specific collectors (730 lines, down from 1,968)
- **Sub-collectors** (`devices/`):
  - `base.py` - BaseDeviceCollector with common functionality (includes memory collection for all devices)
  - `ms.py` - MSCollector for Meraki switches (owns all MS-specific metrics via `_initialize_metrics()`)
  - `mr.py` - MRCollector for Meraki access points (owns all MR-specific metrics via `_initialize_metrics()`, handles per-device and org-wide wireless metrics)
  - `mx.py` - MXCollector for Meraki security appliances
  - `mg.py` - MGCollector for Meraki cellular gateways
  - `mv.py` - MVCollector for Meraki security cameras
  - `mt.py` - MTCollector for Meraki sensors (also used by mt_sensor.py for FAST tier environmental metrics)

**Important Metric Ownership Pattern**:
- Device-specific metrics are owned by their respective collectors
- MR metrics (like `meraki_mr_clients_connected`) are defined in `MRCollector._initialize_metrics()`
- MS metrics (like `meraki_ms_port_status`) are defined in `MSCollector._initialize_metrics()`
- Common metrics (like `meraki_device_up`) remain in `DeviceCollector._initialize_metrics()`
- When adding new device types with specific metrics, create an `_initialize_metrics()` method and call it from `DeviceCollector.__init__()`

### Network Health Collectors (`src/meraki_dashboard_exporter/collectors/`)
- **Main**: `network_health.py` - Coordinates all network health collectors
- **Sub-collectors** (`network_health_collectors/`):
  - `base.py` - BaseNetworkHealthCollector with common functionality
  - `rf_health.py` - RFHealthCollector for channel utilization metrics
  - `connection_stats.py` - ConnectionStatsCollector for wireless connection statistics
  - `data_rates.py` - DataRatesCollector for network throughput metrics
  - `bluetooth.py` - BluetoothCollector for Bluetooth client detection

### Organization Collectors (`src/meraki_dashboard_exporter/collectors/`)
- **Main**: `organization.py` - Coordinates all organization-level collectors
- **Sub-collectors** (`organization_collectors/`):
  - `base.py` - BaseOrganizationCollector with common functionality
  - `api_usage.py` - APIUsageCollector for API request metrics
  - `license.py` - LicenseCollector for licensing metrics (supports both per-device and co-termination models)
  - `client_overview.py` - ClientOverviewCollector for client count and usage metrics

### Other Collectors
- `mt_sensor.py` - Fast-tier MT sensor metrics collector (temperature, humidity, etc.)
- `alerts.py` - Assurance alerts collector
- `config.py` - Configuration tracking metrics
- `manager.py` - Manages all collectors and their update schedules

### Adding New Collectors

#### Main Collectors (Auto-Registered)
Main collectors that inherit directly from `MetricCollector` are automatically registered using the `@register_collector` decorator:

```python
from ..core.collector import MetricCollector
from ..core.constants import UpdateTier
from ..core.registry import register_collector

@register_collector(UpdateTier.MEDIUM)  # Specify the update tier
class MyNewCollector(MetricCollector):
    """My new collector implementation."""

    def _initialize_metrics(self) -> None:
        # Initialize your metrics here
        pass

    async def _collect_impl(self) -> None:
        # Implement collection logic here
        pass
```

The decorator automatically registers the collector with the `CollectorManager`, eliminating the need for manual registration.

#### Sub-Collectors (Manual Registration)
Sub-collectors still require manual registration:
1. For device-specific metrics: Create a new file in `devices/` inheriting from BaseDeviceCollector
2. For network health metrics: Create a new file in `network_health_collectors/` inheriting from BaseNetworkHealthCollector
3. For organization metrics: Create a new file in `organization_collectors/` inheriting from BaseOrganizationCollector
4. Register the collector in the parent coordinator's `__init__` method
5. Add appropriate dispatching logic in the parent collector

### Enhanced Collector Capabilities
- **MRCollector**: Handles both per-device metrics (via `collect()`) and organization-wide wireless metrics:
  - `collect_wireless_clients()` - Client counts across all APs
  - `collect_ethernet_status()` - Power and port status for all APs
  - `collect_packet_loss()` - Packet loss metrics per device and network-wide
  - `collect_cpu_load()` - CPU utilization for all APs
  - `collect_ssid_status()` - SSID and radio configuration status
- **BaseDeviceCollector**: Now includes `collect_memory_metrics()` for all device types
- **MTCollector**: Handles both device metrics and sensor readings via `collect_sensor_metrics()`

## Testing and Validation

- Run linting: `uv run ruff check --fix .`
- Run type checking: `uv run mypy .`
- Generate metric documentation: `uv run python src/meraki_dashboard_exporter/tools/generate_metrics_docs.py`
- After making changes, restart the exporter process to load new code
- Check metrics at http://localhost:9099/metrics

## Integration Test Helpers

The exporter provides comprehensive test helpers in the `testing` module to simplify writing tests:

### Test Factories (`testing.factories`)

#### Data Factories
- `OrganizationFactory` - Create organization test data
- `NetworkFactory` - Create network test data
- `DeviceFactory` - Create device test data (with type-specific methods)
- `AlertFactory` - Create alert test data
- `SensorDataFactory` - Create sensor reading data
- `TimeSeriesFactory` - Create time series data
- `ResponseFactory` - Create API response formats (paginated, errors)

```python
from meraki_dashboard_exporter.testing.factories import (
    OrganizationFactory, NetworkFactory, DeviceFactory
)

# Create test data
org = OrganizationFactory.create(org_id="org_123")
networks = NetworkFactory.create_many(3, org_id=org["id"])
devices = DeviceFactory.create_mixed(6, network_id=networks[0]["id"])
```

### Mock API Builder (`testing.mock_api`)

Fluent interface for building mock API responses:

```python
from meraki_dashboard_exporter.testing.mock_api import MockAPIBuilder

api = (MockAPIBuilder()
    .with_organizations([org1, org2])
    .with_networks(networks, org_id="org_123")
    .with_devices(devices)
    .with_error("getOrganizationAlerts", 404)
    .with_custom_response("getDeviceClients", clients)
    .build())
```

### Metric Assertions (`testing.metrics`)

Helper class for asserting metric values:

```python
from meraki_dashboard_exporter.testing.metrics import MetricAssertions

metrics = MetricAssertions(registry)
metrics.assert_gauge_value("meraki_device_up", 1, serial="Q2KD-XXXX")
metrics.assert_counter_incremented("meraki_api_calls_total", endpoint="getDevices")
metrics.assert_metric_not_set("meraki_device_cpu_percent")
```

#### Metric Snapshots
Compare metrics before and after operations:

```python
from meraki_dashboard_exporter.testing.metrics import MetricSnapshot

before = MetricSnapshot(registry)
# ... do work ...
after = MetricSnapshot(registry)
diff = after.diff(before)
assert diff.counter_delta("api_calls_total", endpoint="getDevices") == 1
```

### Base Test Class (`testing.base`)

Base class with common fixtures and helpers:

```python
from meraki_dashboard_exporter.testing.base import BaseCollectorTest

class TestMyCollector(BaseCollectorTest):
    collector_class = MyCollector
    update_tier = UpdateTier.MEDIUM

    async def test_collection(self, collector, mock_api_builder, metrics):
        # mock_api_builder - MockAPIBuilder instance
        # metrics - MetricAssertions instance
        # collector - Your collector with isolated registry

        # Set up test data
        test_data = self.setup_standard_test_data(mock_api_builder)

        # Run collector
        await self.run_collector(collector)

        # Assert success
        self.assert_collector_success(collector, metrics)
        self.assert_api_call_tracked(collector, metrics, "getOrganizations")
```

### Best Practices for Testing

1. **Use factories for test data** - Consistent, realistic test data
2. **Use MockAPIBuilder** - Cleaner than manual mocking
3. **Inherit from BaseCollectorTest** - Automatic fixture setup
4. **Use MetricAssertions** - Clear metric verification
5. **Test error scenarios** - Use `.with_error()` to test failure handling
6. **Use snapshots for deltas** - Track metric changes during operations

## Deprecated/Removed Metrics

The following metrics have been removed or replaced:
- `meraki_mr_channel_utilization_percent` → replaced by `meraki_ap_channel_utilization_2_4ghz_percent` and `meraki_ap_channel_utilization_5ghz_percent`
- `meraki_device_cpu_usage_percent` → removed (not available via API)
- `meraki_device_uptime_seconds` → removed (not available via API)

## Collector Internal Metrics

The base collector automatically tracks performance metrics:
- `meraki_collector_duration_seconds` - Histogram of time spent collecting metrics (includes _bucket, _count, _sum)
- `meraki_collector_errors_total` - Counter of collector errors
- `meraki_collector_last_success_timestamp_seconds` - Gauge with Unix timestamp of last successful collection
- `meraki_collector_api_calls_total` - Counter of API calls made

These metrics are populated automatically when collectors run and should be used for monitoring the health of the exporter itself.

**Note on Prometheus Counter/Histogram Metrics:**
- Counters and Histograms automatically generate a `_created` metric with Unix timestamp of when the metric was first observed
- This is standard Prometheus behavior and the `_created` metrics can be ignored
- The actual count is in the base metric name (e.g., `meraki_collector_api_calls_total` contains the count, not `meraki_collector_api_calls_created`)

## Logging Strategy

The exporter follows a structured logging approach to balance operational visibility with log volume:

### INFO Level Logging
- **Startup**: Application startup/shutdown messages
- **Discovery**: One-time environment discovery at startup that logs:
  - Organizations being monitored
  - Licensing model (per-device vs co-termination)
  - Network and device counts by type
  - Collector configuration
- **Initialization**: Collector initialization messages
- **Errors**: Major errors that affect operation

### DEBUG Level Logging
- **API Calls**: Every API call with context (org_id, network_id, etc.)
- **Metric Updates**: Every metric value being set
- **Collection Details**: Detailed progress during metric collection
- **Repetitive Info**: Information that would be repetitive at INFO level (e.g., licensing model on each collection)

### Implementation
- All API calls in collectors must use the `@log_api_call` decorator on methods that make Meraki API calls
- The decorator automatically handles DEBUG logging and API call tracking via `self._track_api_call()`
- All metric updates log at DEBUG level when successfully setting values
- Discovery information is logged once at startup via `DiscoveryService`
- Subsequent collections use DEBUG level for details to avoid log spam

Example:
```python
@log_api_call("getOrganizationDevices")
async def _fetch_devices(self, org_id: str) -> list[dict[str, Any]]:
    """Fetch devices for an organization."""
    self._track_api_call("getOrganizationDevices")
    return await asyncio.to_thread(
        self.api.organizations.getOrganizationDevices,
        org_id,
        total_pages="all"
    )
```

## Standardized Logging Patterns

The exporter provides decorators and helpers in `core/logging_decorators.py` and `core/logging_helpers.py` for consistent logging:

### Logging Decorators

#### @log_api_call
Automatically logs API calls with context and tracks them:
```python
from ..core.logging_decorators import log_api_call

@log_api_call("getOrganizationDevices")
async def _fetch_devices(self, org_id: str) -> list[Device]:
    return await self.api.organizations.getOrganizationDevices(org_id)
```

#### @log_collection_progress
Logs progress through batch operations:
```python
from ..core.logging_decorators import log_collection_progress

@log_collection_progress("devices")
async def _process_devices(self, devices: list, current: int, total: int):
    # Process devices...
```

#### @log_batch_operation
Logs batch operations with timing:
```python
from ..core.logging_decorators import log_batch_operation

@log_batch_operation("process alerts", batch_size=50)
async def _process_alerts_batch(self, org_id: str, alerts: list):
    # Process batch...
```

#### @log_collector_discovery
Logs one-time discovery at INFO level:
```python
from ..core.logging_decorators import log_collector_discovery

@log_collector_discovery("network")
async def _discover_networks(self) -> list[Network]:
    # Discover networks...
```

### Logging Helpers

#### LogContext
Context manager for structured logging context:
```python
from ..core.logging_helpers import LogContext

with LogContext(org_id="123", network_id="456"):
    logger.info("Processing network")
    # All logs within this context include org_id and network_id
```

#### Helper Functions
- `log_api_error()` - Consistent API error logging with appropriate levels
- `log_metric_collection_summary()` - Summary statistics after collection
- `log_batch_progress()` - Progress updates for long-running operations
- `log_discovery_info()` - INFO-level discovery logging
- `create_collector_logger()` - Logger with pre-bound collector context

### Best Practices
1. Use `@log_api_call` for all API operations - it automatically tracks and logs
2. Use `LogContext` to add structured context that applies to multiple log entries
3. Use `@log_collection_progress` for operations that process many items
4. Keep DEBUG logs detailed but structured for easy filtering
5. Use INFO logs sparingly for important state changes only

### Comprehensive Logging Guidelines

#### Every Function Should Have Logging
- **Success Path**: Log successful operations at DEBUG level with relevant details (counts, durations, IDs)
- **Error Path**: Log errors with appropriate levels (ERROR for failures, WARNING for degraded functionality)
- **Progress Updates**: For operations processing multiple items, log progress at regular intervals

#### Logging Patterns by Function Type

1. **API Operations** (including low-level wrappers):
```python
logger.debug("Fetching devices", org_id=org_id)
result = await api_call()
logger.debug("Successfully fetched devices", org_id=org_id, count=len(result))
```

2. **Data Processing**:
```python
logger.debug("Processing sensor data", device_count=len(devices))
# ... processing logic ...
logger.debug("Completed processing", successful=success_count, failed=fail_count)
```

3. **Metric Setting**:
```python
logger.debug(
    "Setting device status metric",
    serial=serial,
    status=status,
    value=metric_value
)
```

4. **Validation/Determination Functions**:
```python
if result == "Unknown":
    logger.warning("Unable to determine value", context=context_data)
```

#### Structured Logging Context
Always include relevant identifiers in log messages:
- `org_id`, `org_name` - Organization context
- `network_id`, `network_name` - Network context
- `serial`, `name`, `model` - Device context
- `count`, `duration`, `status` - Operation metrics

#### Log Levels Usage
- **DEBUG**: Normal operations, API calls, metric updates, progress tracking
- **INFO**: Application startup, major state changes, discovery results
- **WARNING**: Degraded functionality, missing optional data, recoverable issues
- **ERROR**: Operation failures, unrecoverable errors, exceptions

#### Performance Considerations
- Use structured logging (key=value) for easy parsing and filtering
- Keep log messages concise but informative
- Include timing information for operations that might be slow
- Log counts and summaries rather than full data dumps

## Error Handling Patterns

The exporter uses standardized error handling patterns defined in `core/error_handling.py`:

### Error Categories
Errors are classified into categories for better monitoring:
- `API_RATE_LIMIT`: 429 errors or rate limit messages
- `API_CLIENT_ERROR`: 4xx errors (bad requests)
- `API_SERVER_ERROR`: 5xx errors (server issues)
- `API_NOT_AVAILABLE`: 404 errors (endpoint not available)
- `TIMEOUT`: Operation timeouts
- `PARSING`: JSON parsing or data format errors
- `VALIDATION`: Data validation failures

### Error Handling Decorator
Use the `@with_error_handling` decorator for standardized error handling:

```python
from ..core.error_handling import with_error_handling

@with_error_handling(
    operation="Fetch devices",
    continue_on_error=True,  # Return None on error
    error_category=ErrorCategory.API_SERVER_ERROR,  # Optional
)
async def _fetch_devices(self, org_id: str) -> list[dict[str, Any]] | None:
    # Implementation
```

### Response Validation
Always validate API response formats:

```python
from ..core.error_handling import validate_response_format

devices = await asyncio.to_thread(self.api.organizations.getOrganizationDevices, org_id)
devices = validate_response_format(
    devices,
    expected_type=list,
    operation="getOrganizationDevices"
)
```

### Concurrency Management
Use helpers for managing concurrent API calls:

```python
from ..core.error_handling import batch_with_concurrency_limit

tasks = [self._process_device(d) for d in devices]
limited_tasks = batch_with_concurrency_limit(tasks, max_concurrent=5)
await asyncio.gather(*limited_tasks, return_exceptions=True)
```

### Error Tracking
Errors are automatically tracked via `_track_error()` when using the decorator, creating Prometheus metrics for monitoring error rates by category.

## API Helper Patterns

The exporter provides standardized API helpers in `core/api_helpers.py` to reduce code duplication:

### APIHelper Class
Use the APIHelper class for common API patterns:

```python
from ..core.api_helpers import create_api_helper

# In collector __init__
self.api_helper = create_api_helper(self)

# Get organizations (handles single/multi-org configs)
organizations = await self.api_helper.get_organizations()

# Get networks with optional filtering
networks = await self.api_helper.get_organization_networks(
    org_id,
    product_types=["wireless", "switch"]
)

# Get devices with filtering
devices = await self.api_helper.get_organization_devices(
    org_id,
    product_types=["sensor"],
    models=["MR", "MS"]
)

# Process items in batches
await self.api_helper.process_in_batches(
    items,
    process_func,
    batch_size=10,
    description="devices"
)

# Get time-based data
data = await self.api_helper.get_time_based_data(
    self.api.wireless.getNetworkWirelessDataRateHistory,
    "getNetworkWirelessDataRateHistory",
    timespan=300,
    interval=300,
    network_id=network_id
)
```

### API Models
Use Pydantic models from `core/api_models.py` for type-safe API responses:

```python
from ..core.api_models import Organization, Network, Device, License

# Validate API responses
org = Organization.model_validate(org_data)
devices = [Device.model_validate(d) for d in device_list]

# Models provide automatic validation and type conversion
# All models support extra fields and have proper defaults
```

Available models include:
- **API Models** (`core/api_models.py`):
  - Organization, Network, Device, DeviceStatus
  - PortStatus, WirelessClient
  - SensorReading, SensorData
  - APIUsage, License, ClientOverview
  - Alert, MemoryUsage
  - PaginatedResponse wrapper
- **Domain Models** (`core/domain_models.py`):
  - RFHealthData, ConnectionStats, NetworkConnectionStats
  - DataRate, SwitchPort, SwitchPortPOE
  - MRDeviceStats, MRRadioStatus
  - ConfigurationChange
  - SensorMeasurement, MTSensorReading
  - OrganizationSummary

## Configuration Management

The exporter uses a sophisticated configuration system with nested Pydantic models:

### Configuration Structure
- **Settings** (`core/config.py`): Main configuration class with nested models
- **Nested Models** (`core/config_models.py`):
  - `APISettings`: API timeouts, retries, concurrency limits, batch sizes
  - `UpdateIntervals`: Fast/medium/slow update intervals with validation
  - `ServerSettings`: HTTP server configuration
  - `OTelSettings`: OpenTelemetry configuration
  - `MonitoringSettings`: Monitoring thresholds and histogram buckets
  - `CollectorSettings`: Enabled/disabled collectors

### Configuration Profiles
Pre-defined profiles for different scenarios:
- **development**: Relaxed limits for development
- **production**: Standard production settings
- **high_volume**: Aggressive settings for large deployments
- **minimal**: Minimal configuration for testing

Set profile via: `MERAKI_EXPORTER_PROFILE=production`

### Environment Variables
- Nested settings use double underscore: `MERAKI_EXPORTER_API__TIMEOUT=60`
- Profile settings can be overridden by environment variables
- Special handling for `MERAKI_API_KEY` (no prefix required)

### Using Configuration in Code
```python
# Access nested configuration
timeout = self.settings.api.timeout
batch_size = self.settings.api.batch_size
```

### Backward Compatibility
Computed properties maintain compatibility:
- `settings.api_timeout` → `settings.api.timeout`
- `settings.fast_update_interval` → `settings.update_intervals.fast`

## Async Patterns and Utilities

The exporter provides standardized async utilities in `core/async_utils.py`:

### ManagedTaskGroup
Structured concurrency for managing related async tasks:
```python
async with ManagedTaskGroup("my_tasks") as group:
    await group.create_task(operation1(), name="op1")
    await group.create_task(operation2(), name="op2")
    # All tasks automatically awaited and cleaned up
```

### Timeout Handling
Execute operations with timeouts:
```python
result = await with_timeout(
    fetch_data(),
    timeout=30.0,
    operation="fetch data",
    default=[]
)
```

### Safe Gathering
Gather coroutines with error logging:
```python
results = await safe_gather(
    *tasks,
    description="network operations",
    log_errors=True
)
```

### Rate-Limited Operations
Execute with semaphore-based rate limiting:
```python
semaphore = asyncio.Semaphore(5)
results = await rate_limited_gather(
    tasks,
    semaphore,
    description="API calls"
)
```

### Retry Logic
Retry operations with exponential backoff:
```python
retry = AsyncRetry(max_attempts=3, base_delay=2.0)
result = await retry.execute(
    lambda: fetch_configuration(),
    operation="fetch config"
)
```

### Chunked Processing
Process items in chunks with delays:
```python
async for chunk in chunked_async_iter(items, chunk_size=10, delay_between_chunks=1.0):
    await process_chunk(chunk)
```

### Circuit Breaker
Prevent cascading failures:
```python
breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)
result = await breaker.call(
    lambda: api_operation(),
    operation="API call"
)
```

### Best Practices
- Use `ManagedTaskGroup` for structured concurrency when coordinating multiple operations
- Use `with_timeout` for operations that might hang beyond SDK timeouts
- Use `safe_gather` instead of raw `asyncio.gather` for non-API operations
- The Meraki SDK already handles retries and rate limiting for API calls
- Use `AsyncRetry` only for non-API operations or when you need exponential backoff
- Use `CircuitBreaker` for endpoints that frequently fail

### When to Use Async Utilities vs SDK Defaults

**Use SDK defaults (no extra wrapping) for**:
- Simple API calls that return quickly
- Operations where SDK's 3 retries are sufficient
- Standard rate limit handling (429 errors)

**Use async utilities for**:
- Coordinating multiple collectors or operations (ManagedTaskGroup)
- Operations that need specific timeout guarantees
- Non-API async operations
- Endpoints with persistent failures (CircuitBreaker)
- When you need true exponential backoff

**Note**: The Meraki SDK already provides:
- Automatic retry on failures (up to 3 times)
- Rate limit handling with wait_on_rate_limit=True
- Configurable timeouts via api_timeout setting
