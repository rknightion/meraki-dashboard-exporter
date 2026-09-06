# Core infrastructure

- Build label dicts through `create_labels()` (`metrics.py`): it validates every key against
  `LabelName` and coalesces a `None` value to `""` instead of dropping the key. A dropped key makes
  `Gauge.labels()` raise for a missing labelname and silently loses the series.
- Declare metrics with `parent._create_gauge(<MetricName enum>, ..., labelnames=[LabelName.X.value,
  ...])` in the collector's `_initialize_metrics()`.
- Metric prefixes are two families: `meraki_*` for Meraki device and network data,
  `meraki_exporter_*` for the exporter's own instrumentation (`CollectorMetricName`).
- `ConfigMetricName` is deliberately an empty enum. Configuration-change metrics live under
  `OrgMetricName`; it does not need populating.
- `@register_collector` takes no arguments. There is no tier argument to pass - cadence comes from
  the endpoint groups the collector declares in `get_endpoint_groups()`.
- Two symbols are not in the module their name suggests: `batch_with_concurrency_limit()` is in
  `error_handling.py`, not `async_utils.py`, and `CollectorProtocol` is in `collector.py`, not
  `type_definitions.py`.
- `OrgRateLimiter` also runs AIMD on top of the token bucket: a real 429 or `Retry-After` halves the
  effective budget, floored at 0.5 rps and at most one halving per 30s cooldown, and
  `effective_rate_per_second()` feeds straight into the scheduler's next solve. A throttled org's
  cadence therefore changes with no config change.
- Cardinality endpoints are top-level routes, not nested under `/status`:
  `setup_cardinality_endpoint(app, monitor)` registers `/cardinality`, `/cardinality/all-metrics`,
  `/cardinality/all-labels`, `/cardinality/export/json`, `/cardinality/label-values/{metric_name}`
  and `/api/metrics/cardinality`.
- `constants/config_constants.py` (`APIConfig`, `RegionalURLs`, `MerakiAPIConfig`) is legacy: its
  `MERAKI_API_BASE_URL*` constants back the regional-origin allowlist and nothing else. Runtime
  config comes from `Settings` / `APISettings`.
- A new enum member goes in the matching domain file under `constants/` and gets re-exported from
  `constants/__init__.py`'s `__all__`. Do not add another top-level constants module.

## Deeper references

- `docs/observability/scheduler.md` - read before changing how the solver derives intervals or how a
  collector declares its endpoint groups.
