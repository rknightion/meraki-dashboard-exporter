---
type: Groma Project
title: meraki-dashboard-exporter
groma:
  profile: architecture
description: Prometheus exporter for the Cisco Meraki Dashboard API
---

meraki-dashboard-exporter polls the Cisco Meraki Dashboard API across one or more organizations and serves fleet-shaped device, network and organization metrics on a Prometheus `/metrics` endpoint. OpenTelemetry carries self-observability traces and an optional per-entity data-log channel. AGENTS.md at the repository root and the AGENTS.md files under `src/meraki_dashboard_exporter/` are the source of truth for invariants and package boundaries.
