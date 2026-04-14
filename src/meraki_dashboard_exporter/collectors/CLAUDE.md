<system_context>
Meraki Dashboard Exporter Collectors - All metric collection logic organized by domain (devices, networks, organizations). Implements the collector pattern with automatic registration and tiered update scheduling.
</system_context>

<critical_notes>
- **Follow update tiers**: FAST (60s), MEDIUM (300s), SLOW (900s) based on data volatility
- **Main collectors**: Use `@register_collector()` decorator for auto-registration
- **Sub-collectors**: Manual registration in parent coordinator's `__init__`
- **Inherit from appropriate base**: `MetricCollector`, `BaseDeviceCollector`, etc.
- **Implement required methods**: `_initialize_metrics()`, `_collect_impl()`
</critical_notes>

<file_map>
## COLLECTOR ORGANIZATION
### Subdirectories (each has its own CLAUDE.md)
- `devices/` - Device-specific collectors (MR, MS, MX, MT, MG, MV) - See `devices/CLAUDE.md`
- `network_health_collectors/` - Network health metrics - See `network_health_collectors/CLAUDE.md`
- `organization_collectors/` - Organization-level metrics - See `organization_collectors/CLAUDE.md`

### Coordinator Files
- `manager.py` - `CollectorManager` orchestrates all collectors with tiered scheduling
- `device.py` - `DeviceCollector` coordinator for device-specific sub-collectors (MEDIUM tier)
- `network_health.py` - `NetworkHealthCollector` coordinator (MEDIUM tier)
- `organization.py` - `OrganizationCollector` coordinator (MEDIUM tier)
- `config.py` - `ConfigCollector` for configuration/security settings (SLOW tier)

### Shared Infrastructure
- `subcollector_mixin.py` - `SubCollectorMixin` providing common sub-collector delegation patterns (_set_metric_value, _track_api_call, update_api)

### Standalone Collectors
- `alerts.py` - Alert/event collection
- `clients.py` - Client device tracking
- `mt_sensor.py` - FAST-tier standalone sensor data collection
- `webhook_metrics.py` - Event-driven webhook metric sink (NOT tier-registered; updated via inbound HTTP pushes)
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
    def _initialize_metrics(self) -> None:
        ...

    async def _collect_impl(self) -> None:
        ...
```

### Sub-collector (Manual registration in parent coordinator)
Sub-collectors are instantiated in their parent coordinator's `__init__` and called during the parent's `_collect_impl()`.

## UPDATE TIER SELECTION
- **FAST (60s)**: Real-time status, critical alerts, sensor readings
- **MEDIUM (300s)**: Device metrics, performance data, client counts
- **SLOW (900s)**: License usage, organization summaries, configuration

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
</fatal_implications>
