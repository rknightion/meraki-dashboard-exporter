---
title: Scaling Guide
description: How to size a single-org exporter instance against the Meraki 10 req/s org API budget, the quantitative calls-per-cycle formula, the knobs that cut demand, and how to shard by organization for multi-org and HA deployments.
tags:
  - scaling
  - deployment
  - rate-limit
  - troubleshooting
  - kubernetes
---

# Scaling Guide

This page gives you a **quantitative way to size the exporter** against the Meraki API rate
limit, and the **shard-by-org / HA recipes** for running more than one organization or surviving
pod loss.

If you only read one thing: **each exporter instance polls exactly one Meraki organization
(1 poller = 1 org, from 1.0 — see the [single-org contract](upgrading.md#single-org-deployment-contract-breaking))**.
Meraki applies both a **10 req/s per-organization** budget and a **100 req/s per-source-IP** budget.
Scaling is therefore a question of keeping one instance's call demand under its org budget *and*
keeping all shards sharing an egress IP under the IP budget — you cannot add exporter replicas to
go faster for the same org.

## The org API budget envelope

Meraki enforces **10 requests/second per organization** (v1 API; the exporter calls no
special-limited `liveTools` endpoints), shared by every application using that organization. It
also enforces **100 requests/second per source IP**, shared by every client that leaves through
that egress address. Every collector's API calls for an org are metered through
a single shared client-side token bucket, sized as:

$$
\text{budget}_{\text{eff}} = 10 \;\text{req/s} \times \texttt{rate\_limit\_shared\_fraction}
$$

`rate_limit_shared_fraction` defaults to **0.8**, so the exporter paces itself to **~8 req/s** and
leaves ~20% headroom for other users of the same org budget. Set it to `1.0` to claim the whole
budget, or lower to leave more room for other tools.

!!! warning "`rate_limit_shared_fraction` and `rate_limit_requests_per_second` do not reduce demand"
    These two settings control the **pace** at which the exporter is *allowed* to issue calls —
    they smooth bursts and share the budget with other consumers. They do **not** reduce the number
    of calls a collection cycle needs. If a cycle demands more calls than the budget can drain in
    one interval, lowering the fraction makes throttling **worse**, not better. To reduce demand you
    must cut work (fewer networks/devices, disabled collectors, longer intervals) — see
    [Cutting API demand](#cutting-api-demand).

## The API-budget sizing formula

Model your org by these counts (the exporter derives them from the inventory after the
[Network Filter](#network-filter) is applied):

| Symbol | Meaning |
|---|---|
| $W$ | wireless (MR) networks |
| $S_n$ | sensor (MT) networks |
| $\text{MR}$ | access points |
| $\text{MS}$ | switches |
| $\text{MX}_\text{phys}$ | physical security appliances |
| $\text{MV}$ | cameras |
| $D$ | total devices |

There is no fixed FAST/MEDIUM/SLOW tier system — an adaptive, budget-aware scheduler
(`core/scheduler.py`, see [Scheduler Architecture](observability/scheduler.md)) assigns every
API fetch to an **endpoint group** with its own volatility floor, and automatically **stretches**
lower-priority groups' intervals when combined demand would exceed the budget. The math below
still matters, though: it estimates the **unstretched, floor-level demand** — i.e. what the
exporter would ask for if every group ran flat-out at its natural floor. That's the number the
solver starts from before it stretches anything, and it's also the number that determines
whether a *single* collector's own run can finish inside its `collector_timeout` (240 s
default) — the solver can lengthen a group's *polling interval*, but it cannot make one
already-in-flight collection cycle's page-fetch loop finish faster. Almost all of this
unstretched demand sits in a handful of endpoint groups that would historically have been
called "MEDIUM" (≈300 s floor). The dominant, operator-actionable terms per **300 s baseline
cycle** are:

$$
\text{calls}_{\text{baseline}} \approx
\underbrace{C_{\mathrm{NH}}}_{\text{network health; current group-cost sum}}
+ \underbrace{W}_{\text{MR conn-stats}}
+ \underbrace{\lceil D/10 \rceil}_{\text{org memory pages}}
+ \underbrace{\lceil \text{MS}/20 \rceil}_{\text{MS port pages}}
+ \underbrace{\lceil \text{MR}/20 \rceil}_{\text{MR CPU batches}}
+ \text{MX}_\text{phys}
+ \text{MV}
+ \underbrace{\sim 28}_{\text{org + device bulk}}
$$

<!-- BEGIN GENERATED NETWORK HEALTH CAPACITY -->
### Network-health capacity (generated from endpoint groups)

These figures are derived from `NetworkHealthCollector.endpoint_groups`. The steady-state number weights each group by `300 / floor_seconds`; it is not the cost of one simultaneous due sweep.

| Shape | Steady-state equivalent (calls/300 s) | One all-groups due sweep |
|---|---:|---:|
| HOMELAB (`W=1`, `AP=1,000`) | **4.58** | 10 |
| `W=400`, `AP=4,000` | **1,041.3** | 3,208 |

A due sweep is larger because it includes every windowed group at once; use the steady-state equivalent for API-budget planning and the due-sweep column when judging a single collection run against its timeout.
<!-- END GENERATED NETWORK HEALTH CAPACITY -->

$$
\text{demand (req/s)} \approx \frac{\text{calls}_{\text{baseline}}}{300}
\qquad\text{vs}\qquad
\text{budget}_{\text{eff}} = 10 \times \texttt{shared\_fraction}
$$

If **demand > budget**, the scheduler stretches only priority 3/4 groups (up to
`scheduler.max_stretch_factor`/`max_interval_seconds`); priority 1/2 availability and sensor
groups keep their floors. If the solved plan remains over budget, it defers lower-priority groups
and exposes `meraki_exporter_scheduler_over_budget` plus the shed group labels. Set
`MERAKI_EXPORTER_COLLECTORS__PROFILE` explicitly to `availability`, `standard`, or `full` above
the computed full-plan threshold; the threshold is calculated from the actual implicit plan and
inventory shape, never a raw network count. Separately, if network-health's *own single run* needs more calls than the budget can drain
inside 240 s, that collector's run will not finish before `collector_timeout` regardless of how
the scheduler paces the *next* run — see the LARGE example below.

### Worked example — SMALL (≈100 devices, 10 networks)

$W=6$, $D=100$. Network health's 300-second equivalent is $2 + 6 + 6 + 6/6 + 6/12 + 12/12 +
6/12 + 6/12 = 17.5$ calls; MR conn-stats $6$; pagination is trivial ($\lceil100/10\rceil=10$
memory pages); org+device bulk $\sim28$ → **~62 calls/300 s equivalent**.

$$
\frac{62}{300} \approx \mathbf{0.21\ req/s}
$$

That is **~2% of the 10 req/s budget** (~3% of the 8 req/s default ceiling). Comfortable — default
settings need no tuning, registry holds ~20–50k series, RSS < 256 Mi.

### Worked example — LARGE (≈5,000 devices, 500 networks)

A university-shaped org: $W=400$ wireless nets, 4,000 MR, 700 MS, 150 MX, 100 MV, 50 MT.

| Load source | Calls/cycle | req/s |
|---|---:|---:|
| Network health (current endpoint groups) | 1,041.3 / 300 s equivalent | **3.47** |
| Device (MR conn-stats 400 + 500 memory pages + 350 MS packet + 200 CPU batches + 167 MV + 150 MX-perf + ~20 bulk) | ~2,000 | **~6.7** |
| Organization + Alerts + Config + sensor readings | ~120 | ~0.4 |
| **Total unstretched demand** | | **~10.6 req/s** |

**~10.6 req/s is still above the 10 req/s org budget** (and 133% of the 8 req/s default ceiling).
The adaptive scheduler will stretch lower-priority groups here (network health is priority 3).
The largest due sweep is not the 1,041.3-call equivalent: it is the per-network 3,600-second groups
together, so capacity planning must distinguish that sweep from steady-state demand. More
CPU/memory does not increase the API budget; see #701 for the remaining large-org demand limit.

### Practical single-org envelope today

With current defaults, and assuming the exporter is granted essentially the whole org budget, one
instance runs cleanly up to roughly:

> **≤ 150–200 wireless networks and ≤ 1,500–2,000 devices per organization.**

Past that you must [cut demand](#cutting-api-demand) (filter networks, raise intervals, disable
collectors) — sharding does **not** help a single oversized org, because the 10 req/s budget is
per-org, not per-instance (see [Scaling out & HA](#scaling-out-ha)).

## Cutting API demand

Ordered by leverage. These are the only levers that actually reduce the calls a cycle needs.

1. **Network Filter — the single biggest lever.** Excluding a wireless network removes the
   applicable per-network network-health calls and its MR conn-stats work at their respective
   endpoint-group floors, at the inventory layer, for all collectors at once. See
   [Network Filter](#network-filter).
2. **Disable collectors you don't need** via
   `MERAKI_EXPORTER_COLLECTORS__DISABLE_COLLECTORS` (JSON array or CSV). Disabling
   `mtsensor` removes the sensor-reading endpoint group entirely; disabling `network_health`
   removes the network-health endpoint groups (at the cost of RF/connection-quality metrics).
3. **Keep the clients collector OFF** (default). It is the worst per-client fan-out; it is disabled
   by default (`MERAKI_EXPORTER_CLIENTS__ENABLED=false`) and per-client signal quality is a further
   opt-in (`MERAKI_EXPORTER_CLIENTS__SIGNAL_QUALITY_ENABLED=false`). Leave both off at scale.
4. **Choose a collection profile, then use the scheduler or pin specific groups yourself.** In
   `adaptive` mode, `availability` keeps only priority-1 groups, `standard` includes priorities
   1–3, and `full` includes everything. Above the solved-plan threshold, set
   `MERAKI_EXPORTER_COLLECTORS__PROFILE` explicitly. The solver lengthens only lower-priority
   groups; if they cannot make the plan fit, it defers them rather than stretching priority 1/2.
   To force a *specific* endpoint group to a longer interval regardless of budget pressure (e.g.
   to permanently deprioritize a noisy group), pin it via
   `MERAKI_EXPORTER_SCHEDULER__GROUP_INTERVAL_OVERRIDES='{"nh_connection_stats": 900}'` (JSON
   object of group name → seconds; pinned groups are excluded from automatic stretching). See
   [Scheduler Architecture](observability/scheduler.md) for the full group name list and the
   solver's stretch order.
5. **Stretch the per-endpoint interval gates.** A handful of expensive per-switch / per-client
   fetches are also exposed as their own dedicated settings (`setting_pin`s on their endpoint
   group) and default to **600 s** — raise them to spread the fan-out further:
   `MERAKI_EXPORTER_API__MS_PORT_USAGE_INTERVAL`, `MERAKI_EXPORTER_API__MS_PACKET_STATS_INTERVAL`,
   `MERAKI_EXPORTER_API__CLIENT_APP_USAGE_INTERVAL`,
   `MERAKI_EXPORTER_API__CLIENT_SIGNAL_QUALITY_INTERVAL`.
6. **Then, only for pacing/headroom**, tune `MERAKI_EXPORTER_API__RATE_LIMIT_SHARED_FRACTION`
   (share the org budget with other tools) and `MERAKI_EXPORTER_API__RATE_LIMIT_REQUESTS_PER_SECOND`
   (default `10`; the client-side pace cap). These smooth calls; they do not reduce them.
7. **Bound how many collectors can be mid-run at once.** Independent of per-group intervals,
   `MERAKI_EXPORTER_COLLECTORS__MAX_CONCURRENT_COLLECTORS` (default `5`) caps how many
   collectors' group-clocked loops may be executing a run concurrently — lowering it smooths
   out simultaneous bursts of API calls at the cost of some collectors waiting longer for their
   turn; it does not change any single group's cadence.

!!! note "Config key names matter"
    Settings are `MERAKI_EXPORTER_<SECTION>__<KEY>` (double underscore, case-insensitive). The rate
    cap is `MERAKI_EXPORTER_API__RATE_LIMIT_REQUESTS_PER_SECOND` — there is **no**
    `..._RATE_LIMIT_RPS` alias, so an env var by that name is silently ignored and has no effect.

## Network Filter

For large or multi-tenant orgs where you only care about a subset of networks, the Network Filter
is the most effective single cut. It applies at the inventory layer, so excluded networks (and
their devices) are skipped by **every** collector and endpoint group.

```bash
MERAKI_EXPORTER_NETWORK_FILTER__INCLUDE_NAMES=prod-*,staging-*
MERAKI_EXPORTER_NETWORK_FILTER__INCLUDE_TAGS=production,critical
MERAKI_EXPORTER_NETWORK_FILTER__EXCLUDE_NAMES=*-test,*-sandbox
```

Resolution semantics: if any `INCLUDE_*` is set, a network must match at least one include rule;
any `EXCLUDE_*` match drops the network (excludes win). The filter is inactive by default. If a
configured filter resolves to **zero** networks at startup, the exporter exits with an error so
typos fail loudly. This happens only after the API successfully verifies that every configured
organization has an empty filtered result; a transient API failure (including HTTP 503) is logged
and the exporter starts its collection loops, which retry normally. Live state is observable via `meraki_network_filter_match`,
`meraki_network_filter_resolved`, and `meraki_network_filter_networks`. See `.env.example` for the
full field set.

## Resource sizing (memory & CPU)

Memory is the binding resource and scales with **Prometheus series cardinality**, which scales with
device/network count — not a fixed value. The old "512 Mi is enough" advice is wrong at scale and
will OOM-kill the pod. Rough single-org tiers (clients collector **off**), matching the Helm
chart's `values.yaml` sizing comments:

| Scale | Devices / networks | Requests | Limits | Notes |
|---|---|---|---|---|
| **Small** | ~100 / ~10 | 100m / 256Mi | 500m / 512Mi | registry ~20–50k series, RSS < 256 Mi; ~0.43 req/s |
| **Medium** | ~1,000 / ~50 | 250m / 512Mi | 1 / 1Gi | comfortably within budget |
| **Large** | ~5,000 / ~500 | 500m / 1.5Gi | 2 / 3Gi+ | registry 0.6–1.1M series; **also exceeds the org API budget** — needs NetworkFilter + interval tuning regardless of pod size |

Set the memory **limit from observed RSS** (`process_resident_memory_bytes` / container memory)
with generous headroom rather than trusting the estimates. Turning the clients collector **on**
raises cardinality and memory substantially — size up further. `MetricTTL` and cardinality caps
are tunables, not fixes: `MERAKI_EXPORTER_MONITORING__MAX_CARDINALITY_PER_COLLECTOR` (default
`10000`) sheds oldest label sets per collector, and `MERAKI_EXPORTER_CARDINALITY__MAX_SERIES_PER_FAMILY`
(default `50000`) bounds per-family growth.

## Scaling out & HA

The exporter is a **single-writer singleton**: no leader election, no work sharding, no automatic
failover. This shapes every multi-instance decision below.

### Shard by organization (1 poller = 1 org)

From 1.0 each instance polls exactly one org
([single-org contract](upgrading.md#single-org-deployment-contract-breaking)). To cover several
organizations, run **one instance per org**, each pinned with
`MERAKI_EXPORTER_MERAKI__ORG_ID` (Helm value `meraki.organizationId`). Because the 10 req/s budget
is **per-org**, separate orgs have separate budgets, so N orgs on N instances scale linearly.

Deploy one Helm release per org — distinct release names keep the Deployments, Services, and
ServiceMonitors separate:

```bash
helm install meraki-org-a oci://ghcr.io/rknightion/charts/meraki-dashboard-exporter \
  --version <exporter-version> \
  --set meraki.existingSecret=meraki-secrets \
  --set meraki.organizationId=111111 \
  --set serviceMonitor.enabled=true

helm install meraki-org-b oci://ghcr.io/rknightion/charts/meraki-dashboard-exporter \
  --version <exporter-version> \
  --set meraki.existingSecret=meraki-secrets \
  --set meraki.organizationId=222222 \
  --set serviceMonitor.enabled=true
```

Each release stays `replicaCount: 1` (the chart hard-fails the render otherwise — see below).
See the [Helm chart](https://github.com/rknightion/meraki-dashboard-exporter/tree/main/charts/meraki-dashboard-exporter)
and its `values.yaml` for the full option set.

### `rate_limit_shared_fraction` arithmetic when consumers share an org

The 10 req/s org budget is shared by **everything** that hits that org's API — this exporter, the
Meraki dashboard UI, other tooling, humans running scripts. `rate_limit_shared_fraction` is how you
hand the exporter its slice:

- **Exporter is the main consumer, some human/dashboard use:** default `0.8` → exporter paces to
  ~8 req/s, ~2 req/s left for everyone else.
- **Exporter must coexist with another heavy automated consumer** taking ~40% of the budget: set
  the exporter to `0.6` → ~6 req/s, leaving ~4 req/s.

The rule of thumb: **the fractions of all automated consumers of one org should sum to ≤ 1.0.** The
limiter is **per-process** and does **not** coordinate across consumers — the split is one you
configure by hand. (If two exporters ever pointed at the *same* org — discouraged, see next — each
would need `0.5` to keep the combined draw within budget. Shard by org instead so every org has
exactly one exporter and one full budget.)

### Egress-IP budget when sharding organizations

The 100 req/s source-IP limit is shared across organizations. The usual shard-by-org recipe assumes
each release has a distinct organization **and that no more than about eight default shards share
one egress IP**: $8 \times (10 \times 0.8) = 64$ req/s, leaving room for bursts and other API
clients below 100 req/s. Do not treat the mathematical maximum of 12 default shards (96 req/s) as
an operating target.

If more organizations must run concurrently, spread their egress across additional public IPs or
lower `MERAKI_EXPORTER_API__RATE_LIMIT_SHARED_FRACTION`; lowering the fraction reduces permitted
pace, not collection demand. Kubernetes nodes and a shared NAT gateway commonly collapse many pods
onto one egress IP, so count the actual NAT/egress topology rather than pod replicas.

### Burst-capacity comparison

Meraki documents an allowance of an extra 10 requests in the first second, totalling 30 requests
in two seconds. The exporter token bucket starts full. With the historical default burst capacity
of 20 and the default 8 req/s effective rate, it can issue 20 immediately plus 16 in two seconds
(36 total), so 20 is not compatible with that documented envelope. The default should be a
conservative 10-token capacity: at 8 req/s it permits at most 18 in the first second and 26 in two
seconds. Operators overriding this setting accept the risk of avoidable 429s.

### Why `replicaCount > 1` for one org is harmful

Running two replicas of the same instance does **not** share load or provide HA — with no leader
election and no work partitioning, each replica independently runs **every** collector. The result:

- **Doubled API load against the same shared org budget** — two pods draw ~2× the calls at one org's
  10 req/s, guaranteeing rate-limit starvation.
- **Duplicated / echoed metrics** — every series is emitted twice under two `instance` labels,
  double-counting counters and making scrapes ambiguous.

The Helm chart therefore **hard-fails the render when `replicaCount > 1`** (or
`autoscaling.maxReplicas > 1`), and uses the `Recreate` strategy so a rollout never briefly runs
two pods. Do not relax these guards without adding leader election first.

### Failover and shutdown semantics

There is **no automatic failover and no warm standby** — the model is single-active-instance. The
exporter is fully **stateless** (all state is re-derived from the Meraki API each cycle), so
recovery is just Kubernetes rescheduling the pod; a brief gap in metrics during reschedule is
expected and harmless. Do **not** run a warm standby to shorten that gap — a second live pod is
exactly the double-load / double-metrics problem above.

On `SIGTERM` the exporter drains best-effort: in-flight HTTP requests finish and running collector
work winds down before exit. Because collector fetches run the synchronous Meraki SDK on a thread
pool, a thread blocked inside an SDK HTTP call cannot be cancelled mid-flight.
`per_fetch_deadline_seconds` (default **120 s**) bounds the awaiting coroutine but cannot interrupt a
synchronous thread already doing HTTP or pagination. Executor joins run off the event loop and share
one **5-second** drain budget across DNS, SDK and registry-serving pools. If a running thread outlives
that budget, its cleanup continues in the background while application shutdown proceeds. The chart's
`terminationGracePeriodSeconds` defaults to **150 s** — `per_fetch_deadline_seconds` plus a 30 s
margin — so Kubernetes doesn't `SIGKILL` mid-drain. Set a longer deadline with
`config.apiPerFetchDeadlineSeconds`; Helm enforces `terminationGracePeriodSeconds >= deadline + 30`.
That check rejects known contradictory settings; an uninterruptible SDK or DNS call can still outlive
the grace period. Full detail is in
[Deployment & Operations](deployment-operations.md#shutdown-behaviour-and-grace-period).

## Adaptive scheduling is the default

The adaptive, budget-aware scheduler described above is **shipped and on by default**
(`scheduler.mode=adaptive`) — it paces the exporter to the org budget automatically by
stretching lower-priority endpoint groups' intervals rather than saturating the budget and
relying on you to hand-tune a fixed interval. See [Scheduler Architecture](observability/scheduler.md)
for the full solver/AIMD mechanism, and `MERAKI_EXPORTER_SCHEDULER__*` in [Configuration](config.md)
for every tunable. `scheduler.mode=fixed` (floors/pins only, no stretching, no AIMD) exists as a
debugging/transition fallback, not a recommended steady-state choice.

## Key metrics to monitor

| Metric | What it tells you |
|---|---|
| `meraki_exporter_scheduler_budget_utilization_ratio` | Fraction of the effective budget the solver is currently planning to use; at/above `target_utilization` for long periods means groups are being stretched |
| `meraki_exporter_scheduler_interval_seconds{group}` | Live solved interval per endpoint group — compare against its floor to see how much it has stretched |
| `meraki_exporter_collector_cadence_seconds{collector}` | Live effective cadence per collector (smallest solved interval among its own groups) |
| `meraki_exporter_collection_utilization_ratio{collector}` | Collector body execution time divided by cadence; admission queue wait is excluded |
| `meraki_exporter_task_queue_wait_seconds{phase="collector_admission"}` | Distribution of time collector runs wait for the bounded execution slots |
| `meraki_exporter_task_expired_before_start_total{phase="collector_admission"}` | Exporter saturation: runs whose single wall-clock budget expired in the admission queue; these do not count as collector endpoint failures |
| `meraki_exporter_api_rate_limiter_throttled_total` | Client-side rate-limit pressure (rising = over budget; also drives AIMD backoff) |
| `meraki_exporter_api_rate_limiter_tokens` | Remaining tokens in the per-org bucket |
| `meraki_exporter_cardinality_limit_reached_total` | Metric shedding is active (cardinality cap hit) |
| `meraki_exporter_org_collection_status` | Per-org collection health (`0` = every sub-collection failed) |
| `meraki_exporter_collector_duration_seconds` | How long the admitted collector body executes; it excludes admission queue wait |
| `meraki_network_filter_networks` | How many networks survive the filter (verify your cuts landed) |

## Troubleshooting

### Continuous rate-limit throttling

- **Symptom:** `meraki_exporter_api_rate_limiter_throttled_total` climbing steadily; 429s in logs;
  `meraki_exporter_scheduler_budget_utilization_ratio` pinned near or above 1.0.
- **Cause:** cycle demand exceeds the org budget even after the solver has stretched every
  eligible group to its cap — a structural [envelope](#practical-single-org-envelope-today)
  problem, not a pacing one.
- **Fix:** cut demand — [Network Filter](#network-filter), pin specific noisy groups via
  `scheduler.group_interval_overrides`, stretch the per-endpoint gates, disable unneeded
  collectors. Lowering the RPS cap alone will not help.

### Collector timeouts

- **Symptom:** `meraki_exporter_collection_errors_total{error_type="TimeoutError"}` rising (the
  run-level collector budget expiring — distinct from
  `meraki_exporter_collector_errors_total{error_type="timeout"}`, which is per-API-call).
- **Fix:** the collector cannot finish inside 240 s when a large due sweep exceeds the available
  API budget. Reduce $W$ via the filter, or pin the offending group(s) to a longer interval via
  `scheduler.group_interval_overrides` (this reduces how often the run happens, not how long a
  single run takes, but fewer runs means fewer chances to time out); raising
  `MERAKI_EXPORTER_COLLECTORS__COLLECTOR_TIMEOUT` only masks it.

### Cardinality spikes / OOM

- **Symptom:** `meraki_exporter_cardinality_limit_reached = 1`, or the pod OOM-kills.
- **Fix:** size memory from observed RSS (see [Resource sizing](#resource-sizing-memory-cpu)),
  keep the clients collector off, and reduce the tracked fleet with the filter. Raising
  `MERAKI_EXPORTER_MONITORING__MAX_CARDINALITY_PER_COLLECTOR` trades memory for retention — it is
  not free.

### Per-org backoff

- **Symptom:** `meraki_exporter_org_collection_status = 0`.
- **Fix:** verify the API key's access to that org and its permissions; check the logs for the
  failing sub-collection.
