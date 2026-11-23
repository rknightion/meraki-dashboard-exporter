"""MR SSID firewall rule count and LAN-access metrics collector (#290)."""

from __future__ import annotations

import asyncio
import json
import math
from collections import deque
from time import monotonic
from typing import TYPE_CHECKING, Any, cast

from ....core.api_facade import FacadeRateLimitExhaustedError, facade_for
from ....core.constants import MRMetricName
from ....core.domain_models import (
    WirelessSsid,
    WirelessSsidFirewallL3Rules,
    WirelessSsidFirewallL7Rules,
)
from ....core.error_handling import (
    ErrorCategory,
    categorize_error,
    validate_response_format,
    with_error_handling,
)
from ....core.fanout_cursor import (
    FanoutCursor,
    _positive_number,
    failure_retry_spacing,
    per_attempt_call_budget,
    sweep_ttl_seconds,
)
from ....core.logging import get_logger
from ....core.logging_decorators import log_api_call
from ....core.logging_helpers import LogContext
from ....core.metrics import LabelName
from ....core.scheduler import EndpointGroupName

if TYPE_CHECKING:
    from ...device import DeviceCollector

logger = get_logger(__name__)

# Meraki always appends a synthetic trailing rule to the L3 rule list that
# cannot be removed by the admin; exclude it from the user-defined count,
# mirroring mx_firewall.py's default-rule exclusion for MX appliances.
_DEFAULT_RULE_COMMENT = "Default rule"


class MRFirewallCollector:
    """Collector for per-SSID L3/L7 firewall rule counts and LAN-access policy.

    Enumerates the SSIDs configured on each wireless network
    (``getNetworkWirelessSsids``) and, for every *enabled* SSID only (bounding
    call volume to at most 15 SSIDs/network), fetches the L3 and L7 firewall
    rule sets. Disabled SSIDs are skipped entirely — this is mandatory, not an
    optimization, because call volume here is networks x enabled-SSIDs x 2.
    """

    def __init__(self, parent: DeviceCollector) -> None:
        """Initialize MR firewall collector.

        Parameters
        ----------
        parent : DeviceCollector
            Parent DeviceCollector instance that owns the metrics.

        """
        self.parent = parent
        self.api = parent.api
        self.settings = parent.settings
        self._discoveries: dict[str, FanoutCursor] = {}
        self._rules: dict[str, FanoutCursor] = {}
        self._pending_l7: dict[str, dict[str, float]] = {}
        self._ssids: dict[str, dict[str, list[WirelessSsid]]] = {}
        self._prefer_rules: dict[str, bool] = {}
        self._initialize_metrics()

    def _initialize_metrics(self) -> None:
        """Initialize SSID firewall-related metrics."""
        self._ssid_firewall_rules = self.parent._create_gauge(
            MRMetricName.MR_SSID_FIREWALL_RULES,
            "Number of user-defined SSID firewall rules by type (excludes the implicit default rule)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SSID,
                LabelName.RULE_TYPE,
            ],
        )

        self._ssid_allow_lan_access = self.parent._create_gauge(
            MRMetricName.MR_SSID_ALLOW_LAN_ACCESS,
            "Whether wireless clients on this SSID may access the LAN (1 = allowed, 0 = blocked)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SSID,
            ],
        )

    @with_error_handling(
        operation="Collect MR SSID firewall rules",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
        apply_deadline=False,
    )
    async def collect_ssid_firewall(
        self,
        org_id: str,
        org_name: str,
        networks: list[dict[str, Any]],
    ) -> None:
        """Collect per-SSID firewall rule counts for all wireless networks.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        networks : list[dict[str, Any]]
            Networks in the organization (already NetworkFilter-filtered via
            ``OrganizationInventory.get_networks``); filtered here to wireless
            networks only.

        """
        group = EndpointGroupName.MR_SSID_FIREWALL
        scheduler = getattr(self.parent, "scheduler", None)
        if scheduler is not None and scheduler.is_enabled(group) is False:
            return

        cutoff = self.parent.ssid_firewall_cutoff
        if cutoff is not None and asyncio.get_running_loop().time() >= cutoff:
            return
        window = asyncio.timeout_at(cutoff)
        try:
            async with window:
                await self._sweep(org_id, networks, cutoff)
        except TimeoutError:
            if not window.expired():
                raise
            # Cancel only this sweep. Any interrupted item stays incomplete,
            # ordered behind unattempted items, without counting as an API error.
            logger.debug("Deferring SSID firewall work at device cycle cutoff", org_id=org_id)

    async def _sweep(
        self, org_id: str, networks: list[dict[str, Any]], cutoff: float | None
    ) -> None:
        """Process due discoveries and rule pairs until the call or time budget ends."""
        group = EndpointGroupName.MR_SSID_FIREWALL
        network_ids = list(
            dict.fromkeys(
                n["id"] for n in networks if n.get("id") and "wireless" in n.get("productTypes", [])
            )
        )
        network_set = set(network_ids)
        discoveries = self._discoveries.setdefault(org_id, FanoutCursor())
        rules = self._rules.setdefault(org_id, FanoutCursor())
        cached = self._ssids.setdefault(org_id, {})
        discoveries.prune(network_ids)
        for network_id in list(cached):
            if network_id not in network_set:
                del cached[network_id]

        interval = float(self.parent._group_interval(group))
        retry = failure_retry_spacing(self.settings, interval)
        budget = per_attempt_call_budget(self.settings, getattr(self.parent, "rate_limiter", None))
        # Reserve the full pair cost even when resuming at L7. The one-item floor
        # permits one pair, but never an extra discovery.
        remaining = budget
        prefer_rules = self._prefer_rules.get(org_id, False)
        did_work = False
        cadence_reader = getattr(self.parent, "collector_cadence_seconds", None)
        cadence = _positive_number(cadence_reader() if callable(cadence_reader) else None) or 0.0

        by_key = {
            json.dumps([network_id, ssid.number]): (network_id, ssid)
            for network_id, ssids in cached.items()
            for ssid in ssids
        }
        rules.prune(by_key)
        pending_l7 = self._pending_l7.setdefault(org_id, {})
        for key in pending_l7.keys() - by_key.keys():
            del pending_l7[key]
        blocked = {
            network_id
            for network_id in network_ids
            if discoveries.last_attempt.get(network_id, -math.inf)
            > discoveries.last_success.get(network_id, -math.inf)
        }
        now = monotonic()
        due_discovery = discoveries.select(
            network_ids, interval=interval, retry_spacing=retry, limit=len(network_ids), now=now
        )
        due_rules = rules.select(
            list(by_key), interval=interval, retry_spacing=retry, limit=len(by_key), now=now
        )
        # Retryable failures go behind work not yet attempted. Plan each fleet
        # queue once; refreshes only inspect their own network's SSIDs.
        for cursor, due in ((discoveries, due_discovery), (rules, due_rules)):
            due.sort(
                key=lambda key: max(
                    cursor.last_success.get(key, -math.inf), cursor.last_attempt.get(key, -math.inf)
                )
            )
        discovery_queue = deque(due_discovery)
        rule_queue = deque(key for key in due_rules if by_key[key][0] not in blocked)
        queued_rules = set(rule_queue)
        clock = asyncio.get_running_loop().time

        while remaining > 0:
            # Do not admit another item even if the timeout callback has not run yet.
            if cutoff is not None and clock() >= cutoff:
                break
            while rule_queue and (
                rule_queue[0] not in by_key or by_key[rule_queue[0]][0] in blocked
            ):
                queued_rules.discard(rule_queue.popleft())
            # A one-call floor can accommodate one pair, only as the whole attempt.
            pair_fits = remaining >= 2 or (budget == 1 and remaining == 1)
            if rule_queue and pair_fits and (prefer_rules or not discovery_queue):
                key = rule_queue.popleft()
                queued_rules.discard(key)
                network_id, ssid = by_key[key]
                rules.record_attempt(key, monotonic())
                self._prefer_rules[org_id] = prefer_rules = False
                remaining -= 2
                did_work = True
                ttl = sweep_ttl_seconds(
                    self.parent._group_ttl_seconds(group),
                    interval,
                    len(network_ids) + 2 * (len(by_key) + 15 * (len(network_ids) - len(cached))),
                    max(1, budget - budget % 2),
                    cadence,
                )
                labels = {
                    LabelName.ORG_ID.value: org_id,
                    LabelName.NETWORK_ID.value: network_id,
                    LabelName.SSID.value: ssid.name or str(ssid.number),
                }
                try:
                    number = str(ssid.number)
                    # Resume at L7 only while the emitted L3 is fresh, so a
                    # persistent L7 failure cannot let healthy L3 series expire.
                    if monotonic() - pending_l7.get(key, -math.inf) >= interval:
                        await self._collect_l3_rules(network_id, number, labels, ttl)
                        pending_l7[key] = monotonic()
                    await self._collect_l7_rules(network_id, number, labels, ttl)
                except Exception as exc:
                    self._track_item_error(exc)
                    logger.exception(
                        "Failed to collect SSID firewall rules",
                        org_id=org_id,
                        network_id=network_id,
                        ssid_number=ssid.number,
                    )
                else:
                    del pending_l7[key]
                    rules.record_success(key, monotonic())
            elif discovery_queue:
                network_id = discovery_queue.popleft()
                discoveries.record_attempt(network_id, monotonic())
                self._prefer_rules[org_id] = prefer_rules = True
                remaining -= 1
                did_work = True
                try:
                    parsed = await self._discover_ssids(org_id=org_id, network_id=network_id)
                except Exception as exc:
                    self._track_item_error(exc)
                    blocked.add(network_id)
                    logger.exception(
                        "Failed to discover SSIDs", org_id=org_id, network_id=network_id
                    )
                else:
                    old_keys = {
                        json.dumps([network_id, ssid.number]) for ssid in cached.get(network_id, [])
                    }
                    cached[network_id] = parsed
                    new_keys = {json.dumps([network_id, ssid.number]): ssid for ssid in parsed}
                    for key in old_keys - new_keys.keys():
                        by_key.pop(key, None)
                        pending_l7.pop(key, None)
                        rules.last_attempt.pop(key, None)
                        rules.last_success.pop(key, None)
                    for key, ssid in new_keys.items():
                        by_key[key] = (network_id, ssid)
                    blocked.discard(network_id)
                    discoveries.record_success(network_id, monotonic())
                    for key in rules.select(
                        list(new_keys),
                        interval=interval,
                        retry_spacing=retry,
                        limit=len(new_keys),
                        now=monotonic(),
                    ):
                        if key not in queued_rules:
                            rule_queue.append(key)
                            queued_rules.add(key)
            else:
                break

        keys = [
            json.dumps([network_id, ssid.number])
            for network_id, ssids in cached.items()
            for ssid in ssids
        ]
        now = monotonic()
        if (
            (did_work or not network_ids)
            and discoveries.all_fresh(network_ids, interval, now)
            and rules.all_fresh(keys, interval, now)
        ):
            self.parent._mark_group_ran(group)

    def _track_item_error(self, exc: Exception) -> None:
        """Record a swallowed item failure against the owning collector."""
        category = (
            ErrorCategory.API_RATE_LIMIT
            if isinstance(exc, FacadeRateLimitExhaustedError)
            else categorize_error(exc)
        )
        if category is ErrorCategory.UNKNOWN:
            category = ErrorCategory.API_CLIENT_ERROR
        self.parent._track_error(category)

    @log_api_call("getNetworkWirelessSsids")
    async def _discover_ssids(self, org_id: str, network_id: str) -> list[WirelessSsid]:
        """Fetch validated, enabled, numbered SSIDs for one network."""
        with LogContext(org_id=org_id, network_id=network_id):
            try:
                raw = await facade_for(self).call(
                    "getNetworkWirelessSsids", self.api.wireless.getNetworkWirelessSsids, network_id
                )
            except Exception as exc:
                # Discovery is optional on these networks. Consume the structured
                # status here, before the API decorator can log 402 as an error.
                status = getattr(exc, "status", None)
                if not isinstance(status, int) or status not in {402, 404}:
                    raise
                logger.debug("SSID discovery not available", status=status)
                return []
        data = validate_response_format(
            raw, expected_type=list, operation="getNetworkWirelessSsids"
        )
        parsed = [WirelessSsid.model_validate(row) for row in data if row.get("enabled")]
        return [ssid for ssid in parsed if ssid.number is not None]

    async def _collect_l3_rules(
        self,
        network_id: str,
        ssid_number: str,
        base_labels: dict[str, str],
        ttl: float | None,
    ) -> None:
        """Fetch and emit the L3 rule count and LAN access policy for a single SSID.

        Parameters
        ----------
        network_id : str
            Network ID for the wireless network.
        ssid_number : str
            SSID number (0-14) as required by the firewall-rules endpoints.
        base_labels : dict[str, str]
            Shared org/network/ssid labels for every emitted series.
        ttl : float | None
            Fully-resolved per-series TTL for the MR_SSID_FIREWALL group.

        """
        l3_raw = await self._fetch_l3_rules(network_id, ssid_number)
        l3_data = validate_response_format(
            l3_raw,
            expected_type=dict,
            operation="getNetworkWirelessSsidFirewallL3FirewallRules",
        )
        l3 = WirelessSsidFirewallL3Rules.model_validate(l3_data)

        # The trailing rule is always the built-in default rule; exclude it
        # from the user-defined count (mirrors mx_firewall.py).
        user_l3_rules = [r for r in l3.rules if (r.comment or "") != _DEFAULT_RULE_COMMENT]

        self.parent._set_metric(
            self._ssid_firewall_rules,
            {**base_labels, LabelName.RULE_TYPE.value: "L3"},
            float(len(user_l3_rules)),
            ttl_seconds=ttl,
        )

        if l3.allowLanAccess is not None:
            self.parent._set_metric(
                self._ssid_allow_lan_access,
                base_labels,
                1.0 if l3.allowLanAccess else 0.0,
                ttl_seconds=ttl,
            )

    async def _collect_l7_rules(
        self,
        network_id: str,
        ssid_number: str,
        base_labels: dict[str, str],
        ttl: float | None,
    ) -> None:
        """Fetch and emit the L7 rule count for a single SSID."""
        l7_raw = await self._fetch_l7_rules(network_id, ssid_number)
        l7_data = validate_response_format(
            l7_raw,
            expected_type=dict,
            operation="getNetworkWirelessSsidFirewallL7FirewallRules",
        )
        l7 = WirelessSsidFirewallL7Rules.model_validate(l7_data)

        self.parent._set_metric(
            self._ssid_firewall_rules,
            {**base_labels, LabelName.RULE_TYPE.value: "L7"},
            float(len(l7.rules)),
            ttl_seconds=ttl,
        )

    @log_api_call("getNetworkWirelessSsidFirewallL3FirewallRules")
    async def _fetch_l3_rules(self, network_id: str, ssid_number: str) -> dict[str, Any]:
        """Fetch the L3 rules with endpoint-accurate API attribution."""
        return cast(
            dict[str, Any],
            await facade_for(self).call(
                "getNetworkWirelessSsidFirewallL3FirewallRules",
                self.api.wireless.getNetworkWirelessSsidFirewallL3FirewallRules,
                network_id,
                ssid_number,
            ),
        )

    @log_api_call("getNetworkWirelessSsidFirewallL7FirewallRules")
    async def _fetch_l7_rules(self, network_id: str, ssid_number: str) -> dict[str, Any]:
        """Fetch the L7 rules with endpoint-accurate API attribution."""
        return cast(
            dict[str, Any],
            await facade_for(self).call(
                "getNetworkWirelessSsidFirewallL7FirewallRules",
                self.api.wireless.getNetworkWirelessSsidFirewallL7FirewallRules,
                network_id,
                ssid_number,
            ),
        )
