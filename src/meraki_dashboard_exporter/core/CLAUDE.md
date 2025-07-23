<system_context>
Core infrastructure for Meraki Dashboard Exporter - Contains foundational components for configuration, logging, metrics, error handling, and domain models. This is the backbone that all collectors and services depend on.
</system_context>

<critical_notes>
- **ALWAYS use MetricName enum** from `constants/metrics_constants.py` instead of hardcoded strings
- **ALWAYS use LabelName enum** from `metrics.py` for consistent labeling
- **Use domain models** from `api_models.py` and `domain_models.py` instead of raw dictionaries
- **Structured logging** - Use context managers and decorators from `logging_helpers.py`
- **Error handling** - Use decorators from `error_handling.py` for consistent error management
</critical_notes>

<file_map>
## CORE COMPONENTS
- `config.py` / `config_models.py` - Configuration management and validation
- `logging.py` / `logging_helpers.py` / `logging_decorators.py` - Structured logging system
- `metrics.py` / `otel_metrics.py` - Prometheus and OpenTelemetry metrics
- `error_handling.py` - Centralized error handling with decorators
- `api_models.py` / `domain_models.py` - Pydantic models for API and business logic
- `collector.py` - Base collector classes and interfaces
- `registry.py` - Collector registration and discovery
- `constants/` - All enums and constants organized by domain
- `type_definitions.py` - Shared type hints and protocols
</file_map>

<paved_path>
## METRIC CREATION PATTERN
```python
# Always use enums for consistency
from ..constants.metrics_constants import MetricName
from .metrics import LabelName

# In collector's _initialize_metrics()
self.device_status = Gauge(
    MetricName.DEVICE_STATUS.value,
    "Device operational status",
    [LabelName.ORG_ID.value, LabelName.SERIAL.value]
)
```

## ERROR HANDLING PATTERN
```python
from .error_handling import with_error_handling, ErrorCategory

@with_error_handling(
    operation="Fetch devices",
    continue_on_error=True,
    error_category=ErrorCategory.API_SERVER_ERROR
)
async def _fetch_devices(self, org_id: str) -> list[Device] | None:
    # Implementation with automatic error handling
```

## LOGGING PATTERN
```python
from .logging_helpers import LogContext
from .logging_decorators import log_api_call

@log_api_call("getOrganizationDevices")
async def _fetch_devices(self, org_id: str) -> list[Device]:
    with LogContext(org_id=org_id):
        logger.info("Fetching devices")
        # All logs include org_id context
```
</paved_path>

<patterns>
## DOMAIN MODEL USAGE
```python
# GOOD: Use validated domain models
device = Device.model_validate(device_data)
reading = SensorReading.model_validate(reading_data)

# BAD: Raw dictionaries
device = {"serial": "...", "name": "..."}
```

## CONFIGURATION ACCESS
```python
from .config import get_config

config = get_config()
api_key = config.meraki.api_key
update_interval = config.collection.device_update_interval
```
</patterns>

<examples>
## Complete Collector with Core Infrastructure
```python
from prometheus_client import Gauge
from ..core.collector import MetricCollector, register_collector
from ..core.constants.metrics_constants import MetricName
from ..core.metrics import LabelName
from ..core.error_handling import with_error_handling
from ..core.logging_decorators import log_api_call
from ..core.domain_models import Device

@register_collector(UpdateTier.MEDIUM)
class ExampleCollector(MetricCollector):
    def _initialize_metrics(self) -> None:
        self.device_count = Gauge(
            MetricName.DEVICE_COUNT.value,
            "Number of devices per organization",
            [LabelName.ORG_ID.value, LabelName.DEVICE_TYPE.value]
        )

    @with_error_handling("Count devices", continue_on_error=True)
    @log_api_call("getOrganizationDevices")
    async def _collect_impl(self) -> None:
        organizations = await self._get_organizations()
        for org in organizations:
            devices = await self._fetch_devices(org.id)
            self._update_metrics(org.id, devices)

    def _update_metrics(self, org_id: str, devices: list[Device]) -> None:
        device_counts = {}
        for device in devices:
            device_counts[device.product_type] = device_counts.get(device.product_type, 0) + 1

        for device_type, count in device_counts.items():
            self.device_count.labels(
                org_id=org_id,
                device_type=device_type
            ).set(count)
```
</examples>

<workflow>
## ADDING NEW METRICS
1. **Define enum** in appropriate `constants/` file
2. **Add labels** to `LabelName` enum in `metrics.py` if needed
3. **Initialize metric** in collector's `_initialize_metrics()`
4. **Set values** in `_collect_impl()` using labels
5. **Add tests** with metric assertions
</workflow>

<fatal_implications>
- **NEVER use hardcoded strings** for metric/label names - always use enums
- **NEVER skip domain model validation** - always use `model_validate()`
- **NEVER log sensitive data** - API keys, tokens, etc.
- **NEVER ignore error handling** - use decorators for consistent behavior
</fatal_implications>
