# AGENTS.md

This repository is designed to be edited by automated agents.

## Workflow Requirements

- **Run checks before every commit**:
  - `make format`
  - `make lint`
  - `make typecheck`
  - `make test`
- Use `uv` and `docker` as defined in the `Makefile` for development.
- Do not modify the generated files `docs/metrics/metrics.md` or `docs/config.md`
  directly. They are produced by the scripts in `src/meraki_dashboard_exporter/tools/`.
- Use the domain models and enums defined under `src/meraki_dashboard_exporter/core`.
- Keep commit messages concise and descriptive.
- Place documentation in the `docs/` folder following MkDocs conventions.

## Reference
See `CLAUDE.md` for project architecture and coding conventions.
