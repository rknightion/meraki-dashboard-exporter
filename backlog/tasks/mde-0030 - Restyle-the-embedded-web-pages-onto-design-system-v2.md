---
id: MDE-0030
title: Restyle the embedded web pages onto design system v2
status: To Do
assignee: []
created_date: '2026-08-31 14:05'
labels:
  - design-system
dependencies: []
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The v2 design is committed at design/ui-v2/: the Meraki Exporter UI canvas (all six pages, light and dark), implementation-spec.md and screenshots/. Read the spec in full before any code change; surface any assumption that looks wrong rather than building on it.

Scope: the stack stays FastAPI + Jinja2 server-rendered with no build tooling and no JS framework - that assessment is settled. The work is: one shared static token stylesheet (the spec's centrepiece, both themes) that all six templates link, with per-template CSS shrinking to page-specific remainders; dark mode added (prefers-color-scheme default, small header toggle winning, persisted to localStorage); nav restructured to four top-level entries (Overview, Clients, Status, Cardinality) with a sub-nav row on the three cardinality pages - no destination renamed or removed; fixed shell with the table region scrolling; emoji section markers replaced by Phosphor inline SVG per the spec's mapping; the 19-column clients table gets horizontal scroll with sticky header and sticky first column; fonts self-hosted (Hanken Grotesk + JetBrains Mono, real system fallbacks, zero external network requests); machine text (MACs, IPs, serials, metric names, label values) in mono; status states word+shape, never colour alone; auth-gated pages keep identical chrome to public ones; the exporter's existing self-reported name stays in the header verbatim.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 all six pages render on the shared token stylesheet, light and dark, light default with working toggle
- [ ] #2 nav is four top-level + cardinality sub-nav; every destination intact
- [ ] #3 clients table: 19 columns, sticky header + sticky first column
- [ ] #4 no emoji markers remain; Phosphor inline SVG per spec; no external network requests
- [ ] #5 AA pairs from the spec hold in both themes
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
- [ ] #4 just check green
<!-- DOD:END -->
