<system_context>
Core infrastructure for Meraki Dashboard Exporter - Contains foundational components for configuration, logging, metrics, error handling, domain models, and observability. This is the backbone that all collectors and services depend on.
</system_context>

<critical_notes>
- **ALWAYS use domain-specific metric enums** from `constants/metrics_constants.py` (e.g., `OrgMetricName`, `MSMetricName`, `MRMetricName`)
- **ALWAYS use LabelName enum** from `metrics.py` for consistent labeling
- **Use domain models** from `api_models.py` and `domain_models.py` instead of raw dictionaries
- **Structured logging** - Use context managers and decorators from `logging_helpers.py`
- **Error handling** - Use decorators from `error_handling.py` for consistent error management
</critical_notes>

<file_map>
## CORE COMPONENTS
### Configuration
- `config.py` - `Settings` class (Pydantic BaseSettings) with nested config models
- `config_models.py` - Nested config models (APISettings, CollectorSettings, OTelSettings, etc.)
- `config_logger.py` - Configuration-aware logging setup

### Logging
- `logging.py` - Structured logging setup (`get_logger()`)
- `logging_helpers.py` - `LogContext` context manager, formatting helpers
- `logging_decorators.py` - `@log_api_call()`, `@log_collection_progress()`, `@log_batch_operation()`

### Metrics & Labels
- `metrics.py` - `LabelName` enum, `MetricFactory`, `LabelSet`, `MetricDefinition`
- `label_helpers.py` - Label construction helpers
- `metric_expiration.py` - Metric TTL and automatic stale metric cleanup
- `exemplars.py` - OpenTelemetry exemplar support

### Error Handling
- `error_handling.py` - `@with_error_handling()` decorator, `ErrorCategory` enum, custom exceptions

### Domain Models
- `api_models.py` - Basic API response models (`Organization`, `Network`, `Device`)
- `domain_models.py` - Extended models (`RFHealthData`, `ConnectionStats`, `SwitchPort`, etc.)

### Collector Infrastructure
- `collector.py` - `MetricCollector` abstract base class with `_initialize_metrics()` and `_collect_impl()`
- `registry.py` - `@register_collector(tier)` decorator for auto-registration
- `async_utils.py` - `ManagedTaskGroup` for bounded concurrency, `batch_with_concurrency_limit()`
- `batch_processing.py` - Batch operation helpers

### API Helpers
- `api_helpers.py` - API wrapper utilities
- `rate_limiter.py` - API rate limiting
- `type_definitions.py` - Shared type hints and protocols

### Observability
- `otel_logging.py` - OpenTelemetry log integration
- `otel_tracing.py` - OpenTelemetry trace instrumentation
- `span_metrics.py` - Span-level metrics

### Other
- `cardinality.py` - Metric cardinality tracking and management
- `discovery.py` - Device/network discovery
- `webhook_handler.py` - Webhook event processing and validation

### Constants (`constants/` subdirectory)
- `metrics_constants.py` - Domain-specific metric enums: `OrgMetricName`, `DeviceMetricName`, `NetworkMetricName`, `MSMetricName`, `MRMetricName`, `MXMetricName`, `MVMetricName`, `MTMetricName`, `AlertMetricName`, `ConfigMetricName`, `NetworkHealthMetricName`, `ClientMetricName`, `CollectorMetricName`, `WebhookMetricName`
- `api_constants.py` - API-related constants
- `config_constants.py` - Configuration constants
- `device_constants.py` - Device types, `UpdateTier` enum
- `sensor_constants.py` - Sensor type constants
</file_map>

<paved_path>
## METRIC CREATION PATTERN
```python
# Always use domain-specific enums
from ..core.constants.metrics_constants import MSMetricName
from ..core.metrics import LabelName

# In collector's _initialize_metrics()
self._port_status = self.parent._create_gauge(
    MSMetricName.MS_PORT_STATUS,
    "Switch port status",
    labelnames=[LabelName.ORG_ID.value, LabelName.SERIAL.value, LabelName.PORT_ID.value],
)
```

## ERROR HANDLING PATTERN
```python
from ..core.error_handling import with_error_handling, ErrorCategory

@with_error_handling(
    operation="Fetch devices",
    continue_on_error=True,
    error_category=ErrorCategory.API_SERVER_ERROR,
)
async def _fetch_devices(self, org_id: str) -> list[Device] | None:
    ...
```

## CONFIGURATION ACCESS
```python
from ..core.config import Settings

# Settings is instantiated once and passed to collectors
# Access: settings.meraki.api_key, settings.api.timeout, settings.update_intervals, etc.
```

## LOGGING PATTERN
```python
from ..core.logging import get_logger
from ..core.logging_helpers import LogContext
from ..core.logging_decorators import log_api_call

logger = get_logger(__name__)

@log_api_call("getOrganizationDevices")
async def _fetch_devices(self, org_id: str) -> list[Device]:
    with LogContext(org_id=org_id):
        logger.info("Fetching devices")
```
</paved_path>

<workflow>
## ADDING NEW METRICS
1. **Define enum** in appropriate `constants/` file
2. **Add labels** to `LabelName` enum in `metrics.py` if needed
3. **Initialize metric** in collector's `_initialize_metrics()` using `parent._create_gauge()`
4. **Set values** in `_collect_impl()` using labels
5. **Add tests** with metric assertions
</workflow>

<fatal_implications>
- **NEVER use hardcoded strings** for metric/label names - always use enums
- **NEVER skip domain model validation** - always use `model_validate()`
- **NEVER log sensitive data** - API keys, tokens, etc.
- **NEVER ignore error handling** - use decorators for consistent behavior
</fatal_implications>
