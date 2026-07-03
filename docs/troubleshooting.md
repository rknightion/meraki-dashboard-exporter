---
title: Troubleshooting
description: Symptom-driven checks and fixes for common Meraki Dashboard Exporter problems - auth errors, empty metrics, readiness, backoff, rate limits, cardinality, and webhooks.
tags:
  - troubleshooting
  - operations
---

# Troubleshooting

A symptom -> check -> fix decision tree for the most common problems operators hit in
production. Each check references a real endpoint, log line, or metric so you can confirm the
diagnosis before applying the fix. For the full endpoint list see [HTTP
Endpoints](reference/endpoints.md); for every config key see [Configuration](config.md).

Start here for a quick overall picture, before diving into a specific symptom below:

```bash
curl -s http://<host>:9099/health   # liveness: process is not wedged
curl -s http://<host>:9099/ready    # readiness: FAST + MEDIUM tiers have completed once
curl -s http://<host>:9099/status   # self-health dashboard: auth, backoff, staleness, rate limits
curl -s http://<host>:9099/config   # redacted effective configuration (#312)
```

## 401/403 errors (bad API key or org API access disabled)

**Symptom:** the exporter starts, but collectors fail immediately and no metrics ever populate,
or `/status` shows `authenticated: false`.

**Check:**

- `curl -s http://<host>:9099/status | jq '.api_health.authenticated'` - this reflects
  `MerakiClient.get_auth_ok()`, which is `true` after any HTTP 200 from the Meraki API, `false`
  after any HTTP 401, and `null`/unset if no auth-signalling response has been seen yet.
- Run an offline config check plus a live auth probe:
  ```bash
  uv run python -m meraki_dashboard_exporter --check --probe
  ```
  This calls `getOrganizations` once and prints `Auth probe: OK` or `Auth probe: FAILED`
  (non-zero exit on failure) without starting the scheduler.
- Errors surfaced from collectors are categorized by HTTP status: `401`/`403`/`400`/`405`/`406`
  all bucket to the same client-error category (see `core/error_handling.py`'s
  `categorize_error`), so a 403 (e.g. "organization API access is not enabled" for a given org)
  looks the same in logs as a bad key - check the log line's `error` field for the actual message
  and status code.

**Fix:**

- Confirm `MERAKI_EXPORTER_MERAKI__API_KEY` is set and correct (regenerate it in the Meraki
  Dashboard under **Organization > Settings > Dashboard API access** if unsure).
- Confirm the organization has API access **enabled** (same Dashboard settings page) - a valid key
  against an org with API access disabled returns 403 for that org specifically, while other orgs
  visible to the same key may still work.
- If you scope to a single org via `MERAKI_EXPORTER_MERAKI__ORG_ID`, confirm that ID is one the key
  can actually see (`--check --probe` will fail if not).

## NetworkFilter resolves to zero networks

**Symptom:** the exporter runs, but a network (or every network) you expect never shows up in
metrics.

**Check:**

- Log line, one per affected organization: `"Network filter resolved to zero networks for
  organization"` (with `org_id`, `org_name`, `total_networks_in_org`, and `configured_filter`
  fields) - emitted by `CollectorManager._validate_network_filter()` at startup.
- `curl -s http://<host>:9099/status | jq '.network_filter'` shows the effective filter state.

**Important nuance:** this only **fails startup** (raises and exits) if the filter resolves to
**zero networks across every configured organization** - a multi-org deployment where the filter
legitimately excludes all networks in one org but matches networks in another will log the ERROR
per-org and keep running, not crash. If you expected a hard failure and didn't get one, check
whether another org in scope still resolved networks.

**Fix:**

- Review the `MERAKI_EXPORTER_NETWORK_FILTER__*` settings (`include_names`/`exclude_names`,
  `include_ids`/`exclude_ids`, `include_tags`/`exclude_tags`) in [Configuration](config.md) - a
  typo'd network name glob or tag is the most common cause.
- The logged `total_networks_in_org` (the **unfiltered** count) vs. the resolved count tells you
  whether the org has any networks at all, or whether the filter is the problem.

## Empty `/metrics`

**Symptom:** `curl http://<host>:9099/metrics` returns 200 but with few or no `meraki_*` series.

**Check, in order:**

1. `/health` - if this returns 503, the liveness dead-man switch has tripped (no collector has
   succeeded within the configured staleness threshold); check logs for the `"Liveness dead-man
   switch tripped"` line and its `reason` field.
2. `/ready` - if this returns 503, the FAST and MEDIUM tiers have not completed a first cycle yet
   (see the readiness-gating section below) - this is expected for the first ~60-300s after
   startup, not necessarily a problem.
3. `/status` - check `collectors[].total_runs` and `collectors[].total_failures` per collector,
   and `api_health.authenticated`.
4. Confirm the scrape target is hitting `/metrics` (not `/` or `/status`) and that no reverse proxy
   is stripping the response body.

**Fix:** almost always one of - not enough time has passed since startup (wait for `/ready`), the
401/403 case above, or every organization is currently backed off (see below).

## Readiness gating: `/ready` only waits on FAST + MEDIUM

**Symptom:** `/ready` returns 200 well before SLOW-tier metrics (e.g. licensing, firmware) appear
in `/metrics`, or a Kubernetes rollout proceeds past the readiness gate while SLOW-tier data is
still empty.

**This is expected behaviour, not a bug.** Per `app.py`'s `/ready` handler:

> Returns 503 until both FAST and MEDIUM collection tiers have completed their first cycle. SLOW
> tier is excluded to avoid blocking Kubernetes readiness probes for up to 900s.

Update tiers are FAST=60s, MEDIUM=300s, SLOW=900s. If you need to confirm SLOW-tier data has
landed too, don't rely on `/ready` for that - instead poll `/status` and check the SLOW-tier
collectors' `total_runs > 0` and `last_success_time`, or just allow up to 900s after startup before
expecting SLOW-tier series in `/metrics`.

## Per-org backoff (repeated collection skips for one organization)

**Symptom:** one organization's metrics stop updating (or were never populated) while others in
the same exporter instance are fine.

**Check:**

- Log lines: `"Organization entering backoff"` (fields: `org_id`, `org_name`, `source`,
  `consecutive_failures`, `backoff_seconds`) and, on recovery, `"Organization recovered from
  backoff"`.
- Per-collector skip lines while an org is backed off: `"Skipping organization collection due to
  backoff"`, `"Skipping device collection for organization in backoff"`, `"Skipping network health
  collection for organization in backoff"`, `"Skipping client collection for organization in
  backoff"`, `"Skipping alert collection for organization in backoff"`, `"Skipping MT sensor alert
  collection for organization in backoff"`.
- `meraki_exporter_org_collection_status{org_id="..."}` - 1 when the last collection succeeded, 0
  when it failed or the org is currently in backoff.

**How it works (`core/org_health.py`'s `OrgHealthTracker`):** backoff is tracked per failure
*source* (organization, device, network-health collectors each report independently under their
own bucket), and the *effective* consecutive-failure count driving backoff is the **max across all
sources** - a persistent failure in any one domain is enough to back the org off, even if the
others are healthy. Backoff duration grows exponentially (`base_backoff * 2^(failures -
threshold)`, capped at `max_backoff`) and clears automatically once **every** source's failure
count drops back under the threshold.

**Fix:** the underlying cause is almost always a real per-org API failure (auth, org-specific 403,
persistent 5xx from Meraki) - fix that and the org recovers automatically on its next successful
collection. There is no manual "clear backoff" endpoint by design; if you need to force an
immediate retry, use `POST /api/collectors/trigger` to trigger a collector run on-demand.

## 429 storms (rate limiting)

**Symptom:** logs show repeated rate-limit waits or throttle events; collection slows down or some
tiers stop completing within their interval.

**Check:**

- `meraki_exporter_api_rate_limiter_throttled_total{org_id, endpoint}` - count of client-side
  rate-limiter waits (the exporter proactively throttling itself before hitting Meraki's limit).
- `meraki_exporter_api_rate_limiter_wait_seconds{org_id, endpoint}` - histogram of time spent
  waiting.
- `meraki_exporter_scheduler_throttle_backoffs_total` - counts AIMD multiplicative-decrease events:
  each increment is one real 429/`Retry-After` response from Meraki that halved the exporter's
  effective client-side rate budget (at most once per 30s cooldown window), separate from the
  proactive client-side throttle above.
- `meraki_exporter_api_rate_limiter_tokens{org_id}` - estimated remaining tokens in the client-side
  bucket; a value pinned near zero indicates sustained pressure.
- `curl -s http://<host>:9099/status | jq '.api_health'` surfaces `throttle_events` and
  `per_org_rate_limits` (tokens remaining per org) in one place.

**Fix:** the AIMD controller already self-adjusts the effective rate down on real 429s and
recovers over time, so transient storms need no operator action. For a sustained problem, reduce
concurrency (`MERAKI_EXPORTER_API__CONCURRENCY_LIMIT*` family) or the number of organizations
polled per instance - see the [Scaling Guide](scaling-guide.md) for the API-budget sizing formula
and shard-by-org recipes.

## Cardinality shedding

**Symptom:** a metric family you expect stops growing new label combinations, or logs show a
cardinality warning/error.

**Check:**

- `GET /cardinality` (HTML report) or `GET /api/metrics/cardinality` (JSON) - both populate only
  **after the first full collection cycle** completes.
- Log lines: `"High cardinality metrics detected"` (warning, with a `warning_metrics` list) or
  `"Critical cardinality threshold exceeded"` (error, with a `critical_metrics` list), emitted by
  the periodic `CardinalityMonitor` sweep.

**Fix:** tune the `MERAKI_EXPORTER_CARDINALITY__*` settings in [Configuration](config.md):
`max_series_per_family` (default 50000) is the per-metric-family cap; `action` is `warn` (log only,
keep emitting - the default) or `drop` (stop emitting new series for that family once the cap is
exceeded). `disabled_metrics` (comma-separated family names) turns a family off entirely if you
don't need it. Note that this project's cardinality model bounds numeric series to fleet-shaped
labels by construction (org/network/device/SSID/port/band) - a family blowing through the cap
usually means either an unexpectedly large fleet or a mis-set `NetworkFilter` pulling in far more
networks/devices than intended (see the NetworkFilter section above).

## Webhook secret misconfiguration

**Symptom:** either the exporter refuses to start with a webhook-related error, or `POST
/api/webhooks/meraki` returns 401/404 for every delivery.

**Check / fix by outcome:**

- **Exporter won't start**, error mentions `require_secret=false`: this is
  `enforce_webhook_security()` refusing to boot with an unauthenticated webhook receiver. Either
  set `MERAKI_EXPORTER_WEBHOOKS__REQUIRE_SECRET=true` (recommended - also set
  `MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET` to match the secret configured in the Meraki Dashboard
  webhook receiver), or explicitly accept the risk with
  `MERAKI_EXPORTER_WEBHOOKS__ALLOW_INSECURE=true`.
- **`404` on the webhook endpoint**: the receiver is disabled - set
  `MERAKI_EXPORTER_WEBHOOKS__ENABLED=true`.
- **`401` on every delivery**: secret mismatch or missing. `record_validation_failure` labels the
  `meraki_webhook_validation_failures_total{validation_error}` counter with `secret_not_configured`
  (receiver has no `shared_secret` set but requires one) or `secret_mismatch` (the payload's
  `sharedSecret` doesn't match). Confirm `MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET` matches exactly
  what's configured in the Dashboard's webhook receiver setup, byte for byte.
- **`413` on delivery**: payload exceeded `MERAKI_EXPORTER_WEBHOOKS__MAX_PAYLOAD_SIZE` (default
  1048576 bytes / 1 MiB) - raise it if you have unusually large webhook payloads.
- General receiver health: `meraki_webhook_events_received_total{org_id, alert_type}`,
  `meraki_webhook_events_processed_total`, `meraki_webhook_events_failed_total{error_type}`, and
  the `/status` endpoint's webhook section (present only when the receiver is enabled).

## Log aggregation and querying

The exporter's structured logs default to `logfmt`
(`MERAKI_EXPORTER_LOGGING__LOG_FORMAT=logfmt`); set it to `json` for JSON-native pipelines. See
[Log Aggregation](deployment-operations.md#log-aggregation) for the Grafana Alloy shipping config
and worked LogQL examples for both formats.
