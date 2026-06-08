"""Device-specific collectors."""

from .base import BaseDeviceCollector
from .mg import MGCollector
from .mr import MRCollector
from .ms import MSCollector
from .ms_stack import MSStackCollector
from .mt import MTCollector
from .mv import MVCollector
from .mx import MXCollector
from .mx_wan_collector import MXWanCollector  # noqa: F401

__all__ = [
    "BaseDeviceCollector",
    "MGCollector",
    "MRCollector",
    "MSCollector",
    "MSStackCollector",
    "MTCollector",
    "MVCollector",
    "MXCollector",
]
