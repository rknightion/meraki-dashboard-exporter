---
title: Scheduler Architecture
description: How the adaptive, budget-aware endpoint scheduler derives per-collector cadence from organization shape and the Meraki API rate-limit budget
tags:
  - scheduler
  - architecture
  - rate-limiting
---

# Scheduler Architecture

The exporter has no fixed FAST/MEDIUM/SLOW tier system. Instead, every API fetch a collector
makes is declared as an **endpoint group**, and an adaptive scheduler (`core/scheduler.py`)
solves each group's polling interval from the organization's size, the group's own volatility,
and the configured Meraki API request budget. Each collector then runs its own group-clocked
loop rather than sharing a global tick.

## The pieces

**Endpoint groups.** Each collector declares one or more `EndpointGroup`s: a name, a `priority`
(1 = up-ness/alerts, 2 = sensor data, 3 = performance/health, 4 = configuration/inventory —
lower number is more important), a `floor_seconds` (the natural data-volatility window; the
group is never polled faster than this regardless of budget), a `cost_fn` (estimated API calls
for one execution, as a function of the org's shape — device/network counts by type), and
optionally `gated=False` for pure demand-accounting overhead groups that always run, an
`enabled_fn` for groups that toggle on/off based on org shape or config (e.g. license-gated
features), and a `setting_pin` linking it to a legacy per-endpoint interval knob.

**Organization shape (`OrgShape`).** A sizing snapshot — network/device counts by product type
— computed from the cached inventory. The scheduler resolves against this shape, so a larger
estate naturally produces larger cost estimates and, if the budget is tight, more stretching.

**The solver (`solve_intervals`).** A pure, deterministic function with no I/O or clock:

1. Every group starts at its own `floor_seconds` — there is no tier heartbeat to inherit.
2. Operator `group_interval_overrides` pins are applied exactly (a pin below the floor is
   honoured with a warning log); pinned groups are excluded from stretching.
3. Total demand is `Σ cost_fn(shape) / interval` across *every* group, including ungated
   overhead groups.
4. While demand exceeds `budget_rps × target_utilization`, the solver stretches the
   unpinned, gated group chosen by `(-priority, stretch_factor, name)` — lowest-priority class
   first, then the least-already-stretched group within that class, name as a deterministic
   tiebreak — multiplying its interval by 1.5 each round, capped at
   `min(floor × max_stretch_factor, max_interval_seconds)`. It stops once demand fits, or once
   every group has hit its cap (logged as `over_budget`).
5. Identical inputs always produce identical output — this is why it can run as a pure function
   in tests without a clock or network.

**The budget.** `requests_per_second × shared_fraction` from `APISettings`, optionally reduced
further by the live AIMD-controlled rate limiter (see below) — `EndpointScheduler` always solves
against the *effective*, AIMD-adjusted budget, not just the static configured one.

**AIMD feedback (`OrgRateLimiter`).** When the Meraki API returns a 429 with `Retry-After`, the
rate limiter applies a multiplicative decrease (`effective ×= aimd_backoff_multiplier`, floored
at `0.5` rps, cooled down to at most one halving per 30s) to the *effective* client-side budget.
Outside of throttle events it recovers additively at `aimd_recovery_rps_per_minute`. A tightened
effective budget flows straight into the next scheduler resolve, which then stretches more
groups to compensate — this is what makes the scheduler "adaptive" beyond just organization
size.

**Resolving.** `EndpointScheduler.resolve(shape)` recomputes every group's interval, emits
Prometheus gauges (`meraki_exporter_scheduler_interval_seconds{group}`,
`meraki_exporter_scheduler_stretch_factor{group}`,
`meraki_exporter_scheduler_estimated_demand_rps`, `meraki_exporter_scheduler_budget_rps`,
`meraki_exporter_scheduler_effective_budget_rps`,
`meraki_exporter_scheduler_budget_utilization_ratio`), and logs a summary (including which
groups stretched and by how much). It runs
periodically at `scheduler.resolve_interval_seconds` (default 900s, matching the inventory TTL)
so a growing/shrinking estate or a persistent throttle event is picked up without a restart.

## Per-collector group-clocked loops

Each collector owns a fixed set of endpoint groups and runs its own asyncio loop
(`ExporterApp._collector_loop` in `app.py`):

1. Run the collector once (`CollectorManager.run_collector_once`). Internally, each of the
   collector's fetches is gated by `EndpointScheduler.should_run(group)`, which is due once
   `interval × 0.9` has elapsed since that group's last **success** (a 10% tolerance so wake-time
   jitter can't cause a skipped beat).
2. Sleep until the earliest-due of the collector's own enabled groups
   (`EndpointScheduler.seconds_until_due`), capped at one scheduler resolve period so a re-solve,
   an AIMD adjustment, or a newly-enabled group is picked up promptly. A spurious early wake is a
   cheap no-op — the gate just says "not due yet" and the loop sleeps again.
3. On the very first steady-state wake after the initial startup collection, the loop delays by
   the collector's `phase_offset_seconds()` — a deterministic (sha256-derived), per-class offset
   bounded by `min(0.5 × cadence, 120s)` — so collectors don't all wake in lockstep. This is
   skipped immediately after a cold start/restart so readiness isn't delayed.

A collector's **cadence** (`MetricCollector.collector_cadence_seconds()`) — the number surfaced
on `/status` and in `meraki_exporter_collector_cadence_seconds{collector}` — is the smallest
solved interval among its own enabled, gated groups; it falls back to
`scheduler.resolve_interval_seconds` if the collector has no scheduler or no enabled gated
groups. It also drives the fan-out smoothing window and the metric-TTL fallback for that
collector's series.

## Failure-retry spacing

`should_run` also tracks *attempts*, not just successes: it records `last_attempt` whenever it
returns `True`. If the most recent attempt did not produce a success (`last_attempt >
last_ran`, or the group has never succeeded), the group's next attempt is additionally spaced
by `scheduler.failure_retry_seconds` (default 300s) instead of hot-looping on every wake. A
group's *normal*, successful cadence is never delayed by this — a 60s-floor group like MT sensor
readings still runs roughly every 54s (interval × 0.9) as long as it keeps succeeding; only a
persistently-failing group backs off. `mark_ran(group)` is only called after at least one
success within a fetch, so a partial success still advances the clock.

## Config knobs

| Setting | Default | Effect |
| --- | --- | --- |
| `MERAKI_EXPORTER_SCHEDULER__MODE` | `adaptive` | `adaptive` (default): solver stretches groups to fit budget. `fixed`: floors/pins only, no stretching, no AIMD — a transition/debugging fallback, not the normal mode. |
| `MERAKI_EXPORTER_SCHEDULER__TARGET_UTILIZATION` | `0.7` | Fraction of the effective budget the solver plans to; the rest is headroom for bursts. |
| `MERAKI_EXPORTER_SCHEDULER__MAX_STRETCH_FACTOR` | `4.0` | Per-group interval cap as a multiple of its floor. |
| `MERAKI_EXPORTER_SCHEDULER__MAX_INTERVAL_SECONDS` | `3600` | Absolute per-group interval cap, regardless of stretch factor. |
| `MERAKI_EXPORTER_SCHEDULER__RESOLVE_INTERVAL_SECONDS` | `900` | How often the solver recomputes from the current org shape. |
| `MERAKI_EXPORTER_SCHEDULER__FAILURE_RETRY_SECONDS` | `300` | Minimum spacing between retries of a group whose last attempt failed. |
| `MERAKI_EXPORTER_SCHEDULER__AIMD_ENABLED` | `true` | Whether 429/`Retry-After` responses adjust the effective budget (adaptive mode only). |
| `MERAKI_EXPORTER_SCHEDULER__GROUP_INTERVAL_OVERRIDES` | `{}` | Per-group interval pins, e.g. `{"nh_connection_stats": 900}`. Pinned groups are excluded from solver stretching. |
| `MERAKI_EXPORTER_COLLECTORS__MAX_CONCURRENT_COLLECTORS` | `5` | Global semaphore bounding how many collectors' group-clocked loops may be mid-run concurrently (replaces the old per-tier concurrency knobs). |

See [Configuration](../config.md) for the full list including constraints, and
[Scaling Guide](../scaling-guide.md) for guidance on pinning specific groups or tuning
concurrency for large estates.

## Where to observe it live

- `/status` — the **Endpoint Groups** table lists every group's current solved interval,
  stretch factor, priority, and pin status; also available as JSON via `/status?format=json`.
- `meraki_exporter_scheduler_interval_seconds{group}`,
  `meraki_exporter_scheduler_stretch_factor{group}`,
  `meraki_exporter_scheduler_estimated_demand_rps`, `meraki_exporter_scheduler_budget_rps`,
  `meraki_exporter_scheduler_effective_budget_rps`,
  `meraki_exporter_scheduler_budget_utilization_ratio` — live scheduler gauges.
- `meraki_exporter_collector_cadence_seconds{collector}` — live effective cadence per collector.
- See [Data Freshness & Alerting Guidance](../data-freshness.md) for how to turn these into
  staleness alert rules.
</content>
