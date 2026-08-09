# Security Policy

## Supported Versions

We release patches for security vulnerabilities. Which versions are eligible for receiving such patches depends on the CVSS v3.0 Rating:

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |
| < latest| :x:                |

## Reporting a Vulnerability

Please report security vulnerabilities to the maintainers via GitHub Security Advisories.

## Security Features

### Container Security

Our Docker images include the following security features:

1. **Non-root User**: Containers run as a non-root user (UID 1000) by default
2. **Minimal Base Image**: Using Python slim-bookworm base image (~40MB)
3. **Read-only Filesystem**: The provided `docker-compose.yml` sets `read_only: true` and mounts `/tmp` as tmpfs
4. **No New Privileges**: Containers cannot gain new privileges (compose defaults)
5. **Health Checks**: Built-in health check endpoints

### Supply Chain Security

1. **Signed Images**: All container images are signed using cosign
2. **SBOM Generation**: Software Bill of Materials (SBOM) generated for every build
3. **Attestations**: Build provenance attestations are generated and published
4. **Vulnerability Scanning**: Automated scanning with Trivy for CRITICAL and HIGH vulnerabilities
5. **Dependency Updates**: Automated dependency updates via Renovate

### Verification

You can verify the authenticity of our container images. Images are built and signed by the
shared `rknightion/.github` [`container-publish.yml`](https://github.com/rknightion/.github/blob/main/.github/workflows/container-publish.yml)
reusable workflow (invoked from this repo's [`publish.yml`](https://github.com/rknightion/meraki-dashboard-exporter/blob/main/.github/workflows/publish.yml)),
so the keyless Fulcio certificate identity reflects *that* reusable workflow's path, not a
workflow file in this repository:

```bash
# Verify container signature
cosign verify ghcr.io/rknightion/meraki-dashboard-exporter:latest \
  --certificate-identity-regexp "^https://github\.com/rknightion/\.github/\.github/workflows/container-publish\.yml@.+$" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"

# Download and inspect SBOM
cosign download sbom ghcr.io/rknightion/meraki-dashboard-exporter:latest

# Verify attestations
cosign verify-attestation ghcr.io/rknightion/meraki-dashboard-exporter:latest \
  --type slsaprovenance \
  --certificate-identity-regexp "^https://github\.com/rknightion/\.github/\.github/workflows/container-publish\.yml@.+$" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
```

## Best Practices

When deploying this exporter:

1. **API Key Security**: Never commit API keys to version control. Use environment variables or secrets management. Where possible, generate a Meraki Dashboard API key for an account with read-only access scoped to the organisations being exported.
2. **Network Security**: Run the exporter in a private network, expose only to authorized Prometheus instances.
3. **Resource Limits**: Apply appropriate CPU and memory limits to prevent resource exhaustion.
4. **Regular Updates**: Keep the exporter updated to receive security patches.

### Webhook receiver

The optional Meraki webhook receiver accepts JSON POSTs at `/api/webhooks/meraki` once enabled
(`MERAKI_EXPORTER_WEBHOOKS__ENABLED=true`). It is configured with:

| Setting | Default | Description |
| --- | --- | --- |
| `MERAKI_EXPORTER_WEBHOOKS__ENABLED` | disabled | Set to `true` to enable the webhook receiver. |
| `MERAKI_EXPORTER_WEBHOOKS__REQUIRE_SECRET` | `true` | Requires a shared secret on incoming webhooks. Disabling the check is intended for local testing only. |
| `MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET` | — | Must match the value set in your Meraki Dashboard webhook configuration. |
| `MERAKI_EXPORTER_WEBHOOKS__MAX_PAYLOAD_SIZE` | `1 MB` | Payloads larger than this are rejected. |

### API key handling

API keys are loaded as Pydantic `SecretStr` values and are not logged or
serialised in the `/status`, `/metrics`, or web UI surfaces. Treat the
container environment that holds `MERAKI_EXPORTER_MERAKI__API_KEY` as sensitive.

### Endpoint authentication

The exporter serves three categories of HTTP endpoint (see the
[HTTP Endpoints reference](reference/endpoints.md) for the full list):

- **Always-open endpoints** (`/metrics`, `/health`, `/ready`) — `/metrics` must
  stay reachable by your Prometheus scraper, and `/health` / `/ready` are
  orchestrator probes. These are never gated.
- **Sensitive `GET` UIs** (`/`, `/status`, `/config`, `/clients`,
  `/cardinality*`, `/api/metrics/cardinality`) — these expose PII and
  operational detail (see the threat model below). They are open by default but
  can be **token-gated** (`MERAKI_EXPORTER_SERVER__API_TOKEN`) and/or
  **suppressed entirely** (`MERAKI_EXPORTER_SERVER__UI_ENABLED=false`).
- **State-changing `POST` control endpoints** — `/api/collectors/trigger`
  (force an on-demand collector run) and `/api/clients/clear-dns-cache` — can
  optionally be protected by the same bearer token.

Set `MERAKI_EXPORTER_SERVER__API_TOKEN` to require callers of the sensitive GET
UIs and the control POSTs to send `Authorization: Bearer <token>` (a
constant-time compare). When it is unset (the default), those endpoints are
unauthenticated. The webhook receiver (`POST /api/webhooks/meraki`) is gated
separately by its own shared secret
(`MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET`), not by this token.

### Endpoint exposure & threat model

**Default posture is unauthenticated and plaintext.** The exporter binds
`0.0.0.0:9099` with no TLS and, by default, no auth on any endpoint. Anyone who
can reach the port can read everything below. This is acceptable **only** on a
trusted/private interface; for any other deployment apply the mitigations that
follow.

What each endpoint exposes:

| Endpoint | Method | Exposes | PII? | Mitigation |
| --- | --- | --- | --- | --- |
| `/metrics` | GET | All metric series: full device/network topology, label values | Low (topology) | Keep open for Prometheus; restrict at the network layer |
| `/` | GET | Collector health, tier schedule, org count | No | `ui_enabled=false` |
| `/status` | GET | Topology-ish health, org health, network-filter state, webhook health | No | token / `ui_enabled=false` |
| `/config` | GET | Effective configuration (secrets masked as `**********`) | No (redacted) | token / `ui_enabled=false` |
| `/clients` | GET | **Client MAC / IP / hostname / username** | **Yes** | token / `ui_enabled=false` |
| `/cardinality*`, `/api/metrics/cardinality` | GET | Metric + label-value surface | Low | token / `ui_enabled=false` |
| `/api/collectors/trigger` | POST | Burns org API-rate-limit budget on demand | No | `api_token` |
| `/api/clients/clear-dns-cache` | POST | Clears DNS cache | No | `api_token` |
| `/api/webhooks/meraki` | POST | Ingest surface | No | shared secret |

For the full client-tracking privacy/GDPR picture — exactly which fields are PII,
where they land (metrics WAL, the `/clients` cache, optional OTel data-logs), and
every mitigation control — see [Data Privacy](privacy.md).

**Mitigations (v1).**

- **Bearer token** — set `MERAKI_EXPORTER_SERVER__API_TOKEN`. Sensitive GET UIs
  and control POSTs then require `Authorization: Bearer <token>`; `/metrics` and
  the probes stay open so Prometheus/Kubernetes keep working.
- **Suppress the UI** — set `MERAKI_EXPORTER_SERVER__UI_ENABLED=false` to drop
  the human UI surface (`/`, `/status`, `/config`, `/clients`, `/cardinality*`)
  entirely; they return `404`. Use this when you only need `/metrics` scraped
  and want no PII/detail surface at all.
- **Reverse proxy + TLS (recommended for any exposed deployment).** Terminate
  TLS and authenticate at a reverse proxy (nginx / Traefik / Caddy / an ingress
  controller) in front of the exporter, and forward only `/metrics` to your
  scraper. Example nginx sketch:

  ```nginx
  server {
    listen 443 ssl;
    ssl_certificate     /etc/ssl/exporter.crt;
    ssl_certificate_key /etc/ssl/exporter.key;

    # Only expose /metrics to the scraper; everything else stays internal.
    location = /metrics {
      allow 10.0.0.0/8;   # Prometheus subnet
      deny  all;
      proxy_pass http://127.0.0.1:9099;
    }
    location / { deny all; }
  }
  ```

  Native listener TLS/mTLS on the exporter itself is a separate, later roadmap
  item; for v1 the supported pattern is reverse-proxy termination.

**Recommended posture.** Bind the exporter to a trusted interface / private
network and expose only `/metrics` (via a reverse proxy where possible). Set
`MERAKI_EXPORTER_SERVER__API_TOKEN` and/or
`MERAKI_EXPORTER_SERVER__UI_ENABLED=false` whenever the sensitive GET UIs or
control POSTs are reachable from any network segment you do not fully trust.

### Beta / early-access API surface

The exporter **never calls Meraki's beta / early-access Dashboard API endpoints**
and never enrolls an org into them — beta endpoints are unversioned and can change
shape or be withdrawn without notice, so consuming them would undermine the v1
stability promise. There is deliberately no flag to opt in.

Instead, the exporter treats an org being on the beta spec as a **risk signal**.
The org's Early Access opt-ins are surfaced as always-on metrics
(`meraki_org_early_access_opt_in_info`, `meraki_org_early_access_opt_in_scoped_networks`),
and a dedicated `meraki_org_has_beta_api` gauge (`1`/`0` per org) plus a startup/runtime
**WARN log** fire when an org has opted into `has_beta_api`. This matters because
`has_beta_api` flips the *whole org* to the beta Dashboard spec, which can move
endpoints this exporter assumes are stable onto the beta surface and silently break
collection — alert on `meraki_org_has_beta_api == 1` to catch that. The exporter only
*reads* the opt-in state; enrolling or un-enrolling an org remains a human decision
made via the Meraki dashboard.
