"""Version information for the Meraki Dashboard Exporter."""

from __future__ import annotations

import os
import re
from pathlib import Path


def get_version() -> str:
    """Get the package version.

    Resolution order:
    1. ``pyproject.toml`` next to the repo root (source checkouts / dev).
    2. ``importlib.metadata`` (pip-installed distributions).
    3. The ``MERAKI_EXPORTER_VERSION`` env var baked into the runtime container
       image (F-118) — the image has no ``pyproject.toml`` and installs deps with
       ``uv sync --no-install-project`` so neither source above is available.
    4. The ``0.0.0+dev`` development sentinel.

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
        # Neither local source available (e.g. the runtime container image).
        pass

    # Baked-in version injected at image build time (F-118).
    baked_version = os.environ.get("MERAKI_EXPORTER_VERSION")
    if baked_version:
        return baked_version

    # Development fallback
    return "0.0.0+dev"


def get_commit() -> str:
    """Get the git commit SHA the running build was produced from.

    Resolution order:
    1. The ``MERAKI_EXPORTER_COMMIT`` env var baked into the runtime container
       image at build time from the ``GIT_COMMIT`` build-arg (CI passes
       ``github.sha`` in both ``ci.yml`` and ``publish.yml``).
    2. The ``"unknown"`` sentinel for local/dev builds that were not built with
       that build-arg (DEP-06) — mirrors ``get_version()``'s ``0.0.0+dev``.

    Returns
    -------
    str
        The commit SHA, or ``"unknown"`` for un-stamped dev builds.

    """
    return os.environ.get("MERAKI_EXPORTER_COMMIT") or "unknown"


__version__ = get_version()
