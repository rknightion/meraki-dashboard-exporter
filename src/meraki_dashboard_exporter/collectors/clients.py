"""Client metrics collector for network-wide client data."""

from __future__ import annotations

import asyncio
import time
from typing import Any, ClassVar, cast

import structlog

from ..core.api_helpers import create_api_helper
from ..core.api_models import NetworkClient
from ..core.batch_processing import process_in_batches_with_errors
from ..core.collector import MetricCollector
from ..core.constants import ClientMetricName
from ..core.constants.metrics_constants import CollectorMetricName
from ..core.error_handling import (
    ErrorCategory,
    validate_response_format,
    with_error_handling,
)
from ..core.label_helpers import create_client_labels, create_network_labels
from ..core.logging_decorators import log_api_call, log_collection_progress
from ..core.metrics import LabelName, create_labels
from ..core.registry import register_collector
from ..core.scheduler import EndpointGroup, EndpointGroupName
from ..services.client_store import ClientStore
from ..services.dns_resolver import DNSResolver

logger = structlog.get_logger(__name__)

# Per-network wireless-client cap used to estimate signal-quality demand (mirrors
# APISettings.client_signal_quality_max_clients default; cost_fn takes only the
# OrgShape, so the cap is encoded here rather than read from settings).
_SIGNAL_QUALITY_CLIENT_CAP = 200


@register_collector
class ClientsCollector(MetricCollector):
    """Collector for client-level metrics across all networks."""

    # Scheduler endpoint groups (#617 §2, MEDIUM tier). ``clients_list`` (pri3)
    # covers the per-network getNetworkClients fan-out; ``clients_app_usage`` and
    # ``clients_signal_quality`` (pri4) keep their existing per-network interval
    # gates but read the interval from the scheduler and are pinned by their
    # legacy interval settings when the operator sets them. Dropped entirely when
    # client collection is disabled (see get_endpoint_groups).
    endpoint_groups: ClassVar[tuple[EndpointGroup, ...]] = (
        EndpointGroup(
            name=EndpointGroupName.CLIENTS_LIST,
            priority=3,
            floor_seconds=300,
            cost_fn=lambda shape: float(shape.network_count),
        ),
        EndpointGroup(
            name=EndpointGroupName.CLIENTS_APP_USAGE,
            priority=4,
            floor_seconds=600,
            cost_fn=lambda shape: float(shape.network_count),
            setting_pin="client_app_usage_interval",
        ),
        EndpointGroup(
            name=EndpointGroupName.CLIENTS_SIGNAL_QUALITY,
            priority=4,
            floor_seconds=600,
            cost_fn=lambda shape: float(shape.wireless_network_count * _SIGNAL_QUALITY_CLIENT_CAP),
            setting_pin="client_signal_quality_interval",
        ),
    )

    def get_endpoint_groups(self) -> tuple[EndpointGroup, ...]:
        """Return client endpoint groups, or ``()`` when clients are disabled.

        When ``clients.enabled`` is False the collector emits nothing, so its
        groups must never enter the solver's demand accounting (#617 §1c).

        Returns
        -------
        tuple[EndpointGroup, ...]
            The declared groups when enabled, else an empty tuple.

        """
        if not self.settings.clients.enabled:
            return ()
        return type(self).endpoint_groups

    @property
    def is_active(self) -> bool:
        """Check if this collector is actively collecting metrics."""
        return getattr(self, "_enabled", False)

    def __init__(self, *args: Any, **kwargs: Any):
        """Initialize the clients collector.

        Parameters
        ----------
        *args : Any
            Positional arguments passed to parent.
        **kwargs : Any
            Keyword arguments passed to parent. ``org_health_tracker`` (F-169), if
            present, is consumed here rather than forwarded to the base collector.

        """
        # Shared per-org health tracker (F-169): consumed before the base __init__
        # (which does not accept it). When present, per-org collection is skipped
        # for organizations currently in backoff. Gating consumer only -- the
        # tracker is owned/updated by OrganizationCollector.
        self.org_health_tracker = kwargs.pop("org_health_tracker", None)

        super().__init__(*args, **kwargs)

        # Check if client collection is enabled
        if not self.settings.clients.enabled:
            logger.info("Client data collection is disabled")
            self._enabled = False
            return

        self._enabled = True
        self.api_helper = create_api_helper(self)

        # Initialize services
        self.client_store = ClientStore(self.settings)
        self.dns_resolver = DNSResolver(self.settings)

        # Initialize DNS stats tracking
        self._last_dns_stats: dict[str, float] | None = None
        self._last_app_usage_by_network: dict[str, float] = {}
        # Per-network throttle for the sequential signal-quality fan-out (F-060).
        self._last_signal_quality_by_network: dict[str, float] = {}
        # Per-collection aggregate counters for the INFO summary (F-171).
        self._collection_networks = 0
        self._collection_clients = 0

    def _initialize_metrics(self) -> None:
        """Initialize Prometheus metrics for client data."""
        # Skip metric initialization if collector is disabled
        if not self.settings.clients.enabled:
            return

        # Client status metric (1 = online, 0 = offline)
        self.client_status = self._create_gauge(
            ClientMetricName.CLIENT_STATUS,
            "Client online status (1 = online, 0 = offline)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.CLIENT_ID,
            ],
        )

        # Client information join metric (issue #533): the ONLY client metric
        # allowed to carry descriptive/PII-ish labels. Numeric client series are
        # ID-only and join via `<numeric> * on(client_id) group_left(mac,
        # description, hostname, ssid) meraki_client_info`.
        self.client_info = self._create_gauge(
            ClientMetricName.CLIENT_INFO,
            "Client information join metric (client_id -> mac/description/hostname/ssid); "
            "value is always 1. Labels churn (old series expire) when a client's hostname/"
            "description/SSID changes.",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.CLIENT_ID,
                LabelName.MAC,
                LabelName.DESCRIPTION,
                LabelName.HOSTNAME,
                LabelName.SSID,
            ],
        )

        # Clients dropped from metric emission by the per-network/global cap (#533).
        self.clients_over_cap = self._create_gauge(
            CollectorMetricName.CLIENTS_OVER_CAP,
            "Clients excluded from metric emission in the most recent cycle because the "
            "per-network or global client cap was reached (0 = within caps)",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
            ],
        )

        # Client usage metrics - using Gauge since these are point-in-time measurements
        # that can go up or down (hourly usage windows from API)
        self.client_usage_sent = self._create_gauge(
            ClientMetricName.CLIENT_USAGE_SENT_BYTES,
            "Bytes sent by client in the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.CLIENT_ID,
            ],
        )

        self.client_usage_recv = self._create_gauge(
            ClientMetricName.CLIENT_USAGE_RECV_BYTES,
            "Bytes received by client in the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.CLIENT_ID,
            ],
        )

        self.client_usage_total = self._create_gauge(
            ClientMetricName.CLIENT_USAGE_TOTAL_BYTES,
            "Total bytes transferred by client in the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.CLIENT_ID,
            ],
        )

        # DNS cache metrics (enum-named; #319)
        self.dns_cache_total = self._create_gauge(
            CollectorMetricName.CLIENT_DNS_CACHE_TOTAL,
            "Total number of entries in DNS cache",
        )

        self.dns_cache_valid = self._create_gauge(
            CollectorMetricName.CLIENT_DNS_CACHE_VALID,
            "Number of valid entries in DNS cache",
        )

        self.dns_cache_expired = self._create_gauge(
            CollectorMetricName.CLIENT_DNS_CACHE_EXPIRED,
            "Number of expired entries in DNS cache",
        )

        # Cache-hit ratio over the process lifetime (0..1) = cache_hits/total_lookups (#319).
        self.dns_cache_hit_ratio = self._create_gauge(
            CollectorMetricName.CLIENT_DNS_CACHE_HIT_RATIO,
            "Ratio of reverse-DNS lookups served from cache (0..1), cumulative over "
            "process lifetime",
        )

        self.dns_lookups_total = self._create_counter(
            CollectorMetricName.CLIENT_DNS_LOOKUPS_TOTAL,
            "Total number of DNS lookups performed",
        )

        self.dns_lookups_successful = self._create_counter(
            CollectorMetricName.CLIENT_DNS_LOOKUPS_SUCCESSFUL_TOTAL,
            "Total number of successful DNS lookups",
        )

        self.dns_lookups_failed = self._create_counter(
            CollectorMetricName.CLIENT_DNS_LOOKUPS_FAILED_TOTAL,
            "Total number of failed DNS lookups",
        )

        self.dns_lookups_cached = self._create_counter(
            CollectorMetricName.CLIENT_DNS_LOOKUPS_CACHED_TOTAL,
            "Total number of DNS lookups served from cache",
        )

        # Cumulative wall-clock seconds spent in actual reverse-DNS lookups
        # (excludes cache hits). Divide the delta by the delta of
        # successful+failed lookups for average lookup latency (#319).
        self.dns_resolution_seconds = self._create_counter(
            CollectorMetricName.CLIENT_DNS_RESOLUTION_SECONDS_TOTAL,
            "Cumulative seconds spent performing reverse-DNS lookups (excludes cache hits)",
        )

        # Client store metrics
        self.client_store_total = self._create_gauge(
            CollectorMetricName.CLIENT_STORE_TOTAL,
            "Total number of clients in the store",
        )

        self.client_store_networks = self._create_gauge(
            CollectorMetricName.CLIENT_STORE_NETWORKS,
            "Total number of networks with clients",
        )

        # Client capability metrics
        self.client_capabilities_count = self._create_gauge(
            ClientMetricName.WIRELESS_CLIENT_CAPABILITIES_COUNT,
            "Count of wireless clients by capability, over the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.TYPE,  # For the capability type
            ],
        )

        # Client distribution metrics
        self.clients_per_ssid = self._create_gauge(
            ClientMetricName.CLIENTS_PER_SSID_COUNT,
            "Count of clients per SSID, over the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.SSID,
            ],
        )

        self.clients_per_vlan = self._create_gauge(
            ClientMetricName.CLIENTS_PER_VLAN_COUNT,
            "Count of clients per VLAN, over the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.VLAN,
            ],
        )

        # Client application usage metrics
        self.client_app_usage_sent = self._create_gauge(
            ClientMetricName.CLIENT_APPLICATION_USAGE_SENT_BYTES,
            "Bytes sent by client per application in the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.CLIENT_ID,
                LabelName.TYPE,  # For the application type
            ],
        )

        self.client_app_usage_recv = self._create_gauge(
            ClientMetricName.CLIENT_APPLICATION_USAGE_RECV_BYTES,
            "Bytes received by client per application in the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.CLIENT_ID,
                LabelName.TYPE,  # For the application type
            ],
        )

        self.client_app_usage_total = self._create_gauge(
            ClientMetricName.CLIENT_APPLICATION_USAGE_TOTAL_BYTES,
            "Total bytes transferred by client per application in the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.CLIENT_ID,
                LabelName.TYPE,  # For the application type
            ],
        )

        # Wireless client signal quality metrics
        self.wireless_client_rssi = self._create_gauge(
            ClientMetricName.WIRELESS_CLIENT_RSSI,
            "Wireless client RSSI (Received Signal Strength Indicator) in dBm, "
            "most recent 5-min sample; collected only when "
            "MERAKI_EXPORTER_CLIENTS__SIGNAL_QUALITY_ENABLED=true",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.CLIENT_ID,
            ],
        )

        self.wireless_client_snr = self._create_gauge(
            ClientMetricName.WIRELESS_CLIENT_SNR,
            "Wireless client SNR (Signal-to-Noise Ratio) in dB, most recent 5-min sample; "
            "collected only when MERAKI_EXPORTER_CLIENTS__SIGNAL_QUALITY_ENABLED=true",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.NETWORK_ID,
                LabelName.CLIENT_ID,
            ],
        )

    async def _collect_impl(self) -> None:
        """Collect client metrics from all organizations and networks."""
        if not self._enabled:
            logger.debug("Client collection is disabled, skipping")
            return

        # Scheduler-gated as the ``clients_list`` group (#617 §2): the whole
        # per-network getNetworkClients fan-out (and its downstream app-usage /
        # signal-quality collection) is skipped this heartbeat until the group is
        # due. The app-usage / signal-quality groups keep their own per-network
        # interval gates layered on top.
        if not self._should_run_group(EndpointGroupName.CLIENTS_LIST):
            logger.debug("clients_list group not due this heartbeat; skipping client collection")
            return

        # Reset per-collection aggregate counters (F-171 INFO summary).
        self._collection_networks = 0
        self._collection_clients = 0
        # Reset the global emission-cap counter (#533) for this collection cycle.
        self._cycle_clients_emitted = 0

        organizations = await self.api_helper.get_organizations()

        if not organizations:
            return

        # Track whether ANY network across ANY org fetched clients successfully so
        # the clients_list group is marked ran only on >=1 successful fetch (#629).
        # Total failure (every network failed, or every org skipped by backoff)
        # leaves the gate open so the next heartbeat retries.
        any_network_succeeded = False

        for org in organizations:
            org_id = org["id"]
            org_name = org["name"]

            # Skip organizations currently in backoff so a persistently-failing org
            # does not receive full-rate client collection every cycle (F-169).
            if self.org_health_tracker is not None and not self.org_health_tracker.should_collect(
                org_id
            ):
                logger.debug(
                    "Skipping client collection for organization in backoff",
                    org_id=org_id,
                    org_name=org_name,
                )
                continue

            # Get all networks for the organization
            networks = await self.api_helper.get_organization_networks(org_id)

            if not networks:
                continue

            # Process networks directly without batching to avoid lambda issues
            # Since we're already processing one org at a time, this is fine
            if await self._process_network_batch(org_id, org_name, networks):
                any_network_succeeded = True

        # Record a successful clients_list cycle so the gate throttles the next,
        # but only when at least one network actually fetched (#629); otherwise
        # leave the gate open so the next heartbeat retries.
        if any_network_succeeded:
            self._mark_group_ran(EndpointGroupName.CLIENTS_LIST)

        # Aggregate INFO summary for the whole collection (F-171): the per-network
        # "Fetched client data" / "Updated client data" lines are debug-level.
        logger.info(
            "Completed client data collection",
            networks_processed=self._collection_networks,
            total_clients=self._collection_clients,
        )

        # Evict client data for networks no longer seen this cycle (departed
        # networks) so the store stays bounded (#543). is_network_stale uses the
        # client cache_ttl (default 1h), so only networks absent for longer than
        # that TTL are removed -- a network merely skipped this MEDIUM cycle is
        # not flapped out.
        evicted_networks = self.client_store.cleanup_stale_networks()
        if evicted_networks:
            logger.debug(
                "Evicted stale networks from client store",
                networks_evicted=evicted_networks,
            )

        # Update DNS cache and client store metrics after all collections
        self._update_cache_metrics()

    async def _process_network_batch(
        self,
        org_id: str,
        org_name: str,
        networks: list[Any],
    ) -> bool:
        """Process a batch of networks for client collection.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        networks : list[Any]
            List of networks to process.

        Returns
        -------
        bool
            ``True`` when at least one network's ``getNetworkClients`` fetch
            succeeded this batch, used by ``_collect_impl`` to decide whether to
            mark the ``clients_list`` group ran (#629).

        """
        if not networks:
            return False

        batch_size = self.settings.api.client_batch_size
        delay_between_batches = self.settings.api.batch_delay

        async def _process_network(network: dict[str, Any]) -> bool | None:
            return await self._collect_network_clients(
                org_id,
                org_name,
                network["id"],
                network["name"],
            )

        results = await process_in_batches_with_errors(
            networks,
            _process_network,
            batch_size=batch_size,
            delay_between_batches=delay_between_batches,
            spread_over_seconds=self._get_smoothing_window(),
            initial_delay=self._get_smoothing_offset(f"{org_id}:clients"),
            min_batch_delay=self.settings.api.smoothing_min_batch_delay,
            max_batch_delay=self.settings.api.smoothing_max_batch_delay,
            item_description="network",
            error_context_func=lambda network: {
                "org_id": org_id,
                "org_name": org_name,
                "network_id": network.get("id"),
                "network_name": network.get("name"),
            },
        )

        # A per-network fetch counts as successful only when it returned the
        # truthy sentinel; swallowed failures return None/False or surface as an
        # Exception in the batch results (#629).
        return any(result is True for _network, result in results)

    @with_error_handling(
        operation="Collect network clients",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    @log_api_call("getNetworkClients")
    async def _collect_network_clients(
        self,
        org_id: str,
        org_name: str,
        network_id: str,
        network_name: str,
    ) -> bool:
        """Collect client data for a specific network.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        network_id : str
            Network ID.
        network_name : str
            Network name.

        Returns
        -------
        bool
            ``True`` when the ``getNetworkClients`` fetch for this network
            succeeded, ``False`` when it failed. The per-network success signal
            lets ``_collect_impl`` mark the ``clients_list`` group ran only when
            at least one network fetched successfully (#629). The outer
            ``@with_error_handling(continue_on_error=True)`` wrapper returns
            ``None`` if anything downstream raises, which also counts as failure.

        """
        logger.debug(
            "Collecting client data",
            org_id=org_id,
            org_name=org_name,
            network_id=network_id,
            network_name=network_name,
        )

        # Always fetch fresh data from API to get current status and usage
        # The cache is only used for hostname lookups, not for skipping API calls
        try:
            clients_data = await asyncio.to_thread(
                self.api.networks.getNetworkClients,
                network_id,
                timespan=3600,  # 1 hour as requested
                perPage=5000,  # Maximum allowed
                total_pages="all",
            )
        except Exception as e:
            logger.error(
                "Failed to fetch clients",
                org_id=org_id,
                network_id=network_id,
                network_name=network_name,
                error=str(e),
            )
            self._track_error(ErrorCategory.API_CLIENT_ERROR)
            return False

        # Validate response format (handles API error responses like rate limits)
        clients_data = validate_response_format(
            clients_data, expected_type=list, operation="getNetworkClients"
        )

        # Parse client data
        clients = [NetworkClient.model_validate(c) for c in clients_data]

        # Accumulate for the aggregate INFO summary emitted by _collect_impl (F-171).
        self._collection_networks += 1
        self._collection_clients += len(clients)

        # F-171: per-network line demoted to debug to keep log volume bounded at scale.
        logger.debug(
            "Fetched client data",
            org_id=org_id,
            network_id=network_id,
            network_name=network_name,
            client_count=len(clients),
        )

        # Apply the per-network/global emission cap (#533) BEFORE DNS resolution
        # so the DNS fan-out (and the store/metrics work below) is also bounded.
        clients = self._apply_emission_cap(org_id, network_id, network_name, clients)

        # Prepare client data for DNS resolution
        client_data = [(c.id, c.ip, c.description) for c in clients]

        # Resolve hostnames with client tracking
        logger.debug(
            "Resolving hostnames for network",
            network_id=network_id,
            client_count=len(clients),
        )
        hostnames = await self.dns_resolver.resolve_multiple(client_data)

        # Update client store
        self.client_store.update_clients(
            network_id,
            clients,
            network_name=network_name,
            org_id=org_id,
            hostnames=hostnames,
        )

        # Update metrics
        await self._update_metrics(org_id, org_name, network_id, network_name, clients, hostnames)

        # Collect application usage data
        await self._collect_application_usage(org_id, org_name, network_id, network_name, clients)

        # Collect wireless signal quality data
        await self._collect_wireless_signal_quality(
            org_id, org_name, network_id, network_name, clients
        )

        # The getNetworkClients fetch (the clients_list group) succeeded for this
        # network; downstream app-usage / signal-quality collection belong to
        # their own groups and their failures are swallowed independently (#629).
        return True

    def _apply_emission_cap(
        self, org_id: str, network_id: str, network_name: str, clients: list[NetworkClient]
    ) -> list[NetworkClient]:
        """Truncate the client list to the per-network and global emission caps (#533).

        Applied before DNS resolution, the client store update, and metric
        emission so a persistently oversized network/org does not blow the DNS
        fan-out, the store, or per-cycle metric cardinality. Always emits the
        ``meraki_exporter_clients_over_cap`` gauge (0 included) so the cap state
        is observable even when nothing was dropped.

        Parameters
        ----------
        org_id : str
            Organization ID.
        network_id : str
            Network ID.
        network_name : str
            Network name (for logging only).
        clients : list[NetworkClient]
            Full list of clients fetched for the network.

        Returns
        -------
        list[NetworkClient]
            The (possibly truncated) list of clients to emit metrics/DNS/store for.

        """
        total_clients = len(clients)

        # Per-network cap first.
        per_network_cap = self.settings.clients.max_clients_per_network
        allowed = clients[:per_network_cap]

        # Then the remaining global budget for this collection cycle.
        global_cap = self.settings.clients.max_clients_total
        remaining_global_capacity = max(global_cap - self._cycle_clients_emitted, 0)
        allowed = allowed[:remaining_global_capacity]

        self._cycle_clients_emitted += len(allowed)

        dropped = total_clients - len(allowed)

        self._set_metric(
            self.clients_over_cap,
            create_labels(org_id=org_id, network_id=network_id),
            dropped,
            CollectorMetricName.CLIENTS_OVER_CAP.value,
            ttl_seconds=self._group_ttl_seconds(EndpointGroupName.CLIENTS_LIST),
        )

        if dropped > 0:
            logger.warning(
                "Client cap exceeded; dropping clients from metric emission",
                org_id=org_id,
                network_id=network_id,
                network_name=network_name,
                total_clients=total_clients,
                emitted=len(allowed),
                dropped=dropped,
                per_network_cap=per_network_cap,
                global_cap=global_cap,
            )

        return allowed

    def _sanitize_label_value(self, value: str | None, max_length: int = 2048) -> str:
        """Sanitize a label value for Prometheus.

        Parameters
        ----------
        value : str | None
            Value to sanitize.
        max_length : int
            Maximum length for the label value.

        Returns
        -------
        str
            Sanitized value.

        """
        if not value:
            return ""

        # Replace characters not allowed in Prometheus labels with hyphen
        # Allowed: [a-zA-Z0-9_-]
        sanitized = ""
        for char in value:
            if char.isalnum() or char in "_- ":
                sanitized += char
            else:
                sanitized += "-"

        # Truncate to max length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        return sanitized

    def _sanitize_capability_for_metric(self, capability: str | None) -> str:
        """Sanitize wireless capability string for use as a metric label.

        Converts capability strings like "802.11ac - 2.4 and 5 GHz" to
        a more metric-friendly format like "802_11ac_2_4_and_5_ghz".

        Parameters
        ----------
        capability : str | None
            Wireless capability string.

        Returns
        -------
        str
            Sanitized capability string suitable for metric labels.

        """
        if not capability:
            return "unknown"

        # Convert to lowercase and replace common patterns
        sanitized = capability.lower()

        # Replace dots with underscores (802.11 -> 802_11)
        sanitized = sanitized.replace(".", "_")

        # Replace spaces and hyphens with underscores
        sanitized = sanitized.replace(" - ", "_")
        sanitized = sanitized.replace(" ", "_")
        sanitized = sanitized.replace("-", "_")

        # Remove any remaining non-alphanumeric characters except underscores
        result = ""
        for char in sanitized:
            if char.isalnum() or char == "_":
                result += char

        # Clean up multiple consecutive underscores
        while "__" in result:
            result = result.replace("__", "_")

        # Remove leading/trailing underscores
        result = result.strip("_")

        return result if result else "unknown"

    def _sanitize_application_name(self, app_name: str | None) -> str:
        """Sanitize application name for use as a metric label.

        Converts application names like "Google HTTPS" to a more
        metric-friendly format like "google_https".

        Parameters
        ----------
        app_name : str | None
            Application name from Meraki API.

        Returns
        -------
        str
            Sanitized application name suitable for metric labels.

        """
        if not app_name:
            return "unknown"

        # Convert to lowercase
        sanitized = app_name.lower()

        # Replace common patterns
        sanitized = sanitized.replace(" - ", "_")
        sanitized = sanitized.replace(" ", "_")
        sanitized = sanitized.replace("-", "_")
        sanitized = sanitized.replace("(", "_")
        sanitized = sanitized.replace(")", "_")
        sanitized = sanitized.replace("/", "_")
        sanitized = sanitized.replace("\\", "_")
        sanitized = sanitized.replace(".", "_")
        sanitized = sanitized.replace(",", "_")
        sanitized = sanitized.replace(":", "_")
        sanitized = sanitized.replace(";", "_")
        sanitized = sanitized.replace("'", "")
        sanitized = sanitized.replace('"', "")

        # Remove any remaining non-alphanumeric characters except underscores
        result = ""
        for char in sanitized:
            if char.isalnum() or char == "_":
                result += char

        # Clean up multiple consecutive underscores
        while "__" in result:
            result = result.replace("__", "_")

        # Remove leading/trailing underscores
        result = result.strip("_")

        return result if result else "unknown"

    def _determine_hostname(
        self,
        client: NetworkClient,
        resolved_hostname: str | None,
    ) -> str:
        """Determine the hostname to use for a client.

        Priority:
        1. Resolved hostname from DNS
        2. Client description (if not empty)
        3. Client IP address
        4. "unknown"

        Parameters
        ----------
        client : NetworkClient
            Client data.
        resolved_hostname : str | None
            Hostname resolved from DNS.

        Returns
        -------
        str
            Hostname to use.

        """
        # Priority 1: DNS resolved hostname
        if resolved_hostname:
            return resolved_hostname

        # Priority 2: Client description
        if client.description:
            return client.description

        # Priority 3: Client IP
        if client.ip:
            return client.ip

        # Priority 4: Fallback
        return "unknown"

    @log_collection_progress("clients")
    async def _update_metrics(
        self,
        org_id: str,
        org_name: str,
        network_id: str,
        network_name: str,
        clients: list[NetworkClient],
        hostnames: dict[str, str | None],
        current: int = 0,
        total: int = 0,
    ) -> None:
        """Update Prometheus metrics for clients.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        network_id : str
            Network ID.
        network_name : str
            Network name.
        clients : list[NetworkClient]
            List of clients.
        hostnames : dict[str, str | None]
            Resolved hostnames by IP.
        current : int
            Current progress (for logging).
        total : int
            Total items (for logging).

        """
        # Per-series TTL for the clients_list group so a stretched cadence does
        # not let these series flap between cycles (#617 §1f).
        ttl = self._group_ttl_seconds(EndpointGroupName.CLIENTS_LIST)

        # Track counts for aggregated metrics
        capabilities_count: dict[str, int] = {}
        ssid_count: dict[str, int] = {}
        vlan_count: dict[str, int] = {}

        for client in clients:
            # Get resolved hostname from DNS
            resolved_hostname = hostnames.get(client.ip) if client.ip else None

            # Determine final hostname using fallback logic
            hostname = self._determine_hostname(client, resolved_hostname)

            # Sanitize label values
            sanitized_hostname = self._sanitize_label_value(hostname)
            sanitized_description = self._sanitize_label_value(client.description)

            # Determine effective SSID
            ssid = client.ssid if client.recentDeviceConnection == "Wireless" else "Wired"

            # Track aggregated counts
            # 1. Wireless capabilities (only for wireless clients)
            if client.recentDeviceConnection == "Wireless" and client.wirelessCapabilities:
                cap_key = self._sanitize_capability_for_metric(client.wirelessCapabilities)
                capabilities_count[cap_key] = capabilities_count.get(cap_key, 0) + 1

            # 2. SSID counts
            ssid_key = ssid or "Unknown"
            ssid_count[ssid_key] = ssid_count.get(ssid_key, 0) + 1

            # 3. VLAN counts
            vlan_key = str(client.vlan) if client.vlan else "untagged"
            vlan_count[vlan_key] = vlan_count.get(vlan_key, 0) + 1

            # Create client labels using helper (ID-only: org_id, network_id,
            # client_id -- issue #533). Descriptive fields live on
            # meraki_client_info below, not on this numeric series.
            labels = create_client_labels(
                {"id": client.id},
                org_id=org_id,
                org_name=org_name,
                network_id=network_id,
                network_name=network_name,
            )

            # Set client status
            status_value = 1 if client.status == "Online" else 0
            self._set_metric(
                self.client_status,
                labels,
                status_value,
                ClientMetricName.CLIENT_STATUS.value,
                ttl_seconds=ttl,
            )

            # Set usage metrics (as gauges - these are point-in-time measurements)
            if client.usage:
                sent_kb = client.usage.get("sent", 0)
                recv_kb = client.usage.get("recv", 0)
                total_kb = client.usage.get("total", 0)

                # Set gauge values (API returns decimal KB; convert to bytes, ×1000)
                self._set_metric(
                    self.client_usage_sent,
                    labels,
                    float(sent_kb) * 1000,
                    ClientMetricName.CLIENT_USAGE_SENT_BYTES.value,
                    ttl_seconds=ttl,
                )
                self._set_metric(
                    self.client_usage_recv,
                    labels,
                    float(recv_kb) * 1000,
                    ClientMetricName.CLIENT_USAGE_RECV_BYTES.value,
                    ttl_seconds=ttl,
                )
                self._set_metric(
                    self.client_usage_total,
                    labels,
                    float(total_kb) * 1000,
                    ClientMetricName.CLIENT_USAGE_TOTAL_BYTES.value,
                    ttl_seconds=ttl,
                )

            # Emit the id-keyed join metric (issue #533): the only client metric
            # carrying descriptive/PII-ish labels. Numeric series above join back
            # onto this via `on(client_id) group_left(...)`.
            info_labels = create_labels(
                org_id=org_id,
                network_id=network_id,
                client_id=client.id,
                mac=client.mac,
                description=sanitized_description,
                hostname=sanitized_hostname,
                ssid=ssid or "Unknown",
            )
            self._set_metric(
                self.client_info,
                info_labels,
                1,
                ClientMetricName.CLIENT_INFO.value,
                ttl_seconds=ttl,
            )

            logger.debug(
                "Updated client metrics",
                client_id=client.id,
                mac=client.mac,
                description=client.description,
                hostname=hostname,
                status=client.status,
                ssid=ssid,
            )

        # Update aggregated metrics after processing all clients
        # 1. Wireless capabilities metrics
        for capability, count in capabilities_count.items():
            # Use create_network_labels for network-level metrics
            network_data = {"id": network_id, "name": network_name}
            cap_labels = create_network_labels(
                network_data,
                org_id=org_id,
                org_name=org_name,
                type=capability,
            )
            self._set_metric(
                self.client_capabilities_count,
                cap_labels,
                count,
                ClientMetricName.WIRELESS_CLIENT_CAPABILITIES_COUNT.value,
                ttl_seconds=ttl,
            )
            logger.debug(
                "Set wireless capability count",
                capability=capability,
                count=count,
                network_id=network_id,
            )

        # 2. SSID metrics
        for ssid_name, count in ssid_count.items():
            # Use create_network_labels for network-level metrics
            network_data = {"id": network_id, "name": network_name}
            ssid_labels = create_network_labels(
                network_data,
                org_id=org_id,
                org_name=org_name,
                ssid=ssid_name,
            )
            self._set_metric(
                self.clients_per_ssid,
                ssid_labels,
                count,
                ClientMetricName.CLIENTS_PER_SSID_COUNT.value,
                ttl_seconds=ttl,
            )
            logger.debug(
                "Set SSID client count",
                ssid=ssid_name,
                count=count,
                network_id=network_id,
            )

        # 3. VLAN metrics
        for vlan_id, count in vlan_count.items():
            # Use create_network_labels for network-level metrics
            network_data = {"id": network_id, "name": network_name}
            vlan_labels = create_network_labels(
                network_data,
                org_id=org_id,
                org_name=org_name,
                vlan=vlan_id,
            )
            self._set_metric(
                self.clients_per_vlan,
                vlan_labels,
                count,
                ClientMetricName.CLIENTS_PER_VLAN_COUNT.value,
                ttl_seconds=ttl,
            )
            logger.debug(
                "Set VLAN client count",
                vlan=vlan_id,
                count=count,
                network_id=network_id,
            )

    @with_error_handling(
        operation="Collect application usage",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    @log_api_call("getNetworkClientsApplicationUsage")
    async def _collect_application_usage(
        self,
        org_id: str,
        org_name: str,
        network_id: str,
        network_name: str,
        clients: list[NetworkClient],
    ) -> None:
        """Collect application usage data for clients.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        network_id : str
            Network ID.
        network_name : str
            Network name.
        clients : list[NetworkClient]
            List of clients.

        """
        if not clients:
            return

        # Per-network interval gate now reads its cadence from the scheduler
        # (#617 §2 clients_app_usage) instead of the raw
        # ``client_app_usage_interval`` setting; the setting still pins the group
        # when the operator sets it explicitly (setting_pin).
        interval = self._group_interval(EndpointGroupName.CLIENTS_APP_USAGE)
        last_run = self._last_app_usage_by_network.get(network_id, 0.0)
        if interval > 0 and (time.time() - last_run) < interval:
            logger.debug(
                "Skipping client application usage collection",
                network_id=network_id,
                interval_seconds=interval,
            )
            return

        # Per-series TTL for the app-usage group (#617 §1f).
        ttl = self._group_ttl_seconds(EndpointGroupName.CLIENTS_APP_USAGE)

        # Extract client IDs
        client_ids = [client.id for client in clients]

        # Create a lookup map for client data
        client_map = {client.id: client for client in clients}

        logger.debug(
            "Fetching application usage data",
            network_id=network_id,
            client_count=len(client_ids),
        )

        # Batch client IDs for API calls. The API's documented per-request limit is
        # 1000 client IDs, but passing that many as a comma-separated query param risks
        # an HTTP 414 (URI Too Long) at scale -- cap well below that (#525).
        batch_size = 100
        for i in range(0, len(client_ids), batch_size):
            batch_ids = client_ids[i : i + batch_size]

            try:
                if i > 0:
                    self._track_api_call("getNetworkClientsApplicationUsage")
                rate_limiter = getattr(self, "rate_limiter", None)
                if rate_limiter is not None and i > 0:
                    await rate_limiter.acquire(org_id, "getNetworkClientsApplicationUsage")
                usage_response = await asyncio.to_thread(
                    self.api.networks.getNetworkClientsApplicationUsage,
                    network_id,
                    clients=",".join(batch_ids),
                    timespan=3600,  # 1 hour as requested
                    perPage=1000,
                    total_pages="all",
                )
                usage_data = cast(
                    list[dict[str, Any]],
                    validate_response_format(
                        usage_response,
                        expected_type=list,
                        operation="getNetworkClientsApplicationUsage",
                    ),
                )

                # Process usage data for each client
                for client_usage in usage_data:
                    client_id = client_usage.get("clientId")
                    if not client_id or client_id not in client_map:
                        continue

                    # Process each application's usage
                    for app_usage in client_usage.get("applicationUsage", []):
                        app_name = app_usage.get("application", "unknown")
                        sanitized_app = self._sanitize_application_name(app_name)

                        received_kb = app_usage.get("received", 0)
                        sent_kb = app_usage.get("sent", 0)
                        total_kb = received_kb + sent_kb

                        # Create client labels using helper (ID-only + type -- #533)
                        labels = create_client_labels(
                            {"id": client_id},
                            org_id=org_id,
                            org_name=org_name,
                            network_id=network_id,
                            network_name=network_name,
                            type=sanitized_app,
                        )

                        # Set metrics (API returns decimal KB; convert to bytes, ×1000)
                        self._set_metric(
                            self.client_app_usage_sent,
                            labels,
                            float(sent_kb) * 1000,
                            ClientMetricName.CLIENT_APPLICATION_USAGE_SENT_BYTES.value,
                            ttl_seconds=ttl,
                        )
                        self._set_metric(
                            self.client_app_usage_recv,
                            labels,
                            float(received_kb) * 1000,
                            ClientMetricName.CLIENT_APPLICATION_USAGE_RECV_BYTES.value,
                            ttl_seconds=ttl,
                        )
                        self._set_metric(
                            self.client_app_usage_total,
                            labels,
                            float(total_kb) * 1000,
                            ClientMetricName.CLIENT_APPLICATION_USAGE_TOTAL_BYTES.value,
                            ttl_seconds=ttl,
                        )

                        logger.debug(
                            "Set application usage metrics",
                            client_id=client_id,
                            application=app_name,
                            sanitized_app=sanitized_app,
                            sent_kb=sent_kb,
                            received_kb=received_kb,
                        )

            except Exception as e:
                logger.error(
                    "Failed to fetch application usage data",
                    network_id=network_id,
                    batch_start=i,
                    batch_size=len(batch_ids),
                    error=str(e),
                )
                self._track_error(ErrorCategory.API_CLIENT_ERROR)
                # Continue with next batch
                continue

        self._last_app_usage_by_network[network_id] = time.time()

        logger.info(
            "Completed application usage collection",
            network_id=network_id,
            client_count=len(client_ids),
        )

    @with_error_handling(
        operation="Collect wireless signal quality",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    @log_api_call("getNetworkWirelessSignalQualityHistory")
    async def _collect_wireless_signal_quality(
        self,
        org_id: str,
        org_name: str,
        network_id: str,
        network_name: str,
        clients: list[NetworkClient],
    ) -> None:
        """Collect wireless signal quality data for clients.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        network_id : str
            Network ID.
        network_name : str
            Network name.
        clients : list[NetworkClient]
            List of clients.

        """
        # Opt-in gate (issue #533): per-client wireless signal quality costs one
        # API call per wireless client per cycle and is prohibitively expensive
        # at scale, so it is disabled by default.
        if not self.settings.clients.signal_quality_enabled:
            logger.debug(
                "Client signal quality collection is disabled",
                network_id=network_id,
            )
            return

        # F-060: gate the whole per-client fan-out behind an interval, mirroring
        # application-usage collection, so we don't drain the shared org rate-limit
        # budget on every MEDIUM-tier cycle. The cadence now comes from the
        # scheduler (#617 §2 clients_signal_quality); the raw
        # ``client_signal_quality_interval`` setting still pins the group when the
        # operator sets it (setting_pin).
        interval = self._group_interval(EndpointGroupName.CLIENTS_SIGNAL_QUALITY)
        last_run = self._last_signal_quality_by_network.get(network_id, 0.0)
        if interval > 0 and (time.time() - last_run) < interval:
            logger.debug(
                "Skipping client signal quality collection",
                network_id=network_id,
                interval_seconds=interval,
            )
            return

        # Per-series TTL for the signal-quality group (#617 §1f).
        ttl = self._group_ttl_seconds(EndpointGroupName.CLIENTS_SIGNAL_QUALITY)

        # Filter to only wireless clients
        wireless_clients = [
            client for client in clients if client.recentDeviceConnection == "Wireless"
        ]

        if not wireless_clients:
            logger.debug("No wireless clients found in network", network_id=network_id)
            return

        # F-060: cap the number of clients queried per network to bound the
        # sequential per-client fan-out (0 disables the cap).
        max_clients = self.settings.api.client_signal_quality_max_clients
        clients_to_query = wireless_clients
        if max_clients > 0 and len(wireless_clients) > max_clients:
            logger.warning(
                "Truncating wireless clients for signal quality collection",
                network_id=network_id,
                total_wireless_clients=len(wireless_clients),
                limit=max_clients,
            )
            clients_to_query = wireless_clients[:max_clients]

        logger.debug(
            "Fetching wireless signal quality data",
            network_id=network_id,
            wireless_client_count=len(clients_to_query),
        )

        rate_limiter = getattr(self, "rate_limiter", None)

        # Process each wireless client individually. One API call per client; the
        # @log_api_call decorator already counts the first, so only track the rest
        # to avoid an off-by-one overcount (mirrors the batched pattern elsewhere).
        for idx, client in enumerate(clients_to_query):
            try:
                if idx > 0:
                    self._track_api_call("getNetworkWirelessSignalQualityHistory")
                # F-060: throttle the fan-out through the shared org rate limiter
                # (mirrors application-usage; the first call is already accounted
                # for by @log_api_call).
                if rate_limiter is not None and idx > 0:
                    await rate_limiter.acquire(org_id, "getNetworkWirelessSignalQualityHistory")
                signal_response = await asyncio.to_thread(
                    self.api.wireless.getNetworkWirelessSignalQualityHistory,
                    network_id,
                    clientId=client.id,
                    timespan=300,  # 5 minutes as required
                    resolution=300,  # 5 minutes as required
                )
                signal_data = cast(
                    list[dict[str, Any]],
                    validate_response_format(
                        signal_response,
                        expected_type=list,
                        operation="getNetworkWirelessSignalQualityHistory",
                    ),
                )

                if not signal_data:
                    logger.debug(
                        "No signal quality data returned",
                        client_id=client.id,
                        network_id=network_id,
                    )
                    continue

                # Get the most recent data point
                latest_data = signal_data[-1] if signal_data else None

                if not latest_data:
                    continue

                # Extract signal quality values
                rssi = latest_data.get("rssi")
                snr = latest_data.get("snr")

                if rssi is None and snr is None:
                    logger.debug(
                        "No RSSI or SNR data in response",
                        client_id=client.id,
                    )
                    continue

                # Create client labels using helper (ID-only -- #533; ssid is
                # dropped here and carried on meraki_client_info instead)
                labels = create_client_labels(
                    {"id": client.id},
                    org_id=org_id,
                    org_name=org_name,
                    network_id=network_id,
                    network_name=network_name,
                )

                # Set metrics
                if rssi is not None:
                    self._set_metric(
                        self.wireless_client_rssi,
                        labels,
                        float(rssi),
                        ClientMetricName.WIRELESS_CLIENT_RSSI.value,
                        ttl_seconds=ttl,
                    )

                if snr is not None:
                    self._set_metric(
                        self.wireless_client_snr,
                        labels,
                        float(snr),
                        ClientMetricName.WIRELESS_CLIENT_SNR.value,
                        ttl_seconds=ttl,
                    )

                logger.debug(
                    "Set wireless signal quality metrics",
                    client_id=client.id,
                    rssi=rssi,
                    snr=snr,
                    ssid=client.ssid,
                )

            except Exception as e:
                logger.error(
                    "Failed to fetch signal quality for client",
                    client_id=client.id,
                    network_id=network_id,
                    error=str(e),
                )
                self._track_error(ErrorCategory.API_CLIENT_ERROR)
                # Continue with next client
                continue

        # Record the run so the interval gate can throttle the next cycle (F-060).
        self._last_signal_quality_by_network[network_id] = time.time()

        logger.debug(
            "Completed wireless signal quality collection",
            network_id=network_id,
            wireless_client_count=len(clients_to_query),
        )

    def _update_cache_metrics(self) -> None:
        """Update DNS cache and client store metrics."""
        # Get DNS cache statistics
        dns_stats = self.dns_resolver.get_cache_stats()

        # Update DNS cache metrics
        self.dns_cache_total.set(dns_stats["total_entries"])
        self.dns_cache_valid.set(dns_stats["valid_entries"])
        self.dns_cache_expired.set(dns_stats["expired_entries"])
        # Cache-hit ratio is a point-in-time ratio gauge, not a delta (#319).
        self.dns_cache_hit_ratio.set(dns_stats["cache_hit_ratio"])

        # Update DNS lookup counters (these are cumulative counters)
        # We need to track the difference since last update
        if self._last_dns_stats is not None:
            # Calculate deltas and increment counters
            total_delta = dns_stats["total_lookups"] - self._last_dns_stats["total_lookups"]
            success_delta = (
                dns_stats["successful_lookups"] - self._last_dns_stats["successful_lookups"]
            )
            failed_delta = dns_stats["failed_lookups"] - self._last_dns_stats["failed_lookups"]
            cached_delta = dns_stats["cache_hits"] - self._last_dns_stats["cache_hits"]
            resolution_delta = (
                dns_stats["total_resolution_time"] - self._last_dns_stats["total_resolution_time"]
            )

            # Increment counters by the delta using inc()
            if total_delta > 0:
                self.dns_lookups_total.inc(total_delta)
            if success_delta > 0:
                self.dns_lookups_successful.inc(success_delta)
            if failed_delta > 0:
                self.dns_lookups_failed.inc(failed_delta)
            if cached_delta > 0:
                self.dns_lookups_cached.inc(cached_delta)
            if resolution_delta > 0:
                self.dns_resolution_seconds.inc(resolution_delta)
        else:
            # First run - set initial values by incrementing from 0
            if dns_stats["total_lookups"] > 0:
                self.dns_lookups_total.inc(dns_stats["total_lookups"])
            if dns_stats["successful_lookups"] > 0:
                self.dns_lookups_successful.inc(dns_stats["successful_lookups"])
            if dns_stats["failed_lookups"] > 0:
                self.dns_lookups_failed.inc(dns_stats["failed_lookups"])
            if dns_stats["cache_hits"] > 0:
                self.dns_lookups_cached.inc(dns_stats["cache_hits"])
            if dns_stats["total_resolution_time"] > 0:
                self.dns_resolution_seconds.inc(dns_stats["total_resolution_time"])

        # Store current stats for next update
        self._last_dns_stats = dns_stats.copy()

        # Get client store statistics
        store_stats = self.client_store.get_statistics()

        # Update client store metrics
        self.client_store_total.set(store_stats["total_clients"])
        self.client_store_networks.set(store_stats["total_networks"])

        logger.debug(
            "Updated cache metrics",
            dns_cache_total=dns_stats["total_entries"],
            dns_cache_valid=dns_stats["valid_entries"],
            dns_cache_expired=dns_stats["expired_entries"],
            dns_lookups_total=dns_stats["total_lookups"],
            dns_lookups_successful=dns_stats["successful_lookups"],
            dns_lookups_failed=dns_stats["failed_lookups"],
            dns_lookups_cached=dns_stats["cache_hits"],
            client_store_total=store_stats["total_clients"],
            client_store_networks=store_stats["total_networks"],
        )
