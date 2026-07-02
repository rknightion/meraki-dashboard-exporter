# Live-API verification — captured samples & what still needs live checks

Captured 2026-07-02 against Rob's homelab: **org `1019781` ("Knight")**, single network
**`L_676102894059020286` ("Mitchell Drive", productTypes: sensor, switch, wireless)**.
Hardware in scope: MR56 APs, MS switches (MS120/MS220/MS250), 8× MT sensors, 2× MV
licenses, SM licenses. Licensing model: **co-termination**. NOT present: MX, MG,
Insight, subscription licensing.

**API access for implementers:** the repo-root `.env` (gitignored, never commit) contains
a working `MERAKI_EXPORTER_MERAKI__API_KEY` for this org. Plain curl works:
`curl -s -H "X-Cisco-Meraki-API-Key: $KEY" "https://api.meraki.com/api/v1/..."`.
Read-only calls only; this is Rob's production homelab.

## Sample 1 — channel utilization: THE SPEC IS WRONG (backs #512, cautions #271/#541)

`GET /networks/L_676102894059020286/networkHealth/channelUtilization?timespan=600&resolution=600&perPage=100`

```json
[
  {
    "serial": "Q3AB-VDGT-R59K",
    "model": "MR56",
    "tags": " recently-added ",
    "wifi0": [
      {"utilization": 12.67, "wifi": 9.47, "non_wifi": 3.2,
       "start_ts": "2026-07-02T17:20:00Z", "end_ts": "2026-07-02T17:30:00Z"}
    ],
    "wifi1": [
      {"utilization": 3.04, "wifi": 0.65, "non_wifi": 2.39,
       "start_ts": "2026-07-02T17:20:00Z", "end_ts": "2026-07-02T17:30:00Z"}
    ]
  }
]
```

Spec v1.72.0 claims fields `utilizationTotal` / `utilization80211` / `utilizationNon80211`
/ `startTime` / `endTime` — **none of those exist on the wire**. Consequences (all in
#512): code's `utilization`/`wifi` reads are CORRECT; `nonWifi` read misses (live is
`non_wifi`) → every `utilization_type="non_wifi"` series is silently 0; the
`endTime`→`endTs` sort fallback keys are both wrong (live is `end_ts`) — inert today
because timespan=600/resolution=600 yields exactly one bucket. Test fixtures currently
mock the CODE's keys, so pytest can't catch this class — fixtures must use this live
shape. When migrating to the org-wide bulk endpoints (#271), verify THEIR live field
names first; do not trust the spec.

## Sample 2 — licenses overview: co-term shape (backs #516)

`GET /organizations/1019781/licenses/overview`

```json
{
  "status": "OK",
  "expirationDate": "Mar 13, 2027 UTC",
  "licensedDeviceCounts": {"MT": 8, "MV": 2, "MS220-8P": 2, "MS250-24P": 1,
                           "MR-ADV": 3, "MS120-8LP": 1, "SM": 10}
}
```

Confirms the co-term branch trigger (`licensedDeviceCounts` present). The subscription-
org payload could NOT be verified here — #516 keeps its live-verification flag; the fix
(prefer overview `states` counts when `licensedDeviceCounts` is absent; treat 400 like
404) is structurally sound regardless.

## Sample 3 — firmware upgrade statuses (backs #526)

`GET /organizations/1019781/firmware/upgrades` → 79 rows; statuses seen:
`["Canceled", "Completed"]`. Note the single-L "Canceled" (spec prose says "Cancelled").
No in-flight upgrade was available, so the `{scheduled, pending, started}` pending-set
remains unverified — check during a real upgrade window.

## Sample 4 — power modules `network` property (backs #508)

`GET /organizations/1019781/devices/powerModules/statuses/byDevice` (first row):

```json
{"mac": "cc:9c:3e:02:94:60", "name": "odin", "network": {"id": "L_676102894059020286"},
 "productType": "switch", "serial": "Q2MW-42Z2-JE5T", "tags": ["recently-added"],
 "slots": [
   {"number": 1, "serial": "Q2BS-PDPL-X9BK", "model": "PWR-MS320-640WAC", "status": "powering"},
   {"number": 2, "serial": null, "model": null, "status": "not connected"}]}
```

Live `network` IS a structured object → the `PowerModuleNetworkRef` Pydantic model is
RIGHT and the spec's bare `object` is merely untyped. The #508 fix is to relax the
apidrift conformance rule (submodel-vs-bare-object → INFO), NOT to loosen the model.

## Sample 5 — application-usage percentage scale (closes APIORG-10, no issue needed)

`GET /organizations/1019781/summary/top/applications/categories/byUsage?quantity=10` →
10 rows; `percentage` values e.g. 99.30, 0.40, 0.23…; **sum ≈ 99.998** → confirmed
0–100 scale, not 0–1. Code is correct; #531's HELP work should state "0-100".

## Which open issues still need live access at implementation time

Verifiable against THIS homelab (key in `.env`): #512 (re-capture channel-util fixture),
#271/#541 (org-wide wireless endpoints field names), #549 partially (2 MV cameras exist —
verify replacement analytics endpoints), #553 (MT readings), #612 (air-marshal fields —
plan-dependent, may be empty), #525 (needs >1000 clients — homelab likely too small;
reason from the URL-length math instead), #594 (golden fixtures from live shapes).

NOT verifiable here (flagged in the issue bodies; verify opportunistically or reason
structurally): #516 (needs a subscription-licensed org), #517/#521/#527 (need MX
hardware), #526 (needs an in-flight firmware upgrade). None of these BLOCK implementation
— each issue states the safe structural fix; live checks tighten confidence.

The Meraki dashboard UI (https://n201.dashboard.meraki.com/) can arbitrate display-unit
questions (kb vs KB vs KiB) if needed during #531 — compare a port's usage figure in the
UI against the API value for the same window.
