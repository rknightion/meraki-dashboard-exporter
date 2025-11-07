"""Large organization simulation fixture for performance and scalability testing.

This module provides fixtures for creating realistic large-scale Meraki deployments
with 1000+ devices across multiple networks and organizations.
"""

from __future__ import annotations

import random
from typing import Any

from .factories import DeviceFactory, NetworkFactory, OrganizationFactory


class LargeOrgScenario:
    """Predefined scenarios for large organization testing."""

    SMALL_ENTERPRISE = {
        "name": "Small Enterprise",
        "orgs": 1,
        "networks_per_org": 10,
        "devices_per_network": 25,
        "total_devices": 250,
    }

    MEDIUM_ENTERPRISE = {
        "name": "Medium Enterprise",
        "orgs": 1,
        "networks_per_org": 25,
        "devices_per_network": 40,
        "total_devices": 1000,
    }

    LARGE_ENTERPRISE = {
        "name": "Large Enterprise",
        "orgs": 1,
        "networks_per_org": 50,
        "devices_per_network": 50,
        "total_devices": 2500,
    }

    MULTI_ORG_SMALL = {
        "name": "Multi-Org Small",
        "orgs": 5,
        "networks_per_org": 10,
        "devices_per_network": 20,
        "total_devices": 1000,
    }

    MULTI_ORG_LARGE = {
        "name": "Multi-Org Large",
        "orgs": 10,
        "networks_per_org": 25,
        "devices_per_network": 40,
        "total_devices": 10000,
    }


class LargeOrgFixture:
    """Factory for creating large organization test fixtures.

    This class provides methods to generate realistic large-scale Meraki
    deployments for performance and scalability testing.

    Examples
    --------
    >>> # Create a medium enterprise with 1000 devices
    >>> fixture = LargeOrgFixture.from_scenario(LargeOrgScenario.MEDIUM_ENTERPRISE)
    >>> organizations = fixture.organizations
    >>> devices = fixture.all_devices  # 1000 devices
    >>> networks = fixture.all_networks  # 25 networks

    >>> # Create a custom large deployment
    >>> fixture = LargeOrgFixture(
    ...     org_count=2,
    ...     networks_per_org=50,
    ...     devices_per_network=100
    ... )

    """

    def __init__(
        self,
        org_count: int = 1,
        networks_per_org: int = 25,
        devices_per_network: int = 40,
        device_type_distribution: dict[str, float] | None = None,
    ) -> None:
        """Initialize large organization fixture.

        Parameters
        ----------
        org_count : int, optional
            Number of organizations to create (default: 1)
        networks_per_org : int, optional
            Number of networks per organization (default: 25)
        devices_per_network : int, optional
            Average devices per network (default: 40)
        device_type_distribution : dict[str, float], optional
            Distribution of device types as percentages (default: realistic mix)

        """
        self.org_count = org_count
        self.networks_per_org = networks_per_org
        self.devices_per_network = devices_per_network

        # Default device type distribution (realistic enterprise deployment)
        self.device_type_distribution = device_type_distribution or {
            "MS": 0.40,  # 40% switches
            "MR": 0.35,  # 35% access points
            "MX": 0.10,  # 10% security appliances
            "MT": 0.10,  # 10% sensors
            "MV": 0.03,  # 3% cameras
            "MG": 0.02,  # 2% cellular gateways
        }

        self.organizations: list[dict[str, Any]] = []
        self.networks_by_org: dict[str, list[dict[str, Any]]] = {}
        self.devices_by_network: dict[str, list[dict[str, Any]]] = {}
        self.devices_by_org: dict[str, list[dict[str, Any]]] = {}

        self._generate()

    @classmethod
    def from_scenario(cls, scenario: dict[str, Any]) -> LargeOrgFixture:
        """Create fixture from a predefined scenario.

        Parameters
        ----------
        scenario : dict
            Scenario configuration (e.g., LargeOrgScenario.MEDIUM_ENTERPRISE)

        Returns
        -------
        LargeOrgFixture
            Configured fixture instance

        """
        return cls(
            org_count=scenario["orgs"],
            networks_per_org=scenario["networks_per_org"],
            devices_per_network=scenario["devices_per_network"],
        )

    def _generate(self) -> None:
        """Generate all organizations, networks, and devices."""
        # Generate organizations
        for _ in range(self.org_count):
            org = OrganizationFactory.create()
            self.organizations.append(org)

            # Generate networks for this org
            networks = self._generate_networks_for_org(org["id"])
            self.networks_by_org[org["id"]] = networks

            # Generate devices for each network
            org_devices = []
            for network in networks:
                devices = self._generate_devices_for_network(org["id"], network)
                self.devices_by_network[network["id"]] = devices
                org_devices.extend(devices)

            self.devices_by_org[org["id"]] = org_devices

    def _generate_networks_for_org(self, org_id: str) -> list[dict[str, Any]]:
        """Generate networks for an organization with varied product types."""
        networks = []

        for i in range(self.networks_per_org):
            # Vary product types across networks for realism
            if i % 5 == 0:
                # Some networks are wireless-only
                product_types = ["wireless"]
            elif i % 7 == 0:
                # Some are switch-only
                product_types = ["switch"]
            elif i % 11 == 0:
                # Some have cameras
                product_types = ["wireless", "switch", "camera"]
            elif i % 13 == 0:
                # Some have appliances
                product_types = ["wireless", "switch", "appliance"]
            else:
                # Most have wireless + switch
                product_types = ["wireless", "switch"]

            network = NetworkFactory.create(
                org_id=org_id,
                name=f"Branch-{i + 1:03d}",
                product_types=product_types,
            )
            networks.append(network)

        return networks

    def _generate_devices_for_network(
        self, org_id: str, network: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate devices for a network based on configured distribution."""
        devices = []

        # Add some randomness to device count per network (±20%)
        device_count = int(self.devices_per_network * random.uniform(0.8, 1.2))

        # Determine which device types to create based on network product types
        product_types = network.get("productTypes", ["wireless", "switch"])
        allowed_types = []

        if "wireless" in product_types:
            allowed_types.extend(["MR", "MT"])  # APs and sensors
        if "switch" in product_types:
            allowed_types.append("MS")
        if "appliance" in product_types:
            allowed_types.append("MX")
        if "camera" in product_types:
            allowed_types.append("MV")
        if "cellularGateway" in product_types:
            allowed_types.append("MG")

        # Generate devices according to distribution
        for _ in range(device_count):
            # Select device type based on distribution and allowed types
            device_type = self._select_device_type(allowed_types)

            device = DeviceFactory.create(
                network_id=network["id"],
                device_type=device_type,
            )
            # Add org context
            device["orgId"] = org_id
            device["orgName"] = f"Org-{org_id[:8]}"
            device["networkName"] = network["name"]

            devices.append(device)

        return devices

    def _select_device_type(self, allowed_types: list[str]) -> str:
        """Select a device type based on distribution and allowed types.

        Parameters
        ----------
        allowed_types : list[str]
            Device types allowed in the current network

        Returns
        -------
        str
            Selected device type

        """
        # Filter distribution to only allowed types
        filtered_dist = {
            dt: prob for dt, prob in self.device_type_distribution.items() if dt in allowed_types
        }

        # Normalize probabilities
        total_prob = sum(filtered_dist.values())
        if total_prob == 0:
            # Fallback to first allowed type
            return allowed_types[0] if allowed_types else "MR"

        normalized_dist = {dt: prob / total_prob for dt, prob in filtered_dist.items()}

        # Select based on weighted random choice
        rand_val = random.random()
        cumulative_prob = 0

        for device_type, prob in normalized_dist.items():
            cumulative_prob += prob
            if rand_val <= cumulative_prob:
                return device_type

        # Fallback
        return list(normalized_dist.keys())[0]

    @property
    def all_networks(self) -> list[dict[str, Any]]:
        """Get all networks across all organizations."""
        networks = []
        for net_list in self.networks_by_org.values():
            networks.extend(net_list)
        return networks

    @property
    def all_devices(self) -> list[dict[str, Any]]:
        """Get all devices across all organizations."""
        devices = []
        for dev_list in self.devices_by_org.values():
            devices.extend(dev_list)
        return devices

    @property
    def total_devices(self) -> int:
        """Total number of devices in the fixture."""
        return len(self.all_devices)

    @property
    def total_networks(self) -> int:
        """Total number of networks in the fixture."""
        return len(self.all_networks)

    def get_devices_by_type(self, device_type: str) -> list[dict[str, Any]]:
        """Get all devices of a specific type.

        Parameters
        ----------
        device_type : str
            Device type (MS, MR, MX, etc.)

        Returns
        -------
        list[dict[str, Any]]
            Devices matching the specified type

        """
        return [device for device in self.all_devices if device.get("model", "")[:2] == device_type]

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the generated fixture.

        Returns
        -------
        dict[str, Any]
            Statistics including counts by type and organization

        """
        stats = {
            "total_organizations": len(self.organizations),
            "total_networks": self.total_networks,
            "total_devices": self.total_devices,
            "avg_networks_per_org": self.total_networks / len(self.organizations),
            "avg_devices_per_network": self.total_devices / self.total_networks,
            "devices_by_type": {},
            "devices_per_org": {},
        }

        # Count devices by type
        for device_type in ["MR", "MS", "MX", "MT", "MG", "MV"]:
            count = len(self.get_devices_by_type(device_type))
            if count > 0:
                stats["devices_by_type"][device_type] = count

        # Count devices per org
        for org in self.organizations:
            org_id = org["id"]
            stats["devices_per_org"][org_id] = len(self.devices_by_org[org_id])

        return stats

    def print_summary(self) -> None:
        """Print a summary of the generated fixture."""
        stats = self.get_stats()

        print("\n" + "=" * 60)
        print("Large Organization Fixture Summary")
        print("=" * 60)
        print(f"Organizations: {stats['total_organizations']}")
        print(f"Networks: {stats['total_networks']}")
        print(f"Total Devices: {stats['total_devices']}")
        print(f"\nAvg Networks/Org: {stats['avg_networks_per_org']:.1f}")
        print(f"Avg Devices/Network: {stats['avg_devices_per_network']:.1f}")

        print("\nDevices by Type:")
        for device_type, count in sorted(stats["devices_by_type"].items()):
            percentage = (count / stats["total_devices"]) * 100
            print(f"  {device_type}: {count:4d} ({percentage:5.1f}%)")

        if stats["total_organizations"] > 1:
            print("\nDevices per Organization:")
            for org_id, count in stats["devices_per_org"].items():
                print(f"  {org_id[:12]}: {count:4d} devices")

        print("=" * 60 + "\n")
