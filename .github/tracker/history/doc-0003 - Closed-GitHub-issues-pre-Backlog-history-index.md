---
id: doc-0003
title: Closed GitHub issues (pre-Backlog history index)
type: other
created_date: '2026-08-14 16:01'
updated_date: '2026-08-17 09:03'
---
GitHub Issues was retired as this project's tracker on **2026-08-14**, after 449 closed issues. This
document is the index of that history. It is the record of *what happened*; the board
(`backlog task list --plain`) is the record of *what is left*.

## Why these were not imported as tasks

**A second ID space could never carry the numbers the history already cites.** Backlog IDs follow
creation order, so `#526` would have become some unrelated `mde-NNNN` — while 901 commits, the
per-directory `CLAUDE.md` files, code comments and the issue bodies themselves all say `#526`. Keeping
the GitHub numbers as the only ID space over this history is what keeps those citations resolvable.
420 of the 449 resolve to at least one commit, listed below.

The second reason is signal. 449 `Done` rows would drown a five-task board, and the only thing a board
is for is showing what is left. One index doc costs one file and loads on demand.

Twelve were closed **not planned** — deliberate decisions not to do something, which are the rows most
worth reading before re-proposing an idea.

## The five open issues that became tasks

These were live work when the tracker moved, so they crossed over. Their bodies were rewritten to be
self-contained on the task, since they can no longer be read on GitHub.

| was | is now |
| --- | --- |
| #717 Investigate the duration-histogram arithmetic that the code says is impossible | `mde-0001` |
| #712 Helm resource defaults sized from a measured MEDIUM fleet | `mde-0002` |
| #721 Gate merges on change-scoped scanners and publication on severity | `mde-0003` |
| #691 MV: plan migration off the deprecated camera analytics endpoints | `mde-0004` |
| #694 Tracker: v1.1 production-hardening programme | milestone `v1.1-hardening` + the *Hardening programme standing decisions* doc |

#694 became no task of its own: it was a parent whose only remaining acceptance was "children done",
which the milestone expresses. Its frozen decisions D1–D18 and its carried-forward corrections are
durable reference, so they are their own doc.

The `TODO(CFG-BIG)` residue in `app.py`, which had no issue at all, became `mde-0005`.

## How to read a row

`outcome` is GitHub's own state reason: **completed** for work that landed or was resolved,
**not planned** for a deliberate decision against it. `commits` lists every commit on every ref whose
subject or body cites `#NNN`, so a row with several commits usually means the work landed in stages,
and a row with none was closed without a code change (a decision, a duplicate, or a docs-only change
that did not cite it).

Bodies, acceptance criteria and comment threads **are not on GitHub any more.** The same 2026-08-14
migration deleted the 444 issues authored by the maintainer and by CI, after capturing all 455 issues
and 642 comments to `archive/github-issues-2026-08-14.json`, so `gh issue view <N>` 404s for the rows
below. Read them there instead:

```sh
jq '.[] | select(.number == 694)' archive/github-issues-2026-08-14.json
jq -r '.[] | select(.number == 694) | .comments[].body' archive/github-issues-2026-08-14.json
```

**The archive is redacted** — device serials, MACs, network IDs and names, organisation IDs, street
addresses, coordinates and host names are replaced by stable placeholders, one token per real value.
`archive/README.md` carries the mapping and the verification method.

Eleven issues were **not** deleted and are still readable on GitHub: the nine filed by outside
contributors, and Renovate's two dependency dashboards. They are in the archive too.

| # | closed | outcome | title | commits |
| --- | --- | --- | --- | --- |
| 726 | 2026-08-12 | completed | product_series counts exporter self-instrumentation as product data (~18% overstated) | `edf538f` |
| 725 | 2026-08-12 | completed | Control UI must not render buttons it cannot authenticate: hide them, document the API call | `16e5f3b` |
| 724 | 2026-08-12 | completed | make check must include ruff format --check: the local gate can pass where CI fails | `353ecfa` |
| 723 | 2026-08-12 | completed | Discovery bypasses the API facade: startup calls are unmetered, unpaced, and outside the #698 gate | `16e5f3b` |
| 722 | 2026-08-12 | completed | Record the extension-cost measurement for a new device family | `6d03473` |
| 720 | 2026-08-12 | completed | Docs corrections: multi-org claims, webhook variable, scaling arithmetic, endpoint reference, log format | `61e49fe` |
| 719 | 2026-08-12 | completed | Doc generators must fail loudly rather than under-report | `0410fc2` |
| 718 | 2026-08-12 | completed | Support matrix must state a verification level per device family | `15da33c` |
| 716 | 2026-08-14 | completed | Startup validation: fail fast on provably-wrong config, warn on merely-suboptimal | `75a36e2` |
| 715 | 2026-08-12 | completed | Webhook freshness window, replay dedupe, and separated delivery metrics | `26813ed` |
| 714 | 2026-08-14 | completed | Deterministic shutdown drain, and a Helm grace-versus-deadline check | `f2feb5d` |
| 713 | 2026-08-14 | completed | Disposable exporter instance with a recorded API corpus and fault-injection proxy | `ed44f79` |
| 711 | 2026-08-12 | completed | Cardinality-endpoint honesty and client-store map eviction | `349e8ed` |
| 710 | 2026-08-12 | completed | Concurrency admission: task-group back-pressure, executor alignment, queue visibility | `9e97504` |
| 709 | 2026-08-12 | completed | Bound the DNS fan-out and disclose reverse-DNS behaviour | `16e5f3b` |
| 708 | 2026-08-12 | completed | Bound client application cardinality with top-N and an other bucket | `16e5f3b` |
| 707 | 2026-08-12 | completed | Fleet fixture generator with seven named presets, tiered in CI | `fa76729` |
| 706 | 2026-08-12 | completed | Apply validate_response_format to the four fetches that bypass it | `16e5f3b` |
| 705 | 2026-08-12 | completed | Preserve error categories instead of erasing known failures into unknown | `16e5f3b` |
| 704 | 2026-08-12 | completed | Scope health backoff by domain; a 404 or 402 on an optional endpoint must never count | `16e5f3b` |
| 703 | 2026-08-12 | completed | Client child endpoint groups: register and cost only when their own flag is on | `fd5cb69` |
| 702 | 2026-08-12 | completed | Scheduler and staleness observability; document /ready as a startup gate | `16e5f3b` |
| 701 | 2026-08-12 | completed | Collection profiles and an over-budget policy that protects priority 1 and 2 | `16e5f3b` |
| 700 | 2026-08-12 | completed | Budget truth: document the per-source-IP limit and verify the burst default | `d5adf5b` |
| 699 | 2026-08-12 | completed | Call construction: perPage at maximum, cost from expected pages, drop unchunked serial filters | `16e5f3b` |
| 698 | 2026-08-12 | completed | One instrumented API facade: project AIMD owns pacing, smart flow off, every call metered | `1997aec` |
| 697 | 2026-08-12 | completed | api_base_url: HTTPS-only, allowlist by default, never carry credentials across a redirect origin | `ca8b938` |
| 696 | 2026-08-12 | completed | Never substitute a MAC for client.id, and scrub identifiers from data-log bodies | `2d73c8d` |
| 695 | 2026-08-12 | completed | Control POSTs must fail closed when no API token is configured | `40e24f8` |
| 693 | 2026-08-11 | completed | api-drift lane: acknowledge mechanism + stop re-posting an unchanged report daily | `a286fac` |
| 692 | 2026-08-11 | not planned | Decision: do not consume wlanIdentifier or campusGateway from getNetworkWirelessSsids | — |
| 690 | 2026-08-11 | completed | apidrift: detect deprecated consumed operations, and stop reporting model-extra for untyped responses | `b354e02` |
| 686 | 2026-08-11 | completed | Meraki OpenAPI drift on consumed operations | `a286fac` `b354e02` `a72e48f` |
| 669 | 2026-07-20 | completed | meraki_mr_clients_connected returns only one line instead of one per AP | `afe2562` |
| 664 | 2026-08-14 | completed | Don't promote service.version to a per-series metric label (OTLP→Prometheus: version belongs on target_info/build_info) | `ae4ea9a` |
| 661 | 2026-07-14 | completed | Dockerfile: replace manual uv tarball checksums with digest-pinned ghcr.io/astral-sh/uv | `8bacd50` |
| 657 | 2026-07-12 | completed | Meraki OpenAPI drift on consumed operations | `5626b3e` |
| 648 | 2026-07-03 | completed | otel: attach scheduler endpoint-group name as a span attribute on collector/API spans | `a9f075b` |
| 647 | 2026-07-03 | completed | otel: collector failures never surface on the collect.collector root span → root-level error panels read zero | `a9f075b` |
| 646 | 2026-07-03 | completed | otel: collect.collector root span is unattributed — cannot identify the collector without descending | `a9f075b` |
| 645 | 2026-07-03 | completed | otel: trace_method attribute auto-extraction reads kwargs only → org.id/network.id never reach spans | `a9f075b` |
| 644 | 2026-07-03 | completed | Docs: document the OTLP-bridge parity envelope vs the Prometheus scrape | `dfe4ff1` |
| 643 | 2026-07-03 | completed | OTLP bridge: histogram le label renders as int on bridge path, float on scrape path | `dfe4ff1` |
| 642 | 2026-07-03 | completed | MX: getDeviceAppliancePerformance returns None → DataValidationError "Expected dict, got NoneType" (~2/min) | `ab5ab6f` |
| 641 | 2026-07-03 | completed | Logs: structlog level="warning" vs Loki detected_level="warn" spelling mismatch | `dfe4ff1` |
| 640 | 2026-07-03 | completed | Logs: default to JSON renderer in-container for clean Loki field extraction | `1e4ee31` |
| 639 | 2026-07-03 | completed | Data-logs: make the emitted/dropped counters discoverable (zero-series == never-emitted is invisible) | `d6a8b8c` |
| 638 | 2026-07-03 | completed | Data-logs: verify + prove the OTLP logs pipeline reaches Loki end-to-end | `4ac87a8` |
| 637 | 2026-07-03 | completed | Data-logs: signal_quality never emits for clients with no packet loss (coupled to packetLoss/byClient) | `d6a8b8c` `4ac87a8` |
| 636 | 2026-07-03 | completed | Clarify (and reconsider) api.concurrency_limit vs the adaptive rate limiter — do we need per-run sub-work caps? | `1e4ee31` |
| 635 | 2026-07-03 | completed | Settings() constructed twice on server start → duplicated startup validator warnings | `cc76452` |
| 634 | 2026-07-03 | completed | Build-metadata env vars (MERAKI_EXPORTER_VERSION/COMMIT) warned as unrecognized + redacted at startup | `cc76452` |
| 633 | 2026-07-03 | completed | Benign getNetworkWirelessMeshStatuses 404 (no repeaters) logged twice at ERROR | `cc76452` |
| 632 | 2026-07-03 | completed | DataRatesCollector crashes (TypeError) on null downloadKbps/uploadKbps — wireless data-rate metrics never emitted | `cc76452` |
| 631 | 2026-07-03 | completed | De-tier the dispatch layer: per-collector group-clocked loops replace the FAST/MEDIUM/SLOW heartbeat loops (completes #617) | `cc76452` `55dd4e5` |
| 630 | 2026-07-03 | completed | Live-verify the frozen scheduler assumptions: volatility floors, #271 byBand/6GHz, #549 MV fields, #331 conn-stats dedup, perPage maxima | `4514bf9` `ae1ffdd` |
| 629 | 2026-07-03 | completed | Scheduler gate-semantics gaps from the #617 implementation audit (mark_ran on failed fan-outs, untracked MS_PORT_OVERVIEW TTL) | `55dd4e5` |
| 628 | 2026-07-03 | completed | Docs site: redesign & rebrand alignment + SEO/LLM discoverability | `6486bbd` |
| 624 | 2026-07-03 | completed | MR org-wide presence gate misses Catalyst (CW*) APs — model-prefix check should include productType | `907aa24` |
| 623 | 2026-07-03 | completed | Epic: auto-detect in-use features/hardware per org and auto-disable unused collectors/endpoints (periodic re-discovery) | `907aa24` |
| 622 | 2026-07-03 | completed | Epic: OTel log emitter for high-cardinality per-entity data (solve cardinality via logs, not metrics) | `d6a8b8c` `2b9400c` `c34a6cc` `0528524` |
| 621 | 2026-07-03 | completed | Surface per-item batch failures in collector_errors_total (process_in_batches_with_errors) | `a382d54` |
| 619 | 2026-07-05 | completed | V1.0.0 release-readiness verification & cut (the P6 gate) | `410575b` `5b24890` `2b9400c` `ae13759` `13bf859` |
| 618 | 2026-07-05 | completed | V1 LAUNCH — master execution plan & tracker (all milestones → v1.0.0) | — |
| 617 | 2026-07-03 | completed | Adaptive budget-aware API scheduler: replace fixed FAST/MEDIUM/SLOW with cost- and volatility-driven scheduling (epic) | `4514bf9` `cc76452` `55dd4e5` `907aa24` `52b39d7` `2cb500d` `3071792` `3e20f34` `bd4ecca` `8f3168a` `f08cd69` |
| 616 | 2026-07-03 | completed | "Why this exporter" comparison / positioning page | `281f899` |
| 615 | 2026-07-03 | completed | Native TLS/mTLS on the exporter listener | — |
| 614 | 2026-07-03 | completed | Webhook events → faster device state transitions (down/up) | `cc08673` `281f899` `5b24890` |
| 613 | 2026-07-03 | completed | Meraki Insight collector (license-gated WAN app-health) | `ae13759` |
| 612 | 2026-07-03 | completed | Air Marshal threat_type breakdown + refresh stale module docstring | `13bf859` |
| 611 | 2026-07-03 | completed | Firmware compliance metrics: per-device firmware version info + per-network up-to-date gauge | `13bf859` |
| 610 | 2026-07-02 | completed | Rename/repurpose the misleading `examples/` dir (currently only a pytest example) | `aebd16a` |
| 609 | 2026-07-02 | completed | Expand `__meraki_op__` annotation coverage so apidrift auto-catches device-model drift | `57455d8` |
| 608 | 2026-07-02 | completed | Make codecov patch status informational | `de15dc9` |
| 607 | 2026-07-02 | completed | Remove redundant pyproject extra-files entry from release-please config | `3ff9be8` |
| 606 | 2026-07-02 | completed | Annotate/document chart version handling (static 0.1.0 is intentional) | `3ff9be8` |
| 605 | 2026-07-02 | completed | Add a container-structure test | `c368e4b` |
| 604 | 2026-07-02 | completed | Local-ops documentation nits (compose --build, APP_VERSION dev, Docker healthcheck) | `7638f6e` |
| 603 | 2026-07-02 | completed | Drop dead armv7 build capability | `6b48c74` |
| 602 | 2026-07-02 | completed | Declare v1 distribution = container image + Helm chart only (no PyPI machinery) | `f119c7a` |
| 601 | 2026-07-02 | completed | Helm: strategy Recreate (or maxSurge 0) for the singleton | `a8740e5` |
| 600 | 2026-07-02 | completed | Helm: warn/fail on replicaCount > 1 (no leader election) | `a8740e5` |
| 599 | 2026-07-03 | completed | Delete dead `log_configuration()`; stop double-logging the startup summary | `c98f0ad` |
| 598 | 2026-07-03 | completed | Accept lowercase log levels | `c98f0ad` |
| 597 | 2026-07-03 | completed | Document/tune shutdown grace vs blocked SDK threads | `b66eb05` |
| 596 | 2026-07-03 | completed | Derive liveness auto-threshold from the fastest enabled tier | `3071792` `5450e0a` |
| 595 | 2026-07-02 | completed | Fix perpetually-red weekly slow-tests job (0 collected → exit 5) | `c368e4b` |
| 594 | 2026-07-02 | completed | Golden /metrics exposition test per device family (units/label regression net) | `25ac17a` |
| 593 | 2026-07-02 | completed | CI: helm lint + kubeconform job wired into ci-success | `c368e4b` |
| 592 | 2026-07-02 | completed | CI: container serve-smoke test (/health + /metrics on the built image) | `c368e4b` |
| 591 | 2026-07-03 | completed | Skip smoothing offsets during initial collection (cut ~3.5min /ready on every rolling restart) | `5450e0a` |
| 590 | 2026-07-03 | completed | Validate `api_base_url` + `org_id` at startup | `c98f0ad` |
| 589 | 2026-07-03 | completed | Friendly, actionable 401 startup error instead of a 2KB frame-locals blob | `3cc9fb2` |
| 588 | 2026-07-03 | completed | `--check` config-validation / dry-run mode | `c98f0ad` |
| 587 | 2026-07-03 | completed | File-based API key (_FILE / secrets_dir) + rotation semantics | `c98f0ad` |
| 586 | 2026-07-03 | completed | First-class proxy + custom-CA support (requests_proxy / certificate_path) | `3cc9fb2` |
| 585 | 2026-07-03 | completed | Enforce single-organization contract for v1 (1 poller = 1 org, breaking) | `bd4ecca` `9860855` `c98f0ad` `9e2dd45` |
| 584 | 2026-07-03 | completed | [F-156] Surface M2/M3 device-specific metrics in the MX/MG/MV (and MS/MT) dashboards — 59 meraki_* metric families are shown on no dashboard | `4ac87a8` `f08cd69` |
| 583 | 2026-07-03 | completed | [F-155] Remove or fix the status="grace_period" license matcher — no license state ever has that value | — |
| 582 | 2026-07-03 | completed | [F-154] Fix exact-match org_id="$organization" on non-repeat panels with a multi-select/All variable | — |
| 581 | 2026-07-03 | completed | [F-153] Fix legendFormat labels that don't exist in the query result — legends render empty in ~10 panels across 5 dashboards | — |
| 580 | 2026-07-03 | completed | [F-152] Remove rate() from windowed-gauge metrics (connection stats, org usage) — 8 panels across 3 dashboards render meaningless numbers | — |
| 579 | 2026-07-03 | completed | [F-151] Fix band label values in mr-access-points 'Radio Configuration' panels (dashboard filters band="2.4GHz"/"5GHz", exporter emits "2.4"/"5"/"6") | — |
| 578 | 2026-07-03 | completed | [F-150] Fix org template variable and panels querying nonexistent `meraki_org` series (real series is `meraki_org_info`) | `4ac87a8` `f08cd69` |
| 577 | 2026-07-02 | completed | FAQ page | `9e2dd45` |
| 576 | 2026-07-02 | completed | Complete endpoint inventory in README/getting-started (or point at generated endpoints.md) | `7638f6e` |
| 575 | 2026-07-02 | completed | api-call-audit.md: remove from customer nav or add dated-internal-snapshot banner | `9e2dd45` |
| 574 | 2026-07-02 | completed | Fix hand-written generator notes: ghost PATH_PREFIX/ENABLE_HEALTH_CHECK + wrong SAMPLING_RATE claim baked into generate_config_docs.py | `2f7711e` |
| 573 | 2026-07-02 | completed | otel.md corrections: SAMPLING_RATE is a normal pydantic setting; TLS available via OTEL__INSECURE=false | `9ea11a6` |
| 572 | 2026-07-02 | completed | .env.example accuracy sweep: remove ghost CLIENTS__DNS_SERVER, add mtsensoralerts to default list, add missing keys, fix filter fail-fast wording | `7638f6e` |
| 571 | 2026-07-02 | completed | Upgrade/migration guide + release-notes convention for breaking metric/config changes | `9e2dd45` |
| 570 | 2026-07-03 | completed | Troubleshooting runbook: symptom→check→fix (401/403, zero filter matches, empty metrics, backoff, 429 storms, shedding, webhook secret) + fix broken LogQL example | `281f899` |
| 569 | 2026-07-03 | completed | Starter Prometheus alert rules: examples/prometheus-rules.yaml (~15 curated) + optional chart prometheusRule template | `410575b` `281f899` |
| 568 | 2026-07-03 | completed | Scaling-out & HA guide: shard-by-org recipes, rate_limit_shared_fraction arithmetic, why replicas>1 is harmful, failover semantics | `bd4ecca` |
| 567 | 2026-07-03 | completed | Data-freshness doc: per-tier staleness table, Meraki-side detection lag, alert for: guidance; fix README real-time webhook overclaim | `281f899` |
| 566 | 2026-07-03 | completed | Support matrix page: per-product-line supported/best-effort/not-collected; SM + Insight as explicit non-goals; tested hardware; regions | `281f899` |
| 565 | 2026-07-02 | completed | Document SERVER__API_TOKEN (security.md auth section, .env.example, README) + default-unauthenticated posture | `7638f6e` |
| 564 | 2026-07-03 | completed | Invert secret-masking to an allowlist (substring heuristic is allowlist-by-omission) | `c98f0ad` |
| 563 | 2026-07-02 | completed | Helm chart: optional NetworkPolicy template (ingress from Prometheus + egress 443/OTLP) | `a8740e5` |
| 562 | 2026-07-02 | completed | Digest-pin base image + verify uv tarball checksum in Dockerfile | `8bacd50` `0652871` `6b48c74` |
| 561 | 2026-07-03 | completed | Bound webhook success-path labels (org_id/alert_type attacker-controlled when require_secret=false) + refuse insecure combo without explicit flag | `f2675a9` |
| 560 | 2026-07-02 | completed | Webhook receiver deployability: document Meraki HTTPS requirement + TLS-termination examples; optional chart ingress | `a8740e5` |
| 559 | 2026-07-03 | completed | Data privacy / GDPR documentation for client tracking (PII in Prometheus, retention, mitigation) | `281f899` |
| 558 | 2026-07-03 | completed | Endpoint exposure hardening: threat-model doc + extend auth to sensitive GETs (or ui_enabled flag) + reverse-proxy/TLS pattern | `f2675a9` |
| 557 | 2026-07-03 | completed | getOrganizations: add total_pages="all" for paved-path consistency | `567149c` |
| 556 | 2026-07-03 | completed | Review 30s single_request_timeout default for large-org bulk fetches + document | `2c2c7e5` |
| 555 | 2026-07-02 | completed | Pass fields="avg" to latency-stats fetchers (skip unused rawDistribution payload) | `8f74757` |
| 554 | 2026-07-03 | completed | CardinalityMonitor: cap retained label-value lists + lengthen interval at scale | `cda95ba` |
| 553 | 2026-07-03 | completed | MT sensor readings: decorate with rate limiter + drop all-serials query param | `55440da` |
| 552 | 2026-07-03 | completed | Gate per-MX getDeviceAppliancePerformance to 900s + document linear cost | `2cb500d` |
| 551 | 2026-07-03 | completed | Route ConfigCollector login-security through the inventory cache (or delete the dead cache method) | `3cc9fb2` |
| 550 | 2026-07-03 | completed | Default rate_limit_shared_fraction to 0.8 + 'shared org budget' doc (sequence AFTER call-volume reductions) | `838ef02` `2c2c7e5` |
| 549 | 2026-07-03 | completed | MV camera: migrate deprecated analytics endpoints, add own interval/off-default, fix rate-limiter org keying | `4514bf9` `2cb500d` |
| 548 | 2026-07-03 | completed | Set perPage to endpoint maxima on paginated fetchers (memory-history 10→20, assurance alerts 30→300) | `fdd9f52` |
| 547 | 2026-07-03 | completed | OrgHealthTracker: make per-org backoff aware of device/network failure domains (single-writer fix) | `08587ff` |
| 546 | 2026-07-03 | completed | Per-fetch deadlines + defined timeout semantics (stop torn partial metric state on collector timeout) | `b66eb05` `4332161` |
| 545 | 2026-07-03 | completed | Single 429 retry owner + bounded/cancellable Retry-After (stop ~12 attempts/fetch) | `4332161` |
| 544 | 2026-07-03 | completed | Dedicated sized executor for SDK calls (stop /metrics queueing behind blocked threads); wire or remove dead semaphore | `b66eb05` `4332161` |
| 543 | 2026-07-03 | completed | Memory bounds: ClientStore eviction + global client cap + DNS cache pruning | `d666ab7` `d2c99b9` |
| 542 | 2026-07-03 | completed | Publish quantitative API-budget sizing formula + correct scaling-guide numbers | `bd4ecca` |
| 541 | 2026-07-03 | completed | Per-endpoint refresh intervals for windowed network-health endpoints (cut NetworkHealth ~8W→~4.7W calls) | `2cb500d` |
| 540 | 2026-07-03 | completed | Per-family cardinality budgets — stop silently deleting live device series at scale (alarm, don't delete) | `838ef02` `cda95ba` |
| 539 | 2026-07-02 | completed | Disambiguate duplicate webhook counters + org-vs-exporter api_requests_total HELP | `42322b6` |
| 538 | 2026-07-02 | completed | Delete dead *MetricName enum members never passed to a constructor (reconcile 7-vs-8 list) | `4410df4` |
| 537 | 2026-07-02 | completed | Add meraki_exporter_build_info{version,commit} + evaluate org API-budget headroom gauge | `be1ed71` |
| 536 | 2026-07-02 | completed | Add data-window/lag language to windowed-metric HELP strings | `9b31a3e` |
| 535 | 2026-07-02 | completed | Publish metric stability & deprecation policy (docs/stability.md) | `64bc2e6` |
| 534 | 2026-07-02 | completed | Decide mutable name-label policy pre-v1 (name/org_name/network_name/port_name churn vs `_info` joins) | `cd76d8d` `9e2dd45` `343ea48` `32dd2f6` `64bc2e6` |
| 533 | 2026-07-02 | completed | Client metrics v1 label contract: ID-only numeric series + `meraki_client_info` join, capped & expiration-tracked | `281f899` `c34a6cc` `d2c99b9` `63221da` `32dd2f6` |
| 532 | 2026-07-02 | completed | Fix mistyped exporter self-metrics (cardinality_analyzed_total gauge, errors_total_expired, cache_size_tracked_metrics) | `167b6ef` |
| 531 | 2026-07-02 | completed | Coordinated v1 metric naming & unit sweep (drop gauge `_total`, base units, `_percent`/`_percentage`, ×1000 kB) | `9e2dd45` `64bc2e6` `416a26a` `8f3168a` |
| 530 | 2026-07-02 | completed | Remove dead WebhookMetricsCollector (or wire it deliberately) | `640b589` `42322b6` |
| 529 | 2026-07-03 | completed | Stop special-casing the bare MERAKI_API_KEY env var that is never consumed | `c98f0ad` |
| 528 | 2026-07-03 | completed | Remove or activate the dead tier-loop 10-consecutive-failure kill switch | `57f79bb` |
| 527 | 2026-07-02 | completed | Verify VPN stats timespan=300 returns populated summaries; widen if sparse | `640b589` `dbbc72f` |
| 526 | 2026-07-02 | completed | Verify and harden firmware _PENDING_STATUSES against live spelling | `cbd4de2` |
| 525 | 2026-07-02 | completed | Reduce application-usage client-ID batch size to avoid URL-length/414 risk | `8889eb3` |
| 524 | 2026-07-02 | completed | Bucket unknown alert severities as "other" instead of dropping them | `28eaf9c` |
| 523 | 2026-07-03 | completed | Drop meraki_org_login_security_strong_passwords_enabled (derived from deprecated field) | `43bf9f8` |
| 522 | 2026-07-03 | completed | Wrap discovery.py single-org getOrganization with validate_response_format | `c98f0ad` |
| 521 | 2026-07-02 | completed | Pass explicit timespan to getDeviceAppliancePerformance for deterministic score | `b9e2257` |
| 520 | 2026-07-02 | completed | Reapply NetworkFilter in api_helpers._fetch_devices_direct and unify product_types filtering | `1aadae6` |
| 519 | 2026-07-03 | completed | Wrap single-org getOrganization fallbacks with validate_response_format | `43bf9f8` |
| 518 | 2026-07-03 | completed | Fix dead China-region timeout auto-bump (matches wrong host substring) | `c98f0ad` |
| 517 | 2026-07-02 | completed | Aggregate MX uplink loss/latency per uplink instead of last-write-wins across destination IPs | `640b589` `74ed0cb` |
| 516 | 2026-07-03 | completed | Handle subscription-licensing organizations instead of going permanently red | `43bf9f8` |
| 515 | 2026-07-03 | completed | Warn at startup on unrecognized MERAKI_EXPORTER_* environment variables | `c98f0ad` |
| 514 | 2026-07-03 | completed | Accept CSV form of COLLECTORS__ENABLED / DISABLE_COLLECTORS without crashing at boot | `c98f0ad` |
| 513 | 2026-07-03 | completed | Apply NetworkFilter to configuration-changes row counting | `43bf9f8` |
| 512 | 2026-07-02 | completed | Fix channel-utilization non_wifi key and bucket sort to live API field names | `6b73c46` |
| 511 | 2026-07-03 | completed | Increment an error counter on bare-except swallow paths and document an alerting recipe | `a382d54` `b6bcaec` |
| 510 | 2026-07-03 | completed | Propagate ManagedTaskGroup child-task failures so coordinators can detect all-failed | `aff2ed4` |
| 509 | 2026-07-02 | completed | Treat "collected nothing" as a collection failure so health signals are honest | `57f79bb` `aff2ed4` `61c4bb1` `8f3168a` |
| 508 | 2026-07-02 | completed | Demote apidrift submodel-vs-bare-object conformance mismatch to INFO to unblock CI | `f9e4316` `8f3168a` `f08cd69` |
| 507 | 2026-07-02 | completed | [F-054] Delete dead code in core (async_utils / metrics / api_helpers) | `24bacf3` |
| 506 | 2026-07-02 | completed | [F-169] Gate Device/NetworkHealth/Clients/Alerts/MTSensorAlerts collectors on OrgHealthTracker backoff | `67cd893` |
| 505 | 2026-07-02 | completed | [F-177] Wire Chart.yaml appVersion into release-please | `25aac12` |
| 504 | 2026-07-02 | completed | [F-007] Paginate org memory-usage fetch so all devices are covered | `0e1508d` |
| 503 | 2026-07-02 | completed | [F-029] Add Pydantic domain models for MG/MS-power/MX-uplink-health/MV collectors | `6f18706` |
| 502 | 2026-07-02 | completed | [F-078] get_devices returns cache dicts by reference; enrichment pollutes cache | `036bc6d` |
| 501 | 2026-07-02 | completed | [F-075] DNS lookups share the default executor and can starve API calls | `036bc6d` |
| 500 | 2026-07-02 | completed | [F-019] None-valued label silently drops the entire metric series | `036bc6d` |
| 499 | 2026-07-02 | completed | [F-108] Collector performance metrics use hardcoded name strings | `036bc6d` |
| 498 | 2026-07-02 | completed | [F-118] Container image self-reports version 0.0.0+dev | `c9e5be8` `009da56` |
| 497 | 2026-07-02 | completed | [F-110] Drive OTLP exporter TLS from settings.otel.insecure | `009da56` |
| 496 | 2026-07-02 | completed | [F-170] Scope network-health rate limiting to the owning org | `009da56` |
| 495 | 2026-07-02 | completed | [F-028/F-074] /status API-health card always reports 0 calls and 0 throttles | `009da56` |
| 494 | 2026-07-02 | completed | [F-171] Demote per-network client log lines to debug | `10c9d87` |
| 493 | 2026-07-02 | completed | [F-060] Signal-quality collection drains the org rate-limit budget | `10c9d87` |
| 492 | 2026-07-02 | completed | [F-112] Fractional client usage drops the whole network's client metrics | `10c9d87` |
| 491 | 2026-07-02 | completed | [F-052] 404 substring check downgrades genuine 500s | `486360f` |
| 490 | 2026-07-02 | completed | [F-002] ManagedTaskGroup loses fail-fast task exceptions | `486360f` |
| 489 | 2026-07-02 | completed | [F-053] api_helpers direct fetchers skip validate_response_format | `486360f` |
| 488 | 2026-07-02 | completed | [F-000] Add validate_response_format to api_helpers._fetch_networks_direct | `486360f` |
| 487 | 2026-07-02 | completed | [F-166] Stop logging the raw webhook payload (with sharedSecret) on validation failure | `451bc6b` |
| 486 | 2026-07-02 | completed | [F-051] Prevent unauthenticated webhook cardinality injection via failure-path labels | `451bc6b` |
| 485 | 2026-07-02 | completed | [F-109] Use constant-time comparison for the webhook shared secret | `451bc6b` |
| 484 | 2026-07-02 | completed | [F-162] Add test coverage for the production collection scheduler | `6420c6c` |
| 483 | 2026-07-02 | completed | [F-003] Bound the cardinality label-value distribution to stop unbounded growth | `6420c6c` |
| 482 | 2026-07-02 | completed | [F-044] Track and cancel the first-collection wait task on shutdown | `6420c6c` |
| 481 | 2026-07-02 | completed | [F-026] Offload synchronous Prometheus registry iteration off the event loop | `6420c6c` |
| 480 | 2026-07-02 | completed | [F-103] Cap webhook body size while reading, regardless of Content-Length | `6420c6c` |
| 479 | 2026-07-02 | not planned | [F-115] Client application-usage KB vs bytes — verify units (WONTFIX) | — |
| 478 | 2026-07-02 | completed | [F-018] Clamp smoothing offset so it can't stretch tier cadence past the interval | `effe4a8` |
| 477 | 2026-07-02 | completed | [F-167] Optional bearer-token guard for state-changing control endpoints | `effe4a8` |
| 476 | 2026-07-02 | completed | [F-105] /ready must reflect real collection success, not just tier completion | `effe4a8` |
| 475 | 2026-07-02 | completed | [F-104] Run startup discovery off the lifespan critical path | `effe4a8` |
| 474 | 2026-07-02 | completed | [F-043] Dead-man liveness switch: /health degrades when the exporter is wedged | `effe4a8` |
| 473 | 2026-07-02 | not planned | [F-136] Harden issue-triage tool restriction (OBSOLETE — workflow removed) | — |
| 472 | 2026-07-02 | not planned | [F-133] Codacy coverage reporter runs an unpinned curl\|bash from master (WONTFIX) | — |
| 471 | 2026-07-02 | completed | [F-178] Add a Renovate custom manager for the pinned Dockerfile UV_VERSION | `1a03f14` |
| 470 | 2026-07-02 | completed | [F-137] Edge :main publishing silently freezes if the release-please job fails | `1a03f14` |
| 469 | 2026-07-02 | completed | [F-135] Pin the tufin/oasdiff image and separate oasdiff tool errors from real drift | `1a03f14` |
| 468 | 2026-07-02 | completed | [F-131] Remove the broken Claude enrichment step from the api-drift report action | `1a03f14` |
| 467 | 2026-07-02 | completed | [F-130] Remove the stale bot (placeholder messages, no exemptions, would auto-close roadmap backlog) | `1a03f14` |
| 466 | 2026-07-02 | completed | [F-160] Fix tests/CLAUDE.md paved-path error-test example (70s real retry-sleep trap) | `24e307b` |
| 465 | 2026-07-02 | completed | [F-134] Add ruff to CI — the lint third of `make check` is enforced nowhere | `24e307b` |
| 464 | 2026-07-02 | completed | [F-132] Gate Codecov/Codacy upload steps on secret availability | `24e307b` |
| 463 | 2026-07-02 | completed | [F-072] Add the mandated exhausted-retry error-shape tests for the four M2 fetchers | `24e307b` |
| 462 | 2026-07-02 | completed | [F-023] Add the Pydantic domain models the M3 acceptance criteria require for the new MX/MT fetchers | `088f3fd` |
| 461 | 2026-07-02 | completed | [F-106] OTel sampling rate: honor .env and don't let a bad value kill tracing | `3687573` |
| 460 | 2026-07-02 | completed | [F-076] Remove non-working clients.dns_server setting (silent no-op + timeout bypass) | `3687573` |
| 459 | 2026-07-02 | completed | [F-034] Validate dict-shaped responses to avoid false zeros (config + mx_firewall) | `088f3fd` `3687573` |
| 458 | 2026-07-02 | completed | [F-016] Replace unbounded asyncio.gather in ConfigCollector | `3687573` |
| 457 | 2026-07-02 | completed | [F-011] Emit config admin metrics via _set_metric for expiration | `3687573` |
| 456 | 2026-07-02 | completed | [F-008] Wire MonitoringSettings.histogram_buckets to the duration histogram | `3687573` `c2fad44` `6d98834` `3d430f8` `f367ea9` |
| 455 | 2026-07-02 | completed | [F-005] Startup summary always reports Network Health & MT Sensors disabled | `3687573` |
| 454 | 2026-07-02 | not planned | [F-178] Add a Renovate regex manager for the pinned UV_VERSION in Dockerfile | — |
| 453 | 2026-07-02 | not planned | [F-177] Wire Chart.yaml appVersion into release-please so it auto-bumps | — |
| 452 | 2026-07-02 | completed | [F-176] Stale '(default: 120s)' comment on collector_timeout in manager.py | `476bee5` |
| 451 | 2026-07-02 | completed | [F-146] Reconcile stale MT-only hardware warning in docs/index.md | `df78af1` |
| 450 | 2026-07-02 | completed | [F-139] Add NetworkFilterSettings to generate_config_docs.py nested_models | `df78af1` |
| 449 | 2026-07-02 | completed | [F-129] Validate config.otelEndpoint at Helm render time when config.otelEnabled is true | `fdea149` |
| 448 | 2026-07-02 | completed | [F-128] .helmignore doesn't exclude CLAUDE.md from the packaged chart | `fdea149` |
| 447 | 2026-07-02 | completed | [F-127] Chart securityContext missing seccompProfile — restricted PSS rejects the pod | `fdea149` |
| 446 | 2026-07-02 | completed | [F-126] Dockerfile fetches uv 'latest' at build time instead of a pinned version | `fdea149` |
| 445 | 2026-07-02 | completed | [F-125] values.yaml extraEnv example uses an unquoted int value | `fdea149` |
| 444 | 2026-07-02 | completed | [F-123] Dockerfile HEALTHCHECK hardcodes port 9099, ignores MERAKI_EXPORTER_SERVER__PORT | `fdea149` |
| 443 | 2026-07-02 | completed | [F-121] Chart.yaml appVersion is stale and not wired to release-please | `fdea149` |
| 442 | 2026-07-02 | completed | [F-119] CI 'Verify non-root user' step is vacuous — never actually checks the runtime UID | `fdea149` |
| 441 | 2026-07-02 | completed | [F-117] Helm chart collectorTimeout default silently reverts the app's 240s default | `fdea149` |
| 440 | 2026-07-02 | completed | [F-159] Remove fictional 'failures' count field from SSID failed-connections handling/tests | `40e3130` |
| 439 | 2026-07-02 | completed | [F-065] Correct wireless data-rate help strings: kilobytes-per-second, not kilobits | `40e3130` |
| 438 | 2026-07-02 | completed | [F-017] Pin timespan/resolution/perPage and sort buckets in RF channel-utilization fetch | `40e3130` |
| 437 | 2026-07-02 | completed | [F-015] Stop setting Bluetooth client count to 0 on rate-limit/error responses | `40e3130` |
| 436 | 2026-07-02 | completed | [F-027] Reduce MV per-camera API fan-out: throttle near-static calls to SLOW cadence | `3543ccb` |
| 435 | 2026-07-02 | completed | [F-004] Stop emitting literal "None" MV label values for null quality/resolution/profileId | `3543ccb` |
| 434 | 2026-07-02 | completed | [F-024] Fix MV zone-name join: zones response field is `id`, not `zoneId` | `3543ccb` |
| 433 | 2026-07-02 | completed | [F-088] Remove MTCollector._set_metric_value override bypassing expiration | `c9d932c` |
| 432 | 2026-07-02 | completed | [F-021] Route MT gateway metrics through expiration tracking | `c9d932c` |
| 431 | 2026-07-02 | completed | [F-092] Stop re-fetching orgs/names/devices every 60s in the MT FAST path | `c9d932c` |
| 430 | 2026-07-02 | completed | [F-069] MTSensorCollector inverted org-name reuse condition | `c9d932c` |
| 429 | 2026-07-02 | completed | [F-061] Add validate_response_format to MT standalone fetchers | `c9d932c` |
| 428 | 2026-07-02 | completed | [F-089] Enforce NetworkFilter on MT org-wide sensor readings | `c9d932c` |
| 427 | 2026-07-02 | completed | [F-031] MT sensor collection bypasses NetworkFilter | `c9d932c` |
| 426 | 2026-07-02 | completed | [F-030] MS org-wide collection block skips Catalyst switches | `bee1402` |
| 425 | 2026-07-02 | completed | [F-071] Add psu_model label to meraki_ms_power_supply_status | `bee1402` |
| 424 | 2026-07-02 | completed | [F-091] Rename '_total'-suffixed non-counter gauges (MS port errors/warnings, MX security events) | `bee1402` |
| 423 | 2026-07-02 | completed | [F-175] MSStackCollector emits stack-member series via raw .labels().set() with no expiration | `7454948` |
| 422 | 2026-07-02 | completed | [F-174] MS STP-priority series collide on network+name because lookup-matched switches emit serial="" | `7454948` |
| 421 | 2026-07-02 | completed | [F-168] Replace per-switch getDeviceSwitchPortsStatuses usage/PoE loop with org-wide endpoints | `7454948` |
| 420 | 2026-07-02 | completed | [F-113] MSStackCollector fabricates the stack role label from serial order instead of the API role | `ba86643` |
| 419 | 2026-07-02 | completed | [F-157] Fix dead MS STP tests (stale 2-arg call + unwired mock_parent.inventory) | `ba86643` |
| 418 | 2026-07-02 | completed | [F-037] Move MS STP-priority collection off the sequential per-network MEDIUM path | `ba86643` |
| 417 | 2026-07-02 | completed | [F-070] Remove stale label-transition series for MS port STP state and 802.1X status | `ba86643` |
| 416 | 2026-07-02 | completed | [F-084] MS port metrics bypass _set_metric expiration — removed switches/ports go stale | `ba86643` |
| 415 | 2026-07-02 | completed | [F-083] collect_port_overview lacks validate_response_format — exhausted-retry error zeroes port counts | `ba86643` |
| 414 | 2026-07-02 | completed | [F-093] Set perPage=1000 on the MX security-events fetch to avoid up-to-10x pagination | `fc2bfaa` |
| 413 | 2026-07-02 | completed | [F-085] MX firewall rules fetched every MEDIUM cycle despite being near-static (SLOW) | `fc2bfaa` |
| 412 | 2026-07-02 | completed | [F-066] Stop calling getDeviceAppliancePerformance for Z-series/vMX appliances | `fc2bfaa` |
| 411 | 2026-07-02 | completed | [F-067] MX VPN latency/jitter/packet-loss gauges are registered but never populated | `fc2bfaa` |
| 410 | 2026-07-02 | completed | [F-013] Remove dead MX VPN latency/jitter/packet-loss metrics parsed from fields the endpoint never returns | `fc2bfaa` |
| 409 | 2026-07-02 | completed | [F-173] AlertsCollector active/severity/network alert gauges are not NetworkFilter-filtered | `960e336` |
| 408 | 2026-07-02 | completed | [F-172] Expose success/failure from the 5 separate org sub-collectors to OrgHealthTracker | `960e336` |
| 407 | 2026-07-02 | completed | [F-158] Strengthen MR happy-path tests + fix fictional mock shapes | `fa62d97` |
| 406 | 2026-07-02 | completed | [F-058] Rename meraki_mr_air_marshal_rogue_ssids_total — it counts all observed foreign SSIDs, not rogues | `fa62d97` |
| 405 | 2026-07-02 | completed | [F-114] SSID usage silently limited to the top 10 (endpoint default quantity) | `fa62d97` |
| 404 | 2026-07-02 | completed | [F-035] Remove the per-network SSID-to-network mapping fan-out | `fa62d97` |
| 403 | 2026-07-02 | completed | [F-082] SSID usage replicated the org-wide total onto every network sharing the SSID name | `fa62d97` |
| 402 | 2026-07-02 | completed | [F-111] Fix MR packet-loss parsing: nested network object + device metrics come from the ByDevice endpoint | `fa62d97` |
| 401 | 2026-07-02 | completed | [F-081] Paginate getOrganizationWirelessDevicesSystemCpuLoadHistory — only 10 of each 20-serial batch got CPU metrics | `fa62d97` |
| 400 | 2026-07-02 | completed | [F-033] Add pagination to MR ethernet-status and CPU-load fetches | `fa62d97` |
| 399 | 2026-07-02 | completed | [F-012] Paginate getOrganizationWirelessDevicesEthernetStatuses — MR ethernet/power metrics truncated at 100 APs | `fa62d97` |
| 398 | 2026-07-02 | completed | [F-116] Single-org mode emits the org ID as the org_name label on every metric | `9a0545a` `6410fa6` |
| 397 | 2026-07-02 | completed | [F-102] Cache the per-device getOrganizationLicenses full-list fetch | `6410fa6` |
| 396 | 2026-07-02 | completed | [F-100] Handle licenses-overview fetch failure distinctly from an empty overview | `6410fa6` |
| 395 | 2026-07-02 | completed | [F-097] Fix meraki_org_licenses_expiring undercount (per-device + co-term paths) | `6410fa6` |
| 394 | 2026-07-02 | completed | [F-099] Guard against non-numeric responseCodeCounts values aborting the loop | `6410fa6` |
| 393 | 2026-07-02 | completed | [F-096] Emit zero counts in APIUsageCollector instead of freezing stale values | `6410fa6` |
| 392 | 2026-07-02 | completed | [F-101] Bound the client-overview stale-zero guard by age / consecutive-zero count | `9a0545a` `6410fa6` |
| 391 | 2026-07-02 | completed | [F-095] Wrap ClientOverviewCollector fetch with validate_response_format | `9a0545a` `6410fa6` |
| 390 | 2026-07-02 | completed | [F-064] Migrate off deprecated getNetworkHealthAlerts in AlertsCollector | `6410fa6` |
| 389 | 2026-07-02 | completed | [F-059] Stale alert gauges: resolved alerts stay nonzero forever in AlertsCollector | `6410fa6` |
| 388 | 2026-07-02 | completed | [F-057] Tie device-availability-history timespan to the configured MEDIUM interval | `9a0545a` `6410fa6` |
| 387 | 2026-07-02 | completed | [F-056] Zero out absent label combos in windowed/status count gauges | `6410fa6` |
| 386 | 2026-07-02 | completed | [F-055] Case-mismatched _PENDING_STATUSES so firmware upgrade counts never match | `6410fa6` |
| 385 | 2026-07-02 | completed | [F-010] Apply NetworkFilter in FirmwareCollector and DeviceAvailabilityHistoryCollector | `9a0545a` `6410fa6` |
| 384 | 2026-07-02 | completed | [F-098] Apply NetworkFilter to devices-by-model and packet-capture collection | `6410fa6` |
| 383 | 2026-07-02 | completed | [F-042] Clamp application-usage quantity to the documented API maximum (50) | `6410fa6` |
| 382 | 2026-07-02 | completed | [F-041] Dead {"items": ...} branch in _collect_device_counts_by_model | `6410fa6` |
| 381 | 2026-07-02 | completed | [F-040] Unreachable org-failure path: sub-collection exceptions swallowed before OrgHealthTracker.record_failure | `6410fa6` |
| 379 | 2026-07-02 | completed | [F-164] Factory malformed double-tz timestamps (fixed) + dead large-org scale-testing infra (follow-up) | `0fbb195` `a583c19` |
| 378 | 2026-07-02 | completed | [F-163] MetricAssertions cached metric snapshots, causing stale reads and false passes | `a583c19` |
| 377 | 2026-07-02 | completed | [F-165] MockAPIBuilder HTTP errors lacked .status, making the production 429-retry branch unreachable in tests | `a583c19` |
| 376 | 2026-07-02 | completed | [F-161] MockAPIBuilder method→module routing wrong for org-wireless/sensor-latest; error routing disagreed with response routing | `a583c19` |
| 375 | 2026-07-02 | completed | [F-050] MockAPIBuilder org_id/param-scoped responses silently collapse to last-write-wins | `a583c19` |
| 374 | 2026-07-02 | completed | [F-124] install-hooks clobbers the pre-commit framework's managed hook | `6d0b538` |
| 373 | 2026-07-02 | completed | [F-122] docker-build-all/docker-build-push request platforms the Dockerfile rejects | `6d0b538` |
| 372 | 2026-07-02 | completed | [F-120] docker-compose-up/down reference deleted docker-compose.dev.yml | `6d0b538` |
| 371 | 2026-07-02 | completed | [F-048] docker-run passes env vars the exporter never reads | `6d0b538` |
| 370 | 2026-07-02 | completed | [F-047] core/CLAUDE.md cardinality paths wrong + MGMetricName missing from enum roster | `24db96d` |
| 369 | 2026-07-02 | completed | [F-009] Undocumented third NetworkFilter bypass site + wrong cardinality endpoint paths in CLAUDE.md | `24db96d` |
| 368 | 2026-07-02 | completed | [F-107] Root CLAUDE.md/AGENTS.md overclaim 'OpenTelemetry mirroring' | `24db96d` |
| 367 | 2026-07-02 | completed | [F-006][F-090] charts CLAUDE.md readinessProbe note is backwards/stale | `24db96d` |
| 366 | 2026-07-02 | completed | [F-049] .github/CLAUDE.md workflow count and harden-runner coverage claim are stale | `24db96d` |
| 365 | 2026-07-02 | completed | [F-086] devices/CLAUDE.md wrongly documents MG/MV as no-op stubs | `24db96d` |
| 364 | 2026-07-02 | completed | [F-045] Collector-layer CLAUDE.md rosters stale after M2/M3 (4 files) | `24db96d` |
| 363 | 2026-07-02 | completed | [F-068] Collector CLAUDE.md rosters missing mt_alerts/mx_ha/mx_uplink_usage/mx_uplink_health | `24db96d` |
| 362 | 2026-07-02 | completed | [F-046] api/CLAUDE.md paved-path with_error_handling example raises TypeError if copy-pasted | `24db96d` |
| 361 | 2026-07-02 | completed | [F-032] api/CLAUDE.md stale AsyncMerakiClient production-usage claim | `24db96d` |
| 360 | 2026-07-02 | completed | [F-149] Document the published Helm chart in README and docs | `2b5aa07` |
| 359 | 2026-07-02 | completed | [F-148] Remove self-contradictory docker-compose claim in integration-dashboards.md | `2b5aa07` |
| 358 | 2026-07-02 | completed | [F-147] Fix invalid LogQL examples in deployment-operations.md | `2b5aa07` |
| 357 | 2026-07-02 | completed | [F-145] Wire scaling-guide.md and api-call-audit.md into the zensical nav | `2b5aa07` |
| 356 | 2026-07-02 | completed | [F-144] Fix broken favicon reference in zensical.toml | `2b5aa07` |
| 355 | 2026-07-02 | completed | [F-143] Fix scaling-guide 'Collector Timeouts' symptom metric name | `2b5aa07` |
| 354 | 2026-07-02 | completed | [F-142] Fix wrong self-monitoring metric names in docs/metrics/overview.md | `2b5aa07` |
| 353 | 2026-07-02 | completed | [F-141] Remove docs claim that /status shows network-filter resolution | `2b5aa07` |
| 352 | 2026-07-02 | completed | [F-140] Remove docs claim that MERAKI_EXPORTER_LOGGING__FORMAT=json exists | `2b5aa07` |
| 351 | 2026-07-02 | completed | [F-138] Fix cosign verification docs: certificate identity points at deleted docker-build.yml | `2b5aa07` |
| 350 | 2026-07-02 | completed | [F-080] Inventory cache hit/miss enums declared but never registered; cache-size gauge name diverges from its enum | `f4add56` |
| 349 | 2026-07-02 | completed | [F-079] meraki_network_filter_match + inventory cache-size series never expire; filter_match uses a raw literal not an enum | `f4add56` |
| 348 | 2026-07-02 | completed | [F-073] meraki_exporter_api_rate_limit_remaining/_total registered but never set (3 dashboards query them) | `f4add56` |
| 347 | 2026-07-02 | completed | [F-062] Remove never-observed meraki_exporter_collection_wait_seconds histogram | `3181a58` `cff7ff9` |
| 346 | 2026-07-02 | completed | [F-039] Remove frozen collector_success_age_seconds gauge — freezes when runs stop | `cff7ff9` |
| 345 | 2026-07-02 | completed | [F-025] Remove phantom pre-initialized zero-forever collector self-metric series | `57181fe` |
| 344 | 2026-07-02 | completed | [F-077] AsyncMerakiClient._request instrumentation is dead: api_duration/api_retry never emit, dashboard latency panels empty | `836a6f3` `f4add56` |
| 343 | 2026-07-02 | completed | [F-022] Unsupported span_callback kwarg on RequestsInstrumentor — Meraki span enrichment silently dead | `96988f3` |
| 342 | 2026-07-02 | completed | [F-036] Wrong @log_api_call endpoint name on collect_packet_loss (ByClient vs ByNetwork) | `4c15bff` |
| 341 | 2026-07-02 | completed | [F-063] Cache hits counted as API calls in _track_api_call call sites | `246d3e7` |
| 340 | 2026-07-02 | completed | [F-014] Double-counted meraki_exporter_collector_api_calls_total: @log_api_call + manual _track_api_call | `fc8c9c2` |
| 339 | 2026-07-03 | completed | Epic: optional OTLP metrics emission via Prometheus-registry bridge | `2b9400c` |
| 338 | 2026-07-02 | completed | [F-087] collect_org_security_events _metrics.clear() erases every org's MX security-event series | `0710ef7` |
| 337 | 2026-07-02 | completed | [F-020] MXHACollector _metrics.clear() wipes other orgs' HA mode/role series | `0710ef7` |
| 336 | 2026-07-02 | completed | [F-001] Multi-org gauge wipe: per-org _metrics.clear() erases other orgs' series | `0710ef7` |
| 335 | 2026-07-02 | completed | [F-094] Route org device-count gauges through _set_metric so grouped label sets expire | `d5ec85b` |
| 334 | 2026-07-02 | completed | [F-038] Implement real Prometheus series removal in MetricExpirationManager | `0710ef7` `d5ec85b` `85c28ca` |
| 332 | 2026-07-02 | not planned | Add MT20 button-press metric (deferred from #246) | — |
| 331 | 2026-07-03 | completed | Batch getNetworkWirelessDevicesConnectionStats (mr/clients.py) into the org-wide client overview already fetched | `4514bf9` |
| 330 | 2026-07-03 | completed | Add uplink status overview aggregate (org-wide counts by status) | `ae13759` |
| 329 | 2026-07-02 | not planned | Insight application health (WAN health scores) | — |
| 328 | 2026-07-03 | completed | General uplink-status fallback / high-availability role for MG (unifies with MX pattern) | `ae13759` |
| 327 | 2026-07-03 | completed | eSIM inventory / rate-plan visibility (ops signal, not time-series) | `ae13759` |
| 326 | 2026-07-03 | completed | Catalyst wireless controller association info | `ae13759` |
| 325 | 2026-07-03 | completed | Power mode change history | `ae13759` |
| 324 | 2026-07-03 | completed | Per-AP/per-client signal quality (SNR/RSSI) — deferred pending cost decision | `ae13759` |
| 323 | 2026-07-03 | completed | Org-wide per-client wireless packet loss | `c34a6cc` `0528524` |
| 322 | 2026-07-03 | completed | Org-wide camera detection history by boundary (people/vehicle in/out counts) | — |
| 321 | 2026-07-03 | completed | Implement Systems Manager (SM) device metrics | `d076e16` `cb48291` |
| 320 | 2026-07-03 | completed | Evaluate adopting meraki.aio.AsyncDashboardAPI (native async SDK) instead of asyncio.to_thread wrapping | — |
| 319 | 2026-07-03 | completed | Expose DNS resolver stats as real Prometheus metrics | `d666ab7` `d2c99b9` |
| 318 | 2026-07-02 | completed | Document/provide Helm resource-sizing guidance (or an HPA example) for larger orgs | `a8740e5` |
| 317 | 2026-07-03 | completed | Surface webhook receiver health on /status | `f2675a9` |
| 316 | 2026-07-03 | completed | Add a CI check that dashboard JSON references only real metric/label names | — |
| 315 | 2026-07-03 | completed | Ship a Grafana provisioning example (docker-compose + datasource/dashboard YAML) | — |
| 314 | 2026-07-03 | completed | Support TLS for the OTLP exporter endpoint | `2b9400c` |
| 313 | 2026-07-03 | completed | Add an OTLP metrics exporter (true OTel "mirroring", not tracing-only) | `2b9400c` |
| 312 | 2026-07-03 | completed | Add a redacted effective-config view (extend /status or new /config endpoint) | `f2675a9` |
| 311 | 2026-07-03 | completed | Surface NetworkFilterSettings effective state on /status | `f2675a9` |
| 310 | 2026-07-03 | completed | Add a log_format setting (logfmt vs JSON) | `c98f0ad` |
| 309 | 2026-07-03 | completed | Add per-metric / per-label cardinality controls beyond whole-collector enable/disable | `cda95ba` |
| 308 | 2026-07-03 | completed | MT↔MV sensor relationship info metric | `13bf859` |
| 307 | 2026-07-03 | completed | Wireless mesh link health | — |
| 306 | 2026-07-03 | completed | Org-wide camera onboarding status | `13bf859` |
| 305 | 2026-07-03 | completed | MV Sense (object detection) enablement status | `13bf859` |
| 304 | 2026-07-03 | completed | Add carrier/band + serving-cell detail for MG (complements uplink status) | `13bf859` |
| 303 | 2026-07-03 | completed | Surface MT20 button presses as a distinguishable metric | `13bf859` `ead1217` |
| 302 | 2026-07-03 | completed | Sensor alert profiles as a config-count metric | `13bf859` |
| 301 | 2026-07-03 | completed | SAML / SSO configuration posture | `13bf859` |
| 300 | 2026-07-03 | completed | Webhook delivery log / failure tracking | `c34a6cc` `13bf859` |
| 299 | 2026-07-03 | completed | Top clients/applications/SSIDs by usage (org-wide "top N" summary) | `13bf859` |
| 298 | 2026-07-03 | completed | Adaptive policy overview counters | `13bf859` |
| 297 | 2026-07-03 | completed | Config templates inventory + per-network binding | `13bf859` |
| 296 | 2026-07-03 | completed | Cable/link partner discovery (CDP/LLDP) topology, org-wide | `13bf859` |
| 295 | 2026-07-03 | completed | Link aggregation (LACP) group membership, network-level config | `13bf859` |
| 294 | 2026-07-03 | completed | Org-wide PoE power-draw trend (organization summary) | `13bf859` |
| 293 | 2026-07-03 | completed | Dynamic ARP Inspection (DAI) trusted-port coverage warnings | `13bf859` |
| 292 | 2026-07-03 | completed | Rogue/unauthorized DHCP server detection per network | `13bf859` |
| 291 | 2026-07-03 | completed | RF profile assignment drift tracking | `13bf859` |
| 290 | 2026-07-03 | completed | SSID firewall rule counts (config drift, parity with MX) | `13bf859` |
| 289 | 2026-07-03 | completed | Add VLAN and static route inventory counts | `13bf859` |
| 288 | 2026-07-03 | completed | Add port forwarding / NAT rule counts (config drift) | `13bf859` |
| 287 | 2026-07-03 | completed | Add site-to-site VPN topology config (mode, hub count, subnets advertised) | `13bf859` |
| 286 | 2026-07-03 | completed | Add DHCP subnet utilization | `13bf859` |
| 285 | 2026-07-03 | completed | Add content filtering config-drift metrics | `13bf859` |
| 284 | 2026-07-02 | completed | Explicit guardrail: do not wire liveTools beta endpoints into passive collectors | `269ec6a` |
| 283 | 2026-07-02 | completed | tools/apidrift blind spot: beta-spec endpoints are invisible to drift detection | `57455d8` |
| 282 | 2026-07-03 | not planned | Per-AP radio status metrics (channel / width / DFS radar / tx power / power mode) | `cd76d8d` |
| 281 | 2026-07-02 | completed | Document has_beta_api production-risk in operator-facing docs | `7638f6e` |
| 280 | 2026-07-03 | not planned | Per-AP wireless health score metrics (performance / onboarding score) | `cd76d8d` |
| 279 | 2026-07-03 | completed | Add a read-only Early Access opt-in state metric | `281f899` `cd76d8d` |
| 278 | 2026-07-03 | completed | Add BetaAPISettings config block + per-org has_beta_api detection cache | `281f899` `cd76d8d` |
| 277 | 2026-07-03 | completed | Add exporter self-resource metrics (memory/CPU) | `f76d984` `6a8e5dc` |
| 276 | 2026-07-03 | completed | Add an explicit self-observability metric for total scrape API-call cost per cycle | `be1ed71` |
| 275 | 2026-07-03 | completed | Wire up OrganizationInventory.set_ttl_for_tier or remove the dead tier-TTL design | `567149c` |
| 274 | 2026-07-03 | completed | API requests by endpoint/method — replace status-code-only totals | `f76d984` `8084b8b` |
| 273 | 2026-07-03 | completed | Eliminate the duplicate per-network getNetworkHealthAlerts loop in AlertsCollector | — |
| 272 | 2026-07-03 | completed | Org-wide wireless packet loss by network (replace/augment per-network health loop) | — |
| 271 | 2026-07-03 | completed | Migrate RF channel-utilization to the org-wide endpoint | `4514bf9` `2cb500d` |
| 270 | 2026-07-03 | completed | Wire OrgRateLimiter into every collector's API calls, not just inventory | `30b0c3b` |
| 269 | 2026-07-01 | completed | Sensor-to-gateway connectivity (RSSI + last-connected) | `639526b` |
| 268 | 2026-07-01 | completed | Network-wide "currently alerting sensors" overview | `639526b` |
| 267 | 2026-07-01 | completed | Collect org-wide device statuses + availability change history | `639526b` |
| 266 | 2026-07-01 | completed | Firmware upgrade status & staged rollout tracking | `639526b` |
| 265 | 2026-07-01 | completed | Admin accounts & 2FA/SSO posture inventory | `639526b` |
| 264 | 2026-07-01 | completed | Add org-wide VPN stats (per-uplink-pair latency + data volume) | `639526b` |
| 263 | 2026-07-01 | completed | Add HA / warm-spare redundancy status | `639526b` |
| 262 | 2026-07-01 | completed | Add MX appliance performance score | `639526b` |
| 261 | 2026-07-01 | completed | Add appliance uplink bandwidth usage (bytes sent/received per uplink) | `639526b` |
| 260 | 2026-07-01 | completed | Air Marshal rogue AP / SSID-spoofing detection | `639526b` |
| 259 | 2026-07-01 | completed | Add network-wide wireless latency stats (device + client breakdown) | `639526b` |
| 258 | 2026-07-01 | completed | PSU/power-module redundancy status (org-wide, covers MS + other device types) | `0a21fec` |
| 257 | 2026-07-01 | completed | Add 802.1X / Secure Port authentication status per port | `0a21fec` |
| 256 | 2026-07-01 | completed | Add per-port STP status from the existing port-status payload | `0a21fec` |
| 255 | 2026-07-01 | completed | Camera quality & retention config as an info metric | `0a21fec` |
| 254 | 2026-07-01 | completed | Add per-uplink loss & latency history (wan1/wan2/cellular) | `0a21fec` |
| 253 | 2026-07-01 | completed | Wire up already-declared MV analytics metrics (people counting) | `0a21fec` |
| 252 | 2026-07-01 | completed | Populate MG cellular uplink status/signal (currently zero MG metrics exist) | `0a21fec` |
| 251 | 2026-07-01 | completed | Reconcile or drop MV_RECORDING_STATUS | `c533579` |
| 250 | 2026-07-01 | completed | Clean up dead MR metric enum entries | `c533579` |
| 249 | 2026-07-01 | completed | Stop constructing a new AsyncMerakiClient per org every FAST-tier cycle in MT collector | `86ced18` |
| 248 | 2026-07-01 | completed | Fix AlertsCollector's unbounded asyncio.gather fan-out | `b27c276` |
| 247 | 2026-07-01 | completed | Fix hardcoded stale service.version in OTel resource attributes | `640dafe` |
| 246 | 2026-07-01 | completed | Add missing MT sensor reading types (no2, o3, pm10, button) | `86ced18` `c533579` |
| 245 | 2026-07-01 | completed | Capture port errors/warnings from the port-status call already being made | `79c4fc5` `c533579` |
| 244 | 2026-07-01 | completed | Wire up the already-declared MX_SECURITY_EVENTS_TOTAL gauge (IDS/IPS + AMP events) | `4705139` `c533579` |
| 243 | 2026-07-01 | completed | Wire the Helm chart's readinessProbe to the app's own /ready endpoint | `8639c1b` |
| 242 | 2026-07-01 | completed | Fix the dead first-run API-key error path (and wrong --help env var) | `dff23c8` |
| 226 | 2026-06-26 | not planned | [test2] Feature request: MG cellular gateway metrics | — |
| 225 | 2026-06-26 | not planned | [test] Exporter crashes on startup with malformed API key | — |
| 221 | 2026-06-26 | completed | arm64 image broken: ModuleNotFoundError: No module named 'pydantic_core._pydantic_core' | `98f58db` `caf73c8` `700de3c` |
| 218 | 2026-07-03 | completed | Still hitting API limit | — |
| 214 | 2026-05-08 | completed | 429 Too Many Requests, retrying in 1 seconds | — |
| 213 | 2026-05-08 | completed | Failed to collect RF health metric | `b1f9456` |
| 212 | 2026-05-08 | completed | Feature Request: Allow to filter by networks | — |
| 199 | 2026-04-15 | completed | meraki_mr_radio_broadcasting | `120e351` |
| 186 | 2026-03-26 | completed | MX devices show device up intermittently | `d22d280` `4e40908` |
| 68 | 2026-03-13 | completed | MX67 Metric Devices | — |
| 8 | 2026-03-16 | completed | Dependency Dashboard | — |
