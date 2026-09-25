---
id: MDE-0073
title: Prune tautological and change-detector unit tests
status: To Do
assignee: []
created_date: '2026-09-25 08:05'
labels:
  - testing
dependencies: []
ordinal: 73000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the 2026-09-25 fleet test-signal audit (sampled read-only). Delete or consolidate tautological tests (restating the implementation) and change-detector tests (pinning incidental text, markup, counts or internals). Keep parsing, state-machine, retry, security/PII, wire-contract and incident regression tests. Re-verify each candidate before deleting it; the list below comes from a sample and is not exhaustive. Candidates: tests/unit/test_domain_models.py:32-40 (pydantic field assignment readback); tests/unit/test_metrics_constants.py:40-45 (substring in the enum's own string); tests/unit/collectors/test_mx_uplink_health_collector.py:56-65 (constructor internals, exact _create_gauge call count). Review the 60 files using assert_called*: keep calls that are a behavioural contract, drop ones pinning private call order. Keep test_golden_metrics_exposition.py; it guards the metric names dashboards use.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each listed candidate is deleted, consolidated or kept with a one-line reason in the notes
- [ ] #2 Other tests in the same pattern found during the work are handled the same way
- [ ] #3 The repo's check recipe passes
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
