# Documentation

This directory contains the source files for the Meraki Dashboard Exporter documentation site.

## Building Locally

To build and serve the documentation locally:

```bash
# Install dependencies
uv add --dev mkdocs mkdocs-material pymdown-extensions

# Serve locally
uv run mkdocs serve

# Build static site
uv run mkdocs build
```

The documentation will be available at http://localhost:8000

## Structure

- `index.md` - Home page
- `getting-started/` - Installation and setup guides
- `metrics/` - Detailed metric documentation
- `operations/` - Deployment and operational guides
- `integration/` - Integration with Prometheus, Grafana, and OpenTelemetry

## Deployment

The documentation is automatically deployed to GitHub Pages when changes are pushed to the main branch. See `.github/workflows/docs.yml` for the deployment configuration.
