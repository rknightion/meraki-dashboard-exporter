"""Meraki Dashboard Exporter for Prometheus."""

# Re-export the CLI entrypoint so callers don't need to import the private module
from .__main__ import main  # noqa: F401

__all__ = ["main"]
