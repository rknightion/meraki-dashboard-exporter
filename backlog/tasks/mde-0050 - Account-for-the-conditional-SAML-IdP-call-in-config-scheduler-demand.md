---
id: MDE-0050
title: Account for the conditional SAML IdP call in config scheduler demand
status: To Do
assignee: []
created_date: '2026-09-03 14:38'
labels:
  - 'area:scheduler'
dependencies: []
priority: medium
type: bug
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit dimension 1 confirmed a live conditional scheduler-accounting defect at the v2.0.0 release tree. `src/meraki_dashboard_exporter/collectors/config.py:37-47` documents that a SAML-enabled organization adds one API call but still fixes `CONFIG_ORG` demand at four. The cycle makes login-security, admins, configuration-changes and SAML-settings calls, then `config.py:556-573` also calls `getOrganizationSamlIdps` when SAML is enabled. In that state the solver underestimates the group by 25 percent and may allocate more demand than intended. `tests/unit/test_config_scheduler_gates.py:57-61` knowingly pins four and has no enabled-SAML demand reconciliation. The implementation needs an explicit product choice between a conservative cost of five for all organizations and a scheduler-visible SAML capability dimension.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 CONFIG_ORG demand accounts for all five calls when SAML is enabled and cannot understate that state
- [ ] #2 A regression exercises an enabled-SAML cycle and reconciles its five facade calls with declared demand
- [ ] #3 The chosen conservative or capability-aware policy documents its behavior for SAML-disabled organizations
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just check (ruff format --check, ruff check, mypy, generated-doc drift, offline API conformance, and the marker-filtered pytest run with the 80% coverage floor — this is exactly what the CI `test` job runs)
- [ ] #2 just gen, when metrics, config, endpoints, collectors, the settings schema or the chart config changed — `just check` includes the drift gate and CI fails the build on it
- [ ] #3 Grafana queries in grafana/dashboards/*.json and grafana/alerts/ updated, if a metric or label name changed
<!-- DOD:END -->
