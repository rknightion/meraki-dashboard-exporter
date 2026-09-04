"""Regression contracts for the paced Meraki SDK facade."""

from __future__ import annotations

import ast
import importlib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import Counter

from meraki_dashboard_exporter.api.client import AsyncMerakiClient
from meraki_dashboard_exporter.collectors.device import DeviceCollector
from meraki_dashboard_exporter.collectors.network_health import NetworkHealthCollector
from meraki_dashboard_exporter.collectors.organization import OrganizationCollector
from meraki_dashboard_exporter.core.api_facade import (
    FacadeRateLimiterUnavailableError,
    MerakiApiFacade,
    facade_for,
)
from meraki_dashboard_exporter.core.api_helpers import APIHelper
from meraki_dashboard_exporter.core.collector import MetricCollector
from meraki_dashboard_exporter.services.inventory import OrganizationInventory

_SOURCE_ROOT = Path(__file__).parents[2] / "src" / "meraki_dashboard_exporter"
OwnerFamily = Literal[
    "collector",
    "device_subcollector",
    "network_health_subcollector",
    "organization_subcollector",
    "api_helper",
    "inventory",
]
_FACADE_OWNER_FAMILIES: dict[str, OwnerFamily] = {
    "collectors/devices": "device_subcollector",
    "collectors/network_health_collectors": "network_health_subcollector",
    "collectors/organization_collectors": "organization_subcollector",
    "collectors": "collector",
    "core/api_helpers.py": "api_helper",
    "services/inventory.py": "inventory",
}
_FACADE_OWNER_EXCEPTIONS: dict[str, str] = {}


@dataclass(frozen=True, order=True)
class FacadeOwner:
    """One concrete production class passed to ``facade_for(self)``."""

    source_path: str
    class_name: str

    @property
    def key(self) -> str:
        """Stable source identifier for diagnostics and exemptions."""
        return f"{self.source_path}:{self.class_name}"


class _FacadeOwnerVisitor(ast.NodeVisitor):
    """Collect enclosing classes that use ``facade_for(self)``."""

    def __init__(self) -> None:
        self.class_name: str | None = None
        self.owners: set[str] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track the class owning calls in its body."""
        previous_class_name = self.class_name
        self.class_name = node.name
        self.generic_visit(node)
        self.class_name = previous_class_name

    def visit_Call(self, node: ast.Call) -> None:
        """Record direct facade-owner calls and continue walking nested calls."""
        if self.class_name is not None and _is_facade_for_self(node):
            self.owners.add(self.class_name)
        self.generic_visit(node)


def _is_facade_for_self(node: ast.Call) -> bool:
    """Whether a call constructs a facade directly from the current owner."""
    if not isinstance(node.func, ast.Name) or node.func.id != "facade_for":
        return False
    if len(node.args) != 1 or not isinstance(node.args[0], ast.Name):
        return False
    return node.args[0].id == "self"


def _facade_owner_inventory() -> tuple[FacadeOwner, ...]:
    """Discover every production class that delegates through ``facade_for(self)``."""
    owners: set[FacadeOwner] = set()
    for path in _SOURCE_ROOT.rglob("*.py"):
        visitor = _FacadeOwnerVisitor()
        visitor.visit(ast.parse(path.read_text(), filename=str(path)))
        relative_path = str(path.relative_to(_SOURCE_ROOT))
        owners.update(FacadeOwner(relative_path, class_name) for class_name in visitor.owners)
    return tuple(sorted(owners))


def _owner_family(owner: FacadeOwner) -> OwnerFamily | None:
    """Return the concrete ownership construction family for an inventoried owner."""
    for path_prefix, family in _FACADE_OWNER_FAMILIES.items():
        if owner.source_path == path_prefix or owner.source_path.startswith(f"{path_prefix}/"):
            return family
    return None


def _owner_class(owner: FacadeOwner) -> type[object]:
    """Load the production class declared by one inventory record."""
    module_name = ".".join((
        "meraki_dashboard_exporter",
        *Path(owner.source_path).with_suffix("").parts,
    ))
    module = importlib.import_module(module_name)
    return cast("type[object]", getattr(module, owner.class_name))


def _blank_instance(owner_type: type[object]) -> object:
    """Create a concrete owner without its unrelated metric/API setup."""
    try:
        return object.__new__(owner_type)
    except TypeError:
        concrete_owner_type = type(
            f"FacadeLimiter{owner_type.__name__}",
            (owner_type,),
            {"collect": lambda self: None},
        )
        return object.__new__(concrete_owner_type)


def _construct_owner_with_limiter(owner: FacadeOwner, limiter: object) -> object:
    """Build the production owner-family chain used by ``facade_for``."""
    owner_instance = _blank_instance(_owner_class(owner))
    family = _owner_family(owner)
    assert family is not None, f"No construction family registered for {owner.key}"

    if family == "collector":
        assert isinstance(owner_instance, MetricCollector)
        owner_instance.rate_limiter = limiter
    elif family == "inventory":
        assert isinstance(owner_instance, OrganizationInventory)
        owner_instance.rate_limiter = limiter
    elif family == "api_helper":
        assert isinstance(owner_instance, APIHelper)
        collector = _blank_instance(DeviceCollector)
        collector.rate_limiter = limiter
        owner_instance.collector = collector
    else:
        parent_types: dict[OwnerFamily, type[object]] = {
            "device_subcollector": DeviceCollector,
            "network_health_subcollector": NetworkHealthCollector,
            "organization_subcollector": OrganizationCollector,
        }
        parent = _blank_instance(parent_types[family])
        parent.rate_limiter = limiter
        owner_instance.parent = parent

    return owner_instance


@pytest.fixture
def metric_facade(monkeypatch: pytest.MonkeyPatch) -> MerakiApiFacade:
    """Provide isolated facade counters for each metric-contract test."""
    attempts = Counter("test_facade_attempts", "test", ["operation", "status"])
    requests = Counter("test_facade_requests", "test", ["endpoint", "method", "status_code"])
    retries = Counter("test_facade_retries", "test", ["endpoint", "retry_reason"])
    monkeypatch.setattr(MerakiApiFacade, "_attempts_total", attempts)
    monkeypatch.setattr(MerakiApiFacade, "_requests_total", requests)
    monkeypatch.setattr(AsyncMerakiClient, "_api_retry_attempts", retries)
    return MerakiApiFacade(
        settings=SimpleNamespace(
            api=SimpleNamespace(
                max_retries=1,
                per_fetch_deadline_seconds=30,
                retry_after_max_seconds=7,
            )
        ),
        rate_limiter=SimpleNamespace(
            acquire=AsyncMock(return_value=0.0),
            record_throttle_event=MagicMock(),
        ),
    )


@pytest.mark.asyncio
async def test_facade_paces_explicit_org_without_forwarding_it_to_sdk(
    metric_facade: MerakiApiFacade,
) -> None:
    """The pacing key is explicit facade metadata, not an SDK keyword argument."""
    sdk_call = MagicMock(return_value=[])

    assert (
        await metric_facade.call(
            "getNetworkSwitchLinkAggregations",
            sdk_call,
            "network-id",
            org_id="org-id",
        )
        == []
    )

    limiter = metric_facade._rate_limiter
    limiter.acquire.assert_awaited_once_with("org-id", "getNetworkSwitchLinkAggregations")
    sdk_call.assert_called_once_with("network-id")
    requests = MerakiApiFacade._requests_total
    assert requests is not None
    assert (
        requests.labels(
            endpoint="getNetworkSwitchLinkAggregations", method="GET", status_code="200"
        )._value.get()
        == 1
    )


@pytest.mark.asyncio
async def test_network_identifier_is_never_inferred_as_an_organization(
    metric_facade: MerakiApiFacade,
) -> None:
    """Network-shaped strings must not select an organization limiter bucket."""
    sdk_call = MagicMock(return_value=[])
    network_id = "N_1234567890123456"

    await metric_facade.call("getNetworkSwitchStp", sdk_call, network_id)

    limiter = metric_facade._rate_limiter
    limiter.acquire.assert_awaited_once_with(None, "getNetworkSwitchStp")


@pytest.mark.asyncio
@pytest.mark.strict_facade_limiter
async def test_unresolved_limiter_fails_before_an_unpaced_sdk_call() -> None:
    """A broken owner tree must fail closed instead of silently bypassing pacing."""
    sdk_call = MagicMock(return_value=[])
    facade = MerakiApiFacade(settings=SimpleNamespace(api=SimpleNamespace()), rate_limiter=None)

    with pytest.raises(FacadeRateLimiterUnavailableError):
        await facade.call("getOrganizations", sdk_call)

    sdk_call.assert_not_called()


@pytest.mark.asyncio
async def test_facade_for_resolves_parent_tree_limiter() -> None:
    """Sub-collector facade owners inherit the coordinator's configured limiter."""
    limiter = SimpleNamespace(
        acquire=AsyncMock(return_value=0.0), record_throttle_event=MagicMock()
    )
    owner = SimpleNamespace(parent=SimpleNamespace(parent=SimpleNamespace(rate_limiter=limiter)))
    sdk_call = MagicMock(return_value=[])

    await facade_for(owner).call("getOrganizationDevices", sdk_call, "org-id")

    limiter.acquire.assert_awaited_once_with("org-id", "getOrganizationDevices")


def test_production_facade_owner_inventory_is_complete() -> None:
    """Every production ``facade_for`` owner has an explicit construction family."""
    owners = _facade_owner_inventory()
    unclassified = [owner.key for owner in owners if _owner_family(owner) is None]
    unexpected_exceptions = set(_FACADE_OWNER_EXCEPTIONS) - {owner.key for owner in owners}

    assert owners
    assert unclassified == []
    assert unexpected_exceptions == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", _facade_owner_inventory(), ids=lambda owner: owner.key)
async def test_every_production_facade_owner_resolves_a_limiter_before_call(
    owner: FacadeOwner,
) -> None:
    """Every non-exempt production owner reaches a limiter before the SDK seam."""
    if reason := _FACADE_OWNER_EXCEPTIONS.get(owner.key):
        pytest.skip(reason)

    limiter = SimpleNamespace(
        acquire=AsyncMock(return_value=0.0), record_throttle_event=MagicMock()
    )
    sdk_call = MagicMock(return_value=[])
    facade = facade_for(_construct_owner_with_limiter(owner, limiter))

    assert facade._rate_limiter is limiter
    assert await facade.call("getOrganizations", sdk_call) == []
    limiter.acquire.assert_awaited_once_with(None, "getOrganizations")
    sdk_call.assert_called_once_with()


@pytest.mark.asyncio
async def test_facade_retry_records_one_compatibility_retry_and_honors_capped_retry_after(
    monkeypatch: pytest.MonkeyPatch, metric_facade: MerakiApiFacade
) -> None:
    """One 429 retry makes one counter increment and one jittered capped wait."""

    class RateLimitedError(Exception):
        status = 429
        retry_after = 99

    sdk_call = MagicMock(side_effect=[RateLimitedError(), []])
    sleep = AsyncMock()
    monkeypatch.setattr("meraki_dashboard_exporter.core.api_facade.asyncio.sleep", sleep)
    monkeypatch.setattr(
        "meraki_dashboard_exporter.core.api_facade._apply_jitter", lambda delay, _: delay
    )

    assert await metric_facade.call("getOrganizationDevices", sdk_call, "org-id") == []

    retries = AsyncMerakiClient._api_retry_attempts
    assert retries is not None
    assert (
        retries.labels(
            endpoint="getOrganizationDevices", retry_reason="http_429_rate_limit"
        )._value.get()
        == 1
    )
    metric_facade._rate_limiter.record_throttle_event.assert_called_once_with("org-id", 7.0)
    sleep.assert_awaited_once_with(7.0)


@pytest.mark.asyncio
async def test_facade_retry_uses_the_documented_ten_second_jittered_base(
    monkeypatch: pytest.MonkeyPatch, metric_facade: MerakiApiFacade
) -> None:
    """Absent Retry-After starts the facade's exponential sequence at ten seconds."""

    class RateLimitedError(Exception):
        status = 429

    sdk_call = MagicMock(side_effect=[RateLimitedError(), []])
    sleep = AsyncMock()
    monkeypatch.setattr("meraki_dashboard_exporter.core.api_facade.asyncio.sleep", sleep)
    monkeypatch.setattr(
        "meraki_dashboard_exporter.core.api_facade._apply_jitter", lambda delay, _: delay
    )

    assert await metric_facade.call("getOrganizationDevices", sdk_call, "org-id") == []

    sleep.assert_awaited_once_with(10.0)


@pytest.mark.asyncio
async def test_non_http_exception_is_an_attempt_outcome_not_an_http_status(
    metric_facade: MerakiApiFacade,
) -> None:
    """The compatibility HTTP counter never contains exception-class label values."""
    sdk_call = MagicMock(side_effect=RuntimeError("socket closed"))

    with pytest.raises(RuntimeError, match="socket closed"):
        await metric_facade.call("getOrganizationDevices", sdk_call, "org-id")

    attempts = MerakiApiFacade._attempts_total
    requests = MerakiApiFacade._requests_total
    assert attempts is not None
    assert requests is not None
    assert attempts.labels(operation="getOrganizationDevices", status="exception")._value.get() == 1
    assert requests.collect()[0].samples == []
