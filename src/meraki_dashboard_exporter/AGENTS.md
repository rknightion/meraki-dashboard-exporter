# Package root

- Imports inside the package are relative.
- `create_app()` in `app.py` memoizes one global `FastAPI` instance (`_app_instance`). A second call
  returns the same app and does not re-run `Settings()`, logging or tracing setup, so a test or
  script that wants a fresh app must reset `_app_instance` itself.
- `/ready` returns 503 until every collector owning an enabled priority-<=3 endpoint group has
  completed a successful run. Config-only collectors (all priority-4 groups) are deliberately
  excluded so a readiness probe is not blocked waiting on slow config data.
- `/status` renders HTML; `?format=json` returns `StatusSnapshot.to_dict()` from the same snapshot.
- Web UI: every page template extends `templates/_base.html`; shared navigation, icons, local fonts,
  design tokens, CSS and the persistent theme toggle live in `templates/_icons/` and `static/`, which
  `app.py` mounts at `/static`. Page-specific markup goes in the page template, shared chrome and
  behaviour in the base template or a static asset. Do not reintroduce inline CSS or JS.
