# Public test fixtures

Every fixture in this directory must be purpose-written and synthetic. Data files use `.synthetic.` in the filename and include `fixtureKind: synthetic` plus `containsRealCustomerData: false` where the format permits it.

Fixtures for strict persisted formats wrap the schema instance in a top-level `document` field so the publication markers remain fixture metadata rather than becoming production fields.

Do not derive fixtures from customer work, private case studies, transcripts, screenshots, account evidence, or usage dashboards. The publication checker enforces the naming and JSON markers; a human must still review provenance and re-identification risk.
