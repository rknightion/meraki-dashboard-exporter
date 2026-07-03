"""Drift guard for the generated Helm chart config knobs.

``scripts/generate_helm_config.py`` templates every non-secret ``MERAKI_EXPORTER_*``
tuning knob from the Pydantic ``Settings`` schema into the chart's ``values.yaml`` and
``templates/configmap.yaml`` (between BEGIN/END markers). These tests fail if the chart
has drifted from the schema (a new/removed/renamed setting without a ``make docgen``
run) or if a secret-typed field ever leaks into the plaintext ConfigMap.

Run ``make docgen`` (or ``python scripts/generate_helm_config.py``) to fix a drift
failure.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
CHART = REPO_ROOT / "charts" / "meraki-dashboard-exporter"
VALUES = CHART / "values.yaml"
CONFIGMAP = CHART / "templates" / "configmap.yaml"

# Env vars deliberately hand-wired outside the generated region (higher-level chart
# values, not ``config.*`` knobs). Keep in sync with configmap.yaml's specials.
SPECIALS = {
    "MERAKI_EXPORTER_MERAKI__ORG_ID",  # meraki.organizationId
    "MERAKI_EXPORTER_SERVER__PORT",  # service.port
}


def _load_generator() -> ModuleType:
    """Import ``scripts/generate_helm_config.py`` as a module."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "generate_helm_config", SCRIPTS / "generate_helm_config.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema_leaves() -> set[str]:
    """Every non-secret, non-excluded ``MERAKI_EXPORTER_*`` leaf in the Settings tree."""
    gen = _load_generator()
    gee = sys.modules["generate_env_example"]
    settings = gee.load_settings_model(REPO_ROOT)
    leaves: set[str] = set()

    def walk(model: type, prefix: str) -> None:
        for name, info in model.model_fields.items():
            env = f"{prefix}{name.upper()}"
            ann = info.annotation
            if gee.is_model(ann):
                walk(ann, f"{env}__")
                continue
            if env in gen.EXCLUDE or gen.is_secret(ann):
                continue
            leaves.add(env)

    walk(settings, gee.ENV_PREFIX)
    return leaves


def test_values_block_not_drifted() -> None:
    """The generated values.yaml knob block matches the current schema."""
    gen = _load_generator()
    block = gen.render_values_block(gen.collect_knobs())
    assert block in VALUES.read_text(), "values.yaml config knobs drifted — run `make docgen`"


def test_configmap_block_not_drifted() -> None:
    """The generated configmap.yaml env mapping matches the current schema."""
    gen = _load_generator()
    block = gen.render_configmap_block(gen.collect_knobs())
    assert block in CONFIGMAP.read_text(), (
        "templates/configmap.yaml config knobs drifted — run `make docgen`"
    )


def test_configmap_env_keys_match_schema() -> None:
    """Every non-secret settings leaf (plus the specials) is wired in configmap.yaml."""
    present = set(re.findall(r"(MERAKI_EXPORTER_[A-Z0-9_]+):", CONFIGMAP.read_text()))
    assert present == _schema_leaves() | SPECIALS


def test_no_secret_env_in_configmap() -> None:
    """Secret-typed settings must never be templated into the plaintext ConfigMap."""
    text = CONFIGMAP.read_text()
    for leaked in ("WEBHOOKS__SHARED_SECRET", "SERVER__API_TOKEN", "MERAKI__API_KEY"):
        assert leaked not in text, f"{leaked} must be injected via a Secret, not the ConfigMap"
