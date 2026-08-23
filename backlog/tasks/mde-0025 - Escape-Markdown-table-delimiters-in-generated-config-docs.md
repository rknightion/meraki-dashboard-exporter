---
id: MDE-0025
title: Escape Markdown table delimiters in generated config docs
status: To Do
assignee: []
created_date: '2026-08-23 17:16'
labels:
  - 'area:docs'
  - needs-triage
  - 'source:coderabbit'
milestone: m-0
dependencies: []
modified_files:
  - scripts/generate_config_docs.py
  - docs/config.md
priority: medium
type: bug
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The generated docs/config.md table is malformed for union and Literal types because scripts/generate_config_docs.py:400 wraps a type string containing raw pipe characters in backticks but does not escape the Markdown table delimiters. The MERAKI_EXPORTER_COLLECTORS__PROFILE row currently splits across extra cells. Fix the generator rather than hand-editing generated output, cover the renderer contract, and regenerate the documentation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Generated config type cells escape Markdown table delimiters without changing the displayed type meaning
- [ ] #2 A focused test covers a Literal or union type containing pipe characters
- [ ] #3 make docgen produces a well-formed MERAKI_EXPORTER_COLLECTORS__PROFILE row and the repository gate passes
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
