# meraki-dashboard-exporter embedded UI - m7kni Design System v2 implementation spec

Target: the six server-rendered pages in `src/meraki_dashboard_exporter/templates/`. Stack is
unchanged - FastAPI + Jinja2, no build step, no frontend framework. The change is structural, not
architectural: six independent per-template `<style>` blocks collapse into two shared static
stylesheets plus a small per-page remainder, and the pages gain a first-class dark theme.

Companion design: `Meraki Exporter UI.dc.html` (all six pages, both themes, plus the empty and
first-run states via the `dataState` control).

Never use an em dash or en dash in copy, page text, or comments. A spaced hyphen is the only dash.

---

## 1. File layout

```
src/meraki_dashboard_exporter/
  static/
    css/
      tokens.css          <- section 2. The design system. Generated upstream, do not hand-edit.
      app.css             <- section 3. The shared chrome, table, stat and status treatment.
    fonts/
      hanken-grotesk-latin.woff2
      hanken-grotesk-latin-ext.woff2
      jetbrains-mono-latin.woff2
      jetbrains-mono-latin-ext.woff2
  templates/
    _base.html            <- new. Section 6. Header, nav, theme toggle, stylesheet links.
    index.html            <- extends _base
    clients.html          <- extends _base
    status.html           <- extends _base
    cardinality.html      <- extends _base
    cardinality_all_metrics.html
    cardinality_all_labels.html
```

Mount in `app.py` next to the existing template configuration:

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")
```

`/static` is a plain GET of files that ship inside the package. It is not an operator surface and
needs no auth gate; the auth posture of `/clients`, `/status` and `/cardinality` is unchanged.

---

## 2. `static/css/tokens.css`

Drop in verbatim. Values are lifted from the design system's published `tokens/tokens.css`; the only
addition is the `prefers-color-scheme` block, which re-points the same names so an operator whose OS
is dark gets dark without touching anything, and `[data-theme]` on `<html>` overrides in both
directions.

```css
/* m7kni Design System v2 - tokens. Generated upstream; do not hand-edit.
 * Light is the default. Dark is applied by OS preference and can be forced
 * either way with data-theme="light" | "dark" on <html>. */

:root {
  /* space - 4px base, no intermediate steps */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
  --space-16: 64px;

  /* radius - precise, not soft */
  --radius-control: 3px;
  --radius-container: 0px;
  --radius-overlay: 6px;
  --radius-full: 9999px;

  --row-table: 36px;

  /* type */
  --font-family-sans: "Hanken Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-family-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  --font-size-2xs: 10px;
  --font-size-xs: 11px;
  --font-size-sm: 12.5px;
  --font-size-md: 13.5px;
  --font-size-lg: 15px;
  --font-size-xl: 18px;
  --font-size-2xl: 24px;
  --font-weight-regular: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --font-weight-bold: 700;
  --tracking-label: 0.13em;

  --duration-fast: 120ms;
  --duration-base: 160ms;
  --duration-slow: 200ms;

  /* colour - petrol accent, petrol-tinted neutrals (~227deg OKLCH at low chroma) */
  --color-bg-canvas: oklch(0.962 0.007 227);
  --color-bg-surface: oklch(0.982 0.004 227);
  --color-bg-raised: oklch(1 0 0);
  --color-bg-hover: oklch(0.945 0.009 227);
  --color-bg-selected: oklch(0.925 0.012 227);
  --color-bg-track: oklch(0.85 0.01 227);
  --color-bg-inverse: oklch(0.27 0.012 227);
  --color-bg-accent: #1d6a8a;
  --color-bg-accent-soft: #e4eef4;
  --color-fg-default: oklch(0.24 0.012 227);
  --color-fg-soft: oklch(0.37 0.015 227);
  --color-fg-muted: oklch(0.5 0.018 227);
  --color-fg-faint: oklch(0.65 0.015 227); /* decorative / disabled / placeholder only */
  --color-fg-on-accent: oklch(1 0 0);
  --color-fg-on-inverse: oklch(0.93 0.005 227);
  --color-border-default: oklch(0.9 0.008 227);
  --color-border-strong: oklch(0.82 0.01 227);
  --color-status-ok: #2f7d4f;
  --color-status-warn: #8f6410;
  --color-status-fail: #a83a2e;
  --color-accent-hover: #175874;

  /* derived in-cell furniture. Mixed from ink, never a fixed grey, so it survives
   * every row background state (see section 9). */
  --row-hover: color-mix(in oklab, var(--color-bg-accent) 4%, var(--color-bg-surface));
  --row-warn: color-mix(in oklab, var(--color-status-warn) 7%, var(--color-bg-surface));
  --row-fail: color-mix(in oklab, var(--color-status-fail) 7%, var(--color-bg-surface));
  --meter-track: color-mix(in oklab, var(--color-fg-default) 14%, var(--color-bg-surface));
}

/* dark - semantic re-pointing of the same names. Surfaces lift, they do not invert. */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --color-bg-canvas: oklch(0.195 0.01 227);
    --color-bg-surface: oklch(0.225 0.011 227);
    --color-bg-raised: oklch(0.26 0.012 227);
    --color-bg-hover: oklch(0.245 0.012 227);
    --color-bg-selected: oklch(0.28 0.014 227);
    --color-bg-track: oklch(0.36 0.012 227);
    --color-bg-inverse: oklch(0.245 0.012 227);
    --color-bg-accent: #66aecb;
    --color-bg-accent-soft: #1f2f38;
    --color-fg-default: oklch(0.92 0.006 227);
    --color-fg-soft: oklch(0.8 0.01 227);
    --color-fg-muted: oklch(0.7 0.015 227);
    --color-fg-faint: oklch(0.55 0.015 227);
    --color-fg-on-accent: #0e161b;
    --color-fg-on-inverse: oklch(0.92 0.006 227);
    --color-border-default: oklch(0.31 0.012 227);
    --color-border-strong: oklch(0.4 0.014 227);
    --color-status-ok: #5fae7f;
    --color-status-warn: #c9a04a;
    --color-status-fail: #d97b64;
    --color-accent-hover: #7cbcd6;
  }
}

:root[data-theme="dark"] {
  --color-bg-canvas: oklch(0.195 0.01 227);
  --color-bg-surface: oklch(0.225 0.011 227);
  --color-bg-raised: oklch(0.26 0.012 227);
  --color-bg-hover: oklch(0.245 0.012 227);
  --color-bg-selected: oklch(0.28 0.014 227);
  --color-bg-track: oklch(0.36 0.012 227);
  --color-bg-inverse: oklch(0.245 0.012 227);
  --color-bg-accent: #66aecb;
  --color-bg-accent-soft: #1f2f38;
  --color-fg-default: oklch(0.92 0.006 227);
  --color-fg-soft: oklch(0.8 0.01 227);
  --color-fg-muted: oklch(0.7 0.015 227);
  --color-fg-faint: oklch(0.55 0.015 227);
  --color-fg-on-accent: #0e161b;
  --color-fg-on-inverse: oklch(0.92 0.006 227);
  --color-border-default: oklch(0.31 0.012 227);
  --color-border-strong: oklch(0.4 0.014 227);
  --color-status-ok: #5fae7f;
  --color-status-warn: #c9a04a;
  --color-status-fail: #d97b64;
  --color-accent-hover: #7cbcd6;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition-duration: 0ms !important; animation-duration: 0ms !important; }
}
```

`color-mix(in oklab, ...)` and `oklch()` are Baseline 2023 and safe for an operator tool opened
next to Grafana. If a hard floor on older browsers is needed, add static hex fallbacks immediately
above each declaration; nothing in the design depends on the mix succeeding, only on it being
distinguishable.

---

## 3. `static/css/app.css`

The whole visual language of all six pages. Nothing below is page-specific.

```css
/* ---------- reset and page frame ---------- */
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body {
  display: flex;
  flex-direction: column;
  overflow: hidden;                 /* the content region scrolls, the chrome never does */
  background: var(--color-bg-canvas);
  color: var(--color-fg-soft);
  font-family: var(--font-family-sans);
  font-size: var(--font-size-md);
  line-height: 1.45;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--color-bg-accent); text-decoration: none; }
a:hover { color: var(--color-accent-hover); text-decoration: underline; }
a:focus-visible, button:focus-visible, input:focus-visible {
  outline: 2px solid var(--color-bg-accent); outline-offset: 1px;
}
::selection { background: var(--color-bg-selected); }
.mono { font-family: var(--font-family-mono); }
.num  { font-variant-numeric: tabular-nums; }
.icon { width: 15px; height: 15px; flex: none; display: inline-block; vertical-align: -2px; }
.icon-sm { width: 13px; height: 13px; }

/* ---------- 1. brand bar ---------- */
.brandbar {
  display: flex; align-items: center; gap: var(--space-3);
  padding: 9px var(--space-5); flex: none;
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border-default);
}
.brandbar .mark {
  width: 16px; height: 16px; flex: none;
  background: var(--color-bg-accent); border-radius: var(--radius-control);
}
.brandbar .name {
  font-size: var(--font-size-lg); font-weight: 650;
  color: var(--color-fg-default); letter-spacing: -0.01em;
}
.chip {                                /* version, commit, cadence, any short machine fact */
  font-family: var(--font-family-mono); font-size: var(--font-size-2xs);
  letter-spacing: var(--tracking-label); text-transform: uppercase;
  color: var(--color-fg-muted);
  border: 1px solid var(--color-border-default); border-radius: var(--radius-control);
  padding: 1px 5px;
}
.brandbar .right { margin-left: auto; display: flex; align-items: center; gap: var(--space-4); }
.meta { font-family: var(--font-family-mono); font-size: var(--font-size-xs); color: var(--color-fg-muted); }

/* ---------- 2. buttons ---------- */
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  font: inherit; font-size: var(--font-size-sm); font-weight: 500;
  padding: 4px 9px; cursor: pointer;
  border: 1px solid var(--color-border-strong); border-radius: var(--radius-control);
  background: var(--color-bg-raised); color: var(--color-fg-default);
  transition: border-color var(--duration-fast) ease-out;
}
.btn:hover { border-color: var(--color-fg-muted); }
.btn-primary {
  background: var(--color-bg-accent); border-color: var(--color-bg-accent);
  color: var(--color-fg-on-accent); font-weight: 600;
}
.btn-primary:hover { background: var(--color-accent-hover); border-color: var(--color-accent-hover); }
.btn[disabled] {
  background: var(--color-bg-canvas); border-color: var(--color-border-default);
  color: var(--color-fg-faint); cursor: not-allowed;
}
.btn-sm { font-size: var(--font-size-xs); padding: 2px 8px; }

/* ---------- 3. nav ---------- */
.nav {
  display: flex; align-items: stretch; padding: 0 var(--space-5); flex: none;
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border-default);
}
.nav a {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 8px 13px; font-size: var(--font-size-md); font-weight: 500;
  color: var(--color-fg-muted); border-bottom: 2px solid transparent;
}
.nav a:hover { color: var(--color-fg-default); text-decoration: none; }
.nav a[aria-current] {
  color: var(--color-fg-default); font-weight: 600;
  border-bottom-color: var(--color-bg-accent);
}
.nav .port { margin-left: auto; align-self: center; font-family: var(--font-family-mono);
  font-size: var(--font-size-xs); color: var(--color-fg-faint); }

.subnav {
  display: flex; align-items: center; gap: 2px; flex: none;
  padding: 6px var(--space-5);
  background: var(--color-bg-canvas);
  border-bottom: 1px solid var(--color-border-default);
}
.subnav .group { margin-right: 10px; }
.subnav a {
  font-size: var(--font-size-sm); font-weight: 500; padding: 3px 10px;
  color: var(--color-fg-muted);
  border: 1px solid transparent; border-radius: var(--radius-control);
}
.subnav a:hover { color: var(--color-fg-default); text-decoration: none; }
.subnav a[aria-current] {
  color: var(--color-bg-accent); font-weight: 600;
  border-color: var(--color-bg-accent); background: var(--color-bg-accent-soft);
}

/* ---------- 4. page title bar ---------- */
.pagehead {
  display: flex; align-items: flex-end; gap: var(--space-3); flex: none;
  padding: 14px var(--space-5) 12px;
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border-default);
}
.pagehead h1 {
  margin: 0; font-size: var(--font-size-xl); font-weight: 650;
  color: var(--color-fg-default); letter-spacing: -0.015em;
}
.pagehead p { margin: 2px 0 0; font-size: var(--font-size-sm); color: var(--color-fg-muted); }
.pagehead .right { margin-left: auto; text-align: right; }

/* ---------- 5. scrolling content region ---------- */
.content { flex: 1; min-height: 0; overflow: auto; }
.content > section { padding: 18px var(--space-5) 0; }
.content::after { content: ""; display: block; height: var(--space-6); }

/* ---------- 6. section header - a rule, not a card ---------- */
.sechead {
  display: flex; align-items: center; gap: var(--space-2);
  padding-bottom: 7px; border-bottom: 1px solid var(--color-border-strong);
}
.sechead h2 { margin: 0; font-size: var(--font-size-lg); font-weight: 650; color: var(--color-fg-default); }
.sechead .right { margin-left: auto; }
.microlabel {                          /* the only label style. mono, uppercase, tracked */
  font-family: var(--font-family-mono); font-size: var(--font-size-2xs); font-weight: 500;
  letter-spacing: var(--tracking-label); text-transform: uppercase;
  color: var(--color-fg-muted);
}
h3.microlabel { margin: var(--space-4) 0 0; font-weight: 600; }

/* ---------- 7. stat strip - divided cells, never card tiles ---------- */
/* One baseline across a divided strip comes from equalising the LABEL box, not from
 * pinning the value to the cell bottom. Cell height varies with things that have
 * nothing to do with the label - a 3-line prose value (index, Scheduling), a .meter
 * under the figure (status, Budget utilization) - so a bottom pin misaligns exactly
 * those cells and orphans short values from their labels. A two-line label box costs
 * 15px once per strip and is correct in every case, including wrapped labels
 * ("Collector timeout (s)", "Appliances (MX)", "Exporter Self-Instrumentation"). */
.stat .microlabel, .grid .cell .microlabel { min-height: 30px; }
.stats {
  display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; flex: none;
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border-default);
}
.stats .stat {
  padding: 11px var(--space-5); border-right: 1px solid var(--color-border-default);
  display: flex; flex-direction: column;
}
.stats .stat:last-child { border-right: 0; }
.stat .figure {
  margin-top: 2px; font-size: var(--font-size-2xl); font-weight: 650;
  color: var(--color-fg-default); letter-spacing: -0.02em; font-variant-numeric: tabular-nums;
}
.stat .row2 { display: flex; align-items: baseline; gap: 7px; margin-top: 2px; }
.stat .sub { font-family: var(--font-family-mono); font-size: var(--font-size-xs); color: var(--color-fg-muted); }

/* an inline grid of the same cells, used inside a section instead of at page level */
.grid {
  display: grid; grid-auto-flow: column; grid-auto-columns: 1fr;
  margin-top: 10px; background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
}
.grid.attached { border-top: 0; }      /* when it sits directly under a .sechead rule */
.grid .cell {
  padding: 9px 14px; border-right: 1px solid var(--color-border-default);
  display: flex; flex-direction: column;
}
.grid .cell:last-child { border-right: 0; }
.grid .value {
  margin-top: 1px; font-family: var(--font-family-mono); font-size: var(--font-size-lg);
  font-weight: 600; color: var(--color-fg-default); font-variant-numeric: tabular-nums;
}
.grid .value .unit { font-size: var(--font-size-xs); font-weight: 400; color: var(--color-fg-muted); }

/* ---------- 8. the dense reference table. This is the definitive pattern. ---------- */
.tbl-box {
  margin-top: 10px; overflow-x: auto;
  background: var(--color-bg-surface); border: 1px solid var(--color-border-default);
}
.tbl-box.attached { border-top: 0; }
table.data { width: 100%; border-collapse: collapse; }
table.data.sticky-col { border-collapse: separate; border-spacing: 0; }

table.data th {
  position: sticky; top: 0; z-index: 2;
  padding: 7px 12px; text-align: left; white-space: nowrap;
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border-strong);
  font-family: var(--font-family-mono); font-size: var(--font-size-2xs); font-weight: 600;
  letter-spacing: 0.12em; text-transform: uppercase; color: var(--color-fg-muted);
  user-select: none;
}
table.data th.num, table.data td.num { text-align: right; }
table.data th.sortable { cursor: pointer; }
table.data th.sortable:hover { color: var(--color-fg-default); }
/* sort state is a mono arrow appended to the label, plus full-strength ink.
 * No icon: the arrow is text, so it survives sorting a 19-column table without 19 SVGs. */
table.data th[aria-sort] { color: var(--color-fg-default); }
table.data th[aria-sort="ascending"]::after  { content: " \2191"; }
table.data th[aria-sort="descending"]::after { content: " \2193"; }

table.data tbody tr { height: var(--row-table); }
table.data td {
  padding: 0 12px; border-bottom: 1px solid var(--color-border-default);
  font-size: var(--font-size-sm); font-variant-numeric: tabular-nums;
}
table.data.tight td, table.data.tight th { padding: 0 10px; }
table.data.tight tbody tr { height: 34px; }
table.data tbody tr:last-child td { border-bottom: 0; }
table.data tbody tr:hover { background: var(--row-hover); }
table.data tr.row-warn { background: var(--row-warn); }
table.data tr.row-fail { background: var(--row-fail); }
table.data tr.row-warn:hover, table.data tr.row-fail:hover { background: var(--row-hover); }

/* cell roles */
td.key   { font-family: var(--font-family-mono); font-weight: 500; color: var(--color-fg-default); }
td.ink   { color: var(--color-fg-default); }
td.dim   { color: var(--color-fg-muted); }
td.machine { font-family: var(--font-family-mono); color: var(--color-fg-soft); }
td.note  { font-size: var(--font-size-xs); color: var(--color-fg-muted); }
td.empty::after { content: "-"; color: var(--color-fg-faint); }
td.trunc { max-width: 170px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* sticky first column - clients only. The sticky cell owns its own background,
 * so it does not pick up the row hover tint; that is intended and readable. */
table.data.sticky-col th:first-child,
table.data.sticky-col td:first-child {
  position: sticky; left: 0;
  background: var(--color-bg-surface);
  border-right: 1px solid var(--color-border-default);
}
table.data.sticky-col th:first-child { z-index: 4; min-width: 150px; }
table.data.sticky-col td:first-child { z-index: 1; }

/* ---------- 9. status - shape plus word, never colour alone ---------- */
.st {
  font-family: var(--font-family-mono); font-size: var(--font-size-xs); font-weight: 600;
  white-space: nowrap; letter-spacing: 0.04em;
}
.st-ok   { color: var(--color-status-ok); }     /* content starts with the glyph: "\25A0 OK"   */
.st-warn { color: var(--color-status-warn); }   /*                               "\25C6 WARN" */
.st-fail { color: var(--color-status-fail); }   /*                               "\25CF FAIL" */
.st-info { color: var(--color-bg-accent); }     /*                               "\25B6 YES"  */
.st-none { color: var(--color-fg-muted); }
.st-lg { font-size: var(--font-size-sm); }
/* the same three glyphs carry into figures, so a stat reads without colour */
.figure.ok, .value.ok     { color: var(--color-status-ok); }
.figure.warn, .value.warn { color: var(--color-status-warn); }
.figure.fail, .value.fail { color: var(--color-status-fail); }

/* ---------- 10. banners, alerts, notices ---------- */
.banner {
  display: flex; align-items: flex-start; gap: 11px; flex: none;
  padding: 11px var(--space-5);
  background: var(--color-bg-accent-soft);
  border-top: 1px solid var(--color-border-default);
  border-bottom: 1px solid var(--color-border-default);
}
.banner.warn { background: color-mix(in oklab, var(--color-status-warn) 9%, var(--color-bg-surface)); }
.banner.fail { background: color-mix(in oklab, var(--color-status-fail) 9%, var(--color-bg-surface)); }
.banner .icon { margin-top: 2px; }
.banner .t { font-size: var(--font-size-md); font-weight: 600; color: var(--color-fg-default); }
.banner .d { font-size: var(--font-size-sm); color: var(--color-fg-soft); }
.banner .pills { margin-left: auto; display: flex; gap: var(--space-2); flex-wrap: wrap; }
.pill {
  font-family: var(--font-family-mono); font-size: var(--font-size-xs);
  color: var(--color-fg-soft);
  border: 1px solid var(--color-border-strong); border-radius: var(--radius-control);
  padding: 1px 6px;
}
.pill.pending { color: var(--color-status-warn); border-color: var(--color-status-warn); }

.alert-list { margin-top: 10px; background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default); border-top: 0; }
.alert {
  display: flex; align-items: baseline; gap: 10px;
  padding: 9px 14px; border-bottom: 1px solid var(--color-border-default);
  border-left: 3px solid transparent;
}
.alert:last-child { border-bottom: 0; }
.alert.warn { border-left-color: var(--color-status-warn);
  background: color-mix(in oklab, var(--color-status-warn) 6%, var(--color-bg-surface)); }
.alert.fail { border-left-color: var(--color-status-fail);
  background: color-mix(in oklab, var(--color-status-fail) 6%, var(--color-bg-surface)); }
.alert .st { width: 88px; flex: none; }
.alert .name { font-family: var(--font-family-mono); font-size: var(--font-size-sm);
  font-weight: 500; color: var(--color-fg-default); }
.alert .n { margin-left: auto; font-family: var(--font-family-mono); font-size: var(--font-size-sm);
  color: var(--color-fg-soft); font-variant-numeric: tabular-nums; }

.callout {                             /* skipped collectors, single warn block */
  display: flex; align-items: flex-start; gap: 10px; margin-top: 14px;
  padding: 11px 14px;
  border: 1px solid var(--color-status-warn); border-left-width: 3px;
  background: color-mix(in oklab, var(--color-status-warn) 8%, var(--color-bg-surface));
}
.callout .icon { margin-top: 2px; color: var(--color-status-warn); }
.callout p { margin: 4px 0 0; font-size: var(--font-size-sm); color: var(--color-fg-soft); }

/* ---------- 11. empty and waiting states ---------- */
.empty {
  margin-top: 10px; padding: 44px var(--space-5); text-align: center;
  background: var(--color-bg-surface); border: 1px solid var(--color-border-default);
}
.empty.attached { border-top: 0; }
.empty .icon { width: 22px; height: 22px; color: var(--color-fg-faint); }
.empty h2 { margin: var(--space-2) 0 0; font-size: var(--font-size-lg); font-weight: 650;
  color: var(--color-fg-default); }
.empty p { margin: 3px 0 0; font-size: var(--font-size-sm); color: var(--color-fg-soft); }
.empty .hint { margin-top: 10px; font-family: var(--font-family-mono);
  font-size: var(--font-size-xs); color: var(--color-fg-muted); }

/* ---------- 12. filter bar and search ---------- */
.filters {
  display: flex; align-items: center; gap: 10px; flex: none;
  padding: 9px var(--space-5);
  background: var(--color-bg-canvas);
  border-bottom: 1px solid var(--color-border-default);
}
.filters.inline { padding: 10px 0 0; background: none; border: 0; }
.search {
  display: flex; align-items: center; gap: 7px; width: 340px;
  padding: 4px 9px; color: var(--color-fg-faint);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-strong); border-radius: var(--radius-control);
}
.search:focus-within { border-color: var(--color-bg-accent); }
.search input {
  width: 100%; border: 0; outline: 0; background: none;
  font: inherit; font-size: var(--font-size-sm); color: var(--color-fg-default);
}
.search input::placeholder { color: var(--color-fg-faint); }
.count { margin-left: auto; font-family: var(--font-family-mono);
  font-size: var(--font-size-xs); color: var(--color-fg-muted); }

/* ---------- 13. meter - magnitude inside a cell ---------- */
.meter { height: 4px; margin-top: 5px; background: var(--meter-track); }
.meter > i { display: block; height: 100%; background: var(--color-bg-accent); }
.meter > i.warn { background: var(--color-status-warn); }
.meter > i.fail { background: var(--color-status-fail); }
/* zero renders as nothing: omit the whole .meter when the value is 0 and dim the figure */

/* ---------- 14. tag list - label sets, metric lists ---------- */
.taglist { display: flex; flex-wrap: wrap; gap: 4px; padding: 8px 0 10px; }
.tag {
  font-family: var(--font-family-mono); font-size: var(--font-size-xs); color: var(--color-fg-soft);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-default); border-radius: var(--radius-control);
  padding: 1px 6px;
}
/* inside a table cell a label set is plain space-separated mono text, not tags.
   Tags are for the expandable "show N metrics" lists only. */
.labelset { font-family: var(--font-family-mono); font-size: var(--font-size-xs);
  color: var(--color-fg-muted); }

/* ---------- 15. pagination ---------- */
.pager { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 12px 0; }
.pager .page-info { font-family: var(--font-family-mono); font-size: var(--font-size-xs);
  color: var(--color-fg-muted); font-variant-numeric: tabular-nums; }

/* ---------- 16. narrow viewports ---------- */
@media (max-width: 900px) {
  body { overflow: auto; }
  .content { overflow: visible; }
  .stats { grid-auto-flow: row; grid-auto-columns: auto; }
  .stats .stat { border-right: 0; border-bottom: 1px solid var(--color-border-default); }
  .grid { grid-auto-flow: row; grid-auto-columns: auto; }
  .grid .cell { border-right: 0; border-bottom: 1px solid var(--color-border-default); }
  .search { width: 100%; }
  .nav { overflow-x: auto; }
}
```

---

## 4. Fonts - hosting expectation

Both families are self-hosted from the package. Zero external network requests: no Google Fonts, no
CDN, no icon font. An exporter on an air-gapped management VLAN must render identically.

Copy four `.woff2` files out of the design system into `static/fonts/`:

| file | family | subset |
| --- | --- | --- |
| `hanken-grotesk-latin.woff2` | Hanken Grotesk (variable, 100-900) | latin |
| `hanken-grotesk-latin-ext.woff2` | Hanken Grotesk (variable, 100-900) | latin-ext |
| `jetbrains-mono-latin.woff2` | JetBrains Mono (variable, 100-800) | latin |
| `jetbrains-mono-latin-ext.woff2` | JetBrains Mono (variable, 100-800) | latin-ext |

Both are SIL OFL 1.1. Ship the two licence files alongside them (`OFL-hanken-grotesk.txt`,
`OFL-jetbrains-mono.txt`) and add both to the FOSSA allowlist. Total added weight is roughly 120 KB
for the four files, served once and cached.

Add to the top of `app.css`, or keep as a third `fonts.css` if you prefer to mirror upstream:

```css
@font-face {
  font-family: "Hanken Grotesk";
  font-style: normal; font-weight: 100 900; font-display: swap;
  src: url("/static/fonts/hanken-grotesk-latin.woff2") format("woff2");
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC,
    U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215,
    U+FEFF, U+FFFD;
}
@font-face {
  font-family: "Hanken Grotesk";
  font-style: normal; font-weight: 100 900; font-display: swap;
  src: url("/static/fonts/hanken-grotesk-latin-ext.woff2") format("woff2");
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1D00-1DBF,
    U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
}
@font-face {
  font-family: "JetBrains Mono";
  font-style: normal; font-weight: 100 800; font-display: swap;
  src: url("/static/fonts/jetbrains-mono-latin.woff2") format("woff2");
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC,
    U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215,
    U+FEFF, U+FFFD;
}
@font-face {
  font-family: "JetBrains Mono";
  font-style: normal; font-weight: 100 800; font-display: swap;
  src: url("/static/fonts/jetbrains-mono-latin-ext.woff2") format("woff2");
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1D00-1DBF,
    U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
}
```

Fallbacks are already in the token stack and are load-bearing, not decorative: if the woff2 files are
stripped from a build, `system-ui` and `ui-monospace` keep every page legible and the mono/sans
distinction intact. The sort arrows, status glyphs and box-drawing characters used in the design
(`\2191 \2193 \25A0 \25C6 \25CF \25B6`) are all inside the latin subset.

---

## 5. Type roles

Machine text dominates these pages, so mono is the default for data and sans is reserved for prose
and headings.

| role | family | size | weight | notes |
| --- | --- | --- | --- | --- |
| page title (`h1`) | sans | 18px | 650 | `letter-spacing: -0.015em` |
| page subtitle | sans | 12.5px | 400 | `--color-fg-muted` |
| section title (`h2`) | sans | 15px | 650 | sits on a `border-strong` rule |
| micro-label | mono | 10px | 500-600 | uppercase, `0.13em`, stat and grid labels, `h3`; two-line box in a stat cell |
| table header | mono | 10px | 600 | uppercase, `0.12em` |
| stat figure | mono-agnostic sans | 24px | 650 | `tabular-nums`, `-0.02em` |
| grid value | mono | 15px | 600 | `tabular-nums` |
| body / prose | sans | 13.5px | 400 | `--color-fg-soft` |
| table cell, prose column | sans | 12.5px | 400 | descriptions, manufacturer, OS |
| table cell, machine | mono | 12.5px | 400-500 | metric names, MACs, IPs, serials, hostnames, timestamps, counts |
| status word | mono | 11px | 600 | glyph + word, `0.04em` |
| chip / pill / meta | mono | 10-11px | 400-500 | version, commit, uptime, port, cadence |
| documentation column | sans | 11px | 400 | `--color-fg-muted` |

Everything that is a count, an identifier, a duration or a timestamp is mono with `tabular-nums`.
Everything a human wrote is sans.

---

## 6. `templates/_base.html`

One header, one nav, one theme toggle, for all six pages. This is where six duplicated `<head>`
blocks go to die.

```jinja
<!DOCTYPE html>
<html lang="en" data-theme="{{ theme_default | default('') }}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Meraki Dashboard Exporter{% endblock %}</title>
  <script>
    /* Applied before first paint so a dark-mode operator never sees a light flash.
     * No stored preference means the OS decides via prefers-color-scheme. */
    try {
      var t = localStorage.getItem("mde-theme");
      if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
    } catch (e) {}
  </script>
  <link rel="stylesheet" href="/static/css/tokens.css">
  <link rel="stylesheet" href="/static/css/app.css">
  {% block head %}{% endblock %}
</head>
<body>
  <div class="brandbar">
    <span class="mark"></span>
    <b class="name">Meraki Dashboard Exporter</b>
    <span class="chip">v{{ version }}</span>
    <span class="right">
      <span class="meta">uptime {{ uptime }}</span>
      <span class="meta">{{ commit }}</span>
      <button class="btn" id="theme-toggle" type="button" aria-live="polite">
        {% include "_icons/moon.svg" %}<span>Dark</span>
      </button>
    </span>
  </div>

  <nav class="nav">
    <a href="/"            {% if page == 'index'       %}aria-current="page"{% endif %}>{% include "_icons/gauge.svg" %}Overview</a>
    <a href="/clients"     {% if page == 'clients'     %}aria-current="page"{% endif %}>{% include "_icons/users-three.svg" %}Clients</a>
    <a href="/status"      {% if page == 'status'      %}aria-current="page"{% endif %}>{% include "_icons/pulse.svg" %}Status</a>
    <a href="/cardinality" {% if page.startswith('cardinality') %}aria-current="page"{% endif %}>{% include "_icons/tag.svg" %}Cardinality</a>
    <span class="port">:{{ port }}</span>
  </nav>

  {% if page.startswith('cardinality') %}
  <div class="subnav">
    <span class="microlabel group">Cardinality</span>
    <a href="/cardinality"              {% if page == 'cardinality'             %}aria-current="page"{% endif %}>Overview</a>
    <a href="/cardinality/all-metrics"  {% if page == 'cardinality_all_metrics' %}aria-current="page"{% endif %}>All metrics</a>
    <a href="/cardinality/all-labels"   {% if page == 'cardinality_all_labels'  %}aria-current="page"{% endif %}>All labels</a>
    <a class="count" href="/cardinality/export/json" download="cardinality_export.json">{% include "_icons/download-simple.svg" %}Export JSON</a>
  </div>
  {% endif %}

  <div class="pagehead">
    <div>
      <h1>{% block h1 %}{% endblock %}</h1>
      <p>{% block lede %}{% endblock %}</p>
    </div>
    <div class="right">{% block headmeta %}{% endblock %}</div>
  </div>

  <div class="content">{% block content %}{% endblock %}</div>

  <script src="/static/js/ui.js" defer></script>
  {% block scripts %}{% endblock %}
</body>
</html>
```

Every route handler gains two context keys: `page` (the identifier used above) and `port`. `version`,
`uptime` and `commit` already exist on `/` and `/status`; pass them to all six so the brand bar is
identical everywhere, including the auth-gated pages. The gated pages get exactly this chrome - no
marketing framing, no reduced header.

### `static/js/ui.js`

Everything the pages need, and nothing they do not. Replaces the three separate copies of the
sort/filter code currently inlined in `cardinality.html`, `cardinality_all_metrics.html`,
`cardinality_all_labels.html` and `clients.html`.

```js
/* theme toggle - 3 states collapse to 2: whatever you see now, give me the other one */
(function () {
  var btn = document.getElementById("theme-toggle");
  if (!btn) return;
  function current() {
    var set = document.documentElement.dataset.theme;
    if (set === "light" || set === "dark") return set;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function label() {
    var next = current() === "dark" ? "light" : "dark";
    btn.lastElementChild.textContent = next === "dark" ? "Dark" : "Light";
    btn.setAttribute("aria-label", "Switch to " + next + " theme");
  }
  btn.addEventListener("click", function () {
    var next = current() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("mde-theme", next); } catch (e) {}
    label();
  });
  label();
})();

/* sortable columns - opt in with <th class="sortable" data-type="numeric"> */
document.querySelectorAll("table.data").forEach(function (table) {
  var tbody = table.tBodies[0];
  if (!tbody) return;
  var original = Array.prototype.slice.call(tbody.rows);
  table.querySelectorAll("th.sortable").forEach(function (th, i) {
    var index = th.cellIndex;
    th.setAttribute("tabindex", "0");
    th.setAttribute("role", "columnheader");
    function go() {
      var order = th.getAttribute("aria-sort") === "ascending" ? "descending"
                : th.getAttribute("aria-sort") === "descending" ? null : "ascending";
      table.querySelectorAll("th").forEach(function (o) { o.removeAttribute("aria-sort"); });
      if (!order) { original.forEach(function (r) { tbody.appendChild(r); }); return; }
      th.setAttribute("aria-sort", order);
      var dir = order === "ascending" ? 1 : -1;
      var numeric = th.dataset.type === "numeric";
      Array.prototype.slice.call(tbody.rows).sort(function (a, b) {
        var av = value(a.cells[index]), bv = value(b.cells[index]);
        if (numeric) return dir * (num(av) - num(bv));
        return dir * av.localeCompare(bv);
      }).forEach(function (r) { tbody.appendChild(r); });
    }
    th.addEventListener("click", go);
    th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
  function value(cell) { return (cell.dataset.sort || cell.dataset.value || cell.textContent).trim(); }
  function num(s) { return parseFloat(s.replace(/[^0-9.-]/g, "")) || 0; }
});

/* filter - <input data-filter-table="metrics-table"> hides non-matching rows and
   any section left with none */
document.querySelectorAll("[data-filter-table]").forEach(function (input) {
  input.addEventListener("input", function () {
    var q = input.value.toLowerCase();
    document.querySelectorAll("#" + input.dataset.filterTable + " tbody tr").forEach(function (row) {
      var hit = row.textContent.toLowerCase().indexOf(q) !== -1;
      row.hidden = !hit;
    });
    document.querySelectorAll("[data-section-of='" + input.dataset.filterTable + "']").forEach(function (s) {
      s.hidden = !s.querySelector("tbody tr:not([hidden])");
    });
    var c = document.querySelector("[data-count-for='" + input.dataset.filterTable + "']");
    if (c) {
      var t = document.querySelectorAll("#" + input.dataset.filterTable + " tbody tr");
      var v = document.querySelectorAll("#" + input.dataset.filterTable + " tbody tr:not([hidden])");
      c.textContent = v.length + " of " + t.length + " shown";
    }
    if (window.__paginate) window.__paginate.reset();
  });
});

/* disclosure - <button data-expands="metrics-7"> */
document.querySelectorAll("[data-expands]").forEach(function (btn) {
  var target = document.getElementById(btn.dataset.expands);
  if (!target) return;
  target.hidden = true;
  btn.addEventListener("click", function () {
    target.hidden = !target.hidden;
    btn.textContent = btn.textContent.replace(target.hidden ? "Hide" : "Show", target.hidden ? "Show" : "Hide");
    btn.classList.toggle("btn-primary", !target.hidden);
  });
});
```

Pagination on `/cardinality/all-metrics` keeps its existing 50-rows-per-page implementation; move it
into `ui.js` behind `window.__paginate` and drop it from the template. It is the only page-specific
script left.

---

## 7. Phosphor icon set

Regular weight, one set, used sparingly. Ship each as a Jinja partial in `templates/_icons/` so the
markup stays readable and the SVG is not duplicated per page. Every file is the same shape:

```html
<svg class="icon" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true" focusable="false"><path d="..."/></svg>
```

Icons are decorative: they always sit beside a word, never alone, and always carry
`aria-hidden="true"`.

| partial | Phosphor name | used on |
| --- | --- | --- |
| `gauge.svg` | gauge | nav: Overview |
| `users-three.svg` | users-three | nav: Clients |
| `pulse.svg` | pulse | nav: Status |
| `tag.svg` | tag | nav: Cardinality; high-cardinality-labels section |
| `check-circle.svg` | check-circle | healthy banners, health check OK |
| `warning.svg` | warning | warn banners, skipped collectors, high cardinality |
| `x-circle.svg` | x-circle | critical cardinality banner |
| `clock.svg` | clock | polling diagnostics section |
| `plugs-connected.svg` | plugs-connected | available endpoints section |
| `chart-line.svg` | chart-line | top metrics by cardinality |
| `siren.svg` | siren | active alerts |
| `lightbulb.svg` | lightbulb | threshold recommendations |
| `hourglass.svg` | hourglass | waiting-for-first-run and no-data states |
| `magnifying-glass.svg` | magnifying-glass | every search field |
| `download-simple.svg` | download-simple | export JSON |
| `moon.svg` / `sun.svg` | moon, sun | theme toggle |

Sixteen partials, roughly 7 KB of markup in total. Source: `phosphor-icons/core`,
`assets/regular/<name>.svg`, MIT licensed. Copy the files as-is and add `class="icon"`,
`fill="currentColor"` and `aria-hidden="true"` to the root `<svg>`; do not re-draw them.

The sort affordance is deliberately not an icon. A 19-column table would need 19 inline SVGs that
change on every click; a mono `\2191` / `\2193` appended by CSS to the active header does the same
job for free (section 3, `table.data th[aria-sort]`).

---

## 8. Per-page notes

All six keep their current information architecture: same purposes, same tables, same columns, same
data. What changes is where the CSS lives and what the chrome looks like.

### 8.1 `index.html` - Overview

- Delete the entire `<style>` block (about 300 lines). Nothing in it survives.
- `extends "_base.html"`; `page = "index"`.
- The `.header` white card becomes the `_base` page title bar. `h1` and the lede keep their exact
  current wording.
- The green `.status-banner` becomes `.banner` with `check-circle` and a `\25A0 HEALTH CHECK OK`
  status word in the title bar's right slot. Copy unchanged.
- The three `.card` tiles are dissolved. Getting Started was a link to `/metrics`, which the endpoint
  table already lists, so it goes; Exporter Stats becomes the page-level `.stats` strip (uptime,
  active collectors, organizations, total metrics, time series); Configuration becomes a three-cell
  `.grid` section at the foot (version, scheduling, org ID) keeping the `{% if org_id %}` guard.
- Polling diagnostics: the two `.stats` rows become `.grid` rows of four and six cells. The scheduler
  summary sentence stays, with `&mdash;` replaced by a spaced hyphen and the inline
  `style="color: #c0392b"` replaced by `class="st st-fail"` with a `\25CF` glyph.
- Collector cadences and Active collectors both become `table.data`. `.cadence-badge` becomes
  `.chip`. `.health-good` / `.health-warning` / `.health-error` become `.st st-ok` / `.st st-warn` /
  `.st st-fail`, each gaining its glyph, and the row itself gains `row-warn` / `row-fail` so a
  degraded collector is findable by scanning, not by reading percentages.
- `.skipped-collectors` becomes `.callout`. Copy unchanged apart from the emoji, which becomes the
  `warning` partial.
- Page-specific CSS remainder: none.

### 8.2 `clients.html` - Network Clients

- Delete the `<style>` block (about 280 lines).
- `page = "clients"`. Title, lede and every column header keep their current wording.
- Order changes so the summary is above the fold: title bar, `.stats` (total, online, offline,
  networks), `.filters` with the search field, DNS cache statistics as a five-cell `.grid`, then one
  section per network.
- `.config-info` (Cache TTL) collapses into a `.meta` line in the title bar's right slot; it is one
  number and did not need a blue box.
- The 19-column table becomes `table.data tight sticky-col` inside `.tbl-box`. All 19 columns stay.
  The header row is sticky vertically and the Description column sticky horizontally, so the row
  identity never scrolls away. `min-width: 1900px` keeps the columns from crushing.
- `.status-online` / `.status-offline` pills become `.st st-ok` `\25A0 ONLINE` and `.st st-fail`
  `\25CF OFFLINE`. `.connection-type` / `.connection-wired` become plain mono `WIRELESS` / `WIRED`
  in `--color-fg-soft` and `--color-fg-default` - the distinction was carried by two pastel fills
  that fail greyscale.
- `.sm-badge` / `.no-sm-badge` become `.st st-ok` `\25A0 YES` and `.st st-none` `\25C6 NO`.
- `.mac-address`, `.ip-address`, `.timestamp`, `.usage-data` all collapse into `td.machine`;
  `.truncate` becomes `td.trunc`. Usage is right-aligned `td.num machine`.
- Each `.network-section` gets `data-section-of="clients-table"` so the search still hides networks
  that no longer match.
- Page-specific CSS remainder: none.

### 8.3 `status.html` - Exporter Status

- Delete the `<style>` block (about 120 lines).
- `page = "status"`. The "Back to home" link goes: the nav supersedes it.
- `.readiness-banner` becomes `.banner` (or `.banner.warn` when not ready) with a `\25A0 READY` /
  `\25C6 NOT READY` status word and the per-collector `.pill` set. `.status-complete` /
  `.status-pending` become `.pill` / `.pill.pending`.
- The four `.card` blocks become four `.tbl-box` / `.grid` sections under `.sechead` rules.
  API health and Data freshness sit side by side in a two-column grid at wide widths.
- `.badge-ok` / `-warning` / `-stale` / `-running` become `.st st-ok` / `st-warn` / `st-fail` /
  `st-info`, each with its glyph and an uppercase word. `.row-warning` / `.row-stale` become
  `.row-warn` / `.row-fail`, so a stale collector is legible in greyscale from the word, from the
  glyph and from the row tint.
- Budget utilization gains a `.meter` under the figure - the one derived-value magnitude on the page
  that reads faster as a bar. Zero utilization shows no track.
- The `<dl class="collector-breakdown">` inline definition list becomes a two-column
  `table.data tight`; run-together `dt`/`dd` pairs were unreadable past four collectors.
- Endpoint groups: stretched groups get `row-warn` and a `\25C6` on the stretch factor; a pinned
  group gets `.st st-info` `\25C6 PINNED`.
- Page-specific CSS remainder: none.

### 8.4 `cardinality.html` - Cardinality Monitor

The dense reference page. Its treatment is the source; the other five derive from it.

- Delete the `<style>` block (about 420 lines, the largest single win).
- `page = "cardinality"`. The "Back to Home" link goes; the sub-nav in `_base` replaces both it and
  the Quick Actions duplication.
- `.loading-notice` (first run pending) becomes `.empty` with the `hourglass` partial. Its 5-second
  `setTimeout` reload stays exactly as it is.
- `.status-banner.{healthy,warning,critical}` becomes `.banner` / `.banner.warn` / `.banner.fail`
  with `check-circle` / `warning` / `x-circle` and a glyph on the title. All three copy variants
  unchanged.
- The nine `.stat-card` tiles become two `.stats` rows: five series and metric counts, then four
  cells for warning count, critical count and the two thresholds. Labels keep their current
  wording verbatim, including "Exporter Self-Instrumentation" and "Cardinality Monitor Series",
  which wrap to two lines - the reserved label box in section 3 keeps all five figures on one
  baseline. Counts carry `\25C6` and `\25CF`
  so "3 warnings" is not amber-only.
- `.recommendations` (blue box) becomes a normal `.sechead` section with `lightbulb`, one row per
  recommendation, the type as a mono micro-label.
- `.alert-item` becomes `.alert` in an `.alert-list`, one line per alert: status word, metric name,
  series count and type. The current two-line heading-plus-paragraph shape wasted a row per alert
  and there can be dozens.
- Top metrics by cardinality: `table.data` with a sticky header. `.cardinality-badge` fills are
  replaced by a glyph plus coloured figure (`\25A0` / `\25C6` / `\25CF`) and the row tint - a filled
  pill in every row of a 200-row table is visual noise. `.metric-type` pill becomes plain uppercase
  mono. `.label-tag` chips become one space-separated mono `.labelset` string; 6 chips per row across
  200 rows was 1,200 bordered boxes. The truncated documentation column keeps its `[:100]` slice.
- High cardinality labels: same treatment, `.label-tag` becomes `td.key`.
- Growth rate: unchanged shape as `table.data tight`. Positive growth is `st-fail`, negative is
  `st-ok`, zero is `--color-fg-muted` - the current colouring is already correct, it only gains signs
  and tabular figures.
- Quick actions: `.action-link` becomes `.btn-primary` for All metrics and `.btn` for the rest.
- The three empty states keep their copy, become `.empty`, and keep the conditional auto-reload
  script at the foot.
- Page-specific CSS remainder: none. All four tables use the shared `table.data`.

### 8.5 `cardinality_all_metrics.html` - All Metrics

- Delete the `<style>` block (about 240 lines).
- `page = "cardinality_all_metrics"`. Nav link and Back link go, sub-nav supersedes them.
- The `.stats-card` "184 / Total Metrics" hero becomes a figure plus micro-label in the title bar's
  right slot.
- `.search-box` becomes `.filters`; the row count moves to `.count` with `data-count-for`.
- `table.data` with sticky header, six columns unchanged. The hardcoded 10,000 / 1,000 thresholds
  in the badge conditional stay as they are; they are the page's own defaults, not the report's.
- `.pagination` becomes `.pager`; buttons become `.btn`. 50 rows per page unchanged.
- Page-specific CSS remainder: the pagination script, moved to `ui.js`.

### 8.6 `cardinality_all_labels.html` - All Labels

- Delete the `<style>` block (about 230 lines).
- `page = "cardinality_all_labels"`. Same title-bar figure treatment as All Metrics.
- `.label-name` (blue mono pill) becomes `td.key` - a bordered blue box on every row of a 27-row
  table added nothing the mono weight does not.
- `.show-metrics-btn` becomes `.btn-sm` with `data-expands="metrics-{{ loop.index }}"`; the expanded
  `.metrics-container` becomes `.taglist` of `.tag` spans. Expanded state turns the button
  `.btn-primary`, matching the existing `.expanded` behaviour without the amber fill.
- The bespoke `toggleMetrics()` function is deleted; the shared disclosure handler covers it.
- Page-specific CSS remainder: none.

---

## 9. AA measurements

Every pair below was computed from the token values in section 2 - OKLCH and hex converted to sRGB,
`color-mix(in oklab, ...)` interpolated in Oklab, WCAG 2.1 relative luminance. Threshold is 4.5:1 for
text and 3:1 for large text and UI boundaries.

### Text pairs

| foreground | background | light | dark |
| --- | --- | --- | --- |
| `fg-default` | `bg-canvas` | 14.72 | 14.43 |
| `fg-default` | `bg-surface` | 15.60 | 13.49 |
| `fg-default` | `bg-raised` | 16.41 | 12.25 |
| `fg-default` | `bg-accent-soft` | 13.94 | 10.91 |
| `fg-default` | `row-warn` | 14.22 | 12.25 |
| `fg-default` | `row-fail` | 14.09 | 12.39 |
| `fg-soft` | `bg-surface` | 9.87 | 9.16 |
| `fg-soft` | `bg-canvas` | 9.31 | 9.80 |
| `fg-soft` | `bg-accent-soft` | 8.82 | 7.40 |
| `fg-soft` | warn banner (9%) | 8.76 | 8.06 |
| `fg-muted` | `bg-surface` | 5.67 | 6.42 |
| `fg-muted` | `bg-canvas` | 5.35 | 6.86 |
| `fg-muted` | `row-warn` | 5.17 | 5.82 |
| `fg-muted` | `row-hover` | 5.36 | 6.09 |
| `bg-accent` (link) | `bg-surface` | 5.73 | 6.89 |
| `bg-accent` (link) | `bg-canvas` | 5.41 | 7.38 |
| `bg-accent` (link) | `bg-accent-soft` | 5.12 | 5.57 |
| `bg-accent` (link) | `row-hover` | 5.42 | 6.54 |
| `fg-on-accent` | `bg-accent` | 6.03 | 7.38 |
| `status-ok` | `bg-surface` | 4.79 | 6.38 |
| `status-ok` | `row-hover` | 4.53 | 6.05 |
| `status-warn` | `bg-surface` | 4.99 | 7.00 |
| `status-warn` | `row-warn` | 4.55 | 6.35 |
| `status-warn` | `row-hover` | 4.72 | 6.64 |
| `status-fail` | `bg-surface` | 6.03 | 5.66 |
| `status-fail` | `row-fail` | 5.45 | 5.20 |
| `status-fail` | `row-hover` | 5.70 | 5.37 |

Lowest text pair in either theme: `status-ok` on a hovered row, 4.53:1 light. Everything passes.

### Non-text pairs (3:1 not required; listed for completeness)

| pair | light | dark |
| --- | --- | --- |
| `border-strong` / `bg-surface` | 1.66 | 1.86 |
| `border-default` / `bg-surface` | 1.28 | 1.30 |
| `meter-track` / `bg-surface` | 1.37 | 1.36 |
| `bg-accent` (meter fill) / `meter-track` | 4.18 | 5.07 |

Hairlines are structure, not information: no rule in the design is the only thing distinguishing two
states. The meter fill against its own track clears 3:1 in both themes.

### The one finding worth recording

The design system's `--color-bg-hover` is a *darker* surface in light theme
(`oklch(0.945)` against a `0.982` surface). Using it as the table row hover put `status-ok` at
**4.30:1** - the only AA failure in the whole set, and only on hover, which is exactly the state a
contrast script that samples static colours would never catch.

The fix is one derived token, and it is in section 2:

```css
--row-hover: color-mix(in oklab, var(--color-bg-accent) 4%, var(--color-bg-surface));
```

A 4% accent tint is visually equivalent as a hover cue and keeps `status-ok` at 4.53 light / 6.05
dark. `--color-bg-hover` remains correct for nav items and buttons, which carry no status colour.
This is the same class of failure FOUNDATIONS records for meter tracks, found in the same way.

`--color-fg-faint` is used only for placeholders, disabled button text and the em-dash-substitute
`-` in empty cells. It is exempt by the design system's own note and carries no information.

---

## 10. Assumptions

Where the repo and the brief left a gap, this is what was assumed. Each is cheap to reverse.

1. **`/static` is new.** The repo has no static mount today; every template is self-contained. The
   spec adds one. If the deployment has a reason to keep the exporter to a single-file-per-route
   model, the two stylesheets can be inlined into `_base.html` instead and everything else holds -
   the cost is losing browser caching across the six pages.
2. **Sample data in the design is illustrative.** Collector names (`OrganizationCollector`,
   `DeviceCollector`, `NetworkHealthCollector`, `MTSensorCollector`, `ConfigCollector`,
   `ClientsCollector`, `AlertsCollector`), endpoint group names (`nh_connection_stats`,
   `device_statuses`, `mt_sensor_readings`, `switch_port_statuses`, `org_licenses`,
   `org_api_requests`, `network_clients`) and metric names (`meraki_device_up`,
   `meraki_client_usage_kb`, `meraki_ms_port_traffic_bytes`, `meraki_mt_temperature_celsius`,
   `meraki_network_filter_match`, `meraki_org_has_beta_api`) are plausible values drawn from the
   README and templates, not a live scrape. Column headers, section titles and copy strings are
   verbatim from the templates and are not assumptions.
3. **`commit` and `port` are available to every route.** The README says both are known
   (`meraki_exporter_build_info`, default 9099). If the port is not in template context, drop the
   `:9099` element from the nav; it is decorative.
4. **Theme preference is per-browser, not per-deployment.** No server-side theme setting, no cookie,
   no config flag. `localStorage` on `mde-theme` with OS preference as the default. The
   `theme_default` context key in `_base.html` is an optional hook if a deployment ever wants to
   force one.
5. **`localStorage` may be unavailable.** Every access is wrapped in `try/catch`; the toggle still
   works for the session, it just does not persist.
6. **Column visibility on `/clients` was not added.** All 19 columns stay visible with horizontal
   scroll and a sticky Description column. A per-column toggle would need state and chrome the brief
   did not ask for.
7. **The auth-gated pages get identical chrome.** `/clients`, `/status` and `/cardinality` render the
   same brand bar and nav as `/`. Nothing in the design signals "this page is sensitive", because
   the gate is a deployment concern and duplicating it in the UI would be an operator-visible lie
   when the gate is off.
8. **The `/metrics` and `/health` endpoints are untouched.** They appear in the Overview endpoint
   table as links only.
9. **Emoji are removed everywhere.** `\1F3AF \1F4CA \1F527 \23F1 \1F6A8 \1F4C8 \1F3F7 \1F4A1 \26A0 \23F3`
   in the current templates each become the Phosphor partial named in section 7. Section wording is
   otherwise unchanged.
10. **Cardinality badge thresholds stay hardcoded** at 1,000 and 10,000 in
    `cardinality_all_metrics.html` and `cardinality_all_labels.html`, matching current behaviour,
    even though `cardinality.html` reads them from `report.summary`. Unifying them is a behaviour
    change and out of scope.
11. **`just check` will need the new paths registered** if it lints or formats CSS and JS. The two
    stylesheets are generated-adjacent (`tokens.css` is copied from upstream and should be excluded
    from hand-edit linting, like the repo's other generated files); `app.css` and `ui.js` are
    hand-written and should be included.
