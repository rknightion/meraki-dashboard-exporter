---
id: MDE-0018
title: Converge broker-token pins and protect secret-bearing jobs
status: To Do
assignee: []
created_date: '2026-08-23 16:42'
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
- [ ] #1 All broker-token call sites use one verified full SHA with a matching version comment unless a documented compatibility constraint requires otherwise
- [ ] #2 Every mint call passes the correct explicit permission-set and role contract
- [ ] #3 Secret-bearing jobs run harden-runner before checkout or token minting
- [ ] #4 actionlint and zizmor pass and no durable PAT secret is introduced
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
