---
id: MDE-0005
title: Delete the stale CFG-BIG getattr guards in app.py
status: Done
assignee: []
created_date: '2026-08-14 15:57'
updated_date: '2026-08-23 18:49'
labels:
  - 'area:core'
  - tech-debt
  - 'priority:low'
  - found-in-source
dependencies: []
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Not migrated from any issue. Found by sweeping the source for `TODO`/`FIXME` residue during the
2026-08-14 tracker migration: these are the only two in `src/`, `tests/`, `scripts/`, `tools/` and
`charts/`, and `CFG-BIG` appears **nowhere else in the repository** — no issue, no doc, no run
artefact. It was an untracked commitment to a "config sweep" with no home, which is exactly the class
of thing this tracker exists to hold.

## The residue

```
src/meraki_dashboard_exporter/app.py:232
    # TODO(CFG-BIG): webhooks.allow_insecure lands with the config sweep;
    # getattr keeps the secure default (False) until then.
    allow_insecure=getattr(self.settings.webhooks, "allow_insecure", False),

src/meraki_dashboard_exporter/app.py:926
    # TODO(CFG-BIG): server.ui_enabled lands with the config sweep;
    # getattr keeps the default (True = UI enabled) until then.
    ui_enabled=getattr(self.settings.server, "ui_enabled", True),
```

## Both fields already landed — verified 2026-08-14

- `WebhookSettings.allow_insecure` — `src/meraki_dashboard_exporter/core/config_models.py:827`,
  `bool = Field(False, ...)`.
- `ServerSettings.ui_enabled` — `src/meraki_dashboard_exporter/core/config_models.py:803`,
  `bool = Field(True, ...)`.

So the sweep the TODOs were waiting for has happened, and the `getattr` guards are stale defensive
residue on two **security-relevant** decisions: whether the webhook receiver may run without a shared
secret, and whether the human UI surface is exposed.

## Why this is worth a task rather than a passing cleanup

`getattr` with a default silently hides the failure it was written to prevent. If either field is ever
renamed, the call site keeps compiling, keeps passing type-checking, and quietly reverts to its
default — which for `ui_enabled` means **exposing the UI**, not suppressing it. Direct attribute
access makes the same rename a `mypy` error, which is the whole reason the settings tree is typed.

Small, self-contained, and touches only `app.py` — a good first task for a lane. Not a security fix
in itself: the current defaults are the safe ones, so the behaviour is correct today. It is the
failure mode that is wrong.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 app.py:232 uses self.settings.webhooks.allow_insecure directly and the TODO(CFG-BIG) comment is gone
- [x] #2 app.py:926 uses self.settings.server.ui_enabled directly and the TODO(CFG-BIG) comment is gone
- [x] #3 No TODO(CFG-BIG) remains anywhere: rg 'CFG-BIG' returns zero hits
- [x] #4 Existing tests covering enforce_webhook_security and ui_guard_decision still pass, and a rename of either settings field is now a mypy error rather than a silent default
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Wave 1 L1: bounded direct-settings cleanup in app.py; child owns local edits and focused validation, root owns integration and final gate.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented and verified in 7327153. make docgen and make check passed; 2,785 tests passed.
<!-- SECTION:FINAL_SUMMARY:END -->
