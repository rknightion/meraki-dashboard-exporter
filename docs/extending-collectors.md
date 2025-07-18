---
title: Extending Collectors
description: How to add new metric collectors
---

# Extending the Collector System

Collectors gather metrics from the Meraki API. New collectors live in `src/meraki_dashboard_exporter/collectors/`.

## Basic steps
1. Create a new module under `collectors/`.
2. Define a class inheriting from `MetricCollector` and decorate it with `@register_collector(UpdateTier.X)`.
3. Implement `_initialize_metrics()` to create Prometheus metrics.
4. Implement `_collect_impl()` with your collection logic.
5. Add metric names to `core/constants/metrics_constants.py`.

```python
@register_collector(UpdateTier.MEDIUM)
class MyCollector(MetricCollector):
    def _initialize_metrics(self) -> None:
        self._my_metric = self._create_gauge(MetricName.MY_METRIC, "description")

    async def _collect_impl(self) -> None:
        data = await self.api.some.endpoint()
        self._my_metric.set(len(data))
```

## Testing
Use the helpers under `tests/` to build unit tests. Run them with:
```bash
uv run pytest
```

See [CLAUDE.md](../CLAUDE.md) for development conventions.
