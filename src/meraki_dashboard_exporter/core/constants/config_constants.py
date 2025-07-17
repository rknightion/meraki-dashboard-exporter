"""Configuration constants and dataclasses for the Meraki Dashboard Exporter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class APIConfig:
    """API configuration settings."""

    timeout: int = 30  # seconds
    max_retries: int = 4  # default for Meraki SDK
    max_concurrent_requests: int = 5
    rate_limit_retry_wait: int = 60  # seconds


@dataclass(frozen=True)
class RegionalURLs:
    """Meraki API regional base URLs."""

    default: str = "https://api.meraki.com/api/v1"  # Global/Default
    canada: str = "https://api.meraki.ca/api/v1"
    china: str = "https://api.meraki.cn/api/v1"
    india: str = "https://api.meraki.in/api/v1"
    us_fed: str = "https://api.gov-meraki.com/api/v1"


@dataclass(frozen=True)
class MerakiAPIConfig:
    """Complete Meraki API configuration."""

    api_config: APIConfig = field(default_factory=APIConfig)
    regional_urls: RegionalURLs = field(default_factory=RegionalURLs)

    @property
    def base_url(self) -> str:
        """Get the default base URL."""
        return self.regional_urls.default


# Default configuration instance
DEFAULT_API_CONFIG: Final[MerakiAPIConfig] = MerakiAPIConfig()

# Legacy constants for backward compatibility
DEFAULT_API_TIMEOUT: Final[int] = DEFAULT_API_CONFIG.api_config.timeout
DEFAULT_MAX_RETRIES: Final[int] = DEFAULT_API_CONFIG.api_config.max_retries

# Regional URLs for backward compatibility
MERAKI_API_BASE_URL: Final[str] = DEFAULT_API_CONFIG.regional_urls.default
MERAKI_API_BASE_URL_CANADA: Final[str] = DEFAULT_API_CONFIG.regional_urls.canada
MERAKI_API_BASE_URL_CHINA: Final[str] = DEFAULT_API_CONFIG.regional_urls.china
MERAKI_API_BASE_URL_INDIA: Final[str] = DEFAULT_API_CONFIG.regional_urls.india
MERAKI_API_BASE_URL_US_FED: Final[str] = DEFAULT_API_CONFIG.regional_urls.us_fed
