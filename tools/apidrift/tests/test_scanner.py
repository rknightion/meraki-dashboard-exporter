"""Tests for the consumed-operation AST scanner."""

from __future__ import annotations

import textwrap
from pathlib import Path

from apidrift.scanner import consumed_operations


def test_scanner_finds_direct_and_to_thread_calls(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "x"
    pkg.mkdir(parents=True)
    (pkg / "a.py").write_text(
        textwrap.dedent(
            """
            import asyncio
            class C:
                async def go(self):
                    a = self.api.switch.getDeviceSwitchPortsStatuses(s)
                    b = await asyncio.to_thread(
                        self.api.organizations.getOrganizations,
                    )
                    ref = self.api.wireless.getNetworkWirelessSsids
            """
        )
    )
    ops = consumed_operations(str(tmp_path / "src"))
    assert ops == {
        "getDeviceSwitchPortsStatuses",
        "getOrganizations",
        "getNetworkWirelessSsids",
    }


def test_scanner_captures_wrapper_form_via_local_var_and_request_string(
    tmp_path: Path,
) -> None:
    pkg = tmp_path / "src"
    pkg.mkdir(parents=True)
    (pkg / "client.py").write_text(
        textwrap.dedent(
            """
            class AsyncMerakiClient:
                async def get_device_wireless_status(self, serial):
                    api_client = await self._get_api_client()
                    return await self._request(
                        "getDeviceWirelessStatus",
                        api_client.wireless.getDeviceWirelessStatus,
                        serial,
                    )
            """
        )
    )
    ops = consumed_operations(str(pkg))
    # Captured by BOTH the attribute-chain strategy (api_client.wireless.X) and
    # the _request string-literal strategy.
    assert "getDeviceWirelessStatus" in ops


def test_scanner_ignores_non_controller_attributes(tmp_path: Path) -> None:
    pkg = tmp_path / "src"
    pkg.mkdir(parents=True)
    (pkg / "b.py").write_text("self.client.getThing()\nself.helper.foo.bar()\n")
    assert consumed_operations(str(pkg)) == set()
