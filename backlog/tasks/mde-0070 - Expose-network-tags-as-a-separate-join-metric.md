---
id: MDE-0070
title: Expose network tags as a separate join metric
status: Done
assignee:
  - '@rknightion'
created_date: '2026-09-23 11:49'
updated_date: '2026-09-23 12:22'
labels:
  - 'area:metrics'
  - 'area:collectors'
dependencies: []
references:
  - 'https://github.com/rknightion/meraki-dashboard-exporter/issues/784'
priority: medium
type: feature
ordinal: 70000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub issue #784 asks for exact network-tag matching in alert routing. The current meraki_network_info family is one series per network and is used by existing network-name joins. Adding one series per tag there would make those joins ambiguous. The filtered network records already carry tags in collectors/organization.py:908-945, so a separate tag carrier can use the same fetch.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each allowed network emits one meraki_network_tag_info series per distinct tag, labelled org_id, network_id, tag, with value 1; untagged and excluded networks emit none
- [x] #2 A removed tag or departed network stops appearing in the tag metric after a successful collection without waiting for TTL expiration
- [x] #3 meraki_network_info retains one series per network with its existing labels, and meraki_device_up labels remain unchanged
- [x] #4 Metric docs include an exact-tag alert join example, and generated metric references and golden contracts are current
- [x] #5 Focused tests and the repository gate pass
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [x] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [x] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Add failing tests for tag emission, deduplication, filter scope, and immediate removal after a successful collection. Add a separate network tag gauge using existing filtered inventory and explicit series reconciliation. Update docs and generated artefacts, then run focused tests and just check.

The pre-commit end-of-file hook removed an extra trailing blank line from the two regenerated references, so adjust their generators to produce exactly one terminal newline, regenerate, and rerun the gate before commit.

Review found an empty direct-fallback result was ambiguous. Call the sanctioned direct fallback from the organization collector when inventory is unavailable, preserving None for failure and [] for successful empty results; verify both with a focused test.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The tag carrier is separate from meraki_network_info, so existing name joins remain unique. Immediate reconciliation removes deleted tags and departed networks after a successful inventory refresh, including an empty inventory. The direct fallback preserves old series on an ambiguous empty result because it also maps a fetch failure to an empty list. No Grafana query needed changing: the new family is additive and existing metric names and labels are unchanged. Live API verification was attempted, but the configured credential returned HTTP 401; the redacted response in issue #784 and the Network domain model both show tags as a string list. Final just check passed 2,974 tests with 91.49% coverage. CodeRabbit reviewed nine files with zero findings.

The first commit attempt was stopped by end-of-file-fixer on the two generated reference pages. Their generators appended a newline even when the assembled markdown already ended with one. Updated both generators to emit exactly one terminal newline and regenerated the pages.

Resolved CodeRabbit minor finding: the organization collector now calls the sanctioned direct fallback when inventory is unavailable, preserving its None-vs-empty result. A focused test first failed on last-network removal, then passed after the correction. This supersedes the earlier note that the direct fallback must retain old tags on every empty result.

Live verification on Camden, 2026-09-23: the deployed exporter reports commit 00d0eb501d9305d73253863280fbd8c197a0b626. Using its configured API key in memory on Camden, getOrganizationNetworks returned HTTP 200: one network, tags present as a nonempty list of strings. After the organization collection interval, the deployed /metrics endpoint exposed one meraki_network_info sample and one meraki_network_tag_info sample with value 1; meraki_device_up had no tag label. No identifiers or tag values were recorded. This supersedes the earlier .env credential HTTP 401 limitation.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added meraki_network_tag_info with one series per allowed network/tag, immediate removal of obsolete tag series, an exact-tag alert query example, generated references, and golden coverage. Verified by final just check (2,974 passed, 91.49% coverage) and CodeRabbit (zero findings). Live API probe returned 401 and remains unverified.

The two documentation generators now emit one terminal newline, so regenerated references satisfy both just gen drift checking and the commit hook.

The direct fallback now removes the last tag on a confirmed empty response while retaining tags after a failed fetch.

Camden live verification subsequently passed on the deployed exact commit: API HTTP 200 returned a tagged network; /metrics exposed one network-tag sample with value 1 and left meraki_device_up labels unchanged.
<!-- SECTION:FINAL_SUMMARY:END -->
