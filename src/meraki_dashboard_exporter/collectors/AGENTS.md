# Collectors

## Registration and discovery

- Top-level collectors take the no-arg `@register_collector` (`core/registry.py`), which only appends
  the class to a module-level list at import time. Registration therefore happens only if the module
  is imported: a new top-level collector module must be added to the explicit import block in
  `CollectorManager._initialize_collectors()` (`manager.py`) or it never registers and never runs,
  with no error.
- Sub-collectors are instantiated by hand in their parent coordinator's `__init__` and never carry
  the decorator.
- A registered class is matched against `settings.collectors.active_collectors` by
  `ClassName.replace("Collector", "").lower()`. A configured name matching no class only warns, so a
  typo disables a collector quietly.
- Implement `_initialize_metrics()` and `_collect_impl()`. Never override `collect()`: it wraps
  `_collect_impl()` with tracing and the duration/error/success metrics.

## SDK calls

Reach the Meraki SDK through the shared facade, not a bare `asyncio.to_thread`. It owns rate
limiting, tracing and call accounting:

```python
response = await facade_for(self).call(
    "getOrganizationSomeEndpoint",
    self.api.organizations.getOrganizationSomeEndpoint,
    org_id,
    org_id=org_id,
)
```

## Filtering org-wide responses

`inventory.get_networks(org_id)` gates which networks are fetched, but a bulk org-wide endpoint
returns rows for every network regardless. Resolve
`await self.inventory.get_allowed_network_ids(org_id)` and skip rows whose network id falls outside
it, or `NetworkFilter` leaks through the response path.

## Endpoint groups

Pick `floor_seconds` by the data's natural volatility: ~60s for real-time status, alerts and sensor
readings; ~300s for device metrics, performance data and client counts; ~900s or more for licensing,
org summaries and configuration. These are conventions, not enforced constants;
`core/scheduler.py::EndpointGroupName` is the list of declared groups and each coordinator's
`get_endpoint_groups()` carries its actual floors and priorities.

## Concurrency

`settings.api.concurrency_limit` bounds fan-out inside one collector.
`settings.collectors.max_concurrent_collectors` is the global ceiling on collector loops, but the
effective admission limit is
`min(max_concurrent_collectors, api.executor_workers // api.concurrency_limit)` with a floor of 1, so
shipped defaults admit two collectors. Raising `max_concurrent_collectors` alone changes nothing.

## Cardinality

Budgets are keyed per metric family, not per collector: `cardinality.max_series_per_family` (50000)
with `cardinality.action` defaulting to `warn`, which alarms and keeps emitting. Nothing removes a
live series unless the action is set to `drop`.

## Where a metric belongs

Device-specific metrics belong to the device sub-collector; common device metrics
(`meraki_device_up`) to `DeviceCollector`; network metrics to `NetworkHealthCollector`; org metrics
to `OrganizationCollector`.

In `network_health_collectors/` and `organization_collectors/` the gauge is created once in the
parent coordinator's `_initialize_metrics()` and a sub-collector sets it by attribute-name string
through `SubCollectorMixin._set_metric_value("_gauge_attr", labels, value)`. Device sub-collectors
differ, see `devices/AGENTS.md`.

## Deeper references

- `ERROR_HANDLING.md` - read before adding a fetcher: when `@with_error_handling` is enough, and the
  three recovery cases that justify a manual `try/except` inside it.
