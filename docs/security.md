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

You can verify the authenticity of our container images:

```bash
# Verify container signature
cosign verify ghcr.io/rknightion/meraki-dashboard-exporter:latest \
  --certificate-identity-regexp "https://github.com/rknightion/meraki-dashboard-exporter/.github/workflows/docker-build.yml@refs/heads/main" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"

# Download and inspect SBOM
cosign download sbom ghcr.io/rknightion/meraki-dashboard-exporter:latest

# Verify attestations
cosign verify-attestation ghcr.io/rknightion/meraki-dashboard-exporter:latest \
  --type slsaprovenance \
  --certificate-identity-regexp "https://github.com/rknightion/meraki-dashboard-exporter/.github/workflows/docker-build.yml@refs/heads/main" \
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
container environment that holds `MERAKI_API_KEY` as sensitive.
