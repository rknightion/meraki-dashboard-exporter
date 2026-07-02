# Changelog

## [0.32.0](https://github.com/rknightion/meraki-dashboard-exporter/compare/v0.31.0...v0.32.0) (2026-07-02)


### Features

* **collectors:** M3 high-value new signal (MR/MX/org/MT) ([639526b](https://github.com/rknightion/meraki-dashboard-exporter/commit/639526b23177f30fde8cad2bbbf1353e89fe861b)), closes [#259](https://github.com/rknightion/meraki-dashboard-exporter/issues/259) [#260](https://github.com/rknightion/meraki-dashboard-exporter/issues/260) [#261](https://github.com/rknightion/meraki-dashboard-exporter/issues/261) [#262](https://github.com/rknightion/meraki-dashboard-exporter/issues/262) [#263](https://github.com/rknightion/meraki-dashboard-exporter/issues/263) [#264](https://github.com/rknightion/meraki-dashboard-exporter/issues/264) [#265](https://github.com/rknightion/meraki-dashboard-exporter/issues/265) [#266](https://github.com/rknightion/meraki-dashboard-exporter/issues/266) [#267](https://github.com/rknightion/meraki-dashboard-exporter/issues/267) [#268](https://github.com/rknightion/meraki-dashboard-exporter/issues/268) [#269](https://github.com/rknightion/meraki-dashboard-exporter/issues/269)
* **devices:** close M2 device-coverage gaps (MG/MV/MS/MX) ([0a21fec](https://github.com/rknightion/meraki-dashboard-exporter/commit/0a21fec06a61c335bb4260c5002e80b4f8c2191a)), closes [#252](https://github.com/rknightion/meraki-dashboard-exporter/issues/252) [#253](https://github.com/rknightion/meraki-dashboard-exporter/issues/253) [#254](https://github.com/rknightion/meraki-dashboard-exporter/issues/254) [#255](https://github.com/rknightion/meraki-dashboard-exporter/issues/255) [#256](https://github.com/rknightion/meraki-dashboard-exporter/issues/256) [#257](https://github.com/rknightion/meraki-dashboard-exporter/issues/257) [#258](https://github.com/rknightion/meraki-dashboard-exporter/issues/258)
* **ms:** surface port errors/warnings from existing port-status data ([79c4fc5](https://github.com/rknightion/meraki-dashboard-exporter/commit/79c4fc5c9d67a8d7e5e2530e8d0b80eb8eea194f)), closes [#245](https://github.com/rknightion/meraki-dashboard-exporter/issues/245)
* **mt:** add no2/o3/pm10 sensor metrics; share client for sensor reads ([86ced18](https://github.com/rknightion/meraki-dashboard-exporter/commit/86ced181da071305b9ef78048f1a2f5e34dd169f)), closes [#246](https://github.com/rknightion/meraki-dashboard-exporter/issues/246) [#249](https://github.com/rknightion/meraki-dashboard-exporter/issues/249)
* **mx:** populate MX_SECURITY_EVENTS_TOTAL from appliance security events ([4705139](https://github.com/rknightion/meraki-dashboard-exporter/commit/470513940d23a66037e4a6a92c56bf0ecbb9aa95)), closes [#244](https://github.com/rknightion/meraki-dashboard-exporter/issues/244)


### Bug Fixes

* **alerts:** bound AlertsCollector fan-out with process_in_batches_with_errors ([b27c276](https://github.com/rknightion/meraki-dashboard-exporter/commit/b27c27630ca247bb0c09701c6efcdc377169cc88)), closes [#248](https://github.com/rknightion/meraki-dashboard-exporter/issues/248)
* **api:** remove dead AsyncMerakiClient._request wrapper and api_duration_seconds ([836a6f3](https://github.com/rknightion/meraki-dashboard-exporter/commit/836a6f3d3f38d57efc8b43ece52a67227fc4f463)), closes [#344](https://github.com/rknightion/meraki-dashboard-exporter/issues/344)
* **app:** cap webhook body, offload registry iteration, bound cardinality, track wait task ([6420c6c](https://github.com/rknightion/meraki-dashboard-exporter/commit/6420c6c00ba94e42eaaf0454e3933da9884c6a9e)), closes [#480](https://github.com/rknightion/meraki-dashboard-exporter/issues/480) [#481](https://github.com/rknightion/meraki-dashboard-exporter/issues/481) [#482](https://github.com/rknightion/meraki-dashboard-exporter/issues/482) [#483](https://github.com/rknightion/meraki-dashboard-exporter/issues/483) [#484](https://github.com/rknightion/meraki-dashboard-exporter/issues/484)
* **build:** correct Makefile docker targets and install-hooks ([6d0b538](https://github.com/rknightion/meraki-dashboard-exporter/commit/6d0b53870cd51f3d223bc16c900de4db481ca90b)), closes [#371](https://github.com/rknightion/meraki-dashboard-exporter/issues/371) [#372](https://github.com/rknightion/meraki-dashboard-exporter/issues/372) [#373](https://github.com/rknightion/meraki-dashboard-exporter/issues/373) [#374](https://github.com/rknightion/meraki-dashboard-exporter/issues/374)
* **chart:** point readinessProbe at /ready instead of /health ([8639c1b](https://github.com/rknightion/meraki-dashboard-exporter/commit/8639c1bf2f33c72b65ec248e9b1e62a9e4d34407)), closes [#243](https://github.com/rknightion/meraki-dashboard-exporter/issues/243)
* **chart:** wire the chart-managed API key secret into the Deployment ([e47a7cc](https://github.com/rknightion/meraki-dashboard-exporter/commit/e47a7cc1c16177b4ae3c2d64fe37743afb22692a))
* **clients:** float usage type, paced signal-quality fan-out, demote per-network logs ([10c9d87](https://github.com/rknightion/meraki-dashboard-exporter/commit/10c9d8753c0adf774bd0490205ff183d3c0a0a89)), closes [#492](https://github.com/rknightion/meraki-dashboard-exporter/issues/492) [#493](https://github.com/rknightion/meraki-dashboard-exporter/issues/493) [#494](https://github.com/rknightion/meraki-dashboard-exporter/issues/494)
* **cli:** repair first-run missing-API-key error path and --help env vars ([dff23c8](https://github.com/rknightion/meraki-dashboard-exporter/commit/dff23c8245a775effa657bfc98bd17fb62bc6b11)), closes [#242](https://github.com/rknightion/meraki-dashboard-exporter/issues/242)
* **collectors:** gate non-org collectors on OrgHealthTracker backoff ([67cd893](https://github.com/rknightion/meraki-dashboard-exporter/commit/67cd89384900411a74bdada02910bafb26f86187)), closes [#506](https://github.com/rknightion/meraki-dashboard-exporter/issues/506)
* **config:** bug-bash lane — startup summary, dead config, expiration, bounded concurrency, response validation ([3687573](https://github.com/rknightion/meraki-dashboard-exporter/commit/3687573de884e797afd2310e305b150e02ff5cd7)), closes [#455](https://github.com/rknightion/meraki-dashboard-exporter/issues/455) [#456](https://github.com/rknightion/meraki-dashboard-exporter/issues/456) [#457](https://github.com/rknightion/meraki-dashboard-exporter/issues/457) [#458](https://github.com/rknightion/meraki-dashboard-exporter/issues/458) [#459](https://github.com/rknightion/meraki-dashboard-exporter/issues/459) [#460](https://github.com/rknightion/meraki-dashboard-exporter/issues/460) [#461](https://github.com/rknightion/meraki-dashboard-exporter/issues/461)
* **core:** dedicated DNS executor, None-label coalescing, cache copies, metric-name enums ([036bc6d](https://github.com/rknightion/meraki-dashboard-exporter/commit/036bc6dd7e01d5d10def2a91e30aa1d5db1328fd)), closes [#499](https://github.com/rknightion/meraki-dashboard-exporter/issues/499) [#500](https://github.com/rknightion/meraki-dashboard-exporter/issues/500) [#501](https://github.com/rknightion/meraki-dashboard-exporter/issues/501) [#502](https://github.com/rknightion/meraki-dashboard-exporter/issues/502)
* **core:** implement real Prometheus series removal in MetricExpirationManager ([85c28ca](https://github.com/rknightion/meraki-dashboard-exporter/commit/85c28ca4fdff1cac6474e5ff903eb68bd2ec56a5)), closes [#334](https://github.com/rknightion/meraki-dashboard-exporter/issues/334)
* **core:** validate direct fetchers, capture task-group exceptions, status-aware 404 ([486360f](https://github.com/rknightion/meraki-dashboard-exporter/commit/486360f4cbbb509a5417a3bb6bf0210f831dff98)), closes [#488](https://github.com/rknightion/meraki-dashboard-exporter/issues/488) [#489](https://github.com/rknightion/meraki-dashboard-exporter/issues/489) [#490](https://github.com/rknightion/meraki-dashboard-exporter/issues/490) [#491](https://github.com/rknightion/meraki-dashboard-exporter/issues/491)
* **deploy:** bug-bash lane — Helm chart, Dockerfile, and CI hardening ([fdea149](https://github.com/rknightion/meraki-dashboard-exporter/commit/fdea149dfd32f8473b06a7425d700a7a6527c5fe)), closes [#441](https://github.com/rknightion/meraki-dashboard-exporter/issues/441) [#442](https://github.com/rknightion/meraki-dashboard-exporter/issues/442) [#443](https://github.com/rknightion/meraki-dashboard-exporter/issues/443) [#444](https://github.com/rknightion/meraki-dashboard-exporter/issues/444) [#445](https://github.com/rknightion/meraki-dashboard-exporter/issues/445) [#446](https://github.com/rknightion/meraki-dashboard-exporter/issues/446) [#447](https://github.com/rknightion/meraki-dashboard-exporter/issues/447) [#448](https://github.com/rknightion/meraki-dashboard-exporter/issues/448) [#449](https://github.com/rknightion/meraki-dashboard-exporter/issues/449)
* **deps:** update dependency meraki to v3.3.0 ([#380](https://github.com/rknightion/meraki-dashboard-exporter/issues/380)) ([5472d84](https://github.com/rknightion/meraki-dashboard-exporter/commit/5472d841c141bc95a066a6cca487751003a4d334))
* **devices:** paginate org memory-usage fetch so all devices are covered ([0e1508d](https://github.com/rknightion/meraki-dashboard-exporter/commit/0e1508d67ae930456c20c204277a16747e7cd65a)), closes [#504](https://github.com/rknightion/meraki-dashboard-exporter/issues/504)
* **devices:** seam pass — Catalyst MS gating, honest gauge names, PSU model label ([bee1402](https://github.com/rknightion/meraki-dashboard-exporter/commit/bee14023fe2e6ba28434c1f9c2d8bd8b5512acfa)), closes [#426](https://github.com/rknightion/meraki-dashboard-exporter/issues/426) [#424](https://github.com/rknightion/meraki-dashboard-exporter/issues/424) [#425](https://github.com/rknightion/meraki-dashboard-exporter/issues/425)
* **devices:** stop per-org _metrics.clear() wiping other orgs' series ([0710ef7](https://github.com/rknightion/meraki-dashboard-exporter/commit/0710ef7b7116d9322bd194cfb294ee335e2449ab)), closes [#336](https://github.com/rknightion/meraki-dashboard-exporter/issues/336) [#337](https://github.com/rknightion/meraki-dashboard-exporter/issues/337) [#338](https://github.com/rknightion/meraki-dashboard-exporter/issues/338)
* **docs:** bug-bash lane — document network-filter config; reconcile stale MT-only warning ([df78af1](https://github.com/rknightion/meraki-dashboard-exporter/commit/df78af1c237386a4c66841e4d42c90ec35f941e9)), closes [#450](https://github.com/rknightion/meraki-dashboard-exporter/issues/450) [#451](https://github.com/rknightion/meraki-dashboard-exporter/issues/451)
* **mr:** paginate/parse MR performance + honest SSID/air-marshal metrics ([fa62d97](https://github.com/rknightion/meraki-dashboard-exporter/commit/fa62d97a4fa20fb20ca5bb88e6e1a69f8f019753)), closes [#399](https://github.com/rknightion/meraki-dashboard-exporter/issues/399) [#400](https://github.com/rknightion/meraki-dashboard-exporter/issues/400) [#401](https://github.com/rknightion/meraki-dashboard-exporter/issues/401) [#402](https://github.com/rknightion/meraki-dashboard-exporter/issues/402) [#403](https://github.com/rknightion/meraki-dashboard-exporter/issues/403) [#404](https://github.com/rknightion/meraki-dashboard-exporter/issues/404) [#405](https://github.com/rknightion/meraki-dashboard-exporter/issues/405) [#406](https://github.com/rknightion/meraki-dashboard-exporter/issues/406) [#407](https://github.com/rknightion/meraki-dashboard-exporter/issues/407)
* **ms:** MS port metric expiry, STP hygiene/cadence, real stack roles ([ba86643](https://github.com/rknightion/meraki-dashboard-exporter/commit/ba86643445201329d61a698a6e4421deedef76c0)), closes [#415](https://github.com/rknightion/meraki-dashboard-exporter/issues/415) [#416](https://github.com/rknightion/meraki-dashboard-exporter/issues/416) [#417](https://github.com/rknightion/meraki-dashboard-exporter/issues/417) [#418](https://github.com/rknightion/meraki-dashboard-exporter/issues/418) [#419](https://github.com/rknightion/meraki-dashboard-exporter/issues/419) [#420](https://github.com/rknightion/meraki-dashboard-exporter/issues/420)
* **mt:** NetworkFilter + expiration + inventory-cache the FAST sensor path ([c9d932c](https://github.com/rknightion/meraki-dashboard-exporter/commit/c9d932c2e6ef35f1117ea1aa0bbee5c27f2c2e63)), closes [#427](https://github.com/rknightion/meraki-dashboard-exporter/issues/427) [#428](https://github.com/rknightion/meraki-dashboard-exporter/issues/428) [#429](https://github.com/rknightion/meraki-dashboard-exporter/issues/429) [#430](https://github.com/rknightion/meraki-dashboard-exporter/issues/430) [#431](https://github.com/rknightion/meraki-dashboard-exporter/issues/431) [#432](https://github.com/rknightion/meraki-dashboard-exporter/issues/432) [#433](https://github.com/rknightion/meraki-dashboard-exporter/issues/433)
* **mv:** correct zone-name join, drop "None" labels, throttle static calls ([3543ccb](https://github.com/rknightion/meraki-dashboard-exporter/commit/3543ccbf4af7639afcb888874ac4996460a61fd3)), closes [#434](https://github.com/rknightion/meraki-dashboard-exporter/issues/434) [#435](https://github.com/rknightion/meraki-dashboard-exporter/issues/435) [#436](https://github.com/rknightion/meraki-dashboard-exporter/issues/436)
* **mx:** drop dead VPN metrics, gate perf/firewall calls, paginate sec-events ([fc2bfaa](https://github.com/rknightion/meraki-dashboard-exporter/commit/fc2bfaa63c95cf2ec2182fe8ce84e3f44f4e4d4f)), closes [#410](https://github.com/rknightion/meraki-dashboard-exporter/issues/410) [#411](https://github.com/rknightion/meraki-dashboard-exporter/issues/411) [#412](https://github.com/rknightion/meraki-dashboard-exporter/issues/412) [#413](https://github.com/rknightion/meraki-dashboard-exporter/issues/413) [#414](https://github.com/rknightion/meraki-dashboard-exporter/issues/414)
* **network-health:** bug-bash lane — bluetooth zeroing, RF util pinning, data-rate units, phantom failures field ([40e3130](https://github.com/rknightion/meraki-dashboard-exporter/commit/40e313097b6a70087e97fbd279f681d666d179c2)), closes [#437](https://github.com/rknightion/meraki-dashboard-exporter/issues/437) [#438](https://github.com/rknightion/meraki-dashboard-exporter/issues/438) [#439](https://github.com/rknightion/meraki-dashboard-exporter/issues/439) [#440](https://github.com/rknightion/meraki-dashboard-exporter/issues/440)
* **observability:** correct collect_packet_loss API-call endpoint label ([4c15bff](https://github.com/rknightion/meraki-dashboard-exporter/commit/4c15bffdcb2afd5d89b2e9eebc39143d6630be11)), closes [#342](https://github.com/rknightion/meraki-dashboard-exporter/issues/342)
* **observability:** real /status API totals, org-scoped rate limiting, OTLP TLS, real version ([009da56](https://github.com/rknightion/meraki-dashboard-exporter/commit/009da5605d8af8f64269dde4b50e2c8fd16bc315)), closes [#495](https://github.com/rknightion/meraki-dashboard-exporter/issues/495) [#496](https://github.com/rknightion/meraki-dashboard-exporter/issues/496) [#497](https://github.com/rknightion/meraki-dashboard-exporter/issues/497) [#498](https://github.com/rknightion/meraki-dashboard-exporter/issues/498)
* **observability:** remove dead self-metrics and stop inventory series leaks ([f4add56](https://github.com/rknightion/meraki-dashboard-exporter/commit/f4add56513a3e7ecad5526f67490123eea032d56)), closes [#348](https://github.com/rknightion/meraki-dashboard-exporter/issues/348) [#349](https://github.com/rknightion/meraki-dashboard-exporter/issues/349) [#350](https://github.com/rknightion/meraki-dashboard-exporter/issues/350)
* **observability:** remove frozen success-age gauge and dead collection-wait histogram ([cff7ff9](https://github.com/rknightion/meraki-dashboard-exporter/commit/cff7ff935b5ad81fdc718a2da1ea65fa8481135b)), closes [#346](https://github.com/rknightion/meraki-dashboard-exporter/issues/346) [#347](https://github.com/rknightion/meraki-dashboard-exporter/issues/347)
* **observability:** remove phantom pre-initialized zero-forever self-metric series ([57181fe](https://github.com/rknightion/meraki-dashboard-exporter/commit/57181febb0fe5fb0a6ee181beead02091cd3ce5c)), closes [#345](https://github.com/rknightion/meraki-dashboard-exporter/issues/345)
* **observability:** stop counting inventory cache hits as API calls ([246d3e7](https://github.com/rknightion/meraki-dashboard-exporter/commit/246d3e72f48aa723fe601fd4659f1f07a80c0dfd)), closes [#341](https://github.com/rknightion/meraki-dashboard-exporter/issues/341)
* **observability:** stop double-counting collector API calls ([fc8c9c2](https://github.com/rknightion/meraki-dashboard-exporter/commit/fc8c9c2daa8fa6c68b7ef5e62b9ae6815a1a6ea8)), closes [#340](https://github.com/rknightion/meraki-dashboard-exporter/issues/340)
* **ops:** bug-bash app-code — liveness dead-man switch, startup discovery, readiness, endpoint auth, smoothing clamp ([effe4a8](https://github.com/rknightion/meraki-dashboard-exporter/commit/effe4a832d61cae7b3f01585df59807c3e237b43)), closes [#474](https://github.com/rknightion/meraki-dashboard-exporter/issues/474) [#475](https://github.com/rknightion/meraki-dashboard-exporter/issues/475) [#476](https://github.com/rknightion/meraki-dashboard-exporter/issues/476) [#477](https://github.com/rknightion/meraki-dashboard-exporter/issues/477) [#478](https://github.com/rknightion/meraki-dashboard-exporter/issues/478)
* **org:** bug-bash follow-ups — surface isolated sub-collector failures + filter alert gauges ([960e336](https://github.com/rknightion/meraki-dashboard-exporter/commit/960e33697d08e6a045161daa35fc788445c858b2)), closes [#408](https://github.com/rknightion/meraki-dashboard-exporter/issues/408) [#409](https://github.com/rknightion/meraki-dashboard-exporter/issues/409)
* **org:** close org-collector correctness gaps (NetworkFilter, expiry, undercounts) ([6410fa6](https://github.com/rknightion/meraki-dashboard-exporter/commit/6410fa601597934e9a3c7153997b46e4819ebf56)), closes [#381](https://github.com/rknightion/meraki-dashboard-exporter/issues/381) [#382](https://github.com/rknightion/meraki-dashboard-exporter/issues/382) [#383](https://github.com/rknightion/meraki-dashboard-exporter/issues/383) [#384](https://github.com/rknightion/meraki-dashboard-exporter/issues/384) [#385](https://github.com/rknightion/meraki-dashboard-exporter/issues/385) [#386](https://github.com/rknightion/meraki-dashboard-exporter/issues/386) [#387](https://github.com/rknightion/meraki-dashboard-exporter/issues/387) [#388](https://github.com/rknightion/meraki-dashboard-exporter/issues/388) [#389](https://github.com/rknightion/meraki-dashboard-exporter/issues/389) [#390](https://github.com/rknightion/meraki-dashboard-exporter/issues/390) [#391](https://github.com/rknightion/meraki-dashboard-exporter/issues/391) [#392](https://github.com/rknightion/meraki-dashboard-exporter/issues/392) [#393](https://github.com/rknightion/meraki-dashboard-exporter/issues/393) [#394](https://github.com/rknightion/meraki-dashboard-exporter/issues/394) [#395](https://github.com/rknightion/meraki-dashboard-exporter/issues/395) [#396](https://github.com/rknightion/meraki-dashboard-exporter/issues/396) [#397](https://github.com/rknightion/meraki-dashboard-exporter/issues/397) [#398](https://github.com/rknightion/meraki-dashboard-exporter/issues/398)
* **org:** route device-count gauges through _set_metric so stale combos expire ([d5ec85b](https://github.com/rknightion/meraki-dashboard-exporter/commit/d5ec85b4769e911dfdf30168f050084836643f33)), closes [#335](https://github.com/rknightion/meraki-dashboard-exporter/issues/335)
* **otel:** use dynamic package version for service.version ([640dafe](https://github.com/rknightion/meraki-dashboard-exporter/commit/640dafebca7858bcb94744b16c317682e4a6e335)), closes [#247](https://github.com/rknightion/meraki-dashboard-exporter/issues/247)
* **otel:** use supported response_hook for requests span enrichment ([96988f3](https://github.com/rknightion/meraki-dashboard-exporter/commit/96988f3a90e45f21f72aa73aaaa7e1528ee8a6a1)), closes [#343](https://github.com/rknightion/meraki-dashboard-exporter/issues/343)
* **tests:** correct shared test-helper bugs masking real behaviour ([a583c19](https://github.com/rknightion/meraki-dashboard-exporter/commit/a583c19e062996cd25eb84e7ee40da1db4b21854)), closes [#375](https://github.com/rknightion/meraki-dashboard-exporter/issues/375) [#376](https://github.com/rknightion/meraki-dashboard-exporter/issues/376) [#377](https://github.com/rknightion/meraki-dashboard-exporter/issues/377) [#378](https://github.com/rknightion/meraki-dashboard-exporter/issues/378) [#379](https://github.com/rknightion/meraki-dashboard-exporter/issues/379)
* **webhook:** constant-time secret, bounded failure labels, no secret in logs ([451bc6b](https://github.com/rknightion/meraki-dashboard-exporter/commit/451bc6b3b68c058badd8714fd37297efad291573)), closes [#485](https://github.com/rknightion/meraki-dashboard-exporter/issues/485) [#486](https://github.com/rknightion/meraki-dashboard-exporter/issues/486) [#487](https://github.com/rknightion/meraki-dashboard-exporter/issues/487)


### Performance Improvements

* **ms:** bug-bash follow-ups — org-wide port usage/PoE, real STP serials, stack metric expiration ([7454948](https://github.com/rknightion/meraki-dashboard-exporter/commit/7454948e7a4d0e080201058473f7de504cb1f48f)), closes [#421](https://github.com/rknightion/meraki-dashboard-exporter/issues/421) [#422](https://github.com/rknightion/meraki-dashboard-exporter/issues/422) [#423](https://github.com/rknightion/meraki-dashboard-exporter/issues/423)


### Code Refactoring

* **core:** delete dead utility code ([24bacf3](https://github.com/rknightion/meraki-dashboard-exporter/commit/24bacf3d10e5c90c21e76c1793847fb4d887a7dd)), closes [#507](https://github.com/rknightion/meraki-dashboard-exporter/issues/507)
* **devices:** bug-bash F-023 — validate MX/MT fetcher responses via Pydantic domain models ([088f3fd](https://github.com/rknightion/meraki-dashboard-exporter/commit/088f3fdcc243d4c6cb6fa9f0bbd348531b4193fe)), closes [#462](https://github.com/rknightion/meraki-dashboard-exporter/issues/462) [#459](https://github.com/rknightion/meraki-dashboard-exporter/issues/459)
* **devices:** validate MG/MS-power/MX-uplink-health/MV rows via Pydantic models ([6f18706](https://github.com/rknightion/meraki-dashboard-exporter/commit/6f1870603fa4cb07b5fa6aa802ff6c64ddc9f36a)), closes [#503](https://github.com/rknightion/meraki-dashboard-exporter/issues/503)


### Documentation

* add roadmap-task workflow to CLAUDE.md; drop superseded planning docs ([935f66b](https://github.com/rknightion/meraki-dashboard-exporter/commit/935f66b70fc836a88dcdecdfa881fe677559b8a1))
* add v1-readiness evidence pack backing issues [#508](https://github.com/rknightion/meraki-dashboard-exporter/issues/508)–[#617](https://github.com/rknightion/meraki-dashboard-exporter/issues/617) ([8f3168a](https://github.com/rknightion/meraki-dashboard-exporter/commit/8f3168ad7cffa84a5b664c9351eeff662b8ad76b))
* audit and refresh CLAUDE.md files repo-wide ([719609f](https://github.com/rknightion/meraki-dashboard-exporter/commit/719609f295cc754a4bee51354ea8fcef72550187))
* CLAUDE.md accuracy sweep + durable wave workflow + dashboards context ([f08cd69](https://github.com/rknightion/meraki-dashboard-exporter/commit/f08cd6946b989586675115edc4c3033836f783aa))
* **claude:** refresh stale CLAUDE.md/AGENTS.md rosters and claims ([24db96d](https://github.com/rknightion/meraki-dashboard-exporter/commit/24db96de79815f5980eda01127270804855f0b53)), closes [#361](https://github.com/rknightion/meraki-dashboard-exporter/issues/361) [#362](https://github.com/rknightion/meraki-dashboard-exporter/issues/362) [#363](https://github.com/rknightion/meraki-dashboard-exporter/issues/363) [#364](https://github.com/rknightion/meraki-dashboard-exporter/issues/364) [#365](https://github.com/rknightion/meraki-dashboard-exporter/issues/365) [#366](https://github.com/rknightion/meraki-dashboard-exporter/issues/366) [#367](https://github.com/rknightion/meraki-dashboard-exporter/issues/367) [#368](https://github.com/rknightion/meraki-dashboard-exporter/issues/368) [#369](https://github.com/rknightion/meraki-dashboard-exporter/issues/369) [#370](https://github.com/rknightion/meraki-dashboard-exporter/issues/370)
* **collectors:** correct stale collector_timeout default comment (120s -&gt; 240s) ([476bee5](https://github.com/rknightion/meraki-dashboard-exporter/commit/476bee5c08f46f890b389ffa7a31fd2d1f285498)), closes [#452](https://github.com/rknightion/meraki-dashboard-exporter/issues/452)
* fix stale/incorrect docs-site content ([2b5aa07](https://github.com/rknightion/meraki-dashboard-exporter/commit/2b5aa07f0a12ce55e1236c55185457352b099d57)), closes [#351](https://github.com/rknightion/meraki-dashboard-exporter/issues/351) [#352](https://github.com/rknightion/meraki-dashboard-exporter/issues/352) [#353](https://github.com/rknightion/meraki-dashboard-exporter/issues/353) [#354](https://github.com/rknightion/meraki-dashboard-exporter/issues/354) [#355](https://github.com/rknightion/meraki-dashboard-exporter/issues/355) [#356](https://github.com/rknightion/meraki-dashboard-exporter/issues/356) [#357](https://github.com/rknightion/meraki-dashboard-exporter/issues/357) [#358](https://github.com/rknightion/meraki-dashboard-exporter/issues/358) [#359](https://github.com/rknightion/meraki-dashboard-exporter/issues/359) [#360](https://github.com/rknightion/meraki-dashboard-exporter/issues/360)
* reconcile org-collector docs with the Wave-2 code fixes ([9a0545a](https://github.com/rknightion/meraki-dashboard-exporter/commit/9a0545a00b3c27712b72ca6e8f4e922ba9d24222))
* regenerate metrics/collector reference for M1 ([a6af126](https://github.com/rknightion/meraki-dashboard-exporter/commit/a6af1266cbb652def6e407788dc78e8f7e051e72))

## [0.31.0](https://github.com/rknightion/meraki-dashboard-exporter/compare/v0.30.1...v0.31.0) (2026-06-30)


### Features

* **apidrift:** detect Meraki API drift on consumed operations ([bc07e1a](https://github.com/rknightion/meraki-dashboard-exporter/commit/bc07e1a9fd315c34e898bc01241c6429ea9caad1))
* Meraki API drift detection ([1aa88c4](https://github.com/rknightion/meraki-dashboard-exporter/commit/1aa88c4373661368a907fd7a3031e0d57fcb27ed))


### Bug Fixes

* **security:** harden apidrift live-url against SSRF; repair invalid .snyk policy ([56f7435](https://github.com/rknightion/meraki-dashboard-exporter/commit/56f74354267433c4b98f260742f8a1a9174bd453))


### Code Refactoring

* **models:** map models to source ops, fix vlan type, drop dead models ([3b4f96a](https://github.com/rknightion/meraki-dashboard-exporter/commit/3b4f96ac3f703d0d4706157b0e7d943a5b5819f9))


### Dependencies

* drop unused 'safety' runtime dependency (removes vulnerable nltk) ([f711738](https://github.com/rknightion/meraki-dashboard-exporter/commit/f711738f12f6d586d0a25b7e237249aa4e97ced9))

## [0.30.1](https://github.com/rknightion/meraki-dashboard-exporter/compare/v0.30.0...v0.30.1) (2026-06-26)


### Bug Fixes

* **docker:** build multi-arch images on native runners ([487ee51](https://github.com/rknightion/meraki-dashboard-exporter/commit/487ee5192f583b8e2663ff3db1a618387707c055)), closes [#221](https://github.com/rknightion/meraki-dashboard-exporter/issues/221)
* **docs:** remove glightbox slide_effect option (rejected by zensical 0.0.44) ([8e1aecd](https://github.com/rknightion/meraki-dashboard-exporter/commit/8e1aecd3ae38c31f3dc1bed09cc6b8f47cfc244a))

## [0.30.0](https://github.com/rknightion/meraki-dashboard-exporter/compare/v0.29.0...v0.30.0) (2026-05-08)


### Features

* **config:** add NetworkFilterSettings model ([d768050](https://github.com/rknightion/meraki-dashboard-exporter/commit/d7680501333374b597fd4daf47e0ad136904f029))
* **config:** wire network_filter into Settings ([bed4c59](https://github.com/rknightion/meraki-dashboard-exporter/commit/bed4c59c9b6af291cb963f0b49e8c14fef0bfd14))
* **core:** add NetworkFilter resolver ([d11209f](https://github.com/rknightion/meraki-dashboard-exporter/commit/d11209f1a9dd1102b6e9904d526754e16f906588))
* **inventory:** apply NetworkFilter at the read path ([e2bc90f](https://github.com/rknightion/meraki-dashboard-exporter/commit/e2bc90fdc5898b6d9b4aa15a8e1a39d38432d6ca))
* **network-filter:** wire startup, fail-fast, metrics, and docs ([87f7619](https://github.com/rknightion/meraki-dashboard-exporter/commit/87f7619a84faa484a86745ebfbd0df45649cf94a))


### Bug Fixes

* **collectors:** apply NetworkFilter to org-wide device endpoints ([2c21787](https://github.com/rknightion/meraki-dashboard-exporter/commit/2c21787e2025fe2fbabb1ef9f1d7b8745f927e85))
* **inventory:** validate SDK responses before caching ([7392b61](https://github.com/rknightion/meraki-dashboard-exporter/commit/7392b61f0c7ee2d38fbb2b2424109228fbe8ef9a))
* **metric:** use binary value instead of label for network_filter_match ([a4c9436](https://github.com/rknightion/meraki-dashboard-exporter/commit/a4c943655a65390fe8bf7438712e1cdc41ecfc34))
* validate API responses to handle SDK exhausted-retry error shape ([6d769f7](https://github.com/rknightion/meraki-dashboard-exporter/commit/6d769f7cb07da1691063025af6eb52ecf567c7c6))


### Code Refactoring

* **collectors:** route network fetches through inventory ([c92803a](https://github.com/rknightion/meraki-dashboard-exporter/commit/c92803a8ebb74452e87ff2aac8aedc39d2ead6bb))
* route network health device/network lookups through inventory cache ([8ed0969](https://github.com/rknightion/meraki-dashboard-exporter/commit/8ed09691d1e222d2a974d92ba3dfd99c892ae642))


### Documentation

* add limited-testing warning to readme, docs site, and release notes ([7032af1](https://github.com/rknightion/meraki-dashboard-exporter/commit/7032af11d1318986eed3a510a592f2f985e83c04))

## [0.29.0](https://github.com/rknightion/meraki-dashboard-exporter/compare/v0.28.2...v0.29.0) (2026-04-15)


### Features

* add /status health dashboard endpoint ([172a23c](https://github.com/rknightion/meraki-dashboard-exporter/commit/172a23c1cf08cd072b2963b5fe65b47670f0e148))
* add firewall & security policy collector for MX appliances ([543b461](https://github.com/rknightion/meraki-dashboard-exporter/commit/543b46110396c30e662ceb7ca0ce670b6e95f164))
* add Kubernetes Helm chart ([dc429a6](https://github.com/rknightion/meraki-dashboard-exporter/commit/dc429a67a74fe4ad4218197558d89bc4fd17bed1))
* add tier-aware metric expiration ([33aa55a](https://github.com/rknightion/meraki-dashboard-exporter/commit/33aa55a8f084227eeba9368c04842f528c852110))
* Waves 3-5 remaining source and test changes ([ca95923](https://github.com/rknightion/meraki-dashboard-exporter/commit/ca9592336f1be9bd13922826c17cacfcb6b42f75))


### Bug Fixes

* add type annotations to ms_stack test helper function ([dfba644](https://github.com/rknightion/meraki-dashboard-exporter/commit/dfba64469527e6fb8e861b157cd60586ef415134))
* bound packet metric and MS collector caches ([f9953a9](https://github.com/rknightion/meraki-dashboard-exporter/commit/f9953a9a93fed4f7a3618cd103ef9f816a8a1033))
* cap collector-internal smoothing at 30% of timeout budget ([800c81e](https://github.com/rknightion/meraki-dashboard-exporter/commit/800c81e6a596ebbbc885b100a752e7bf4e8cc59f))
* increase default collector timeout from 120s to 240s ([fcab2e8](https://github.com/rknightion/meraki-dashboard-exporter/commit/fcab2e872e43a098a0efea6ca03a37f46f74aec1))
* rename POE metric enums from WATTS to WATTHOURS ([fd4238e](https://github.com/rknightion/meraki-dashboard-exporter/commit/fd4238e2771036ac53fd21851cd560b5ce083fa5))
* replace Python 2 exception syntax with tuple form ([f68ebdf](https://github.com/rknightion/meraki-dashboard-exporter/commit/f68ebdf63387c4e9ed7bfa4337eba17e24bef511))
* update TemplateResponse for Starlette 1.0 and parallelize MSStackCollector ([0f3cd48](https://github.com/rknightion/meraki-dashboard-exporter/commit/0f3cd489291f15e3675d5a7a95e58580e698ddb2))
* use device_lookup for MR radio metric labels ([#199](https://github.com/rknightion/meraki-dashboard-exporter/issues/199)) ([644e695](https://github.com/rknightion/meraki-dashboard-exporter/commit/644e6950b4d886f41ea74a99e6d1bcaa1003b547))


### Code Refactoring

* improve API client type safety ([927728f](https://github.com/rknightion/meraki-dashboard-exporter/commit/927728f2e72abaf8b85ef7f5c0a04ae8c496b9ef))
* standardize sub-collector init and API updates ([64eaf9f](https://github.com/rknightion/meraki-dashboard-exporter/commit/64eaf9fcab3ccdc777a12b97f31d6101e2fbe30b))


### Documentation

* add API call reduction audit ([6f3a1f4](https://github.com/rknightion/meraki-dashboard-exporter/commit/6f3a1f41778f7635c74ec21a1613b6b721eff1a5))
* add improvement roadmap spec and Wave 1 implementation plan ([60c6357](https://github.com/rknightion/meraki-dashboard-exporter/commit/60c6357ad335525d92a95c1d802d58eb35f42ad7))
* add log aggregation examples with Grafana Alloy and LogQL ([d793627](https://github.com/rknightion/meraki-dashboard-exporter/commit/d7936270523c209d202aa6c263806a6fc3f0d054))
* add scaling guide with deployment recommendations ([dc2a798](https://github.com/rknightion/meraki-dashboard-exporter/commit/dc2a798a00db0e0d1c9b69f7c2fcf8fe7424a54b))
* update CLAUDE.md files across project ([e299f28](https://github.com/rknightion/meraki-dashboard-exporter/commit/e299f28e1493daae868ae83d9afa3825735d28db))

## [0.28.2](https://github.com/rknightion/meraki-dashboard-exporter/compare/v0.28.1...v0.28.2) (2026-03-26)


### Bug Fixes

* **deps:** update dependency meraki to v2.2.0 ([#173](https://github.com/rknightion/meraki-dashboard-exporter/issues/173)) ([342aa2e](https://github.com/rknightion/meraki-dashboard-exporter/commit/342aa2ed7ea83764cd28ee63b8949128be75521b))
* **devices:** use availability_status field for device status detection ([4e40908](https://github.com/rknightion/meraki-dashboard-exporter/commit/4e409085bc8edb69c4ca6b89eff5078f05701c5d)), closes [#186](https://github.com/rknightion/meraki-dashboard-exporter/issues/186)


### Code Refactoring

* **devices:** remove common metrics collection from device-specific collectors ([8ec6095](https://github.com/rknightion/meraki-dashboard-exporter/commit/8ec6095f3fc7613cc93fd6e6f34189c8d2694cbd))

## [0.28.1](https://github.com/rknightion/meraki-dashboard-exporter/compare/v0.28.0...v0.28.1) (2026-03-13)


### Dependencies

* switch meraki from git to PyPI source & update ([8bc84a4](https://github.com/rknightion/meraki-dashboard-exporter/commit/8bc84a4776d40e6be41d863c9c8c36adbfb8d9fa))

## [0.28.0](https://github.com/rknightion/meraki-dashboard-exporter/compare/v0.27.1...v0.28.0) (2026-03-13)


### Features

* add API metrics instrumentation ([a688581](https://github.com/rknightion/meraki-dashboard-exporter/commit/a688581f0381d902d49837751c3ddc53db5322ae))
* add collector management helper methods ([caa563a](https://github.com/rknightion/meraki-dashboard-exporter/commit/caa563a3afa45668eafe6531ef1ce30c32b3ef8f))
* add collector status display and trigger UI ([6e08cfb](https://github.com/rknightion/meraki-dashboard-exporter/commit/6e08cfbba940a266e8dc536107dd611f8959f507))
* add collector trigger endpoint ([b7b169e](https://github.com/rknightion/meraki-dashboard-exporter/commit/b7b169effee6f24e78bf65fb304060e63c720d2b))
* add manual collector trigger API endpoint ([507f0d8](https://github.com/rknightion/meraki-dashboard-exporter/commit/507f0d879ad10831ffa058d30c768bb0e433d5c7))
* add MX appliance uplink status metrics ([ad153ef](https://github.com/rknightion/meraki-dashboard-exporter/commit/ad153ef758a3d5fd99d556083c11a5c35dbc5e5a))
* add MX appliance uplink status metrics ([09d3554](https://github.com/rknightion/meraki-dashboard-exporter/commit/09d3554f4146533d25d35e809c2d7635e8455a1a))
* add MX uplink info metric ([99c33c1](https://github.com/rknightion/meraki-dashboard-exporter/commit/99c33c1bad8f90e60f1eba92ce5d82aa6cf43fb0))
* add new observability metrics ([abc0dec](https://github.com/rknightion/meraki-dashboard-exporter/commit/abc0dec436dc937bb555a13c60f26a3db9fdcaa7))
* add thread-safe metrics initialization ([abed04b](https://github.com/rknightion/meraki-dashboard-exporter/commit/abed04b60913dbebb5c632f83baf852418f74fef))
* **api:** add rate limiting and collection smoothing ([d1e56ef](https://github.com/rknightion/meraki-dashboard-exporter/commit/d1e56ef923f701bf6cb7464f004b346c0a180f0c))
* **core:** add timeout-based smoothing cap ([4834801](https://github.com/rknightion/meraki-dashboard-exporter/commit/483480191a9e8eb13593a995a24c26b32dab124f))
* enhance startup logging and discovery ([fb98bdc](https://github.com/rknightion/meraki-dashboard-exporter/commit/fb98bdcefd866392f5eba658df493428d470ef77))
* **inventory:** add device availability caching ([1ea56e9](https://github.com/rknightion/meraki-dashboard-exporter/commit/1ea56e9803b4da74689a466f1873fc90a7159da7))
* **logging:** add smoothing cap to startup ([56fc174](https://github.com/rknightion/meraki-dashboard-exporter/commit/56fc174e729fe901dfffb9c36ca5dc38301063cf))
* **otel:** add metrics export routing config ([e199645](https://github.com/rknightion/meraki-dashboard-exporter/commit/e199645b729a320502c6c77df2751d0dbebe63db))
* **otel:** add metrics filtering system ([a67287e](https://github.com/rknightion/meraki-dashboard-exporter/commit/a67287e223a0a19c3e5d37dba2647a9d0503e48b))
* **otel:** integrate filtering into app ([84633f0](https://github.com/rknightion/meraki-dashboard-exporter/commit/84633f07ecf96961a8495a6fcf335b0ff08d6e2e))
* **ui:** expose smoothing cap diagnostics ([da6bc9b](https://github.com/rknightion/meraki-dashboard-exporter/commit/da6bc9b0eb96b9414b66d7cf9057f7e5756322d3))


### Bug Fixes

* **ci:** skip registry cache on PRs to prevent 403 errors ([e971085](https://github.com/rknightion/meraki-dashboard-exporter/commit/e971085e8ad49752f729700ee0eb7b71e03b0813))
* clear stale device status label series ([d0de7e4](https://github.com/rknightion/meraki-dashboard-exporter/commit/d0de7e408ebfd2d0672264bef6b29c2000134ac3))
* clear stale MX uplink status labels ([57420b9](https://github.com/rknightion/meraki-dashboard-exporter/commit/57420b9a3830fbff541836bac888cd51452f7f1f))
* **device:** improve status result validation ([97364ad](https://github.com/rknightion/meraki-dashboard-exporter/commit/97364ade390280c67ea23f7ec0f7462e119cdd7a))
* ensure metrics available in inventory service ([d856ed0](https://github.com/rknightion/meraki-dashboard-exporter/commit/d856ed038d54fa24e4a368033eeb7f9f63a8511b))
* improve retry logic with jitter and Retry-After ([98be37e](https://github.com/rknightion/meraki-dashboard-exporter/commit/98be37e9ecf86101ec6b1b3ed5998c2ec5be8478))
* **ms:** add SDK method availability check ([2b2a99c](https://github.com/rknightion/meraki-dashboard-exporter/commit/2b2a99c104823ecf8d0a3591ae2612e25c77cce8))
* **ms:** correct API endpoint for switch ports status ([c9f551d](https://github.com/rknightion/meraki-dashboard-exporter/commit/c9f551dcb7183f3301863d8cc27e721e511e6275))
* prevent race conditions in device lookup ([ecdbfce](https://github.com/rknightion/meraki-dashboard-exporter/commit/ecdbfce75f4fb34e589cf56f3bdc188d5745c2ed))
* resolve test failures in device collector and error handling tests ([4707340](https://github.com/rknightion/meraki-dashboard-exporter/commit/4707340089047dfe23b86f803a437defefe79da2))
* secure sensitive data masking in logs ([89120a4](https://github.com/rknightion/meraki-dashboard-exporter/commit/89120a41b327ba084960501a0cece359cfffc753))


### Performance Improvements

* **mr:** optimize to network-level collection ([3d4a0a4](https://github.com/rknightion/meraki-dashboard-exporter/commit/3d4a0a4ca09a73db75fd21dd93830643d157e1de))


### Code Refactoring

* add collector tracking infrastructure ([c33bdef](https://github.com/rknightion/meraki-dashboard-exporter/commit/c33bdef2bd561ffba49661764ade006afa6544bd))
* add concurrency control to collector execution ([a5c59c7](https://github.com/rknightion/meraki-dashboard-exporter/commit/a5c59c7ba6d21a95fcdd27986aa60981d2c83656))
* **alerts:** use inventory cache for data ([16f29b8](https://github.com/rknightion/meraki-dashboard-exporter/commit/16f29b8b3d115d15186bdbe8c63cb9e98973cbf8))
* **api:** use inventory cache in APIHelper ([4d7feb0](https://github.com/rknightion/meraki-dashboard-exporter/commit/4d7feb04183244a9794d46ce0b8c77a3d94ec629))
* **ci:** simplify docs workflow and remove deps ([800196b](https://github.com/rknightion/meraki-dashboard-exporter/commit/800196be575123db940e913f5c6ff12309ae1c12))
* **collectors:** add inventory access pattern ([36b6941](https://github.com/rknightion/meraki-dashboard-exporter/commit/36b6941c9f741c5efb93381515341452a355a937))
* **config:** use inventory cache for orgs ([3a217ca](https://github.com/rknightion/meraki-dashboard-exporter/commit/3a217caf4792160fe6bf0a120ee31c17af104fb3))
* **device:** use inventory for availability ([a5cff09](https://github.com/rknightion/meraki-dashboard-exporter/commit/a5cff093c6861e9212cfe795e1065329741e9f41))
* enhance batch processing in collectors ([001bd0c](https://github.com/rknightion/meraki-dashboard-exporter/commit/001bd0c157f495b18f8ad73942dd21c9e0378581))
* improve startup sequence with sequential init ([4dcace4](https://github.com/rknightion/meraki-dashboard-exporter/commit/4dcace425d4649fe43a2316a8a34fdd915f71ea3))
* **metrics:** rename to meraki_exporter_ prefix ([6a983cf](https://github.com/rknightion/meraki-dashboard-exporter/commit/6a983cf5aef22a00e15ff42a38367d5363f2fcc4))
* **otel:** remove span metrics processor ([cef99d5](https://github.com/rknightion/meraki-dashboard-exporter/commit/cef99d546fe2d25478e8e49829676665676f3a61))
* remove unused imports and metrics code ([ca8721e](https://github.com/rknightion/meraki-dashboard-exporter/commit/ca8721e08bdfb4ad2e90d8105ddbf37c528782c6))
* reuse AsyncMerakiClient metrics counter ([a4ebab9](https://github.com/rknightion/meraki-dashboard-exporter/commit/a4ebab9eec3b3eb2dfb2be6ca062c03d4ac5e5d0))
* simplify config defaults and add docs tooling ([6cd4a6f](https://github.com/rknightion/meraki-dashboard-exporter/commit/6cd4a6f80c52c150631ff26632061ef07ce69e0f))
* use instrumented API calls ([f46afc4](https://github.com/rknightion/meraki-dashboard-exporter/commit/f46afc49ed3f599d4e43cd114d6677aa45b343cf))


### Documentation

* add missing parameter documentation ([621b81f](https://github.com/rknightion/meraki-dashboard-exporter/commit/621b81f7c51f741dcacb0866f8d1f65168e9cffe))
* clean up formatting and descriptions ([9fa79c6](https://github.com/rknightion/meraki-dashboard-exporter/commit/9fa79c6ebaa296a45fad909d788c3b0f64a8ca57))
* **config:** update configuration reference ([c9ff636](https://github.com/rknightion/meraki-dashboard-exporter/commit/c9ff636c159fb7da9a012d28ea4e9608ebd1d0e8))
* improve OpenTelemetry configuration ([a8e1a48](https://github.com/rknightion/meraki-dashboard-exporter/commit/a8e1a4868bbbc32d56d9d7d344f6c91959cda374))
* **metrics:** update metrics documentation ([9ff5b3a](https://github.com/rknightion/meraki-dashboard-exporter/commit/9ff5b3a417f4460da25ee16d6960406629f4ddaf))
* **otel:** update observability guides ([fdd0c64](https://github.com/rknightion/meraki-dashboard-exporter/commit/fdd0c644ccf914748acac11b2ba7030956089c7e))
* remove ADR and patterns sections ([8dc3710](https://github.com/rknightion/meraki-dashboard-exporter/commit/8dc3710b5839da9ab86515e6928047a0be27cb73))
* streamline collector documentation ([ca79d1c](https://github.com/rknightion/meraki-dashboard-exporter/commit/ca79d1cc575d00e907fbc3c89fa352bd71fd6192))
* update ([8c05f71](https://github.com/rknightion/meraki-dashboard-exporter/commit/8c05f717d3eab6bc2946fee4b1790afc80d30a70))
* update API configuration reference ([05c56e3](https://github.com/rknightion/meraki-dashboard-exporter/commit/05c56e38d3cf230e5aca8a3d951434c138a6af12))
* update endpoint reference ([4f56bb1](https://github.com/rknightion/meraki-dashboard-exporter/commit/4f56bb1a2b9c2d29c4c7d96da2be92a543f0131e))
* update getting started and guides ([c148640](https://github.com/rknightion/meraki-dashboard-exporter/commit/c1486405be62e4aaf3f16b8ef4780caa89f34f50))
* update metrics overview and index ([381330f](https://github.com/rknightion/meraki-dashboard-exporter/commit/381330f138578cfbeefe58aec8413cfe0a7e956f))

## [0.27.1](https://github.com/rknightion/meraki-dashboard-exporter/compare/v0.27.0...v0.27.1) (2025-12-01)


### Bug Fixes

* add automated docker build on release creation ([c6e3328](https://github.com/rknightion/meraki-dashboard-exporter/commit/c6e332859e8da0494e245f1203208c2f7900afb2))

## [0.27.0](https://github.com/rknightion/meraki-dashboard-exporter/compare/v0.26.1...v0.27.0) (2025-12-01)


### Features

* add retry mechanism for rate-limited API responses ([7177659](https://github.com/rknightion/meraki-dashboard-exporter/commit/7177659d07f100a1f69fa454342fc690cf128bfe))


### Bug Fixes

* **error-handling:** add api error response validation ([d4708df](https://github.com/rknightion/meraki-dashboard-exporter/commit/d4708dff439700baae1cc364fa93784a4647bbd9))


### Documentation

* add comprehensive changelog for version 0.26.1 ([bc70586](https://github.com/rknightion/meraki-dashboard-exporter/commit/bc70586248d8cf6c63c0df1d01525aa60a6f2786))

## [0.26.1](https://github.com/rknightion/meraki-dashboard-exporter/compare/v0.26.0...v0.26.1) (2025-12-01)


### Bug Fixes

* remove error suppression from docker help test ([3a4af40](https://github.com/rknightion/meraki-dashboard-exporter/commit/3a4af403918e7dcab850e7b37d41f5384fcbe30f))


### Code Refactoring

* replace asyncio with inspect for coroutine detection ([d9976c1](https://github.com/rknightion/meraki-dashboard-exporter/commit/d9976c103a0708a82f82cbdf7329dc6ae3487c4a))


### Documentation

* rewrite collector reference with practical usage guide ([489d631](https://github.com/rknightion/meraki-dashboard-exporter/commit/489d631a42a0b78cacc1f4887a0f0c70a06036b7))

## Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.26.1] - 2025-12-01

### Highlights
- Bounded parallel collection with shared inventory caching and configurable batch sizes to speed up multi-org runs and cut API calls.
- Docker-first packaging with a dedicated entrypoint plus a refreshed dependency stack targeting Python 3.14.
- Wireless SSID collection fixes that align with the latest Meraki APIs for more accurate MR metrics.
- Documentation overhaul (new collector guide, config updates, SEO/social cards) and release automation via release-please.

### Features & Improvements
- Added an inventory caching service (organizations, networks, devices) with TTLs, new collector concurrency/cache metrics, and the metric expiration framework controlled by `MERAKI_EXPORTER_MONITORING__METRIC_TTL_MULTIPLIER`.
- Collectors now use `ManagedTaskGroup` bounded concurrency and larger configurable batch sizes (devices 20, networks 30, clients 20 by default) for faster collection.
- Docker image rebuilt around `docker-entrypoint.py` and docs now recommend Docker as the primary deployment path.
- Expanded `.env.example` with grouped settings, OTEL/monitoring options, and added `uv.lock` for reproducible installs; exposed the package `main` for easier embedding.
- Improved OpenTelemetry tracing coverage and API client hooks; added Claude PR/code-review workflows and release-please automation.

### Fixes
- MR wireless collector now paginates SSID status, parses radio details correctly, and uses the organization summary SSID usage endpoint.
- Device type detection falls back to `productType` when the model prefix is unknown (thanks @dmitchsplunk for the first external contribution in #83).
- Docker CLI help test no longer suppresses errors, ensuring failures surface during CI.

### Documentation
- Collector reference rewritten into a practical usage guide; configuration docs updated with new settings and metric TTL guidance.
- Documentation site moved to https://m7kni.io with new SEO/social assets and Docker-first getting started flow.

### CI/CD
- Baseline runtime and CI bumped to Python 3.14 with refreshed dependency pins and pre-commit hooks.
- CI simplified to Ubuntu-only testing, optimized PR Docker builds, and removed legacy workflows (PyPI publish, Dependabot, CodeQL, etc.).

### Contributors
- @dmitchsplunk for improving device type detection (first external community contribution).
