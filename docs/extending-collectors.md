# Extending the Collector System

This guide explains how to add new collectors to the Meraki Dashboard Exporter.

## Quick Start: Adding a New Collector

### 1. Create Your Collector File
Create a new file in `src/meraki_dashboard_exporter/collectors/`:

```python
# src/meraki_dashboard_exporter/collectors/my_new_collector.py
from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.collector import MetricCollector
from ..core.constants import UpdateTier, OrgMetricName
from ..core.error_handling import with_error_handling
from ..core.logging import get_logger
from ..core.metrics import LabelName
from ..core.registry import register_collector

if TYPE_CHECKING:
    from meraki import DashboardAPI
    from prometheus_client import CollectorRegistry
    from ..core.config import Settings

logger = get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)  # Auto-registers with manager
class MyNewCollector(MetricCollector):
    """Collector for my new metrics."""
    
    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics."""
        self._my_metric = self._create_gauge(
            OrgMetricName.ORG_MY_METRIC,  # Add to constants first!
            "Description of my metric",
            labelnames=[LabelName.ORG_ID, LabelName.ORG_NAME]
        )
    
    @with_error_handling(
        operation="Collect my metrics",
        continue_on_error=True,
    )
    async def _collect_impl(self) -> None:
        """Implement collection logic."""
        # Fetch organizations
        organizations = await self._fetch_organizations()
        
        for org in organizations:
            value = await self._collect_org_data(org["id"])
            
            self._set_metric_value(
                "_my_metric",
                {
                    LabelName.ORG_ID: org["id"],
                    LabelName.ORG_NAME: org["name"],
                },
                value
            )
```

### 2. Add Metric Names to Constants
Add your metric names to the appropriate enum:

```python
# src/meraki_dashboard_exporter/core/constants/metrics_constants.py
class OrgMetricName(StrEnum):
    # ... existing metrics ...
    ORG_MY_METRIC = "meraki_organization_my_metric"
```

### 3. That's It!
The collector will be automatically discovered and registered. No manual registration needed!

## Detailed Guide

### Choosing the Right Base Class

#### For Simple Collectors
Inherit directly from `MetricCollector`:
```python
@register_collector(UpdateTier.MEDIUM)
class SimpleCollector(MetricCollector):
    """A standalone collector."""
```

#### For Device-Specific Collectors
Create a sub-collector without the decorator:
```python
# src/meraki_dashboard_exporter/collectors/devices/my_device.py
from .base import BaseDeviceCollector

class MyDeviceCollector(BaseDeviceCollector):
    """Collector for MY device type."""
    
    def collect(self, device: dict[str, Any]) -> None:
        """Collect metrics for a single device."""
        # Device-specific logic
```

Then register in the parent:
```python
# In DeviceCollector.__init__
self.my_collector = MyDeviceCollector(self)
```

### Using Error Handling

Always use the error handling decorator:

```python
@with_error_handling(
    operation="Fetch widget data",
    continue_on_error=True,  # Don't fail entire collection
    error_category=ErrorCategory.API_CLIENT_ERROR,
)
async def _fetch_widgets(self, org_id: str) -> list[Widget] | None:
    """Fetch widgets with automatic error handling."""
    response = await self.api.organizations.getOrganizationWidgets(org_id)
    
    # Validate response format
    widgets = validate_response_format(
        response,
        expected_type=list,
        operation="getOrganizationWidgets"
    )
    
    return widgets
```

### Working with Update Tiers

Choose the appropriate tier based on data characteristics:

```python
# Real-time data (sensors, environmental)
@register_collector(UpdateTier.FAST)  # 60 seconds

# Operational data (status, clients, usage)
@register_collector(UpdateTier.MEDIUM)  # 5 minutes

# Configuration data (licenses, settings)
@register_collector(UpdateTier.SLOW)  # 15 minutes
```

### Using API Helpers

Leverage the APIHelper for common patterns:

```python
async def _collect_impl(self) -> None:
    """Use API helpers for cleaner code."""
    # Get organizations (handles single/multi-org configs)
    organizations = await self.api_helper.get_organizations()
    
    # Get devices with filtering
    devices = await self.api_helper.get_organization_devices(
        org_id,
        product_types=["wireless", "switch"],
        models=["MR36", "MS250"]
    )
    
    # Process in batches
    await self.api_helper.process_in_batches(
        devices,
        self._process_device,
        batch_size=10,
        description="devices"
    )
```

### Metric Naming Conventions

Follow these patterns for metric names:

```python
# Organization level
meraki_organization_<metric>_<unit>
meraki_organization_widgets_total

# Network level  
meraki_network_<metric>_<unit>
meraki_network_bandwidth_mbps

# Device level
meraki_<device_type>_<metric>_<unit>
meraki_mr_clients_connected
meraki_ms_port_enabled

# Use appropriate units
_total          # For counters
_bytes          # For data sizes
_seconds        # For durations
_percent        # For percentages (0-100)
_ratio          # For ratios (0-1)
```

### Testing Your Collector

Create a test file using the test helpers:

```python
# tests/collectors/test_my_new_collector.py
import pytest

from meraki_dashboard_exporter.collectors.my_new_collector import MyNewCollector
from meraki_dashboard_exporter.core.constants import UpdateTier
from meraki_dashboard_exporter.testing.base import BaseCollectorTest
from meraki_dashboard_exporter.testing.factories import OrganizationFactory


class TestMyNewCollector(BaseCollectorTest):
    collector_class = MyNewCollector
    update_tier = UpdateTier.MEDIUM
    
    @pytest.mark.asyncio
    async def test_collect_basic(self, collector, mock_api_builder, metrics):
        """Test basic collection."""
        # Set up test data
        org = OrganizationFactory.create()
        
        # Configure mock API
        api = (mock_api_builder
            .with_organizations([org])
            .with_custom_response("getOrganizationWidgets", [
                {"id": "1", "value": 42}
            ])
            .build())
        
        collector.api = api
        
        # Run collection
        await self.run_collector(collector)
        
        # Verify metrics
        self.assert_collector_success(collector, metrics)
        metrics.assert_gauge_value(
            "meraki_organization_my_metric",
            42,
            org_id=org["id"]
        )
```

## Common Patterns

### Pattern 1: Hierarchical Collection
```python
async def _collect_impl(self) -> None:
    """Collect metrics hierarchically."""
    for org in await self.api_helper.get_organizations():
        networks = await self.api_helper.get_organization_networks(org["id"])
        
        for network in networks:
            devices = await self.api_helper.get_organization_devices(
                org["id"],
                network_ids=[network["id"]]
            )
            
            # Set network-level metric
            self._network_device_count.labels(
                org_id=org["id"],
                network_id=network["id"],
                network_name=network["name"]
            ).set(len(devices))
```

### Pattern 2: Time-Based Data
```python
async def _collect_bandwidth_usage(self, network_id: str) -> None:
    """Collect time-based metrics."""
    # Get last 5 minutes of data
    usage = await self.api_helper.get_time_based_data(
        self.api.networks.getNetworkTraffic,
        "getNetworkTraffic",
        timespan=300,
        network_id=network_id
    )
    
    if usage:
        # Use most recent data point
        latest = usage[-1]
        self._set_metric_value(
            "_bandwidth_mbps",
            {"network_id": network_id},
            latest["value"]
        )
```

### Pattern 3: Conditional Metrics
```python
def _set_device_metric(self, device: dict[str, Any]) -> None:
    """Set metrics based on device type."""
    device_type = device["model"][:2]
    
    if device_type == "MR":
        # Access point specific metrics
        self._mr_specific_metric.labels(...).set(...)
    elif device_type == "MS":
        # Switch specific metrics
        self._ms_specific_metric.labels(...).set(...)
```

## Troubleshooting

### Collector Not Found
- Ensure file is in `collectors/` directory
- Check that `@register_collector` decorator is used
- Verify no import errors in your module

### Metrics Not Appearing
- Check `_initialize_metrics()` is implemented
- Verify metric names are added to constants
- Ensure `_set_metric_value()` is called with correct parameters
- Check logs for errors during collection

### API Errors
- Use `@with_error_handling` decorator
- Set `continue_on_error=True` for non-critical operations
- Check API endpoint availability for your organization
- Verify API permissions

## Best Practices

1. **Always use type hints** for better IDE support and documentation
2. **Follow existing patterns** - consistency is key
3. **Add comprehensive docstrings** with examples
4. **Use structured logging** with context
5. **Handle errors gracefully** - partial collection is better than none
6. **Test edge cases** - empty responses, API errors, malformed data
7. **Monitor performance** - use collector metrics to track duration
8. **Document API quirks** in code comments