"""Pytest fixtures for large organization testing."""

from __future__ import annotations

import pytest

from ..helpers.large_org_fixture import LargeOrgFixture, LargeOrgScenario


@pytest.fixture
def small_enterprise_fixture() -> LargeOrgFixture:
    """Create a small enterprise fixture (250 devices).

    Returns
    -------
    LargeOrgFixture
        Fixture with 1 org, 10 networks, ~250 devices

    """
    return LargeOrgFixture.from_scenario(LargeOrgScenario.SMALL_ENTERPRISE)


@pytest.fixture
def medium_enterprise_fixture() -> LargeOrgFixture:
    """Create a medium enterprise fixture (1000 devices).

    Returns
    -------
    LargeOrgFixture
        Fixture with 1 org, 25 networks, ~1000 devices

    """
    return LargeOrgFixture.from_scenario(LargeOrgScenario.MEDIUM_ENTERPRISE)


@pytest.fixture
def large_enterprise_fixture() -> LargeOrgFixture:
    """Create a large enterprise fixture (2500 devices).

    Returns
    -------
    LargeOrgFixture
        Fixture with 1 org, 50 networks, ~2500 devices

    """
    return LargeOrgFixture.from_scenario(LargeOrgScenario.LARGE_ENTERPRISE)


@pytest.fixture
def multi_org_small_fixture() -> LargeOrgFixture:
    """Create a multi-org small fixture (1000 devices across 5 orgs).

    Returns
    -------
    LargeOrgFixture
        Fixture with 5 orgs, 10 networks each, ~1000 devices total

    """
    return LargeOrgFixture.from_scenario(LargeOrgScenario.MULTI_ORG_SMALL)


@pytest.fixture
def multi_org_large_fixture() -> LargeOrgFixture:
    """Create a multi-org large fixture (10000 devices across 10 orgs).

    WARNING: This fixture is very large and may take significant time to generate.
    Use sparingly and consider marking tests with @pytest.mark.slow.

    Returns
    -------
    LargeOrgFixture
        Fixture with 10 orgs, 25 networks each, ~10000 devices total

    """
    return LargeOrgFixture.from_scenario(LargeOrgScenario.MULTI_ORG_LARGE)


@pytest.fixture
def custom_large_org() -> type[LargeOrgFixture]:
    """Factory fixture for creating custom large organization fixtures.

    Returns
    -------
    type[LargeOrgFixture]
        LargeOrgFixture class for custom instantiation

    Examples
    --------
    >>> def test_custom(custom_large_org):
    ...     fixture = custom_large_org(
    ...         org_count=3,
    ...         networks_per_org=20,
    ...         devices_per_network=50
    ...     )
    ...     assert fixture.total_devices == 3000

    """
    return LargeOrgFixture
