---
type: C4 System
title: Meraki Dashboard webhooks
status: stable
groma:
  id: meraki-dashboard-webhooks
  technology: HTTPS POST
---

Meraki Dashboard's alert webhook sender, configured by the operator to post to the exporter's optional webhook receiver with a shared secret.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [meraki-dashboard-webhooks](meraki-dashboard-webhooks.md) | [src/meraki_dashboard_exporter/app.py](../../src/meraki_dashboard_exporter/app.py) | Posts alerts | HTTPS POST, shared secret |
