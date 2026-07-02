# Scaling Guide

Recommendations for deploying the Meraki Dashboard Exporter at different scales.

## Small Deployment (< 100 devices)

**Profile:** Single org, 1-5 networks, basic monitoring

| Setting | Value |
|---------|-------|
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT` | 3 |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_FAST` | 3 |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_MEDIUM` | 2 |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_SLOW` | 1 |
| `MERAKI_EXPORTER_MONITORING__MAX_CARDINALITY_PER_COLLECTOR` | 5000 |
| Resources | cpu: 50m, memory: 128Mi |
| Scrape interval | 60s |

**Notes:** Default settings work well. No special tuning needed.

## Medium Deployment (100-1,000 devices)

**Profile:** 1-3 orgs, 10-50 networks, production monitoring

| Setting | Value |
|---------|-------|
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT` | 5 |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_FAST` | 5 |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_MEDIUM` | 3 |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_SLOW` | 2 |
| `MERAKI_EXPORTER_API__RATE_LIMIT_REQUESTS_PER_SECOND` | 8 |
| `MERAKI_EXPORTER_MONITORING__MAX_CARDINALITY_PER_COLLECTOR` | 10000 |
| Resources | cpu: 100m, memory: 256Mi |
| Scrape interval | 60s |

**Notes:**
- Enable inventory cache warming (automatic on startup)
- Monitor `meraki_exporter_collection_utilization_ratio` - if >0.5, increase concurrency
- Watch `meraki_exporter_api_rate_limiter_throttled_total` for rate limit pressure

## Large Deployment (1,000-5,000 devices)

**Profile:** Multiple orgs, 50-200 networks, production SLAs

| Setting | Value |
|---------|-------|
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT` | 5 |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_FAST` | 7 |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_MEDIUM` | 5 |
| `MERAKI_EXPORTER_API__CONCURRENCY_LIMIT_SLOW` | 3 |
| `MERAKI_EXPORTER_API__RATE_LIMIT_REQUESTS_PER_SECOND` | 10 |
| `MERAKI_EXPORTER_API__BATCH_SIZE` | 20 |
| `MERAKI_EXPORTER_MONITORING__MAX_CARDINALITY_PER_COLLECTOR` | 25000 |
| `MERAKI_EXPORTER_MONITORING__METRIC_TTL_MULTIPLIER` | 3.0 |
| Resources | cpu: 250m, memory: 512Mi |
| Scrape interval | 60s |

**Notes:**
- Monitor `meraki_exporter_collection_utilization_ratio` closely - if >0.8 for any collector, that collector can't keep up with its interval
- Enable OpenTelemetry tracing at 1% sampling to identify slow API calls
- Use `meraki_exporter_cardinality_limit_reached` to detect metric shedding
- Monitor `meraki_exporter_org_collection_status` for per-org health
- Consider disabling non-critical collectors (clients, alerts) if rate limited
- The shared inventory cache feeds all collectors with network/device lookups,
  so filtering at the inventory layer (see Network Filter below) immediately
  reduces downstream API call volume across every tier.

## Reducing API Call Volume with the Network Filter

For large or multi-tenant organisations where you only care about a subset of
networks, the **Network Filter** is the most effective single lever for cutting
API usage. It applies at the inventory layer, so excluded networks (and their
devices) are skipped by every collector.

Configure via include/exclude rules on name globs, IDs, or tags:

```bash
MERAKI_EXPORTER_NETWORK_FILTER__INCLUDE_NAMES=prod-*,staging-*
MERAKI_EXPORTER_NETWORK_FILTER__INCLUDE_TAGS=production,critical
MERAKI_EXPORTER_NETWORK_FILTER__EXCLUDE_NAMES=*-test,*-sandbox
```

Resolution semantics: if any `INCLUDE_*` is set, networks must match at least
one include rule; any `EXCLUDE_*` match drops the network (excludes win). The
filter is inactive by default. If a configured filter resolves to zero
networks across all orgs at startup, the exporter exits with an error so
typos fail loudly.

Live filter state is observable via `meraki_network_filter_match`,
`meraki_network_filter_resolved`, and `meraki_network_filter_total`. See
`.env.example` for the full set of fields.

## Key Metrics to Monitor

| Metric | What It Tells You |
|--------|-------------------|
| `meraki_exporter_collection_utilization_ratio` | % of interval consumed by collection |
| `meraki_exporter_api_rate_limiter_throttled_total` | Rate limit pressure |
| `meraki_exporter_cardinality_limit_reached` | Metric shedding active |
| `meraki_exporter_org_collection_status` | Per-org collection health |
| `meraki_exporter_collector_duration_seconds` | How long each collection takes |

## Troubleshooting

### Rate Limit Exhaustion
- **Symptom:** `meraki_exporter_api_rate_limiter_throttled_total` increasing rapidly
- **Fix:** Reduce `MERAKI_EXPORTER_API__RATE_LIMIT_REQUESTS_PER_SECOND`, increase intervals, or disable non-critical collectors

### Collector Timeouts
- **Symptom:** `meraki_exporter_collection_errors_total{error_type="TimeoutError"}` increasing — this
  is the run-level collector budget expiring (distinct from the similarly-named
  `meraki_exporter_collector_errors_total{error_type="timeout"}`, which fires for individual
  API-call timeouts, not the overall collector run)
- **Fix:** Increase `MERAKI_EXPORTER_COLLECTORS__COLLECTOR_TIMEOUT`, reduce batch sizes, increase concurrency

### Cardinality Spikes
- **Symptom:** `meraki_exporter_cardinality_limit_reached` = 1
- **Fix:** Increase `MERAKI_EXPORTER_MONITORING__MAX_CARDINALITY_PER_COLLECTOR` or investigate which collector is generating excessive label combinations

### Org-Level Backoff
- **Symptom:** `meraki_exporter_org_collection_status` = 0 for specific orgs
- **Fix:** Check if org's API access is working, verify API key permissions
