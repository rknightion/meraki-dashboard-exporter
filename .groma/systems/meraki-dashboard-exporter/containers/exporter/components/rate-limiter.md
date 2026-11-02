---
type: C4 Component
title: Rate limiter (core/rate_limiter.py)
status: stable
groma:
  id: rate-limiter
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/rate_limiter.py
  technology: Python
  group: Meraki API access
description: Per-organization token bucket with AIMD back-off
---

`OrgRateLimiter` keeps one token bucket per organization, using a configurable share of the org's API budget and leaving the rest as headroom for other consumers. A real 429 or `Retry-After` halves the effective rate (floored, with a cooldown between halvings), and the effective rate feeds the scheduler's next solve, so a throttled org's cadence changes without a config change.
