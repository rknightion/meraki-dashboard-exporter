# GitHub Issues archive

`github-issues-2026-08-14.json` is the complete contents of this repository's GitHub Issues tracker as
of **2026-08-14**, captured immediately before most of those issues were deleted. The project moved to
Backlog.md on that date; see the *Closed GitHub issues* doc (`backlog doc list --plain`) for the
browsable index, and this file for the bodies and replies behind it.

**This is the record, not a convenience copy.** 444 of the 455 issues it describes no longer exist on
GitHub, so `gh issue view <N>` 404s for them. Anything in the repository that cites `#NNN` — `AGENTS.md`,
901 commit messages, code comments — resolves here.

## What it contains

455 issues and all 642 comments. Per issue: number, title, body, state, state reason, author, labels,
milestone, assignees, created/updated/closed timestamps, URL, and every comment with its author and
timestamp.

```sh
jq '.[] | select(.number == 694)' archive/github-issues-2026-08-14.json          # one issue
jq -r '.[] | select(.number == 694) | .comments[].body' archive/…                # its replies
jq -r '.[] | select(.title | test("cardinality"; "i")) | "#\(.number) \(.title)"' archive/…
jq -r '.[] | select(.author.login != "rknightion") | "#\(.number) \(.author.login)"' archive/…
```

Comment completeness was verified against the REST API's own per-issue counts before capture
(`gh api --paginate 'repos/.../issues?state=all&per_page=100' --jq '…|.comments'`), because `gh`'s
`--json comments` paginates. 454 of 455 matched exactly. The one that did not is **#170**, Renovate's
dependency dashboard, where the issue object reports `comments: 1` while
`/issues/170/comments` returns `[]` and the timeline carries no comment event — a stale denormalised
counter on GitHub's side, not a comment this archive dropped. #170 is also one of the issues that was
*kept*, so nothing is at risk there either way.

## What was kept on GitHub, and why

The tracker stays **enabled**: external contributors must be able to file, and the support matrix
depends on that channel for sanitised real API responses from device families nobody here owns.

Only issues authored by the maintainer or by a CI app were deleted — 442 plus 2 automated API-drift
reports. **Every issue authored by anyone else was left exactly where it was**, open or closed: nine
issues from six outside contributors. Renovate's dependency dashboards were also left in place, both
the live one and its closed predecessor from the previous Renovate app.

## It is redacted, and the placeholders are stable

Issue bodies quoted identifiers this repository's own rules keep out of tracked files. Committing them
raw would have moved those identifiers from somewhere deletable into permanent public git history, at
the exact moment they were being deleted. **534 substitutions over 172 distinct values.**

| Placeholder | Was |
| --- | --- |
| `<serial-N>` | Meraki device serials |
| `<mac-N>` | device MAC addresses |
| `<net-id-N>` | Meraki network IDs |
| `<device-N>` | access-point host names |
| `<net-name-N>`, `<net-name-site>` | network / site names |
| `<reporter-org-id>`, `<maintainer-org-id>`, `<demo-org-id>` | Meraki organisation IDs |
| `<org-name>` | an organisation name |
| `<address-N>` | street addresses |
| `<coord-N>` | device latitude / longitude values |
| `<dashboard-url-N>` | Meraki dashboard URLs (they embed a shard and a network slug) |
| `<lan-ip>`, `<pod-ip>` | RFC1918 addresses |
| `<soak-host>` | the live soak host's name |
| `<watchtower-container>` | its container name |

**The most sensitive material here was not the maintainer's.** One bug report from an outside
contributor pasted a full `getOrganizationDevices` traceback: their organisation ID and name, network
IDs and site names, 28 access-point names, serials and MACs, three street addresses and 56 latitude /
longitude pairs precise to a building. That issue is one of the nine left on GitHub, so redacting it
here does not hide anything from them — it only keeps their site out of this repository's permanent
history.

**One distinct real value maps to one placeholder throughout**, so a reader can still tell that two
issues discuss the same network without learning which. Two strings that *look* redactable were
deliberately left alone because the issue author wrote them as documentation placeholders:
`aa:bb:cc:dd:ee:01` and `N_1234567890123456789`.

Also deliberately **not** redacted: 40 forty-character hex strings, which are dangerous to treat as a
class because a Meraki API key is also 40 hex characters. Each was resolved individually — 7 are
commits in this repository, 32 are upstream GitHub Action pins of the form `owner/action vX@sha` from
Renovate PR bodies, and 1 is a commit in the sibling `rknightion/.github` repository, confirmed against
the GitHub API. None is a credential. Every credential-shaped string in the tracker was a documentation
placeholder (`Bearer <token>`, an env-var name).

## How it was verified

The sweep ran over **decoded string fields**, recursively, never over the serialized JSON. That
distinction is the standard trap: in `json.dumps` output an escape such as `\n` leaves a literal `n`
immediately before the following word, which breaks a `\b` word boundary, so a blob sweep can certify a
file clean while it still leaks.

**Measured on this file, the two methods happened to agree** — 526 word-boundary matches over the 172
literals by either route, with zero divergence, because none of these values sits at the start of a
line. That is a property of this data, not a reason to trust the convenient method: the field sweep is
the one that *cannot* undercount, so it is the one used. Verification then asserted that all 172
literals are absent from the decoded fields (0 leaks) and that the identifier-class detectors —
serials, network IDs, MACs, addresses, coordinates, dashboard URLs, RFC1918 addresses, host names,
emails, token shapes — come back empty apart from the two documented keeps, with issue count, comment
count and issue numbering unchanged at 455 / 642 / identical.
