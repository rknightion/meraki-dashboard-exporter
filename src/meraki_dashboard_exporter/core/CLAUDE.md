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
- `config_models.py` - Nested config models (`APISettings` including `validate_kwargs` for Meraki SDK 3.2.0, `CollectorSettings` with default `collector_timeout=240`, `OTelSettings`, `NetworkFilterSettings`, etc.)
- `config_logger.py` - Configuration-aware logging setup
- `network_filter.py` - `NetworkFilter` resolver for include/exclude rules across name (glob), id, and tag. Pure logic; applied at the inventory read path in `services/inventory.py`. `discovery.py::DiscoveryService` is the documented exception that bypasses the filter.

### Logging
- `logging.py` - Structured logging setup (`get_logger()`)
- `logging_helpers.py` - `LogContext` context manager, formatting helpers
- `logging_decorators.py` - `@log_api_call()`, `@log_collection_progress()`, `@log_batch_operation()`

### Metrics & Labels
- `metrics.py` - `LabelName` enum and `create_labels()` label-dict builder (validates keys, coalesces `None`→`""`, F-019)
- `label_helpers.py` - Label construction helpers
- `metric_expiration.py` - Metric TTL and automatic stale metric cleanup
- `exemplars.py` - OpenTelemetry exemplar support

### Error Handling
- `error_handling.py` - `@with_error_handling()` decorator, `ErrorCategory` enum, custom exceptions, and `validate_response_format(response, expected_type, operation)` helper. New API fetchers must call `validate_response_format` to normalize the SDK's exhausted-retry error shape (a dict with `errors` key) and unwrap `{"items": [...]}` responses where applicable.

### Domain Models
- `api_models.py` - Basic API response models (`Organization`, `Network`, `Device`)
- `domain_models.py` - Extended models (`RFHealthData`, `ConnectionStats`, `SwitchPort`, etc.)

### Collector Infrastructure
- `collector.py` - `MetricCollector` abstract base class with `_initialize_metrics()` and `_collect_impl()`
- `registry.py` - `@register_collector(tier)` decorator for auto-registration
- `async_utils.py` - `ManagedTaskGroup` for bounded concurrency, plus `with_timeout()`, `managed_resource()`, `AsyncRetry`, `chunked_async_iter()` (note: `batch_with_concurrency_limit()` lives in `error_handling.py`, not here)
- `batch_processing.py` - Batch operation helpers

### API Helpers
- `api_helpers.py` - `APIHelper` class (`create_api_helper(collector)` factory) wrapping common per-collector API call patterns. `get_organization_networks()` prefers `self.collector.inventory.get_networks(org_id)` but falls back to `_fetch_networks_direct()` (a direct `getOrganizationNetworks` call that manually reapplies `NetworkFilter`) when `inventory` is `None` — a third sanctioned bypass site alongside `discovery.py` and `collectors/alerts.py`, reachable from production via `collectors/organization.py` and `collectors/clients.py`.
- `rate_limiter.py` - `OrgRateLimiter`: per-organization client-side token-bucket rate limiting
- `type_definitions.py` - Shared `TypedDict`s (e.g. `DeviceStatusInfo`, `PortStatusData`, `AlertData`) and type aliases (`OrganizationId`, `NetworkId`, etc.) for common API dict shapes. (The `CollectorProtocol` lives in `collector.py`, not here.)

### Observability
- `otel_logging.py` - OpenTelemetry log integration
- `otel_tracing.py` - OpenTelemetry trace instrumentation
- `span_metrics.py` - Span-level metrics

### Other
- `cardinality.py` - `CardinalityMonitor` + `setup_cardinality_endpoint(app, monitor)`: metric cardinality tracking and its endpoints (`/api/metrics/cardinality`, `/cardinality` HTML, `/cardinality/all-metrics`, `/cardinality/all-labels`, `/cardinality/export/json`, `/cardinality/label-values/{metric_name}`) — these are top-level routes, not nested under `/status`.
- `discovery.py` - `DiscoveryService`: one-time startup environment audit (`run_discovery()`). Deliberately bypasses `NetworkFilter` (calls `getOrganizationNetworks` directly) so operators see the full pre-filter inventory in startup diagnostics. This is the only sanctioned *unfiltered* bypass; `collectors/alerts.py::AlertsCollector._fetch_networks_direct` and `api_helpers.py::APIHelper._fetch_networks_direct` are two further sanctioned *filtered* fallbacks (see below), used only when `self.inventory` is unavailable.
- `webhook_handler.py` - `WebhookHandler`: webhook event processing and validation
- `org_health.py` - `OrgHealthTracker`/`OrgHealth`: per-organization exponential-backoff tracker for graceful degradation. After N consecutive failures (default 5) an org is backed off (default 60s, capped at 3600s) while collection continues normally for healthy orgs; used by `collectors/organization.py` and `collectors/manager.py`, surfaced on `/status` via `services/status.py`.

### Constants (`constants/` subdirectory)
- `metrics_constants.py` - Domain-specific metric enums: `OrgMetricName`, `DeviceMetricName`, `NetworkMetricName`, `MSMetricName`, `MRMetricName`, `MXMetricName`, `MVMetricName`, `MTMetricName`, `MGMetricName`, `AlertMetricName`, `ConfigMetricName`, `NetworkHealthMetricName`, `ClientMetricName`, `CollectorMetricName`, `WebhookMetricName`. Two prefix families: `meraki_*` for Meraki network/device data, `meraki_exporter_*` for the exporter's own instrumentation (`CollectorMetricName`). `ConfigMetricName` is currently an empty enum (`pass`) - config-change metrics live under `OrgMetricName`; don't assume it needs populating.
- `api_constants.py` - `APIField` (common response field-name enum), `APITimespan`, `LicenseState`, `PortState`, `RFBand`
- `config_constants.py` - `APIConfig`/`RegionalURLs`/`MerakiAPIConfig` dataclasses and derived `MERAKI_API_BASE_URL*` constants (legacy; prefer `Settings`/`APISettings` in `config.py`/`config_models.py` for runtime config)
- `device_constants.py` - `DeviceType`, `DeviceStatus`, `ProductType`, `UpdateTier` enums
- `sensor_constants.py` - `SensorMetricType`, `SensorDataField` enums
- All exported together via `constants/__init__.py`'s `__all__`; new enum members go in the domain file, not a new top-level file - see "ADDING NEW METRICS" below.
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
from ..core.error_handling import (
    ErrorCategory,
    validate_response_format,
    with_error_handling,
)


@with_error_handling(
    operation="Fetch devices",
    continue_on_error=True,
    error_category=ErrorCategory.API_SERVER_ERROR,
)
async def _fetch_devices(self, org_id: str) -> list[Device] | None:
    raw = await asyncio.to_thread(
        self.api.organizations.getOrganizationDevices, org_id, total_pages="all"
    )
    # Mandatory: normalize the SDK exhausted-retry error shape and unwrap
    # {"items": [...]} responses. Raises RetryableAPIError / DataValidationError
    # so the decorator can categorize correctly.
    devices = validate_response_format(raw, expected_type=list, operation="getOrganizationDevices")
    return [Device.model_validate(d) for d in devices]
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
- **NEVER skip `validate_response_format`** for new fetchers - the SDK can return error-shaped dicts after retry exhaustion
- **NEVER bypass `NetworkFilter` unfiltered** outside `core/discovery.py::DiscoveryService` - all collector network reads go through `OrganizationInventory.get_networks(org_id)`. Two sanctioned filtered fallbacks exist for when `inventory` is unavailable (`collectors/alerts.py::AlertsCollector._fetch_networks_direct`, `api_helpers.py::APIHelper._fetch_networks_direct`), each manually reapplying `NetworkFilter`.
</fatal_implications>
