<system_context>
Network health collectors for Meraki Dashboard Exporter - Handles network-level performance and health metrics including Bluetooth tracking, RF health, connection statistics, and data rates.
</system_context>

<critical_notes>
- **Inherit from BaseNetworkHealthCollector** for consistent network-level patterns
- **Network-scoped metrics**: Focus on network-wide aggregations and health indicators
- **Manual registration**: Network health collectors are registered in NetworkHealthCollector coordinator
- **MEDIUM update tier**: Network health data changes regularly (300s interval)
</critical_notes>

<file_map>
## NETWORK HEALTH COLLECTOR FILES
- `base.py` - BaseNetworkHealthCollector with common network health patterns
- `bluetooth.py` - Bluetooth client tracking and analytics
- `connection_stats.py` - Network connection quality and performance metrics
- `data_rates.py` - Network throughput and data transfer metrics
- `rf_health.py` - Radio frequency health and interference metrics
</file_map>

<paved_path>
## NETWORK HEALTH COLLECTOR PATTERN
```python
from .base import BaseNetworkHealthCollector
from ..core.constants.metrics_constants import MetricName
from ..core.metrics import LabelName

class ConnectionStatsCollector(BaseNetworkHealthCollector):
    """Collector for network connection statistics"""

    def _initialize_metrics(self) -> None:
        self.connection_success_rate = Gauge(
            MetricName.CONNECTION_SUCCESS_RATE.value,
            "Network connection success rate percentage",
            [LabelName.ORG_ID.value, LabelName.NETWORK_ID.value]
        )

    async def _collect_impl(self) -> None:
        organizations = await self._get_organizations()
        for org in organizations:
            networks = await self._fetch_networks(org.id)
            for network in networks:
                await self._collect_connection_stats(org.id, network.id)
```

## NETWORK-LEVEL API PATTERN
```python
@log_api_call("getNetworkWirelessConnectionStats")
async def _collect_connection_stats(self, org_id: str, network_id: str) -> None:
    self._track_api_call("getNetworkWirelessConnectionStats")

    # Network-level API calls use network ID
    connection_data = await asyncio.to_thread(
        self.api.wireless.getNetworkWirelessConnectionStats,
        network_id,
        timespan=3600
    )

    self._update_connection_metrics(org_id, network_id, connection_data)
```
</paved_path>

<patterns>
## NETWORK HEALTH METRIC CATEGORIES

### RF Health Metrics
- **Signal quality**: Signal strength and noise floor measurements
- **Interference**: RF interference and channel conflicts
- **Channel utilization**: Network-wide channel usage patterns
- **Coverage**: Signal coverage and dead zones

### Connection Statistics
- **Success rates**: Connection attempt vs success ratios
- **Association time**: Time to establish connections
- **Roaming performance**: Handoff success and timing
- **Failure analysis**: Connection failure categorization

### Data Rate Metrics
- **Throughput**: Network-level data transfer rates
- **Bandwidth utilization**: Usage vs available bandwidth
- **Quality of service**: QoS performance metrics
- **Application performance**: Per-application network metrics

### Bluetooth Analytics
- **Device tracking**: Bluetooth device presence and movement
- **Dwell time**: How long devices stay in areas
- **Foot traffic**: Movement patterns and analytics
- **Zone analytics**: Area-specific presence metrics
</patterns>

<examples>
## Complete Network Health Collector Example
```python
import asyncio
from prometheus_client import Gauge
from ..core.constants.metrics_constants import MetricName
from ..core.metrics import LabelName
from ..core.error_handling import with_error_handling
from ..core.logging_decorators import log_api_call
from .base import BaseNetworkHealthCollector

class RFHealthCollector(BaseNetworkHealthCollector):
    """Collector for RF health and interference metrics"""

    def _initialize_metrics(self) -> None:
        self.rf_quality_score = Gauge(
            MetricName.RF_QUALITY_SCORE.value,
            "RF quality score for the network",
            [LabelName.ORG_ID.value, LabelName.NETWORK_ID.value, LabelName.BAND.value]
        )

        self.interference_level = Gauge(
            MetricName.INTERFERENCE_LEVEL.value,
            "RF interference level in dBm",
            [LabelName.ORG_ID.value, LabelName.NETWORK_ID.value, LabelName.BAND.value]
        )

    @with_error_handling("Collect RF health metrics", continue_on_error=True)
    async def _collect_impl(self) -> None:
        organizations = await self._get_organizations()

        for org in organizations:
            networks = await self._fetch_networks(org.id)

            for network in networks:
                # Only collect for wireless networks
                if "wireless" in network.product_types:
                    await self._collect_rf_health(org.id, network.id)

    @log_api_call("getNetworkWirelessRfProfiles")
    async def _collect_rf_health(self, org_id: str, network_id: str) -> None:
        """Collect RF health metrics for a wireless network"""
        self._track_api_call("getNetworkWirelessRfProfiles")

        try:
            # Get RF profile data
            rf_profiles = await asyncio.to_thread(
                self.api.wireless.getNetworkWirelessRfProfiles,
                network_id
            )

            # Get channel utilization data
            channel_data = await asyncio.to_thread(
                self.api.wireless.getNetworkWirelessChannelUtilizationHistory,
                network_id,
                timespan=3600,
                resolution=300
            )

            # Process and update metrics
            self._update_rf_metrics(org_id, network_id, rf_profiles, channel_data)

        except Exception as e:
            self.logger.error(f"Failed to collect RF health for network {network_id}: {e}")

    def _update_rf_metrics(self, org_id: str, network_id: str, rf_profiles: list, channel_data: list) -> None:
        """Update RF health metrics from collected data"""

        # Calculate RF quality scores by band
        band_quality = self._calculate_rf_quality(rf_profiles, channel_data)

        for band, metrics in band_quality.items():
            # RF quality score (0-100)
            self.rf_quality_score.labels(
                org_id=org_id,
                network_id=network_id,
                band=band
            ).set(metrics["quality_score"])

            # Interference level
            self.interference_level.labels(
                org_id=org_id,
                network_id=network_id,
                band=band
            ).set(metrics["interference_dbm"])

    def _calculate_rf_quality(self, rf_profiles: list, channel_data: list) -> dict:
        """Calculate RF quality metrics from raw data"""
        band_metrics = {}

        # Process channel utilization data
        for entry in channel_data:
            for band_data in entry.get("byBand", []):
                band = band_data.get("band")
                if not band:
                    continue

                if band not in band_metrics:
                    band_metrics[band] = {
                        "utilization_samples": [],
                        "interference_samples": []
                    }

                # Collect utilization samples
                utilization = band_data.get("utilization", {}).get("total", 0)
                band_metrics[band]["utilization_samples"].append(utilization)

                # Collect interference samples (if available)
                interference = band_data.get("interference", {}).get("avg", -70)
                band_metrics[band]["interference_samples"].append(interference)

        # Calculate final metrics
        result = {}
        for band, data in band_metrics.items():
            avg_utilization = sum(data["utilization_samples"]) / len(data["utilization_samples"]) if data["utilization_samples"] else 0
            avg_interference = sum(data["interference_samples"]) / len(data["interference_samples"]) if data["interference_samples"] else -70

            # Quality score: inverse of utilization (0-100)
            quality_score = max(0, 100 - avg_utilization)

            result[band] = {
                "quality_score": quality_score,
                "interference_dbm": avg_interference
            }

        return result
```

## Bluetooth Tracking Collector Example
```python
class BluetoothCollector(BaseNetworkHealthCollector):
    """Collector for Bluetooth analytics and tracking"""

    def _initialize_metrics(self) -> None:
        self.bluetooth_clients = Gauge(
            MetricName.BLUETOOTH_CLIENTS.value,
            "Number of Bluetooth clients detected",
            [LabelName.ORG_ID.value, LabelName.NETWORK_ID.value, LabelName.LOCATION.value]
        )

        self.dwell_time_avg = Gauge(
            MetricName.DWELL_TIME_AVERAGE.value,
            "Average dwell time for Bluetooth clients in seconds",
            [LabelName.ORG_ID.value, LabelName.NETWORK_ID.value, LabelName.LOCATION.value]
        )

    @log_api_call("getNetworkBluetoothClients")
    async def _collect_bluetooth_analytics(self, org_id: str, network_id: str) -> None:
        """Collect Bluetooth analytics for network"""
        self._track_api_call("getNetworkBluetoothClients")

        try:
            bluetooth_data = await asyncio.to_thread(
                self.api.bluetooth.getNetworkBluetoothClients,
                network_id,
                timespan=3600
            )

            # Process location-based analytics
            location_stats = self._process_bluetooth_data(bluetooth_data)

            for location, stats in location_stats.items():
                self.bluetooth_clients.labels(
                    org_id=org_id,
                    network_id=network_id,
                    location=location
                ).set(stats["client_count"])

                self.dwell_time_avg.labels(
                    org_id=org_id,
                    network_id=network_id,
                    location=location
                ).set(stats["avg_dwell_time"])

        except Exception as e:
            self.logger.error(f"Failed to collect Bluetooth analytics: {e}")
```
</examples>

<workflow>
## ADDING NEW NETWORK HEALTH COLLECTOR
1. **Identify network scope**: Ensure metric applies to network-level health
2. **Inherit from BaseNetworkHealthCollector**: Provides network iteration patterns
3. **Choose appropriate APIs**: Use network-level endpoints rather than organization-level
4. **Define network health metrics**: Focus on performance and quality indicators
5. **Handle wireless-only metrics**: Check network product types before collection
6. **Register in coordinator**: Add to NetworkHealthCollector's subcollectors list
7. **Test with various network types**: Ensure compatibility across network configurations
</workflow>

<api_quirks>
## NETWORK HEALTH API LIMITATIONS
- **Wireless-only metrics**: Many network health APIs only work with wireless networks
- **Data availability**: Not all networks have complete health data
- **Timespan requirements**: Some endpoints require specific timespan values
- **Resolution parameters**: Channel utilization may need resolution parameter
- **Product type filtering**: Check network.product_types before making wireless API calls
</api_quirks>

<hatch>
## ALTERNATIVE NETWORK HEALTH APPROACHES
- **Aggregation strategies**: Combine device-level metrics into network summaries
- **Historical trending**: Calculate health trends over time windows
- **Threshold-based alerting**: Convert continuous metrics to health status indicators
- **Cross-network comparison**: Benchmark network performance against organization averages
</hatch>

<fatal_implications>
- **NEVER assume all networks support wireless metrics** - check product types
- **NEVER aggregate metrics across different network types** without proper labeling
- **NEVER skip network product type validation** before making wireless API calls
- **NEVER ignore timespan constraints** for network health endpoints
</fatal_implications>
