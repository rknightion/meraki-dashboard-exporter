# V1 readiness assessment — findings synthesis (accumulating)

## GH-SURVEY KEY FACTS (complete)
- 276 issues: 66 open, 210 closed. 172 bug-bash `[F-xxx]` all closed (#334–#507, M9=111/M10=61).
- Open backlog: M4 rate-limit hardening (8: #270 P0 OrgRateLimiter wiring, #271-277), M5 beta-API (7: #278 P0 plumbing), M6 config/security-drift metrics (24), M7 usability/DX (11: #309 cardinality controls P1, #310 log_format P1, #311 NetworkFilter on /status P1, #313 OTLP metrics exporter, #314 TLS for OTLP), M8 deferred (12: #320 async SDK eval, #321 SM, #324 SNR/RSSI), M11 (#339 OTLP epic). Non-roadmap: #218 REAL USER rate-limit complaint (large env), #332 MT20 button deferred, #170 renovate.
- Issue template: header line `**Area:** x · **Type:** y · **Priority:** Pn · **Effort:** S/M/L · **Milestone:** Mn — name`; sections `### Goal / data unlocked`, `### Meraki API`, `### Files to touch`, `### Notes / risks`, `### Acceptance criteria` (3-box generic / 7-box new-metric); footnote `<sub>Auto-generated…</sub>`.
- Labels: dual priority (`P0`-`P3` AND `priority: critical/high/medium/low`), `roadmap` or `bug-bash`, compact `area:*` (mr ms mx mt mg mv org network-health clients licensing core ops config web-ui docs deploy otel dashboards dx beta-api).
- Project #2: fields Status(Todo/In Progress/Done), Priority(P0-P3), Effort(S/M/L), Type(new-metric/feature/qol/ops/beta-api), Area(20 vals). Organized by Milestone. Status lags closure for M1-M3 items (9 "In Progress" actually done — cleanup opportunity).
- Milestones all open-state M1–M11; M9/M10 fully closed content-wise.
- 7 parked dashboard findings F-150–F-156: NO issues exist yet (all bug-bash issues closed) → must create.
- Dedupe watch: #270/#271-277 (rate limit), #309-#319 (DX/ops), #218, #313/#339 (OTLP), #320 (async SDK), #321 (SM), #324 (SNR/RSSI), #318 (Helm sizing docs), #316 (dashboard CI check), #315 (Grafana provisioning example).

## DEP LANE (lane-deploy) — part 1 received; verdict: strong, no P0/P1
- DEP-01 | P2 | Helm/ops | replicaCount>1 harmful (no leader election/sharding; N× API usage + dup series). Fix: warning + template fail when >1. values.yaml:6, deployment.yaml:11.
- DEP-02 | P3 | Helm | No NetworkPolicy template. Optional networkPolicy.enabled (ingress metrics port, egress 443/OTLP).
- DEP-03 | P3 | Helm | Default RollingUpdate double-scrapes on upgrade at replicas=1 (maxSurge). Fix: strategy Recreate/maxSurge 0. PDB N/A.
- DEP-04 | P3 | Release | No pip/PyPI artifact; pyproject lacks [build-system] + [project.scripts]. Decide: add backend+publish, or declare container/Helm-only.
- DEP-05 | P3 | Multi-arch | armv7 dead capability (Dockerfile:33-37, Makefile) — never CI-built/published (shared reusable builds amd64+arm64 only). Fix: drop armv7 branch.
- DEP-06 | P3 | Local ops nits | make docker-compose-up `--build` no-op (image-only compose); local builds lack APP_VERSION build-arg (report 0.0.0+dev — note in README); Docker healthcheck /health + restart:unless-stopped does NOT self-heal on unhealthy outside k8s — document.
- Coverage: helm lint/template all permutations OK; release automation + provenance GOOD; image hardened.

## DOC LANE (lane-docs) — interim (sub-lanes pending)
- DOC-01 | P1 | docs/security | SERVER__API_TOKEN (config_models.py:339; app.py:179,784,813 guards POST /api/collectors/trigger + /api/clients/clear-dns-cache) undocumented in README/.env.example/security.md (only in generated config.md). Fix: document + default-unauthenticated posture note.
- DOC-02 | P1 | docs | Missing v1 customer docs: PII/privacy page, upgrade/migration guide, metric stability/deprecation policy, FAQ, support matrix (MX/MG/MV best-effort warning belongs there), troubleshooting decision tree. Existing OK: scaling-guide.md (sizing tiers), rate-limit budget, scrape config in integration-dashboards.md. Multi-org only passing mention.
- DOC-03 | P3 | README:264 | Endpoint inventory omits `/` landing, /clients HTML, POST /api/clients/clear-dns-cache, POST /api/collectors/trigger.
- Checked-OK: README quickstart mechanically valid; getting-started accurate; regional base URLs + network-filter + webhook + OTEL env vars match .env.example.

## DEP LANE part 2 — checked-and-OK (complete; lane done)
- Dockerfile/compose/entrypoint hardened & correct (non-root, healthcheck honors port override, APP_VERSION wired). .env with real key is gitignored (verified untracked).
- Probes RIGHT: /health liveness w/ dead-man 503; /ready gated on FAST+MEDIUM first cycle; chart wires liveness→/health readiness→/ready.
- Helm chart: lint clean; apiKey/existingSecret/both/neither + otel validations hard-fail correctly; full securityContext; SA token not mounted; ServiceMonitor optional; configmap env names verified real.
- Versions consistent (pyproject=manifest=appVersion 0.31.0); release-please→container-publish reusable: native multi-arch, cosign keyless, provenance attestation, SBOM, Trivy; chart to oci://ghcr.io/rknightion/charts (signed). Consumption: image ✅ chart ✅ pip ❌ (DEP-04 decision).
- CI: SHA-pinned actions, least-priv, ci-success gate, docker-build-test asserts non-root.
- Note: examples/ contains ONLY a pytest example (misleading dir name; real config examples = .env.example/compose/values.yaml).

## GAP LANE (lane-v1gaps) — part 1/3: GATES V1
- Context: 245 metrics/34 endpoints; spec path counts: org 175, appliance 102, wireless 98, networks 77, switch 56, sm 43, devices 38, camera 29, cellularGateway 16, licensing 15, sensor 13, insight 4.
- GAP-01 | P0 | release contract | No metric-name stability contract/deprecation policy for 1.0. Scope: docs/stability.md (Stable vs Experimental tiers, rename policy dual-publish ≥1 minor, labels-additive note) + pre-1.0 rename sweep first. High conf.
- GAP-02 | P1 (MSP borderline P0) | multi-org | org_id is all-or-exactly-one (config_models.py:447); no ORG_IDS list / org include-exclude (NetworkFilter is network-scoped). Scope: MERAKI__ORG_IDS CSV + org filter w/ fail-fast + meraki_org_filter_* gauges. High conf.
- GAP-03 | P1 | docs | Device-down detection latency undocumented (MEDIUM 300s tier + Meraki-side lag ⇒ ~10+min worst); README oversells webhooks ("real-time") — webhooks only COUNT events, don't flip meraki_device_up. Scope: data-freshness doc w/ per-tier staleness table + alert `for:` guidance; soften README. Verify Meraki offline-detection delay figure.
- GAP-04 | P1 | webhooks | Receiver not deployable as documented: Meraki requires HTTPS receiver; exporter is HTTP-only, chart has no ingress.yaml, docs show http://. Scope: docs TLS-termination example + chart ingress block; native TLS later. Verify current Meraki HTTPS webhook rule.
- GAP-05 | P1 | security | Endpoint exposure half-finished: /clients (PII), /status, /cardinality, /metrics unauth; POST /api/collectors/trigger open by default (API-budget burn); no TLS. Scope v1-min: network-exposure doc + extend api_token to UIs and/or ui_enabled=false; native TLS roadmap.

## DOC LANE FINAL (supersedes interim) — 12 findings; all 4 generated docs IN SYNC (docgen no-diff)
- DOC-01 | P1 | SERVER__API_TOKEN undocumented (security.md no auth section; .env.example lines 30-31; README). Guards only 2 POSTs (app.py:179-195,784,813); GETs always unauth. Fix: security.md "Endpoint authentication" subsection + .env.example line + README bullet.
- DOC-02 | P1 | Missing pages: PII/privacy (CLIENTS__ENABLED data), upgrade guide, metric stability policy, FAQ, support matrix (MX/MG/MV best-effort), troubleshooting tree. Multi-org only passing mention.
- DOC-03 | P2 | security.md:84 says `MERAKI_API_KEY` — wrong var (real: MERAKI_EXPORTER_MERAKI__API_KEY).
- DOC-04 | P2 | otel.md:45-48 false claim SAMPLING_RATE not a pydantic field (it is: config_models.py:304-312).
- DOC-05 | P3 | otel.md:26-28 says plaintext gRPC required; OTEL__INSECURE=false exists (config_models.py:293).
- DOC-06 | P2 | api-call-audit.md stale internal snapshot in customer nav (zensical.toml Development). Fix: drop from nav or banner.
- DOC-07 | P2 | .env.example:97 documents nonexistent CLIENTS__DNS_SERVER (extra="ignore" silently no-ops). Remove or implement.
- DOC-08 | P2 | .env.example:46 default-enabled list stale — missing `mtsensoralerts` (8 not 7; config_models.py:378-388).
- DOC-09 | P3 | config.md:107 note names nonexistent PATH_PREFIX/ENABLE_HEALTH_CHECK — baked into scripts/generate_config_docs.py:291-295 (docgen won't fix; edit generator).
- DOC-10 | P3 | scaling-guide.md small-tier table contradicts its own "defaults work" note.
- DOC-11 | P3 | deployment-operations.md:113 LogQL `|= "Failed to collect"` may match no real log string (low conf — re-check manually).
- DOC-12 | P3 | README:264/getting-started endpoint list incomplete (missing /, /clients, 2 POSTs, 5 cardinality sub-routes; generated endpoints.md complete).
- OK: all generated docs in sync; 245 metric names cross-checked 0 missing; 8 enum members DEAD (never constructed) — optional code cleanup; internal links resolve; README quickstart valid.

## GAP LANE part 2/3
- GAP-06 | P1 | scaling docs | No sharding/multi-instance/HA guidance (shard-by-org works today; RATE_LIMIT_SHARED_FRACTION exists for budget sharing; 2 replicas double calls). Scope: "Scaling out & HA" page.
- GAP-07 | P1 | onboarding | No starter Prometheus alert rules. Scope: examples/prometheus-rules.yaml + chart prometheusRule template (~15 curated rules w/ for: durations tied to freshness table).
- GAP-08 | P1 | docs | v1 messaging vs "MX/MG/MV untested" warning — need formal support matrix page (per product line supported/best-effort/not-collected; SM/Insight as explicit non-goals).
- GAP-09 | P2 | connectivity | No proxy/custom-CA support (api/client.py:150 doesn't pass requests_proxy/certificate_path; likely works via HTTPS_PROXY untested/undocumented; read-only rootfs makes CA mount non-obvious).
- GAP-10 | P2 | credentials | No _FILE/secrets_dir key loading; no rotation without restart; single key only (per-org keys tie to GAP-02).
- GAP-11 | P2 | privacy | No PII controls beyond on/off: client series carry client_id/mac/description/hostname (clients.py:88-170) + unauth /clients page. Scope: ANONYMIZE_MACS, LABEL_ALLOWLIST, privacy doc.
- GAP-12 | P2 | firmware | No per-device firmware version/up-to-date compliance metric (only org upgrade event counts; device inventory firmware field unused; spec has FirmwareUpgradesByDevice + NetworkFirmwareUpgrades).
- GAP-13 | P2 | config granularity | No sub-collector enable/disable (8 coarse names; "device" spans 6 types + ~10 subs). Scope: dotted names device.mv etc. [OVERLAPS existing issue #309 — check]
- GAP-14 | P2 | ops docs | No troubleshooting runbook (symptom→check→fix: 401/403, org API disabled, filter resolved=0, readiness gating, backoff, 429, shedding, webhook secret).
- GAP-15 | P2 | chart | No NetworkPolicy/PDB/PrometheusRule templates; config block covers ~12 settings (extraEnv cookbook needed). [overlaps DEP-02/03, GAP-07]

## APIORG LANE part 1 — coverage table all-OK except:
- **APIORG-01 | P0 | network-health | rf_health.py:220-222,257-259 reads latest_bucket "utilization"/"wifi"/"nonWifi" but spec v1.72.0 fields are utilizationTotal/utilization80211/utilizationNon80211 ⇒ ALL channel-utilization gauges silently 0. Tests mock the WRONG keys too (test_network_health_collector.py) so suite stays green. Dead RFHealthData block :191/:194 also wrong. Verify live-API then fix + fix fixtures.**
- APIORG-02 | P2 | licensing | Subscription-licensing orgs fall to per-device branch (license.py:150) → getOrganizationLicenses 400s (only "404" special-cased at L183) → zero license metrics + retry noise. Fix: treat 400/unsupported like 404 + prefer overview states counts. Verify live-API.
- APIORG-03 | P3 | licensing | Per-device expiry recomputed locally (hand-rolled date parse, hardcoded 30d) vs API's states.expiring counts w/ server thresholds.
- All other org/network fetchers verified OK (pagination/timespans/models correct; NetworkFilter law held everywhere; sanctioned bypasses correct).

## CFG LANE part 1 (+full settings inventory captured in report)
- **CFG-01 | P1 | Documented CSV form for COLLECTORS__ENABLED/DISABLE_COLLECTORS HARD-CRASHES at boot (SettingsError; set[str] w/o NoDecode/_split_csv shim unlike NetworkFilterSettings; .env.example:45-48 shows the crashing CSV form). Reproduced.**
- CFG-02 | P1 | Typo'd/unknown MERAKI_EXPORTER_* env vars silently ignored (extra="ignore"); startup env dump prints them (looks applied). Fix: startup reconciliation WARN.
- CFG-03 | P2 | China timeout auto-bump dead code: checks "china" in URL but real endpoint is api.meraki.cn (config.py:87 vs config_constants.py:25). Reproduced.
- CFG-04 | P2 | api_base_url accepts any string (no URL validation).
- CFG-05 | P2 | log level uppercase-only regex rejects "info" (config_models.py:575).
- CFG-06 | P2 | No proxy/custom-CA passthrough (SDK supports requests_proxy/certificate_path). [= GAP-09]

## DOC 2/2 — CLAUDE.md corrections (apply in task #4)
- tests/CLAUDE.md: remove large_org pytest-plugin claim + 2 file_map bullets + test_large_org_fixture.py entry (commit 0fbb195); counts 49→57 unit modules (58 files), 15→17 device tests; add force_debug_log_capture fixture; add ClientFactory.
- core/CLAUDE.md: async_utils.py line — batch_with_concurrency_limit() is NOT there (it's in error_handling.py); async_utils = ManagedTaskGroup, with_timeout, managed_resource, AsyncRetry, chunked_async_iter (24bacf3 deleted CircuitBreaker/safe_gather/rate_limited_gather).
- .github/CLAUDE.md: stale.yml gone → replace with release-please-lock.yml (regenerates uv.lock on release PR under PAT); harden-runner list: scorecard, ci, release-please-lock, api-drift (NOT stale.yml).
- charts/CLAUDE.md: appVersion "0.28.0" → 0.31.0 (or soften to "tracks release").
- tools/apidrift/CLAUDE.md: scanner still documents dead `_request("opId")` wrapper matching (low priority nuance).
- All other CLAUDE.md files verified accurate. AGENTS.md is a symlink to root CLAUDE.md.

## GAP LANE part 3/3 (COMPLETE)
- GAP-16 P2 upgrade/migration doc absent; GAP-17 P2 Insight not collected (0/4 endpoints, license-gated collector); GAP-18 P3 SM not collected (0/43, state as non-goal in matrix); GAP-19 P3 MV analytics minimal/MT excellent/MG no usage-history (matrix task); GAP-20 P3 subscription-licensing unverified (= APIORG-02); GAP-21 P3 comparison-vs-community-exporters page; GAP-22 P3 webhook→state-metrics future; GAP-23 P3 native TLS listener (exporter-toolkit parity).
- NOT gaps (verified good): regional bases, network filter, config-change audit, license expiry, scaling docs to 5k, probes/dead-man, air marshal, API self-protection, 13 dashboards exist.
- V1 GATE LIST (ruthless): GAP-01 stability contract, GAP-02 org include/exclude (or document per-org sharding + demote), GAP-03 freshness doc + README webhook fix, GAP-04 webhook HTTPS reality, GAP-05 exposure/threat-model doc, GAP-06 sharding/HA doc, GAP-07 starter alert rules, GAP-08 support matrix. (5/8 docs-only.)

## SEC LANE (COMPLETE) — no P0 on default posture
- SEC-01 | P1 | Entire HTTP surface unauth + plaintext; /clients leaks MAC/IP/hostname/username; /cardinality leaks label values; api_token guards only 2 POSTs. Fix: docs + extend token to sensitive GETs or ui_enabled flag + NetworkPolicy.
- SEC-02 | P1 | Client tracking = PII in Prometheus; zero GDPR/privacy docs. Opt-in default good. Fix: privacy doc + hash/suppress option. [= GAP-11]
- SEC-03 | P2 | Webhook SUCCESS path labels org_id/alert_type from attacker-controlled payload when require_secret=false → cardinality bomb (failure path was hardened F-051, success path NOT). Fix: validate org_id vs known set, bound alert_type; refuse insecure combo w/o explicit flag.
- SEC-04 | P2 | Base image tag-pinned not digest-pinned; uv tarball no checksum.
- SEC-05 | P2 | No NetworkPolicy template [= DEP-02/GAP-15].
- SEC-06 | P3 | chart doesn't expose OTEL__INSECURE knob.
- SEC-07 | P3 | config_logger masking is substring-heuristic (allowlist-by-omission future risk).
- SEC-08 | P3/info | webhook JSON depth/CPU minor; alert_data not labelled (good).
- OK list: constant-time compares, body cap, SecretStr e2e, autoescape XSS-clean, container/chart hardening, SHA-pinned CI, cosign/SBOM, OTel spans clean, .env ignored. NOTE: WebhookMetricsCollector (collectors/webhook_metrics.py) is DEAD CODE — never instantiated (network_id label would be a risk if wired). NOTE: pyproject pins meraki==3.3.0 (CLAUDE.md said 3.2.0 — fixed).
- SEC v1 priorities: SEC-01+05, SEC-02, SEC-03.

## CFG LANE (COMPLETE) — 18 findings (2 P1, 8 P2, 8 P3)
- CFG-07 P2 bad-key 401 dumps ~2KB frame-locals blob after one clear line (inventory warm_cache); fix: concise actionable 401 message, traceback at DEBUG.
- CFG-08 P2 no JSON log format (LogfmtRenderer hardcoded, logging.py:148) [= existing issue #310 P1! DEDUPE].
- CFG-09 P2 .env.example drift [= DOC-07/08] + CLIENT_SIGNAL_QUALITY_* absent entirely.
- CFG-10 P2 no --check/--validate dry-run mode (__main__.py).
- CFG-11 P3 config.md "Additional Runtime Options" block wrongly claims SAMPLING_RATE not-pydantic (generator:356-367) [= DOC-04 sibling].
- CFG-12 P3 log_configuration() dead stub; startup summary logged TWICE (config_logger.py:79; 123-290 + 291-381).
- CFG-13 P3 bare MERAKI_API_KEY special-cased in env dump but not consumed (add alias or stop referencing).
- CFG-14 P3 /health stays 200 ~45min under total auth failure (liveness 3×slow); /ready correct; document + surface authenticated=false on /status.
- CFG-15 P3 org_id unvalidated. CFG-16 P3 no listener TLS (state in security.md). CFG-17 P3 .env.example "exits at startup" wording imprecise (RuntimeError only if ALL orgs empty, during warm-up; verify terminal). CFG-18 P3 config.md PATH_PREFIX/ENABLE_HEALTH_CHECK ghost note (generator:291) [= DOC-09].
- OK: friendly missing-key error, interval cross-validation, SecretStr redaction verified, filter CSV+JSON parsing, safe defaults, /ready gating correct, JSON-form enabled_collectors works.

## APIORG part 2 + supplement (COMPLETE)
- APIORG-04 P3 dead RFHealthData block (rf_health.py:186-199) — delete or wire (single edit closes APIORG-01 too).
- APIORG-05 P2 air marshal: spec now has bounded encryption(WEP/WPA/open)/types(rogue/spoof) enums — add threat_type breakdown + fix stale module docstring. Verify live.
- APIORG-06 P2 channel-util per-network loop; org-wide bulk getOrganizationWirelessDevicesChannelUtilizationByNetwork/ByDevice exists (verify field names/pagination first). [check dupe vs existing #271!]
- APIORG-07 P3 latency-stats: pass fields="avg" to skip unused rawDistribution payload (latency_stats.py:104-107,137-140).
- APIORG-08 P3 network_health_collectors/CLAUDE.md drift: claims channel-util takes no resolution/timespan; code pins timespan=600/resolution=600/perPage=100 (rf_health.py:123-130). FIX CLAUDE.md.
- APIORG-02 corroborated + WORSE: subscription-org 400 → collect() None → org_collection_status=0 permanently (stuck-red health). Fix (b) overview-states preferred.
- APIORG-09 P3 firmware _PENDING_STATUSES {scheduled,pending,started} not spec-attested (no enum; verify live w/ in-flight upgrade).
- APIORG-10 P3 app-usage percentage 0-100 vs 0-1 not spec-pinned (verify live; ensure HELP says 0-100).
- OK: pagination/perPage/timespans all bounded correctly; units kb correct for client_overview; NetworkFilter law enforced everywhere; no deprecated ops.

## TCI LANE (COMPLETE)
- **TCI-01 | P0 | CI RED ON MAIN NOW: apidrift conformance exit 3 — DevicePowerModuleStatus.network typed PowerModuleNetworkRef (domain_models.py:651, commit 10c9d87) vs spec bare `object` → WARNING → exit 3. Fails last 5 pushes + the pending 0.32.0 release PR. Fix: loosen model to dict OR demote submodel-vs-bare-object to INFO in conformance.py (preferred). Do NOT || true.**
- TCI-02 P2 weekly slow-tests job red forever: pytest -m slow collects 0 (exit 5) since large-org fixtures deleted (0fbb195). Tolerate exit 5 or drop job.
- TCI-03 P2 docker-build-test never serves: add /health+/metrics smoke on built container.
- TCI-04 P2 no helm lint/kubeconform in CI (chart published unvalidated). Verify shared reusable doesn't lint.
- TCI-05 P2 no golden-exposition metrics test (units/label-set regression net).
- TCI-06 P3 no container-structure test.
- TCI-07 P2 chart version 0.1.0 unannotated in release-please BUT lane-deploy verified publish overrides via helm package --version ${TAG#v} → NOT a bug; downgrade to P3 doc/consistency (annotate or comment why static). CROSS-LANE RESOLUTION: DEP report confirms override.
- TCI-08 P3 redundant pyproject extra-files entry in release-please-config.
- TCI-09 P3 codecov patch 70% not informational (red X noise).
- OK: 1314 tests ~20s 87% cov, mypy strict clean; metric-OUTPUT assertions strong (113 gauge-value); NetworkFilter e2e tested; expiration integration 730 lines; cardinality regression tests; release-please PAT works (security workflows green on release PR).

## MET LANE parts 1&2 (part 3 pending)
- 253 metric names (238 enum + 15 literals); nearly all Gauges; docs generated & byte-reproducible (no drift).
- MET-01 | P1 | _total on GAUGE snapshot counts (org networks/devices/licenses/admins/ms_ports/vpn_peers/firewall_rules/bluetooth_clients/air_marshal etc.) — v1-BLOCKING rename wave (note: F-091 consciously kept these — re-litigate).
- MET-02 | P1 | _total on WINDOWED/resetting gauges (org_api_requests_total "last hour" flagship; config_changes; ms_port_packets 5-min; mr packets; connection_stats; failed_connections; alerts totals; usage_total_kb) — most dangerous class. v1-BLOCKING.
- MET-03 | P1 | _count vs _total inconsistency for identical windowed semantics (F-091 swept only 2 families).
- MET-04 | P1 | non-base units in names: _kb/_mb (org usage, client usage, vpn usage, app usage, ssid usage), _kbps (download/upload — DOUBLE BUG: value is kiloBYTES/s per F-065), _ms (4 latency families), _minutes/_days (login security), _watthours (PoE). v1-BLOCKING; verify true units via spec before scaling.
- MET-05 | P1 | _percent (10) vs _percentage (3) inconsistency; percent-vs-ratio question. v1-BLOCKING.
- MET-06 | P1 | self-metric typing errors: cardinality_analyzed_total is a GAUGE (cardinality.py:117); collection_errors_total_expired COUNTER doesn't end _total (metric_expiration.py:91); cache_size_tracked_metrics misnamed concat (metric_expiration.py:96).

## MET LANE part 3/3 (COMPLETE)
- MET-07 | P2 | client metrics label by mac+hostname+description (PII, unbounded); OFF by default via CLIENTS__ENABLED=false. Decide label contract pre-v1: drop mac/hostname/description from numerics + meraki_client_info join metric. [= APIORG-12, GAP-11, SEC-02 — MERGE]
- MET-08 | P2 | mutable name labels (name/org_name/network_name/port_name) denormalized on every series → churn/orphans on rename; inventory.py:143 already applies the right pattern to filter gauges. Pre-v1 DECISION: accept+document or move to _info joins.
- MET-09 | P2 | ~12 windowed metrics' HELP omits the window (verified vs fetcher timespans; list captured). Cheap, non-breaking, flows to docs via docgen.
- MET-10 | P2 | self-metrics strong; 2 gaps: (a) NO meraki_exporter_build_info{version,commit}; (b) no real org API-budget headroom gauge.
- MET-11 | P3 | 7 dead enum members never instantiated (ORG_LOGIN_SECURITY_ENABLED, ORG_LOGIN_SECURITY_IP_RESTRICTIONS_ENABLED, NETWORK_CLIENTS_TOTAL, NETWORK_DEVICE_STATUS, NETWORK_TRAFFIC_BYTES, HEALTH_ALERT_INFO, ORGANIZATION_HEALTH_ALERTS_TOTAL) — delete. [DOC lane said 8; reconcile at filing]
- MET-12 | P3 | duplicate webhook counters (events_received_total vs events_total same HELP) + meraki_org_api_requests_total vs meraki_exporter_api_requests_total name collision w/ opposite semantics — disambiguate HELP.
- MET-13 | + | docs generated, byte-reproducible, zero drift (strength).
- Cardinality at 5org/500net/5k-dev: ~0.5-1M series, all bounded labels (MS ports #1 driver ~34 families/port; MR radio+loss #2). No default-config bomb. Watch: MS port volume, clients-if-enabled.
- Recommend ONE coordinated "metric naming v1 sweep" issue for MET-01..06 (all touch metrics_constants.py + docgen together).

## APIORG SUPPLEMENT 2 (2 CORRECTIONS + new)
- **APIORG-11 | P1 | config.py _collect_configuration_changes (L456-483) does NOT filter rows by get_allowed_network_ids (fatal-rule violation; alerts.py:424-425 does it right). Inflated config-changes count under active NetworkFilter. Fix: keep rows w/ networkId None-or-allowed. High conf, structural.**
- **APIORG-12 | P1→triage-P2 | per-client metrics (client_status, usage×3, app_usage×3, rssi, snr) labeled CLIENT_ID+MAC, emission path UNCAPPED (max_clients_per_network caps only ClientStore; only signal-quality fan-out capped). NOTE: agent claimed "on by default" but ClientsCollector self-gates on CLIENTS__ENABLED=false default (per DOC lane) — effective default OFF. = MET-07; merge. Product decision: cap metrics path + drop mac or client_id.**
- APIORG-13 | P2 | assurance alerts perPage default 30 vs max 300 → ~10x more calls. Add perPage=300.
- APIORG-14 | P2 | getOrganization single-org fallback unwrapped by validate_response_format (alerts.py:301-304, config.py:219-222).
- APIORG-15 | P3 | applicationUsage batches 1000 client-ids in one GET query param → URL-length/414 risk; drop to 50-200.
- APIORG-16 | P3 | strong_passwords_enabled metric from deprecated always-true field — drop.
- APIORG-17 | P3 | unknown alert severities silently dropped from by-severity summary — bucket "other".

## APIDEV LANE (COMPLETE) — no P0/P1; pagination clean everywhere; 36/36 SDK methods exist
- APIDEV-01 | P2 | getDeviceCameraAnalyticsZones + getDeviceCameraAnalyticsLive both DEPRECATED in v1.72.0 (mv.py:219,268) — whole MV analytics domain at risk; migrate (AnalyticsOverview/boundary endpoints) or comment+roadmap. Verify replacement live.
- APIDEV-02 | P2 | mx_uplink_health.py:125-159 last-write-wins across per-destination-IP rows → loss/latency reflect arbitrary destination. Fix: aggregate max (worst-path) per (serial, interface).
- APIDEV-03 | P3 | ×1024 for kB fields (ms.py usageInKb etc., base.py memory) vs ×1000 for kbps in same functions — SI inconsistency ~2.4% over-report; standardize ×1000 for data-volume (memory KiB defensible).
- APIDEV-04 | P3 | getDeviceAppliancePerformance no timespan → nondeterministic window (spec optional [1800..1209600]); pass explicit.
- APIDEV-05 | P3 | SDK 3.3.0 vs docs 3.2.0 (root CLAUDE.md fixed this session).
- APIDEV-06 | P3 | vpn stats timespan=300 may yield sparse summaries — verify live.
- OK: pagination clean (main mandate); validate_response_format on all 40; nested schemas verified; unit conversions otherwise correct; product-type/network filtering per law.
- apidrift: mature+CI-wired; automates shape-drift/deprecation for __meraki_op__-annotated models; does NOT cover pagination/param-bounds/units/aggregation semantics. Recommendation: annotate more device-side models.

## LIVE-API VERIFICATION RESULTS (main thread, org 1019781 "Knight", net L_676102894059020286)
- **APIORG-01 REVISED P0→P1**: LIVE returns utilization/wifi/non_wifi + start_ts/end_ts — SPEC IS WRONG (utilizationTotal/... names don't exist on the wire for this legacy endpoint). Code's "utilization"/"wifi" reads are CORRECT; real bugs: (1) code reads "nonWifi" but live is "non_wifi" → all utilization_type="non_wifi" series silently 0 (VERIFIED); (2) _latest_bucket sorts by endTime→endTs but live is end_ts → sort inert (benign now: single bucket at timespan=600). Fix: non_wifi key + add end_ts sort key + fix test fixtures to live shape + document spec-vs-live discrepancy (apidrift caveat).
- APIORG-10 RESOLVED: live percentage is 0-100 (sums ≈100) — code correct; just add "0-100" to HELP.
- APIORG-02: Rob's org is CO-TERM (status OK + licensedDeviceCounts) — subscription case not live-verifiable here; structural fix stands, keep verify note.
- APIORG-09: live history shows only Canceled/Completed (note: single-L "Canceled" vs spec text "Cancelled"); no in-flight upgrade → pending-statuses set unverifiable now; keep as-is with verify note.
- TCI-01 fix direction CONFIRMED: live power-modules `network` = structured object {"id": ...} → PowerModuleNetworkRef model is RIGHT, spec is just untyped. Correct fix = demote submodel-vs-bare-object to INFO in apidrift conformance.py (NOT loosening the model to dict).

## APIORG FINAL (supplement 3) — 23 findings total
- APIORG-18 | P2 | api_helpers._fetch_devices_direct (L257-300) does NOT reapply NetworkFilter (networks sibling does) — latent (fires only when inventory None). Mirror the sibling.
- APIORG-19 | P2 | inventory.get_login_security dead code (zero prod callers); config.py fetches uncached every SLOW cycle. Route through cache or delete method.
- APIORG-20 | P3 | discovery single-org getOrganization unwrapped by validate_response_format.
- APIORG-21 | P3 | getOrganizations without total_pages="all" (perPage default 9000 → negligible; consistency only).
- APIORG-22 | P3 | single_request_timeout default 30s low for large-org total_pages="all" fetches — doc/default review.
- APIORG-23 | P3 | product_types filter asymmetry cached-vs-fallback path.
- PEP 758 unparenthesized except is VALID py3.14 — ruled out as false alarm (twice: also scale lane).
- APIORG-02 TRIPLE-corroborated.

## SCALE LANE (COMPLETE) — THE decisive lane
Capacity: SMALL ~0.43 rps (4% budget) fine. LARGE-1org (500 nets/5k dev): ~17.8 rps demand = 178% of 10rps org budget; NetworkHealth alone 3,200 calls/cycle ≥320s > 240s timeout → times out EVERY cycle. Practical single-org envelope today: ~≤150-200 wireless nets / ≤1,500-2,000 devices. LARGE-5org per-org OK (~36%/org) except global-bucket ceiling.
- **SCALE-01 | P0 | shared 10k max_cardinality_per_collector keyed by collector_name="DeviceCollector" for ALL device sub-collectors → silently Gauge.remove()s LIVE series from ~10 48-port switches / ~600 APs up; permanent shed/recreate flapping at scale (metric_expiration.py:322-368, collector.py:646-652). Fix: per-sub-collector/per-family budgets + scale default + alarm-don't-delete.**
- **SCALE-02 | P0 | NetworkHealth 8 calls/wireless-net/300s (network_health.py:349 bundle) unrunnable at 400W. Fix: org-wide ChannelUtilizationByDevice migration (perPage 1000; = existing issue #271!), per-endpoint interval gating, doc ceiling.**
- SCALE-03 | P1 | aggregate demand 178% of org budget at LARGE-1org — publish quantitative sizing formula + land reductions.
- SCALE-04 | P1 | rate limiter porous 3 ways: (a) one token per DECORATED METHOD not per HTTP request (pagination/loops under 1 token); (b) network_id/serial-first fetchers mis-keyed to global bucket (rf_health, latency×2, air_marshal, mv×3, mt_alerts) → single org can draw ~20rps & multi-org serializes on one global 10rps bucket; (c) undecorated sites acquire nothing (ms.py:1488 STP, mr/performance.py:922 packet-loss-byNetwork, mt.py:305 sensor readings). [REFINES existing P0 issue #270]
- SCALE-05 | P1 | RSS multi-GB at LARGE vs published 512Mi sizing (registry 0.6-1.1M series clients-off; ClientStore no global cap; DNS caches unbounded; CardinalityMonitor retains full label lists). Fix sizing table + caps.
- SCALE-06 | P1 | clients collector: 9 families via raw .labels().set() → NEVER expiration-tracked (leak for process lifetime); hostname/description attacker-influenced; app-usage client×app uncapped; signal-quality 1 call/client (80k calls/600s @scale). Fix: _set_metric routing, caps, opt-in labels. [merges w/ APIORG-12/MET-07]
- SCALE-07 | P2 | MV per-camera ×3 (live analytics @300s) + global-bucket keyed; own interval/off-default.
- SCALE-08 | P2 | getDeviceAppliancePerformance 1/MX/300s no bulk alternative; gate 900s/document.
- SCALE-09 | P2 | org-wide channel-util endpoints exist (ByDevice/ByNetwork, perPage 1000) — replacement for rf_health per-network loop; NO org-wide equivalent for conn-stats/failed/latency/air-marshal (interval-gate those instead). [= #271 + APIORG-06]
- SCALE-10 | P2 | perPage at SDK defaults: memory-history none (default 10 vs max 20 → 500 pages/cycle @5k dev, devices/base.py:106-112); assurance alerts default 30 vs 300 [= APIORG-13].
- SCALE-11 | P2 | MEDIUM polls re-read 30-60min windows every 300s (conn-stats 1800, failed/air-marshal/latency 3600, port overview 43200) — per-endpoint intervals cut NetworkHealth ~8W→4.7W.
- SCALE-12 | P2 | default shared_fraction=1.0 + docs recommend full budget — noisy-neighbor; default 0.8 + doc AFTER volume reductions land.
- SCALE-13 | P3 | mt.py:305 all-serials query param + undecorated; SCALE-14 P3 DNS cold fan-out > timeout, lazy eviction; SCALE-15 P3 cardinality monitor O(series) walk/60s retains label lists; SCALE-16 P3 to_thread default pool ~cpu+4 threads caps real concurrency (250m CPU pod ≈ 5) — batch knobs no-op above it; SCALE-17 P3 devices/CLAUDE.md STALE: claims ms.py uses raw .labels().set() w/o tracking but ms.py has 46 _set_metric sites (this staleness inverts cardinality reasoning) → FIX CLAUDE.md.
- OK list: tier loops don't self-overlap; startup sequential + jitter; inventory rate-limited/warmed; MS org-level path + perPage maxed; alerts per-network loop already removed; OrgHealthTracker gates 6 collectors; limiter self-metrics real; org-first fetchers key correctly (refuted a sub-audit claim); no liveTools; clients off by default.

## RES LANE (COMPLETE) — live-run verified
- **RES-01 | P1 (v1-blocker) | Total API failure reported as SUCCESS — LIVE-CONFIRMED w/ fake key: coordinators swallow all failures (device.py:364-365, organization.py:308-309, network_health, config, mt.py:169-170 bare try/except + continue_on_error=True org fetches) → collect() records success → /ready 200, /health 200 forever, success_timestamp advances, failure_streak 0, /status 100%. Fix: "collected nothing" = failure (coordinator re-raise on org-fetch failure or all-org-task failure; or manager treats 0-updates+errors as failure; min: gate readiness on api 200s).**
- RES-02 | P2 | ManagedTaskGroup never propagates child failures (async_utils.py:146-206 logs only) — structural root; add failed_count/raise_on_all_failed.
- RES-03 | P2 | 240s timeout cancels coroutine, not SDK threads; torn partial metric state persists ~2× interval then EXPIRES (vanish not stale-marked).
- RES-04 | P2 | all SDK calls + /metrics generate_latest + cardinality share default executor (min(32,cpu+4)); client._semaphore NEVER USED; scrapes queue behind blocked SDK threads in 429 storms. Fix: dedicated SDK executor (mirror DNS F-075) + wire/remove semaphore.
- RES-05 | P2 | retry multiplication: SDK (3 attempts, unbounded Retry-After sleep in-thread) × with_error_handling rate-limit retries (3 more, 10-60s) ≈ 12 HTTP attempts/logical fetch. Pick ONE 429 owner.
- RES-06 | P2 | OrgHealthTracker written ONLY by OrganizationCollector; 6 readers → backoff blind to device/network failure domains; dies if org collector disabled.
- RES-07 | P2 | ClientStore never evicts departed clients (cleanup_stale_networks 0 call sites); DNS _cache/_client_tracking unbounded [overlaps SCALE-05/14].
- RES-08 | P3 | liveness auto-threshold 3×slow=45min ≫ metric TTL (2×interval) — wedge = empty metrics ~40min before restart.
- RES-09 | P3 | tier-loop 10-failure kill switch is dead code (nothing raises); if fired would stop tiers silently w/o exiting process. Delete or sys.exit.
- RES-10 | P3 | smoothing offsets applied to INITIAL collection → /ready ~3.5min on every rolling restart (LIVE-CONFIRMED). Skip offsets until tier initial complete.
- RES-11 | P3 | SIGTERM drain best-effort; blocked SDK threads can exceed 30s grace → SIGKILL noise. Chart grace note.
- RES-12 | P3 | bare-swallow paths don't increment collector_errors_total; direct SDK calls not counted in api_requests_total (inventory-only). Add _track_error + alerting recipe.
- Clusters: {RES-01,02,12} failure-masking (fix together); {RES-03,04,05} thread/retry design pass. Regression test: fake-key run must yield /ready 503 + failure_streak>0.
- OK: startup non-crashing + /ready gating correct pre-collection; config errors clean; expiration manager real; webhook path solid; DNS pool right; no FD/session leaks; PEP758 valid (3rd confirmation).
