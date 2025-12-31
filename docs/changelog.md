# Changelog

## [0.28.0](https://github.com/rknightion/meraki-dashboard-exporter/compare/v0.27.1...v0.28.0) (2025-12-28)


### Features

* add API metrics instrumentation ([a688581](https://github.com/rknightion/meraki-dashboard-exporter/commit/a688581f0381d902d49837751c3ddc53db5322ae))
* add collector status display and trigger UI ([6e08cfb](https://github.com/rknightion/meraki-dashboard-exporter/commit/6e08cfbba940a266e8dc536107dd611f8959f507))
* add manual collector trigger API endpoint ([507f0d8](https://github.com/rknightion/meraki-dashboard-exporter/commit/507f0d879ad10831ffa058d30c768bb0e433d5c7))
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

* **device:** improve status result validation ([97364ad](https://github.com/rknightion/meraki-dashboard-exporter/commit/97364ade390280c67ea23f7ec0f7462e119cdd7a))
* ensure metrics available in inventory service ([d856ed0](https://github.com/rknightion/meraki-dashboard-exporter/commit/d856ed038d54fa24e4a368033eeb7f9f63a8511b))
* improve retry logic with jitter and Retry-After ([98be37e](https://github.com/rknightion/meraki-dashboard-exporter/commit/98be37e9ecf86101ec6b1b3ed5998c2ec5be8478))
* **ms:** add SDK method availability check ([2b2a99c](https://github.com/rknightion/meraki-dashboard-exporter/commit/2b2a99c104823ecf8d0a3591ae2612e25c77cce8))
* **ms:** correct API endpoint for switch ports status ([c9f551d](https://github.com/rknightion/meraki-dashboard-exporter/commit/c9f551dcb7183f3301863d8cc27e721e511e6275))
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
* **config:** update configuration reference ([c9ff636](https://github.com/rknightion/meraki-dashboard-exporter/commit/c9ff636c159fb7da9a012d28ea4e9608ebd1d0e8))
* **metrics:** update metrics documentation ([9ff5b3a](https://github.com/rknightion/meraki-dashboard-exporter/commit/9ff5b3a417f4460da25ee16d6960406629f4ddaf))
* **otel:** update observability guides ([fdd0c64](https://github.com/rknightion/meraki-dashboard-exporter/commit/fdd0c644ccf914748acac11b2ba7030956089c7e))
* remove ADR and patterns sections ([8dc3710](https://github.com/rknightion/meraki-dashboard-exporter/commit/8dc3710b5839da9ab86515e6928047a0be27cb73))
* streamline collector documentation ([ca79d1c](https://github.com/rknightion/meraki-dashboard-exporter/commit/ca79d1cc575d00e907fbc3c89fa352bd71fd6192))
* update ([8c05f71](https://github.com/rknightion/meraki-dashboard-exporter/commit/8c05f717d3eab6bc2946fee4b1790afc80d30a70))
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
