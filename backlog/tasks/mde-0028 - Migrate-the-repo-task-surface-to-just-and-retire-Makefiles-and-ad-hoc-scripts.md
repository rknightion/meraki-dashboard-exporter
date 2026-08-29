---
id: MDE-0028
title: Migrate the repo task surface to just and retire Makefiles and ad-hoc scripts
status: To Do
assignee: []
created_date: '2026-08-28 19:29'
updated_date: '2026-08-29 09:18'
labels:
  - 'wave:2-fleet'
dependencies: []
priority: medium
type: chore
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Migrate this repo's developer and CI task surface to the `just` command runner, per the frozen fleet
standard (mandatory vocabulary `default` / `setup` / `fmt` / `fmt-check` / `lint` / `test` / `check`;
six groups `check` / `build` / `dev` / `gen` / `infra` / `release`; one self-contained top-level
`justfile`; no shared or vendored `.just` file; no unstable `just` features).

Everything in this task was verified against the repo as it stands and against `just 1.58.0`. The
justfile below is not a sketch: it was written out and run through `just --fmt --check` (exit 0),
`just --list` (exit 0), `just --groups` (prints exactly the six), `just --dump --dump-format json`
(exit 0) and `just --dry-run check` (expands to the exact `.github/workflows/ci.yml` `test`-job
command sequence). Drop it in and adjust only if the toolchain has moved since.

## 1. Outcome

The repo has a top-level `justfile` and no `Makefile`. `just --list` is the one true answer to "what
can I do here". `just check` runs, in order, exactly what the `ci.yml` `test` job runs — ruff format
check, ruff lint, mypy, the eight doc generators plus a drift diff, the offline Meraki model
conformance check, and the marker-filtered pytest run with the 80% coverage floor — so a green local
gate is a green CI `test` job. `just ci` additionally covers the `docker-build-test` and
`helm-lint-kubeconform` legs of `ci-success` for anyone with Docker, Helm and kubeconform installed.
`scripts/generate-docs.sh` is gone, absorbed into the `gen` recipe's dependency list;
`scripts/cloud-environment-setup.sh` survives as a file (it bootstraps a cloud container that has no
`just` yet) but now installs `just` and ends by telling the agent to run `just check`. Every workflow
step that held build/test/lint/generate logic is a one-line `run: just <recipe>` behind a pinned
`extractions/setup-just` step. `AGENTS.md`, the per-directory `CLAUDE.md` files, `docs/`, and
`backlog/config.yml`'s `definition_of_done` name `just` recipes, never `make` targets.

## 2. The complete justfile

Create this at the repo root as `justfile` (lowercase, no extension).

```just
set shell := ["bash", "-euo", "pipefail", "-c"]

# Docker BuildKit, carried over from the retired Makefile.
export DOCKER_BUILDKIT := "1"
export COMPOSE_DOCKER_CLI_BUILD := "1"

image_name := "meraki-dashboard-exporter"
registry := "ghcr.io/rknightion"
py_version := "3.14"
chart := "charts/meraki-dashboard-exporter"
meraki_spec_url := "https://raw.githubusercontent.com/meraki/openapi/master/openapi/spec3.json"

# Every path a scripts/generate_*.py writes. `gen-check` diffs exactly these.
generated := "docs/config.md docs/metrics/metrics.md docs/collectors/reference.md docs/reference/endpoints.md docs/scaling-guide.md .env.example charts/meraki-dashboard-exporter/values.yaml charts/meraki-dashboard-exporter/templates/configmap.yaml"

version := `sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml 2>/dev/null || echo 0.0.0`

# show the task surface
default:
    @just --list

# install the pinned Python and the locked dev dependencies into .venv
setup:
    uv python install {{ py_version }}
    uv sync --all-extras --locked

# format Python sources and this justfile in place
[group('check')]
fmt:
    uv run ruff format .
    just --fmt

# verify Python and justfile formatting; never writes
[group('check')]
[no-exit-message]
fmt-check:
    uv run ruff format --check .
    just --fmt --check

# lint with ruff; never writes
[group('check')]
[no-exit-message]
lint:
    uv run ruff check --no-fix .

# lint with ruff and apply its safe autofixes
[group('check')]
lint-fix:
    uv run ruff check --fix .

# type-check with mypy - this is the gate
[group('check')]
[no-exit-message]
typecheck:
    uv run mypy .

# advisory astral ty preview run; diagnostics are informational only
[group('check')]
ty:
    -uv run ty check src
    @echo "ty is advisory only - mypy (just typecheck) remains the source of truth"

# run the PR test suite; a filter narrows it with -k and drops the coverage floor
[group('check')]
[no-exit-message]
test filter="":
    uv run pytest -m "not fleet_scheduled and not fleet_on_demand" {{ if filter == "" { "--cov=meraki_dashboard_exporter --cov-report=xml --cov-fail-under=80" } else { "-k " + quote(filter) } }}

# run the scheduled fleet scale presets (slow, cron-only in CI)
[group('check')]
[no-exit-message]
test-fleet-scheduled:
    uv run pytest -m fleet_scheduled -v -s --timeout=300

# run the on-demand fleet scale presets (slow, dispatch-only in CI)
[group('check')]
[no-exit-message]
test-fleet-on-demand:
    uv run pytest -m fleet_on_demand -v -s --timeout=300

# offline Meraki model-conformance check against the vendored spec
[group('check')]
[no-exit-message]
api-conformance:
    PYTHONPATH=src:tools uv run python -m apidrift --baseline spec/meraki-openapi.json.gz --live spec/meraki-openapi.json.gz --ignore spec/apidrift-ignore.txt --src src --conformance-only --format md

# full drift check against the LIVE Meraki spec; fetches over the network
[group('check')]
[no-exit-message]
api-drift:
    PYTHONPATH=src:tools uv run python -m apidrift --baseline spec/meraki-openapi.json.gz --live-url "{{ meraki_spec_url }}" --ignore spec/apidrift-ignore.txt --src src --format md

# suggest source operations for unmapped Pydantic models (review aid)
[group('check')]
api-suggest:
    PYTHONPATH=src:tools uv run python -m apidrift --baseline spec/meraki-openapi.json.gz --live spec/meraki-openapi.json.gz --src src --suggest

# validate the committed live-verified failure corpus
[group('check')]
[no-exit-message]
harness-validate:
    uv run python -m tests.harness.runner validate-corpus

# fail if the committed generated artefacts drift from the source tree
[group('check')]
gen-check: gen
    @git diff --quiet -- {{ generated }} || { echo "::error::Generated artefacts are stale. Run 'just gen' and commit the result."; git diff --stat -- {{ generated }}; git diff -- {{ generated }}; exit 1; }

# lint the chart, render it, and schema-validate the rendered manifests
[group('check')]
helm-check:
    {{ require('helm') }} lint {{ chart }} --set meraki.apiKey=dummy
    {{ require('helm') }} template test-release {{ chart }} --set meraki.apiKey=dummy > /tmp/rendered-manifests.yaml
    {{ require('kubeconform') }} -summary -strict -ignore-missing-schemas /tmp/rendered-manifests.yaml

# assert image labels and the non-root runtime user on a built image
[group('check')]
[script('bash')]
image-verify tag="meraki-dashboard-exporter:latest":
    set -euo pipefail
    docker run --rm -e MERAKI_EXPORTER_MERAKI__API_KEY=00000000000000000000000000000000deadbeef '{{ tag }}' --help
    docker inspect '{{ tag }}' | jq '.[0].Config.Labels'
    actual_user="$(docker run --rm --entrypoint whoami '{{ tag }}')"
    if [ "${actual_user}" != "exporter" ]; then
      echo "::error::Container runs as '${actual_user}', expected non-root user 'exporter'"
      exit 1
    fi
    echo "Verified container runs as non-root user: ${actual_user}"
    configured_user="$(docker inspect -f '{{{{.Config.User}}' '{{ tag }}')"
    if [ "${configured_user}" != "exporter" ]; then
      echo "::error::Image Config.User is '${configured_user}', expected 'exporter'"
      exit 1
    fi

# run container-structure-test against a built image
[group('check')]
[no-exit-message]
image-structure tag="meraki-dashboard-exporter:latest":
    {{ require('container-structure-test') }} test --image '{{ tag }}' --config .github/container-structure-test.yaml

# start a built image and assert /health and /metrics answer 200
[group('check')]
[script('bash')]
smoke tag="meraki-dashboard-exporter:latest":
    set -euo pipefail
    container_id="$(docker run -d --rm -p 9099:9099 -e MERAKI_EXPORTER_MERAKI__API_KEY=00000000000000000000000000000000deadbeef -e MERAKI_EXPORTER_MERAKI__ORG_ID=123456 '{{ tag }}')"
    echo "Started container ${container_id}"
    cleanup() {
      echo "::group::container logs"
      docker logs "${container_id}" || true
      echo "::endgroup::"
      docker stop "${container_id}" >/dev/null 2>&1 || true
    }
    trap cleanup EXIT
    check_endpoint() {
      local path="$1"
      local status=000
      for attempt in $(seq 1 30); do
        status="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:9099${path}" || echo 000)"
        if [ "${status}" = "200" ]; then
          echo "${path} responded 200 on attempt ${attempt}"
          return 0
        fi
        sleep 2
      done
      echo "::error::${path} did not return 200 after retries (last status: ${status})"
      return 1
    }
    check_endpoint /health
    check_endpoint /metrics

# THE GATE - exactly what the CI `test` job enforces
[group('check')]
check: fmt-check lint typecheck gen-check api-conformance test

# `check` plus the container and chart legs of ci-success; needs docker, helm, kubeconform
[group('check')]
ci: check helm-check image image-verify image-structure smoke

# regenerate every committed generated artefact from the source tree
[group('gen')]
gen: docs-config docs-env docs-helm docs-scaling docs-metrics docs-collectors docs-endpoints validate-env-docs

# regenerate docs/config.md from the Pydantic settings models
[group('gen')]
docs-config:
    uv run python scripts/generate_config_docs.py

# regenerate .env.example from the settings tree
[group('gen')]
docs-env:
    uv run python scripts/generate_env_example.py

# regenerate the chart's config knobs and ConfigMap env mapping
[group('gen')]
docs-helm:
    uv run python scripts/generate_helm_config.py

# regenerate the network-health capacity region of docs/scaling-guide.md
[group('gen')]
docs-scaling:
    uv run python scripts/generate_scaling_capacity_docs.py

# regenerate docs/metrics/metrics.md from the metric constructors
[group('gen')]
docs-metrics:
    uv run python scripts/generate_metrics_docs.py

# regenerate docs/collectors/reference.md from the collector classes
[group('gen')]
docs-collectors:
    uv run python scripts/generate_collector_docs.py

# regenerate docs/reference/endpoints.md from the FastAPI routes
[group('gen')]
docs-endpoints:
    uv run python scripts/generate_endpoints_docs.py

# validate documented MERAKI_EXPORTER_* vars against the settings tree
[group('gen')]
[no-exit-message]
validate-env-docs:
    uv run python scripts/validate_documented_env_vars.py

# re-vendor spec/meraki-openapi.json.gz from upstream Meraki
[group('gen')]
refresh-spec:
    curl -fsSL "{{ meraki_spec_url }}" -o /tmp/meraki-spec3.json
    @python3 -c "import json; print('info.version =', json.load(open('/tmp/meraki-spec3.json'))['info']['version'])"
    gzip -9 -c /tmp/meraki-spec3.json > spec/meraki-openapi.json.gz
    @echo "Vendored spec/meraki-openapi.json.gz - now update the version note in spec/README.md"

# build the sdist and wheel into dist/
[group('build')]
build:
    uv build

# build the exporter image for this architecture and load it locally
[group('build')]
image:
    docker buildx build --load --tag {{ image_name }}:latest --tag {{ image_name }}:{{ version }} --build-arg PY_VERSION={{ py_version }} --cache-from type=local,src=/tmp/.buildx-cache --cache-to type=local,dest=/tmp/.buildx-cache,mode=max .

# build the exporter image for amd64 and arm64 (cannot be loaded locally)
[group('build')]
image-all:
    docker buildx build --platform linux/amd64,linux/arm64 --tag {{ image_name }}:latest --tag {{ image_name }}:{{ version }} --build-arg PY_VERSION={{ py_version }} --cache-from type=local,src=/tmp/.buildx-cache --cache-to type=local,dest=/tmp/.buildx-cache,mode=max .

# run the exporter from source (long-running; ctrl-c to stop)
[group('dev')]
run:
    uv run python -m meraki_dashboard_exporter

# run the exporter with uvicorn auto-reload (long-running; ctrl-c to stop)
[group('dev')]
run-dev:
    uv run uvicorn meraki_dashboard_exporter.app:create_app --factory --reload --host 0.0.0.0 --port 9099

# build then run the exporter image (long-running; ctrl-c to stop)
[group('dev')]
image-run: image
    docker run --rm -it -p 9099:9099 -e MERAKI_EXPORTER_MERAKI__API_KEY -e MERAKI_EXPORTER_LOGGING__LEVEL=DEBUG {{ image_name }}:latest

# build then open a shell inside the exporter image
[group('dev')]
image-shell: image
    docker run --rm -it --entrypoint /bin/sh {{ image_name }}:latest

# print the local image's manifest
[group('dev')]
image-inspect:
    docker buildx imagetools inspect {{ image_name }}:latest

# print the index digest to pin on both Dockerfile FROM lines
[group('dev')]
image-base-digest:
    docker buildx imagetools inspect python:{{ py_version }}-slim-bookworm --format '{{{{println .Manifest.Digest}}'

# build locally and replay one failure mode, or pass mode=all
[group('dev')]
harness-run mode="baseline":
    uv run python -m tests.harness.runner --build-exporter run {{ if mode == "all" { "--all-modes" } else { "--mode " + quote(mode) } }}

# write the HTML coverage report to htmlcov/ and open it
[group('dev')]
coverage-report:
    uv run pytest --cov=meraki_dashboard_exporter --cov-report=html --cov-report=term
    @just _open htmlcov/index.html

# upgrade uv.lock to the newest allowed versions
[group('dev')]
deps-update:
    uv lock --upgrade

# print the resolved dependency tree
[group('dev')]
deps-show:
    uv tree

# print outdated dependencies
[group('dev')]
deps-outdated:
    uv pip list --outdated

# install the pre-commit framework hooks into .git/hooks
[group('dev')]
install-hooks:
    uvx pre-commit install

# print the version in pyproject.toml
[group('dev')]
version:
    @echo {{ version }}

# list TODO/FIXME/XXX markers under src/
[group('dev')]
todo:
    @grep -rn "TODO\|FIXME\|XXX" --include="*.py" src/ || echo "No TODO items found"

# remove build, cache and coverage artefacts
[group('dev')]
clean:
    rm -rf build/ dist/ *.egg-info .coverage coverage.xml htmlcov/ .pytest_cache/ .ruff_cache/ .mypy_cache/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete

# start the local docker compose stack (long-running; ctrl-c to stop)
[group('infra')]
compose-up:
    docker compose -f docker-compose.yml up --build

# stop the local docker compose stack
[group('infra')]
compose-down:
    docker compose -f docker-compose.yml down

# create and bootstrap the multi-arch buildx builder
[group('infra')]
buildkit-setup:
    docker buildx create --name multiarch-builder --driver docker-container --use || true
    docker buildx inspect --bootstrap

# show the buildx builders and the active one
[group('infra')]
buildkit-info:
    docker buildx ls
    docker buildx inspect

# build and PUSH the multi-arch image to the registry
[confirm('Push a multi-arch image to ghcr.io? Releases normally go through release-please.')]
[group('release')]
image-push:
    docker buildx build --platform linux/amd64,linux/arm64 --push --tag {{ registry }}/{{ image_name }}:latest --tag {{ registry }}/{{ image_name }}:{{ version }} --build-arg PY_VERSION={{ py_version }} --cache-from type=local,src=/tmp/.buildx-cache --cache-to type=local,dest=/tmp/.buildx-cache,mode=max .

# prune the machine-wide docker buildx cache
[confirm('Prune the machine-wide docker buildx cache?')]
[group('release')]
clean-docker:
    docker buildx prune -f
    rm -rf /tmp/.buildx-cache

[macos]
[private]
_open target:
    open '{{ target }}'

[linux]
[private]
_open target:
    xdg-open '{{ target }}'
```

### Notes on deliberate choices in the file above

- **`check` is the source-tree gate; `ci` is the superset.** `ci-success` gates on three jobs
  (`test`, `docker-build-test`, `helm-lint-kubeconform`). Making `check` depend on the container and
  chart legs would require a running Docker daemon, `helm` and `kubeconform` for every `just check`,
  which agents would then route around — the exact failure §1 of the standard warns about, arrived at
  from the other direction. So `check` == the `test` job (a fast, always-runnable source gate) and
  `ci` == `check` + `helm-check` + `image` + `image-verify` + `image-structure` + `smoke`. Both are in
  the `check` group and both are named in the docs.
- **No `set dotenv-load`.** A real `.env` exists in working copies and holds a live Meraki API key.
  The Makefile never sourced it and neither does the justfile; loading it would silently change every
  recipe's environment.
- **`export DOCKER_BUILDKIT` / `COMPOSE_DOCKER_CLI_BUILD`** carry over the Makefile's `export` lines
  verbatim (standard §12: `export VAR` → `export var := "…"`).
- **`version` is a backtick assignment**, evaluated lazily (`"eager":false` in `just --dump`), so
  `just --list` does not shell out. The `|| echo 0.0.0` fallback is preserved from the Makefile.
- **`GITHUB_REPO` is dropped.** `Makefile:9` defines it and nothing uses it — verified dead.
- **`fmt` lives in the `check` group** alongside `fmt-check`, so `just --group check` shows the whole
  quality surface including its fix half.

## 3. Makefile disposition

One Makefile only: `/Users/rob/repos/meraki-dashboard-exporter/Makefile` (349 lines). No
`GNUmakefile`, no subdirectory Makefiles.

| Make target (line) | Replacement recipe | Notes |
|---|---|---|
| `help` (34) | `default` | The `grep`/`awk` self-documenting block is replaced by `just --list`. |
| `install` (47) | `setup` | `uv sync` → `uv sync --all-extras --locked`; merged with `install-dev`. |
| `install-dev` (52) | `setup` | Merged. `setup` also does `uv python install 3.14`. |
| `format` (58) | `fmt` | `fmt` additionally runs `just --fmt` (standard §1). |
| `lint` (63) | `lint` + `fmt-check` | The make target bundled `ruff check` and `ruff format --check`; the standard splits them. **`check` depends on both**, so CI parity holds. |
| `lint-fix` (69) | `lint-fix` | Unchanged body. |
| `typecheck` (74) | `typecheck` | Unchanged body (`uv run mypy .`). |
| `ty` (79) | `ty` | `-` error-ignore prefix carries over identically (standard §12). Still advisory, still not in `check`. |
| `test` (85) | `test` | **Body changed to the CI command** — `-m "not fleet_scheduled and not fleet_on_demand" --cov=meraki_dashboard_exporter --cov-report=xml --cov-fail-under=80`. `make test` was `pytest -v`, which is not what CI runs. See trap 4. |
| `test-cov` (90) | `coverage-report` | Merged into `coverage-report`, which was its only consumer. |
| `coverage-report` (95) | `coverage-report` | `$(OPEN_CMD)` `ifeq` becomes two `[private]` `_open` recipes attributed `[macos]` / `[linux]`. |
| `check` (100) | `check` | **Expanded.** Was `lint typecheck test`. Now `fmt-check lint typecheck gen-check api-conformance test` — the four CI checks the make target silently omitted. |
| `refresh-meraki-spec` (107) | `refresh-spec` | Renamed (shorter, group `gen`). Body identical including the `spec/README.md` reminder. |
| `api-drift` (115) | `api-drift` | Body identical, collapsed to one line (each just recipe line is its own shell). |
| `api-conformance` (123) | `api-conformance` | Body identical. Now a `check` dependency, matching CI. |
| `api-suggest` (131) | `api-suggest` | Body identical. |
| `docker-build` (139) | `image` | Same buildx flags, same two tags, same local cache paths. |
| `docker-build-all` (151) | `image-all` | Same. |
| `docker-build-push` (164) | `image-push` | Group `release`, **`[confirm]` mandatory** (mutates a remote registry). |
| `docker-run` (177) | `image-run` | Keeps the `image` dependency. |
| `docker-shell` (186) | `image-shell` | Keeps the `image` dependency. |
| `docker-test` (193) | `image-verify` | Widened to the full CI assertion set: `--help`, label dump, `whoami` exact match, `Config.User` exact match. `[script('bash')]` — it has `if` blocks. |
| `docker-inspect` (199) | `image-inspect` | Dropped the `|| echo "Image not found"` tail; `docker buildx imagetools inspect` already prints a good error. |
| `docker-base-digest` (204) | `image-base-digest` | Go template `{{.Manifest.Digest}}` must be escaped — see trap 3. |
| `docker-compose-up` (210) | `compose-up` | Group `infra`. |
| `docker-compose-down` (215) | `compose-down` | Group `infra`. |
| `failure-harness-validate` (220) | `harness-validate` | Renamed. **`tests/unit/test_failure_harness_713.py:805` asserts on this string inside `Makefile` — see trap 1.** |
| `failure-harness-run` (224) | `harness-run mode="baseline"` | `$(or $(MODE),baseline)` → a real parameter default. `mode=all` maps to `--all-modes`, matching `failure-harness.yml`. |
| `buildkit-setup` (229) | `buildkit-setup` | Group `infra`. Body identical. |
| `buildkit-info` (236) | `buildkit-info` | Group `infra`. Body identical. |
| `version` (245) | `version` | Body identical minus the ANSI colour codes. |
| `build` (250) | `build` | `uv build`. |
| `docgen` (256) | `gen` | Absorbs `scripts/generate-docs.sh` as a dependency list of eight recipes in the same order. |
| `docs-metrics` (261) | `docs-metrics` | Unchanged. |
| `docs-config` (266) | `docs-config` | Unchanged. |
| `docs-collectors` (271) | `docs-collectors` | Unchanged. |
| `docs-endpoints` (276) | `docs-endpoints` | Unchanged. |
| *(none)* | `docs-env`, `docs-helm`, `docs-scaling`, `validate-env-docs` | **New.** These four generators were only reachable through `generate-docs.sh`; the Makefile had no per-generator target for them. |
| `run` (282) | `run` | Unchanged. Doc comment marks it long-running. |
| `run-dev` (287) | `run-dev` | Unchanged. Doc comment marks it long-running. |
| `clean` (293) | `clean` | Added `coverage.xml` (CI writes it, the Makefile did not clean it). |
| `clean-docker` (300) | `clean-docker` | `[confirm]` — `docker buildx prune -f` is machine-wide, not repo-scoped. |
| `pre-commit` (307) | *(dropped)* | Was `format lint typecheck`. `just check` supersedes it; `.pre-commit-config.yaml` is the real hook config and is untouched. |
| `install-hooks` (311) | `install-hooks` | `uvx pre-commit install`. Unchanged. |
| `tree` (318) | *(dropped)* | Shell-out to an optional `tree` binary with a hand-maintained ignore list. No recipe. |
| `todo` (322) | `todo` | Body identical. |
| `metrics` (327) | *(dropped)* | `docker-run` + `sleep 3` + `$(OPEN_CMD)` on a long-running foreground container — it never worked as written (the `open` never runs until the container exits). Use `just image-run` and browse to `http://localhost:9099/metrics`. |
| `deps-update` (334) | `deps-update` | Unchanged. |
| `deps-show` (339) | `deps-show` | Unchanged. |
| `deps-outdated` (344) | `deps-outdated` | Unchanged. |
| `.PHONY` / `RED`/`GREEN`/`YELLOW`/`BLUE`/`NC` / `UNAME_S` / `OPEN_CMD` / `GITHUB_REPO` | *(deleted)* | `.PHONY` is meaningless in just; the colour vars were only for `@echo` decoration; `UNAME_S`/`OPEN_CMD` become `[macos]`/`[linux]` attributes; `GITHUB_REPO` was dead. |

**Then delete it:** `git rm Makefile`. This must happen in the same commit as the
`tests/unit/test_failure_harness_713.py:805` edit (trap 1) and the `.dockerignore` edit (trap 2).

## 4. Script disposition

Two tracked shell scripts (`git ls-files | grep -E '\.(sh|bash|zsh|ps1)$'`). Nine Python helpers under
`scripts/`. One Python tool package under `tools/`. One shipped runtime entrypoint.

| File | Verdict | Recipe | Detail |
|---|---|---|---|
| `scripts/generate-docs.sh` | **ABSORB** | `gen` | Pure sequencer: eight `"${RUNNER[@]}" "$SCRIPT_DIR/<generator>.py"` calls in a fixed order. Becomes `gen: docs-config docs-env docs-helm docs-scaling docs-metrics docs-collectors docs-endpoints validate-env-docs` — just runs dependencies sequentially in listed order, preserving the ordering the script relied on. `git rm scripts/generate-docs.sh` **last**, after `ci.yml:67` and every doc reference are updated. |
| `scripts/cloud-environment-setup.sh` | **KEEP** | `setup` does not wrap it — it is not a developer command | It bootstraps a container that has no `uv`, no `npm`-installed Backlog.md, and no `just`; it is pasted verbatim into the Codex Cloud / Claude Code "environment setup script" field (`scripts/cloud-environment-setup.sh:4`, `backlog/tasks/mde-0006`), i.e. an external, non-developer, non-CI consumer. It also has real control flow (version comparison, `.bashrc` PATH persistence, conditional installs). **Two required edits inside it:** add a pinned `just` install alongside the `uv` and Backlog.md installs, and change the final line `Run 'make check' to execute the full validation gate.` to `Run 'just check' to execute the full validation gate.` |
| `scripts/generate_config_docs.py` | **KEEP** | `docs-config` | Real program — `importlib`-loads `core/config_models.py` and walks Pydantic `FieldInfo`. |
| `scripts/generate_env_example.py` | **KEEP** | `docs-env` | Real program — writes `.env.example` from the settings tree. |
| `scripts/generate_helm_config.py` | **KEEP** | `docs-helm` | Real program — splices marker-delimited regions into `values.yaml` and `templates/configmap.yaml`. |
| `scripts/generate_scaling_capacity_docs.py` | **KEEP** | `docs-scaling` | Real program — AST-parses `NetworkHealthCollector.endpoint_groups`. |
| `scripts/generate_metrics_docs.py` | **KEEP** | `docs-metrics` | Real program — two AST visitor classes. |
| `scripts/generate_collector_docs.py` | **KEEP** | `docs-collectors` | Real program — AST walk of the collectors package. |
| `scripts/generate_endpoints_docs.py` | **KEEP** | `docs-endpoints` | Real program — AST walk of the FastAPI routes. |
| `scripts/validate_documented_env_vars.py` | **KEEP** | `validate-env-docs` | Real program — validator, not a task. |
| `tools/apidrift/` (package, `__main__.py` + 9 modules + 10 test modules) | **KEEP** | `api-conformance`, `api-drift`, `api-suggest` | A program with its own test suite in `testpaths`. |
| `tests/harness/runner` (`python -m tests.harness.runner`) | **KEEP** | `harness-validate`, `harness-run` | A program. |
| `docker-entrypoint.py` | **KEEP** | *(none — never invoked by a developer)* | Shipped runtime artifact; it is the image `ENTRYPOINT` and executes on a target machine with no `just`. Do not touch. |

## 5. CI changes

### The setup-just step (exact YAML)

Insert this immediately after the `astral-sh/setup-uv` / `actions/checkout` steps in every job that
gains a `just` call. Resolve the real commit SHA for `extractions/setup-just` v4 before committing —
do not invent one; the fleet convention is SHA-pinned with a trailing `# vN` comment.

```yaml
      - name: Set up just
        uses: extractions/setup-just@<RESOLVE-SHA-FOR-v4> # v4
        with:
          just-version: '1.58.0'
```

`just-version` is pinned exactly: `just --fmt` output is explicitly outside any backwards-compatibility
guarantee, so an unpinned bump can turn `fmt-check` red with no repo change. `apt install just` is not
an option on the runners.

### `.github/workflows/ci.yml`

**Job `test`** — insert setup-just after line 45 (`enable-cache: true`), then:

| Current | Becomes |
|---|---|
| L46-49 `Install project (incl. dev extras)` → `run: uv sync --locked` | **Unchanged.** Keep it: it is the `--locked` staleness assertion the comment describes, and it must run before `just` needs `.venv`. Do not replace it with `just setup` — `setup` uses `--all-extras --locked`, a different assertion. |
| L51-54 `Lint (ruff)` → `run: \|` two ruff commands | Delete the step. |
| L56-57 `Type-check (mypy)` → `run: uv run mypy .` | Delete the step. |
| L65-73 `Docs are in sync with the code` → `run: \|` generate + `git diff` | Delete the step. |
| L75-83 `Meraki model conformance` → `run: \|` apidrift | Delete the step. |
| L85-90 `Run tests` → `run: >- uv run pytest …` | Replace all five deleted steps with a single step: `- name: Gate` / `run: just check`. |

The `PYTHONPATH: src:tools` and `PYTHONPATH: src` step-level `env:` blocks go away — the recipes set
`PYTHONPATH=src:tools` inline, and `pyproject.toml`'s `[tool.pytest.ini_options] pythonpath` already
covers pytest.

`coverage.xml` is still produced (the `test` recipe keeps `--cov-report=xml`), so the two upload steps
(L92-105) and the `HAS_CODECOV_TOKEN` / `HAS_CODACY_TOKEN` job-level `env:` block (L24-26) are
**unchanged**.

**Job `docker-build-test`** — insert setup-just after the checkout step, then:

| Current | Becomes |
|---|---|
| L119-134 `Set up Docker Buildx` + `docker/build-push-action` | **Unchanged.** Never convert a `uses:` into `run: just`. The image is built by the action and tagged `meraki-dashboard-exporter:test`. |
| L136-165 `Test Docker image startup` (`run: \|`, ~30 lines) | `run: just image-verify meraki-dashboard-exporter:test` — keep the step-level `env: MERAKI_EXPORTER_MERAKI__API_KEY`, or drop it since the recipe passes the dummy key itself. |
| L167-175 `Install container-structure-test` | **Unchanged.** Runner tool provisioning, not build logic; it carries a `# renovate:` pin comment that must survive. |
| L177-181 `Container structure test` | `run: just image-structure meraki-dashboard-exporter:test` |
| L183-217 `Serve smoke test` (`run: \|`, functions + trap + retry loop) | `run: just smoke meraki-dashboard-exporter:test` — the step-level `env:` block becomes redundant (the recipe sets both vars). |

**Job `helm-lint-kubeconform`** — insert setup-just after the checkout step, then:

| Current | Becomes |
|---|---|
| L232-251 `Install Helm` + `Install kubeconform` | **Unchanged.** Tool provisioning with `# renovate:` pins. |
| L253-254 `Helm lint` | Collapse all three into one step: `- name: Chart gate` / `run: just helm-check` |
| L256-263 `Render chart templates` | ↑ (the recipe renders to `/tmp/rendered-manifests.yaml`, not `${RUNNER_TEMP}`) |
| L265-267 `kubeconform validate` | ↑ |

**Jobs `scheduled-fleet-tests` (L269-286) and `on-demand-fleet-tests` (L288-305)** — insert setup-just
after the `astral-sh/setup-uv` step in each, keep `uv sync --all-extras --locked` as-is, and replace
the final step's `run:` with `just test-fleet-scheduled` / `just test-fleet-on-demand` respectively.

**Job `ci-success` (L307-322)** — **do not touch.** Its `name: ci-success`, `if: always()`,
`needs: [test, docker-build-test, helm-lint-kubeconform]` and the two failure-detection steps are the
branch ruleset's single required check. No `just` in this job.

**Also unchanged in `ci.yml`:** the `on:` triggers including the Monday `schedule` cron, the top-level
`permissions:` block, every `step-security/harden-runner` step, every `persist-credentials: false`,
and every SHA pin.

### `.github/workflows/api-drift.yml`

Insert setup-just after the setup-uv step (L26-31).

| Current | Becomes |
|---|---|
| L36-39 `Fetch live Meraki OpenAPI spec` | **Unchanged.** It writes `/tmp/live.json`, which the next step consumes; the local `api-drift` recipe uses `--live-url` instead and is not a substitute. |
| L41-54 `Run apidrift (findings + reduced specs)` | **Unchanged.** It uses `--live /tmp/live.json --emit-reduced /tmp/reduced` and `set +e` + `$GITHUB_OUTPUT` exit-code capture — a CI-only invocation with no local equivalent. Converting it would mean adding recipe parameters for `--live` and `--emit-reduced` and losing the exit-code plumbing. Leave it. |
| L56-61, L63-88, L83-88 | **Unchanged.** oasdiff docker run + the two tool-error gates. |
| L90-101 `report-drift` / `resolve-drift` | **Unchanged.** `uses:` local composite actions. Never converted. |

`api-drift.yml` therefore needs **no** setup-just step at all. Skip it. Listed here so a later agent
does not "fix" the omission.

### Workflows that must not change at all

`codeql.yml`, `dependency-review.yml`, `scorecard.yml`, `zizmor.yml`, `actionlint.yml`,
`docker-security.yml`, `release-please.yml`, `release-please-lock.yml`, `publish.yml`, `auto-rc.yml`,
`arm-automerge.yml`, `ghcr-cleanup.yml`, `trigger-docs-sync.yml`. These are GitHub-native or reusable
`uses: rknightion/.github/...` calls, or they carry OpenBao broker-token minting
(`permission-set:` / `role:` / `id-token: write`) that must not be perturbed. `failure-harness.yml` is
the one exception below.

### `.github/workflows/failure-harness.yml`

Insert setup-just after the setup-uv step (L25-29).

| Current | Becomes |
|---|---|
| L30 `- run: uv sync --locked` | **Unchanged.** |
| L31-32 `Build local exporter image` | **Unchanged** — `docker build --pull=false --tag meraki-dashboard-exporter:failure-harness .`; the harness runner resolves that exact tag. |
| L33-41 `Run selected replay` (`run: \|` with an `if`/`else` on `$HARNESS_MODE`) | `run: just harness-run "${HARNESS_MODE}"` — keep the `env: HARNESS_MODE: ${{ inputs.mode }}` block. The recipe's `mode == "all"` branch reproduces the `--all-modes` path. |
| L42-47 `Upload redacted failure-harness artifacts` | **Unchanged.** `tests/unit/test_failure_harness_713.py:801` asserts on that exact action SHA. |

`permissions: {}` and the `workflow_dispatch`-only trigger must survive —
`tests/unit/test_failure_harness_713.py:797-800` asserts `push:` and `pull_request:` are absent.

## 6. Docs and agent-contract changes

| File:line | Current | Change to |
|---|---|---|
| `AGENTS.md:78` | `` - `make check` - Run all checks (lint, typecheck, test) `` | Delete this line and the three below it; replace the whole `make` block with the Task interface section below. |
| `AGENTS.md:79` | `` - `make docgen` - Generate all documentation `` | ↑ |
| `AGENTS.md:80` | `` - `make docker-compose-up` - Start with Docker `` | ↑ |
| `AGENTS.md:81` | `` - `make run-dev` - Run with auto-reload for development `` | ↑ |
| `AGENTS.md:212` | `` `make check` always, `make docgen` when its inputs changed `` | `` `just check` always, `just gen` when its inputs changed `` |
| `CLAUDE.md` | No `make` reference | Unchanged — it is a 15-line pointer that `@AGENTS.md`-imports. |
| `docs/CLAUDE.md:44-48` | The `make docgen` / `make docs-*` fenced block | `just gen`, `just docs-config`, `just docs-metrics`, `just docs-collectors`, `just docs-endpoints`, and add `just docs-env`, `just docs-helm`, `just docs-scaling` — those three generated artefacts were never listed. |
| `docs/CLAUDE.md` `<critical_notes>` + `<fatal_implications>` | Four `make docgen` mentions | `just gen` |
| `scripts/CLAUDE.md:6` | `` Run `make docgen` (or `./scripts/generate-docs.sh`) `` | `` Run `just gen` `` |
| `scripts/CLAUDE.md:31` | `` make docgen                # or: ./scripts/generate-docs.sh `` | `just gen` |
| `scripts/CLAUDE.md` `<file_map>` first bullet | Describes `generate-docs.sh` as the orchestrator | Rewrite: the orchestrator is now the `gen` recipe in the root `justfile`; `generate-docs.sh` no longer exists. Keep the note that `trigger-docs-sync.yml` watches `scripts/**`. |
| `scripts/CLAUDE.md` `<paved_path>` | `make docs-config` etc. | `just docs-config` etc.; add `just docs-env`, `just docs-helm`, `just docs-scaling`. |
| `scripts/generate_env_example.py:10` | `` Run via ``make docgen`` (wired into ``scripts/generate-docs.sh``). `` | `` Run via ``just gen``. `` (docstring — a source edit, so `just check` must pass after it) |
| `tools/apidrift/CLAUDE.md:11` | `` (see Makefile / CI) `` | `` (see the root `justfile` / CI) `` |
| `tools/apidrift/CLAUDE.md:17` | `` `make refresh-meraki-spec` `` | `` `just refresh-spec` `` |
| `tools/apidrift/CLAUDE.md:117` | `` ## Running locally (Makefile targets, see repo root `Makefile`) `` | `` ## Running locally (recipes, see the repo root `justfile`) `` |
| `tools/apidrift/CLAUDE.md:118,120,123,124` | `make api-drift` / `make api-conformance` / `make api-suggest` / `make refresh-meraki-spec` | `just api-drift` / `just api-conformance` / `just api-suggest` / `just refresh-spec` |
| `tools/apidrift/CLAUDE.md:141` | `` Run `make api-conformance` locally `` | `` Run `just api-conformance` locally `` |
| `tools/apidrift/CLAUDE.md:148` | `` regenerate via `make refresh-meraki-spec` `` | `` regenerate via `just refresh-spec` `` |
| `docs/extending-collectors.md:45` | `` Regenerate docs with `scripts/generate-docs.sh` (or the individual generators). `` | `` Regenerate docs with `just gen` (or an individual `just docs-*` recipe). `` |
| `docs/development/release-process.md:53` | `` `make check` is the local Python gate. It runs `ruff check`, `ruff format --check`, mypy, and the test suite. `` | `` `just check` is the local gate and is exactly what the CI `test` job runs: ruff format check, ruff lint, mypy, generated-doc drift, offline API conformance, and the marker-filtered test suite with the 80% coverage floor. `` |
| `docs/development/release-process.md:57` | `` CI deliberately covers additional checks that are not part of `make check`: `` | `` CI deliberately covers additional checks that are not part of `just check` (`just ci` adds the container and chart legs locally): `` — and delete "generated-documentation drift detection, offline API-model conformance" from the list below it, since `just check` now covers both. |
| `docs/development/release-process.md:70` | `` `make check` intentionally remains a fast source-tree gate `` | `` `just check` intentionally remains a fast source-tree gate `` |
| `docs/development/failure-harness.md:17-18` | `make failure-harness-validate` / `make failure-harness-run MODE=baseline` | `just harness-validate` / `just harness-run baseline` |
| `docs/development/failure-harness.md:135` | `` `make failure-harness-validate` before committing `` | `` `just harness-validate` before committing `` |
| `backlog/docs/doc-0002 - Wave-operating-model.md:147` | `` change its source and run `make docgen`. The eight generators are wired through `scripts/generate-docs.sh` `` | `` change its source and run `just gen`. The eight generators are wired through the `gen` recipe in the root `justfile` `` — **edit via `backlog doc edit`, never by hand.** |
| `backlog/docs/doc-0002 - Wave-operating-model.md:152` | `` `make check` did not include `ruff format --check` `` | Keep the historical claim but re-anchor it: `` The old `make check` did not include `ruff format --check`, so the local gate passed where CI failed; `just check` now mirrors the CI `test` job step for step. `` Same: via `backlog doc edit`. |
| `.dockerignore:90` | `Makefile` | `justfile` — see trap 2. |
| `docs/changelog.md:86` | Mentions "Makefile docker targets" | **Do not edit.** Generated by release-please; it is a historical changelog entry. |
| `evidence/findings-synthesis.md:18` | Mentions `Makefile` | **Do not edit.** Point-in-time evidence artefact. |
| `backlog/tasks/mde-0006 …:15` | References `scripts/cloud-environment-setup.sh` | **Do not edit.** The script is a KEEP; the reference stays valid. |
| `README.md:301,313` | `uv run python scripts/generate_endpoints_docs.py` / `…generate_metrics_docs.py` | Optional: `just docs-endpoints` / `just docs-metrics`. These are reader-facing "kept in sync via" notes, not instructions to a contributor; changing them is safe but not required. |

### The AGENTS.md Task interface section

Replace `AGENTS.md:78-81` (inside the `<bash_commands>` block, keeping the `uv run …` and
`backlog …` lines around it) with:

```markdown
## Task interface

This repo's task surface is a `justfile`. Discover it, don't guess it:

    just --list                        # human-readable
    just --dump --dump-format json     # machine-readable
    just --show <recipe>               # what a recipe actually runs

- `just check` is the full gate and is exactly what the CI `test` job enforces. It must pass before
  you commit. `just ci` adds the container and chart legs of `ci-success` and needs Docker, Helm and
  kubeconform.
- Prefer `just <recipe>` over the underlying tool. If you are typing `pytest`, you want `just test`.
- Run `just` with stdin from /dev/null. Recipes marked `[confirm]` are destructive — stop and ask
  before running one; never pass `--yes` or `JUST_YES=1`.
- If a task you need does not exist, add a recipe with a `#` doc comment and a `[group(...)]`
  rather than running a bare command.
```

Do **not** paste the recipe list into `AGENTS.md`. It rots on the next recipe added, and an agent
will then trust the stale copy over `just --list`.

## 7. backlog/config.yml

Current `definition_of_done` (lines 5-7) names `make` targets. Replace via
`backlog config set definition_of_done` (or the equivalent `backlog` CLI call — **never hand-edit
`backlog/config.yml`**) with:

```yaml
definition_of_done:
  - "just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)"
  - "just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it"
  - "Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed"
```

The third line is unchanged. The second now says `just gen` and widens the trigger list, because
`gen` also regenerates `.env.example`, `charts/…/values.yaml`, `charts/…/templates/configmap.yaml`
and `docs/scaling-guide.md` — artefacts the old `make docgen` wording never mentioned.

## 8. Order of work

Green at every step. Commit boundaries are marked.

1. **Write `justfile`** at the repo root, exactly as in §2. Do not delete anything yet.
2. **Prove it locally**, evidence not assertion:
   - `just --fmt --check` → exit 0
   - `just --list` → exit 0, every public recipe shows a doc comment, groups are exactly the six
   - `just --dump --dump-format json > /dev/null` → exit 0 (proves no unstable feature slipped in)
   - `just --groups` → `build check dev gen infra release`
   - `just --dry-run check` → the command list matches `ci.yml` L51-90 step for step
   - `just check < /dev/null` → exit 0 on a clean tree
   - `just gen && git diff --stat` → no diff (proves `gen` is idempotent)
   - `just check < /dev/null` a second time → still exit 0 (proves re-runnable)
   - If Docker is available: `just image && just image-verify && just smoke`
   - If Helm + kubeconform are available: `just helm-check`
   **Commit 1** — `chore: add justfile`. The Makefile still works; nothing else has changed.
3. **Switch CI.** Edit `ci.yml` and `failure-harness.yml` per §5, including the pinned setup-just
   steps. Push and watch `ci-success` go green on the real runner before proceeding. The Makefile is
   still present and still correct, so a revert is one file.
   **Commit 2** — `ci: call just recipes from the workflows`.
4. **Update the agent contracts and docs** per §6 (`AGENTS.md`, `docs/CLAUDE.md`,
   `scripts/CLAUDE.md`, `tools/apidrift/CLAUDE.md`, `docs/extending-collectors.md`,
   `docs/development/release-process.md`, `docs/development/failure-harness.md`,
   `scripts/generate_env_example.py:10`). Update `backlog/config.yml`'s `definition_of_done` and
   `backlog/docs/doc-0002` through the `backlog` CLI. Run `just check`.
   **Commit 3** — `docs: point the task surface at just`.
5. **Edit `scripts/cloud-environment-setup.sh`** — add the pinned `just` install and change the final
   `make check` line to `just check`. Run `bash -n scripts/cloud-environment-setup.sh` at minimum;
   ideally run it in a throwaway container.
   **Commit 4** — `chore: install just in the cloud setup script`.
6. **Deletions, last, in one commit.** By now nothing references either file.
   - `git rm Makefile`
   - `git rm scripts/generate-docs.sh`
   - Edit `.dockerignore:90` `Makefile` → `justfile`
   - Edit `tests/unit/test_failure_harness_713.py:805`:
     `assert "failure-harness-validate" in Path("Makefile").read_text(encoding="utf-8")`
     → `assert "harness-validate" in Path("justfile").read_text(encoding="utf-8")`
   - `git grep -n -E '\bmake [a-z]|generate-docs\.sh|Makefile' -- . ':(exclude)uv.lock' ':(exclude)archive/*' ':(exclude)docs/changelog.md' ':(exclude)evidence/*'`
     must return nothing.
   - `just check < /dev/null` → exit 0.
   **Commit 5** — `chore!: retire the Makefile and generate-docs.sh`.

## 9. Traps specific to this repo

1. **A unit test reads the Makefile.** `tests/unit/test_failure_harness_713.py:805`:
   `assert "failure-harness-validate" in Path("Makefile").read_text(encoding="utf-8")`. Deleting the
   Makefile makes `just test` raise `FileNotFoundError` — the test suite goes red the instant the file
   is gone. The edit in step 6 is not optional and must be in the same commit as the `git rm`. Two
   sibling assertions in the same function (`.github/workflows/failure-harness.yml` shape, the
   `upload-artifact` SHA, `docs.toml` containing "Failure Harness") stay as they are.
2. **`.dockerignore:90` lists `Makefile`.** Leaving it there and adding nothing means `justfile` is
   sent into the Docker build context on every build, changing the context hash and invalidating the
   layer cache on every justfile edit. Swap the line, do not just delete it.
3. **Go template braces collide with just interpolation.** `docker inspect -f '{{.Config.User}}'` and
   `imagetools inspect --format '{{println .Manifest.Digest}}'` must be written with the **opening**
   braces doubled and the closing braces left alone: `'{{{{.Config.User}}'`. Verified on 1.58 —
   `{{{{` renders as a literal `{{`, but `}}}}` renders as a literal `}}}}` (four characters), which
   silently corrupts the format string. The two affected recipes are `image-verify` and
   `image-base-digest`.
4. **`make test` was never what CI ran, and this repo has already been burned by exactly that.**
   `Makefile:87` was `uv run pytest -v`; `ci.yml:88-90` runs
   `pytest -m "not fleet_scheduled and not fleet_on_demand" --cov=… --cov-fail-under=80`. Separately,
   `backlog/docs/doc-0002:151` records that `make check` omitted `ruff format --check` and so passed
   locally where CI failed. The `test` recipe must carry the marker filter **and** the coverage floor,
   and `check` must depend on `fmt-check`. Do not "simplify" either.
5. **`gen-check` must diff the generated paths, not the whole tree.** CI runs `git diff --quiet` on a
   clean checkout, so whole-tree and generated-paths are equivalent there. Locally they are not: an
   agent with any unrelated edit in flight would get a false drift failure and would then stop running
   `just check`. The `generated` variable in §2 lists all eight write targets — `docs/config.md`,
   `docs/metrics/metrics.md`, `docs/collectors/reference.md`, `docs/reference/endpoints.md`,
   `docs/scaling-guide.md`, `.env.example`, `charts/meraki-dashboard-exporter/values.yaml`,
   `charts/meraki-dashboard-exporter/templates/configmap.yaml`. **If a generator is added or its
   output path moves, this list must be updated or the drift gate silently stops catching it.**
6. **Absorbing `generate-docs.sh` drops its `python3` fallback.** The script picks
   `uv run python` when `uv` is on PATH and plain `python3` otherwise. The `docs-*` recipes call
   `uv run python` unconditionally. This is deliberate: `just setup`, `ci.yml` and
   `cloud-environment-setup.sh` all install `uv`, and a silent fallback to a system `python3` without
   the locked deps produces wrong generated docs rather than a clean failure. If it bites, the fix is
   `{{ require('uv') }}`, not a re-added fallback.
7. **Multi-line shell needs `[script('bash')]`.** `image-verify` and `smoke` carry `if` blocks, a
   `trap`, shell functions and a retry loop. In a line-based recipe every line is its own
   `bash -euo pipefail -c`, so those constructs fail with "extra leading whitespace". Both are
   attributed `[script('bash')]` (verified stable in 1.58 — it does **not** require `--unstable` and
   does not break `just --list`). Note that `[script]` bypasses `set shell`, hence the explicit
   `set -euo pipefail` as the first body line of each.
8. **`just --fmt` sorts recipe attributes alphabetically.** `[confirm(...)]` sorts before
   `[group(...)]`, `[group(...)]` before `[macos]` before `[no-exit-message]` before `[private]` before
   `[script(...)]` before `[working-directory(...)]`. Writing them in any other order makes
   `just --fmt --check` — and therefore `just check` — fail with a diff. The file in §2 is already in
   canonical order.
9. **`helm` and `kubeconform` are not on a dev Mac.** `helm-check` uses `require('helm')` /
   `require('kubeconform')`, which halts with a clear "could not find executable" error at the point of
   use. Verified: a `require()` for a missing tool does **not** break `just --list` or `just --dump` —
   it only fires when that recipe runs. Same for `container-structure-test` in `image-structure`.
10. **`[confirm]` hangs on an agent's open-but-silent stdin.** Always invoke as
    `just <recipe> < /dev/null`, which makes `[confirm]` fail closed at exit 1. `image-push` and
    `clean-docker` are the two confirm-gated recipes.
11. **`refresh-spec` and `api-drift` reach the network.** `refresh-spec` overwrites the committed
    `spec/meraki-openapi.json.gz`; it is not `[confirm]`-gated because git recovers it, but it prints
    the reminder to hand-update `spec/README.md`, which nothing enforces.
12. **`trigger-docs-sync.yml` path filter.** It fires on `docs/**`, `docs.toml`, `scripts/**`. The
    generators stay under `scripts/`, so the filter remains correct after `generate-docs.sh` is
    deleted. A change confined to the root `justfile` will not trigger a docs sync — correct, since the
    justfile is not site input.
13. **`uv sync --locked` vs `just setup`.** `ci.yml:49` asserts the lockfile is not stale using
    `uv sync --locked` (no `--all-extras`); `setup` uses `uv sync --all-extras --locked`. They are
    different assertions. Do not collapse the CI step into `just setup`.
14. **`.pre-commit-config.yaml` runs ruff and mypy independently of `just`.** It is not wired to the
    justfile and must not be — a hook that shells out to `just` would need `just` on every committer's
    PATH. `install-hooks` wraps `uvx pre-commit install` and that is the whole relationship.

## 10. Out of scope

**Do not touch:**

- `ci-success` in `ci.yml` — its job name, `if: always()`, `needs:` list and both steps. It is the
  branch ruleset's single required check and Renovate automerge waits on it.
- Every `permissions:` block, `concurrency:` group, `persist-credentials: false`, SHA pin,
  `# renovate:` datasource comment, `workflow_call` input, and matrix definition in any workflow.
- Every `uses:` line. Never convert one into `run: just`.
- The reusable-workflow calls to `rknightion/.github/...` in `docker-security.yml`, `actionlint.yml`,
  `zizmor.yml`, `codeql.yml`, `dependency-review.yml`, `scorecard.yml`, `publish.yml`, `auto-rc.yml`,
  `arm-automerge.yml`, `ghcr-cleanup.yml`.
- Every OpenBao broker-token step: `release-please.yml` (`release-please-meraki-dashboard-exporter`),
  `release-please-lock.yml` (`lockfile-meraki-dashboard-exporter`), `trigger-docs-sync.yml`
  (`docs-sync-meraki-dashboard-exporter`). Do not provision `RELEASE_PLEASE_TOKEN` or `DOCS_SYNC_PAT`.
- `.github/actions/report-drift/action.yml` and `.github/actions/resolve-drift/action.yml` — local
  composite actions whose `run:` bodies are `gh` API plumbing, not build logic.
- `release-please-config.json`, `.release-please-manifest.json`, `renovate.json`, `codecov.yml`,
  `.codacy.yaml`, `.secrets.baseline`, `.safety-project.ini`, `.whitesource`, `.node-version`.
- `.pre-commit-config.yaml` — trap 14.
- `docs.toml` and everything under `charts/`, `grafana/`, `src/`, `spec/`, `evidence/`, `archive/`,
  `examples/`, except the generated chart regions that `just gen` already owns.
- `docs/changelog.md` (release-please-owned) and `evidence/findings-synthesis.md` (point-in-time
  artefact) — both mention `Makefile` historically and both stay as they are.

**KEEP scripts — wrap, never absorb:**
`scripts/cloud-environment-setup.sh` (edited only for the `just` install and the final `just check`
line), `scripts/generate_config_docs.py`, `scripts/generate_env_example.py`,
`scripts/generate_helm_config.py`, `scripts/generate_scaling_capacity_docs.py`,
`scripts/generate_metrics_docs.py`, `scripts/generate_collector_docs.py`,
`scripts/generate_endpoints_docs.py`, `scripts/validate_documented_env_vars.py`,
the whole `tools/apidrift/` package, `tests/harness/runner`, and `docker-entrypoint.py` (shipped
runtime, never invoked by a developer, no recipe at all).

**Not part of this task:** adding new checks, changing the coverage floor, touching the Dockerfile,
changing ruff/mypy configuration, or restructuring `scripts/`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A top-level justfile exists defining all seven mandatory recipes (default, setup, fmt, fmt-check, lint, test, check); 'just --groups' prints exactly build, check, dev, gen, infra, release; only default and setup are ungrouped.
- [ ] #2 'just --dry-run check' expands to ruff format --check, ruff check, mypy, the eight scripts/generate_*.py runs plus the generated-path drift diff, the offline apidrift --conformance-only run, and pytest -m "not fleet_scheduled and not fleet_on_demand" --cov=meraki_dashboard_exporter --cov-report=xml --cov-fail-under=80 - step for step what the ci.yml 'test' job enforces.
- [ ] #3 'just check < /dev/null' exits 0 twice in a row on a clean tree, and 'just gen && git diff --stat' produces no diff (gen is idempotent).
- [ ] #4 'just --fmt --check' exits 0 and 'just --dump --dump-format json' exits 0, proving canonical formatting and that no unstable just feature is in the file.
- [ ] #5 'just --list' shows a # doc comment and a [group(...)] for every public recipe; image-push and clean-docker carry [confirm]; helpers are [private] or _-prefixed.
- [ ] #6 Makefile and scripts/generate-docs.sh are deleted from the index, .dockerignore names justfile instead of Makefile, and tests/unit/test_failure_harness_713.py asserts 'harness-validate' in justfile rather than 'failure-harness-validate' in Makefile.
- [ ] #7 scripts/cloud-environment-setup.sh survives as a file, installs a pinned just, and ends by naming 'just check'; every KEEP program (the eight scripts/generate_*.py, validate_documented_env_vars.py, tools/apidrift, tests/harness/runner) is reachable through a named recipe.
- [ ] #8 .github/workflows/ci.yml jobs test, docker-build-test, helm-lint-kubeconform, scheduled-fleet-tests and on-demand-fleet-tests each carry a SHA-pinned extractions/setup-just step with just-version '1.58.0' and call just recipes; failure-harness.yml calls 'just harness-run'; the ci-success job name, if: always() and needs: [test, docker-build-test, helm-lint-kubeconform] are unchanged.
- [ ] #9 git grep -n -E '\\bmake [a-z]|generate-docs\\.sh' excluding uv.lock, archive/, docs/changelog.md and evidence/ returns nothing; AGENTS.md carries the Task interface section from the standard and does not paste the recipe list.
- [ ] #10 backlog/config.yml definition_of_done names 'just check' and 'just gen' (set through the backlog CLI, not hand-edited), and backlog doc-0002 no longer tells agents to run 'make docgen'.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 make check (uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest -v)
- [ ] #2 make docgen, when metrics, config, endpoints or collectors changed — CI fails the build on generated-docs drift
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Comments

<!-- COMMENTS:BEGIN -->
author: campaign-ordering
created: 2026-08-29 09:18
---
## Fleet ordering — WAVE 2. Starts after the Wave 0 pilot (`sf2loki` / SFL-0073) and the Wave 1 hubs land.

Within Wave 2 the order is free — these repos do not depend on each other. Batching by language is worthwhile so one lane reuses its Makefile-to-recipe mapping across similar repos.

Do not start before the pilot reports. The standard may be amended off the back of it, and picking this up early risks coding against a superseded seam.

**Provisioning `just` in CI.** Which mechanism depends on the runner, and the two must not be mixed:

| Runner | Mechanism |
| --- | --- |
| `arc-arm64` (m7kni self-hosted) | `just` is **baked into the runner image** by `m7kni/ci-tools` (`runner-image/Dockerfile`, `ARG JUST_VERSION`). Do **not** add `extractions/setup-just`, and delete the step if this repo already has one — it installs a second `just` earlier on `PATH` and turns the image pin into a lie. |
| GitHub-hosted (all `rknightion` repos) | `extractions/setup-just`, SHA-pinned, with an explicit `just-version:`. |

Both sides currently sit on **1.58.0** and are Renovate-managed. `ci-tools`' `Tool version drift` workflow fails if the Dockerfile `ARG` and the published image ever disagree, and lists any repo still carrying a second pin.

**While you are in the workflow files, check the hub pin.** On 2026-08-29 Renovate was unfrozen for `rknightion/.github` in `m7kni/renovate-config` — it had been `enabled: false` on the mistaken belief that callers tracked `@main`, which froze the fleet across 19 different hub SHAs (v1.3.1 June → v1.9.7 August) so that no hub fix ever propagated. Bumps now arrive as one grouped, CI-gated, automerged PR per repo. **A `uses:` whose comment is not a real `# vX.Y.Z` still cannot be bumped** (it resolves to a digest-only update, which the fleet rules disable) — if you find one, repair the comment as part of this task.
---
<!-- COMMENTS:END -->
