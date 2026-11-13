---
title: Extending Collectors
description: Add a Meraki metric collector, register its module, choose endpoint groups, and test its scheduled collection path.
---

# Extending the Collector System

Collectors gather metrics from the Meraki API. New collectors live in `src/meraki_dashboard_exporter/collectors/`. Always consult the relevant `AGENTS.md` in the target directory before making changes.

## Collector hierarchy and registration
- **Main collectors** are auto-registered with the no-arg `@register_collector` decorator and each runs its own group-clocked loop, scheduled by `CollectorManager`/`ExporterApp._collector_loop`. There is no update-tier argument to the decorator — cadence is derived per collector from the endpoint groups it declares (see [Scheduler Architecture](observability/scheduler.md)).
- **Registration is import-driven**: add your module to the import list in `src/meraki_dashboard_exporter/collectors/manager.py` so the decorator executes.
- **Sub-collectors** are instantiated by a parent coordinator (manual registration in the parent `__init__`).

## Measured extension cost

This is a closed-set measurement, not an estimate. A new top-level collector changes **three
existing files**: its module is added to `collectors/manager.py`'s import-to-register list, its
endpoint groups are declared, and its metrics are added to
`core/constants/metrics_constants.py` (excluding the new module, generated docs, and tests).

A genuinely new Meraki **product family** changes **six existing seams**:

1. `DeviceType` and `ProductType` in `src/meraki_dashboard_exporter/core/constants/device_constants.py`.
2. The exports of `src/meraki_dashboard_exporter/collectors/devices/__init__.py`.
3. The sub-collector imports and routing in `src/meraki_dashboard_exporter/collectors/device.py`.
4. `EndpointGroupName` and `OrgShape` in `src/meraki_dashboard_exporter/core/scheduler.py`.
5. `OrganizationInventory.get_org_shape` in `src/meraki_dashboard_exporter/services/inventory.py`.
6. `src/meraki_dashboard_exporter/core/constants/metrics_constants.py` — metric enum.

A new **model subtype** of an existing family costs **zero structural seams**: Catalyst/CS already
routes through MS and Catalyst CW through MR. Do not introduce declarative family registration to
avoid a cost that this measurement does not show for model subtypes.

## Basic steps
1. Create a new module under `collectors/` and add it to the import list in `collectors/manager.py`.
2. Define a class inheriting from `MetricCollector` (or the relevant base) and decorate it with `@register_collector`. Declare its endpoint group(s) (name, priority, `floor_seconds`, `cost_fn`) as the `endpoint_groups` class attribute, and add the group's name to `EndpointGroupName` in `core/scheduler.py` so the scheduler knows how to pace it.
3. Define metrics in `_initialize_metrics()` using `_create_gauge/_create_counter/_create_histogram/_create_info` and MetricName/LabelName enums.
4. Implement `_collect_impl()` with proper error handling (`with_error_handling`) and response validation (`validate_response_format` or Pydantic models). `validate_response_format` also normalises the Meraki SDK 3.x exhausted-retry error envelope, so prefer it for any new fetcher. The SDK is synchronous: call it only through `facade_for(self).call(...)`.
5. Use shared services:
   - `self.inventory` for org/network/device lookups. **Network fetches must go through `inventory.get_networks(org_id)`** (or `self.parent.inventory.get_networks(org_id)` from sub-collectors). Calling `getOrganizationNetworks` directly bypasses the configured `NetworkFilter` (`core/network_filter.py`).
   - `ManagedTaskGroup` with `settings.api.concurrency_limit` for bounded parallelism.
   - `_set_metric()` to ensure metric expiration tracking is applied.
6. Add metric enums to `core/constants/metrics_constants.py` and tests under `tests/`.
7. Regenerate docs with `just gen` (or an individual `just docs-*` recipe).

```python
@register_collector
class MyCollector(MetricCollector):
    endpoint_groups: ClassVar[tuple[EndpointGroup, ...]] = (
        EndpointGroup(
            name=EndpointGroupName.MY_GROUP,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda shape: 1.0,
        ),
    )

    def _initialize_metrics(self) -> None:
        self._example_metric = self._create_gauge(
            MyMetricName.EXAMPLE_METRIC,
            "Example metric description",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID],
        )

    async def _collect_impl(self) -> None:
        if not self._should_run_group(EndpointGroupName.MY_GROUP):
            return
        organizations = await self.inventory.get_organizations()
        async with ManagedTaskGroup(
            name="my_collector", max_concurrency=self.settings.api.concurrency_limit
        ) as group:
            for org in organizations:
                await group.create_task(self._process_org(org["id"]))
        self._mark_group_ran(EndpointGroupName.MY_GROUP)

    @with_error_handling(operation="Collect example data", continue_on_error=True)
    async def _process_org(self, org_id: str) -> None:
        raw = await facade_for(self).call(
            "getOrganizationExample",
            self.api.organizations.getOrganizationExample,
            org_id,
            org_id=org_id,
            total_pages="all",
        )
        rows = validate_response_format(raw, expected_type=list, operation="getOrganizationExample")
        for row in rows:
            labels = {LabelName.ORG_ID.value: org_id, LabelName.NETWORK_ID.value: row["networkId"]}
            self._set_metric(self._example_metric, labels, float(row["value"]))
```

## Error handling strategy
Use the error handling decorator to keep collectors resilient and to emit consistent error metrics:

```python
from ..core.error_handling import with_error_handling, ErrorCategory

@with_error_handling(
    operation="Fetch devices",
    continue_on_error=True,
    error_category=ErrorCategory.API_SERVER_ERROR,
)
async def _fetch_devices(self, org_id: str) -> list[Device] | None:
    ...
```

Common categories include `API_RATE_LIMIT`, `API_CLIENT_ERROR`, `API_SERVER_ERROR`,
`API_NOT_AVAILABLE`, `TIMEOUT`, `PARSING`, and `VALIDATION`.

Use `continue_on_error=True` for optional/partial data (per-org/per-network failures),
and `continue_on_error=False` for critical prerequisites (org discovery, auth).

## API response formats
Meraki endpoints may return a list directly or wrap items in a dict (often under `items`)
when pagination metadata is included. Prefer the shared validator:

```python
validated = validate_response_format(
    response,
    expected_type=list,
    operation="getOrganizationDevices",
)
```

If you must unpack manually, handle both `list` and `{"items": [...]}` formats and
log unexpected shapes.

## Collection patterns
- **Bounded concurrency**: use `ManagedTaskGroup` with `settings.api.concurrency_limit`.
- **Batching**: respect `*_BATCH_SIZE` and `BATCH_DELAY` when iterating large lists.
- **Inventory caching**: fetch orgs/networks/devices through `self.inventory`. The inventory is the single enforcement point for `NetworkFilter`; pass `unfiltered=True` only for explicit audit/diagnostic flows.
- **Per-collector timeout**: defaults to 240s (`CollectorSettings.collector_timeout`); plan work to fit, or split into smaller collectors.
- **Metric lifecycle**: call `_set_metric()` (or `_set_metric_value()` in sub-collectors).

## Testing
Use the helpers under `tests/` to build unit tests. Run them with:
```bash
just test
```
