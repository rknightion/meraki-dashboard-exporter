---
title: Extending Collectors
description: How to add new metric collectors
---

# Extending the Collector System

Collectors gather metrics from the Meraki API. New collectors live in `src/meraki_dashboard_exporter/collectors/`. Always consult the relevant `CLAUDE.md` in the target directory before making changes.

## Basic steps
1. Create a new module under `collectors/` and import it so the registry sees it.
2. Define a class inheriting from `MetricCollector` (or the relevant base) and decorate it with `@register_collector(UpdateTier.X)`.
3. Define metrics in `_initialize_metrics()` using `_create_gauge/_create_counter/_create_histogram/_create_info` and MetricName/LabelName enums.
4. Implement `_collect_impl()` with proper error handling (`with_error_handling`) and response validation (`validate_response_format` or Pydantic models).
5. Use shared services:
   - `self.inventory` for org/network/device lookups to reuse cache.
   - `ManagedTaskGroup` with `settings.api.concurrency_limit` for bounded parallelism.
   - `_set_metric()` to ensure metric expiration tracking is applied.
6. Add metric enums to `core/constants/metrics_constants.py` and tests under `tests/`.

```python
@register_collector(UpdateTier.MEDIUM)
class MyCollector(MetricCollector):
    def _initialize_metrics(self) -> None:
        self._example_metric = self._create_gauge(
            MyMetricName.EXAMPLE_METRIC,
            "Example metric description",
            labelnames=[LabelName.ORG_ID, LabelName.NETWORK_ID],
        )

    @with_error_handling("Collect example data", continue_on_error=True)
    async def _collect_impl(self) -> None:
        # Reuse cached inventory lookups
        organizations = await self.inventory.get_organizations()
        async with ManagedTaskGroup(max_concurrency=self.settings.api.concurrency_limit) as group:
            for org in organizations:
                await group.create_task(self._process_org(org.id))

    async def _process_org(self, org_id: str) -> None:
        data = await self.api.some.endpoint(org_id)
        for item in validate_response_format(data, expected_type=list, operation="example"):
            labels = {LabelName.ORG_ID.value: org_id, LabelName.NETWORK_ID.value: item["networkId"]}
            self._set_metric(self._example_metric, labels, float(item["value"]))
```

## Testing
Use the helpers under `tests/` to build unit tests. Run them with:
```bash
uv run pytest
```
