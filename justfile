set shell := ["bash", "-euo", "pipefail", "-c"]

# Docker BuildKit defaults for image recipes.
export DOCKER_BUILDKIT := "1"
export COMPOSE_DOCKER_CLI_BUILD := "1"

image_name := "meraki-dashboard-exporter"
registry := "ghcr.io/rknightion"
py_version := "3.14"
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

# type-check with mypy; this is the source-of-truth type gate
[group('check')]
[no-exit-message]
typecheck:
    uv run mypy .

# advisory Astral ty preview run; diagnostics are informational only
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

# full drift check against the live Meraki spec; fetches over the network
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

# the source-tree gate: exactly what the CI test job enforces
[group('check')]
check: fmt-check lint typecheck gen-check api-conformance test

# image needs a Docker daemon.
# image-verify needs a Docker daemon.
# image-structure needs a Docker daemon.
# smoke needs a Docker daemon.
# run the Docker-backed CI legs after the source-tree gate
[group('check')]
ci: check image image-verify image-structure smoke

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

# build the local exporter image required by the failure harness
[group('dev')]
harness-image:
    docker build --pull=false --tag meraki-dashboard-exporter:failure-harness .

# replay one failure mode, or pass mode=all
[group('dev')]
harness-run mode="baseline":
    uv run python -m tests.harness.runner run {{ if mode == "all" { "--all-modes" } else { "--mode " + quote(mode) } }}

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

# remove build, cache, and coverage artefacts
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

# build and push the multi-arch image to the registry
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
