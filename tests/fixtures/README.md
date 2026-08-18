# Public test fixtures

Every fixture in this directory must be purpose-written and synthetic. Data files use `.synthetic.` in the filename and include `fixtureKind: synthetic` plus `containsRealCustomerData: false` where the format permits it.

Fixtures for strict persisted formats wrap the schema instance in a top-level `document` field so the publication markers remain fixture metadata rather than becoming production fields.

Do not derive fixtures from customer work, private case studies, transcripts, screenshots, account evidence, or usage dashboards. The publication checker enforces the naming and JSON markers; a human must still review provenance and re-identification risk.

The `usage/` fixtures deliberately cover internal development, customer-only
runtime, individual sessions, synthesis, model mix, long-context and cache-write
pricing, tools, a credit, subscription/API separation, and missing
request-level data. All run quantities are invented. The pricing snapshot alone
copies dated public facts from its linked official sources and is not a live
price lookup or a subscription-plan claim.

`release/minimal-planning.synthetic.json` is the end-to-end release fixture. It
contains only invented planning inputs and expected version/file assertions.
The clean smoke test uses it to install and discover the skill in a new project,
then initialize, inspect, render-check, and validate a workspace without
claiming that customer research or a sprint occurred.
