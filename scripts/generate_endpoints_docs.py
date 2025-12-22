#!/usr/bin/env python3
"""Generate documentation for HTTP endpoints exposed by the exporter."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}

ENDPOINT_NOTES = {
    "/clients": "Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true",
    "/api/clients/clear-dns-cache": "Requires MERAKI_EXPORTER_CLIENTS__ENABLED=true",
    "/api/webhooks/meraki": "Requires MERAKI_EXPORTER_WEBHOOKS__ENABLED=true",
}

CARDINALITY_NOTE = "Cardinality data appears after the first full collection cycle."


@dataclass
class Endpoint:
    """Captured HTTP endpoint."""

    method: str
    path: str
    description: str
    file: str
    line: int


def find_repo_root(start_path: Path) -> Path:
    """Find the repository root by walking upwards."""
    for candidate in [start_path, *start_path.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
            return candidate
    raise FileNotFoundError("Could not locate repository root (pyproject.toml + src)")


def read_text(path: Path) -> str:
    """Read a file as UTF-8 text."""
    return path.read_text(encoding="utf-8")


def extract_endpoints(file_path: Path, repo_root: Path) -> list[Endpoint]:
    """Extract FastAPI endpoints from a file."""
    endpoints: list[Endpoint] = []
    tree = ast.parse(read_text(file_path), filename=str(file_path))

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr not in HTTP_METHODS:
                continue
            if not isinstance(decorator.func.value, ast.Name):
                continue
            if decorator.func.value.id != "app":
                continue

            if not decorator.args:
                continue

            path_arg = decorator.args[0]
            if not isinstance(path_arg, ast.Constant) or not isinstance(path_arg.value, str):
                continue

            docstring = ast.get_docstring(node) or ""
            description = docstring.split("\n")[0].strip() if docstring else node.name

            endpoints.append(
                Endpoint(
                    method=decorator.func.attr.upper(),
                    path=path_arg.value,
                    description=description,
                    file=str(file_path.relative_to(repo_root)),
                    line=node.lineno,
                )
            )

    return endpoints


def generate_markdown(endpoints: list[Endpoint]) -> str:
    """Generate markdown documentation for endpoints."""
    lines = ["# HTTP Endpoints", ""]
    lines.append("This page lists HTTP endpoints exposed by the exporter.")
    lines.append("")

    lines.append("| Method | Path | Description | Notes |")
    lines.append("|--------|------|-------------|-------|")

    for endpoint in sorted(endpoints, key=lambda e: (e.path, e.method)):
        notes = ENDPOINT_NOTES.get(endpoint.path, "")
        if endpoint.path.startswith("/cardinality") or endpoint.path.startswith(
            "/api/metrics/cardinality"
        ):
            notes = CARDINALITY_NOTE
        lines.append(
            f"| `{endpoint.method}` | `{endpoint.path}` | {endpoint.description} | {notes} |"
        )

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `/metrics` and `/health` are always available.")
    lines.append("- The client UI and DNS cache endpoint are gated by client collection.")
    lines.append("- The webhook endpoint returns 404 when webhooks are disabled.")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Main entry point."""
    repo_root = find_repo_root(Path(__file__).resolve())
    app_file = repo_root / "src" / "meraki_dashboard_exporter" / "app.py"
    cardinality_file = repo_root / "src" / "meraki_dashboard_exporter" / "core" / "cardinality.py"

    endpoints: list[Endpoint] = []
    for file_path in [app_file, cardinality_file]:
        if file_path.exists():
            endpoints.extend(extract_endpoints(file_path, repo_root))

    # Deduplicate endpoints by method + path
    deduped: dict[tuple[str, str], Endpoint] = {}
    for endpoint in endpoints:
        deduped[(endpoint.method, endpoint.path)] = endpoint

    output_file = repo_root / "docs" / "reference" / "endpoints.md"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(generate_markdown(list(deduped.values())) + "\n", encoding="utf-8")

    print(f"Endpoint documentation written to {output_file}")


if __name__ == "__main__":
    main()
