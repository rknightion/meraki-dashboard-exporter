---
type: C4 Component
title: Org health tracker (core/org_health.py)
status: stable
groma:
  id: org-health
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/core/org_health.py
  technology: Python
  group: Collection runtime
description: Backs off a failing organization while healthy ones keep collecting
---

After repeated consecutive failures an organization is backed off with a doubling delay up to a cap, per failure domain, so one broken org does not stall the rest. An org that disappears from output for a while is usually this back-off.
