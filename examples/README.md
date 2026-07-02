# examples/

This directory is reserved for **real deployment and configuration examples** — the
kind of thing an operator copies to get the exporter running (e.g. starter Prometheus
alert rules, docker-compose snippets, Kubernetes manifests). It is intentionally empty
right now; the first occupant is tracked by the starter-alert-rules work (config
example: `examples/prometheus-rules.yaml`).

It previously held `test_example_with_helpers.py`, a demo of the collector-test
patterns (`BaseCollectorTest`, `MockAPIBuilder`, factories, `MetricAssertions`). That
was misleading here for two reasons: it wasn't a usage example at all, and it had gone
stale — it imported from an old `..testing.base`/`..testing.factories` path that no
longer exists (the real helpers now live under `tests/helpers/`), and it wasn't
collected by pytest anyway (`testpaths` in `pyproject.toml` only covers `tests/` and
`tools/apidrift/tests`). Its content is now fully superseded by
`tests/unit/test_alerts_collector.py`, which exercises the same `AlertsCollector`
against the current `tests.helpers.*` APIs.

For the test-writing patterns that file used to demonstrate, see `tests/CLAUDE.md` and
`tests/unit/test_alerts_collector.py` for a live, currently-passing example.

For actual configuration examples today (until this directory gains deploy artifacts
of its own), see:
- `.env.example` at the repo root
- `docker-compose.yml` / `docker-compose.*.yml`
- `charts/meraki-dashboard-exporter/values.yaml`
