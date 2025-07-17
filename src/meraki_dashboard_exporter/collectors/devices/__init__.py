"""Device-specific collectors."""

from .base import BaseDeviceCollector
from .mg import MGCollector
from .mr import MRCollector
from .ms import MSCollector
from .mt import MTCollector
from .mv import MVCollector
from .mx import MXCollector

__all__ = [
    "BaseDeviceCollector",
    "MGCollector",
    "MRCollector",
    "MSCollector",
    "MTCollector",
    "MVCollector",
    "MXCollector",
]
