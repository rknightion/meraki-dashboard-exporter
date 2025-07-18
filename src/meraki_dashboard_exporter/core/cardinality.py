"""Cardinality monitoring and control for Prometheus metrics."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from prometheus_client import CollectorRegistry, Counter, Gauge
from prometheus_client.core import REGISTRY, Metric

from .logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)


class CardinalityMonitor:
    """Monitors and reports on metric cardinality.

    Tracks the cardinality of metrics and labels to help identify
    high-cardinality metrics that might cause performance issues.

    Parameters
    ----------
    registry : CollectorRegistry | None
        Prometheus registry to monitor.
    warning_threshold : int
        Cardinality threshold for warnings (default: 1000).
    critical_threshold : int
        Cardinality threshold for critical alerts (default: 10000).

    """

    def __init__(
        self,
        registry: CollectorRegistry | None = None,
        warning_threshold: int = 1000,
        critical_threshold: int = 10000,
    ) -> None:
        """Initialize the cardinality monitor."""
        self.registry = registry or REGISTRY
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

        # Track cardinality over time
        self._cardinality_history: dict[str, list[tuple[float, int]]] = defaultdict(list)
        self._last_check_time = time.time()

        # Initialize monitoring metrics
        self._initialize_metrics()

        logger.info(
            "Initialized CardinalityMonitor",
            warning_threshold=warning_threshold,
            critical_threshold=critical_threshold,
        )

    def _initialize_metrics(self) -> None:
        """Initialize cardinality monitoring metrics."""
        self.metric_cardinality = Gauge(
            "meraki_metric_cardinality_total",
            "Total cardinality (unique label combinations) per metric",
            labelnames=["metric_name"],
            registry=self.registry,
        )

        self.label_cardinality = Gauge(
            "meraki_label_cardinality_total",
            "Cardinality per label per metric",
            labelnames=["metric_name", "label_name"],
            registry=self.registry,
        )

        self.cardinality_warnings = Counter(
            "meraki_cardinality_warnings_total",
            "Number of cardinality warnings triggered",
            labelnames=["metric_name", "severity"],
            registry=self.registry,
        )

        self.total_series = Gauge(
            "meraki_total_series",
            "Total number of time series across all metrics",
            registry=self.registry,
        )

    def analyze_cardinality(self) -> dict[str, Any]:
        """Analyze current metric cardinality.

        Returns
        -------
        dict[str, Any]
            Cardinality analysis results.

        """
        start_time = time.time()
        results: dict[str, Any] = {
            "timestamp": start_time,
            "metrics": {},
            "total_series": 0,
            "warnings": [],
            "critical": [],
        }

        # Collect all metrics
        for metric_family in self.registry.collect():
            if metric_family.name.startswith("meraki_metric_cardinality"):
                # Skip our own metrics
                continue

            metric_info = self._analyze_metric(metric_family)
            if metric_info:
                results["metrics"][metric_family.name] = metric_info
                results["total_series"] += metric_info["cardinality"]

                # Check thresholds
                if metric_info["cardinality"] >= self.critical_threshold:
                    results["critical"].append({
                        "metric": metric_family.name,
                        "cardinality": metric_info["cardinality"],
                    })
                    self.cardinality_warnings.labels(
                        metric_name=metric_family.name,
                        severity="critical",
                    ).inc()
                elif metric_info["cardinality"] >= self.warning_threshold:
                    results["warnings"].append({
                        "metric": metric_family.name,
                        "cardinality": metric_info["cardinality"],
                    })
                    self.cardinality_warnings.labels(
                        metric_name=metric_family.name,
                        severity="warning",
                    ).inc()

        # Update monitoring metrics
        self.total_series.set(results["total_series"])

        # Log summary
        duration = time.time() - start_time
        logger.debug(
            "Cardinality analysis complete",
            duration=f"{duration:.3f}s",
            total_series=results["total_series"],
            metrics_count=len(results["metrics"]),
            warnings=len(results["warnings"]),
            critical=len(results["critical"]),
        )

        if results["critical"]:
            logger.error(
                "Critical cardinality threshold exceeded",
                critical_metrics=results["critical"],
            )
        elif results["warnings"]:
            logger.warning(
                "High cardinality metrics detected",
                warning_metrics=results["warnings"],
            )

        return results

    def _analyze_metric(self, metric_family: Metric) -> dict[str, Any] | None:
        """Analyze a single metric's cardinality.

        Parameters
        ----------
        metric_family : Metric
            The metric family to analyze.

        Returns
        -------
        dict[str, Any] | None
            Metric analysis or None if no samples.

        """
        label_values: dict[str, set[str]] = defaultdict(set)
        sample_count = 0

        try:
            for sample in metric_family.samples:
                sample_count += 1

                # Track unique label values
                for label_name, label_value in sample.labels.items():
                    label_values[label_name].add(str(label_value))

            if sample_count == 0:
                return None

            # Calculate per-label cardinality
            label_cardinalities = {label: len(values) for label, values in label_values.items()}

            # Update metrics
            self.metric_cardinality.labels(metric_name=metric_family.name).set(sample_count)

            for label_name, cardinality in label_cardinalities.items():
                self.label_cardinality.labels(
                    metric_name=metric_family.name,
                    label_name=label_name,
                ).set(cardinality)

            # Store history
            current_time = time.time()
            history = self._cardinality_history[metric_family.name]
            history.append((current_time, sample_count))

            # Keep only last hour of history
            cutoff_time = current_time - 3600
            self._cardinality_history[metric_family.name] = [
                (t, c) for t, c in history if t > cutoff_time
            ]

            return {
                "cardinality": sample_count,
                "label_cardinalities": label_cardinalities,
                "type": metric_family.type,
                "documentation": metric_family.documentation,
            }

        except Exception as e:
            logger.exception(
                "Error analyzing metric",
                metric_name=metric_family.name,
                error=str(e),
            )
            return None

    def get_cardinality_report(self) -> dict[str, Any]:
        """Generate a detailed cardinality report.

        Returns
        -------
        dict[str, Any]
            Detailed cardinality report.

        """
        analysis = self.analyze_cardinality()

        # Add top metrics by cardinality
        sorted_metrics = sorted(
            analysis["metrics"].items(),
            key=lambda x: x[1]["cardinality"],
            reverse=True,
        )

        report = {
            "summary": {
                "total_series": analysis["total_series"],
                "total_metrics": len(analysis["metrics"]),
                "warnings": len(analysis["warnings"]),
                "critical": len(analysis["critical"]),
            },
            "top_metrics": [
                {
                    "name": name,
                    "cardinality": info["cardinality"],
                    "labels": list(info["label_cardinalities"].keys()),
                }
                for name, info in sorted_metrics[:20]
            ],
            "high_cardinality_labels": self._find_high_cardinality_labels(analysis),
            "growth_rate": self._calculate_growth_rates(),
        }

        return report

    def _find_high_cardinality_labels(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Find labels with high cardinality across metrics.

        Parameters
        ----------
        analysis : dict[str, Any]
            Cardinality analysis results.

        Returns
        -------
        list[dict[str, Any]]
            High cardinality labels.

        """
        label_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total_cardinality": 0, "metrics": []}
        )

        for metric_name, info in analysis["metrics"].items():
            for label_name, cardinality in info["label_cardinalities"].items():
                label_stats[label_name]["total_cardinality"] += cardinality
                label_stats[label_name]["metrics"].append(metric_name)

        # Sort by total cardinality
        sorted_labels = sorted(
            label_stats.items(),
            key=lambda x: x[1]["total_cardinality"],
            reverse=True,
        )

        return [
            {
                "label": label_name,
                "total_cardinality": stats["total_cardinality"],
                "metric_count": len(stats["metrics"]),
                "example_metrics": stats["metrics"][:5],
            }
            for label_name, stats in sorted_labels[:10]
        ]

    def _calculate_growth_rates(self) -> dict[str, float]:
        """Calculate cardinality growth rates.

        Returns
        -------
        dict[str, float]
            Growth rates per metric.

        """
        growth_rates = {}
        current_time = time.time()

        for metric_name, history in self._cardinality_history.items():
            if len(history) < 2:
                continue

            # Calculate growth over last 5 minutes
            five_min_ago = current_time - 300
            recent_samples = [(t, c) for t, c in history if t > five_min_ago]

            if len(recent_samples) >= 2:
                start_cardinality = recent_samples[0][1]
                end_cardinality = recent_samples[-1][1]

                if start_cardinality > 0:
                    growth_rate = ((end_cardinality - start_cardinality) / start_cardinality) * 100
                    growth_rates[metric_name] = growth_rate

        return growth_rates


def setup_cardinality_endpoint(app: FastAPI, monitor: CardinalityMonitor) -> None:
    """Set up cardinality monitoring endpoint.

    Parameters
    ----------
    app : FastAPI
        FastAPI application.
    monitor : CardinalityMonitor
        Cardinality monitor instance.

    """

    @app.get("/debug/cardinality")
    async def get_cardinality_report() -> dict[str, Any]:
        """Get cardinality analysis report."""
        return monitor.get_cardinality_report()

    logger.info("Added cardinality monitoring endpoint: /debug/cardinality")
