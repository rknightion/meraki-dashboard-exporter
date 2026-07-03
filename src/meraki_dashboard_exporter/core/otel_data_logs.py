"""OpenTelemetry data-log emitter for high-cardinality per-entity product data (#622).

This is a NEW, dedicated OTLP **log** channel — distinct from tracing
(``otel_tracing.py``) and from trace-context-in-logs (``otel_logging.py``,
which despite its name does NOT export logs). It carries per-entity detail whose
entity population is unbounded or churny (per-client packet loss, per-connection
rows, ...) so that data never becomes a labelled Prometheus series and never
inflates metric cardinality.

Design invariants
-----------------
- **Private LoggerProvider.** The emitter builds its own ``LoggerProvider`` and
  does NOT call ``set_logger_provider`` and attaches NO ``LoggingHandler`` to
  stdlib/structlog. Application logs stay on stdout exactly as before; this is a
  product-data channel, not app-log export.
- **``_logs`` namespace confinement.** Every ``opentelemetry._logs`` /
  ``opentelemetry.sdk._logs`` import lives ONLY in this module. The logs SDK is
  still underscore-prefixed at OTel 1.43; confining the imports here means a
  future package rename is a one-file fix (and fails loudly in CI).
- **Off by default / cheap no-op.** When ``otel.logs.enabled`` is False (or an
  event is not in the allowlist) ``emit`` / ``is_event_enabled`` short-circuit
  on a boolean so producer code needs no config branching and pays no cost.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

# The OTel logs SDK is still underscore-prefixed (_logs) at 1.43; these private
# imports are deliberately confined to this one module (see module docstring), so
# the PLC2701 private-name warning is suppressed here rather than repo-wide.
from opentelemetry._logs import SeverityNumber  # noqa: PLC2701
from opentelemetry.sdk._logs import LoggerProvider  # noqa: PLC2701
from opentelemetry.sdk._logs.export import (  # noqa: PLC2701
    BatchLogRecordProcessor,
    SimpleLogRecordProcessor,
)
from prometheus_client import CollectorRegistry, Counter
from prometheus_client.core import REGISTRY

from .constants.metrics_constants import CollectorMetricName
from .logging import get_logger
from .metrics import LabelName
from .otel_tracing import build_otel_resource

if TYPE_CHECKING:
    from collections.abc import Mapping

    from opentelemetry.sdk._logs.export import LogExporter  # noqa: PLC2701

    from .config import Settings

logger = get_logger(__name__)

#: Default INFO severity re-exported so producers never import from ``_logs``.
INFO = SeverityNumber.INFO


class DataLogEvent(StrEnum):
    """Built-in data-log event names (the ``event.name`` attribute on each record).

    Namespaced ``meraki.<domain>.<entity>.<signal>``. This is the FROZEN, bounded
    set of event names — it bounds the self-observability counter cardinality and
    is what ``otel.logs.events`` allowlists against. Producer lanes add their event
    here (one line) when they land, then call ``emit(DataLogEvent.X, ...)``.
    """

    # #323 — per-client wireless packet loss (first producer, Lane 2).
    WIRELESS_CLIENT_PACKET_LOSS = "meraki.wireless.client.packet_loss"


#: The bounded universe of built-in event names (bounds counter cardinality).
BUILT_IN_EVENTS: frozenset[str] = frozenset(e.value for e in DataLogEvent)

#: Attribute keys treated as personal identifiers. The emitter DROPS these from
#: every record unless ``otel.logs.include_identifiers`` is True (#533 ID-only
#: stance / #559 GDPR). Stable IDs (``client.id``) are NOT in this set and are
#: always emitted. Producers must name any PII attribute from this set; the set
#: is extensible as new per-entity producers land.
PII_ATTRIBUTE_KEYS: frozenset[str] = frozenset({
    "client.mac",
    "client.hostname",
    "client.description",
})


class DataLogEmitter:
    """Emits structured OTLP log records for high-cardinality per-entity data.

    Constructed once in ``ExporterApp`` and threaded to every collector (see
    ``MetricCollector.__init__``'s ``data_log_emitter`` kwarg). Sub-collectors
    reach it via ``self.parent.data_log_emitter``.

    Parameters
    ----------
    settings : Settings
        Application settings (reads ``settings.otel.logs`` + resolved endpoint /
        insecure via ``settings.otel.logs_endpoint`` / ``logs_insecure``).
    registry : CollectorRegistry | None
        Prometheus registry for the self-observability counters. Defaults to the
        global ``REGISTRY``.
    exporter : LogExporter | None
        Test seam. When provided (e.g. an ``InMemoryLogRecordExporter``) it is
        wrapped in a synchronous ``SimpleLogRecordProcessor`` for deterministic
        assertions. When None and logs are enabled, a real
        ``BatchLogRecordProcessor(OTLPLogExporter(...))`` is built.

    """

    def __init__(
        self,
        settings: Settings,
        *,
        registry: CollectorRegistry | None = None,
        exporter: LogExporter | None = None,
    ) -> None:
        """Build the emitter; a cheap no-op when ``otel.logs.enabled`` is False."""
        self.settings = settings
        logs_cfg = settings.otel.logs
        self._enabled: bool = logs_cfg.enabled
        self._include_identifiers: bool = logs_cfg.include_identifiers
        # None => all built-in events; otherwise the explicit allowlist.
        self._events_allowlist: frozenset[str] | None = (
            frozenset(logs_cfg.events) if logs_cfg.events is not None else None
        )

        self._provider: LoggerProvider | None = None
        self._logger: Any | None = None
        self._emitted_counter: Counter | None = None
        self._dropped_counter: Counter | None = None

        if not self._enabled:
            logger.info("OTel data-log emitter disabled (otel.logs.enabled is False)")
            return

        reg = registry if registry is not None else REGISTRY
        self._emitted_counter = Counter(
            CollectorMetricName.DATA_LOG_RECORDS_EMITTED_TOTAL.value,
            "Data-log records handed to the OTLP log pipeline, by event (#622).",
            labelnames=[LabelName.EVENT.value],
            registry=reg,
        )
        self._dropped_counter = Counter(
            CollectorMetricName.DATA_LOG_RECORDS_DROPPED_TOTAL.value,
            (
                "Data-log records dropped before entering the OTLP pipeline "
                "(emit raised), by event (#622). Best-effort: batch-queue "
                "overflow drops are logged by the SDK, not counted here."
            ),
            labelnames=[LabelName.EVENT.value],
            registry=reg,
        )

        self._setup_provider(exporter)

    def _setup_provider(self, exporter: LogExporter | None) -> None:
        """Build the private LoggerProvider + processor (never sets the global)."""
        try:
            resource = build_otel_resource(self.settings)
            provider = LoggerProvider(resource=resource)

            if exporter is not None:
                # Synchronous processor for deterministic tests.
                provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
            else:
                # Import the OTLP exporter lazily so the _logs OTLP import stays
                # off the module-load path in test/no-op scenarios.
                from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (  # noqa: PLC2701
                    OTLPLogExporter,
                )

                otlp_exporter = OTLPLogExporter(
                    endpoint=self.settings.otel.logs_endpoint,
                    insecure=self.settings.otel.logs_insecure,
                )
                provider.add_log_record_processor(
                    BatchLogRecordProcessor(
                        otlp_exporter,
                        max_queue_size=2048,
                        max_export_batch_size=512,
                        export_timeout_millis=30000,
                    )
                )

            self._provider = provider
            self._logger = provider.get_logger("meraki_dashboard_exporter.data_logs")
            logger.info(
                "OTel data-log emitter initialized",
                endpoint=self.settings.otel.logs_endpoint,
                include_identifiers=self._include_identifiers,
                events=(
                    sorted(self._events_allowlist) if self._events_allowlist is not None else "all"
                ),
            )
        except Exception:
            # Never let a misconfigured data channel abort startup.
            logger.exception("Failed to initialize OTel data-log emitter; disabling")
            self._enabled = False
            self._provider = None
            self._logger = None

    @property
    def enabled(self) -> bool:
        """Whether the emitter is live (logs enabled and provider constructed)."""
        return self._enabled and self._logger is not None

    @property
    def include_identifiers(self) -> bool:
        """Whether PII identifier attributes are included on emitted records.

        Producers may read this to skip *building/fetching* identifier values
        entirely when they are gated off (zero cost); the emitter also strips
        them defensively regardless (see ``PII_ATTRIBUTE_KEYS``).
        """
        return self._include_identifiers

    def is_event_enabled(self, event_name: str) -> bool:
        """Return whether records for ``event_name`` would actually be emitted.

        Producers MUST call this before doing any API fetch for a data-log
        signal so non-users pay zero rate-limit cost. Short-circuits cheaply.

        Parameters
        ----------
        event_name : str
            A ``DataLogEvent`` value (or its string form).

        Returns
        -------
        bool
            True only if logs are enabled AND (no allowlist OR the event is
            allowlisted).

        """
        if not self.enabled:
            return False
        if self._events_allowlist is not None and event_name not in self._events_allowlist:
            return False
        return True

    def emit(
        self,
        event_name: str,
        attributes: Mapping[str, str | int | float | bool],
        *,
        severity: SeverityNumber = INFO,
        body: str | None = None,
    ) -> None:
        """Emit one OTLP data-log record. FROZEN public API — producers depend on it.

        No-op (cheap) when the emitter is disabled or the event is allowlisted
        out, so producers call unconditionally with no config branching.

        Parameters
        ----------
        event_name : str
            A ``DataLogEvent`` value; becomes the record's ``event.name``.
        attributes : Mapping[str, str | int | float | bool]
            Dot-namespaced bounded attribute keys (e.g. ``org.id``,
            ``network.id``, ``downstream.loss_percent``). Keys in
            ``PII_ATTRIBUTE_KEYS`` are dropped unless ``include_identifiers`` is
            True.
        severity : SeverityNumber
            Log severity; INFO always (this is data, not alerting). Do not vary.
        body : str | None
            Optional compact human-readable summary for the record body.

        """
        event_name = str(event_name)
        if not self.is_event_enabled(event_name):
            return

        try:
            attrs: dict[str, str | int | float | bool] = {"event.name": event_name}
            if self._include_identifiers:
                attrs.update(attributes)
            else:
                attrs.update({k: v for k, v in attributes.items() if k not in PII_ATTRIBUTE_KEYS})

            assert self._logger is not None  # guaranteed by is_event_enabled/enabled
            self._logger.emit(
                event_name=event_name,
                body=body,
                severity_number=severity,
                attributes=attrs,
            )
        except Exception:
            logger.exception("Failed to emit data-log record", data_log_event=event_name)
            if self._dropped_counter is not None:
                self._dropped_counter.labels(**{LabelName.EVENT.value: event_name}).inc()
            return

        if self._emitted_counter is not None:
            self._emitted_counter.labels(**{LabelName.EVENT.value: event_name}).inc()

    def shutdown(self) -> None:
        """Flush and shut down the private LoggerProvider (idempotent, safe)."""
        if self._provider is None:
            return
        try:
            self._provider.shutdown()
            logger.info("OTel data-log emitter shutdown complete")
        except Exception:
            logger.exception("Error shutting down OTel data-log emitter")
