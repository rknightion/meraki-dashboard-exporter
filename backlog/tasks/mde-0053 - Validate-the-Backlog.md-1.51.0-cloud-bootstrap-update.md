---
id: MDE-0053
title: Validate the Backlog.md 1.51.0 cloud-bootstrap update
status: To Do
assignee: []
created_date: '2026-09-03 14:40'
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
- [ ] #1 Backlog.md 1.51.0 is tested against task create/edit/finalize, append-only notes, guard-hook denials and CLI plain/JSON reads in a disposable tracker copy
- [ ] #2 Generated instruction changes are reviewed against this repository operating model before the bootstrap pin moves
- [ ] #3 The cloud setup script validation and full repository gate pass after the version change
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
