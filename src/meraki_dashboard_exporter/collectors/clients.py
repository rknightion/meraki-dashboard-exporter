"""Client metrics collector for network-wide client data."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from ..core.api_helpers import create_api_helper
from ..core.api_models import NetworkClient
from ..core.collector import MetricCollector
from ..core.constants import ClientMetricName, UpdateTier
from ..core.error_handling import ErrorCategory, with_error_handling
from ..core.logging_decorators import log_api_call, log_collection_progress
from ..core.metrics import LabelName
from ..core.registry import register_collector
from ..services.client_store import ClientStore
from ..services.dns_resolver import DNSResolver

logger = structlog.get_logger(__name__)


@register_collector(UpdateTier.MEDIUM)
class ClientsCollector(MetricCollector):
    """Collector for client-level metrics across all networks."""

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
            Keyword arguments passed to parent.

        """
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
        self._last_dns_stats: dict[str, int] | None = None

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
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.CLIENT_ID,
                LabelName.MAC,
                LabelName.DESCRIPTION,
                LabelName.HOSTNAME,
                LabelName.SSID,
            ],
        )

        # Client usage metrics - using Gauge since these are point-in-time measurements
        # that can go up or down (hourly usage windows from API)
        self.client_usage_sent = self._create_gauge(
            ClientMetricName.CLIENT_USAGE_SENT_KB,
            "Kilobytes sent by client in the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.CLIENT_ID,
                LabelName.MAC,
                LabelName.DESCRIPTION,
                LabelName.HOSTNAME,
                LabelName.SSID,
            ],
        )

        self.client_usage_recv = self._create_gauge(
            ClientMetricName.CLIENT_USAGE_RECV_KB,
            "Kilobytes received by client in the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.CLIENT_ID,
                LabelName.MAC,
                LabelName.DESCRIPTION,
                LabelName.HOSTNAME,
                LabelName.SSID,
            ],
        )

        self.client_usage_total = self._create_gauge(
            ClientMetricName.CLIENT_USAGE_TOTAL_KB,
            "Total kilobytes transferred by client in the last hour",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.CLIENT_ID,
                LabelName.MAC,
                LabelName.DESCRIPTION,
                LabelName.HOSTNAME,
                LabelName.SSID,
            ],
        )

        # DNS cache metrics
        self.dns_cache_total = self._create_gauge(
            "meraki_exporter_client_dns_cache_total",
            "Total number of entries in DNS cache",
        )

        self.dns_cache_valid = self._create_gauge(
            "meraki_exporter_client_dns_cache_valid",
            "Number of valid entries in DNS cache",
        )

        self.dns_cache_expired = self._create_gauge(
            "meraki_exporter_client_dns_cache_expired",
            "Number of expired entries in DNS cache",
        )

        self.dns_lookups_total = self._create_counter(
            "meraki_exporter_client_dns_lookups_total",
            "Total number of DNS lookups performed",
        )

        self.dns_lookups_successful = self._create_counter(
            "meraki_exporter_client_dns_lookups_successful_total",
            "Total number of successful DNS lookups",
        )

        self.dns_lookups_failed = self._create_counter(
            "meraki_exporter_client_dns_lookups_failed_total",
            "Total number of failed DNS lookups",
        )

        self.dns_lookups_cached = self._create_counter(
            "meraki_exporter_client_dns_lookups_cached_total",
            "Total number of DNS lookups served from cache",
        )

        # Client store metrics
        self.client_store_total = self._create_gauge(
            "meraki_exporter_client_store_total",
            "Total number of clients in the store",
        )

        self.client_store_networks = self._create_gauge(
            "meraki_exporter_client_store_networks",
            "Total number of networks with clients",
        )

        # Client capability metrics
        self.client_capabilities_count = self._create_gauge(
            ClientMetricName.WIRELESS_CLIENT_CAPABILITIES_COUNT,
            "Count of wireless clients by capability",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.TYPE,  # For the capability type
            ],
        )

        # Client distribution metrics
        self.clients_per_ssid = self._create_gauge(
            ClientMetricName.CLIENTS_PER_SSID_COUNT,
            "Count of clients per SSID",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.SSID,
            ],
        )

        self.clients_per_vlan = self._create_gauge(
            ClientMetricName.CLIENTS_PER_VLAN_COUNT,
            "Count of clients per VLAN",
            labelnames=[
                LabelName.ORG_ID,
                LabelName.ORG_NAME,
                LabelName.NETWORK_ID,
                LabelName.NETWORK_NAME,
                LabelName.VLAN,
            ],
        )

    async def _collect_impl(self) -> None:
        """Collect client metrics from all organizations and networks."""
        if not self._enabled:
            logger.debug("Client collection is disabled, skipping")
            return

        organizations = await self.api_helper.get_organizations()

        if not organizations:
            return

        for org in organizations:
            org_id = org["id"]
            org_name = org["name"]

            # Get all networks for the organization
            networks = await self.api_helper.get_organization_networks(org_id)

            if not networks:
                continue

            # Process networks directly without batching to avoid lambda issues
            # Since we're already processing one org at a time, this is fine
            await self._process_network_batch(org_id, org_name, networks)

        # Update DNS cache and client store metrics after all collections
        self._update_cache_metrics()

    async def _process_network_batch(
        self,
        org_id: str,
        org_name: str,
        networks: list[Any],
    ) -> None:
        """Process a batch of networks for client collection.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        networks : list[Any]
            List of networks to process.

        """
        tasks = []
        for network in networks:
            task = self._collect_network_clients(
                org_id,
                org_name,
                network["id"],
                network["name"],
            )
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

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
    ) -> None:
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
        self._track_api_call("getNetworkClients")
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
            return

        # Parse client data
        clients = [NetworkClient.model_validate(c) for c in clients_data]

        logger.info(
            "Fetched client data",
            org_id=org_id,
            network_id=network_id,
            network_name=network_name,
            client_count=len(clients),
        )

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

            # Common labels
            labels = {
                str(LabelName.ORG_ID): org_id,
                str(LabelName.ORG_NAME): org_name,
                str(LabelName.NETWORK_ID): network_id,
                str(LabelName.NETWORK_NAME): network_name,
                str(LabelName.CLIENT_ID): client.id,
                str(LabelName.MAC): client.mac,
                str(LabelName.DESCRIPTION): sanitized_description,
                str(LabelName.HOSTNAME): sanitized_hostname,
                str(LabelName.SSID): ssid or "Unknown",
            }

            # Set client status
            status_value = 1 if client.status == "Online" else 0
            self.client_status.labels(**labels).set(status_value)

            # Set usage metrics (as gauges - these are point-in-time measurements)
            if client.usage:
                sent_kb = client.usage.get("sent", 0)
                recv_kb = client.usage.get("recv", 0)
                total_kb = client.usage.get("total", 0)

                # Set gauge values
                self.client_usage_sent.labels(**labels).set(float(sent_kb))
                self.client_usage_recv.labels(**labels).set(float(recv_kb))
                self.client_usage_total.labels(**labels).set(float(total_kb))

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
            self.client_capabilities_count.labels(**{
                str(LabelName.ORG_ID): org_id,
                str(LabelName.ORG_NAME): org_name,
                str(LabelName.NETWORK_ID): network_id,
                str(LabelName.NETWORK_NAME): network_name,
                str(LabelName.TYPE): capability,
            }).set(count)
            logger.debug(
                "Set wireless capability count",
                capability=capability,
                count=count,
                network_id=network_id,
            )

        # 2. SSID metrics
        for ssid_name, count in ssid_count.items():
            self.clients_per_ssid.labels(**{
                str(LabelName.ORG_ID): org_id,
                str(LabelName.ORG_NAME): org_name,
                str(LabelName.NETWORK_ID): network_id,
                str(LabelName.NETWORK_NAME): network_name,
                str(LabelName.SSID): ssid_name,
            }).set(count)
            logger.debug(
                "Set SSID client count",
                ssid=ssid_name,
                count=count,
                network_id=network_id,
            )

        # 3. VLAN metrics
        for vlan_id, count in vlan_count.items():
            self.clients_per_vlan.labels(**{
                str(LabelName.ORG_ID): org_id,
                str(LabelName.ORG_NAME): org_name,
                str(LabelName.NETWORK_ID): network_id,
                str(LabelName.NETWORK_NAME): network_name,
                str(LabelName.VLAN): vlan_id,
            }).set(count)
            logger.debug(
                "Set VLAN client count",
                vlan=vlan_id,
                count=count,
                network_id=network_id,
            )

    def _update_cache_metrics(self) -> None:
        """Update DNS cache and client store metrics."""
        # Get DNS cache statistics
        dns_stats = self.dns_resolver.get_cache_stats()

        # Update DNS cache metrics
        self.dns_cache_total.set(dns_stats["total_entries"])
        self.dns_cache_valid.set(dns_stats["valid_entries"])
        self.dns_cache_expired.set(dns_stats["expired_entries"])

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

            # Increment counters by the delta using inc()
            if total_delta > 0:
                self.dns_lookups_total.inc(total_delta)
            if success_delta > 0:
                self.dns_lookups_successful.inc(success_delta)
            if failed_delta > 0:
                self.dns_lookups_failed.inc(failed_delta)
            if cached_delta > 0:
                self.dns_lookups_cached.inc(cached_delta)
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
