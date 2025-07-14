"""Version information for the Meraki Dashboard Exporter."""

from __future__ import annotations

import re
from pathlib import Path


def get_version() -> str:
    """Get the version from pyproject.toml.

    Returns
    -------
    str
        The package version.

    """
    try:
        # Try to read from pyproject.toml
        root = Path(__file__).parent.parent.parent
        pyproject_path = root / "pyproject.toml"

        if pyproject_path.exists():
            content = pyproject_path.read_text()
            match = re.search(r'version = "([^"]+)"', content)
            if match:
                return match.group(1)

        # Fallback to importlib.metadata if installed
        import importlib.metadata

        return importlib.metadata.version("meraki-dashboard-exporter")
    except Exception:
        # Development fallback
        return "0.0.0+dev"


__version__ = get_version()
