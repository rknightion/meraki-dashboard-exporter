---
id: MDE-0068
title: Expose client IP on meraki_client_info and evict superseded info series
status: Done
assignee: []
created_date: '2026-09-12 09:55'
updated_date: '2026-09-12 10:17'
labels:
  - 'area:clients'
  - 'area:core'
  - 'area:privacy'
  - 'priority:medium'
dependencies: []
ordinal: 68000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub issue #764 (external reporter) asks for the client IP as an explicit label on `meraki_client_info` so a SOC/SIEM investigation can answer "which client held 192.0.2.10 at 14:00 yesterday" from Prometheus retention. The reporter also pushed a fork branch implementing the naive version; it is not a PR and is incomplete against this repo's gate.

## Mechanism 1 - the label is cheap, the churn is not

`ClientData.ip` / `ip6` / `ip6Local` already exist (`core/domain_models.py:1049-1051`) and are already fetched, and `LabelName.IP` already exists (`core/metrics.py:91`). Adding the label is additive and explicitly permitted by `docs/stability.md:107`.

The cost is series churn. `meraki_client_info` series expire on TTL = group interval x `monitoring.metric_ttl_multiplier` (2.0), and `CLIENTS_LIST` has `floor_seconds=300`, so a superseded label set stays exposed for up to ~10 minutes. During that window a client has TWO live info series and the documented join `<numeric> * on(client_id) group_left(mac, hostname) meraki_client_info` fails the whole query with "many-to-one matching must be explicit". That latent bug exists today for hostname/description/SSID churn; IP churn makes it routine rather than rare.

## Mechanism 2 - eviction, not a query workaround

`MetricExpirationManager._remove_series` (`core/metric_expiration.py:192`) already removes the real Prometheus series via `Gauge.remove` plus its bookkeeping, but it is reachable only from the TTL sweep and the cardinality-shed path. Giving it a public supersede entry point, and memoising the last emitted info label set per client in `ClientsCollector`, means the old series disappears in the same emit that creates the new one. A scrape then never sees two, panels always show the current IP, and no dashboard or doc workaround is needed. It also retroactively fixes hostname/description/SSID churn.

## Mechanism 3 - IPv6 must be opt-in, IPv4 must not

SLAAC privacy extensions (RFC 8981) rotate the temporary global address roughly daily by default on Windows, macOS, iOS and Android, so populating `ip6` mints about one new series per client per day by construction. At the `max_clients_total` cap of 25000 that is ~750k series/month of index growth in the consumer's TSDB. IPv4 in an enterprise estate with sticky leases is far lower. So `ip` defaults on with an escape hatch, `ip6` defaults off. `ip6Local` is link-local and carries no correlation value; it is deliberately not exposed.

## Constraints

- Both label KEYS stay in the literal `labelnames=[...]` list. `scripts/generate_metrics_docs.py` AST-parses that list literal, so a conditionally built list breaks doc generation. The config flags gate the VALUE, not the key.
- Do not run either address through `_sanitize_label_value` (`collectors/clients.py:771`): it replaces every character outside [a-zA-Z0-9_-] with a hyphen, which would render 192.0.2.10 as 192-0-2-10 and mangle every IPv6 colon.
- `tests/unit/golden/metrics/clients.txt:13-15` pins both the HELP string and the label key set and must be regenerated (`UPDATE_METRICS_GOLDENS=1`).
- `docs/privacy.md:42-47` enumerates the `meraki_client_info` label set verbatim and separately names IP address as potential GDPR personal data; it is wrong the moment this lands.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 meraki_client_info carries ip and ip6 label keys unconditionally; ip is populated by default, ip6 only when its opt-in setting is true, and neither value passes through _sanitize_label_value
- [x] #2 A client whose info label set changes has its superseded series removed from the registry in the same emit, so only one meraki_client_info series per client is ever exposed; covered by a unit test that asserts the old label set is gone
- [x] #3 clients.ip_label_enabled (default true) and clients.ip6_label_enabled (default false) exist, are documented, and appear in the generated config/env/helm artefacts
- [x] #4 docs/privacy.md, docs/stability.md and the documented group_left join example reflect the new label set and tolerate a transient duplicate on older exporters
- [x] #5 just check and just gen are green with no drift, and the golden metrics snapshot is regenerated
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Two corrections to this task's own description, found in review.

**The stale-series window is a floor, not a cap.** The description says a superseded label set stays exposed for 'up to ~10 minutes'. `floor_seconds=300` on `CLIENTS_LIST` is the FLOOR the solver may not go below, not the interval it uses, so with `metric_ttl_multiplier` 2.0 the window is AT LEAST ~10 minutes and grows whenever the solver stretches the group under budget pressure. That makes the join-breakage worse than stated, not better.

**The one-series guarantee is scoped to this exporter.** 'exactly one live info series per client' holds for a single instance emitting through `_expire_superseded_client_info`. It does not hold for a consumer scraping an older exporter, nor for a recording rule or federation whose lookback spans a label change. `docs/stability.md` carries that caveat and the migration-safe query (`topk(1, meraki_client_info) by (client_id)`, not `max by (...)` - aggregating by the labels you pull across still returns two series when one of THOSE labels is what changed).

## What landed beyond the plan

`ClientsCollector._last_info_labels` is reconciled at the end of `_update_metrics` against the union of this pass's clients and `ClientStore.get_network_clients(network_id)`, and departed networks are dropped at cycle end. Without it the memo grows one entry per client ID ever seen on a churny guest network. Reconciling against the store rather than only this pass is deliberate: the store already applies the caps and its own complete-snapshot reconciliation, so a client the emission cap truncated out of this pass keeps its memo and still gets its predecessor evicted when it returns.

`_ip_label_value` takes a required `version` and drops a wrong-family address either way, plus any link-local IPv6. Without the family check a `ip6` field carrying a `fe80::` address would make the privacy doc's promise that the link-local `ip6Local` is never exposed false. An IPv4 link-local (169.254/16) is deliberately kept - it is real evidence of a client that failed DHCP.

Pre-existing, unrelated: `ruff format --check` covers Python code blocks in markdown and `src/meraki_dashboard_exporter/api/AGENTS.md` was already drifted on main, so `just check` was red before this change. The one-line reformat is included here.
<!-- SECTION:NOTES:END -->
