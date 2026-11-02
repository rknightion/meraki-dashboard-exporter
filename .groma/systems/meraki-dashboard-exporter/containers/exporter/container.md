---
type: C4 Container
title: Exporter process
status: stable
groma:
  id: exporter
  parent: meraki-dashboard-exporter
  technology: Python, FastAPI, uvicorn, Meraki Python SDK, prometheus_client
description: 'The FastAPI process: collectors, scheduler and HTTP surface'
---

One long-running Python process, started with `python -m meraki_dashboard_exporter` (the container image runs it through `docker-entrypoint.py`) and served by uvicorn. Startup loads `Settings`, builds the Meraki SDK client and its thread-pool executor, runs one-time discovery, and hands the registered collectors to the collector manager. Each collector declares endpoint groups; the scheduler solves each group's interval from organization shape and the API budget, and every SDK call goes through the API facade, which applies the per-org rate limiter and owns 429 retries. Collectors write gauges into the Prometheus registry, where the metric-expiration manager removes series for devices and networks that stop reporting. The same process serves `/metrics`, `/health`, `/ready`, `/status`, `/clients`, `/cardinality` and the webhook and control endpoints.
