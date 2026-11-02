---
type: C4 Component
title: Client store (services/client_store.py)
status: stable
groma:
  id: client-store
  parent: exporter
  code:
    - scanner: python
      file: src/meraki_dashboard_exporter/services/client_store.py
  technology: Python
  group: Shared services
description: In-memory client records behind the /clients page
---

Holds the client records the clients collector gathers, for the `/clients` page. Its hostname rule must match the clients collector's own, or the page and the metric labels disagree.
