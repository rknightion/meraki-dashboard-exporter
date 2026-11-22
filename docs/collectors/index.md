# Collectors Overview

Collectors run and are organized as summarized below.

## Organization
- **CollectorManager** orchestrates collection runs and loads auto-registered collectors.
- **Main collectors** own shared metrics and delegate to device/network/org sub-collectors.
- **Sub-collectors** are registered by their parent coordinator.

## Execution Model
- **Update schedules**: Collectors run on scheduler-solved cadences (see [Scheduler Architecture](../observability/scheduler.md)).
- **Shared inventory**: Cached org/network/device inventories reduce duplicate API calls across collectors.
- **Metric lifecycle**: Metrics set through expiration-aware helpers are cleaned up when stale.
- **Health & cardinality**: The exporter emits collector health and cardinality metrics for operational visibility.

For the full list of collectors, see the generated [Collector Reference](reference.md).
