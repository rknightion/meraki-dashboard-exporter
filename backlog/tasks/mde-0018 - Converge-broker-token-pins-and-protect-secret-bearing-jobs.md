---
id: MDE-0018
title: Converge broker-token pins and protect secret-bearing jobs
status: Done
assignee:
  - '@codex'
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 17:06'
labels:
  - 'area:ci'
  - security
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
documentation:
  - /Users/rob/repos/chat-personal/camden/openbao/runbooks/CI-SECRETS.md
priority: high
type: chore
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #733 P2.16/P3.1 remain in release-please.yml, release-please-lock.yml, and trigger-docs-sync.yml. broker-token is pinned to two bare SHAs without Renovate-readable version comments, while harden-runner protects the untrusted relock job but not the job that mints a contents-write installation token. Read the OpenBao CI-SECRETS runbook before changing this. Resolve the current shared-action release and required role inputs, converge pins, and apply runner auditing to the jobs while tokens are live without exposing credentials.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All broker-token call sites use one verified full SHA with a matching version comment unless a documented compatibility constraint requires otherwise
- [x] #2 Every mint call passes the correct explicit permission-set and role contract
- [x] #3 Secret-bearing jobs run harden-runner before checkout or token minting
- [x] #4 actionlint and zizmor pass and no durable PAT secret is introduced
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Read the OpenBao CI credential runbook and inspect the current shared broker-token action release and inputs. 2. Converge the three call sites on a verified full SHA plus version comment, add explicit roles where required, and place harden-runner before token-bearing execution. 3. Validate YAML, actionlint, zizmor, CodeRabbit, and make check before commit.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented in ed59990cdbc2e91f3b9ae7d897475ae8842314f6. Converged all three broker-token call sites on verified rknightion/.github v1.9.1 (3eccd1b2f86c998fde32790f370da41d10a4c89b) with SHA/version comments and explicit role inputs. Added harden-runner as the first step in every secret-bearing job and removed ambient GITHUB_TOKEN write scopes from release-please after CodeRabbit identified them as unnecessary. Verification: actionlint passed; zizmor completed with no findings (13 existing suppressions); paid-plan CodeRabbit re-review completed with 0 findings; make check passed (ruff, format, mypy 121 files, 2737 tests, one existing Starlette deprecation warning). make docgen was not run because no metrics, config, endpoints, collectors, or generated-doc inputs changed. Grafana verification was not applicable because no metric or label names changed.
<!-- SECTION:FINAL_SUMMARY:END -->
