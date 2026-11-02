---
type: Groma Flow
title: Collect and serve device metrics
groma:
  id: collect-and-serve-device-metrics
---

One device-collector cycle from startup to a Prometheus scrape. Every SDK call passes through the API facade, which takes a token from the per-organization rate limiter before running the call; the scrape reads whatever the collectors last wrote to the registry.

## Steps

| From | To | Action |
| --- | --- | --- |
| [Operator](../actors/operator.md) | [Entry point (__main__)](../systems/meraki-dashboard-exporter/containers/exporter/components/entrypoint.md) | Start the exporter with environment configuration |
| [Entry point (__main__)](../systems/meraki-dashboard-exporter/containers/exporter/components/entrypoint.md) | [HTTP app (app.py)](../systems/meraki-dashboard-exporter/containers/exporter/components/web-app.md) | Start the FastAPI app under uvicorn |
| [HTTP app (app.py)](../systems/meraki-dashboard-exporter/containers/exporter/components/web-app.md) | [Collector manager (collectors/manager.py)](../systems/meraki-dashboard-exporter/containers/exporter/components/collector-manager.md) | Start the collector loops |
| [Collector manager (collectors/manager.py)](../systems/meraki-dashboard-exporter/containers/exporter/components/collector-manager.md) | [Devices](../systems/meraki-dashboard-exporter/containers/exporter/components/collectors-device.md) | Run the device collector when its endpoint groups are due |
| [Devices](../systems/meraki-dashboard-exporter/containers/exporter/components/collectors-device.md) | [API facade (core/api_facade.py)](../systems/meraki-dashboard-exporter/containers/exporter/components/api-facade.md) | Fetch org-wide device data |
| [API facade (core/api_facade.py)](../systems/meraki-dashboard-exporter/containers/exporter/components/api-facade.md) | [Rate limiter (core/rate_limiter.py)](../systems/meraki-dashboard-exporter/containers/exporter/components/rate-limiter.md) | Acquire a token for the organization |
| [API facade (core/api_facade.py)](../systems/meraki-dashboard-exporter/containers/exporter/components/api-facade.md) | [Meraki API client (api/)](../systems/meraki-dashboard-exporter/containers/exporter/components/api-client.md) | Run the SDK call on the client executor |
| [Meraki API client (api/)](../systems/meraki-dashboard-exporter/containers/exporter/components/api-client.md) | [Meraki Dashboard API](../externals/meraki-dashboard-api.md) | Send the HTTPS request |
| [Prometheus scraper](../externals/prometheus-scraper.md) | [HTTP app (app.py)](../systems/meraki-dashboard-exporter/containers/exporter/components/web-app.md) | Scrape /metrics |
