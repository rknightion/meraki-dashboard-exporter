---
type: C4 System
title: Prometheus scraper
status: stable
groma:
  id: prometheus-scraper
  technology: HTTP
---

Prometheus or any compatible scraper that pulls `/metrics`, the exporter's primary output.

## Relationships

| Source | Target | Description | Technology |
| --- | --- | --- | --- |
| [prometheus-scraper](prometheus-scraper.md) | [src/meraki_dashboard_exporter/app.py](../../src/meraki_dashboard_exporter/app.py) | Scrapes metrics | HTTP /metrics |
