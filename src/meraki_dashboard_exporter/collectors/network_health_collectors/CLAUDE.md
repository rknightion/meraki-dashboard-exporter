<system_context>
Network health collectors for Meraki Dashboard Exporter - Handles network-level performance and health metrics including Bluetooth tracking, RF health, connection statistics, and data rates.
</system_context>

<critical_notes>
- **Inherit from `BaseNetworkHealthCollector`** (in `base.py`) for consistent network-level patterns
- **Network-scoped metrics**: Focus on network-wide aggregations and health indicators
- **Manual registration**: Sub-collectors registered in `NetworkHealthCollector` coordinator
- **MEDIUM update tier**: Network health data changes regularly (300s interval)
- **Wireless-only**: Many network health APIs only work with wireless networks - check `network.product_types`
</critical_notes>

<file_map>
## NETWORK HEALTH COLLECTOR FILES
- `base.py` - `BaseNetworkHealthCollector` with common patterns; initialized with `parent: NetworkHealthCollector`
- `bluetooth.py` - Bluetooth client tracking and analytics
- `connection_stats.py` - Network connection quality and performance metrics
- `data_rates.py` - Network throughput and data transfer metrics
- `rf_health.py` - Radio frequency health and interference metrics
</file_map>

<paved_path>
## NETWORK HEALTH COLLECTOR PATTERN
```python
from .base import BaseNetworkHealthCollector

class MyNetworkHealthCollector(BaseNetworkHealthCollector):
    def _initialize_metrics(self) -> None:
        self._my_metric = self.parent._create_gauge(
            NetworkHealthMetricName.SOME_METRIC,
            "Description",
            labelnames=[LabelName.ORG_ID.value, LabelName.NETWORK_ID.value],
        )

    async def _collect_for_network(self, org_id: str, network_id: str) -> None:
        # Network-level API calls use network ID
        data = await asyncio.to_thread(
            self.api.wireless.getNetworkWirelessConnectionStats,
            network_id,
            timespan=3600,
        )
```
</paved_path>

<api_quirks>
- **Wireless-only metrics**: Check `network.product_types` before making wireless API calls
- **Timespan requirements**: Some endpoints require specific timespan values
- **Resolution parameters**: Channel utilization may need `resolution` parameter
</api_quirks>

<fatal_implications>
- **NEVER assume all networks support wireless metrics** - check product types
- **NEVER aggregate metrics across different network types** without proper labeling
- **NEVER ignore timespan constraints** for network health endpoints
</fatal_implications>
