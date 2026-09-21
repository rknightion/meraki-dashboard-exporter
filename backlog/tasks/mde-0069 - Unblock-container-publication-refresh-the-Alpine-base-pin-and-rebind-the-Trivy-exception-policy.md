---
id: MDE-0069
title: >-
  Unblock container publication: refresh the Alpine base pin and rebind the
  Trivy exception policy
status: To Do
assignee: []
created_date: '2026-09-21 12:25'
updated_date: '2026-09-21 12:28'
labels:
  - 'area:ci'
  - 'priority:high'
dependencies: []
ordinal: 69000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Every container build since 2026-09-05 failed the publication Trivy gate, so no image or chart has reached GHCR since 2026-09-04 and the v2.1.0 tag has a GitHub release with no image behind it.

Mechanism: the digest pinned at Dockerfile:15 and Dockerfile:58 resolved to Alpine 3.23.5, carrying libuuid 2.41.4-r0. Six HIGH CVEs (CVE-2026-53612, -53613, -53614, -76642, -78408, -78410) landed against it, all fixed in 2.41.6-r1, which Alpine had already published into the v3.23 repository. The upstream python:3.14-alpine3.23 image had not been rebuilt, so the pinned base stayed vulnerable. container-publish runs Trivy with severity CRITICAL,HIGH and exit-code 1, so both matrix legs failed and 'merge + sign + sbom' and 'helm publish' skipped.

Second defect, latent: .trivyignore.yaml still listed fifteen exceptions written against the Debian base (pkg:deb/debian/perl-base, libsqlite3-0, libncursesw6, gzip, libacl1). The image moved to Alpine at 2844a98 on 2026-09-03, so every one of those purls matched nothing. scripts/validate_trivy_exceptions.py validates shape, not applicability, so the policy passed while accepting nothing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Dockerfile base pin resolves to an Alpine release whose libuuid is 2.41.6-r1 or newer
- [ ] #2 The runtime stage patches base packages at build time so a lagging upstream base rebuild cannot block publication again
- [ ] #3 Trivy at CRITICAL,HIGH with the committed exception policy exits 0 on both linux/amd64 and linux/arm64
- [ ] #4 .trivyignore.yaml contains only exceptions whose purls match packages actually present in the Alpine image
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verified locally on 2026-09-21 before the commit, on both matrix architectures, with the same scanner CI pins (aquasecurity/trivy-action v0.36.0 ships Trivy 0.70.0) against an OCI directory built from this tree:

- linux/amd64 gate exit 0, linux/arm64 gate exit 0 with the committed policy.
- Without any exception policy, the only remaining HIGH findings on either arch are setuptools CVE-2025-47273 and msgpack GHSA-6v7p-g79w-8964. Every OS-package finding is gone.
- Both of those report PkgPath null. They come from pip's vendored copies in the base image (pip/_vendor/msgpack and pip/_vendor/pkg_resources). No setuptools or msgpack dist-info exists anywhere in the image and neither is in uv.lock, so neither is installed, imported or executed here.

Negative result worth keeping: a CodeRabbit major finding asked for a 'paths' filter on those two exceptions, scoped to the pip/_vendor paths. It was rejected on evidence, not judgement, and must not be reapplied:

1. scripts/validate_trivy_exceptions.py enforces the entry key set exactly, so a paths field fails the policy job in publish.yml before any image is built.
2. Trivy reports PkgPath null for both findings, so a paths filter matches nothing. Measured: adding the filter puts the gate back to exit 1 with 2 HIGH, which is the exact failure this task exists to clear.

The apk upgrade in the runtime stage is deliberate and trades exact package-level reproducibility against the pinned digest for a self-healing gate. The digest pin is retained for the base image identity; the upgrade only patches packages Alpine has already fixed in the v3.23 repository. Removing it to 'restore reproducibility' reopens the outage.

Second pre-existing Alpine-migration leftover found while committing, fixed in the same change: the hadolint pre-commit hook ignored DL3008, which is apt's version-pinning rule. The Alpine move made apk's DL3018 the applicable one and it was never added, so hadolint had been failing at HEAD since 2844a98 on the untouched builder-stage apk add. Verified against HEAD's own Dockerfile through hadolint v2.15.1: exit 1, findings at lines 18, 61 and 103.

hadolint's default failure threshold is info, so DL3066 ('USER exporter' is non-numeric) also contributed to the non-zero exit. Fixed rather than ignored: USER is now numeric 1000, matching the chart's securityContext runAsUser/fsGroup and letting runAsNonRoot compare a uid. Same account, since adduser already creates it with -u 1000. Smoke-tested on the rebuilt arm64 image: id reports uid=1000(exporter) gid=1000(exporter) and the package imports on Python 3.14.7.
<!-- SECTION:NOTES:END -->
