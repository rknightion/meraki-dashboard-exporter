"""Metric assertion helpers for testing."""

from __future__ import annotations

from typing import Any

from prometheus_client import CollectorRegistry


class MetricAssertions:
    """Helper class for asserting metric values in tests.

    Examples
    --------
    metrics = MetricAssertions(registry)
    metrics.assert_gauge_value("meraki_device_up", 1, serial="Q2KD-XXXX")
    metrics.assert_counter_incremented("meraki_api_calls_total", endpoint="getDevices")
    metrics.assert_metric_not_set("meraki_device_cpu_percent")

    """

    def __init__(self, registry: CollectorRegistry) -> None:
        """Initialize with a collector registry.

        Parameters
        ----------
        registry : CollectorRegistry
            The registry containing metrics

        """
        self.registry = registry
        self._metrics_cache: dict[str, Any] = {}

    def get_metric(self, metric_name: str) -> Any:
        """Get a metric by name from the registry.

        Parameters
        ----------
        metric_name : str
            The metric name

        Returns
        -------
        Any
            The metric object

        Raises
        ------
        AssertionError
            If metric not found

        """
        if metric_name in self._metrics_cache:
            return self._metrics_cache[metric_name]

        # Search through all collectors in registry
        for collector in self.registry._collector_to_names:
            metrics = collector.collect()
            for metric in metrics:
                if metric.name == metric_name:
                    self._metrics_cache[metric_name] = metric
                    return metric

        raise AssertionError(f"Metric '{metric_name}' not found in registry")

    def assert_gauge_value(self, metric_name: str, expected_value: float, **labels: str) -> None:
        """Assert a gauge has the expected value.

        Parameters
        ----------
        metric_name : str
            The metric name
        expected_value : float
            Expected value
        **labels : str
            Label key-value pairs

        Raises
        ------
        AssertionError
            If assertion fails

        """
        metric = self.get_metric(metric_name)

        # Find the sample with matching labels
        for sample in metric.samples:
            if sample.name == metric_name and self._labels_match(sample.labels, labels):
                if sample.value != expected_value:
                    raise AssertionError(
                        f"Metric '{metric_name}' with labels {labels} has value "
                        f"{sample.value}, expected {expected_value}"
                    )
                return

        # If we get here, no matching sample was found
        raise AssertionError(
            f"Metric '{metric_name}' with labels {labels} not found. "
            f"Available labels: {self._get_available_labels(metric, metric_name)}"
        )

    def assert_counter_value(self, metric_name: str, expected_value: float, **labels: str) -> None:
        """Assert a counter has the expected value.

        Parameters
        ----------
        metric_name : str
            The metric name (without _total suffix)
        expected_value : float
            Expected value
        **labels : str
            Label key-value pairs

        Raises
        ------
        AssertionError
            If assertion fails

        """
        # Get the metric
        metric = self.get_metric(metric_name)

        # Counter samples have _total suffix
        sample_name = f"{metric_name}_total"

        # Find the sample with matching labels
        for sample in metric.samples:
            if sample.name == sample_name and self._labels_match(sample.labels, labels):
                if sample.value != expected_value:
                    raise AssertionError(
                        f"Counter '{metric_name}' with labels {labels} has value "
                        f"{sample.value}, expected {expected_value}"
                    )
                return

        # If we get here, no matching sample was found
        raise AssertionError(
            f"Counter '{metric_name}' with labels {labels} not found. "
            f"Available labels: {self._get_available_labels(metric, sample_name)}"
        )

    def assert_counter_incremented(
        self, metric_name: str, min_increment: int = 1, **labels: str
    ) -> None:
        """Assert a counter was incremented.

        Parameters
        ----------
        metric_name : str
            The metric name
        min_increment : int
            Minimum increment expected
        **labels : str
            Label key-value pairs

        Raises
        ------
        AssertionError
            If assertion fails

        """
        metric = self.get_metric(metric_name)

        # Counter samples have _total suffix
        sample_name = f"{metric_name}_total"

        for sample in metric.samples:
            if sample.name == sample_name and self._labels_match(sample.labels, labels):
                if sample.value < min_increment:
                    raise AssertionError(
                        f"Counter '{metric_name}' with labels {labels} has value "
                        f"{sample.value}, expected at least {min_increment}"
                    )
                return

        raise AssertionError(f"Counter '{metric_name}' with labels {labels} not found")

    def assert_histogram_count(self, metric_name: str, expected_count: int, **labels: str) -> None:
        """Assert a histogram has the expected count.

        Parameters
        ----------
        metric_name : str
            The metric name
        expected_count : int
            Expected observation count
        **labels : str
            Label key-value pairs

        Raises
        ------
        AssertionError
            If assertion fails

        """
        metric = self.get_metric(metric_name)
        count_name = f"{metric_name}_count"

        # Find the count sample with matching labels
        for sample in metric.samples:
            if sample.name == count_name and self._labels_match(sample.labels, labels):
                if sample.value != expected_count:
                    raise AssertionError(
                        f"Histogram '{metric_name}' count with labels {labels} has value "
                        f"{sample.value}, expected {expected_count}"
                    )
                return

        # If we get here, no matching sample was found
        raise AssertionError(
            f"Histogram '{metric_name}' count with labels {labels} not found. "
            f"Available labels: {self._get_available_labels(metric, count_name)}"
        )

    def assert_histogram_sum_range(
        self, metric_name: str, min_sum: float, max_sum: float, **labels: str
    ) -> None:
        """Assert a histogram sum is within range.

        Parameters
        ----------
        metric_name : str
            The metric name
        min_sum : float
            Minimum expected sum
        max_sum : float
            Maximum expected sum
        **labels : str
            Label key-value pairs

        Raises
        ------
        AssertionError
            If assertion fails

        """
        sum_name = f"{metric_name}_sum"
        metric = self.get_metric(sum_name)

        for sample in metric.samples:
            if sample.name == sum_name and self._labels_match(sample.labels, labels):
                if not (min_sum <= sample.value <= max_sum):
                    raise AssertionError(
                        f"Histogram '{metric_name}' sum with labels {labels} is "
                        f"{sample.value}, expected between {min_sum} and {max_sum}"
                    )
                return

        raise AssertionError(f"Histogram '{metric_name}' with labels {labels} not found")

    def assert_info_value(
        self, metric_name: str, expected_info: dict[str, str], **labels: str
    ) -> None:
        """Assert an info metric has the expected value.

        Parameters
        ----------
        metric_name : str
            The metric name
        expected_info : dict[str, str]
            Expected info labels
        **labels : str
            Additional label filters

        Raises
        ------
        AssertionError
            If assertion fails

        """
        info_name = f"{metric_name}_info"
        metric = self.get_metric(info_name)

        for sample in metric.samples:
            if sample.name == info_name and self._labels_match(sample.labels, labels):
                # Check if all expected info labels are present
                for key, value in expected_info.items():
                    if sample.labels.get(key) != value:
                        raise AssertionError(
                            f"Info metric '{metric_name}' expected {key}='{value}', "
                            f"got {key}='{sample.labels.get(key)}'"
                        )
                return

        raise AssertionError(f"Info metric '{metric_name}' with labels {labels} not found")

    def assert_metric_exists(self, metric_name: str) -> None:
        """Assert a metric exists in the registry.

        Parameters
        ----------
        metric_name : str
            The metric name

        Raises
        ------
        AssertionError
            If metric doesn't exist

        """
        self.get_metric(metric_name)  # Will raise if not found

    def assert_metric_not_set(self, metric_name: str, **labels: str) -> None:
        """Assert a metric was not set (has no samples with given labels).

        Parameters
        ----------
        metric_name : str
            The metric name
        **labels : str
            Label key-value pairs

        Raises
        ------
        AssertionError
            If metric has samples with given labels

        """
        try:
            metric = self.get_metric(metric_name)
        except AssertionError:
            # Metric doesn't exist at all, that's fine
            return

        # Check if any samples match the labels
        for sample in metric.samples:
            # Skip _created, _bucket, etc. samples
            if not sample.name.startswith(metric_name):
                continue

            if self._labels_match(sample.labels, labels):
                raise AssertionError(
                    f"Metric '{metric_name}' with labels {labels} was set to {sample.value}, "
                    f"expected it not to be set"
                )

    def get_metric_value(self, metric_name: str, **labels: str) -> float | None:
        """Get the value of a metric with given labels.

        Parameters
        ----------
        metric_name : str
            The metric name (can include suffixes like _count, _sum for histograms)
        **labels : str
            Label key-value pairs

        Returns
        -------
        float | None
            The metric value or None if not found

        """
        # Handle histogram suffixes - if looking for something like metric_count,
        # we need to find the base metric first
        base_metric_name = metric_name
        if metric_name.endswith(("_count", "_sum", "_bucket")):
            for suffix in ["_count", "_sum", "_bucket"]:
                if metric_name.endswith(suffix):
                    base_metric_name = metric_name[: -len(suffix)]
                    break

        try:
            metric = self.get_metric(base_metric_name)
        except AssertionError:
            return None

        for sample in metric.samples:
            if sample.name == metric_name and self._labels_match(sample.labels, labels):
                return float(sample.value)

        return None

    def assert_histogram_observed(self, metric_name: str, **labels: str) -> None:
        """Assert a histogram has been observed (count > 0).

        Parameters
        ----------
        metric_name : str
            The metric name
        **labels : str
            Label key-value pairs

        Raises
        ------
        AssertionError
            If histogram count is 0

        """
        count = self.get_histogram_count(metric_name, **labels)
        if count == 0:
            raise AssertionError(
                f"Histogram '{metric_name}' with labels {labels} has not been observed"
            )

    def get_gauge_value(self, metric_name: str, **labels: str) -> float:
        """Get the value of a gauge metric.

        Parameters
        ----------
        metric_name : str
            The metric name
        **labels : str
            Label key-value pairs

        Returns
        -------
        float
            The gauge value

        Raises
        ------
        AssertionError
            If metric not found

        """
        value = self.get_metric_value(metric_name, **labels)
        if value is None:
            raise AssertionError(f"Gauge '{metric_name}' with labels {labels} not found")
        return value

    def get_counter_value(self, metric_name: str, **labels: str) -> float:
        """Get the value of a counter metric.

        Parameters
        ----------
        metric_name : str
            The metric name
        **labels : str
            Label key-value pairs

        Returns
        -------
        float
            The counter value

        Raises
        ------
        AssertionError
            If metric not found

        """
        value = self.get_metric_value(metric_name, **labels)
        if value is None:
            raise AssertionError(f"Counter '{metric_name}' with labels {labels} not found")
        return value

    def get_histogram_count(self, metric_name: str, **labels: str) -> int:
        """Get the count value of a histogram metric.

        Parameters
        ----------
        metric_name : str
            The metric name
        **labels : str
            Label key-value pairs

        Returns
        -------
        int
            The histogram count

        Raises
        ------
        AssertionError
            If metric not found

        """
        count_name = f"{metric_name}_count"
        value = self.get_metric_value(count_name, **labels)
        if value is None:
            raise AssertionError(f"Histogram '{metric_name}' with labels {labels} not found")
        return int(value)

    def get_all_label_sets(self, metric_name: str) -> list[dict[str, str]]:
        """Get all label combinations for a metric.

        Parameters
        ----------
        metric_name : str
            The metric name

        Returns
        -------
        list[dict[str, str]]
            List of label dictionaries

        """
        metric = self.get_metric(metric_name)
        label_sets = []

        for sample in metric.samples:
            if sample.name == metric_name:
                label_sets.append(dict(sample.labels))

        return label_sets

    def print_metric_samples(self, metric_name: str) -> None:
        """Print all samples for a metric (useful for debugging).

        Parameters
        ----------
        metric_name : str
            The metric name

        """
        metric = self.get_metric(metric_name)
        print(f"\nSamples for {metric_name}:")
        for sample in metric.samples:
            if sample.name.startswith(metric_name):
                print(f"  {sample.name}{sample.labels} = {sample.value}")

    def _labels_match(self, sample_labels: dict[str, str], expected_labels: dict[str, str]) -> bool:
        """Check if sample labels match expected labels.

        Parameters
        ----------
        sample_labels : dict[str, str]
            Labels from the sample
        expected_labels : dict[str, str]
            Expected label values

        Returns
        -------
        bool
            True if all expected labels match

        """
        for key, value in expected_labels.items():
            # Convert enum values to strings for comparison
            expected_value = value.value if hasattr(value, "value") else str(value)

            # Handle case where sample labels have enum keys
            sample_value = None
            for sample_key, sample_val in sample_labels.items():
                # If sample_key is an enum, get its value
                if hasattr(sample_key, "value") and sample_key.value == key:
                    sample_value = sample_val
                    break
                elif sample_key == key:
                    sample_value = sample_val
                    break

            if sample_value != expected_value:
                return False
        return True

    def _get_available_labels(self, metric: Any, metric_name: str) -> list[dict[str, str]]:
        """Get all available label combinations for a metric.

        Parameters
        ----------
        metric : Any
            The metric object
        metric_name : str
            The metric name

        Returns
        -------
        list[dict[str, str]]
            Available label combinations

        """
        labels_list = []
        for sample in metric.samples:
            if sample.name == metric_name:
                # Convert enum keys to strings for display
                label_dict = {}
                for key, value in sample.labels.items():
                    # If key is an enum, use its value
                    key_str = key.value if hasattr(key, "value") else str(key)
                    label_dict[key_str] = value
                labels_list.append(label_dict)
        return labels_list


class MetricSnapshot:
    """Capture metric state for comparison.

    Examples
    --------
    # Capture initial state
    before = MetricSnapshot(registry)

    # Do some work...

    # Capture final state
    after = MetricSnapshot(registry)

    # Check what changed
    diff = after.diff(before)
    assert diff.counter_delta("api_calls_total", endpoint="getDevices") == 1

    """

    def __init__(self, registry: CollectorRegistry) -> None:
        """Capture current metric state.

        Parameters
        ----------
        registry : CollectorRegistry
            The registry to snapshot

        """
        self.registry = registry
        self.state: dict[str, dict[tuple[str, ...], float]] = {}
        self._capture()

    def _capture(self) -> None:
        """Capture current metric values."""
        for collector in self.registry._collector_to_names:
            metrics = collector.collect()
            for metric in metrics:
                if metric.name not in self.state:
                    self.state[metric.name] = {}

                for sample in metric.samples:
                    # Create a flat tuple key for consistent comparison
                    # First element is sample name, rest are sorted label pairs
                    label_items = sorted(sample.labels.items())
                    key_parts = [sample.name]
                    for k, v in label_items:
                        key_parts.extend([k, v])
                    key_tuple = tuple(key_parts)
                    self.state[metric.name][key_tuple] = sample.value

    def diff(self, other: MetricSnapshot) -> MetricDiff:
        """Compare with another snapshot.

        Parameters
        ----------
        other : MetricSnapshot
            Earlier snapshot to compare against

        Returns
        -------
        MetricDiff
            Difference between snapshots

        """
        return MetricDiff(other, self)


class MetricDiff:
    """Difference between two metric snapshots."""

    def __init__(self, before: MetricSnapshot, after: MetricSnapshot) -> None:
        """Initialize with before and after snapshots.

        Parameters
        ----------
        before : MetricSnapshot
            Earlier snapshot
        after : MetricSnapshot
            Later snapshot

        """
        self.before = before
        self.after = after

    def counter_delta(self, metric_name: str, **labels: str) -> float:
        """Get counter increment between snapshots.

        Parameters
        ----------
        metric_name : str
            Counter name
        **labels : str
            Label filters

        Returns
        -------
        float
            The delta value

        """
        full_name = metric_name if metric_name.endswith("_total") else f"{metric_name}_total"
        return self._get_delta(full_name, **labels)

    def gauge_delta(self, metric_name: str, **labels: str) -> float:
        """Get gauge change between snapshots.

        Parameters
        ----------
        metric_name : str
            Gauge name
        **labels : str
            Label filters

        Returns
        -------
        float
            The delta value

        """
        return self._get_delta(metric_name, **labels)

    def _get_delta(self, metric_name: str, **labels: str) -> float:
        """Get value change for a metric."""
        # Find matching samples in both snapshots
        before_value = self._find_value(self.before.state, metric_name, labels)
        after_value = self._find_value(self.after.state, metric_name, labels)

        if before_value is None:
            before_value = 0
        if after_value is None:
            return 0

        return after_value - before_value

    def _find_value(
        self,
        state: dict[str, dict[tuple[str, ...], float]],
        metric_name: str,
        labels: dict[str, str],
    ) -> float | None:
        """Find metric value in state."""
        if metric_name not in state:
            return None

        metric_state = state[metric_name]

        for key_tuple, value in metric_state.items():
            # First element is sample name
            if len(key_tuple) == 0 or key_tuple[0] != metric_name:
                continue

            # Reconstruct labels from the flat tuple
            # Skip first element (sample name) and process pairs
            sample_labels = {}
            for i in range(1, len(key_tuple), 2):
                if i + 1 < len(key_tuple):
                    sample_labels[key_tuple[i]] = key_tuple[i + 1]

            if all(sample_labels.get(k) == v for k, v in labels.items()):
                return value

        return None
