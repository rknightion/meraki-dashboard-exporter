<system_context>
Organization-level collectors for Meraki Dashboard Exporter - Handles metrics that apply to entire organizations such as API usage, license consumption, and client overview statistics.
</system_context>

<critical_notes>
- **Inherit from BaseOrganizationCollector** for consistent organization patterns
- **SLOW update tier**: Most org metrics change infrequently (900s interval)
- **Manual registration**: Organization collectors are registered in OrganizationCollector coordinator
- **High-level aggregation**: Focus on organization-wide summaries rather than device specifics
</critical_notes>

<file_map>
## ORGANIZATION COLLECTOR FILES
- `base.py` - BaseOrganizationCollector with common organization patterns
- `api_usage.py` - API request tracking and quota monitoring
- `license.py` - License usage and availability metrics
- `client_overview.py` - Organization-wide client statistics and trends
</file_map>

<paved_path>
## ORGANIZATION COLLECTOR PATTERN
```python
from .base import BaseOrganizationCollector
from ..core.constants.metrics_constants import MetricName
from ..core.metrics import LabelName

class APIUsageCollector(BaseOrganizationCollector):
    """Collector for organization API usage metrics"""

    def _initialize_metrics(self) -> None:
        self.api_requests_total = Gauge(
            MetricName.API_REQUESTS_TOTAL.value,
            "Total API requests made by organization",
            [LabelName.ORG_ID.value, LabelName.ENDPOINT.value]
        )

    async def _collect_impl(self) -> None:
        organizations = await self._get_organizations()
        for org in organizations:
            await self._collect_api_usage(org.id)
```

## TIMESPAN HANDLING FOR ORG METRICS
```python
# Client overview requires exactly 3600 seconds
@log_api_call("getOrganizationClientsOverview")
async def _collect_client_overview(self, org_id: str) -> None:
    self._track_api_call("getOrganizationClientsOverview")

    client_data = await asyncio.to_thread(
        self.api.organizations.getOrganizationClientsOverview,
        org_id,
        timespan=3600  # Must be exactly 1 hour
    )

    self._update_client_metrics(org_id, client_data)
```
</paved_path>

<patterns>
## ORGANIZATION METRIC CATEGORIES

### API Usage Tracking
- **Request counts**: Total API calls per endpoint
- **Response codes**: Success/failure ratios
- **Rate limit status**: Current usage vs limits
- **Update tier**: SLOW (900s) - Usage patterns change slowly

### License Management
- **License consumption**: Used vs available licenses
- **License types**: Different product license tracking
- **Expiration dates**: License renewal monitoring
- **Update tier**: SLOW (900s) - License changes are infrequent

### Client Overview Statistics
- **Total clients**: Organization-wide client counts
- **Client trends**: Growth/decline over time
- **Usage patterns**: Active vs inactive clients
- **Update tier**: MEDIUM (300s) - Client counts change regularly
</patterns>

<examples>
## Complete Organization Collector Example
```python
import asyncio
from prometheus_client import Gauge
from ..core.constants.metrics_constants import MetricName
from ..core.metrics import LabelName
from ..core.error_handling import with_error_handling
from ..core.logging_decorators import log_api_call
from .base import BaseOrganizationCollector

class LicenseCollector(BaseOrganizationCollector):
    """Collector for organization license metrics"""

    def _initialize_metrics(self) -> None:
        self.license_usage = Gauge(
            MetricName.LICENSE_USAGE.value,
            "License usage count by type",
            [LabelName.ORG_ID.value, LabelName.LICENSE_TYPE.value, LabelName.STATUS.value]
        )

        self.license_limit = Gauge(
            MetricName.LICENSE_LIMIT.value,
            "License limit by type",
            [LabelName.ORG_ID.value, LabelName.LICENSE_TYPE.value]
        )

    @with_error_handling("Collect license metrics", continue_on_error=True)
    async def _collect_impl(self) -> None:
        organizations = await self._get_organizations()

        for org in organizations:
            await self._collect_license_data(org.id)

    @log_api_call("getOrganizationLicenses")
    async def _collect_license_data(self, org_id: str) -> None:
        """Collect license usage and limits for organization"""
        self._track_api_call("getOrganizationLicenses")

        try:
            license_data = await asyncio.to_thread(
                self.api.organizations.getOrganizationLicenses,
                org_id,
                total_pages="all"
            )

            # Process license information
            license_summary = self._process_license_data(license_data)

            # Update metrics
            for license_type, info in license_summary.items():
                # Used licenses
                self.license_usage.labels(
                    org_id=org_id,
                    license_type=license_type,
                    status="used"
                ).set(info["used"])

                # Available licenses
                self.license_usage.labels(
                    org_id=org_id,
                    license_type=license_type,
                    status="available"
                ).set(info["available"])

                # Total limit
                self.license_limit.labels(
                    org_id=org_id,
                    license_type=license_type
                ).set(info["total"])

        except Exception as e:
            self.logger.error(f"Failed to collect license data for org {org_id}: {e}")

    def _process_license_data(self, license_data: list[dict]) -> dict:
        """Process raw license data into summary format"""
        summary = {}

        for license_item in license_data:
            license_type = license_item.get("productType", "unknown")

            if license_type not in summary:
                summary[license_type] = {
                    "used": 0,
                    "available": 0,
                    "total": 0
                }

            # Extract usage information
            used = license_item.get("deviceCount", 0)
            total = license_item.get("totalLicenseCount", 0)
            available = max(0, total - used)

            summary[license_type]["used"] += used
            summary[license_type]["total"] += total
            summary[license_type]["available"] += available

        return summary
```

## Client Overview Collector Example
```python
class ClientOverviewCollector(BaseOrganizationCollector):
    """Collector for organization client overview metrics"""

    def _initialize_metrics(self) -> None:
        self.client_count = Gauge(
            MetricName.CLIENT_COUNT_TOTAL.value,
            "Total client count in organization",
            [LabelName.ORG_ID.value, LabelName.TIME_PERIOD.value]
        )

    @log_api_call("getOrganizationClientsOverview")
    async def _collect_client_overview(self, org_id: str) -> None:
        """Collect client overview - requires exactly 3600s timespan"""
        self._track_api_call("getOrganizationClientsOverview")

        try:
            # Client overview requires exactly 1 hour timespan
            client_data = await asyncio.to_thread(
                self.api.organizations.getOrganizationClientsOverview,
                org_id,
                timespan=3600
            )

            # Extract metrics from response
            if "counts" in client_data:
                total = client_data["counts"].get("total", 0)

                self.client_count.labels(
                    org_id=org_id,
                    time_period="1h"
                ).set(total)

        except Exception as e:
            self.logger.error(f"Failed to collect client overview for org {org_id}: {e}")
```
</examples>

<workflow>
## ADDING NEW ORGANIZATION COLLECTOR
1. **Identify organization scope**: Ensure metric applies to entire organization
2. **Inherit from BaseOrganizationCollector**: Provides organization iteration patterns
3. **Choose update tier**: Usually SLOW (900s) for license/usage, MEDIUM (300s) for client data
4. **Define org-level metrics**: Focus on aggregation and summaries
5. **Handle API constraints**: Some endpoints have specific timespan requirements
6. **Register in coordinator**: Add to OrganizationCollector's subcollectors list
7. **Test with multiple orgs**: Ensure proper isolation between organizations
</workflow>

<api_quirks>
## ORGANIZATION API SPECIFIC LIMITATIONS
- **Client overview timespan**: Must be exactly 3600 seconds
- **License pagination**: Some license endpoints require `total_pages="all"`
- **API usage data**: Historical data may be limited or delayed
- **Cross-organization data**: No single call to get data across all organizations
- **Rate limiting**: Organization-level calls count toward per-org rate limits
</api_quirks>

<hatch>
## ALTERNATIVE ORGANIZATION PATTERNS
- **Caching strategies**: Cache non-zero values for client overview metrics
- **Batch processing**: Group multiple organization calls when possible
- **Fallback data**: Use last known good values when API calls fail
- **Trend calculation**: Calculate growth/decline metrics from historical data
</hatch>

<fatal_implications>
- **NEVER aggregate across organizations** without proper labeling
- **NEVER assume all organizations have same capabilities**
- **NEVER skip timespan validation** for endpoints with specific requirements
- **NEVER cache sensitive license information** inappropriately
</fatal_implications>
