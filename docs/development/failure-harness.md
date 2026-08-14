---
title: Failure Harness
description: Offline, disposable exporter failure replay against a redacted verified corpus.
tags:
  - Docker
  - Troubleshooting
---

# Failure Harness

The failure harness runs a locally built exporter against a locally built HTTPS replay origin. It
never calls Meraki. A run fails closed unless `tests/harness/corpus/manifest.json` exists and every
fixture has a matching SHA-256 and `LIVE-VERIFIED` provenance. Synthetic unit-test metadata is
explicitly `SHAPE-ASSUMED` and cannot drive a run.

```console
make failure-harness-validate
make failure-harness-run MODE=baseline
uv run python -m tests.harness.runner --build-exporter run --all-modes
uv run python -m tests.harness.runner --build-exporter --target-operation getOrganizationDevices run --mode slow_valid
uv run python -m tests.harness.runner --build-exporter observe-duration
```

The runner builds the proxy from the local exporter tag with pulls disabled, records the resolved
exporter image ID as a provenance label, and then runs both images by their local `sha256:` IDs. It
creates a fresh CA/certificate with `replay-origin` in its SAN, copies the verified corpus into a
temporary runtime directory, invokes Compose, probes
`/health` and `/metrics`, retains the raw metrics response plus redacted plans, logs, journals,
probes (when available), and aggregate evidence, and always runs `compose down --volumes`. If that
shutdown times out, exits nonzero, or leaves exact-project resources behind, the runner force-removes
only containers and networks bearing the exact run's Compose-project label, verifies that none
remain, and records why the fallback was needed in a redacted `teardown-<mode>.json` artifact and
aggregate evidence. This retention also happens
when a later mode fails, so completed modes and the failed mode's partial evidence are not lost.
Compose cannot pull images, uses an internal network, publishes no host ports, and disables
Watchtower on both services. Health and metrics probes run inside the exporter container and their
output is retained as host-side evidence.

Modes are `baseline`, `trusted_tls`, `unauthorized`, `forbidden`, both seconds and HTTP-date 429
`Retry-After` variants, `timeout`, `stall`, `tls_failure`, `html`, `slow_valid`, real TCP `reset`,
and `dns_failure`. Each emits a monotonic-timestamped journal decision. A target SDK operation can
be selected with `--target-operation`; verified non-target fixtures continue normally, while an
unrecorded or mismatched request fails closed. `slow_valid` additionally requires a two-second delay
and a subsequent matched verified fixture for the faulted route. `stall` requires a barrier-entry and
a recorded deterministic hold before it passes. `reset` requires the proxy abort record and an
exporter-side transport failure log. The 429 modes retain the response-sent `Retry-After` header in
the redacted journal: seconds mode is exactly `2`, while HTTP-date mode must be an HTTP-date value.
Timeout/stall requests enter a deterministic barrier and are released only when the origin process is
torn down.

## DeviceCollector duration observation

`observe-duration` is a separate native replay command, not a fault mode. It starts a clean
baseline replay, requires every manifest route to have a verified-fixture match and HTTP 200 response,
and requires non-empty organization, network, device, and availability cache-population evidence. It
then takes two idle snapshots at least 250 ms apart. Their histogram, collector status,
`device_availability` scheduler state, journal length, and exporter-log length must be identical.
The disposable Compose environment alone enables JSON DEBUG logging so the proof can inspect
structured inventory-cache events; it does not alter production logging.

The runner records wall-clock and monotonic observation boundaries and captures raw `/metrics` plus
authenticated `/status?format=json`. It then waits for the next natural scheduler wrapper invocation;
it deliberately does not use the manual force endpoint, because force bypasses the selected profile
and would call product-family routes absent from the four-route corpus. The disposable Compose
environment supplies a fixed explicitly non-secret token solely for the protected status request.

It writes redacted `duration-observation.json` with the pre/post raw responses, histogram count and
sum, `total_runs`, `total_successes`, `total_failures`, `is_running`, journal boundary, elapsed time,
and calculated mean. It also retains the image IDs, manifest provenance, raw and parsed journal/log
boundaries, parsed scheduler state, corpus-backed product-series evidence, and all deltas. If a gate
fails after startup, the fullest partial candidate is retained with its stage and redacted error;
teardown evidence remains a separate artifact.

Native acceptance is deliberately exact: one histogram observation, one run, one success, no
failures, an advancing collector `last_success_time`, a positive sum, and a positive mean no greater
than the observation elapsed time. The wrapper must use warm caches: structured post-boundary logs
need finite non-negative cache ages and hits for organizations, networks, and devices, with no miss,
update, or invalidation. It must log non-empty device processing while availability remains not due.
The `device_availability` attempt and success state must therefore remain unchanged. This establishes
that the histogram measures every successful top-level collector wrapper, including cached processing
cycles where no endpoint group is due; it is not an API-latency histogram. The journal suffix must be
exactly empty: any post-boundary origin request fails the proof. Teardown remains bounded and must
leave no resources bearing the exact Compose-project label.

This proves only `DeviceCollector`; it does not exercise `ClientsCollector`.
The command fails closed if a newly due endpoint group reaches a route that is absent from the
LIVE-VERIFIED corpus. Capture and sanitise that route under an explicit read-only evidence grant;
never relax the journal gate or invent a response merely to make the observation pass.

The GitHub Actions workflow is manual-only. In **Actions → Failure harness → Run workflow**, provide
`all` to exercise every mode, or provide one of the mode names above to run only that replay. Its
redacted `.failure-harness-artifacts` upload is attempted even when the selected run fails.

## Refreshing the corpus

Only a separately authorised capture may refresh it. Capture into an untracked temporary directory;
never commit raw responses, keys, certificates, addresses, contact details, or credentials. Run
`sanitize_capture_set` once for the complete required operation set so its shared placeholder state
preserves organization/network/device joins:

```python
sanitize_capture_set({
    "getOrganization": organization,
    "getOrganizationNetworks": networks,
    "getOrganizationDevices": devices,
    "getOrganizationDevicesAvailabilities": availabilities,
})
```

It rejects missing required operations and credential fields, replaces MACs with locally administered
stable values and IPs with RFC 5737/RFC 3849 values, and redacts location/user-controlled strings.
Review output, calculate fixture digests, record the capture provenance, then run
`make failure-harness-validate` before committing only sanitized JSON.
