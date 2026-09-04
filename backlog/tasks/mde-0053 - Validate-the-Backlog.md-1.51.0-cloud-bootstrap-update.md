---
id: MDE-0053
title: Validate the Backlog.md 1.51.0 cloud-bootstrap update
status: Done
assignee: []
created_date: '2026-09-03 14:40'
updated_date: '2026-09-04 06:33'
labels:
  - 'area:tooling'
dependencies: []
priority: low
type: chore
ordinal: 53000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The Wave 3 currency pass found `scripts/cloud-environment-setup.sh:8` pinning Backlog.md 1.50.1 while 1.51.0 is available. The newer release adds task-graph behavior, changes lifecycle/local-copy handling and refreshes agent guidance. Because this repository relies on CLI-only tracker mutation, guard hooks and generated operating instructions, the bootstrap pin was left unchanged until those workflow changes are checked rather than treating it as a harmless installer bump.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Backlog.md 1.51.0 is tested against task create/edit/finalize, append-only notes, guard-hook denials and CLI plain/JSON reads in a disposable tracker copy
- [x] #2 Generated instruction changes are reviewed against this repository operating model before the bootstrap pin moves
- [x] #3 The cloud setup script validation and full repository gate pass after the version change
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Validate Backlog.md 1.51.0 create/edit/finalize, append-only fields, guard denials and plain/JSON reads in a disposable tracker, review generated guidance, then update only the bootstrap pin if safe.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Accepted Backlog.md 1.51.0 in 18e9cbd after reviewing the package changes and exercising create, edit, finalize, append-only notes, and plain and JSON reads in a disposable tracker. Updated the cloud-bootstrap pin, added cloud-setup-check to the repository gate, observed bash -n succeed, and just check passed 2,958 selected tests at 91.49% coverage. The disposable checkout had no global guard hook, so denial behavior was not independently proven and is recorded as unproven rather than passed.

Follow-up guard verification: the active Codex PreToolUse guard returned an explicit deny decision for a constructed bare notes flag and returned no deny output for the append-notes form. The guard criterion is therefore proven; neither payload invoked the Backlog CLI.
<!-- SECTION:FINAL_SUMMARY:END -->
