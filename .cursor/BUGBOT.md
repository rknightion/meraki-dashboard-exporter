# Meraki exporter review guide

## What this is

Operators run this exporter to monitor Meraki organizations in Prometheus. OpenTelemetry carries traces and optional per-entity data logs. Prometheus is the metrics interface.

## Invariants

- Collector network lookups go through `OrganizationInventory.get_networks` so configured scope applies consistently. Preserve the filter on existing inventory-unavailable fallbacks and keep startup discovery's exception confined to discovery.
- Use the instrumented SDK facade for Meraki calls. Keep polling and fan-out within the scheduler's API budget. Bulk organization calls avoid creating an unbounded per-device polling loop.
- Keep Prometheus metric and label names stable and cardinality bounded. Use the metric enums and collector emission helper so stale values can expire. Put new per-client data in the data-log channel.

## Changes to scrutinize

- Check new API model fields against validated response shapes, including nulls and omitted fields. Preserve the separate outcome for license-gated endpoints and prevent SDK errors from reaching the parser as ordinary data.
- For configuration, webhook and logging changes, check the error paths and diagnostics for credential disclosure. URL credentials and rejected secret values must remain masked.
- Check startup and runtime changes against the container's non-root user and `/health` and `/metrics` behavior. For changed metrics, trace the matching dashboard and alert consumers.

## Findings already covered by CI

Formatting, Ruff, mypy, offline API conformance and workflow lint already report their own failures. Review behavior at the SDK, inventory, metric expiry and container boundaries.

## Verification

`just check` runs the local application checks and verifies generated references. `just groma-check` checks the architecture map. The separate native image job exercises the container contract. Verify changes to Meraki response shapes against appropriate sanitized evidence when local fixtures leave uncertainty.
