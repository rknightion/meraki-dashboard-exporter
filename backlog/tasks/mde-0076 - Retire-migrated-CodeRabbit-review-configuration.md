---
id: MDE-0076
title: Retire migrated CodeRabbit review configuration
status: Done
assignee: []
created_date: '2026-11-06T11:53:00Z'
updated_date: '2026-11-06T11:53:00Z'
labels: []
dependencies: []
priority: low
type: chore
ordinal: 76000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The repository review instructions have been migrated to the replacement managed review workflow. The obsolete root CodeRabbit configuration can now be retired while preserving exporter behavior and existing validation requirements.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The obsolete root reviewer configuration is removed and its preimage remains recoverable.
- [x] #2 The change contains only the configuration deletion and this task record; application, build, deployment and generated content remain unchanged.
- [x] #3 The task record contains no credentials, customer identifiers, private repository references or local paths, and the scoped diff passes whitespace validation.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Remove only the obsolete reviewer configuration after checking its retained preimage and migrated instructions. Verify the diff is configuration plus task metadata only, inspect public-safe wording, and record the bounded declarative validation exemption.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verified the captured configuration preimage matches its retained copy and the migrated review instructions. The scoped change is only the root configuration deletion and this task record. Public-safe wording and git diff --check passed. Existing bounded declarative-config validation applies: no application, image, architecture, generated artifact or runtime change requires the full application gate for this retirement. No full-suite or paid review PASS is claimed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Removed the obsolete review configuration after instruction migration, preserving the preimage and all application/build/deployment sources. Scoped diff and public-record validation passed; publication is handled separately.
<!-- SECTION:FINAL_SUMMARY:END -->
