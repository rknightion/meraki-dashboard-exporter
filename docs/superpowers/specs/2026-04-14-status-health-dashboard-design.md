# Status Health Dashboard Endpoint

## Summary

A `/status` endpoint that exposes exporter self-health as both a human-readable HTML page and a machine-readable JSON API. Aggregates internal state from existing managers into a single point-in-time snapshot.

## Motivation

The exporter already tracks rich health data internally -- collector success/failure rates, API call counts, rate limiter state, metric freshness, org backoff status -- but this data is only accessible through Prometheus metrics or scattered across internal objects. A dedicated status page makes it easy to eyeball exporter health in a browser without needing Grafana, and the JSON format lets scripts or external tooling consume the same data.

## Non-Goals

- **Not a replacement for Prometheus metrics.** This reads internal state, not the Prometheus registry.
- **Not a Kubernetes probe.** `/health` and `/ready` remain unchanged for liveness/readiness probes.
- **Not a live dashboard.** No WebSocket, no auto-refresh, no JavaScript.

## Architecture

### New Files

| File | Purpose |
|------|---------|
| `src/meraki_dashboard_exporter/services/status.py` | `StatusService` class and `StatusSnapshot` dataclass |
| `src/meraki_dashboard_exporter/templates/status.html` | HTML template for the browser view |

### Modified Files

| File | Change |
|------|--------|
| `src/meraki_dashboard_exporter/app.py` | Add `GET /status` route, instantiate `StatusService` |
| `src/meraki_dashboard_exporter/templates/index.html` | Add `/status` link to navigation |

### Dependencies

None. All data sources already exist in the codebase.

## Data Model

### StatusSnapshot

A point-in-time snapshot dataclass with four sections:

#### 1. Collectors

One entry per registered collector:

| Field | Type | Source |
|-------|------|--------|
| `name` | `str` | Collector class name |
| `tier` | `str` | FAST / MEDIUM / SLOW (from collector registry, not `collector_health`) |
| `total_runs` | `int` | `CollectorManager.collector_health` |
| `total_successes` | `int` | `CollectorManager.collector_health` |
| `total_failures` | `int` | `CollectorManager.collector_health` |
| `success_rate` | `float` | Computed: `total_successes / total_runs * 100` |
| `failure_streak` | `int` | `CollectorManager.collector_health` |
| `last_success_time` | `float \| None` | `CollectorManager.collector_health` (unix timestamp) |
| `last_success_ago` | `str` | Computed: human-readable relative time ("2m ago") |
| `is_running` | `bool` | `CollectorManager.is_collector_running()` |
| `staleness` | `str` | Computed: "ok" / "warning" / "stale" based on time since last success vs tier interval |

Staleness thresholds:
- **ok**: last success within 1x the tier's collection interval
- **warning**: last success within 2x the tier's collection interval
- **stale**: last success beyond 2x the tier's collection interval, or never succeeded

#### 2. API Health

| Field | Type | Source |
|-------|------|--------|
| `total_calls` | `int` | `AsyncMerakiClient._api_call_count` |
| `throttle_events` | `int` | `OrgRateLimiter` throttle counter |
| `per_org_rate_limits` | `list[dict]` | `OrgRateLimiter._tokens` (remaining tokens per org) |

#### 3. Data Freshness

| Field | Type | Source |
|-------|------|--------|
| `total_tracked_metrics` | `int` | `MetricExpirationManager.get_stats()` |
| `by_collector` | `dict[str, int]` | `MetricExpirationManager.get_stats()` |
| `ttl_multiplier` | `float` | `MetricExpirationManager.get_stats()` |

#### 4. System

| Field | Type | Source |
|-------|------|--------|
| `uptime` | `str` | `ExporterApp._format_uptime()` |
| `version` | `str` | `__version__` |
| `readiness` | `dict` | `CollectorManager.get_readiness_status()` |
| `org_health` | `list[dict]` | `OrgHealthTracker._orgs` (per-org backoff state) |
| `timestamp` | `str` | ISO 8601 timestamp of when the snapshot was taken |

### JSON Output

The `StatusSnapshot` serialized as a JSON object. Example structure:

```json
{
  "timestamp": "2026-04-14T12:00:00Z",
  "system": {
    "version": "1.2.3",
    "uptime": "3h 42m",
    "readiness": {
      "ready": true,
      "collectors": {"fast": true, "medium": true, "slow": true}
    },
    "org_health": [
      {
        "org_id": "123456",
        "org_name": "Acme Corp",
        "consecutive_failures": 0,
        "in_backoff": false
      }
    ]
  },
  "collectors": [
    {
      "name": "DeviceCollector",
      "tier": "FAST",
      "total_runs": 150,
      "total_successes": 148,
      "total_failures": 2,
      "success_rate": 98.7,
      "failure_streak": 0,
      "last_success_time": 1744632000.0,
      "last_success_ago": "30s ago",
      "is_running": false,
      "staleness": "ok"
    }
  ],
  "api_health": {
    "total_calls": 5432,
    "throttle_events": 3,
    "per_org_rate_limits": [
      {"org_id": "123456", "tokens_remaining": 8.5}
    ]
  },
  "data_freshness": {
    "total_tracked_metrics": 1247,
    "by_collector": {"DeviceCollector": 320, "MRCollector": 450},
    "ttl_multiplier": 2.0
  }
}
```

## Route Behavior

| Request | Response |
|---------|----------|
| `GET /status` | HTML page (200) |
| `GET /status?format=json` | JSON object (200) |

No authentication. Consistent with existing public endpoints (`/`, `/health`, `/cardinality`, `/clients`).

## HTML Template

Self-contained HTML with inline CSS. No JavaScript, no external dependencies.

### Style

Follows the existing `index.html` conventions:
- Same CSS custom properties (`--bg-color`, `--card-bg`, `--success-color`, etc.)
- Same system font stack, card layout, border-radius
- Same color palette for consistency

### Layout

1. **Header** -- "Exporter Status" title with version and uptime
2. **Readiness banner** -- green/yellow bar showing which tiers have completed their first collection
3. **Collectors table** -- one row per collector
   - Columns: Name, Tier, Runs, Success Rate, Failure Streak, Last Success, Staleness, Running
   - Row background color-coded: green (ok), yellow (warning), red (stale or failure streak >= 3)
4. **API Health card** -- total calls, throttle events, per-org token counts
5. **Data Freshness card** -- total tracked metrics with per-collector breakdown
6. **Organization Health section** -- only rendered if any orgs are in backoff; shows org name, failure count, backoff time remaining

### Navigation

A link to `/status` is added to the existing index page's navigation alongside `/metrics`, `/cardinality`, `/clients`.

## StatusService Class

```python
class StatusService:
    def __init__(
        self,
        collector_manager: CollectorManager,
        expiration_manager: MetricExpirationManager,
        client: AsyncMerakiClient,
        settings: Settings,
        start_time: float,
    ) -> None: ...

    def get_snapshot(self) -> StatusSnapshot: ...
```

- Instantiated once in `ExporterApp.__init__()` after the managers are created
- `get_snapshot()` is synchronous -- reads current state from managers, computes derived fields, returns a dataclass
- No caching -- each call reads fresh state (the data sources are all in-memory, so this is cheap)

## Testing

- Unit tests for `StatusService.get_snapshot()` with mocked managers
- Test staleness computation logic (ok/warning/stale thresholds)
- Test JSON serialization of `StatusSnapshot`
- Test the `/status` route returns HTML by default and JSON with `?format=json`
- Test that the HTML contains expected sections (collector table, API health, etc.)
