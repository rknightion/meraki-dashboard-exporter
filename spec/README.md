# Vendored Meraki OpenAPI spec

`meraki-openapi.json.gz` is the gzipped, vendored baseline of the Cisco Meraki Dashboard
API OpenAPI spec. The `api-drift` CI lane uses it as the comparison baseline for detecting
upstream API drift on the operations this exporter consumes.

- **Source:** <https://raw.githubusercontent.com/meraki/openapi/master/openapi/spec3.json>
- **Vendored version (`info.version`):** 1.72.0
- **Do not hand-edit.** Refresh with `make refresh-meraki-spec`, then update the version above.

## How drift detection uses this

1. The `apidrift` tool (`tools/apidrift/`) AST-scans `src/` for the Meraki SDK operations
   this exporter actually consumes.
2. It reduces both this baseline and the freshly-fetched live spec to that consumed surface.
3. `oasdiff` compares the two reduced specs for breaking changes; the tool additionally
   checks Pydantic models against the live spec's response schemas.

## Acknowledging drift

When the daily `api-drift` job flags a breaking change, either:

1. **Fix + re-vendor** — update the affected collectors/models, run `make refresh-meraki-spec`,
   and update the version note above, **or**
2. **Defer** — add a line to `oasdiff-ignore.txt` describing the change to suppress it until
   you're ready to address it.
</content>
