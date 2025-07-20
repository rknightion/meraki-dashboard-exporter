"""Client data store for managing client information."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import structlog

from ..core.api_models import NetworkClient
from ..core.config import Settings
from ..core.domain_models import ClientData

logger = structlog.get_logger(__name__)


class ClientStore:
    """In-memory store for client data with TTL support."""

    def __init__(self, settings: Settings):
        """Initialize client store.

        Parameters
        ----------
        settings : Settings
            Application settings.

        """
        self.settings = settings
        self.cache_ttl = settings.clients.cache_ttl
        self.max_clients_per_network = settings.clients.max_clients_per_network

        # Store clients by network ID
        self._clients: dict[str, dict[str, ClientData]] = {}

        # Track last update time per network
        self._last_update: dict[str, float] = {}

        # Track network names for display
        self._network_names: dict[str, str] = {}

        # Track organization IDs for networks
        self._network_orgs: dict[str, str] = {}

    def update_clients(
        self,
        network_id: str,
        clients: list[NetworkClient],
        network_name: str | None = None,
        org_id: str | None = None,
        hostnames: dict[str, str | None] | None = None,
    ) -> None:
        """Update clients for a network.

        Parameters
        ----------
        network_id : str
            Network ID.
        clients : list[NetworkClient]
            List of client data from API.
        network_name : str | None
            Network name for display.
        org_id : str | None
            Organization ID.
        hostnames : dict[str, str | None] | None
            Resolved hostnames by IP address.

        """
        if network_name:
            self._network_names[network_id] = network_name
        if org_id:
            self._network_orgs[network_id] = org_id

        # Initialize network store if needed
        if network_id not in self._clients:
            self._clients[network_id] = {}

        network_clients = self._clients[network_id]
        updated_count = 0
        new_count = 0

        # Limit number of clients per network
        clients_to_process = clients[: self.max_clients_per_network]
        if len(clients) > self.max_clients_per_network:
            logger.warning(
                "Client limit exceeded for network",
                network_id=network_id,
                network_name=network_name,
                total_clients=len(clients),
                limit=self.max_clients_per_network,
            )

        # Process each client
        for client in clients_to_process:
            client_id = client.id

            # Get hostname from resolved list
            hostname = None
            if hostnames and client.ip:
                hostname = hostnames.get(client.ip)

            # Calculate the hostname that will be used in metrics
            # This follows the same logic as ClientsCollector._determine_hostname
            calculated_hostname = hostname or client.description or client.ip or "unknown"

            # Create or update client data
            if client_id in network_clients:
                # Update existing client
                existing = network_clients[client_id]
                existing.ip = client.ip
                existing.ip6 = client.ip6
                existing.ip6Local = client.ip6Local
                existing.user = client.user
                existing.hostname = hostname or existing.hostname
                existing.calculatedHostname = calculated_hostname
                existing.lastSeen = client.lastSeen
                existing.status = client.status
                existing.usage = client.usage
                existing.ssid = client.ssid
                existing.vlan = client.vlan
                existing.switchport = client.switchport
                existing.deviceTypePrediction = client.deviceTypePrediction
                existing.recentDeviceSerial = client.recentDeviceSerial
                existing.recentDeviceName = client.recentDeviceName
                existing.recentDeviceMac = client.recentDeviceMac
                existing.recentDeviceConnection = client.recentDeviceConnection
                existing.notes = client.notes
                existing.groupPolicy8021x = client.groupPolicy8021x
                existing.adaptivePolicyGroup = client.adaptivePolicyGroup
                existing.smInstalled = client.smInstalled
                existing.namedVlan = client.namedVlan
                existing.pskGroup = client.pskGroup
                existing.wirelessCapabilities = client.wirelessCapabilities
                updated_count += 1
            else:
                # Add new client
                network_clients[client_id] = ClientData(
                    id=client.id,
                    mac=client.mac,
                    description=client.description,
                    hostname=hostname,
                    calculatedHostname=calculated_hostname,
                    ip=client.ip,
                    ip6=client.ip6,
                    ip6Local=client.ip6Local,
                    user=client.user,
                    firstSeen=client.firstSeen,
                    lastSeen=client.lastSeen,
                    manufacturer=client.manufacturer,
                    os=client.os,
                    deviceTypePrediction=client.deviceTypePrediction,
                    recentDeviceSerial=client.recentDeviceSerial,
                    recentDeviceName=client.recentDeviceName,
                    recentDeviceMac=client.recentDeviceMac,
                    recentDeviceConnection=client.recentDeviceConnection,
                    ssid=client.ssid,
                    vlan=client.vlan,
                    switchport=client.switchport,
                    status=client.status,
                    usage=client.usage,
                    notes=client.notes,
                    groupPolicy8021x=client.groupPolicy8021x,
                    adaptivePolicyGroup=client.adaptivePolicyGroup,
                    smInstalled=client.smInstalled,
                    namedVlan=client.namedVlan,
                    pskGroup=client.pskGroup,
                    wirelessCapabilities=client.wirelessCapabilities,
                    networkId=network_id,
                    networkName=network_name,
                    organizationId=org_id,
                )
                new_count += 1

        # Update timestamp
        self._last_update[network_id] = time.time()

        logger.info(
            "Updated client data",
            network_id=network_id,
            network_name=network_name,
            new_clients=new_count,
            updated_clients=updated_count,
            total_clients=len(network_clients),
        )

    def get_client(self, network_id: str, client_id: str) -> ClientData | None:
        """Get a specific client.

        Parameters
        ----------
        network_id : str
            Network ID.
        client_id : str
            Client ID.

        Returns
        -------
        ClientData | None
            Client data or None if not found.

        """
        if network_id not in self._clients:
            return None

        return self._clients[network_id].get(client_id)

    def get_network_clients(self, network_id: str) -> list[ClientData]:
        """Get all clients for a network.

        Parameters
        ----------
        network_id : str
            Network ID.

        Returns
        -------
        list[ClientData]
            List of clients for the network.

        """
        if network_id not in self._clients:
            return []

        return list(self._clients[network_id].values())

    def get_all_clients(self) -> list[ClientData]:
        """Get all clients across all networks.

        Returns
        -------
        list[ClientData]
            List of all clients.

        """
        clients: list[ClientData] = []
        for network_clients in self._clients.values():
            clients.extend(network_clients.values())
        return clients

    def get_client_by_mac(self, mac: str) -> ClientData | None:
        """Find a client by MAC address.

        Parameters
        ----------
        mac : str
            MAC address to search for.

        Returns
        -------
        ClientData | None
            Client data or None if not found.

        """
        mac_lower = mac.lower()
        for network_clients in self._clients.values():
            for client in network_clients.values():
                if client.mac.lower() == mac_lower:
                    return client
        return None

    def get_clients_by_ip(self, ip: str) -> list[ClientData]:
        """Find clients by IP address.

        Parameters
        ----------
        ip : str
            IP address to search for.

        Returns
        -------
        list[ClientData]
            List of clients with this IP.

        """
        clients: list[ClientData] = []
        for network_clients in self._clients.values():
            for client in network_clients.values():
                if client.ip == ip:
                    clients.append(client)
        return clients

    def is_network_stale(self, network_id: str) -> bool:
        """Check if network data is stale.

        Parameters
        ----------
        network_id : str
            Network ID to check.

        Returns
        -------
        bool
            True if data is stale or missing.

        """
        if network_id not in self._last_update:
            return True

        age = time.time() - self._last_update[network_id]
        return age > self.cache_ttl

    def get_network_names(self) -> dict[str, str]:
        """Get all known network names.

        Returns
        -------
        dict[str, str]
            Mapping of network ID to name.

        """
        return self._network_names.copy()

    def get_statistics(self) -> dict[str, Any]:
        """Get store statistics.

        Returns
        -------
        dict[str, Any]
            Store statistics.

        """
        total_clients = sum(len(clients) for clients in self._clients.values())
        online_clients = sum(
            1
            for clients in self._clients.values()
            for client in clients.values()
            if client.status == "Online"
        )

        return {
            "total_networks": len(self._clients),
            "total_clients": total_clients,
            "online_clients": online_clients,
            "offline_clients": total_clients - online_clients,
            "networks": {
                network_id: {
                    "name": self._network_names.get(network_id, "Unknown"),
                    "client_count": len(clients),
                    "last_update": datetime.fromtimestamp(
                        self._last_update.get(network_id, 0)
                    ).isoformat(),
                    "is_stale": self.is_network_stale(network_id),
                }
                for network_id, clients in self._clients.items()
            },
        }

    def clear(self) -> None:
        """Clear all stored data."""
        self._clients.clear()
        self._last_update.clear()
        self._network_names.clear()
        self._network_orgs.clear()
        logger.info("Client store cleared")

    def cleanup_stale_networks(self) -> int:
        """Remove data for stale networks.

        Returns
        -------
        int
            Number of networks cleaned up.

        """
        stale_networks = [
            network_id for network_id in self._clients if self.is_network_stale(network_id)
        ]

        for network_id in stale_networks:
            del self._clients[network_id]
            del self._last_update[network_id]
            logger.info(
                "Removed stale network data",
                network_id=network_id,
                network_name=self._network_names.get(network_id),
            )

        return len(stale_networks)
