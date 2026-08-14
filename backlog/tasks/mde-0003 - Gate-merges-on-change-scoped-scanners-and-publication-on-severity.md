---
id: MDE-0003
title: Gate merges on change-scoped scanners and publication on severity
status: To Do
assignee: []
created_date: '2026-08-14 15:56'
labels:
  - 'area:ci'
  - security
  - 'priority:medium'
  - migrated-from-github
milestone: m-0
dependencies: []
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Migrated from GitHub issue #721 (`priority: medium`, `area: ci`, `security`) on 2026-08-14. Child of
the retired programme tracker #694; decision **D14**; closes audit finding **F-L8-06**.

**Authority boundary — read before starting.** Part of this lands in the shared workflow repository
`rknightion/.github`, not here. That repository may be inspected read-only and an exact change plan
prepared, but **it may not be edited, committed, pushed or have its rulesets changed without explicit
authority from Rob**. A local-only partial gate must not ship: half a gate reads as a gate.

## Mechanism

Verified live: the `main` ruleset requires **exactly one** check — `ci-success`
(`.github/workflows/ci.yml:299`). CodeQL, Docker Security, Scorecard, zizmor and dependency-review all
run independently and gate nothing. The reusable publication workflow pushes, signs and attests the
image **before** a non-gating Trivy SARIF scan (`.github/workflows/release-please.yml:71-89`,
`publish.yml:31`, `docker-security.yml`). So known-vulnerable code can merge, and a known-vulnerable
image can ship and then be signed and attested.

Existing strengths to preserve: all 35 external Actions are pinned to immutable SHAs, images are
signed with SBOMs, and SARIF is uploaded. **The gap is enforcement, not detection.** That detection
alone is insufficient is already proven here — CI was red for 20 consecutive runs over two days and
nobody noticed.

## Why the split by determinism (D14)

A change-scoped scanner failing is always the author's fault and always fixable, so gating on it
never blocks on the outside world. Gating *everything* on merge would stall the repo on third-party
CVE disclosures and, on a solo-maintainer repo, predictably ends with the gate bypassed — which is
worse than not having the gate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Merge requires zizmor, actionlint and dependency-review alongside ci-success
- [ ] #2 Publication blocks on HIGH/CRITICAL from Trivy and CodeQL, with the scan moved BEFORE push, sign and attest
- [ ] #3 A committed exception file carries, per accepted CVE: identifier, reason, and an expiry date, so an acceptance resurfaces rather than becoming permanent
- [ ] #4 An expired exception fails the publish gate
- [ ] #5 Signing, SBOM and SARIF upload are all preserved
- [ ] #6 .whitesource, .safety-project.ini and .codacy.yaml are each confirmed to be running, or deleted as vestigial
- [ ] #7 Codecov and Codacy uploads are confirmed either required or explicitly best-effort — they are currently token-gated and silently no-op
- [ ] #8 docs/security.md documents the gate and the exception policy
- [ ] #9 Any change needed in rknightion/.github is either authorised by Rob and landed, or written up here as an exact plan with this task Parked — no local-only partial gate ships
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
