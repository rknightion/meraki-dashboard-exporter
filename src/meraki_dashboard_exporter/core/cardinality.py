"""Cardinality monitoring and control for Prometheus metrics."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi.responses import HTMLResponse
from prometheus_client import CollectorRegistry, Counter, Gauge
from prometheus_client.core import REGISTRY, Metric
from starlette.requests import Request

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

        # Cache for expensive analysis results
        self._analysis_cache: dict[str, Any] | None = None
        self._cache_timestamp = 0.0
        self._cache_ttl = 60.0  # Cache for 60 seconds (matching fast tier)

        # Track if collectors have run at least once
        self._first_run_complete = False
        self._first_analysis_time: float | None = None

        # Store full metric data for detailed views
        self._full_metric_data: dict[str, Any] = {}
        self._label_value_distribution: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )

        # Initialize monitoring metrics
        self._initialize_metrics()

        logger.info(
            "Initialized CardinalityMonitor",
            warning_threshold=warning_threshold,
            critical_threshold=critical_threshold,
        )

    def _initialize_metrics(self) -> None:
        """Initialize cardinality monitoring metrics."""
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

        # Add analysis performance metrics
        self.analysis_duration = Gauge(
            "meraki_cardinality_analysis_duration_seconds",
            "Time taken to complete cardinality analysis",
            registry=self.registry,
        )

        self.analyzed_metrics_count = Gauge(
            "meraki_cardinality_analyzed_metrics_total",
            "Total number of metrics analyzed in last run",
            registry=self.registry,
        )

    def _is_cache_valid(self) -> bool:
        """Check if the analysis cache is still valid.

        Returns
        -------
        bool
            True if cache is valid, False otherwise.

        """
        return (
            self._analysis_cache is not None
            and time.time() - self._cache_timestamp < self._cache_ttl
        )

    def _get_cached_analysis(self) -> dict[str, Any] | None:
        """Get cached analysis if valid.

        Returns
        -------
        dict[str, Any] | None
            Cached analysis or None if invalid.

        """
        if self._is_cache_valid():
            logger.debug("Using cached cardinality analysis")
            return self._analysis_cache
        return None

    def _cache_analysis(self, analysis: dict[str, Any]) -> None:
        """Cache analysis results.

        Parameters
        ----------
        analysis : dict[str, Any]
            Analysis results to cache.

        """
        self._analysis_cache = analysis
        self._cache_timestamp = time.time()
        logger.debug("Cached cardinality analysis results")

    def mark_first_run_complete(self) -> None:
        """Mark that collectors have completed their first run."""
        self._first_run_complete = True
        logger.info("First collector run completed, cardinality analysis now available")

    def analyze_cardinality(self, use_cache: bool = True) -> dict[str, Any]:
        """Analyze current metric cardinality.

        Parameters
        ----------
        use_cache : bool
            Whether to use cached results if available.

        Returns
        -------
        dict[str, Any]
            Cardinality analysis results.

        """
        # Try to use cached results first
        if use_cache:
            cached = self._get_cached_analysis()
            if cached is not None:
                return cached

        # Don't analyze if collectors haven't run yet
        if not self._first_run_complete:
            return {
                "timestamp": time.time(),
                "metrics": {},
                "total_series": 0,
                "warnings": [],
                "critical": [],
                "error": "Waiting for initial collector run to complete",
                "first_run_pending": True,
            }

        start_time = time.time()
        if self._first_analysis_time is None:
            self._first_analysis_time = start_time

        results: dict[str, Any] = {
            "timestamp": start_time,
            "metrics": {},
            "total_series": 0,
            "warnings": [],
            "critical": [],
            "first_analysis_time": self._first_analysis_time,
        }

        metric_count = 0
        # Collect all metrics
        try:
            for metric_family in self.registry.collect():
                if (
                    metric_family.name.startswith("meraki_cardinality_")
                    or metric_family.name.startswith("meraki_total_series")
                    or metric_family.name.startswith("meraki_analyzed_metrics_")
                    or metric_family.name.startswith("meraki_analysis_duration")
                ):
                    # Skip our own metrics to avoid recursion
                    continue

                metric_info = self._analyze_metric(metric_family)
                if metric_info:
                    results["metrics"][metric_family.name] = metric_info
                    results["total_series"] += metric_info["cardinality"]
                    metric_count += 1

                    # Check thresholds
                    if metric_info["cardinality"] >= self.critical_threshold:
                        results["critical"].append({
                            "metric": metric_family.name,
                            "cardinality": metric_info["cardinality"],
                            "type": metric_info["type"],
                        })
                        self.cardinality_warnings.labels(
                            metric_name=metric_family.name,
                            severity="critical",
                        ).inc()
                    elif metric_info["cardinality"] >= self.warning_threshold:
                        results["warnings"].append({
                            "metric": metric_family.name,
                            "cardinality": metric_info["cardinality"],
                            "type": metric_info["type"],
                        })
                        self.cardinality_warnings.labels(
                            metric_name=metric_family.name,
                            severity="warning",
                        ).inc()

        except Exception as e:
            logger.exception("Error during cardinality analysis", error=str(e))
            results["error"] = f"Analysis failed: {e}"

        # Update monitoring metrics
        duration = time.time() - start_time
        self.total_series.set(results["total_series"])
        self.analysis_duration.set(duration)
        self.analyzed_metrics_count.set(metric_count)

        # Log summary
        logger.debug(
            "Cardinality analysis complete",
            duration=f"{duration:.3f}s",
            total_series=results["total_series"],
            metrics_count=metric_count,
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

        # Cache the results
        self._cache_analysis(results)
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
                    # Track label value distribution
                    self._label_value_distribution[metric_family.name][label_name].add(
                        str(label_value)
                    )

            if sample_count == 0:
                return None

            # Calculate per-label cardinality
            label_cardinalities = {label: len(values) for label, values in label_values.items()}

            # Store history
            current_time = time.time()
            history = self._cardinality_history[metric_family.name]
            history.append((current_time, sample_count))

            # Keep only last hour of history
            cutoff_time = current_time - 3600
            self._cardinality_history[metric_family.name] = [
                (t, c) for t, c in history if t > cutoff_time
            ]

            metric_data = {
                "cardinality": sample_count,
                "label_cardinalities": label_cardinalities,
                "label_values": {label: list(values) for label, values in label_values.items()},
                "type": metric_family.type,
                "documentation": metric_family.documentation or "No documentation available",
                "label_count": len(label_cardinalities),
            }

            # Store full data for detailed views
            self._full_metric_data[metric_family.name] = metric_data

            return metric_data

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

        # Calculate health status
        health_status = "healthy"
        if analysis["critical"]:
            health_status = "critical"
        elif analysis["warnings"]:
            health_status = "warning"

        report = {
            "summary": {
                "total_series": analysis["total_series"],
                "total_metrics": len(analysis["metrics"]),
                "warnings": len(analysis["warnings"]),
                "critical": len(analysis["critical"]),
                "health_status": health_status,
                "analysis_timestamp": datetime.fromtimestamp(analysis["timestamp"]).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "warning_threshold": self.warning_threshold,
                "critical_threshold": self.critical_threshold,
            },
            "top_metrics": [
                {
                    "name": name,
                    "cardinality": info["cardinality"],
                    "labels": list(info["label_cardinalities"].keys()),
                    "label_values": info.get("label_values", {}),
                    "label_count": info.get("label_count", len(info["label_cardinalities"])),
                    "type": info.get("type", "unknown"),
                    "documentation": info.get("documentation", "No documentation"),
                }
                for name, info in sorted_metrics[:30]  # Increased from 20 to 30
            ],
            "high_cardinality_labels": self._find_high_cardinality_labels(analysis),
            "growth_rate": self._calculate_growth_rates(),
            "warnings": analysis.get("warnings", []),
            "critical": analysis.get("critical", []),
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
            lambda: {"total_cardinality": 0, "metrics": [], "max_cardinality": 0}
        )

        for metric_name, info in analysis["metrics"].items():
            for label_name, cardinality in info["label_cardinalities"].items():
                label_stats[label_name]["total_cardinality"] += cardinality
                label_stats[label_name]["metrics"].append(metric_name)
                label_stats[label_name]["max_cardinality"] = max(
                    label_stats[label_name]["max_cardinality"], cardinality
                )

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
                "max_cardinality": stats["max_cardinality"],
                "metric_count": len(stats["metrics"]),
                "example_metrics": stats["metrics"][:5],
            }
            for label_name, stats in sorted_labels[:30]  # Increased from 15 to 30
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

            # Calculate growth over last 10 minutes for better sensitivity
            ten_min_ago = current_time - 600
            recent_samples = [(t, c) for t, c in history if t > ten_min_ago]

            if len(recent_samples) >= 2:
                start_cardinality = recent_samples[0][1]
                end_cardinality = recent_samples[-1][1]

                if start_cardinality > 0:
                    growth_rate = ((end_cardinality - start_cardinality) / start_cardinality) * 100
                    growth_rates[metric_name] = round(growth_rate, 2)

        return growth_rates

    def get_threshold_recommendations(self) -> dict[str, Any]:
        """Get recommendations for threshold adjustments.

        Returns
        -------
        dict[str, Any]
            Threshold recommendations.

        """
        analysis = self.analyze_cardinality()

        recommendations: dict[str, Any] = {
            "current_thresholds": {
                "warning": self.warning_threshold,
                "critical": self.critical_threshold,
            },
            "recommendations": [],
        }

        # Analyze current distribution
        cardinalities = [info["cardinality"] for info in analysis["metrics"].values()]
        if cardinalities:
            cardinalities.sort()
            p95 = cardinalities[int(len(cardinalities) * 0.95)] if cardinalities else 0
            p99 = cardinalities[int(len(cardinalities) * 0.99)] if cardinalities else 0

            # Recommend based on percentiles
            if self.warning_threshold < p95:
                recommendations["recommendations"].append({
                    "type": "warning",
                    "message": f"Consider raising warning threshold to {p95} (95th percentile)",
                    "suggested_value": p95,
                })

            if self.critical_threshold < p99:
                recommendations["recommendations"].append({
                    "type": "critical",
                    "message": f"Consider raising critical threshold to {p99} (99th percentile)",
                    "suggested_value": p99,
                })

        return recommendations

    def get_label_value_distribution(self, metric_name: str | None = None) -> dict[str, Any]:
        """Get distribution of label values.

        Parameters
        ----------
        metric_name : str | None
            Specific metric to analyze, or None for all metrics.

        Returns
        -------
        dict[str, Any]
            Label value distribution data.

        """
        if metric_name:
            return {
                metric_name: {
                    label: list(values)
                    for label, values in self._label_value_distribution.get(metric_name, {}).items()
                }
            }

        # Get top label values across all metrics
        label_value_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for labels in self._label_value_distribution.values():
            for label, values in labels.items():
                for value in values:
                    label_value_counts[label][value] += 1

        # Get top 10 values per label
        result = {}
        for label, value_counts in label_value_counts.items():
            sorted_values = sorted(value_counts.items(), key=lambda x: x[1], reverse=True)
            result[label] = {
                "total_unique_values": len(value_counts),
                "top_values": [
                    {"value": value, "occurrence_count": count}
                    for value, count in sorted_values[:10]
                ],
            }

        return result

    def get_all_metrics(self) -> list[dict[str, Any]]:
        """Get all metrics with full details.

        Returns
        -------
        list[dict[str, Any]]
            All metrics sorted by name.

        """
        return [
            {
                "name": name,
                "cardinality": data.get("cardinality", 0),
                "type": data.get("type", "unknown"),
                "labels": list(data.get("label_cardinalities", {}).keys()),
                "label_count": data.get("label_count", 0),
                "documentation": data.get("documentation", ""),
            }
            for name, data in sorted(self._full_metric_data.items())
        ]

    def get_all_labels(self) -> list[dict[str, Any]]:
        """Get all labels with usage statistics.

        Returns
        -------
        list[dict[str, Any]]
            All labels sorted by total cardinality.

        """
        label_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total_cardinality": 0,
                "metrics_used_in": set(),
                "max_cardinality": 0,
                "unique_values": set(),
            }
        )

        for metric_name, metric_data in self._full_metric_data.items():
            for label_name, cardinality in metric_data.get("label_cardinalities", {}).items():
                label_stats[label_name]["total_cardinality"] += cardinality
                label_stats[label_name]["metrics_used_in"].add(metric_name)
                label_stats[label_name]["max_cardinality"] = max(
                    label_stats[label_name]["max_cardinality"], cardinality
                )
                # Add unique values
                if label_name in self._label_value_distribution.get(metric_name, {}):
                    label_stats[label_name]["unique_values"].update(
                        self._label_value_distribution[metric_name][label_name]
                    )

        # Convert to list and sort
        result = []
        for label_name, stats in label_stats.items():
            result.append({
                "label": label_name,
                "total_cardinality": stats["total_cardinality"],
                "max_cardinality": stats["max_cardinality"],
                "metrics_used_in": len(stats["metrics_used_in"]),
                "unique_value_count": len(stats["unique_values"]),
                "metrics": sorted(stats["metrics_used_in"]),
            })

        return sorted(result, key=lambda x: x["total_cardinality"], reverse=True)

    def get_histogram_analysis(self) -> list[dict[str, Any]]:
        """Analyze histogram metrics for bucket cardinality.

        Returns
        -------
        list[dict[str, Any]]
            Histogram metrics with bucket analysis.

        """
        histograms = []

        for metric_name, data in self._full_metric_data.items():
            if data.get("type") == "histogram":
                # Count bucket metrics
                bucket_count = sum(1 for label in data.get("label_values", {}).get("le", []))

                histograms.append({
                    "name": metric_name,
                    "total_cardinality": data.get("cardinality", 0),
                    "bucket_count": bucket_count,
                    "base_labels": [
                        label
                        for label in data.get("label_cardinalities", {}).keys()
                        if label != "le"
                    ],
                    "documentation": data.get("documentation", ""),
                })

        return sorted(histograms, key=lambda x: x["total_cardinality"], reverse=True)

    def export_as_json(self) -> dict[str, Any]:
        """Export full cardinality data as JSON.

        Returns
        -------
        dict[str, Any]
            Complete cardinality data for export.

        """
        report = self.get_cardinality_report()
        return {
            "timestamp": report["summary"]["analysis_timestamp"],
            "summary": report["summary"],
            "all_metrics": self.get_all_metrics(),
            "all_labels": self.get_all_labels(),
            "label_value_distribution": self.get_label_value_distribution(),
            "histogram_analysis": self.get_histogram_analysis(),
            "growth_rates": report.get("growth_rate", {}),
        }

    def clear_cache(self) -> None:
        """Clear the analysis cache to force fresh analysis."""
        self._analysis_cache = None
        self._cache_timestamp = 0.0
        logger.debug("Cleared cardinality analysis cache")


def setup_cardinality_endpoint(app: FastAPI, monitor: CardinalityMonitor) -> None:
    """Set up cardinality monitoring endpoint.

    Parameters
    ----------
    app : FastAPI
        FastAPI application.
    monitor : CardinalityMonitor
        Cardinality monitor instance.

    """

    @app.get("/cardinality", response_class=HTMLResponse)
    async def get_cardinality_report(request: Request) -> HTMLResponse:
        """Get cardinality analysis report in HTML format."""
        # Get the report data
        report = monitor.get_cardinality_report()
        recommendations = monitor.get_threshold_recommendations()

        # Get app state for template access
        templates = app.state.templates

        # Prepare context for template
        context = {
            "request": request,
            "report": report,
            "recommendations": recommendations,
        }

        return templates.TemplateResponse("cardinality.html", context)  # type: ignore[no-any-return]

    @app.get("/cardinality/all-metrics", response_class=HTMLResponse)
    async def get_all_metrics(request: Request) -> HTMLResponse:
        """Get all metrics with cardinality details."""
        # Get all metrics data
        all_metrics = monitor.get_all_metrics()

        # Get app state for template access
        templates = app.state.templates

        # Prepare context for template
        context = {
            "request": request,
            "metrics": all_metrics,
            "total_metrics": len(all_metrics),
        }

        return templates.TemplateResponse("cardinality_all_metrics.html", context)  # type: ignore[no-any-return]

    @app.get("/cardinality/all-labels", response_class=HTMLResponse)
    async def get_all_labels(request: Request) -> HTMLResponse:
        """Get all labels with usage statistics."""
        # Get all labels data
        all_labels = monitor.get_all_labels()

        # Get app state for template access
        templates = app.state.templates

        # Prepare context for template
        context = {
            "request": request,
            "labels": all_labels,
            "total_labels": len(all_labels),
        }

        return templates.TemplateResponse("cardinality_all_labels.html", context)  # type: ignore[no-any-return]

    @app.get("/cardinality/export/json")
    async def export_cardinality_json() -> dict[str, Any]:
        """Export cardinality data as JSON."""
        return monitor.export_as_json()

    @app.get("/cardinality/label-values/{metric_name}")
    async def get_metric_label_values(metric_name: str) -> dict[str, Any]:
        """Get label value distribution for a specific metric."""
        return monitor.get_label_value_distribution(metric_name)

    logger.info(
        "Added cardinality monitoring endpoints: /cardinality, /cardinality/all-metrics, /cardinality/all-labels"
    )
