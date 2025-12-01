# Changelog

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
