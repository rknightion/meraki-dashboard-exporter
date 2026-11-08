---
id: doc-0004
title: Hardening programme standing decisions (D1-D18)
type: other
created_date: '2026-08-14 16:02'
updated_date: '2026-08-14 16:02'
---
These are the **frozen decisions and carried-forward corrections** of the v1.1 production-hardening
programme, taken during triage on **2026-08-12** and migrated here on 2026-08-14 from GitHub issue
#694, which was the programme tracker before this repo moved to Backlog.md.

**Do not re-litigate them.** Each answers a question the audit raised, and each carries its reason
because a decision without its reason gets argued back. If you have new evidence one is wrong, say so
on the affected task before acting.

The remaining work is the `v1.1-hardening` milestone: `backlog task list --plain -m v1.1-hardening`.
Phases P0 (release boundary / security), P1 (API ownership) and P2 (scheduler and resilience) are
complete. P3 (fixtures and scale), P4 (lifecycle and failure harness) and P5 (truth and docs) have one
task each left.

## Where this came from

An adversarial nine-lane read-only audit run on 2026-08-12 against `5579b26`, with live contention
testing against a personal organisation. It produced **43 findings** (1 blocker, 10 high, 26 medium, 5
low, 1 info after adjudication). Triage added **3 more**: two vendor-limit findings the audit missed
and one arithmetic contradiction it under-stated. All 46 were mapped onto child issues, and the
mapping was the audit trail — no finding was dropped.

The mission it was accepted under: make this exporter safe and sane to run in production, unattended,
for months, against a **large Meraki organization**. At the time it should not have been offered to a
500-network / 5,000-device customer — an unauthenticated control endpoint could force full
collections, the scale model projected an unsustainable API plan and a multi-million-series registry
for a plausible switch-heavy fleet, and two rate limiters paced the same traffic without knowing about
each other.

---

## D1 — Control-POST authentication: fail closed, no escape hatch

`/api/collectors/trigger` and `/api/clients/clear-dns-cache` return **401 unless `server.api_token` is
set**. **No** `insecure_allow_unauthenticated_control` flag — rejected because a permanently-supported
insecure mode gets set in a Helm values file and forgotten, returning the blocker to the field. The web
UI **omits or disables** the trigger and DNS-clear buttons, with an explanatory tooltip, when no token
is configured. This **overturns the earlier #558 / F-167 decision**, which knowingly left POST auth
optional. Breaking change for v1.0.x users of those buttons; needs a `docs/upgrading.md` entry.

## D2 — Fleet fixtures: one generator, SEVEN named presets, tiered in CI

A single generator parameterised by `(networks, per-family device counts, ports/switch, SSIDs/network,
clients)`.

| Preset | Shape | Stresses |
|---|---|---|
| `HOMELAB` | 1 net / 19 dev (1 MR56, MS120-8LP, MS250-24P, 16 MT) | the measured baseline — must reproduce live numbers |
| `BRANCH-RETAIL` | 750 nets x (2 MX + 1 MS24 + 3 MR) ~ 4,500 dev | **network-count-driven API budget** — the dominant real shape |
| `CAMPUS` | 20 nets, ~4,000 MR + 1,200 MS48 ~ 5,200 dev | dense wireless, per-AP fan-out |
| `DENSE-SWITCH` | 50 nets, 2,000 MS @ 48 ports ~ 96k ports | **cardinality / series explosion** |
| `XL-MULTI-SITE` | 3,500 nets / ~20,000 dev | pagination depth, org ceiling |
| `MULTI-ORG-SHARD` | N instances x N orgs from one source IP | the 100 req/s per-source-IP limit |
| `CAMERA-HEAVY` | 30 nets x 800 MV | MV, the least-verified family |

**CI tiering:** every PR → `HOMELAB` + `BRANCH-RETAIL`. Scheduled → `CAMPUS`, `DENSE-SWITCH`,
`XL-MULTI-SITE`. On demand → `MULTI-ORG-SHARD`, `CAMERA-HEAVY`.

**Binding honesty rule:** `CAMERA-HEAVY`, and every absent-family element in any other preset, is
marked `SHAPE-ASSUMED` in the fixture, so a green test can never read as having verified a family
nobody owns.

### Vendor limits the presets must respect (researched 2026-08-12, authoritative)

- **50,000** devices/org recommended max; **5,000** devices/network combined.
- Hard **per-network** caps: **MX = 2**, **MG = 4**, MV = 1,000, MT = 1,700, APs = 5,000,
  switches = 5,000. This makes "1,000 devices per family bucket, evenly distributed" **structurally
  impossible** — a 500-network org cannot hold more than 1,000 MX or 2,000 MG.
- More than 700 orgs → Meraki asks you to contact your account team. Meraki names **20,000+ devices**
  as the point where API monitoring beats SNMP.
- Real published estates are **branch-shaped, not campus-shaped**: a 3,500-store grocery chain, a
  740-location optical retailer, a 500-store retailer; community operators run 1,000+ networks in one
  org and hit the 10 req/s ceiling daily. **The audit modelled no such shape**, and it is the one most
  likely to break this exporter, because most of its cost scales with network count.

## D3 — Client collection: supported at LARGE, with every unbounded dimension bounded

Rejected moving per-client signals to data-logs-only (breaking on a released 1.x, and it reverses
#533's approved ID-only join) and rejected declaring it small/medium-only (a warning that still lets
you enable it merely documents the failure). The defect is **unboundedness, not volume** — ~275k series
is only ~13% of the LARGE projection, but applications-per-client had no cap an operator could set.
`clients.enabled` defaults to **`False`**, so the default path carries none of this risk.

## D4 — Pacing: project AIMD owns it, smart flow OFF, one instrumented facade

Set `smart_flow_enabled=False` explicitly; `OrgRateLimiter` becomes the sole pacer. Every SDK call
routes through **one facade** that acquires a token, records the attempt and owns retries. Verified in
the pinned SDK (`meraki/config.py`): `SMART_FLOW_ENABLED = True`, `SMART_FLOW_ORG_RATE = 9`,
**`SMART_FLOW_GLOBAL_RATE = 100`** — the SDK already implements the per-source-IP limit, so disabling
smart flow removes that protection, which is why D5 exists — and **`SMART_FLOW_CACHE_PATH =
~/.meraki/.cache/rate_limit_cache.json`** with a 7-day TTL, which writes rate-limit state into `$HOME`
and breaks or misplaces itself on a read-only root filesystem. Measured scope at the time: **141 raw
`asyncio.to_thread` call sites**.

## D5 — The 100 req/s per-source-IP limit: documentation only, no code

A single process cannot know how many siblings share its NAT IP, so enforcement would be guessing.
Document the limit and its arithmetic in `docs/scaling-guide.md`, cap recommended **shards per egress
IP at ~8** at the default `shared_fraction`, and state that larger fleets must spread across egress IPs
or lower `shared_fraction`.

## D6 — Over-budget: explicit profile selection above a computed threshold

Above a threshold **computed from the solved plan versus budget** (not a raw network count, so it is
shape-aware), startup **fails unless `collectors.profile` is set explicitly**, naming the measured
demand and the options. Profiles: `availability` = priority 1 only, `standard` = priorities 1–3,
`full` = everything. **Inside** a chosen profile, if demand still exceeds budget, priority 1 and 2 keep
their floors and priority 3/4 shed — the scheduler must **stop stretching priority 1/2**, which was the
actual defect (availability degrading to 480s, MT to 240s). `over_budget` and per-group skip counters
are exposed so it is alertable.

## D7 — `/ready` stays a startup gate; staleness becomes metrics

Document `/ready` as "initial collection completed". `/health` keeps the dead-man staleness check. Add
**per-collector and per-endpoint-group last-success age as Prometheus metrics** so alerting lives in
Prometheus, not a probe. Why `/ready` is not freshness-based: a NotReady pod is dropped from Service
endpoints, so **Prometheus stops scraping and you lose the metrics that explain the failure**, and a
transient Meraki outage would stall or roll back deployments.

## D8 — Backoff scoped by domain; org-wide only on org-wide evidence

Each domain / endpoint group tracks its own failure streak and backs off independently. Org-wide
suppression fires only on **401/403 on any call, or connectivity failure spanning multiple domains**. A
**404 or 402 on an optional license-gated endpoint never counts toward any streak** — it means "not
licensed", which is permanent state, not a failure.

## D9 — `api_base_url`: HTTPS-only, allowlist by default, unconditional redirect credential strip

Reject plain `http`. Accept the five origins already in `KNOWN_REGION_BASE_URLS` silently; anything
else requires explicit `meraki.allow_custom_api_base_url: true`. **Independently and unconditionally,
never carry the `Authorization` header across an origin change on redirect** — that path is
attacker-influenced rather than operator-chosen. Narrows #590 without reversing it.

## D10 — Bad config: fail fast on provably-wrong, warn on merely-suboptimal

The real bug was the blanket `except` in `_startup_collections`: continuing is **correct for a
transient Meraki outage and wrong for a deterministic config error**. **Refuse to start:** zero-match
`NetworkFilter`; empty effective collector set; `collector_timeout` < `per_fetch_deadline_seconds`.
**Warn and run:** executor under-provisioned against admission; workable-but-unusual pacing.

## D11 — Helm resources: raise defaults to cover MEDIUM, document LARGE separately

Decoupled from D6's profiles deliberately. **The new default must come from the `MEDIUM` preset's
MEASURED RSS once D2's fixture runs, not from a judgement call** — otherwise 512Mi is replaced by
another number with nothing behind it. This is `mde-0002`.

## D12 — Client identifiers: never substitute a MAC, and scrub bodies

Delete the `client.id or client.mac` fallback. With no ID, emit the row with the identifier field
**omitted, not the row dropped**. When `include_identifiers=false`, **scrub MAC-shaped strings from the
message body too** — key-only filtering was the underlying bug.

## D13 — Webhooks: freshness window + TTL dedupe on alertId, and split the metrics

Reject payloads whose `sentAt` is outside a bounded, configurable window (sane floor for clock skew,
clear log on rejection). Bounded TTL cache keyed on `alertId` or body fingerprint; apply device state
**once per alert**. Emit `delivery_attempts_total` and `unique_alerts_total` **separately**, so
Meraki's legitimate retries stay visible while state transitions are idempotent.

## D14 — Scanner gating: split by determinism

**Merge gates** on change-scoped, stable scanners: `zizmor`, `actionlint`, `dependency-review`.
**Publish gates** on HIGH/CRITICAL from Trivy and CodeQL, with **the scan moved BEFORE
push/sign/attest**, plus a committed exception file carrying a reason and an **expiry date** per
accepted CVE. Gating everything on merge would stall the repo on third-party CVE disclosures and, on a
solo repo, predictably ends with the gate bypassed. This is `mde-0003`.

## D15 — A disposable instance, recorded corpus and fault-injection proxy

A throwaway containerised exporter against a **recorded Meraki response corpus**, with a proxy
injecting 429s, timeouts, TLS failures, HTML bodies, slow responses and connection resets on demand.
**Pinned by digest, never `:main`, excluded from automatic image updates.** No live org involvement —
you cannot revoke a working key to test revocation, but a proxy returns 401 all day. **Response shapes
in the corpus must come from real captures, never invented**, or the corpus encodes the same wrong
assumption as the code. Landed 2026-08-14 as a reusable local/CI test capability, not a deployment.

## D16 — Publish verification level per device family

Rewrite `docs/support-matrix.md` so each family carries **live-verified / spec-verified /
community-reported**, with the date and what was checked. Add an issue template soliciting sanitised
real responses — one response is all a fixture needs, and a user with an MX is likelier to paste JSON
into an issue than to grant org access. (This is part of why the GitHub tracker stays open.)

## D17 — Doc generators: fail loudly instead of under-reporting

Parse failures **exit non-zero**. Delete the dead `CircuitBreaker` and `async_utils.py` exclusions.
Convert the "Found N…" eyeball check into **assertions**, and fail if `config.md`'s hardcoded
`nested_models` list diverges from the settings tree `.env.example` walks.

## D18 — "New device family" means a new product type

Six seams applies to a genuinely new Meraki **product type**. A new **model subtype of an existing
product** costs nothing structural — Catalyst/CS already routes through the MS collector. No fix
required.

---

# Corrections carried forward — do not re-derive these

Each of these was believed, investigated and disproved. The belief is kept with the correction, because
a bare corrected fact loses the warning that the old belief was seductive.

- **The 60 HTTP 400s were NOT the exporter.** The Dashboard request audit log showed 59 were external
  `createOrganizationActionBatch` POSTs from a different consumer; the exporter issues no POSTs at all.
  The 60th was the audit's own deliberate malformed GET.
- **`meraki_org_api_requests_count` is a trailing-hour, ALL-CLIENT gauge**, not exporter lifetime
  volume. It cannot validate a calls-per-cycle model. This is what produced the finding that the
  exporter's own counter only increments in `OrganizationInventory._make_api_call`.
- **`scripts/CLAUDE.md` falsely denied the CI docs-drift gate existed.** It does exist, and it was red
  for 20 consecutive runs (2026-08-10 → 2026-08-12) before being fixed in `ce03473`. *Since corrected:
  `scripts/CLAUDE.md` now documents the gate.* The transferable lesson stands — treat every in-repo
  `CLAUDE.md` as a claim to verify, not ground truth.
- **`CircuitBreaker` did not exist anywhere in this codebase**, yet `generate_metrics_docs.py` still
  excluded it, and excluded all of `async_utils.py` for a reason that had evaporated with it. *Since
  corrected under D17 in `0410fc2`; both exclusions are gone.*
- **Pushing to `main` redeploys the live soak host.** It runs watchtower, so a push rebuilds
  `ghcr.io/…:main`, watchtower pulls it, and the container restarts — which destroyed the 15-hour
  counters the audit was handed. Any work depending on soak counters must pin a digest or snapshot
  first. This is why `mde-0001` cannot be settled from soak counters.
- **The 2026-07-02 `evidence/` pack is STALE** (baseline `f08cd69`, spec 1.72.0, SDK 3.3.0; the tree
  was 168 commits, spec 1.73.0 and SDK 4.4.0 further on by the time of the audit). Use it to see what
  was already assessed, never as current truth.
