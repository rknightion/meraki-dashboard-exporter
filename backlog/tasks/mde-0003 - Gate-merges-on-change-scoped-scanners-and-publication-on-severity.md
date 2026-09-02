---
id: MDE-0003
title: Gate merges on change-scoped scanners and publication on severity
status: Parked
assignee: []
created_date: '2026-08-14 15:56'
updated_date: '2026-09-02 05:37'
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
- [x] #1 Merge requires zizmor, actionlint and dependency-review alongside ci-success
- [x] #2 Publication blocks on HIGH/CRITICAL from Trivy and CodeQL, with the scan moved BEFORE push, sign and attest
- [x] #3 A committed exception file carries, per accepted CVE: identifier, reason, and an expiry date, so an acceptance resurfaces rather than becoming permanent
- [x] #4 An expired exception fails the publish gate
- [ ] #5 Signing, SBOM and SARIF upload are all preserved
- [x] #6 .whitesource, .safety-project.ini and .codacy.yaml are each confirmed to be running, or deleted as vestigial
- [x] #7 Codecov and Codacy uploads are confirmed either required or explicitly best-effort — they are currently token-gated and silently no-op
- [x] #8 docs/security.md documents the gate and the exception policy
- [x] #9 Any change needed in rknightion/.github is either authorised by Rob and landed, or written up here as an exact plan with this task Parked — no local-only partial gate ships
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Replacement lane L12: inspect local and shared workflow repositories read-only, map every D14 acceptance criterion to exact files and changes, and return the contractual Parked handoff; no local-only partial gate will ship.

Wave 1 L5 maps an exact cross-repository security change set read-only; root will apply both shared and local halves together, observe real check names, update the ruleset, and verify the full gate.

Repair the released reusable by exporting a real OCI layout directory for Trivy and ORAS, make SARIF upload precede an explicit blocking enforcement step, validate and release the shared workflow, repin every local caller, then require a successful exact-head publication before finalization.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Read-only mapping completed 2026-08-23. Live ruleset requires only ci-success; local ci-success aggregates test, docker-build-test, and Helm validation, while zizmor, actionlint, and dependency review remain independent. The shared container publication workflow pushes architecture digests and signs/attests before its non-gating Trivy scan; CodeQL is separate. Signing, provenance, both SBOM formats, and SARIF already exist and must be preserved. Exact authorized implementation: in the shared workflow repository add pre-push Trivy HIGH/CRITICAL and publication-scoped CodeQL gates, validate a committed identifier/reason/ISO-expiry exception file (expired entries fail), upload SARIF with always semantics, then permit push/sign/attest/SBOM/chart. Locally pass the new inputs, aggregate the three deterministic scanner checks into ci-success, make coverage uploads explicitly best-effort, remove the two proven-unreferenced legacy scanner configs, decide the externally-managed Codacy config from live integration state, document policy, and update the ruleset after observing exact check names. Verification must prove expired exception failure, unexcepted severe finding failure before any publication, preserved security artifacts, workflow lint, and make check. Resume boundary: explicit authority to edit/commit/push the shared workflow repository and mutate this repository ruleset; without that, AC1-AC8 cannot ship coherently and no local partial gate is permitted.

Implemented both halves of the gate. Shared reusable v1.18.1 (ff43f62) exports an unpacked OCI layout, scans each architecture before any registry login or copy, uploads SARIF, and enforces the scanner result afterward. Local main 4209175 pins that release and retains the four required merge checks. Exact-head CI run 33571760598 attempt 2 passed after attempt 1 recorded one isolated timing-only test failure. Publication run 33571760879 proved both architecture scans and SARIF uploads, then correctly blocked every push, merge, sign, attestation, SBOM, and chart step on 18 unique unaccepted HIGH/CRITICAL identifiers (28 architecture/package results). Sixteen runtime Debian findings report no fixed version; setuptools and msgpack findings came from third-party base-image SBOM data and both packages are absent from the runtime environment. No exception was added. Resume boundary: remediate those findings or record explicit identifier/reason/expiry acceptances, rerun exact-head edge publication, and verify image signing, provenance, both SBOM formats, and chart signing downstream of the gate.

The latest publication evidence supersedes the earlier authority-boundary Final Summary.

2026-09-02 main-thread unblock (commits a3b131e, 3b311fe): the AC3 exception file existed but was empty, so publication failed closed on every push and no image could reach the registry. Base image moved to Debian 13 trixie, cutting built-image HIGH/CRITICAL from 28 to 15. All 15 populated in .trivyignore.yaml with identifier, package binding, reason and a 2026-12-01 expiry: 13 trixie base packages with no fixed version, plus setuptools and msgpack which come from the base image SBOM attestation and were verified absent from the runtime filesystem and uv.lock. Two mechanism defects were fixed in the same pass. The validator required a bare YYYY-MM-DD expiry, the one format Trivy cannot parse from a JSON-shaped ignore file; the contract is now RFC3339 UTC. Exceptions carried no package binding, so an accepted base CVE would also have suppressed the same identifier in a first-party dependency; purls is now required and non-empty. Verified locally: trivy exits 0 with zero findings using this file, just check green at 2833 tests. AC5 is still unproven because signing, provenance, both SBOM formats and chart signing have never run downstream of the new gate. Resume by confirming publication now completes at exact head and proving those five artifacts.

2026-09-02 publication verified green at main 3b311fe. Release Please run 33594716832 passed edge/policy, both architecture builds, 'edge / image / merge + sign + sbom' and 'edge / image / helm publish'; auto-rc 33594854197 also succeeded. The :main tag resolves to sha256:5ee10d7f9b9ab0d4d74cca09d4566106e0b7409d522d48e1103e85e5d0bf3d11 and the soak host pulled it automatically, now running that revision healthy. AC5 is therefore satisfiable and largely demonstrated; what remains is naming each of image signing, provenance, both SBOM formats and chart signing against a run at the final head.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Parked at the explicit cross-repository authority boundary. A read-only current-state audit produced the exact shared/local workflow, exception-policy, documentation, ruleset, and verification sequence; no partial local gate or external mutation was made.
<!-- SECTION:FINAL_SUMMARY:END -->
