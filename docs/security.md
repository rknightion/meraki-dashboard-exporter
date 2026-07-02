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

If you enable the optional Meraki webhook receiver
(`MERAKI_EXPORTER_WEBHOOKS__ENABLED=true`), the exporter will accept JSON
POSTs at `/api/webhooks/meraki`. By default it requires a shared secret
(`MERAKI_EXPORTER_WEBHOOKS__REQUIRE_SECRET=true`); configure
`MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET` to match the value set in your
Meraki Dashboard webhook configuration. Disabling the secret check is
intended for local testing only. Payloads larger than
`MERAKI_EXPORTER_WEBHOOKS__MAX_PAYLOAD_SIZE` (default 1 MB) are rejected.

### API key handling

API keys are loaded as Pydantic `SecretStr` values and are not logged or
serialised in the `/status`, `/metrics`, or web UI surfaces. Treat the
container environment that holds `MERAKI_EXPORTER_MERAKI__API_KEY` as sensitive.

### Endpoint authentication

The exporter serves two categories of HTTP endpoint (see the
[HTTP Endpoints reference](reference/endpoints.md) for the full list):

- **Read-only `GET` endpoints** (`/metrics`, `/status`, `/health`, `/ready`,
  `/clients`, `/cardinality`, ...) are **always unauthenticated**. They expose
  operational metrics and health data but no secrets and no control surface.
- **State-changing `POST` control endpoints** — `/api/collectors/trigger`
  (force an on-demand collector run) and `/api/clients/clear-dns-cache` — can
  optionally be protected by a bearer token.

Set `MERAKI_EXPORTER_SERVER__API_TOKEN` to require callers of those two POSTs to
send `Authorization: Bearer <token>`. When it is unset (the default), those
POSTs are unauthenticated. The webhook receiver
(`POST /api/webhooks/meraki`) is gated separately by its own shared secret
(`MERAKI_EXPORTER_WEBHOOKS__SHARED_SECRET`), not by this token.

**Recommended posture.** Because all GETs are unauthenticated and the control
POSTs default to open, bind the exporter to a trusted interface / private
network and expose only `/metrics` to your Prometheus scraper. Set
`MERAKI_EXPORTER_SERVER__API_TOKEN` if the control POSTs are reachable from any
network segment you do not fully trust.

### Beta API surface

A forthcoming v1 flag (`MERAKI_EXPORTER_BETA_API__ENABLED`, landing with the
support-matrix work) opts the exporter into Meraki's **beta / early-access**
Dashboard API endpoints. Enabling it broadens the data collected but carries
production risk: beta endpoints are unversioned, can change response shape or be
withdrawn without notice, and may carry different rate-limit and stability
guarantees than the GA `/api/v1` surface. Leave it disabled (the default) for
production deployments unless you specifically need a beta-only metric and
accept that it may break on any Meraki-side change.
