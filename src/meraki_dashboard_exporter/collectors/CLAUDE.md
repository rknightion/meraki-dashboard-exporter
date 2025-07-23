<system_context>
Meraki Dashboard Exporter Collectors - Contains all metric collection logic organized by domain (devices, networks, organizations). Implements the collector pattern with automatic registration and tiered update scheduling.
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
- `devices/` - Device-specific collectors (MR, MS, MX, MT, MG, MV) - See `devices/CLAUDE.md`
- `network_health_collectors/` - Network health metrics - See `network_health_collectors/CLAUDE.md`
- `organization_collectors/` - Organization-level metrics - See `organization_collectors/CLAUDE.md`
- `manager.py` - Collector orchestration and scheduling
- `config.py` - Configuration-based collector management
- `device.py` - Main device collector coordinator
- `network_health.py` - Network health coordinator
- `organization.py` - Organization coordinator
- `alerts.py` - Alert/event collection
- `clients.py` - Client device tracking
- `mt_sensor.py` - Sensor data collection
</file_map>

<paved_path>
## COLLECTOR REGISTRATION PATTERNS

### Main Collector (Auto-registered)
```python
from ..core.collector import register_collector, MetricCollector, UpdateTier

@register_collector(UpdateTier.MEDIUM)
class MyCollector(MetricCollector):
    def _initialize_metrics(self) -> None:
        # Define metrics here
        pass

    async def _collect_impl(self) -> None:
        # Collection logic here
        pass
```

### Sub-collector (Manual registration)
```python
# In parent coordinator's __init__
from .my_subcollector import MySubCollector

class MainCollector(MetricCollector):
    def __init__(self, api_client, config):
        super().__init__(api_client, config)
        self.subcollectors = [
            MySubCollector(api_client, config),
            # Other subcollectors...
        ]
```

### Device-Specific Collector
```python
from .base import BaseDeviceCollector

class MRCollector(BaseDeviceCollector):
    """Collector for MR (Wireless) devices"""

    def _initialize_metrics(self) -> None:
        self.channel_utilization = Gauge(
            MetricName.CHANNEL_UTILIZATION.value,
            "Wireless channel utilization",
            [LabelName.ORG_ID.value, LabelName.SERIAL.value, LabelName.BAND.value]
        )
```
</paved_path>

<patterns>
## UPDATE TIER SELECTION
- **FAST (60s)**: Real-time status, critical alerts, client counts
- **MEDIUM (300s)**: Device metrics, sensor readings, performance data
- **SLOW (900s)**: License usage, organization summaries, historical data

## METRIC OWNERSHIP
- **Device-specific metrics**: Owned by respective device collectors (MR, MS, etc.)
- **Common device metrics**: Owned by main DeviceCollector (`meraki_device_up`)
- **Network metrics**: Owned by NetworkHealthCollector
- **Organization metrics**: Owned by OrganizationCollector
</patterns>

<examples>
## Complete Device Collector Example
```python
from prometheus_client import Gauge
from ..core.collector import register_collector, UpdateTier
from ..core.constants.metrics_constants import MetricName
from ..core.metrics import LabelName
from ..core.error_handling import with_error_handling
from ..core.logging_decorators import log_api_call
from .base import BaseDeviceCollector

@register_collector(UpdateTier.MEDIUM)
class ExampleDeviceCollector(BaseDeviceCollector):
    """Collector for example device metrics"""

    def _initialize_metrics(self) -> None:
        self.signal_strength = Gauge(
            MetricName.SIGNAL_STRENGTH.value,
            "Device signal strength in dBm",
            [LabelName.ORG_ID.value, LabelName.SERIAL.value]
        )

    @with_error_handling("Collect device metrics", continue_on_error=True)
    async def _collect_impl(self) -> None:
        organizations = await self._get_organizations()
        for org in organizations:
            await self._process_organization(org.id)

    @log_api_call("getOrganizationDevicesSignalStrength")
    async def _process_organization(self, org_id: str) -> None:
        devices = await self._fetch_devices(org_id, product_types=["MR"])

        for device in devices:
            signal_data = await self._fetch_signal_strength(device.serial)
            if signal_data:
                self.signal_strength.labels(
                    org_id=org_id,
                    serial=device.serial
                ).set(signal_data.strength)
```

## Coordinator Pattern Example
```python
class DeviceCollector(MetricCollector):
    """Main device collector that coordinates device-specific collectors"""

    def __init__(self, api_client, config):
        super().__init__(api_client, config)
        # Register device-specific collectors
        self.device_collectors = [
            MRCollector(api_client, config),  # Wireless
            MSCollector(api_client, config),  # Switches
            MXCollector(api_client, config),  # Security appliances
            MTCollector(api_client, config),  # Sensors
            MGCollector(api_client, config),  # Cellular gateways
            MVCollector(api_client, config),  # Cameras
        ]

    async def _collect_impl(self) -> None:
        # Common device metrics (meraki_device_up)
        await self._collect_device_status()

        # Delegate to device-specific collectors
        for collector in self.device_collectors:
            await collector.collect()
```
</examples>

<workflow>
## ADDING NEW COLLECTOR
1. **Choose inheritance**: `MetricCollector`, `BaseDeviceCollector`, or other base
2. **Select update tier**: Based on data volatility and importance
3. **Define metrics** in `_initialize_metrics()` using enums
4. **Implement collection** in `_collect_impl()` with error handling
5. **Register collector**: Auto via decorator or manual in coordinator
6. **Add tests** with factories and metric assertions
7. **Update documentation** if adding new metric types
</workflow>

<common_tasks>
## DEBUGGING COLLECTORS
1. **Check registration**: Verify collector appears in startup logs
2. **Monitor API calls**: Use DEBUG logging to see API interactions
3. **Validate metrics**: Check `/metrics` endpoint for expected metrics
4. **Test error handling**: Verify graceful degradation on API errors
5. **Review update intervals**: Ensure appropriate tier assignment
</common_tasks>

<fatal_implications>
- **NEVER implement collection logic in `__init__`** - use `_collect_impl()`
- **NEVER skip error handling** for API calls - use decorators
- **NEVER forget to register collectors** - use decorator or manual registration
- **NEVER block the event loop** - use `asyncio.to_thread()` for sync operations
</fatal_implications>
