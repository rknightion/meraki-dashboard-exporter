<system_context>
Meraki Dashboard Exporter Collectors - All metric collection logic organized by domain (devices, networks, organizations). Implements the collector pattern with automatic registration and tiered update scheduling.
</system_context>

<critical_notes>
- **Follow update tiers**: FAST (60s), MEDIUM (300s), SLOW (900s) based on data volatility (default per-collector timeout: 240s, configurable via `CollectorSettings.collector_timeout`, range 30-600s)
- **Main collectors**: Use `@register_collector(tier)` decorator (`core/registry.py`) for auto-registration; real base class lives in `core/collector.py::MetricCollector`, not in this directory
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
- `device.py` - `DeviceCollector` coordinator (MEDIUM tier) fanning out to per-device-type sub-collectors (MG/MR/MS/MS-stack/MT/MV/MX) via `ManagedTaskGroup`, bounded by `settings.api.concurrency_limit`
- `network_health.py` - `NetworkHealthCollector` coordinator (MEDIUM tier) fanning out to `network_health_collectors/` (bluetooth, connection_stats, data_rates, rf_health, ssid_performance) via `ManagedTaskGroup`
- `organization.py` - `OrganizationCollector` coordinator (MEDIUM tier) fanning out to `organization_collectors/` (`APIUsageCollector`, `ClientOverviewCollector`, `LicenseCollector`) via `ManagedTaskGroup`; the only collector that also receives an `org_health_tracker` kwarg from the manager
- `config.py` - `ConfigCollector` for configuration/security settings (SLOW tier)

### Shared Infrastructure
- `subcollector_mixin.py` - `SubCollectorMixin` providing common sub-collector delegation patterns (`_set_metric_value`, `_track_api_call`, `update_api`); mixed into `devices/base.py::BaseDeviceCollector`, `network_health_collectors/base.py::BaseNetworkHealthCollector`, `organization_collectors/base.py::BaseOrganizationCollector`, and standalone sub-collectors (`devices/mx_firewall.py`, `devices/mx_vpn.py`, `devices/ms_stack.py`)

### Standalone Collectors
- `alerts.py` - `AlertsCollector` (MEDIUM tier) - alert/event collection
- `clients.py` - `ClientsCollector` (MEDIUM tier) - client device tracking
- `mt_sensor.py` - `MTSensorCollector` (FAST tier) - standalone sensor data collection
- `mt_alerts.py` - `MTSensorAlertsCollector` (MEDIUM tier) - MT sensor alert collection
- `webhook_metrics.py` - `WebhookMetricsCollector` - event-driven webhook metric sink; a plain class (does NOT inherit `MetricCollector`, NOT `@register_collector`-decorated, NOT tier-registered); updated via inbound HTTP pushes from `core/webhook_handler.py`
</file_map>

<paved_path>
## COLLECTOR REGISTRATION

### Main Collector (Auto-registered via decorator)
```python
from ..core.registry import register_collector
from ..core.collector import MetricCollector
from ..core.constants.device_constants import UpdateTier


@register_collector(UpdateTier.MEDIUM)
class MyCollector(MetricCollector):
    def _initialize_metrics(self) -> None: ...

    async def _collect_impl(self) -> None: ...
```
`register_collector()` (`core/registry.py`) just appends the class to a module-level
`_COLLECTOR_REGISTRY: dict[UpdateTier, list[type[MetricCollector]]]` at import time — it does
not instantiate anything.

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
2. **Read the registry**: calls `core/registry.py::get_registered_collectors()` to get the
   tier -> class mapping built in step 1.
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

## UPDATE TIER SELECTION
- **FAST (60s)**: Real-time status, critical alerts, sensor readings
- **MEDIUM (300s)**: Device metrics, performance data, client counts
- **SLOW (900s)**: License usage, organization summaries, configuration

## CONCURRENCY WITHIN A COORDINATOR
`device.py`, `network_health.py`, and `organization.py` each fan out per-organization (and, for
`device.py`, per-device-type) work through `core/async_utils.py::ManagedTaskGroup`, bounded by the
relevant `settings.api.concurrency_limit*` setting — never spawn raw unbounded `asyncio.gather`/tasks
in a coordinator's `_collect_impl()`.

## METRIC OWNERSHIP
- **Device-specific metrics**: Owned by respective device collectors (MR, MS, etc.)
- **Common device metrics**: Owned by main `DeviceCollector` (`meraki_device_up`)
- **Network metrics**: Owned by `NetworkHealthCollector`
- **Organization metrics**: Owned by `OrganizationCollector`
</paved_path>

<workflow>
## ADDING NEW COLLECTOR
1. **Choose inheritance**: `MetricCollector` (main) or domain-specific base class (sub)
2. **Select update tier**: Based on data volatility and importance
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
