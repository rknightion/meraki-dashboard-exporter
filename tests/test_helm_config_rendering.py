"""Helm config values must reach settings as parseable environment strings."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from meraki_dashboard_exporter.core.config import Settings

CHART = Path(__file__).resolve().parents[1] / "charts" / "meraki-dashboard-exporter"


def test_values_file_config_renders_parseable_settings(tmp_path, monkeypatch):
    """Natural YAML values reach settings in their expected representations."""
    values = tmp_path / "values.yaml"
    values.write_text("""\
config:
  webhooksMaxPayloadSize: 2097152
  collectorsEnabledCollectors: [alerts, device]
  schedulerGroupIntervalOverrides: {nh_connection_stats: 900}
  apiValidateKwargs: true
  apiBatchDelay: 2.5
  logLevel: "DEBUG"
""")
    result = subprocess.run(
        [
            "helm",
            "template",
            "test-release",
            str(CHART),
            "--set",
            "meraki.apiKey=dummy",
            "-f",
            str(values),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    documents = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    data = next(doc["data"] for doc in documents if doc["kind"] == "ConfigMap")
    expected = {
        "MERAKI_EXPORTER_WEBHOOKS__MAX_PAYLOAD_SIZE": "2097152",
        "MERAKI_EXPORTER_COLLECTORS__ENABLED_COLLECTORS": '["alerts","device"]',
        "MERAKI_EXPORTER_SCHEDULER__GROUP_INTERVAL_OVERRIDES": '{"nh_connection_stats":900}',
        "MERAKI_EXPORTER_API__VALIDATE_KWARGS": "true",
        "MERAKI_EXPORTER_API__BATCH_DELAY": "2.5",
        "MERAKI_EXPORTER_LOGGING__LEVEL": "DEBUG",
    }
    assert {key: data[key] for key in expected} == expected
    for key in expected:
        monkeypatch.setenv(key, data[key])
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    settings = Settings()
    assert settings.webhooks.max_payload_size == 2097152
    assert settings.collectors.enabled_collectors == {"alerts", "device"}
    assert settings.scheduler.group_interval_overrides == {"nh_connection_stats": 900}
    assert settings.api.validate_kwargs is True
    assert settings.api.batch_delay == 2.5
    assert settings.logging.level == "DEBUG"


def test_set_and_string_values_keep_their_rendering(tmp_path):
    """Existing --set, string and null overrides retain their rendering."""
    values = tmp_path / "values.yaml"
    values.write_text("""config:
  collectorsEnabledCollectors: '["alerts", "device"]'
  apiBatchDelay: null
""")
    result = subprocess.run(
        [
            "helm",
            "template",
            "test-release",
            str(CHART),
            "--set",
            "meraki.apiKey=dummy",
            "--set",
            "config.webhooksMaxPayloadSize=2097152",
            "-f",
            str(values),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    documents = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    data = next(doc["data"] for doc in documents if doc["kind"] == "ConfigMap")
    assert data["MERAKI_EXPORTER_WEBHOOKS__MAX_PAYLOAD_SIZE"] == "2097152"
    assert data["MERAKI_EXPORTER_COLLECTORS__ENABLED_COLLECTORS"] == '["alerts", "device"]'
    assert data["MERAKI_EXPORTER_API__BATCH_DELAY"] is None
