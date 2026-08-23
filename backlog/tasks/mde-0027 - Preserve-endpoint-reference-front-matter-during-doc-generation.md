---
id: MDE-0027
title: Preserve endpoint-reference front matter during doc generation
status: Done
assignee: []
created_date: '2026-08-23 18:38'
updated_date: '2026-08-23 18:49'
labels:
  - 'area:docs'
  - 'priority:low'
  - needs-triage
milestone: m-0
dependencies: []
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Running make docgen currently rewrites docs/reference/endpoints.md without its Zensical front matter and adds a trailing blank line. Because CI regenerates and diffs this file, the checked-in metadata cannot remain stable. Make scripts/generate_endpoints_docs.py emit the repository-owned title and description front matter deterministically and pin the output contract.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 make docs-endpoints preserves valid title and description front matter in docs/reference/endpoints.md
- [x] #2 Repeated endpoint generation is byte-for-byte idempotent with no trailing-whitespace warning
- [x] #3 A focused generator test pins the front matter contract
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Update the endpoint generator output prologue and focused generator regression, regenerate the reference, then include it in the shared docgen/check gates.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Discovered during integration and fixed in 7327153. Endpoint front matter generation is deterministic, tested, and byte-idempotent.
<!-- SECTION:FINAL_SUMMARY:END -->
