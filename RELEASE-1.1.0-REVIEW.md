# v1.1.0 Release Review — Remediation Brief

**Target:** release-please PR [#673](https://github.com/rknightion/meraki-dashboard-exporter/pull/673) `chore(main): release 1.1.0`
**Release span:** `v1.0.2..main` — 74 commits, 221 files, ~2,234 insertions / 818 deletions in `src/` alone
**Review date:** 2026-08-16 · **Reviewed at:** `main` @ `4fa7cfc`, PR head `2a1619a`
**Method:** six parallel review agents, one per subsystem, each required to state a concrete failure
scenario and to attempt to refute its own findings before reporting. Every claim below carries a
`file:line` anchor. Findings marked CONFIRMED were traced end to end or reproduced with a probe script;
PLAUSIBLE means the mechanism is certain but reachability is deployment-dependent.

---

## HOW TO USE THIS DOCUMENT

You are a coding agent tasked with resolving the issues below. Read this section fully before editing.

### Your mission
Unblock the v1.1.0 release and fix the defects this review found, **in the priority order given**.
P0 unblocks CI. P1 items are release-blocking correctness or availability regressions. P2 are real
bugs that should not ship silently. P3 are lower-severity and may be deferred to a follow-up — but say
explicitly which you deferred.

### Ground rules — these override your defaults
These come from `AGENTS.md` and the per-directory `CLAUDE.md` files. Violating them is a failed task.

1. **Read the `CLAUDE.md` of every subdirectory you touch before editing it.** They are the contract.
2. **Never use hardcoded metric or label names** — always the domain enums
   (`OrgMetricName`/`DeviceMetricName`/`MSMetricName`/`MRMetricName`/`CollectorMetricName` in
   `core/constants/metrics_constants.py`, `LabelName` in `core/metrics.py`).
3. **Never call `getOrganizationNetworks` directly from a collector** — go through
   `OrganizationInventory.get_networks(org_id)` so `NetworkFilter` is enforced. Only three bypasses are
   sanctioned: `core/discovery.py::DiscoveryService` (unfiltered, audit), and
   `collectors/alerts.py::_fetch_networks_direct` + `core/api_helpers.py::_fetch_networks_direct`
   (both reapply `NetworkFilter` manually).
4. **Never use unbounded parallelism** — `ManagedTaskGroup` / `process_in_batches_with_errors`, never
   raw `asyncio.gather`.
5. **Never add a client-keyed or otherwise unbounded per-entity labelled Prometheus metric** — those
   route to the OTel data-log emitter (`core/otel_data_logs.py`). The opt-in `collectors/clients.py`
   ID-only series + `meraki_client_info` join is grandfathered.
6. **Wrap new API fetchers with `core.error_handling.validate_response_format`.**
7. **Emit metrics via `parent._set_metric()`** so expiration tracking works.
8. **Never log or expose API keys.**
9. **Never modify a test to match an incorrect implementation.** If a test encodes the bug, fix the
   code and the test together, and say so in your summary.

### How to work
- **Test-first for every behavioural fix**: write the failing test, watch it fail *for the intended
  reason*, then make the minimal change, then green. Several findings below include the exact test that
  is missing — those tests are part of the deliverable, not optional.
- **Verify assumptions against reality, do not trust this document blindly.** It was written against
  `4fa7cfc`; line numbers drift. Confirm each anchor before editing. If a finding is already fixed or
  the analysis is wrong, say so explicitly rather than inventing a change.
- **One commit per deliverable**, Conventional Commits (release-please parses the subject).
- **Where a finding offers two fix directions, they are genuinely different products.** Pick one,
  state which and why, in a sentence. Do not silently pick the smaller one because it is easier.
- **If a fix requires a decision this brief does not cover — stop and ask.** Do not invent a policy.

### Definition of done (the gate in `backlog/config.yml`)
Run these and **see the output** — evidence, not assertion:
```bash
make check                 # ruff + ruff format + mypy + pytest
make docgen                # only when generator inputs changed; commit the result
```
Plus, when a metric or label name moves: update the affected `grafana/dashboards/*.json` queries and
`grafana/alerts/*.yaml` rules, and say what you changed.

### Important context about the CI environment
CI runs **Python 3.14.7** and **uv 0.12.5**. Older 3.14 release candidates fail with
`TypeError: _eval_type() got an unexpected keyword argument 'prefer_fwd_module'` from pydantic — that
is a local-toolchain artifact, not a code defect. Use `uv python install 3.14.7`.

---

## P0 — THE CI BLOCKER (do this first, it is a one-line change)

### P0.1 Stale `uv.lock` fails `uv sync --locked` on the release PR

**Status: root-caused and reproduced end to end. This is the ONLY thing failing CI.**

| | |
|---|---|
| **Failing check** | `test` → `ci-success` (the latter fails only because it aggregates `test`) |
| **Failing step** | `.github/workflows/ci.yml:49` — `uv sync --locked` |
| **Error** | `error: The lockfile at uv.lock needs to be updated, but --locked was provided.` |
| **Cause** | release-please bumped `pyproject.toml` 1.0.2→1.1.0; `uv.lock:625` still records the project's own version as `1.0.2` |

**Why the auto-remediation did not fire.** `.github/workflows/release-please-lock.yml` exists precisely
to fix this, and **both its jobs were skipped**. Its author guard at lines 33-38 allows
`rknightion-token-broker[bot]`, `github-actions[bot]`, `release-please[bot]`. PR #673's author is
`rknightion` (user id 12484127) — a human account matching none of them. The workflow *did* trigger at
10:11:34 UTC on `synchronize`; the job was **skipped**, not errored.

**Critical: the allowlist is already correct — do NOT edit it.** PR #673 was created **2026-07-23**,
when `release-please.yml` still authenticated with `secrets.RELEASE_PLEASE_TOKEN`, a PAT owned by
`rknightion`. Commit `0f9c03c` (2026-08-08) replaced that PAT with a broker-minted GitHub App token;
`release-please.yml:26-28` records the consequence: *"The release PR's author becomes the App rather
than rknightion."* Commit `bc8c1a9` added `rknightion-token-broker[bot]` to the allowlist for exactly
that reason. **A PR's `user.login` is immutable, and release-please force-pushes an existing release
branch in place rather than re-authoring it** — which is why #673 carries commits through 2026-08-16
while its author is still the July identity. Every *future* release PR will match the guard. Adding
`rknightion` would permanently re-admit a retired identity to a secret-adjacent guard to accommodate
one legacy PR. Close-then-**reopen** would not help either: reopening preserves `user.login`.

**Fix (verified by executing it):**
```bash
git fetch origin release-please--branches--main--components--meraki-dashboard-exporter
git checkout release-please--branches--main--components--meraki-dashboard-exporter
uv lock
git add uv.lock
git commit -m "chore: sync uv.lock with release version 1.1.0"
git push origin HEAD:release-please--branches--main--components--meraki-dashboard-exporter
```
`uv lock` output: `Updated meraki-dashboard-exporter v1.0.2 -> v1.1.0`. **The resulting diff is exactly
one line** — no dependency resolution change:
```diff
 [[package]]
 name = "meraki-dashboard-exporter"
-version = "1.0.2"
+version = "1.1.0"
```
Caveat: release-please force-pushes the release branch when it regenerates, so a further push to `main`
before merge would discard this commit. Merge promptly, or re-run.

**Options considered and rejected:** editing the author allowlist (widens a security guard for one
stale PR); dropping `--locked` from CI (removes the only guard against lockfile drift — the exact class
`ci.yml:47-48` documents); a release-please native mechanism (**does not exist** — the `generic`
updater only rewrites lines carrying an `x-release-please-version` marker, and a marker comment in a
machine-generated `uv.lock` would be clobbered by the next `uv lock`). Closing #673 so release-please
recreates it broker-authored is correct but heavier — keep as fallback.

**Post-fix CI is fully green — independently verified twice**, on CI's exact toolchain
(Python 3.14.7, uv 0.12.5), against the release branch:

| Step | Result |
|---|---|
| `uv sync --locked` | PASS |
| `ruff check` / `ruff format --check` | PASS — all checks passed, 358 files formatted |
| `mypy .` | PASS — no issues in 121 source files |
| `./scripts/generate-docs.sh` + drift check | PASS — generators exit 0, `git diff` empty |
| apidrift offline conformance | PASS — exit 0 |
| `pytest --cov-fail-under=80` | PASS — **2728 passed, 5 deselected, coverage 91.14%** |

`docker-build-test`, `helm-lint-kubeconform`, `zizmor`, `actionlint`, `dependency-review` and `semgrep`
already pass on the PR head. No generator embeds the project version, so the bump cannot itself cause
docs drift.

---

## P1 — RELEASE-BLOCKING DEFECTS

These are behaviour regressions or availability hazards that ship to every user. Fix before tagging.

### P1.1 [HIGH] The default profile silently stops collecting 40 of 79 endpoint groups
**`core/scheduler.py:64`, `:414-420`, `:422-427`, `:511`** · CONFIRMED (reproduced)

`active_profile()` resolves an unset `collectors.profile` to `"standard"` (priority ≤ 3), so
`_groups_for_profile()` drops every priority-4 group from the solve and `profile_allows()` returns
`False` for them — they can never be scheduled.

```python
_PROFILE_PRIORITIES = {"availability": 1, "standard": 3, "full": 4}   # :64
def active_profile(self) -> str:
    return self.configured_profile() or "standard"                     # :414-416
```

**Failure scenario.** Stock config, no env vars changed, *any* org size. Upgrading v1.0.2 → v1.1.0 takes
the exporter from **79 registered groups to 39 runnable**. Reproduced — the 40 disallowed groups
include `config_org`, `insight_applications`, `insight_app_health`, `org_licenses`, `org_firmware`,
`org_firmware_compliance`, `org_top_usage`, `org_app_usage`, `org_config_templates`,
`org_device_model_overview`, `org_adaptive_policy`, `org_packet_captures`, `org_webhook_logs`,
`ms_stacks`, `ms_stp`, `ms_port_overview`, `ms_power_summary`, `ms_dhcp_security`,
`ms_link_aggregations`, `mv_analytics`, `mv_onboarding`, `mv_sense_config`, `mr_rf_profiles`,
`mr_signal_quality`, `mr_ssid_usage`, `mr_ssid_firewall`, `mr_wireless_controller`,
`mx_firewall_config`, `mx_vlan_config`, `mx_vpn_config`, `mx_nat_config`, `mx_security_config`,
`mx_dhcp_subnets`, `mx_uplinks_overview`, `mt_alert_profiles`, `mt_relationships`, `mg_esims`,
`mg_cellular_config`, `clients_app_usage`, `clients_signal_quality`.

`ConfigCollector`, `InsightCollector`, MV analytics, MS stacks/STP, licensing and firmware all go dark.
Because `_group_ttl_seconds()` still resolves a TTL, `MetricExpirationManager` then **deletes those
series**, so existing dashboards and alert rules break (`absent()`/staleness rules fire) with no error
logged — only `logger.info(..., profile="standard", groups=39)`.

v1.0.2 solved every group (`git show v1.0.2:core/scheduler.py:458` → `self._groups.values()`); the new
code solves `self._groups_for_profile(profile)`. `docs/scaling-guide.md:113`, `:175-179` present
profiles as something to set *above the computed threshold* — the docs never say the standard filter
applies unconditionally, including to under-budget fleets.

**Fix — pick one and say which.**
(a) Default the unset profile to `full`, preserving v1.0.2 behaviour and letting the over-budget
shedder do the demand work it was written for. **Recommended** — this is a silent data-loss regression
on upgrade, and the shedder already exists for the case the filter is trying to solve.
(b) Keep `standard`, but treat it as a documented BREAKING change: emit a startup WARNING naming the
dropped groups, and cover it in the release notes and `docs/scaling-guide.md`.

**Acceptance:** a test asserting that with no `collectors.profile` set, the number of runnable groups
equals the number of registered groups (option a), or that a WARNING naming the dropped groups is
emitted at startup (option b).

---

### P1.2 [HIGH] Cross-origin auth stripping breaks Meraki shard/region redirects — permanent 401 outage
**`api/client.py:27-52`** · mechanism CONFIRMED (traced through meraki 4.4.0), reachability PLAUSIBLE

The `#697` credential boundary compares each request URL against a one-time snapshot of the
*configured* base-URL origin. But the Meraki SDK legitimately retargets requests to other
`*.meraki.com` hosts — and **permanently rewrites `session._base_url` when it does**.

```python
configured_origin = _origin(base_url)          # snapshot of api.meraki.com, never updated
def send_with_auth_boundary(self, method, url, **kwargs):
    if _origin(url) == configured_origin:
        return original_send(method, url, **kwargs)
    request = self._client.build_request(method, url, **kwargs)
    request.headers.pop("Authorization", None)   # strips on ANY other host
```
```python
# meraki 4.4.0 response_handler.py
def handle_3xx(self, response):
    abs_url = response.headers["Location"]
    substring = "meraki.com/api/v"
    if substring not in abs_url: substring = "meraki.cn/api/v"
    self._base_url = abs_url[: abs_url.find(substring) + len(substring) + 1]
    return abs_url
```

**Failure scenario.** A request returns `302/308` with `Location: https://n123.meraki.com/api/v1/...`.
The SDK mutates `_base_url` to the new host and re-enters `_send_request` with the n123 URL. `_origin()`
now differs → the patched sender pops `Authorization` → Meraki replies 401 → `_handle_client_error`
(with `retry_4xx_error=False`) raises `APIError(status=401)` → `record_auth_outcome(False)` → `/ready`
fails. **`_base_url` stays rewritten on the shared singleton session, so every subsequent request in the
process resolves to `n123.meraki.com`, is stripped, and 401s** — a permanent, restart-only outage that
presents to the operator as "bad API key".

A second, redirect-free trigger for the same root cause: `RestSession._get_pages_legacy` follows
`response.links["next"]["url"]` verbatim, and `validate_base_url` accepts any absolute
`meraki.com/.ca/.cn/.in/gov-meraki.com` URL — so a `Link: rel=next` on a different host makes page 2 of
every `total_pages="all"` fetch unauthenticated.

The three tests in `tests/unit/test_697_698_api_transport.py` cover same-origin, explicit `:443`, and
`attacker.invalid` only. **There is no test for a legitimate off-host `*.meraki.com` target** — which is
why this passed.

**Fix.** Replace the single-origin equality test with the same Meraki-owned-domain allowlist the SDK
itself uses (`common.validate_base_url`'s `meraki.com|meraki.ca|meraki.cn|meraki.in|gov-meraki.com`,
matched on the **host boundary** so `api.meraki.com.attacker.net` does not match). Strip `Authorization`
only for hosts outside it.

**Acceptance:** tests asserting `https://n123.meraki.com/api/v1/...` **keeps** the header and
`https://api.meraki.com.attacker.net/...` **loses** it.

---

### P1.3 [HIGH] MS org-wide port endpoints lost `serials=` scope and never re-filter — NetworkFilter bypass
**`collectors/devices/ms.py:911`, `:1452`; leaking loops at `:930`, `:1499`** · CONFIRMED (reproduced)

Commit `16e5f3b` dropped `serials=serials` from `getOrganizationSwitchPortsStatusesBySwitch`,
`getOrganizationSwitchPortsUsageHistoryByDeviceByInterval` and
`getOrganizationSwitchPortsClientsOverviewByDevice`, but the row loops still use
`device_lookup.get(serial, {})` **without skipping serials absent from the filtered device list**.

```python
device_lookup = {device.get("serial"): device for device in devices}
...
for switch in switches:
    serial = switch.get("serial")
    if not serial: continue
    device_info = device_lookup.get(serial, {})   # <- no skip when absent
```

**Failure scenario.** Org has 500 switches across 50 networks; `MERAKI_EXPORTER_NETWORK_FILTER__*`
narrows the exporter to 2 networks / 20 switches. `inventory.get_devices()` returns 20, but the org
endpoint returns all 500. Result: `meraki_ms_port_status`, `_port_info`, `_port_errors/warnings`,
`_port_stp/8021x`, `_port_neighbor_present`, `_port_traffic_bytes_per_second`, `_port_usage_bytes`,
`_port_client_count`, `meraki_ms_poe_port_energy_joules`, `_poe_total_energy_joules` and
`meraki_ms_power_usage_watts` are **all emitted for the 480 excluded switches, labelled with their real
`network_id`**. ~25× the intended series across ~11 families, all inside the single `DeviceCollector`
cardinality bucket — so it can trip `cardinality.max_series_per_family` and evict legitimate series.
API cost rises correspondingly (`perPage=20`, `total_pages="all"` now paginates the whole org).

Two independent signals this was meant to be filtered: the docstring at `ms.py:1413-1414` still says the
`devices` list is *"used to scope the org query via `serials=`"*, and the covering test at
`tests/unit/collectors/test_ms_collector.py:1325` says *"The org-wide endpoint cannot accept unbounded
serial filters; **filter the response locally**"* — then only asserts `"serials" not in kwargs`.
**The local filter was never written.**

**Fix.** All three SDK methods accept `networkIds` (verified in installed meraki 4.4.0) — pass
`networkIds=sorted(await self.parent.inventory.get_allowed_network_ids(org_id))`, exactly as
`organization.py::_collect_device_counts_by_model` already does. That is bounded by network count rather
than serial count, which is the problem `16e5f3b` was solving. Additionally add the belt-and-braces
guard `if serial not in device_lookup: continue`, which is what the test comment claims exists.

**Acceptance:** a test with a device list narrower than the org response asserting no metric is emitted
for the excluded serials. Update the misleading test comment at `test_ms_collector.py:1325`.

---

### P1.4 [HIGH] A startup config error kills the collector task but leaves `/health` returning 200 forever
**`app.py:526` (task creation), `:570`, `:612` (re-raises)** · CONFIRMED

`_startup_collections()` is fire-and-forget; the new `except StartupConfigurationError: raise` clauses
propagate into a task nobody awaits.

**Failure scenario.** `network_filter` matches nothing *and* the Meraki API is transiently failing when
`lifespan` runs `validate_startup_configuration()` (`manager.py:434-441` swallows non-Startup errors
there by design). Lifespan yields, uvicorn binds. The background task then reaches
`_validate_network_filter()` (`manager.py:746`) → `StartupConfigurationError`. Line 570 re-raises; the
task dies **before line 578 starts any `_collector_loop`**. Nothing awaits `startup_task`, and
`add_done_callback(self._background_tasks.discard)` never retrieves the exception — the only trace is
asyncio's "Task exception was never retrieved" at GC. Because no collector ever *attempted* a run,
`manager.has_attempted_collection()` stays `False`, so `_liveness_check` returns `(False, "starting up")`
**forever** and `/health` serves 200 indefinitely. `/ready` stays 503, so under the shipped chart the
pod sits NotReady and is **never restarted**. `_log_startup_summary()` is also skipped.

`tests/unit/test_app_scheduler.py:205-222` awaits `_startup_collections()` *directly*, proving the
coroutine raises — not that the process aborts. No test drives this through `lifespan`.

**Fix.** Give `startup_task` a done-callback that inspects the exception and, on
`StartupConfigurationError`, signals process exit (SIGTERM, or a fatal flag `_liveness_check` honours);
or move the check so it can only fire pre-yield. At minimum, `_liveness_check` must not report
"starting up" indefinitely once the startup task has terminated.

**Acceptance:** a test driving the failure through the real `lifespan` and asserting the process
terminates (or `/health` goes unhealthy) rather than serving 200 forever.

---

### P1.5 [HIGH] The over-budget startup gate aborts the process, and the remedy it prints is a no-op
**`collectors/manager.py:615-640`, `core/scheduler.py:429-433`** (abort path `app.py:485-489`) · CONFIRMED (reproduced)

`validate_profile_selection()` raises `RuntimeError` when `profile` is unset and the solved *standard*
plan exceeds budget — but the check only tests **whether a profile was named**, not whether the chosen
one fits.

```python
def requires_explicit_profile(self) -> bool:
    return self.configured_profile() is None and self._profile_threshold_demand_rps > (
        (self._budget_used_at_last_solve or 0.0) * float(self._sched("target_utilization"))
    )
```

**Failure scenario.** A fleet whose solved standard demand is 6.70 rps against a 5.60 rps target
(default 10 rps × 0.8 shared × 0.7 utilization). v1.0.2 started and logged an over-budget warning. This
build raises from `lifespan` before `yield` → `_shutdown()` → uvicorn aborts → **the container
crash-loops**. The operator reads *"Choose availability, standard, or full"*, sets `standard`, and gets:
```
profile=None        requires_explicit=True   over_budget=True  demand=6.701 solved=39 shed=['clients_list','device_memory']
profile='standard'  requires_explicit=False  over_budget=True  demand=6.701 solved=39 shed=['clients_list','device_memory']
```
Identical solve, identical shed set, identical demand — **the gate blocked a plan and then accepted the
same plan.** `PROFILE=full` (strictly more demand) also satisfies it.

**Fix — pick one.** (a) Make the gate assert the *selected* profile's solved demand fits the target,
rejecting `standard`/`full` when they do not and pointing at `availability`. (b) Downgrade the check to
a loud startup WARNING plus the existing `meraki_exporter_scheduler_over_budget` gauge rather than a
hard abort. **Recommended: (b)** — a hard abort that a no-op remedy satisfies provides no safety, and
crash-looping an exporter is worse than running it over budget. If you keep the abort, (a) is mandatory.

---

### P1.6 [HIGH] `max_concurrent_collectors` silently overridden — stock default drops 5 → 2, and queueing is booked as failure
**`collectors/manager.py:38-51`, applied at `:110-112`** · CONFIRMED — *found independently by two agents*

```python
configured = int(settings.collectors.max_concurrent_collectors)   # 5
executor_workers = int(settings.api.executor_workers)             # 10
fanout = int(settings.api.concurrency_limit)                      # 5
executor_capacity = max(1, executor_workers // fanout)            # 2
return min(configured, executor_capacity)                         # 2
```

The reduction is **never logged**, and `config_models.py:901-913` still documents
`max_concurrent_collectors` as *"Max number of collectors … concurrently, GLOBALLY"* with default 5.
Worse, `concurrency_limit` is operator-tunable to 20: `10 // 20 = 0 → max(1,0) = 1` — **one collector at
a time globally**.

**Failure scenario.** `_admit_collector` bounds the queue wait at `collector_timeout` (240s) and books
an expiry as a *collector failure* via `_record_pre_start_failure` (`:883-893`) — incrementing
`total_runs`, `failure_streak` **and** `total_failures`, and raising
`meraki_exporter_collection_errors_total{error_type="TaskExpiredBeforeStartError"}`. On a large fleet
where one collector run takes ~200s, 8 collectors on ~300s floors need ~1600s of work per cycle against
2×300s of capacity — permanent saturation. Collectors that never reach `mark_ran` keep `/ready` red;
`_liveness_check` eventually flips `/health` to 503 → pod restarts → same saturation. Raising
`max_concurrent_collectors` has no effect unless `api.executor_workers` is raised too, and nothing tells
the operator. `_collector_loop` (`app.py:662`) calls `run_collector_once` on every wake regardless of
due-ness, so the queue is deeper than the number of actually-due collectors.

**Fix.** Log a WARNING when the derived cap is below the configured value, naming both inputs; and
either raise the default `executor_workers` so the stock combination still yields 5, or validate the
three knobs together in `_validate_static_startup_configuration`. Separately, stop counting
`TaskExpiredBeforeStartError` toward `failure_streak` — it describes exporter saturation, not collector
health — or give admission its own shorter deadline so queue pressure is distinguishable.

**Acceptance:** a test asserting the derived limit for the *shipped* defaults and that a WARNING fires
when it differs from the configured value. The existing parametrised case `(5, 5, 10, 2)` asserts the
value but not the contradiction.

---

### P1.7 [HIGH] `force=True` at startup bypasses both the profile filter and the over-budget shed set
**`collectors/manager.py:602`, `core/collector.py:569-576`** · CONFIRMED (reproduced) — *found independently by two agents*

```python
if getattr(self, "_force_run", False):
    return True                                   # collector.py:569-570 — returns before...
...
if profile_allows is not None and not profile_allows(group):
    return False                                  # ...this is ever reached
```
`collect_initial()` was changed this release to `run_collector_once(collector, force=True)` (was
unforced at v1.0.2).

**Failure scenario.** Default profile, over-budget fleet. At process start the exporter fetches **all 79
groups** — the 40 the standard profile excludes plus the groups the shedder deferred — then never
fetches them again. Those series appear in `/metrics`, are expired by `MetricExpirationManager` ~two
intervals later, and reappear on the next restart. **Recording rules and `absent_over_time()` alerts
flap on every deploy**, and the unbudgeted burst lands exactly when `warm_cache`/discovery are already
competing for the rate-limit budget. The same bypass applies to `POST /api/collectors/trigger`
(`app.py:1220`).

**Fix.** Move the `profile_allows()`/`is_shed()` test **above** the `_force_run` short-circuit. Force
should defeat the *due-ness* gate (what #631 intended), never the *affordability* gate. Make the manual
trigger behave the same, or give it a separate explicit opt-in flag.

**Acceptance:** a test covering `collect_initial` against a profile-excluded and a shed group —
currently `grep force=True tests/` only finds the manual-trigger tests.

---

## P2 — REAL BUGS THAT SHOULD NOT SHIP SILENTLY

### P2.1 [MEDIUM] `facade_for()` silently resolves no rate limiter for three owners — those calls are unpaced
**`core/api_facade.py:142-147`** · CONFIRMED — *found independently by two agents, same root cause*

```python
parent = getattr(owner, "parent", None)
limiter = getattr(owner, "rate_limiter", None) or getattr(parent, "rate_limiter", None)
```
The lookup walks exactly one level. Three owners fail it:
- **`APIHelper`** (`core/api_helpers.py:30-41`) stores its collector as `self.collector`, not `parent`,
  and defines no `rate_limiter`. All four migrated call sites lost the pacing the deleted
  `_acquire_rate_limit()` provided.
- **`MXFirewallCollector`** (14 call sites at `mx_firewall.py:281,316,397,430,473,545,564,583,641,670,731`)
  and **`MXVpnCollector`** (`mx_vpn.py:145,302,388`) sit two levels below the owning `MetricCollector`:
  their `parent` is `MXCollector`, a `BaseDeviceCollector` which sets only `parent`/`api`/`settings`.

Probe result: `facade_for(MXCollector-like) limiter: <FakeLimiter>` but
`facade_for(MXFirewall-like) limiter: None`.

**Failure scenario.** An org with 300 appliance networks runs `MXFirewallCollector.collect_for_network`
per network: L3, L7, content filtering, malware, intrusion, port-forwarding, 1:1 NAT, 1:many NAT, VLANs,
static routes ≈ 10 calls/network ≈ **3000 requests fired with zero token-bucket pacing**, gated only by
`ManagedTaskGroup(max_concurrency=api.concurrency_limit)`. Meraki returns 429s; the facade retries them
itself, so the collector burns its 240s budget in backoff and the AIMD feedback throttles everything
else.

The MX case is **not a regression** — the previous pacing owner had the identical one-level lookup — but
the facade commit's stated contract is *"every attempt is paced and metered"*, and these are the only
places it silently isn't. Ship the facade as the single pacing seam or don't.

**Fix.** Make `facade_for` walk the `parent` chain until it finds a limiter (and also consult
`owner.collector` for `APIHelper`); or, cleaner, have `BaseDeviceCollector.__init__` set
`self.rate_limiter = getattr(parent, "rate_limiter", None)` so any depth resolves in one hop. Make an
unresolvable limiter **loud** (warn once) rather than silently unpaced.

**Acceptance:** a test asserting every `facade_for` owner in the tree resolves a non-`None` limiter.

---

### P2.2 [MEDIUM] Facade 429 backoff dropped jitter and cut the base delay 10× — synchronized retry storms
**`core/api_facade.py:117-119`** · CONFIRMED

```python
await asyncio.sleep(retry_after if retry_after is not None else min(2**attempt, 60))
```
The path it replaced applied `_apply_jitter(delay, 0.2)` with `base_delay=10.0`.

**Failure scenario.** `concurrency_limit=5` fan-out, up to 10 SDK threads in flight. Meraki 429s all of
them at `t=0` with `Retry-After: 1`. Every coroutine computes the identical `1.000s` sleep, so all wake
in the same event-loop tick and re-fire together against a bucket that has refilled ~8 tokens — another
synchronized volley. Three lockstep rounds complete in ~7s (previously ~70s, spread ±20%), so the
exporter delivers ~4× the retry pressure to an already-throttled org, while `record_throttle_event`'s
30s cooldown permits only one AIMD halving across the whole burst.

`_apply_jitter` (`error_handling.py:780`) is documented *"to avoid thundering herd effects"* and is now
bypassed for every SDK-originated 429.

**Fix.** Apply `_apply_jitter()` to the facade's sleep (already importable from `error_handling`) and
raise the no-`Retry-After` floor toward the previous `base_delay`, so both owners agree on backoff shape.

---

### P2.3 [MEDIUM] Two `close()` paths block the event loop during shutdown
CONFIRMED — *same pattern, two independent sites*

**(a) `api/client.py:349`** — `AsyncMerakiClient.close()` is `async` but calls the synchronous,
thread-joining `self._executor.shutdown(wait=True, ...)` directly on the loop thread (was `wait=False`
before this diff).

**Failure scenario.** SIGTERM mid-cycle while `getOrganizationDevices(total_pages="all")` is on page 3
of 12. `_shutdown()` waits only 3s for task cancellation (`app.py:300-302`), and asyncio cancellation
does **not** cancel the worker thread, which keeps paging at `single_request_timeout=30s` per page.
`await self.client.close()` then blocks the loop for up to ~9 more pages × 30s. Nothing on the loop runs
— `/health`, `/metrics` and uvicorn's own graceful-shutdown machinery are all frozen — so a default 30s
`terminationGracePeriodSeconds` expires and the pod is SIGKILLed before `_serving_executor.shutdown`
ever runs.

**(b) `services/dns_resolver.py:85-90`**, called from `app.py:322-327` — a *synchronous*
`ThreadPoolExecutor.shutdown(wait=True)` invoked from the async lifespan, on a pool whose threads the
module itself documents as impossible to interrupt:
```python
# `socket.gethostbyaddr` cannot be interrupted, so when `with_timeout`
# abandons the await the underlying thread keeps running until the OS resolver returns.
```
With `dns_max_concurrent_lookups=32` (default, raised from 5 this release) and a black-holing resolver,
32 threads block for 20-40s+ each (`/etc/resolv.conf` `timeout:5 attempts:2` × N nameservers).
`cancel_futures=True` only drops *queued* work, not running joins.

**Fix.** Move both joins off the loop and bound them. For (a), `asyncio.to_thread` won't work (it needs
a *different* executor) — use `run_in_executor(self._serving_executor, functools.partial(...))` wrapped
in `asyncio.timeout`, falling back to `wait=False` on expiry. For (b),
`await asyncio.wait_for(asyncio.to_thread(resolver.close), timeout=…)`, or simply
`shutdown(wait=False, cancel_futures=True)` and let the daemon threads die with the process — the pool
already isolates the blast radius; joining it is what re-couples it to shutdown latency.

---

### P2.4 [MEDIUM] Deduplicated and stale webhook deliveries return HTTP 401 → Meraki retries forever, and one alert can be permanently lost
**`app.py:1333-1338`; `core/webhook_handler.py:484`, `:493`** · CONFIRMED

`process_webhook` returns `None` for a *successfully deduplicated* replay and for a stale delivery; the
route maps any `None` to 401 "Webhook validation failed" — telling Meraki the delivery failed.

**Failure scenario.** Meraki delivers `alertId=X`, accepted (200). Meraki retries the identical body.
The second delivery is authenticated, fresh, and matched in `_replay_cache` → `None` → **401**. Meraki
treats non-2xx as failure and retries again; every retry is a cache hit and gets 401.
`meraki_webhook_events_failed_total` does **not** move (the replay path returns before the failure
counters), so the operator sees a receiver Meraki reports as failing while `/status` reports zero
failures. With a receiver clock >300s off, *every* delivery 401s forever.

Worse: `_is_replay` inserts the cache entry **before** the device-state applier runs, so an exception in
downstream processing (caught at `webhook_handler.py:583`) returns `None` → 401 → Meraki retries → now a
cache hit → **that alert is permanently lost**.

`tests/unit/test_webhook_replay_715.py` exercises only `WebhookHandler` directly and never asserts an
HTTP status.

**Fix.** Make `process_webhook` distinguish *rejected* (401) from *idempotently dropped* (200) — a
result enum or dedicated sentinel — and answer 200 for replays. Insert the replay-cache entry only after
processing succeeds, or evict it on the exception path.

**Acceptance:** tests asserting the HTTP status for a replayed delivery (200) and for a downstream
processing failure (not a poisoned cache entry).

---

### P2.5 [MEDIUM] Over-budget guard in `collect_initial` raises bare `RuntimeError` that is swallowed
**`collectors/manager.py:584-593`; `app.py:572-573`** · CONFIRMED

The duplicate profile check inside `collect_initial` raises `RuntimeError`, not
`StartupConfigurationError`, so `_startup_collections` catches it under `except Exception` and continues
— **while also skipping the entire initial collection**.

**Failure scenario.** `validate_profile_selection` returns early when `_resolve_and_log_schedule()`
returns `False`, i.e. when `get_org_shape` throws because the API is briefly unavailable at startup
(`manager.py:628`, deliberate per D10). Lifespan yields. The background `collect_initial` then warms the
cache successfully, resolves, finds `requires_explicit_profile()` True → `RuntimeError` → `app.py:572`
logs *"Initial collection failed, continuing with tiered loops"* and starts every collector loop with the
implicit `standard` profile. Net: the exporter runs exactly the over-budget plan D6 says must be
refused, **and** performs no initial collection (the loop at line 600 is never reached), delaying first
data by a full cadence. `validate_profile_selection`'s own docstring claims this *"cannot be logged and
swallowed by the background initial-collection task"*; in this path it is.

**Fix.** Raise `StartupConfigurationError` here (and fix P1.4 so it actually aborts), or drop the
duplicate check and rely solely on the pre-yield validator, logging a warning so initial collection
still runs.

---

### P2.6 [MEDIUM] `validate_profile_selection` moves a full inventory warm onto the pre-yield critical path
**`collectors/manager.py:624`, called from `app.py:486`** · code path CONFIRMED, impact PLAUSIBLE

`await self.inventory.warm_cache()` now runs inside `lifespan` **before** `yield`, so uvicorn does not
bind and `/health` is unreachable until organizations, networks and devices have all been fetched.

**Failure scenario.** A large org with `total_pages="all"` pagination takes >120s to warm. The shipped
chart's liveness probe is `/health`, `initialDelaySeconds: 30`, `periodSeconds: 30`,
`failureThreshold: 3` ≈ 120s of grace. The container is killed mid-warm, restarts, warms again, is
killed again — a crash loop that also burns the API budget on every attempt. This is the exact hazard
the existing comment at `app.py:498-502` documents for `DiscoveryService`. Note the slow path is the
**default**: the function returns immediately when `collectors.profile` is set, so only unconfigured
deployments pay it.

**Fix.** Bound the pre-yield preflight with a short `asyncio.timeout` and treat expiry as "shape
unverifiable" (the same startup-tolerant branch already used when `_resolve_and_log_schedule()` returns
`False`), or run the profile check after yield and terminate from there.

---

### P2.7 [MEDIUM] The explicit-profile gate fires in `scheduler.mode=fixed`, where the demand figure is meaningless
**`core/scheduler.py:498`, `:500-509`, `:429-433`** · CONFIRMED (reproduced)

In fixed mode `solve_budget` is `math.inf`, so the "standard plan" solve performs no stretching and
`_profile_threshold_demand_rps` is raw floors-only demand. `requires_explicit_profile()` then compares
that unstretched number against `budget × target_utilization`:
```
mode fixed -> over_budget True  demand 19.452  target 5.6  requires_explicit_profile: True
```
An operator who sets `MERAKI_EXPORTER_SCHEDULER__MODE=fixed` — deliberately opting out of budget-driven
interval fitting — cannot start the process.

**Fix.** Return `False` from `requires_explicit_profile()` when `mode != "adaptive"`, mirroring
`needs_resolve()` at `:759-761`, which already guards on mode.

---

### P2.8 [MEDIUM] One `run_collector_once` can occupy up to 2 × `collector_timeout`
**`collectors/manager.py:842-843` and `:921-922`** · CONFIRMED

The same `timeout` value bounds both the admission wait and the execution, so worst case is
`collector_timeout` queued **plus** `collector_timeout` executing — 480s at defaults. Operators sizing
`collector_timeout` against a group interval (the documented purpose, `config_models.py:895-899`) get
half the cadence headroom they configured, and `_collection_utilization` (`:962-967`, computed from
execution time only) does not show the queued half. The docstring at `:376-382` still says *"Run a
single collector once with the configured timeout"*.

**Fix.** Derive one wall-clock budget for the whole call — take the deadline once and pass the remaining
time into `_execute_admitted_collector` — or give admission its own, much smaller, dedicated knob.

---

### P2.9 [MEDIUM] Org-wide 5xx no longer suppresses sibling collector domains
**`core/org_health.py:247-277`, escalation at `:228-245`** · CONFIRMED

When `source` is supplied, `should_collect` consults only that source's deadline and `SOURCE_GLOBAL`,
ignoring the aggregate `backoff_until`. Escalation to `SOURCE_GLOBAL` happens only for `API_AUTH_ERROR`,
or for `CONNECTIVITY`/`TIMEOUT` once **two** domains have independently hit the threshold — so
`API_SERVER_ERROR`, `API_RATE_LIMIT`, `API_CLIENT_ERROR`, `UNKNOWN` and the categoryless call at
`organization.py:689` can **never** escalate.

**Failure scenario.** Meraki returns HTTP 500 for an org. `OrganizationCollector` records 5 consecutive
`API_SERVER_ERROR` failures under `SOURCE_ORGANIZATION`. `DeviceCollector` (`device.py:690`) and
`NetworkHealthCollector` (`network_health.py:354`) evaluate `max(their own 0.0, global 0.0) == 0.0` and
**keep polling the broken org at full cadence**. Under v1.0.2 the single aggregate `backoff_until`
suppressed all three. The module docstring at `:10-16` no longer describes the code, and the inline
comment at `:269-272` says *"The organization source is reserved for an org-wide verdict"* while the
code reads `SOURCE_GLOBAL`.

**Fix.** Either widen escalation to any repeated non-`API_NOT_AVAILABLE` category once a single domain
crosses the threshold, or keep the aggregate `backoff_until` as an additional term in the sourced
branch. Update the module docstring either way.

---

### P2.10 [MEDIUM] `org_api_usage` is marked failed forever when only the optional enrichment fails
**`collectors/organization_collectors/api_usage.py:346`** · mechanism CONFIRMED

`_mark_group_ran(ORG_API_USAGE)` moved from immediately after the cheap primary overview fetch to behind
`if bulk_complete:`, so a failure of the explicitly best-effort `getOrganizationApiRequests` enrichment
leaves the group admitted-but-unmarked — which the new end-of-run accounting in `core/collector.py:233`
converts into a scheduler group failure **every cycle**.

**Failure scenario.** A busy org where `getOrganizationApiRequests` (now `perPage=1000`,
`total_pages="all"`, up to 36 pages) exceeds `api.per_fetch_deadline_seconds` (120s). Status-code
metrics are emitted fine, but: (a)
`meraki_exporter_scheduler_group_failures_total{group="org_api_usage"}` increments forever; (b) the
group's success timestamp freezes, so the shipped `MerakiExporterSchedulerGroupStale` alert
(`grafana/alerts/alerting-rules.yaml:164`) **fires permanently against a group whose primary metrics are
fresh**; (c) `should_run` falls back to `failure_retry_seconds` (300s) instead of the solved interval, so
on an org whose `org_api_usage` was stretched to e.g. 1800s the doomed multi-minute fetch is re-attempted
6× more often — and because `asyncio.timeout` cannot cancel the SDK executor thread, those pages are
still requested against the rate-limit budget. The code's own two verdicts contradict each other: the org
is reported healthy, the group is reported failed.

**Fix.** Mark the group ran on primary-overview success and track the enrichment separately — its own
endpoint group, or an explicit partial-success signal that does not feed `mark_failed`.

---

### P2.11 [MEDIUM] MS DHCP-security and link-aggregation fan-outs lost their org-keyed rate-limit bucket
**`collectors/devices/ms.py:2264`, `:2315`, `:2418`** · CONFIRMED (reproduced)

The sweep removed the explicit `await rate_limiter.acquire(org_id, "<op>")` from these three per-network
fetches. The facade recovers the org key from `structlog` contextvars, but the enclosing
`with LogContext(org_id=org_id)` block closes before the fan-out — and `LogContext.__exit__` **unbinds**
rather than restores, so it also wipes the outer `device.py:790` binding. `_resolve_org_id` returns
`None` and `OrgRateLimiter.acquire` uses `key = org_id or "global"` — a **separate token bucket**.
```
outer bound: {'org_id': '123456'}   after inner exit: {}   resolved org for facade call: None
```
**The same commit explicitly fixed the sibling site**: `ms.py:1748` was changed to
`LogContext(org_id=org_id, network_id=network_id)` precisely so the facade could key the limiter.
`:2263`, `:2314` and `:2417` were left behind.

**Failure scenario.** A 200-network org runs `MS_DHCP_SECURITY` + `MS_LINK_AGGREGATIONS`: 600 calls paced
against the `"global"` bucket while everything else paces against the org bucket. Both refill at
`effective_rate_per_second()`, so combined outbound rate approaches **2×** the configured limit against
a single org whose Meraki ceiling is 10 rps → 429 storms and AIMD backoff that then throttles everything
else. Secondary: `meraki_exporter_rate_limiter_*{org_id="global"}` series appear, breaking per-org
attribution.

**Fix.** Add `org_id=org_id` to the three inner `LogContext(...)` calls, matching the STP site. Longer
term: `LogContext.__exit__` should reset to the previous value rather than unbind, and
`_resolve_org_id`'s `len(candidate) == 18` heuristic should be dropped — an 18-character Meraki *network*
ID would be silently keyed as an org.

---

### P2.12 [MEDIUM] `meraki_exporter_cardinality_self_series` can go negative
**`core/cardinality.py:425-441` (walk 1) and `:492-503` (walk 2)** · CONFIRMED (reproduced)

`product_series`/`exporter_series` are counted in one `registry.collect()` pass, `exposed_series` in a
second pass taken later, and `self_series` is the **difference** — so every series added or removed
between the passes is charged to the monitor's own bucket.

**Failure scenario.** `analyze_cardinality` runs on `_serving_executor` (`app.py:736-738`) while
collectors mutate the registry on the event loop, with no coordination. Walk 2 is itself a full
O(series) walk, so the gap is the entire duration of walk 2. On a 50k-series fleet,
`MetricExpirationManager._remove_series` expires 200 departed-device series during that window →
`self_series = 9 − 200 = −191`. A "number of time series" gauge goes negative; any alert or panel on it
breaks. The reverse case silently inflates `self_series`. Reproduced: `product = 60  exporter = 0
self = -43  exposed = 17`.

**Fix.** Take **one** snapshot — materialise `list(self.registry.collect())` once and compute all four
buckets from it, classifying the monitor's own families into `self_series` rather than inferring them.
That also halves the analysis cost, which matters since it was explicitly offloaded for being expensive.

---

### P2.13 [MEDIUM] Cardinality drill-down pages contradict their own new subtitles
**`templates/cardinality_all_metrics.html:264`, `cardinality_all_labels.html:286`; source `core/cardinality.py:431-441`, `:830-849`, `:851-894`** · CONFIRMED

`#726` split the *counters* into product/exporter buckets but left `_analyze_metric` running **before**
the split, so `_full_metric_data` — the sole source for both drill-down pages — still holds every
non-monitor family, while the page copy now asserts those families are excluded.

**Failure scenario.** An operator opens `/cardinality/all-metrics`, reads *"Product-data metrics only;
exporter and CardinalityMonitor self-instrumentation are excluded"*, and sees
`meraki_exporter_api_requests_total`, `meraki_exporter_collector_duration_seconds`,
`python_gc_objects_collected_total`, `process_cpu_seconds_total` listed as product data.
`/cardinality/all-labels` likewise attributes exporter-only labels (`endpoint`, `method`, `status_code`,
`collector`, `group`, `phase`) to product metrics. The two pages also disagree on the count:
`/cardinality` shows product-only, `/cardinality/all-metrics` shows everything, with no explanation.

**Fix.** Classify before storing (record exporter families separately, or tag each entry with its bucket
and filter in `get_all_metrics`/`get_all_labels`), or revert the two subtitles. Either way, make
`/cardinality`'s `total_metrics` and `/cardinality/all-metrics`'s count the same population.

---

### P2.14 [MEDIUM] Client IP and client ID escape into INFO/WARNING/ERROR logs, outside the DEBUG-only caveat the privacy doc promises
**`services/dns_resolver.py:120-126` (INFO), `:299-304` → `core/async_utils.py:508-516` (WARNING/ERROR); MAC at DEBUG in `collectors/clients.py:1107-1115`** · CONFIRMED (behaviour pre-dates `2d73c8d`)

`docs/privacy.md:104-105` bounds identifier logging to DEBUG, but:
```python
logger.info("Client IP changed, invalidating DNS cache", client_id=client_id, old_ip=old_ip, new_ip=ip)
```
```python
operation=f"DNS lookup for {ip}"   # interpolated into WARNING and ERROR text by with_timeout
```

**Failure scenario.** An operator follows the documented mitigation and runs at `INFO` to keep client
data out of the log pipeline. DHCP lease churn then produces one INFO line per lease change carrying a
`client_id`/`old_ip`/`new_ip` triple; a slow resolver produces `Timeout during DNS lookup for
10.4.7.219` at **WARNING**, one line per client IP per cycle, and a non-`OSError` failure produces the
same string at **ERROR** with a traceback. All land in whatever ships container stdout — exactly the
surface the doc told the operator they had controlled. Separately the MAC is logged at DEBUG, which the
doc's caveat does not mention at all.

**Fix.** Pass a non-identifying `operation` label to `with_timeout` (e.g. `"reverse DNS lookup"`, with
the IP only in a DEBUG structured field), and demote the IP-change line to DEBUG or drop
`old_ip`/`new_ip`. If MAC-at-DEBUG is intended, state it in `docs/privacy.md` alongside the IP/hostname
caveat.

---

### P2.15 [MEDIUM] Three agent-contract docs are now false, and one of them causes a silent failure
CONFIRMED

**(a) `.github/CLAUDE.md:25-29`, `:86`, `:112`** state *"release-please uses a PAT … **NEVER revert to
`GITHUB_TOKEN`**"*. `0f9c03c` and `bc8c1a9` removed that PAT entirely; the token is broker-minted.
During a broker outage, an operator or agent debugging the failed mint reads a rule labelled **NEVER**
telling them the PAT is required, and restores `secrets.RELEASE_PLEASE_TOKEN` — reintroducing exactly
the cross-repo-scoped credential `0f9c03c` removed. A privilege regression reached by following the
documentation correctly.

**(b) `.github/CLAUDE.md:38-51`, `:91`, `:115`** describe a Claude Code Action call site in
`report-drift/action.yml` taking `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN`, with a "never remove the
untrusted-data framing" FATAL rule. **That step does not exist** —
`grep -rniE "anthropic|claude" .github/` matches only `.github/CLAUDE.md` itself. `:58` likewise still
describes `trigger-docs-sync.yml` as firing on `zensical.toml` with `secrets.DOCS_SYNC_PAT`.

**(c) `docs/CLAUDE.md:2,13,14,20,29,31,49,56`** — the actively harmful one. `57fea59` deleted
`zensical.toml` (285 lines) and inverted the docs model; `76e6147` then added `/zensical.toml` to
`.gitignore`. The doc still says *"Site nav is defined in `zensical.toml`'s `[project] nav` array …
Adding a new page requires adding it there too, or it won't appear in navigation."* An agent that
follows this creates `zensical.toml`, runs `git add zensical.toml`, and the add is a **silent no-op** —
no error, nothing staged. The commit lands with the page but no nav entry, and the page is unreachable.
The repo now ships `docs.toml` with a different `[[site.nav]]` schema.

**Fix.** Rewrite (a) and (b) for the broker flow — if the untrusted-data framing rule is worth keeping,
restate it as policy for *future* LLM call sites rather than a description of an existing one. Point (c)
at `docs.toml` and its `[[site.nav]]` schema, and record that the repo can no longer build the site
standalone.

---

### P2.16 [MEDIUM] `broker-token` pins carry no version comment and have diverged onto two SHAs
**`release-please.yml:35` + `release-please-lock.yml:108` (`@b9ab5f80…`); `trigger-docs-sync.yml:40` (`@1cd0af4c…`)** · CONFIRMED

`.github/CLAUDE.md:13-16` requires every third-party `uses:` pinned to a 40-char SHA **with a trailing
`# vX.Y.Z` comment**; the paved path (line 104) says *"don't introduce a second, different pin"*. All
three `broker-token` refs carry a bare SHA with no version comment — the only such refs in the repo,
which now carries four distinct `rknightion/.github` revisions.

**Failure scenario.** `a148a86` is the proof-of-mechanism: the action changed behaviour (stopped
defaulting the JWT role to the permission-set name), docs-sync began failing login with HTTP 400 *"role
does not exist"*, and the fix required **both** the bump to `1cd0af4` **and** an explicit `role:` input.
The two release lanes were left on `b9ab5f8`. When the next upstream change lands,
`release-please.yml`'s mint step fails the same way — and because `edge`'s guard is
`if: !cancelled() && needs.release-please.outputs.release_created != 'true'` (`release-please.yml:98`),
a failed mint yields an empty `release_created`, so **`:main` edge images keep publishing indefinitely
while no release is ever cut**, and nothing goes red in a way anyone watches.

zizmor passing does not refute this: its `unpinned-uses` audit is satisfied by any hash pin, whereas the
version comment is the repo-specific requirement that lets Renovate resolve a `currentValue`. Renovate
bumped five other actions between 2026-08-05 and 08-15; both `broker-token` pins sat untouched.

**Fix.** Converge all three sites on one revision (`1cd0af4`, known to support explicit `role:`), append
matching `# vX.Y.Z` comments, and either confirm the release lanes work with the role defaulted or pass
`role:` explicitly there too.

---

## P3 — LOWER SEVERITY (fix opportunistically; state anything you defer)

| ID | Severity | Location | Issue |
|---|---|---|---|
| P3.1 | LOW-MED | `release-please-lock.yml:83-125`, `release-please.yml:14-46`, `trigger-docs-sync.yml:24-56` | harden-runner is on the job holding **no** secret (`relock`) and absent from `push-lockfile`, which mints a `contents:write` App token and runs three external actions while it is live. `trigger-docs-sync` is worse — its token is `contents:write` on a *different* repo. Audit-only mode caps severity, but the audit trail is the whole point. |
| P3.2 | LOW | `core/api_facade.py:130-139` | `meraki_exporter_api_retry_attempts_total` is now permanently **zero** — the facade took over 429 retries but never calls `_track_retry`. Separately `meraki_exporter_api_requests_total` gets `method="unknown"` and a `status_code` holding an exception class name; a `DataValidationError` on a real HTTP 200 is not counted by `get_successful_api_requests()`, the `/ready` gate. |
| P3.3 | LOW | `core/error_handling.py:479-484`, `:674` | Widening the not-available heuristic to `"402" in error_msg` roughly doubles the substring surface: a pydantic `ValidationError` whose text contains a serial like `Q2QN-4025-XXXX` is downgraded to DEBUG and mis-tracked as `API_NOT_AVAILABLE`, masking a parsing regression. Anchor it (`re.search(r"\b(402\|404)\b", …)`). |
| P3.4 | LOW | `collectors/devices/ms_stack.py:245` | `if any(successful_fetches)` is `False` for an **empty** list, so an org with no switch networks books a group failure every cycle. Use `if not successful_fetches or any(successful_fetches):`, or hoist the computation above `_should_run_group` as `network_health.py:472` does. |
| P3.5 | LOW | `core/collector.py:231-233`, `core/scheduler.py:709-720` | Success-path `mark_failed()` books a failure for any group that opened its gate then took an early return before `_mark_group_ran()` — e.g. `InsightCollector` when `get_organizations()` returns `[]`. Counter-only impact. |
| P3.6 | LOW | `services/dns_resolver.py:295-308` | `..._lookups_timeout_total` counts every non-`OSError` failure as a timeout, because `with_timeout` returns the same sentinel for `TimeoutError` and any `Exception`. A `RuntimeError: cannot schedule new futures after shutdown` is booked as a resolver timeout. |
| P3.7 | LOW | `services/dns_resolver.py:383`, `:389-399` | `..._dns_queue_depth` saturates at `maxsize` (32) by construction — 25,000 queued clients and 32 report the same value — and concurrent `resolve_multiple` calls (up to 20 networks) race to reset the shared peak. The real backlog (the executor's unbounded queue) is not measured. |
| P3.8 | LOW | `core/cardinality.py:32-41` vs `:235-253` | `_CARDINALITY_SELF_METRIC_NAMES` hardcodes three metric-name literals (rule violation), one of which must stay in sync with a Counter registered under a *different* literal via prometheus_client's implicit `_total` stripping. `test_726_cardinality_buckets.py` only asserts `self_series > 0`, so a desync passes. |
| P3.9 | LOW | `core/otel_data_logs.py:97-103`, applied `:312-319` | The MAC scrubber's bare 12-hex alternative is applied to **every** string attribute and the whole body, so `network.name = "Store 0123456789ab"` or a 12-digit ID becomes `[redacted-mac]` — silent, irreversible correlation loss. Restrict the bare form to MAC-plausible keys, or emit a `data.redacted=true` marker. |
| P3.10 | LOW | `app.py:913-918` | A non-ASCII `Authorization` header makes `hmac.compare_digest` raise `TypeError` → **HTTP 500 + traceback** from an unauthenticated request. Fails closed, so robustness not bypass. Compare bytes, or guard with `provided.isascii()`. |
| P3.11 | LOW | `app.py:394-401` | `_check_api_token` tests emptiness on `expected.strip()` but compares the **unstripped** value, so a token from `$(cat /run/secrets/token)` with a trailing newline is "configured" yet can never match — both control endpoints 401 permanently while the UI renders the controls as enabled. Make `normalize_blank_api_token` return the stripped `SecretStr`. |
| P3.12 | LOW | `core/webhook_handler.py:406-409`, `models/webhook.py:63` | A timezone-naive `sentAt` is interpreted in the host's local timezone, so `TZ=America/New_York` + a non-`Z` timestamp makes every delivery 4-5h "stale" → per P2.4, retried forever. Type it `AwareDatetime` or coerce to UTC in a validator. |
| P3.13 | LOW | `.github/workflows/api-drift.yml:34` | The only `uv sync` without `--locked`. The daily drift lane can execute against a different `pydantic`/`meraki` set than CI pinned, so a hard-failing conformance finding may not reproduce locally. |
| P3.14 | LOW | `pyproject.toml:48` | `zensical>=0.0.14` is dead — `57fea59` removed standalone site builds, no Makefile target, no importer. Every `uv sync` installs it; it stays in `dependency-review` and Renovate scope. |
| P3.15 | LOW | `charts/.../templates/_validation.tpl:20` | `default 120` duplicates `APISettings.per_fetch_deadline_seconds` but sits **outside** the `generate_helm_config.py` generated markers. If the schema default rises to 180, the guard passes a config that SIGKILLs mid-fetch. Today's `terminationGracePeriodSeconds: 150` sits exactly on the `120+30` boundary — no slack. No test covers it. |
| P3.16 | LOW | `docs/changelog.md` (1.1.0) | *"isolate release lock workflow secret"* is listed twice. `26505fd` is the **merge commit** for PR #680 whose body repeats the branch commit's `fix:` subject, so release-please counted it twice. Cosmetic here — but a merge body reading `feat!:` or `BREAKING CHANGE:` would count toward the **version decision**. Prefer squash-merge, or clear merge bodies. |
| P3.17 | LOW | `core/webhook_handler.py:395-427` | **Docs-only.** Replay protection dedupes byte-identical retries; since Meraki's shared secret travels *inside* the body, anyone able to replay also holds the secret and can mutate `alertId` for a fresh key. Memory *is* bounded and future-dating *is* rejected — no code defect. Describe it in `docs/security.md` as **delivery deduplication**, not an anti-replay security control. |

---

## RELEASE NOTES — UPGRADE-BREAKING CHANGES THAT ARE CURRENTLY UNDOCUMENTED

No commit in this release carries a `!` marker or a `BREAKING CHANGE:` footer, so release-please
computed a **minor** bump. The following are behaviour or startup-compatibility breaks that users will
hit on upgrade. `docs/upgrading.md` claims *"three deterministic configuration refusals"* — **there are
at least six.** Decide for each whether it is intended; document every one you keep.

| # | Change | Location | Documented? |
|---|---|---|---|
| 1 | `meraki.api_base_url` with a **non-HTTPS** scheme now raises. `http://` was explicitly permitted in v1.0.2. Breaks local mock/proxy setups. | `config_models.py:1101` | **No** |
| 2 | `meraki.api_base_url` outside `KNOWN_REGION_BASE_URLS` now raises unless `allow_custom_api_base_url=true`. v1.0.2 accepted with a warning (CFG-15: *"custom proxies and future regions must keep working"*). **Breaks every corporate-proxy / egress-gateway deployment.** | `config_models.py:1121` | **No** |
| 3 | `collectors.collector_timeout` in the still-valid 30-119 range now raises, compared against the new `per_fetch_deadline_seconds` (120). | `manager.py:454-460` | Yes |
| 4 | All collectors disabled now raises — which makes a **webhook-receiver-only deployment impossible**, since `WebhookHandler` is independent of collectors. | `manager.py:445-451` | Partly — the webhook consequence is not |
| 5 | An active `network_filter` resolving to zero networks now aborts (was a swallowed `RuntimeError`). | `manager.py:746` | Yes |
| 6 | Any fleet whose solved `standard` plan exceeds budget, with `profile` unset, now **exits** (was a warning). Because `solve_intervals` refuses to stretch priority-1/2 groups at all, a fleet whose priority-1/2 floor demand alone exceeds budget is *guaranteed* to hit this. See P1.5 — the printed remedy is a no-op. | `manager.py:615-641` | **No** |
| 7 | `api.rate_limit_burst` default **20 → 10**. | `config_models.py:195` | **No** |
| 8 | `collectors.max_concurrent_collectors` is now advisory, silently capped to **2** at shipped defaults (was 5). Field description still presents it as authoritative. See P1.6. | `manager.py:38-51` | **No** |
| 9 | Control endpoints fail closed — `POST /api/collectors/trigger` and `/api/clients/clear-dns-cache` now 401 unless `server.api_token` is set. | `app.py` | Yes, correctly marked BREAKING |
| 10 | **If P1.1 is resolved as option (b)**: the default profile drops 40 endpoint groups. This is the largest user-visible change in the release and must be called out prominently. | `core/scheduler.py:414-420` | **No** |

Also note for the notes, even though no name changed: **P1.3 materially changes the series population**
of eleven `meraki_ms_port_*` / `meraki_ms_poe_*` / `meraki_ms_power_usage_watts` families for any
deployment using `NetworkFilter`. Dashboard queries still match, but panel totals and `topk` results
silently include excluded networks.

**Metric surface changes** (no metric or label was renamed or removed anywhere in `collectors/`):
- `meraki_exporter_api_requests_total{endpoint,method,status_code}` — **behaviour change**. Registered
  but never incremented in v1.0.2; `core/api_facade.py:130` now populates it. `method` is hardcoded
  `"unknown"`; `status_code` is `"200"` on success but an **exception class name** on failure.
  `grafana/dashboards/self-observability.json` and `grafana/alerts/recording-rules.yaml:56`
  (`meraki:api_requests:rate5m`, commented *"by HTTP status code"*) already reference it and will start
  returning data. No alert filters on a numeric `status_code`, so nothing breaks — but the panel legend
  will show exception names alongside `200`. **No dashboard edit was made for this.**
- `meraki_exporter_api_request_attempts_total{operation,status}` — **new**, not referenced in `grafana/`.
- New: `CollectorMetricName.CLIENT_DNS_QUEUE_DEPTH`, `CLIENT_DNS_QUEUE_WAIT_SECONDS`,
  `CLIENT_DNS_LOOKUPS_TIMEOUT_TOTAL` (`collectors/clients.py`).

---

## VERIFIED SOUND — DO NOT RE-INVESTIGATE

Each of these was a hypothesis an agent actively tried to break and could not. Recorded so you don't
spend budget re-deriving them.

**Concurrency & lifecycle.** `ManagedTaskGroup.create_task` backpressure genuinely precedes allocation on
every path; `except BaseException` closes the un-started coroutine before re-raising, `finally` balances
the pending gauge, and `_on_complete` releases the semaphore exactly once including on cancelled paths.
No same-group re-entrant `create_task` exists, so the blocking acquire cannot self-deadlock. The
`asyncio.timeout` + `Semaphore.acquire()` pairing does **not** leak a permit — verified against CPython
3.14's `asyncio.timeouts.Timeout.__aexit__`. The `#695` check-then-acquire on `collector_lock` **is**
atomic (an uncontended `asyncio.Lock.acquire()` returns without suspending). `solve_intervals`'
priority-1/2 stretch exclusion terminates and has no division-by-zero. `_shutdown` is idempotent and
correctly ordered.

**API layer.** All 109 distinct SDK operations the exporter calls exist in installed meraki 4.4.0 and
resolve as `operationId`s in the vendored spec. Every private SDK attribute the new code reaches for
exists in 4.4.0. `smart_flow_enabled=False` is correctly pinned (4.4.0 defaults it to **`True`**, and the
SDK's smart-flow helpers bypass both the facade and the auth boundary — keep that flag pinned).
**Facade coverage has no holes**: all 120 `facade_for(...).call("<op>", ...)` sites have an operation
string matching the SDK method name — zero mis-pointed fetchers. The only unrouted call is
`__main__.py:70` (`--probe` CLI, one shot, no loop). 429 attempts stay bounded at `1 + max_retries`; no
retry multiplication. `#700` burst arithmetic checks out: `burst=10` with 8 rps refill yields ≤18
requests in the first second, inside Meraki's 10/s + 10-first-second envelope. **No path exposes the API
key** to a log line, exception message, span attribute, metric label, or data-log record.

**NetworkFilter.** No new `getOrganizationNetworks` call site. Exactly four remain — the inventory
enforcement point plus the three sanctioned bypasses, both fallbacks still reapplying the filter.

**Collectors sweep.** No wrong `org_id`/`network_id`/`serial` threaded into any converted call; no label
populated from the wrong variable; no new/duplicated endpoint-group names; no `floor_seconds`/`priority`
changes. The one cost-model change (`organization.py:59`, `ORG_API_USAGE` 2→37) is correctly derived.
The `on_error` signature migration covers all six call sites — no latent `TypeError`. No raw
`asyncio.gather` introduced.

**Webhooks.** The freshness test **is** symmetric (future-dated payloads are rejected). `_is_replay` uses
`time.monotonic()` for TTL while `_is_stale` uses `time.time()` — correct in each case, not a mix-up.
Cache eviction is genuinely bounded, so no memory-DoS. `validate_secret` uses `compare_digest` and now
runs **before** `model_validate` — the right order. The check cannot be skipped via missing headers,
malformed bodies, or alternate content types. The byte cap is enforced by **streaming**, not by trusting
`Content-Length`.

**Control auth.** No `except: pass` on the auth path. Two independent layers, both `compare_digest`.
`/api/webhooks/meraki` is correctly excluded from `CONTROL_POST_PATHS`, and trailing-slash /
percent-encoding evasion cannot reach an unguarded handler.

**Privacy sinks.** OTel data-log attributes and bodies, OTel span attributes, `/status`, `/cardinality`,
and all Prometheus label values in the diff are **clean** of client identifiers. `client.id` is now
omitted rather than MAC-substituted. App logs do not reach OTLP (`otel_logging.py` attaches no handler).
`/clients` and the label-value endpoints leak by design, gated behind `SENSITIVE_UI_PREFIXES` +
`server.api_token` — unchanged. One note: `_label_value_distribution` is never evicted, so MACs of
departed clients persist for the process lifetime even after `#711`'s `ClientStore._evict_network`
removes them.

**Templates.** All five are autoescaped, no `|safe`, no Jinja inside `<script>`, no dangling references
to anything the refactor deleted.

**Release plumbing.** Secret isolation in `release-please-lock.yml` genuinely works — `relock` runs the
only PR-controlled execution and holds no secret; `push-lockfile` executes nothing from the PR.
`head_ref` is correctly routed through an env var, not interpolated into the shell. The apidrift
conformance gate still gates: the new `--ignore` mechanism *downgrades* rather than drops findings, and
`spec/apidrift-ignore.txt` currently contains **only comments, zero active patterns**. `ci-success`'s
`needs:` list is complete. `76e6147` really did remove the committed hub artifacts. Chart changes are
sound and `helm-lint-kubeconform` passes. **No secrets are exposed to an LLM anywhere** — the
prompt-injection surface `.github/CLAUDE.md` warns about no longer exists.

---

## TEST GAPS TO CLOSE

Beyond the acceptance tests named inline:
- Nothing exercises the `/api/webhooks/meraki` **HTTP status** for a replayed or stale delivery.
- Nothing drives `StartupConfigurationError` through the real `lifespan` + background-task path.
- `test_config_models_validation.py` adds no coverage for `normalize_blank_api_token`, the three new
  `WebhookSettings` bounds, `collectors.profile`, or the
  `collector_timeout`/`per_fetch_deadline_seconds` relationship.
- `test_forced_admission_695.py` covers only two-concurrent-forced-runs, not the queue-deadline expiry
  path in `_admit_collector`.
- `test_698_api_facade_gate.py` only matches the literal AST shape `asyncio.to_thread(self.api…)`. It
  would miss `loop.run_in_executor(exec, self.api.x.y)`, a bare synchronous `self.api.x.y(...)` (exactly
  the `__main__.py` shape), or `fn = self.api.x.y` hoisted into a variable. Consider matching "any
  `self.api.<controller>.<method>` reference not lexically inside a `facade_for(...).call(...)` argument
  list".
- No test asserts every `facade_for` owner resolves a non-`None` rate limiter (P2.1).
- No test covers `validateShutdownGrace` or `apiPerFetchDeadlineSeconds` in the chart (P3.15).

---

## SUGGESTED SEQUENCING

1. **P0.1** — unblock CI (one line, do it now, independent of everything else).
2. **P1.1** and **P1.5** together — both are the profile/budget design; decide the policy once.
3. **P1.2** — the auth boundary; smallest blast radius to fix, highest severity if it fires.
4. **P1.3**, **P1.6**, **P1.7** — independent, parallelisable.
5. **P1.4** + **P2.5** together — same startup-error-handling seam.
6. **P2.x** in any order; **P2.1** and **P2.11** are both pacing and share a root cause worth fixing once.
7. **P3.x** and the release-notes table last, but do not skip the notes — items 1, 2, 6, 7, 8 will
   generate upgrade bug reports if they ship undocumented.
