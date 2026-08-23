---
id: MDE-0026
title: Document shared task-admission metrics in the generated reference
status: Done
assignee: []
created_date: '2026-08-23 17:26'
updated_date: '2026-08-23 18:49'
labels:
  - 'area:docs'
  - needs-triage
  - 'source:coderabbit'
milestone: m-0
dependencies: []
modified_files:
  - scripts/generate_metrics_docs.py
  - docs/metrics/metrics.md
priority: medium
type: bug
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scripts/generate_metrics_docs.py does not discover the Gauge/Histogram/Counter constructors nested inside the TaskAdmissionMetrics dataclass assembly in core/async_utils.py:43-74. As a result, docs/metrics/metrics.md omits meraki_exporter_tasks_pending, meraki_exporter_tasks_active, meraki_exporter_task_queue_wait_seconds, and meraki_exporter_task_expired_before_start_total even though they are production metrics and the collector_admission phase is operationally important. Extend the AST generator rather than hand-editing generated output, document the bounded phase labels, and regenerate the reference.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All four shared task-admission metrics appear in the generated metric reference with correct types and the phase label
- [x] #2 The reference explains the collector_admission and task_group phase values without implying endpoint failure
- [x] #3 Generator regression coverage and make docgen pass without unrelated drift
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 1 L10: teach the metrics-doc generator to discover TaskAdmissionMetrics with phase documentation and focused coverage; root owns broad docgen and final gate.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented and verified in 7327153. All four task-admission metrics and bounded phase meanings are generated; full gates passed.
<!-- SECTION:FINAL_SUMMARY:END -->
