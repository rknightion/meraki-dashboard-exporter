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
- **Symptom:** `meraki_exporter_collector_errors_total{error_type="timeout"}` increasing
- **Fix:** Increase `MERAKI_EXPORTER_COLLECTORS__COLLECTOR_TIMEOUT`, reduce batch sizes, increase concurrency

### Cardinality Spikes
- **Symptom:** `meraki_exporter_cardinality_limit_reached` = 1
- **Fix:** Increase `MERAKI_EXPORTER_MONITORING__MAX_CARDINALITY_PER_COLLECTOR` or investigate which collector is generating excessive label combinations

### Org-Level Backoff
- **Symptom:** `meraki_exporter_org_collection_status` = 0 for specific orgs
- **Fix:** Check if org's API access is working, verify API key permissions
