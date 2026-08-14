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
