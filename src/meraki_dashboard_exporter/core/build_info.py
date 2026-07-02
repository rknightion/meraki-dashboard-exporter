"""Static exporter build-info metric (``meraki_exporter_build_info``).

The classic Prometheus build-info pattern: a constant gauge whose value is always
``1`` and whose ``version``/``commit`` labels identify the running build, so
operators can pin a scrape to an exact build or alert on version skew across a
rollout.
"""

from __future__ import annotations

from prometheus_client import REGISTRY, CollectorRegistry, Gauge

from ..__version__ import get_commit, get_version
from .constants.metrics_constants import CollectorMetricName
from .metrics import LabelName


def register_build_info(registry: CollectorRegistry = REGISTRY) -> Gauge:
    """Register ``meraki_exporter_build_info`` and set it to 1.

    The ``version`` label is sourced from :func:`get_version` and ``commit`` from
    :func:`get_commit`. Local/dev builds produced without the ``APP_VERSION`` and
    ``GIT_COMMIT`` Docker build-args report ``version="0.0.0+dev"`` and
    ``commit="unknown"`` (DEP-06).

    Parameters
    ----------
    registry : CollectorRegistry
        The registry to register the gauge on; defaults to the global default
        registry. A parameter mainly so tests can use an isolated registry.

    Returns
    -------
    Gauge
        The registered build-info gauge.

    """
    build_info = Gauge(
        CollectorMetricName.BUILD_INFO.value,
        "Exporter build information as a constant gauge (value always 1); the "
        "version and commit labels identify the running build. Local/dev builds "
        "without the APP_VERSION and GIT_COMMIT build-args report "
        "version='0.0.0+dev' and commit='unknown'.",
        labelnames=[LabelName.VERSION.value, LabelName.COMMIT.value],
        registry=registry,
    )
    build_info.labels(version=get_version(), commit=get_commit()).set(1)
    return build_info
