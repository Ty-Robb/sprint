# Public test fixtures

Every fixture in this directory must be purpose-written and synthetic. Data files use `.synthetic.` in the filename and include `fixtureKind: synthetic` plus `containsRealCustomerData: false` where the format permits it.

Do not derive fixtures from customer work, private case studies, transcripts, screenshots, account evidence, or usage dashboards. The publication checker enforces the naming and JSON markers; a human must still review provenance and re-identification risk.
