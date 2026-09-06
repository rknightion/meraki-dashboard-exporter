# docs/

**This is a Zensical site, not MkDocs.** Its plugin and theme behaviour differs from vanilla
`mkdocs-material`, so a `mkdocs.yml`-shaped assumption is wrong here.

The site is not built in this repo. The repository owns `docs.toml` (root); a push to `main`
touching `docs/**`, `docs.toml` or `scripts/**` fires `.github/workflows/trigger-docs-sync.yml`,
which dispatches into `m7kni/m7kni-net-site`. That hub generates the Zensical configuration and
presentation, builds and publishes.

## Generated pages and their generators

Regenerate with `just gen`; each has its own `just docs-*` recipe for one artefact at a time.

| committed artefact | generator |
|---|---|
| `docs/config.md` | `scripts/generate_config_docs.py` |
| `docs/scaling-guide.md` (marker region) | `scripts/generate_scaling_capacity_docs.py` |
| `docs/metrics/metrics.md` | `scripts/generate_metrics_docs.py` |
| `docs/collectors/reference.md` | `scripts/generate_collector_docs.py` |
| `docs/reference/endpoints.md` | `scripts/generate_endpoints_docs.py` |
| `.env.example` (repo root) | `scripts/generate_env_example.py` |
| `charts/meraki-dashboard-exporter/values.yaml` and `templates/configmap.yaml` (marker regions) | `scripts/generate_helm_config.py` |

`docs/changelog.md` is also generated, but by release-please, not by a script:
`release-please-config.json` sets `"changelog-path": "docs/changelog.md"` and the action rewrites it
on every release PR.

`docs/api-call-audit.md` looks generated and is not: it is a hand-maintained point-in-time audit.

## Page conventions

- **Site nav lives in `docs.toml`'s `[[site.nav]]` entries**, not in any file under `docs/`. A new
  page that is not added there is built but unreachable.
- `.meta.yml` (`docs/`, `docs/collectors/`, `docs/metrics/`) supplies per-section SEO and social
  defaults to every page in that directory that does not override the matching frontmatter key.
- Hand-written pages carry YAML frontmatter (`title`, `description`, `tags`, `hide`). Copy the
  shape from a neighbouring page rather than inventing one.
- `docs/includes/abbreviations.md` is appended to every page by the site build, so a glossary term
  belongs there, not repeated per page.
