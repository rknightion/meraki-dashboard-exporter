"""MX Firewall & Security Policy collector."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from meraki.exceptions import APIError

from ...core.constants.metrics_constants import MXMetricName
from ...core.domain_models import (
    ApplianceContentFiltering,
    ApplianceFirewallRules,
    ApplianceOneToManyNatRules,
    ApplianceOneToOneNatRules,
    AppliancePortForwardingRules,
    ApplianceSecurityEvent,
    ApplianceSecurityIntrusionSettings,
    ApplianceSecurityMalwareSettings,
    ApplianceStaticRoute,
    ApplianceVlan,
)
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
    policy setting for each appliance network. Firewall configuration changes
    infrequently, so this fan-out targets the ``mx_firewall_config`` group's
    solved interval (900s floor), but ``collect_for_network`` is actually
    dispatched every ``DeviceCollector`` cycle by
    ``_collect_mx_specific_metrics`` — there is no separate scheduling loop for
    this fan-out. That cadence is therefore self-enforced inside
    ``collect_for_network`` via
    ``_should_collect_firewall_rules``/``_mark_firewall_rules_collected``, keyed
    on the ``mx_firewall_config`` group's solved interval (see F-085).
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
        # mx_firewall_config cadence can be enforced even though collect_for_network
        # is dispatched every DeviceCollector cycle (see F-085).
        self._last_firewall_collection: dict[str, float] = {}
        # Phase 4 (#285/#288/#289): per-network throttles for the three NEW
        # config-drift endpoint groups, mirroring _last_firewall_collection above.
        # Each is a genuinely independent per-network fan-out (collect_for_network
        # is invoked once per appliance network per MEDIUM-tier cycle), so a
        # group-global _should_run_group/_mark_group_ran gate would collect only
        # the first network dispatched and skip every other network in the org
        # for the rest of the cycle -- exactly the bug _last_firewall_collection
        # already avoids for the firewall-rules group above.
        self._last_security_config_collection: dict[str, float] = {}
        self._last_nat_config_collection: dict[str, float] = {}
        self._last_vlan_config_collection: dict[str, float] = {}
        self._initialize_metrics()

    def _should_collect_firewall_rules(self, network_id: str) -> bool:
        """Return whether enough time has elapsed to (re)collect firewall rules.

        Mirrors the ``_should_collect_port_usage``/``_mark_port_usage_collected``
        throttle pattern in ``ms.py``. The interval is read from the
        ``mx_firewall_config`` endpoint group's solved interval (#617, floor
        900s), so the adaptive scheduler can stretch it; this collector is
        invoked every ``DeviceCollector`` cycle by
        ``_collect_mx_specific_metrics``.
        """
        interval = float(self.parent._group_interval(EndpointGroupName.MX_FIREWALL_CONFIG))
        if interval <= 0:
            return True
        last = self._last_firewall_collection.get(network_id, 0.0)
        return (time.time() - last) >= interval

    def _mark_firewall_rules_collected(self, network_id: str) -> None:
        """Record that firewall rules were just collected for this network."""
        self._last_firewall_collection[network_id] = time.time()

    def _should_collect_security_config(self, network_id: str) -> bool:
        """Return whether the mx_security_config group is due for this network (#285)."""
        interval = float(self.parent._group_interval(EndpointGroupName.MX_SECURITY_CONFIG))
        if interval <= 0:
            return True
        last = self._last_security_config_collection.get(network_id, 0.0)
        return (time.time() - last) >= interval

    def _mark_security_config_collected(self, network_id: str) -> None:
        """Record that security config was just collected for this network."""
        self._last_security_config_collection[network_id] = time.time()

    def _should_collect_nat_config(self, network_id: str) -> bool:
        """Return whether the mx_nat_config group is due for this network (#288)."""
        interval = float(self.parent._group_interval(EndpointGroupName.MX_NAT_CONFIG))
        if interval <= 0:
            return True
        last = self._last_nat_config_collection.get(network_id, 0.0)
        return (time.time() - last) >= interval

    def _mark_nat_config_collected(self, network_id: str) -> None:
        """Record that NAT config was just collected for this network."""
        self._last_nat_config_collection[network_id] = time.time()

    def _should_collect_vlan_config(self, network_id: str) -> bool:
        """Return whether the mx_vlan_config group is due for this network (#289)."""
        interval = float(self.parent._group_interval(EndpointGroupName.MX_VLAN_CONFIG))
        if interval <= 0:
            return True
        last = self._last_vlan_config_collection.get(network_id, 0.0)
        return (time.time() - last) >= interval

    def _mark_vlan_config_collected(self, network_id: str) -> None:
        """Record that VLAN/static-route config was just collected for this network."""
        self._last_vlan_config_collection[network_id] = time.time()

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

        # Phase 4 (#285): content filtering + malware + IDS/IPS config drift.
        network_labels = [LabelName.ORG_ID, LabelName.NETWORK_ID]
        self._content_filtering_blocked_categories = self.parent._create_gauge(
            MXMetricName.MX_CONTENT_FILTERING_BLOCKED_CATEGORIES,
            "Number of blocked URL categories configured for content filtering",
            labelnames=network_labels,
        )
        self._content_filtering_blocked_url_patterns = self.parent._create_gauge(
            MXMetricName.MX_CONTENT_FILTERING_BLOCKED_URL_PATTERNS,
            "Number of blocked URL patterns configured for content filtering",
            labelnames=network_labels,
        )
        self._content_filtering_allowed_url_patterns = self.parent._create_gauge(
            MXMetricName.MX_CONTENT_FILTERING_ALLOWED_URL_PATTERNS,
            "Number of allowed URL patterns configured for content filtering",
            labelnames=network_labels,
        )
        self._malware_protection_enabled = self.parent._create_gauge(
            MXMetricName.MX_MALWARE_PROTECTION_ENABLED,
            "Advanced Malware Protection enablement (1=enabled, 0=disabled)",
            labelnames=network_labels,
        )
        self._malware_allowed_urls = self.parent._create_gauge(
            MXMetricName.MX_MALWARE_ALLOWED_URLS,
            "Number of URLs excluded from Advanced Malware Protection scanning",
            labelnames=network_labels,
        )
        self._malware_allowed_files = self.parent._create_gauge(
            MXMetricName.MX_MALWARE_ALLOWED_FILES,
            "Number of files excluded from Advanced Malware Protection scanning",
            labelnames=network_labels,
        )
        self._ids_mode = self.parent._create_gauge(
            MXMetricName.MX_IDS_MODE,
            "IDS/IPS mode one-hot indicator (1=active mode for this network)",
            labelnames=[*network_labels, LabelName.MODE],
        )
        self._ids_ruleset = self.parent._create_gauge(
            MXMetricName.MX_IDS_RULESET,
            "IDS/IPS ruleset one-hot indicator (1=active ruleset for this network)",
            labelnames=[*network_labels, LabelName.RULESET],
        )

        # Phase 4 (#288): port-forwarding / NAT rule counts.
        self._port_forwarding_rules = self.parent._create_gauge(
            MXMetricName.MX_PORT_FORWARDING_RULES,
            "Number of port forwarding rules configured for a network",
            labelnames=network_labels,
        )
        self._nat_rules = self.parent._create_gauge(
            MXMetricName.MX_NAT_RULES,
            "Number of NAT rules configured for a network by type",
            labelnames=[*network_labels, LabelName.NAT_TYPE],
        )

        # Phase 4 (#289): VLAN + static-route counts.
        self._vlans_total = self.parent._create_gauge(
            MXMetricName.MX_VLANS,
            "Number of VLANs configured for a network",
            labelnames=network_labels,
        )
        self._static_routes_total = self.parent._create_gauge(
            MXMetricName.MX_STATIC_ROUTES,
            "Total number of static routes configured for a network",
            labelnames=network_labels,
        )
        self._static_routes_enabled = self.parent._create_gauge(
            MXMetricName.MX_STATIC_ROUTES_ENABLED,
            "Number of enabled static routes configured for a network",
            labelnames=network_labels,
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
        if self._should_collect_firewall_rules(network_id):
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
        else:
            logger.debug(
                "Skipping firewall rules collection (group interval not yet elapsed)",
                org_id=org_id,
                network_id=network_id,
                interval_seconds=self.parent._group_interval(EndpointGroupName.MX_FIREWALL_CONFIG),
            )

        # Phase 4 (#285/#288/#289): each of these is independently gated/decorated
        # (own per-network throttle + own error boundary) so a failure in one
        # config-drift domain never blocks the others for this network/cycle.
        await self.collect_security_config(org_id, network_id)
        await self.collect_nat_config(org_id, network_id)
        await self.collect_vlan_config(org_id, network_id)

    @log_api_call("getNetworkApplianceContentFiltering")
    @with_error_handling(
        operation="Collect MX security config (content filtering, malware, IDS/IPS)",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_security_config(self, org_id: str, network_id: str) -> None:
        """Collect content-filtering, malware, and IDS/IPS config drift (#285).

        Fetches three per-network config endpoints: content filtering, Advanced
        Malware Protection (AMP), and IDS/IPS (intrusion). Malware/intrusion
        return HTTP 400/404 when the network's org lacks an Advanced Security
        license -- that condition is caught locally and debug-logged, not raised,
        so a missing license on one sub-call never blocks the others.

        Parameters
        ----------
        org_id : str
            Organization ID.
        network_id : str
            Network ID for the appliance network.

        """
        if not self._should_collect_security_config(network_id):
            logger.debug(
                "Skipping security config collection (mx_security_config cadence not yet elapsed)",
                org_id=org_id,
                network_id=network_id,
            )
            return

        base_labels = {
            LabelName.ORG_ID: org_id,
            LabelName.NETWORK_ID: network_id,
        }
        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MX_SECURITY_CONFIG)

        # Content filtering (no license gate; always available on MX appliances).
        cf_response = await asyncio.to_thread(
            self.api.appliance.getNetworkApplianceContentFiltering,
            network_id,
        )
        cf_data = validate_response_format(
            cf_response,
            expected_type=dict,
            operation="getNetworkApplianceContentFiltering",
        )
        content_filtering = ApplianceContentFiltering.model_validate(cf_data)
        self.parent._set_metric(
            self._content_filtering_blocked_categories,
            base_labels,
            float(len(content_filtering.blockedUrlCategories)),
            ttl_seconds=ttl_seconds,
        )
        self.parent._set_metric(
            self._content_filtering_blocked_url_patterns,
            base_labels,
            float(len(content_filtering.blockedUrlPatterns)),
            ttl_seconds=ttl_seconds,
        )
        self.parent._set_metric(
            self._content_filtering_allowed_url_patterns,
            base_labels,
            float(len(content_filtering.allowedUrlPatterns)),
            ttl_seconds=ttl_seconds,
        )

        # Malware protection -- 400/404 without an Advanced Security license.
        try:
            self._track_api_call("getNetworkApplianceSecurityMalware")
            malware_response = await asyncio.to_thread(
                self.api.appliance.getNetworkApplianceSecurityMalware,
                network_id,
            )
            malware_data = validate_response_format(
                malware_response,
                expected_type=dict,
                operation="getNetworkApplianceSecurityMalware",
            )
            malware = ApplianceSecurityMalwareSettings.model_validate(malware_data)
            self.parent._set_metric(
                self._malware_protection_enabled,
                base_labels,
                1.0 if malware.mode == "enabled" else 0.0,
                ttl_seconds=ttl_seconds,
            )
            self.parent._set_metric(
                self._malware_allowed_urls,
                base_labels,
                float(len(malware.allowedUrls)),
                ttl_seconds=ttl_seconds,
            )
            self.parent._set_metric(
                self._malware_allowed_files,
                base_labels,
                float(len(malware.allowedFiles)),
                ttl_seconds=ttl_seconds,
            )
        except APIError as e:
            if e.status in {400, 404}:
                logger.debug(
                    "Malware protection not available (no Advanced Security license)",
                    org_id=org_id,
                    network_id=network_id,
                    status=e.status,
                )
            else:
                raise

        # IDS/IPS (intrusion) -- 400/404 without an Advanced Security license.
        try:
            self._track_api_call("getNetworkApplianceSecurityIntrusion")
            intrusion_response = await asyncio.to_thread(
                self.api.appliance.getNetworkApplianceSecurityIntrusion,
                network_id,
            )
            intrusion_data = validate_response_format(
                intrusion_response,
                expected_type=dict,
                operation="getNetworkApplianceSecurityIntrusion",
            )
            intrusion = ApplianceSecurityIntrusionSettings.model_validate(intrusion_data)
            if intrusion.mode:
                self.parent._set_metric(
                    self._ids_mode,
                    {**base_labels, LabelName.MODE: intrusion.mode},
                    1.0,
                    ttl_seconds=ttl_seconds,
                )
            if intrusion.idsRulesets:
                self.parent._set_metric(
                    self._ids_ruleset,
                    {**base_labels, LabelName.RULESET: intrusion.idsRulesets},
                    1.0,
                    ttl_seconds=ttl_seconds,
                )
        except APIError as e:
            if e.status in {400, 404}:
                logger.debug(
                    "IDS/IPS not available (no Advanced Security license)",
                    org_id=org_id,
                    network_id=network_id,
                    status=e.status,
                )
            else:
                raise

        self._mark_security_config_collected(network_id)

    @log_api_call("getNetworkApplianceFirewallPortForwardingRules")
    @with_error_handling(
        operation="Collect MX port-forwarding/NAT config",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_nat_config(self, org_id: str, network_id: str) -> None:
        """Collect port-forwarding and NAT rule counts for a network (#288).

        Empty rule arrays are a normal, expected response (no port-forwarding
        or NAT rules configured) and are emitted as a count of 0, not skipped.

        Parameters
        ----------
        org_id : str
            Organization ID.
        network_id : str
            Network ID for the appliance network.

        """
        if not self._should_collect_nat_config(network_id):
            logger.debug(
                "Skipping NAT config collection (mx_nat_config cadence not yet elapsed)",
                org_id=org_id,
                network_id=network_id,
            )
            return

        base_labels = {
            LabelName.ORG_ID: org_id,
            LabelName.NETWORK_ID: network_id,
        }
        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MX_NAT_CONFIG)

        pf_response = await asyncio.to_thread(
            self.api.appliance.getNetworkApplianceFirewallPortForwardingRules,
            network_id,
        )
        pf_data = validate_response_format(
            pf_response,
            expected_type=dict,
            operation="getNetworkApplianceFirewallPortForwardingRules",
        )
        port_forwarding = AppliancePortForwardingRules.model_validate(pf_data)
        self.parent._set_metric(
            self._port_forwarding_rules,
            base_labels,
            float(len(port_forwarding.rules)),
            ttl_seconds=ttl_seconds,
        )

        self._track_api_call("getNetworkApplianceFirewallOneToOneNatRules")
        one_to_one_response = await asyncio.to_thread(
            self.api.appliance.getNetworkApplianceFirewallOneToOneNatRules,
            network_id,
        )
        one_to_one_data = validate_response_format(
            one_to_one_response,
            expected_type=dict,
            operation="getNetworkApplianceFirewallOneToOneNatRules",
        )
        one_to_one = ApplianceOneToOneNatRules.model_validate(one_to_one_data)
        self.parent._set_metric(
            self._nat_rules,
            {**base_labels, LabelName.NAT_TYPE: "1:1"},
            float(len(one_to_one.rules)),
            ttl_seconds=ttl_seconds,
        )

        self._track_api_call("getNetworkApplianceFirewallOneToManyNatRules")
        one_to_many_response = await asyncio.to_thread(
            self.api.appliance.getNetworkApplianceFirewallOneToManyNatRules,
            network_id,
        )
        one_to_many_data = validate_response_format(
            one_to_many_response,
            expected_type=dict,
            operation="getNetworkApplianceFirewallOneToManyNatRules",
        )
        one_to_many = ApplianceOneToManyNatRules.model_validate(one_to_many_data)
        self.parent._set_metric(
            self._nat_rules,
            {**base_labels, LabelName.NAT_TYPE: "1:many"},
            float(len(one_to_many.rules)),
            ttl_seconds=ttl_seconds,
        )

        self._mark_nat_config_collected(network_id)

    @log_api_call("getNetworkApplianceVlans")
    @with_error_handling(
        operation="Collect MX VLAN/static-route config",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_vlan_config(self, org_id: str, network_id: str) -> None:
        """Collect VLAN and static-route counts for a network (#289).

        ``getNetworkApplianceVlans`` returns HTTP 400 when VLANs are not
        enabled for the network (single-LAN mode) -- that is caught locally
        and debug-logged, not raised, so the static-route counts below are
        still collected. Only aggregate counts are emitted, never per-VLAN or
        per-route series (unbounded cardinality).

        Parameters
        ----------
        org_id : str
            Organization ID.
        network_id : str
            Network ID for the appliance network.

        """
        if not self._should_collect_vlan_config(network_id):
            logger.debug(
                "Skipping VLAN config collection (mx_vlan_config cadence not yet elapsed)",
                org_id=org_id,
                network_id=network_id,
            )
            return

        base_labels = {
            LabelName.ORG_ID: org_id,
            LabelName.NETWORK_ID: network_id,
        }
        ttl_seconds = self.parent._group_ttl_seconds(EndpointGroupName.MX_VLAN_CONFIG)

        try:
            vlans_response = await asyncio.to_thread(
                self.api.appliance.getNetworkApplianceVlans,
                network_id,
            )
            vlans_data = validate_response_format(
                vlans_response,
                expected_type=list,
                operation="getNetworkApplianceVlans",
            )
            vlans = [ApplianceVlan.model_validate(v) for v in vlans_data]
            self.parent._set_metric(
                self._vlans_total,
                base_labels,
                float(len(vlans)),
                ttl_seconds=ttl_seconds,
            )
        except APIError as e:
            if e.status in {400, 404}:
                logger.debug(
                    "VLANs not enabled for this network (single-LAN mode)",
                    org_id=org_id,
                    network_id=network_id,
                    status=e.status,
                )
            else:
                raise

        self._track_api_call("getNetworkApplianceStaticRoutes")
        routes_response = await asyncio.to_thread(
            self.api.appliance.getNetworkApplianceStaticRoutes,
            network_id,
        )
        routes_data = validate_response_format(
            routes_response,
            expected_type=list,
            operation="getNetworkApplianceStaticRoutes",
        )
        routes = [ApplianceStaticRoute.model_validate(r) for r in routes_data]
        self.parent._set_metric(
            self._static_routes_total,
            base_labels,
            float(len(routes)),
            ttl_seconds=ttl_seconds,
        )
        self.parent._set_metric(
            self._static_routes_enabled,
            base_labels,
            float(sum(1 for r in routes if r.enabled)),
            ttl_seconds=ttl_seconds,
        )

        self._mark_vlan_config_collected(network_id)

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

        The ``timespan`` is bounded to the ``mx_security_events`` group's solved
        interval (``parent._group_interval(EndpointGroupName.MX_SECURITY_EVENTS)``, 300s floor)
        because this method is invoked once per ``DeviceCollector`` cycle from
        ``_collect_mx_specific_metrics``.
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

        # Fetch the window since the last poll: the group's solved interval
        # (covers the whole cadence even when the solver stretches it, #631).
        timespan = int(self.parent._group_interval(EndpointGroupName.MX_SECURITY_EVENTS))

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
