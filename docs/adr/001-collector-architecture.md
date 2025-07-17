# ADR-001: Collector Architecture

**Status**: Accepted
**Date**: 2024-01-15
**Decision Makers**: Development Team

## Context

The Meraki Dashboard Exporter needs to collect metrics from various Meraki API endpoints at different intervals while managing API rate limits, handling errors gracefully, and maintaining good performance.

## Decision

We will use a hierarchical collector architecture with the following key patterns:

### 1. Three-Tier Update System
- **FAST** (60s): Real-time metrics like sensor readings
- **MEDIUM** (300s): Operational metrics aligned with Meraki's 5-minute data blocks
- **SLOW** (900s): Configuration and slowly-changing data

### 2. Collector Hierarchy
```
CollectorManager
├── Main Collectors (auto-registered via @register_collector)
│   ├── OrganizationCollector
│   │   └── Sub-collectors (manually registered)
│   │       ├── APIUsageCollector
│   │       ├── LicenseCollector
│   │       └── ClientOverviewCollector
│   ├── DeviceCollector
│   │   └── Device Type Collectors
│   │       ├── MRCollector
│   │       ├── MSCollector
│   │       └── (others)
│   └── NetworkHealthCollector
│       └── Health Sub-collectors
```

### 3. Metric Ownership Pattern
Each collector owns its specific metrics:
- Main collectors own shared metrics
- Sub-collectors own type-specific metrics
- Metrics are initialized in `_initialize_metrics()` method

### 4. Registration Pattern
Main collectors use decorator-based auto-registration:
```python
@register_collector(UpdateTier.MEDIUM)
class MyCollector(MetricCollector):
    pass
```

## Consequences

### Positive
- Clear separation of concerns
- Easy to add new collectors
- Metrics are organized by ownership
- Update intervals align with API characteristics
- Reduced code duplication

### Negative
- More complex initialization flow
- Sub-collectors require manual registration
- Potential for metric naming conflicts

## Alternatives Considered

1. **Flat collector structure**: Simpler but would lead to massive files
2. **Single update interval**: Simpler but inefficient API usage
3. **Dynamic metric creation**: More flexible but harder to track metrics

## Implementation Notes

- Use `BaseDeviceCollector` for common device functionality
- Always call parent's `_initialize_metrics()` when extending
- Track API calls via `_track_api_call()` for monitoring
- Use error categories for proper error tracking
