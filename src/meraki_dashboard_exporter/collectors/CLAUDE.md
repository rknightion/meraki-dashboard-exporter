<system_context>
Meraki Dashboard Exporter Collectors - All metric collection logic organized by domain (devices, networks, organizations). Implements the collector pattern with automatic registration and adaptive, endpoint-group-clocked scheduling (there is no fixed FAST/MEDIUM/SLOW tier system, #631).
</system_context>

<critical_notes>
- **No fixed update tiers**: each collector declares one or more endpoint groups (`get_endpoint_groups()`: name, priority 1-4, `floor_seconds`, `cost_fn`) and runs its own group-clocked loop; the scheduler (`core/scheduler.py`) solves each group's actual interval from org shape and the API budget (default per-collector timeout: 240s, configurable via `CollectorSettings.collector_timeout`, range 30-600s). See `core/CLAUDE.md` and `docs/observability/scheduler.md`.
- **Main collectors**: Use the no-arg `@register_collector` decorator (`core/registry.py`) for auto-registration; real base class lives in `core/collector.py::MetricCollector`, not in this directory
- **Sub-collectors**: Manual registration in parent coordinator's `__init__` (never decorated)
- **Inherit from appropriate base**: `MetricCollector` (main), `BaseDeviceCollector`/`BaseNetworkHealthCollector`/`BaseOrganizationCollector` (sub, each mixing in `SubCollectorMixin`)
- **Implement required methods**: `_initialize_metrics()`, `_collect_impl()` — both abstract on `MetricCollector`; never override `collect()` itself, it wraps `_collect_impl()` with tracing + duration/error/success metrics
- **Network fetches MUST go through inventory**: Always use `await self.inventory.get_networks(org_id)` (or `self.parent.inventory.get_networks(org_id)` from sub-collectors). Never call `self.api.organizations.getOrganizationNetworks` directly — that bypasses the configured `NetworkFilter`. The one exception in this directory is `alerts.py::AlertsCollector._fetch_networks_direct`, a fallback used only when `self.inventory` is `None`; it manually reapplies `NetworkFilter` so filtering still holds. A second, sibling fallback lives outside this directory in `core/api_helpers.py::APIHelper._fetch_networks_direct` (reached via `APIHelper.get_organization_networks`, called from e.g. `organization.py`/`clients.py` when inventory is unavailable) — it also reapplies `NetworkFilter` manually.
- **Validate fetcher responses**: New API fetchers must wrap responses with `validate_response_format` from `core.error_handling` to normalize the SDK exhausted-retry error shape.
</critical_notes>

<file_map>
## COLLECTOR ORGANIZATION
### Subdirectories (each has its own CLAUDE.md)
- `devices/` - Device-specific collectors (MR, MS, MX, MT, MG, MV) - See `devices/CLAUDE.md`
- `network_health_collectors/` - Network health metrics - See `network_health_collectors/CLAUDE.md`
- `organization_collectors/` - Organization-level metrics - See `organization_collectors/CLAUDE.md`

### Coordinator Files
- `manager.py` - `CollectorManager`: discovers, instantiates, and schedules all collectors (see REGISTRATION & DISCOVERY below)
- `device.py` - `DeviceCollector` coordinator (mostly ~300s-floor groups) fanning out to per-device-type sub-collectors (MG/MR/MS/MS-stack/MT/MV/MX) via `ManagedTaskGroup`, bounded by `settings.api.concurrency_limit`
- `network_health.py` - `NetworkHealthCollector` coordinator (~300s-floor groups) fanning out to `network_health_collectors/` (bluetooth, connection_stats, data_rates, rf_health, ssid_performance) via `ManagedTaskGroup`
- `organization.py` - `OrganizationCollector` coordinator (mostly ~300s-floor groups) fanning out to `organization_collectors/` (`APIUsageCollector`, `ClientOverviewCollector`, `LicenseCollector`) via `ManagedTaskGroup`; the only collector that also receives an `org_health_tracker` kwarg from the manager
- `config.py` - `ConfigCollector` for configuration/security settings (~900s-floor groups)

### Shared Infrastructure
- `subcollector_mixin.py` - `SubCollectorMixin` providing common sub-collector delegation patterns (`_set_metric_value`, `_track_api_call`, `update_api`); mixed into `devices/base.py::BaseDeviceCollector`, `network_health_collectors/base.py::BaseNetworkHealthCollector`, `organization_collectors/base.py::BaseOrganizationCollector`, and standalone sub-collectors (`devices/mx_firewall.py`, `devices/mx_vpn.py`, `devices/ms_stack.py`)

### Standalone Collectors
- `alerts.py` - `AlertsCollector` (~300s-floor groups) - alert/event collection
- `clients.py` - `ClientsCollector` (~300s-floor groups) - client device tracking
- `mt_sensor.py` - `MTSensorCollector` (~60s-floor group) - standalone sensor data collection
- `mt_alerts.py` - `MTSensorAlertsCollector` (~300s-floor group) - MT sensor alert collection
- `webhook_metrics.py` - **removed (issue #530)**: `WebhookMetricsCollector` was dead code (never instantiated/wired anywhere; its `network_id`-labeled counter was also a cardinality risk). The live webhook receiver's metrics (`meraki_webhook_events_received_total`, `_processed_total`, `_failed_total`, `_processing_duration_seconds`, `_validation_failures_total`) are owned entirely by `core/webhook_handler.py::WebhookHandler` and are unaffected — those remain Stable per `docs/stability.md`.
</file_map>

<paved_path>
## COLLECTOR REGISTRATION

### Main Collector (Auto-registered via decorator)
```python
from ..core.registry import register_collector
from ..core.collector import MetricCollector


@register_collector
class MyCollector(MetricCollector):
    def _initialize_metrics(self) -> None: ...

    async def _collect_impl(self) -> None: ...

    def get_endpoint_groups(self) -> tuple[EndpointGroup, ...]:
        return (
            EndpointGroup(
                name=EndpointGroupName.MY_GROUP,
                priority=3,
                floor_seconds=300,
                cost_fn=lambda shape: 1.0,
            ),
        )
```
`register_collector()` (`core/registry.py`) just appends the class to a module-level
`_COLLECTOR_REGISTRY: list[type[MetricCollector]]` at import time — it does not instantiate
anything or take a tier argument. `get_endpoint_groups()` is what tells the scheduler how to
pace the collector (see `core/scheduler.py::EndpointGroup`/`EndpointGroupName`).

### Sub-collector (Manual registration in parent coordinator)
Sub-collectors are instantiated in their parent coordinator's `__init__` (e.g. `DeviceCollector.__init__`
builds `self.mr_collector = MRCollector(self)`, etc.) and called during the parent's `_collect_impl()`.
They never use `@register_collector`.

## DISCOVERY & INSTANTIATION (`CollectorManager`, `manager.py`)
1. **Import-to-register**: `CollectorManager._initialize_collectors()` explicitly imports every
   top-level collector module (`from . import alerts, clients, config, device, mt_alerts,
   mt_sensor, network_health, organization`) purely to execute their `@register_collector`
   decorators — this is what triggers step 2. Sub-collector modules never need this since they
   aren't decorated.
2. **Read the registry**: calls `core/registry.py::get_registered_collectors()` to get the flat
   list of registered classes built in step 1 (registration order, no tier grouping).
3. **Filter by name**: each class's short name (`ClassName.replace("Collector", "").lower()`, e.g.
   `NetworkHealthCollector` -> `networkhealth`) is checked against
   `settings.collectors.active_collectors` (`CollectorSettings.enabled_collectors -
   disable_collectors`, default `{alerts, clients, config, device, mtsensor, mtsensoralerts,
   networkhealth, organization}` in `core/config_models.py`); non-matching classes are recorded in
   `self.skipped_collectors` and skipped.
4. **Instantiate**: each surviving class is constructed with `api`, `settings`, the shared
   `self.inventory` (`OrganizationInventory`), `expiration_manager`, and `rate_limiter`
   (`OrgRateLimiter`); `OrganizationCollector` alone gets an extra `org_health_tracker` kwarg.
5. **Per-run execution**: `CollectorManager.run_collector_once()` runs a collector under the
   configured `settings.collectors.collector_timeout`; `_validate_collector_configuration()` warns
   (does not fail) if a configured name in `active_collectors` matches no registered collector
   (typo detection).

## ENDPOINT GROUP FLOOR SELECTION
Pick `floor_seconds` by the data's natural volatility, and `priority` (1=up-ness/alerts,
2=sensor, 3=perf/health, 4=config/inventory) by how important it is to protect from stretching
when the org is over budget:
- **~60s floor**: Real-time status, critical alerts, sensor readings
- **~300s floor**: Device metrics, performance data, client counts
- **~900s+ floor**: License usage, organization summaries, configuration

These are conventions, not enforced constants — see `core/scheduler.py::EndpointGroupName` for
every declared group and its actual floor/priority, and `docs/observability/scheduler.md` for how
the solver stretches groups above their floor under budget pressure.

## CONCURRENCY WITHIN A COORDINATOR
`device.py`, `network_health.py`, and `organization.py` each fan out per-organization (and, for
`device.py`, per-device-type) work through `core/async_utils.py::ManagedTaskGroup`, bounded by
`settings.api.concurrency_limit` — never spawn raw unbounded `asyncio.gather`/tasks in a
coordinator's `_collect_impl()`. Separately, `settings.collectors.max_concurrent_collectors`
(default 5) bounds how many collectors' own group-clocked loops may be mid-run at once, globally.

## METRIC OWNERSHIP
- **Device-specific metrics**: Owned by respective device collectors (MR, MS, etc.)
- **Common device metrics**: Owned by main `DeviceCollector` (`meraki_device_up`)
- **Network metrics**: Owned by `NetworkHealthCollector`
- **Organization metrics**: Owned by `OrganizationCollector`
</paved_path>

<workflow>
## ADDING NEW COLLECTOR
1. **Choose inheritance**: `MetricCollector` (main) or domain-specific base class (sub)
2. **Declare endpoint group(s)**: `floor_seconds` based on data volatility, `priority` based on importance
3. **Define metrics** in `_initialize_metrics()` using domain-specific enums
4. **Implement collection** in `_collect_impl()` with error handling
5. **Register collector**: Auto via `@register_collector` or manual in coordinator
6. **Add tests** with factories and metric assertions
</workflow>

<fatal_implications>
- **NEVER implement collection logic in `__init__`** - use `_collect_impl()`
- **NEVER skip error handling** for API calls - use decorators
- **NEVER forget to register collectors** - use decorator or manual registration
- **NEVER block the event loop** - use `asyncio.to_thread()` for sync operations
- **NEVER call `self.api.organizations.getOrganizationNetworks` directly** - always go through `self.inventory.get_networks(org_id)` so `NetworkFilter` is enforced. `core/discovery.py::DiscoveryService` is the only sanctioned *unfiltered* bypass (audit-only, startup diagnostics); `alerts.py::AlertsCollector._fetch_networks_direct` and `core/api_helpers.py::APIHelper._fetch_networks_direct` are sanctioned *filtered* fallbacks for when `self.inventory` is unavailable (each manually reapplies `NetworkFilter`), not bypasses.
- **NEVER iterate org-wide SDK responses without filtering by `get_allowed_network_ids`** - rows referencing networks outside the filter must be skipped.
</fatal_implications>
