# CLAUDE3.md

<system_context>
Meraki Dashboard Exporter - A production-ready Prometheus exporter that collects metrics from Cisco Meraki Dashboard API and exposes them for monitoring. Supports OpenTelemetry mirroring and includes comprehensive collectors for devices, networks, organizations, and sensor data.
</system_context>

<critical_notes>
- **ALWAYS use MetricName enum** from `constants.py` instead of hardcoded strings
- **ALWAYS use LabelName enum** from `core/metrics.py` for consistent labeling
- **Use domain models** from `core/api_models.py` and `core/domain_models.py` instead of raw dictionaries
- **Follow update tiers**: FAST (60s), MEDIUM (300s), SLOW (900s) based on data volatility
- **Use structured logging** with context managers and decorators
- **Security**: Never log or expose API keys, use read-only when possible
- **Memory**: Be mindful of API rate limits and implement proper error handling
</critical_notes>

<file_map>
## KEY FILES & DIRECTORIES
- `src/meraki_dashboard_exporter/core/` - Core infrastructure (logging, config, models, metrics)
- `src/meraki_dashboard_exporter/collectors/` - Main collector implementations
- `src/meraki_dashboard_exporter/collectors/devices/` - Device-specific collectors (MR, MS, MX, MT, MG, MV)
- `src/meraki_dashboard_exporter/api/client.py` - Meraki API wrapper
- `src/meraki_dashboard_exporter/app.py` - Main FastAPI application
- `pyproject.toml` - Project dependencies and configuration
- `tests/` - Comprehensive test suite with helpers and factories
- `dashboards/` - Grafana dashboard JSON exports
- `docs/` - Documentation including ADRs and metrics reference
</file_map>

<paved_path>
## ARCHITECTURE PATTERNS (CANONICAL APPROACHES)

### Adding New Collectors
1. **Main Collectors**: Use `@register_collector(UpdateTier.X)` decorator for auto-registration
2. **Sub-collectors**: Manual registration in parent coordinator's `__init__`
3. **Inherit from appropriate base**: `MetricCollector`, `BaseDeviceCollector`, etc.
4. **Implement required methods**: `_initialize_metrics()`, `_collect_impl()`

### Metric Creation
```python
# ALWAYS use enums
from ..core.constants import MetricName
from ..core.metrics import LabelName

# In _initialize_metrics()
self.device_status = Gauge(
    MetricName.DEVICE_STATUS.value,
    "Device operational status",
    [LabelName.ORG_ID.value, LabelName.SERIAL.value]
)
```

### API Interactions
```python
# Use decorators and tracking
@log_api_call("getOrganizationDevices")
async def _fetch_devices(self, org_id: str) -> list[Device]:
    self._track_api_call("getOrganizationDevices")
    return await asyncio.to_thread(
        self.api.organizations.getOrganizationDevices,
        org_id,
        total_pages="all"  # When supported
    )
```

### Error Handling
```python
from ..core.error_handling import with_error_handling

@with_error_handling(
    operation="Fetch devices",
    continue_on_error=True,
    error_category=ErrorCategory.API_SERVER_ERROR
)
async def _fetch_devices(self, org_id: str) -> list[Device] | None:
    # Implementation
```
</paved_path>

<patterns>
## COMMON PATTERNS

### Domain Model Usage
```python
# GOOD: Use domain models
device = Device.model_validate(device_data)
sensor_reading = SensorReading.model_validate(reading_data)

# BAD: Raw dictionaries
device = {"serial": "...", "name": "..."}
```

### Logging with Context
```python
from ..core.logging_helpers import LogContext

with LogContext(org_id=org_id, network_id=network_id):
    logger.info("Processing network devices")
    # All logs within this context include org_id and network_id
```

### Metric Ownership by Device Type
- Device-specific metrics owned by respective collectors (`MRCollector`, `MSCollector`, etc.)
- Common metrics (`meraki_device_up`) owned by main `DeviceCollector`
- Each device collector implements `_initialize_metrics()` for its specific metrics
</patterns>

<workflow>
## DEVELOPMENT WORKFLOW

### Adding New Device Support
1. **Create device collector** in `collectors/devices/{type}.py`
2. **Inherit from BaseDeviceCollector**
3. **Implement _initialize_metrics()** for device-specific metrics
4. **Register in DeviceCollector.__init__()**
5. **Add to device constants** in `core/constants/device_constants.py`
6. **Update tests** with new device type

### Adding New Organization Metrics
1. **Create collector** in `collectors/organization_collectors/`
2. **Inherit from BaseOrganizationCollector**
3. **Register in OrganizationCollector.__init__()**
4. **Add appropriate update tier** (usually MEDIUM or SLOW)

### Testing New Features
1. **Use test factories** from `tests/helpers/factories.py`
2. **Mock API responses** with `MockAPIBuilder`
3. **Assert metrics** with `MetricAssertions`
4. **Test error scenarios** using `.with_error()`
</workflow>

<bash_commands>
## COMMON COMMANDS
- `uv run python -m meraki_dashboard_exporter` - Start the exporter
- `uv run ruff check --fix .` - Lint and auto-fix code
- `uv run mypy .` - Type checking
- `uv run pytest` - Run tests
- `uv run pytest -v -k test_name` - Run specific test
- `uv run python src/meraki_dashboard_exporter/tools/generate_metrics_docs.py` - Generate metrics docs
- `uv add package_name` - Add new dependency
- `docker-compose up` - Start with Docker
- `make docs-serve` - Serve documentation locally
</bash_commands>

<code_style>
## STYLE GUIDELINES
- **Formatting**: Black with 88-char line length
- **Type hints**: Use `from __future__ import annotations` and proper typing
- **Imports**: Group stdlib, third-party, local with proper organization
- **Docstrings**: NumPy-style with type hints
- **Constants**: Use Literal & Enum/StrEnum appropriately
- **Early returns**: Reduce nesting where possible
- **Async**: Use `asyncio.to_thread()` for Meraki SDK calls
</code_style>

<api_quirks>
## MERAKI API LIMITATIONS & QUIRKS
- **CPU metrics**: Only available for MR devices via `getOrganizationWirelessDevicesSystemCpuLoadHistory`
- **Uptime metrics**: Not available via API for any device types
- **Sensor readings**: May return both `temperature` and `rawTemperature` - only process `temperature`
- **Memory metrics**: Use `getOrganizationDevicesSystemMemoryUsageHistoryByInterval` WITHOUT `total_pages`
- **Client overview**: Requires exactly 3600 second timespan for reliable data
- **Response formats**: Some endpoints wrap in `{"items": [...]}`, others return arrays directly
- **Deprecated APIs**: Use `getOrganizationDevices` instead of `getNetworkDevices`
</api_quirks>

<testing_patterns>
## TESTING APPROACHES
- **Inherit from BaseCollectorTest** for automatic fixture setup
- **Use test factories** for consistent, realistic test data
- **Mock with MockAPIBuilder** for cleaner API mocking
- **Assert metrics** with MetricAssertions for clear verification
- **Test error scenarios** with `.with_error()` method
- **Use snapshots** for tracking metric changes during operations
</testing_patterns>

<common_tasks>
## STEP-BY-STEP GUIDES

### Adding a New Metric
1. Define in appropriate MetricName enum in `constants.py`
2. Add label names to LabelName enum in `core/metrics.py` if needed
3. Initialize metric in collector's `_initialize_metrics()` method
4. Set metric values in `_collect_impl()` or sub-methods
5. Add tests covering the new metric
6. Update documentation

### Debugging Collection Issues
1. Check logs at DEBUG level for API calls and metric updates
2. Verify metric registration in collector's `_initialize_metrics()`
3. Check API response format handling for wrapper objects
4. Validate domain model parsing
5. Ensure proper error handling with context
</common_tasks>

<fatal_implications>
## CRITICAL "DO NOT" RULES
- **NEVER use hardcoded metric/label names** - always use enums
- **NEVER log API keys or sensitive data**
- **NEVER assume API response format** - always validate
- **NEVER skip error handling** for API calls
- **NEVER use `any` types** without explicit justification
- **NEVER modify tests to match incorrect implementations**
- **NEVER commit without running linters and type checks**
</fatal_implications>

<examples>
## CODE EXAMPLES

### Complete Device Collector Example
```python
@register_collector(UpdateTier.MEDIUM)
class ExampleCollector(BaseDeviceCollector):
    def _initialize_metrics(self) -> None:
        self.example_metric = Gauge(
            MetricName.EXAMPLE_STATUS.value,
            "Example device status",
            [LabelName.ORG_ID.value, LabelName.SERIAL.value]
        )

    @log_api_call("getExampleData")
    async def _collect_impl(self) -> None:
        organizations = await self._get_organizations()
        for org in organizations:
            await self._process_organization(org.id)

    async def _process_organization(self, org_id: str) -> None:
        devices = await self._fetch_devices(org_id)
        for device in devices:
            self.example_metric.labels(
                org_id=org_id,
                serial=device.serial
            ).set(1 if device.status == "online" else 0)
```

### Test Example with Factories
```python
async def test_collector_metrics(self, collector, mock_api_builder, metrics):
    # Setup test data
    org = OrganizationFactory.create()
    devices = DeviceFactory.create_many(3, network_id="net_123")

    mock_api_builder.with_organizations([org]).with_devices(devices)

    # Run collector
    await self.run_collector(collector)

    # Assert metrics
    metrics.assert_gauge_value("meraki_device_up", 1, serial=devices[0]["serial"])
```
</examples>

<advanced_patterns>
## ADVANCED TECHNIQUES
- **Parallel Collection**: Use async batch processing for multiple API calls
- **Circuit Breaker**: Implement for endpoints with frequent failures
- **Caching Strategies**: Cache non-zero values for client overview metrics
- **MCP Integration**: Use external tools via Model Context Protocol
- **Headless Automation**: Use `-p` flag for CI/CD integration
- **Git Worktrees**: Run multiple Claude instances on different branches
- **Custom Slash Commands**: Create reusable prompt templates in `.claude/commands/`
</advanced_patterns>

<hatch>
## ALTERNATIVE APPROACHES
When the paved path doesn't fit:
- **Custom Metrics**: Use MetricFactory for non-standard metrics
- **Alternative APIs**: Some endpoints have multiple access methods
- **Error Recovery**: Implement fallback strategies for failed API calls
- **Performance Tuning**: Adjust update intervals based on data importance
- **Manual Override**: Environment variables for debugging specific collectors
</hatch>
