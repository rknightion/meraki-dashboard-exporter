"""Golden /metrics exposition regression net, per device family (#594).

This is a *contract* test. For each metric family (MR, MS, MX, MG, MV, MT,
device-common, org, network-health, clients) it drives the family's real
coordinator collector(s) through the shared test factories + ``MockAPIBuilder``,
renders the resulting Prometheus exposition, normalizes out everything volatile
(sample **values**, timestamps, ``_created`` series, histogram bucket ``le``
boundaries) and compares the surviving *shape* against a checked-in golden
snapshot under ``tests/unit/golden/metrics/<family>.txt``.

What the golden pins (and therefore what a regression trips on):

- the **metric name** (units live in the name by Prometheus convention, so a
  ``_bytes`` -> ``_kb`` or ``_percent`` -> ``_ratio`` rename is caught),
- the **TYPE** line (gauge / counter / histogram / info),
- the **HELP** string, and
- the **label KEY SET** of every series (label *keys*, never the volatile label
  *values* like serials/IPs). For ``info`` series this includes the payload
  keys, so dropping/renaming an info label is caught too.

The contract is derived from the metrics the collectors actually *register*
(construction registers every declared metric regardless of data) unioned with
any label key-sets observed in emitted samples, so it is deterministic and does
not depend on every downstream API endpoint being mocked.

Regenerating the goldens
------------------------
After an *intentional* metric-contract change, regenerate and eyeball the diff::

    UPDATE_METRICS_GOLDENS=1 uv run pytest tests/unit/test_golden_metrics_exposition.py

Then re-run without the env var to confirm green, and commit the updated
``tests/unit/golden/metrics/*.txt`` alongside the code change. The goldens here
reflect the post-#531/#533/#517/#527/#530 v1 metric contract.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest import mock

import pytest
from prometheus_client import REGISTRY as GLOBAL_REGISTRY
from prometheus_client import CollectorRegistry

from meraki_dashboard_exporter.core import collector as collector_mod
from meraki_dashboard_exporter.core.collector import MetricCollector
from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.services.inventory import OrganizationInventory
from tests.helpers.factories import (
    DeviceFactory,
    DeviceStatusFactory,
    NetworkFactory,
    OrganizationFactory,
)
from tests.helpers.mock_api import MockAPIBuilder

GOLDEN_DIR = Path(__file__).parent / "golden" / "metrics"
UPDATE_ENV = "UPDATE_METRICS_GOLDENS"

# Metrics owned by the exporter's own instrumentation / other subsystems, not by
# the data collectors under test. Excluded from every family golden so infra
# churn does not bleed into the per-family contracts.
_EXCLUDE_PREFIXES = ("meraki_exporter_", "meraki_webhook_")

# Ordered prefix -> family split for the DeviceCollector registry. Anything that
# does not match a device-type prefix falls through to "device_common".
_DEVICE_SPLIT: tuple[tuple[str, str], ...] = (
    ("mr", "meraki_mr_"),
    ("ms", "meraki_ms_"),
    ("mx", "meraki_mx_"),
    ("mg", "meraki_mg_"),
    ("mv", "meraki_mv_"),
    ("mt", "meraki_mt_"),
)

ALL_FAMILIES = [
    "mr",
    "ms",
    "mx",
    "mg",
    "mv",
    "mt",
    "device_common",
    "network_health",
    "org",
    "clients",
]


# --------------------------------------------------------------------------- #
# Contract extraction helpers
# --------------------------------------------------------------------------- #


def _extract_contract(
    registry: CollectorRegistry,
) -> dict[str, tuple[str, str, set[tuple[str, ...]]]]:
    """Extract ``name -> (type, help, {label-key-tuples})`` from a registry.

    Label key-sets come from two sources unioned together:

    - the metric's *declared* label names (present even when no sample was
      emitted), and
    - the label keys of any emitted samples (this is what surfaces ``info``
      payload keys, which are not part of the declared label names).

    Volatile sample artifacts are normalized away: the histogram bucket ``le``
    label is dropped, and ``_created`` bookkeeping series are ignored.
    """
    contracts: dict[str, tuple[str, str, set[tuple[str, ...]]]] = {}

    for coll in list(registry._collector_to_names):
        name = getattr(coll, "_name", None)
        if not name:
            continue
        mtype = getattr(coll, "_type", "unknown")
        documentation = getattr(coll, "_documentation", "")
        declared = tuple(sorted(getattr(coll, "_labelnames", ()) or ()))

        keysets: set[tuple[str, ...]] = {declared}
        try:
            for metric in coll.collect():
                for sample in metric.samples:
                    if sample.name.endswith("_created"):
                        continue
                    keys = tuple(sorted(k for k in sample.labels.keys() if k != "le"))
                    keysets.add(keys)
        except Exception:
            # Best-effort: a collector that cannot snapshot still contributes
            # its declared shape above.
            pass

        if name in contracts:
            # Merge duplicate registrations (e.g. an MT metric declared by both
            # the device MT sub-collector and the standalone sensor collector).
            _mtype, _doc, existing = contracts[name]
            existing |= keysets
        else:
            contracts[name] = (mtype, documentation, keysets)

    return contracts


def _render_family(family: str, contracts: dict[str, tuple[str, str, set[tuple[str, ...]]]]) -> str:
    """Render the deterministic golden text for one family."""
    lines: list[str] = [
        f"# golden metrics exposition contract: family={family}",
        "# fields: NAME / TYPE / HELP / LABELS (label KEY sets, values normalized out)",
        "",
    ]
    for name in sorted(contracts):
        mtype, documentation, keysets = contracts[name]
        lines.append(f"{name} {mtype}")
        lines.append(f"  help: {documentation}")
        for keyset in sorted(keysets):
            lines.append(f"  labels: {','.join(keyset)}")
    return "\n".join(lines).rstrip() + "\n"


def _select(
    contracts: dict[str, tuple[str, str, set[tuple[str, ...]]]],
    predicate,
) -> dict[str, tuple[str, str, set[tuple[str, ...]]]]:
    return {name: v for name, v in contracts.items() if predicate(name)}


def _included(name: str) -> bool:
    return not name.startswith(_EXCLUDE_PREFIXES)


# --------------------------------------------------------------------------- #
# Data + coordinator driving
# --------------------------------------------------------------------------- #

_ORG_ID = "123456"


def _representative_api() -> MockAPIBuilder:
    """A modest, family-agnostic dataset that exercises the common code paths.

    The golden is contract-based (declared metrics are captured on construction
    regardless of data), so this only needs to be *valid* enough to let the
    coordinators run without exploding; unmocked endpoints degrade gracefully
    through the collectors' own error handling.
    """
    org = OrganizationFactory.create(org_id=_ORG_ID, name="Golden Org")
    networks = [
        NetworkFactory.create(
            network_id="N_1",
            name="Golden Net 1",
            org_id=_ORG_ID,
            product_types=[
                "wireless",
                "switch",
                "appliance",
                "sensor",
                "cellularGateway",
                "camera",
            ],
        )
    ]
    devices = [
        DeviceFactory.create_mr(serial="Q2MR-0000-0001", network_id="N_1"),
        DeviceFactory.create_ms(serial="Q2MS-0000-0001", network_id="N_1"),
        DeviceFactory.create_mx(serial="Q2MX-0000-0001", network_id="N_1"),
        DeviceFactory.create_mt(serial="Q2MT-0000-0001", network_id="N_1"),
        DeviceFactory.create(
            serial="Q2MG-0000-0001", device_type="MG", model="MG21", network_id="N_1"
        ),
        DeviceFactory.create(
            serial="Q2MV-0000-0001", device_type="MV", model="MV12", network_id="N_1"
        ),
    ]
    statuses = [DeviceStatusFactory.create_availability(serial=d["serial"]) for d in devices]

    return (
        MockAPIBuilder()
        .with_organizations([org])
        .with_networks(networks, org_id=_ORG_ID)
        .with_devices(devices, org_id=_ORG_ID)
        .with_device_statuses(statuses, org_id=_ORG_ID)
    )


def _run_coordinator(coordinator_cls, settings: Settings, **extra):
    """Construct a coordinator in an isolated registry and best-effort run it.

    Construction alone registers every declared metric; the collect() run
    additionally exercises emission (surfacing e.g. info-payload label keys).
    The run is wrapped so partial/failed collection never breaks the contract.
    """
    api = _representative_api().build()
    registry = CollectorRegistry()

    # OrganizationInventory registers a couple of gauges into the *global*
    # default registry (no registry kwarg), so snapshot it and unregister
    # anything this build adds, keeping sequential builds collision-free. Those
    # inventory/network-filter metrics are not part of any family golden.
    global_before = set(GLOBAL_REGISTRY._collector_to_names)

    # Route the base class's performance metrics into this isolated registry and
    # force re-initialization so builds don't collide on the global REGISTRY.
    with mock.patch.object(collector_mod, "REGISTRY", registry):
        MetricCollector._metrics_initialized = False
        MetricCollector._collector_duration = None
        MetricCollector._collector_errors = None
        MetricCollector._collector_last_success = None
        MetricCollector._collector_api_calls = None

        try:
            inventory = OrganizationInventory(api, settings)
            inst = coordinator_cls(
                api=api,
                settings=settings,
                registry=registry,
                inventory=inventory,
                **extra,
            )
            # Keep helper services pointed at the mock API (mirrors BaseCollectorTest).
            if getattr(inst, "inventory", None) is not None:
                inst.inventory.api = api
            if hasattr(inst, "_sync_subcollector_api"):
                inst._sync_subcollector_api()

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(asyncio.wait_for(inst.collect(), timeout=60))
            except Exception:
                pass
            finally:
                loop.close()
        finally:
            for coll in list(GLOBAL_REGISTRY._collector_to_names):
                if coll not in global_before:
                    GLOBAL_REGISTRY.unregister(coll)

    return registry


def _fast_env() -> None:
    """Mirror conftest.fast_test_settings.

    That fixture is function-scoped and has not run yet when this module-scoped
    fixture builds the contract, so replicate its knobs (no smoothing, no retry
    sleeps, no client-side rate limiting) to keep the build fast.
    """
    os.environ.setdefault("MERAKI_EXPORTER_MERAKI__API_KEY", "a" * 40)
    os.environ["MERAKI_EXPORTER_API__SMOOTHING_ENABLED"] = "false"
    os.environ["MERAKI_EXPORTER_API__MAX_RETRIES"] = "0"
    os.environ["MERAKI_EXPORTER_API__RATE_LIMIT_ENABLED"] = "false"


def _base_settings() -> Settings:
    _fast_env()
    return Settings()


def _clients_settings() -> Settings:
    _fast_env()
    prev = os.environ.get("MERAKI_EXPORTER_CLIENTS__ENABLED")
    os.environ["MERAKI_EXPORTER_CLIENTS__ENABLED"] = "true"
    try:
        return Settings()
    finally:
        if prev is None:
            os.environ.pop("MERAKI_EXPORTER_CLIENTS__ENABLED", None)
        else:
            os.environ["MERAKI_EXPORTER_CLIENTS__ENABLED"] = prev


def _build_all_families() -> dict[str, dict[str, tuple[str, str, set[tuple[str, ...]]]]]:
    """Drive every coordinator once and partition into per-family contracts."""
    # Imported lazily so registration side effects are contained to this call.
    from meraki_dashboard_exporter.collectors.clients import ClientsCollector
    from meraki_dashboard_exporter.collectors.device import DeviceCollector
    from meraki_dashboard_exporter.collectors.mt_sensor import MTSensorCollector
    from meraki_dashboard_exporter.collectors.network_health import NetworkHealthCollector
    from meraki_dashboard_exporter.collectors.organization import OrganizationCollector

    base = _base_settings()

    device_contract = _select(_extract_contract(_run_coordinator(DeviceCollector, base)), _included)
    mt_contract = _select(_extract_contract(_run_coordinator(MTSensorCollector, base)), _included)
    nh_contract = _select(
        _extract_contract(_run_coordinator(NetworkHealthCollector, base)), _included
    )
    org_contract = _select(
        _extract_contract(_run_coordinator(OrganizationCollector, base)), _included
    )
    clients_contract = _select(
        _extract_contract(_run_coordinator(ClientsCollector, _clients_settings())), _included
    )

    families: dict[str, dict[str, tuple[str, str, set[tuple[str, ...]]]]] = {
        fam: {} for fam in ALL_FAMILIES
    }

    # Partition the DeviceCollector registry by metric-name prefix.
    for name, value in device_contract.items():
        for fam, prefix in _DEVICE_SPLIT:
            if name.startswith(prefix):
                families[fam][name] = value
                break
        else:
            families["device_common"][name] = value

    # MT sensor metrics fold into the mt family (union with any device-side mt_).
    for name, value in mt_contract.items():
        if name in families["mt"]:
            _t, _d, keysets = families["mt"][name]
            keysets |= value[2]
        else:
            families["mt"][name] = value

    families["network_health"] = nh_contract
    families["org"] = org_contract
    families["clients"] = clients_contract

    return families


@pytest.fixture(scope="module")
def all_families() -> dict[str, dict[str, tuple[str, str, set[tuple[str, ...]]]]]:
    """Build the per-family metric contracts once for the whole module."""
    return _build_all_families()


# --------------------------------------------------------------------------- #
# The regression net
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("family", ALL_FAMILIES)
def test_golden_metrics_exposition(family: str, all_families) -> None:
    """Each family's rendered metric contract must match its checked-in golden."""
    rendered = _render_family(family, all_families[family])
    golden_path = GOLDEN_DIR / f"{family}.txt"

    if os.environ.get(UPDATE_ENV):
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(rendered)
        pytest.skip(f"Regenerated golden for family={family} ({UPDATE_ENV} set)")

    assert golden_path.exists(), (
        f"Missing golden for family={family}. Regenerate with "
        f"{UPDATE_ENV}=1 uv run pytest {Path(__file__).name}"
    )

    expected = golden_path.read_text()
    assert rendered == expected, (
        f"Metric exposition contract drift for family={family}.\n"
        f"If this change to metric names / TYPE / HELP / label keys is intentional, "
        f"regenerate with {UPDATE_ENV}=1 and review the diff before committing.\n"
    )


def test_every_family_declares_metrics(all_families) -> None:
    """Guard against a family silently collecting nothing (broken driving)."""
    empty = [fam for fam in ALL_FAMILIES if not all_families[fam]]
    assert not empty, f"Families produced no metrics (setup regression?): {empty}"


def test_no_family_prefix_leaks(all_families) -> None:
    """Device-type metrics must not leak into device_common (partition sanity)."""
    leaked = [
        name
        for name in all_families["device_common"]
        if any(name.startswith(prefix) for _fam, prefix in _DEVICE_SPLIT)
    ]
    assert not leaked, f"device-type metrics mis-filed under device_common: {leaked}"
