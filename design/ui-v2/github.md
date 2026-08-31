repo: rknightion/meraki-dashboard-exporter
branch: main
path: src/meraki_dashboard_exporter/templates

## Last sync

date: 2026-08-31T11:12:16Z

### Updated in this project

- Recreated all six embedded operator pages and restyled them onto m7kni Design System v2, light and dark.
- Unified the six duplicated per-template CSS blocks into one shared token stylesheet plus one shared app stylesheet.
- Replaced emoji section markers with Phosphor regular inline SVG, and pill fills with shape-plus-word status.
- Wrote `implementation-spec.md`: drop-in CSS, `_base.html`, `ui.js`, font hosting, type roles, AA measurements, assumptions.

## Screen map

| Screen (in `Meraki Exporter UI.dc.html`) | Repo files it was built from |
| --- | --- |
| Overview | `src/meraki_dashboard_exporter/templates/index.html`, `README.md` |
| Clients | `src/meraki_dashboard_exporter/templates/clients.html` |
| Status | `src/meraki_dashboard_exporter/templates/status.html` |
| Cardinality overview | `src/meraki_dashboard_exporter/templates/cardinality.html` |
| Cardinality - all metrics | `src/meraki_dashboard_exporter/templates/cardinality_all_metrics.html` |
| Cardinality - all labels | `src/meraki_dashboard_exporter/templates/cardinality_all_labels.html` |
| Shared chrome (brand bar, nav, sub-nav, theme toggle) | all six templates above |

Icons are copied from `phosphor-icons/core`, `assets/regular/` (MIT).
