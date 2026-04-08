<system_context>
Organization-level collectors for Meraki Dashboard Exporter - Handles metrics that apply to entire organizations such as API usage, license consumption, and client overview statistics.
</system_context>

<critical_notes>
- **Inherit from `BaseOrganizationCollector`** (in `base.py`) for consistent organization patterns
- **SLOW update tier**: Most org metrics change infrequently (900s interval)
- **Manual registration**: Sub-collectors registered in `OrganizationCollector` coordinator
- **Inventory integration**: Access shared cache via `self.inventory = getattr(parent, "inventory", None)`
</critical_notes>

<file_map>
## ORGANIZATION COLLECTOR FILES
- `base.py` - `BaseOrganizationCollector` with common patterns and inventory service integration
- `api_usage.py` - API request tracking and quota monitoring
- `license.py` - License usage and availability metrics
- `client_overview.py` - Organization-wide client statistics and trends
</file_map>

<paved_path>
## ORGANIZATION COLLECTOR PATTERN
```python
from .base import BaseOrganizationCollector

class MyOrgCollector(BaseOrganizationCollector):
    def _initialize_metrics(self) -> None:
        self._my_metric = self.parent._create_gauge(
            OrgMetricName.SOME_METRIC,
            "Description",
            labelnames=[LabelName.ORG_ID.value],
        )

    async def _collect_for_org(self, org_id: str) -> None:
        data = await asyncio.to_thread(
            self.api.organizations.getOrganizationSomeEndpoint,
            org_id,
        )
```
</paved_path>

<api_quirks>
- **Client overview timespan**: Must be exactly 3600 seconds
- **License pagination**: Some license endpoints require `total_pages="all"`
- **Rate limiting**: Organization-level calls count toward per-org rate limits
</api_quirks>

<fatal_implications>
- **NEVER aggregate across organizations** without proper labeling
- **NEVER skip timespan validation** for endpoints with specific requirements
</fatal_implications>
