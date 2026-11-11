"""Send a request to an ASGI app with exact header bytes.

``TestClient`` goes through httpx, which re-encodes a header value that is not valid UTF-8 (byte
0xFF reaches the app as the two bytes 0xC3 0xBF). Tests about the raw bytes a client puts on the
wire use this helper instead.
"""

from __future__ import annotations

import asyncio
from typing import Any


def raw_request_status(
    app: Any,
    method: str,
    path: str,
    headers: list[tuple[bytes, bytes]],
    body: bytes = b"",
) -> int:
    """Run one HTTP request through ``app`` and return the response status code."""
    status: dict[str, int] = {}

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            status["code"] = message["status"]

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), *headers],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))
    return status["code"]
