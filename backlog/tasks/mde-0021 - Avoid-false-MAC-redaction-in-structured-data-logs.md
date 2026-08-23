---
id: MDE-0021
title: Avoid false MAC redaction in structured data logs
status: Done
assignee: []
created_date: '2026-08-23 16:42'
updated_date: '2026-08-23 18:49'
labels:
  - 'area:otel'
  - 'source:pr733'
milestone: m-0
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/pull/733'
priority: low
type: bug
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #733 P3.9 remains in core/otel_data_logs.py:70-110 and emit filtering. The bare 12-hex alternative is applied to every string attribute and the body, so legitimate names or IDs such as a store label ending in twelve hex characters are irreversibly replaced. Preserve default identifier scrubbing while applying the bare form only where the key or context makes a MAC plausible, and expose a bounded redaction marker if operators need to distinguish redacted from absent.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Separated or colon-delimited MAC strings remain redacted when identifiers are disabled
- [x] #2 Unrelated names and IDs containing twelve hexadecimal characters are preserved
- [x] #3 Bare MAC values are redacted only in MAC-plausible keys or explicitly documented contexts
- [x] #4 Tests cover bodies, identifier keys, non-identifier attributes, and include_identifiers=true
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 1 L6: make bare-MAC redaction context-sensitive while retaining delimiter-form scrubbing; root integrates and finalizes.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented and verified in 7327153. MAC redaction is context-aware without weakening separated-form protection; full gates passed.
<!-- SECTION:FINAL_SUMMARY:END -->
