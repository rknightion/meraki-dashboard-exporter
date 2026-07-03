"""MX Firewall & Security Policy collector."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from ...core.constants.metrics_constants import MXMetricName
from ...core.domain_models import ApplianceFirewallRules, ApplianceSecurityEvent
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.metrics import LabelName
from ...core.scheduler import EndpointGroupName
from ..subcollector_mixin import SubCollectorMixin

if TYPE_CHECKING:
    from meraki import DashboardAPI

    from ...core.config import Settings

logger = get_logger(__name__)


class MXFirewallCollector(SubCollectorMixin):
    """Collector for MX firewall rules and security policy metrics.

    Collects L3 and L7 firewall rule counts per network, plus the default
    policy setting for each appliance network. Intended to run at the SLOW
    cadence (900s) as firewall configuration changes infrequently, but
    ``collect_for_network`` is actually dispatched every MEDIUM-tier (300s)
    cycle by ``DeviceCollector._collect_mx_specific_metrics`` — there is no
    separate SLOW-tier scheduling loop for this fan-out. The SLOW cadence is
    therefore self-enforced inside ``collect_for_network`` via
    ``_should_collect_firewall_rules``/``_mark_firewall_rules_collected``,
    keyed on ``settings.update_intervals.slow`` (see F-085).
    """

    def __init__(self, parent: Any) -> None:
        """Initialize MX firewall collector.

        Parameters
        ----------
        parent : Any
            Parent collector instance (MXCollector) that exposes
            ``_create_gauge``, ``_set_metric``, ``api``, and ``settings``.

        """
        self.parent = parent
        self.api: DashboardAPI = parent.api
        self.settings: Settings = parent.settings
        # Tracks the last time firewall rules were collected per network_id so the
        # SLOW-tier cadence can be enforced even though collect_for_network is
        # dispatched every MEDIUM-tier cycle by DeviceCollector (see F-085).
        self._last_firewall_collection: dict[str, float] = {}
        self._initialize_metrics()

    def _should_collect_firewall_rules(self, network_id: str) -> bool:
        """Return whether enough time has elapsed to (re)collect firewall rules.

        Mirrors the ``_should_collect_port_usage``/``_mark_port_usage_collected``
        throttle pattern in ``ms.py``. The interval is read from the
        ``mx_firewall_config`` endpoint group's solved interval (#617, floor
        900s) rather than ``settings.update_intervals.slow`` directly, so the
        adaptive scheduler can stretch it; this collector is invoked every
        MEDIUM-tier (300s) cycle by ``DeviceCollector._collect_mx_specific_metrics``.
        """
        interval = float(self.parent._group_interval(EndpointGroupName.MX_FIREWALL_CONFIG))
        if interval <= 0:
            return True
        last = self._last_firewall_collection.get(network_id, 0.0)
        return (time.time() - last) >= interval

    def _mark_firewall_rules_collected(self, network_id: str) -> None:
        """Record that firewall rules were just collected for this network."""
        self._last_firewall_collection[network_id] = time.time()

    def _initialize_metrics(self) -> None:
        """Initialize firewall-related Prometheus gauge metrics."""
        self._firewall_rules_total = self.parent._create_gauge(
            MXMetricName.MX_FIREWALL_RULES,
            "Number of user-defined firewall rules by type (excludes default rule)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.RULE_TYPE,
            ],
        )
        self._firewall_default_policy = self.parent._create_gauge(
            MXMetricName.MX_FIREWALL_DEFAULT_POLICY,
            "Firewall default policy for L3 rules (1=allow, 0=deny)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
            ],
        )
        self._security_events_count = self.parent._create_gauge(
            MXMetricName.MX_SECURITY_EVENTS_COUNT,
            "Security events by type in the current collection window (not a monotonic total)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.EVENT_TYPE,
            ],
        )

    @log_api_call("getNetworkApplianceFirewallL3FirewallRules")
    @with_error_handling(
        operation="Collect MX firewall rules",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_for_network(
        self,
        org_id: str,
        org_name: str,
        network_id: str,
        network_name: str,
    ) -> None:
        """Collect firewall rule counts and default policy for a single network.

        Fetches L3 and L7 firewall rules for the given appliance network.
        The last rule in the L3 rule list is always the default rule and is
        excluded from the user-defined rule count.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        network_id : str
            Network ID for the appliance network.
        network_name : str
            Human-readable network name.

        """
        if not self._should_collect_firewall_rules(network_id):
            logger.debug(
                "Skipping firewall rules collection (SLOW-tier cadence not yet elapsed)",
                org_id=org_id,
                network_id=network_id,
                interval_seconds=self.settings.update_intervals.slow,
            )
            return

        base_labels = {
            LabelName.ORG_ID: org_id,
            LabelName.NETWORK_ID: network_id,
        }
        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MX_FIREWALL_CONFIG)

        # L3 rules. Wrap in validate_response_format so an SDK exhausted-retry
        # error shape (a dict with an "errors" key) raises instead of silently
        # yielding empty rules and emitting a false-zero rule count (F-034).
        l3_response = await asyncio.to_thread(
            self.api.appliance.getNetworkApplianceFirewallL3FirewallRules,
            network_id,
        )
        l3_data = validate_response_format(
            l3_response,
            expected_type=dict,
            operation="getNetworkApplianceFirewallL3FirewallRules",
        )
        l3_rules = ApplianceFirewallRules.model_validate(l3_data).rules

        # The last rule is always the built-in default rule; exclude it from the count
        user_l3_rules = [r for r in l3_rules if (r.comment or "") != "Default rule"]

        self.parent._set_metric(
            self._firewall_rules_total,
            {**base_labels, LabelName.RULE_TYPE: "L3"},
            float(len(user_l3_rules)),
            ttl_seconds=ttl_seconds,
        )

        # Default policy: determined from the last rule's policy field
        if l3_rules:
            default_rule = l3_rules[-1]
            default_policy = default_rule.policy or "deny"
            self.parent._set_metric(
                self._firewall_default_policy,
                base_labels,
                1.0 if default_policy == "allow" else 0.0,
                ttl_seconds=ttl_seconds,
            )

        # L7 rules (same error-shape normalization as L3)
        self._track_api_call("getNetworkApplianceFirewallL7FirewallRules")
        l7_response = await asyncio.to_thread(
            self.api.appliance.getNetworkApplianceFirewallL7FirewallRules,
            network_id,
        )
        l7_data = validate_response_format(
            l7_response,
            expected_type=dict,
            operation="getNetworkApplianceFirewallL7FirewallRules",
        )
        l7_rules = ApplianceFirewallRules.model_validate(l7_data).rules

        self.parent._set_metric(
            self._firewall_rules_total,
            {**base_labels, LabelName.RULE_TYPE: "L7"},
            float(len(l7_rules)),
            ttl_seconds=ttl_seconds,
        )

        self._mark_firewall_rules_collected(network_id)

        logger.debug(
            "Collected firewall rules",
            org_id=org_id,
            network_id=network_id,
            l3_user_rules=len(user_l3_rules),
            l7_rules=len(l7_rules),
        )

    @log_api_call("getOrganizationApplianceSecurityEvents")
    @with_error_handling(
        operation="Collect MX security events",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_org_security_events(self, org_id: str, org_name: str) -> None:
        """Collect aggregated MX security event counts for an organization.

        Fetches org-wide IDS/IPS and AMP security events (``getOrganizationApplianceSecurityEvents``)
        in a single call per organization and aggregates the count of events by ``eventType``
        (e.g. "IDS Alert", "File Scanned") over the current collection window.

        The ``timespan`` is bounded to the MEDIUM update-tier interval
        (``settings.update_intervals.medium``, default 300s) because this method is invoked once
        per MEDIUM-tier collection cycle from ``DeviceCollector._collect_mx_specific_metrics``.
        Bounding the timespan to the poll interval means each cycle's counts reflect only events
        detected since the previous cycle, avoiding double-counting events across cycles.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        # mx_security_events gate (#617): single org-wide call per cycle.
        if not self.parent._should_run_group(EndpointGroupName.MX_SECURITY_EVENTS):
            return

        timespan = self.settings.update_intervals.medium

        events_response = await asyncio.to_thread(
            self.api.appliance.getOrganizationApplianceSecurityEvents,
            org_id,
            total_pages="all",
            timespan=timespan,
            perPage=1000,
        )

        events_response = validate_response_format(
            events_response,
            expected_type=list,
            operation="getOrganizationApplianceSecurityEvents",
        )

        # Resolve allowed network IDs for filter enforcement on this org-wide response.
        allowed_network_ids = (
            await self.parent.inventory.get_allowed_network_ids(org_id)
            if self.parent.inventory is not None
            else None
        )
        skipped = 0
        counts: dict[str, int] = {}

        for raw_event in events_response:
            network_id = raw_event.get("networkId", "")
            if allowed_network_ids is not None and network_id not in allowed_network_ids:
                skipped += 1
                continue

            event = ApplianceSecurityEvent.model_validate(raw_event)
            event_type = event.eventType or "unknown"
            counts[event_type] = counts.get(event_type, 0) + 1

        # NB: do NOT clear the gauge here. collect_org_security_events runs once per
        # org (concurrently across orgs, sharing one gauge instance), so a global
        # _metrics.clear() would wipe every other org's series mid-cycle. Event types
        # with zero events this cycle are reclaimed by the metric expiration manager
        # via parent._set_metric tracking instead.

        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MX_SECURITY_EVENTS)
        for event_type, count in counts.items():
            self.parent._set_metric(
                self._security_events_count,
                {
                    LabelName.ORG_ID: org_id,
                    LabelName.EVENT_TYPE: event_type,
                },
                float(count),
                ttl_seconds=ttl_seconds,
            )

        # Mark after a successful org-wide fetch (failures retry next cycle).
        self.parent._mark_group_ran(EndpointGroupName.MX_SECURITY_EVENTS)

        logger.debug(
            "Collected MX security events",
            org_id=org_id,
            event_count=len(events_response),
            event_types=len(counts),
            skipped_count=skipped,
        )
