"""Regression coverage for nested task-admission metric discovery."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import generate_metrics_docs as metrics_docs  # noqa: E402


def test_task_admission_metrics_are_documented_with_bounded_phase_labels() -> None:
    """Nested constructors retain their types, phase label, and operational note."""
    repo_root = metrics_docs.find_repo_root(SCRIPTS_DIR)
    constants_dir = repo_root / "src" / "meraki_dashboard_exporter" / "core" / "constants"
    metrics_file = repo_root / "src" / "meraki_dashboard_exporter" / "core" / "metrics.py"
    metric_name_map = metrics_docs.parse_metric_constants(constants_dir)
    label_map = metrics_docs.parse_label_constants(metrics_file)

    metrics = metrics_docs.scan_for_metrics(
        repo_root / "src", repo_root, metric_name_map, label_map
    )
    task_metrics = {
        metric.name: metric for metric in metrics if metric.name.startswith("meraki_exporter_task")
    }

    assert {name: metric.metric_type for name, metric in task_metrics.items()} == {
        "meraki_exporter_tasks_pending": "gauge",
        "meraki_exporter_tasks_active": "gauge",
        "meraki_exporter_task_queue_wait_seconds": "histogram",
        "meraki_exporter_task_expired_before_start_total": "counter",
    }
    assert {tuple(metric.labels) for metric in task_metrics.values()} == {("phase",)}

    rendered = metrics_docs.generate_markdown(metrics)
    assert "`collector_admission`" in rendered
    assert "`task_group`" in rendered
    assert "not endpoint failure" in rendered


def test_scan_resolves_positional_and_starred_labels(tmp_path: Path) -> None:
    """Scan direct and helper constructors with positional and expanded labels."""
    (tmp_path / "metrics.py").write_text(
        """
plain = Gauge("plain", "help", ["org_id", "network_id"])
enum = Counter("enum", "help", [LabelName.ORG_ID.value, LabelName.NETWORK_ID.value])
class Example:
    def register(self):
        some_labels = [LabelName.ORG_ID, LabelName.NETWORK_ID]
        expanded = [*some_labels, LabelName.MODE]
        self.metric = self._create_gauge("starred", "help", labelnames=[*some_labels, LabelName.MODE])
        self.other = self._create_gauge("assigned", "help", labelnames=expanded)
""",
        encoding="utf-8",
    )
    label_map = {
        "LabelName.ORG_ID": "org_id",
        "LabelName.NETWORK_ID": "network_id",
        "LabelName.MODE": "mode",
    }
    metrics = metrics_docs.scan_for_metrics(tmp_path, tmp_path, {}, label_map)
    assert {metric.name: metric.labels for metric in metrics} == {
        "plain": ["org_id", "network_id"],
        "enum": ["org_id", "network_id"],
        "starred": ["org_id", "network_id", "mode"],
        "assigned": ["org_id", "network_id", "mode"],
    }


def test_real_metrics_retain_positional_and_starred_labels() -> None:
    """The real metric catalogue includes the full declared label sets."""
    repo_root = metrics_docs.find_repo_root(SCRIPTS_DIR)
    source = repo_root / "src" / "meraki_dashboard_exporter"
    metrics = metrics_docs.scan_for_metrics(
        repo_root / "src",
        repo_root,
        metrics_docs.parse_metric_constants(source / "core" / "constants"),
        metrics_docs.parse_label_constants(source / "core" / "metrics.py"),
    )
    labels = {metric.name: tuple(metric.labels) for metric in metrics}
    assert labels["meraki_webhook_events_received_total"] == ("org_id", "alert_type")
    assert labels["meraki_mx_nat_rules"] == ("org_id", "network_id", "nat_type")
