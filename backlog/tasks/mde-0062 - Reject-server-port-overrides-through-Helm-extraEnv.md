---
id: MDE-0062
title: Reject server-port overrides through Helm extraEnv
status: In Progress
assignee: []
created_date: '2026-09-03 18:46'
updated_date: '2026-09-04 05:53'
labels:
  - 'area:helm'
dependencies: []
priority: medium
type: chore
ordinal: 62000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit dimension 4 confirmed preventive chart hardening at the v2.0.0 release tree. charts/meraki-dashboard-exporter/templates/configmap.yaml:9-13 owns MERAKI_EXPORTER_SERVER__PORT from service.port, while templates/deployment.yaml:58-95 uses service.port for the named container port and probes. Arbitrary extraEnv is appended at deployment.yaml:65-73, and _validation.tpl:27-30 rejects only a per-fetch deadline override. Rendering extraEnv with MERAKI_EXPORTER_SERVER__PORT=8080 alongside service.port 9099 produces an explicit env value that overrides envFrom while the Service and probes remain on 9099, causing an operator-induced restart loop. Existing tests cover only the deadline override.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Helm rendering rejects MERAKI_EXPORTER_SERVER__PORT in extraEnv and directs operators to service.port
- [ ] #2 A focused render regression preserves ordinary extraEnv entries and rejects the conflicting port entry
- [ ] #3 The application listener, named container port, Service and both probes remain derived from one chart value
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Add a failing Helm render regression for MERAKI_EXPORTER_SERVER__PORT in extraEnv, reject it with service.port guidance, and retain ordinary extraEnv plus the single-value listener/service/probe derivation.
<!-- SECTION:PLAN:END -->
