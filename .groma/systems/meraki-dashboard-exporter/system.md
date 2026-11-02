---
type: C4 System
title: meraki-dashboard-exporter
status: stable
groma:
  id: meraki-dashboard-exporter
description: Polls the Meraki Dashboard API and serves Prometheus metrics
---

A single Python service, shipped as a container image and a Helm chart. It reads Meraki organization, network, device and client data through the Meraki Dashboard API with a budget-aware scheduler, and exposes bounded aggregates (org, network, device serial, SSID, port, band) as Prometheus metrics. Per-client or otherwise unbounded detail goes to an opt-in OTLP data-log channel instead of metric labels. It also serves health, readiness, an HTML status and clients UI, an optional webhook receiver for Meraki alerts, and a bearer-token-protected control API.
