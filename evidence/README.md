# V1 readiness assessment — evidence pack (2026-07-02)

Solved research data backing the `v1-readiness` GitHub issues (#508–#617). Implementing
agents should **treat the facts here as verified as of 2026-07-02** against: the code at
commit `f08cd69`, Meraki OpenAPI spec **v1.72.0** (670 paths), installed Meraki SDK
**3.3.0**, and live API calls against Rob's homelab org (see `live-api-verification.md`).
If the code has moved since, re-confirm file:line refs before editing — but do NOT
re-derive the analysis from scratch; it was produced by an 11-lane multi-agent assessment
with adversarial live verification.

## Files

- `findings-synthesis.md` — the master cross-lane synthesis: every finding from all 11
  lanes (scale, resilience, security, v1-gaps, deploy, metrics, api-device, api-org,
  config, tests/CI, docs) with mechanisms, file:line refs, severities, merge notes, and
  the live-API verification verdicts. **Start here.**
- `scale-and-capacity.md` — the full SCALE lane report: per-collector API-call formulas,
  the capacity table (SMALL vs 500-network university scale), rate-limiter defect
  analysis, and the checked-OK list. Backs #540–#557, #270, #617, #542.
- `resilience-failure-modes.md` — the full RES lane report incl. the live fake-key run
  evidence (readiness/liveness lying). Backs #509–#511, #528, #544–#547, #591, #596, #597.
- `metric-contract-audit.md` — the full MET lane report: compact family table, naming/
  typing/unit findings, cardinality-at-scale math, checked-OK list. Backs #531–#539, #533.
- `api-conformance.md` — the APIORG + APIDEV lane reports: per-fetcher verdict tables vs
  spec v1.72.0 + SDK 3.3.0, all findings incl. the two corrections. Backs #512–#527,
  #548–#557, #611, #612.
- `live-api-verification.md` — raw live-API response samples captured during the
  assessment + org/network IDs + exactly which open issues still need live verification
  at implementation time and what hardware the homelab can/cannot verify.

## How issues reference this pack

Issue bodies are self-contained for the change itself; this pack is the deep context
(the "why", the math, the coverage tables). When an issue says
`Source: v1-readiness findings XXX-NN`, the full detail for that finding ID is in
`findings-synthesis.md` (and the per-lane file if one exists).

## Ground rules for implementers

- Decisions recorded in issue bodies (single-org contract, rename-now, ID-only client
  labels, container/Helm-only, no interim releases) are FINAL — do not re-litigate.
- The OpenAPI spec is not always right: `getNetworkNetworkHealthChannelUtilization`'s
  spec schema is wrong vs the live wire format (see #512 / `live-api-verification.md`).
  When an issue flags `Verification-needed: live-API`, do that before coding.
- This folder is development evidence, not customer docs — it is deliberately outside
  `docs/` and excluded from the container image.
