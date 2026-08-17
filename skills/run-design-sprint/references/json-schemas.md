# JSON Schemas and Workspace Migrations

Every JSON document read by the repository's runtime tools has a JSON Schema
Draft 2020-12 contract in [`schemas/`](schemas/). The validator is
dependency-free and reports instance locations as JSONPath, for example
`$.sections[2].rows[0][1]`.

## Persisted families

| Family | Files | Current version | Compatibility |
|---|---|---:|---|
| Workspace state | `sprint-state.json` | `3.0` | `1.0` and `2.0` are migratable |
| Assignment manifest | `assignment-manifest.json` | `1.0` | Current only; created when absent during workspace migration |
| Artifact data | `artifact-data/*.json` | `2.0` | `1.0` is migratable |
| Artifact specifications | `references/artifact-specs.json` | `1.0` | Current only |
| Role contracts | `references/role-contracts.json` | `1.0` | Current only |
| Method profiles | `references/method-profiles.json` | `1.0` | Current only |
| Session manifest | `customer-testing/session-manifest.json` | `1.0` | Current only |
| Customer session | `customer-testing/sessions/*/session.json` | `1.0` | Current only |
| Session summary | `customer-testing/sessions/*/summary.json` | `1.0` | Current only |
| Prototype/MVP brief | `artifact-data/10-prototype-brief.json` → `prototypeBrief` | `1.0` nested in artifact data `2.0` | Current only |
| Immutable tested version | `prototype/*/tested-version.json` | `1.0` | Current only; records are never migrated in place |
| Public usage evidence | `*.usage-evidence.json` publication records | `1.0` | Current only |
| Redacted usage record | `*.usage-record.json` publication records | `1.0` | Current only |
| Pricing snapshot | `*.pricing-snapshot.json` dated calculation inputs | `1.0` | Current only |
| Usage report | `*.usage-report.json` deterministic generated reports | `1.0` | Current only |

The state schema includes its separate method-profile, execution-mode, and
route selectors; explicit process and terminal states; audited skip records;
fidelity principles, step records, participation, timeboxes, deviations,
impacts, and summary; plus nested gate, decision,
artifact-registration, customer-testing, resolved-question, and next-action
records. Gate decisions include a stable decision ID, decider label, considered-input content digests, a route/concept/gate subject snapshot, lifecycle status, and supersession provenance. The artifact schema includes evidence records and the `paragraphs`,
`list`, `ordered-list`, `table`, `cards`, and `key-value` section families.
Conditional schema rules require every artifact ID's declared section titles
and completed gate records' explicit decision reference. The assignment schema
requires packet/input and result digests, assignee/run identity, timestamps,
lifecycle status, required outputs, and independence metadata.

The session manifest is the canonical membership and counting record. Each
manifest entry resolves to one isolated strict session record and one strict
anonymized summary. Runtime validation reconciles version hashes, participant
and session IDs, statuses, source pointers, packet hashes, synthesis inputs,
and the aggregate count in workspace state. These three families deliberately
start at `1.0` independently of workspace-state schema `3.0`; they have no
legacy version or migration path. New manifests carry the optional
`testArtifactWorkflowVersion: "1.0"` capability marker. Under that marker,
prototype catalogs and every session entry, record, and summary must link an
immutable tested-version descriptor. Older `1.0` session documents without the
marker remain schema-valid and retain their legacy hash-bound behavior.

The prototype/MVP brief schema defines the ladder selection, four-to-six-scene
experience, signals, real/simulated boundary, environments, capabilities,
safety, evidence capture, build constraints, provider-neutral tool assessment,
deployment/cleanup/rollback plan, approvals, build packets, trial runs, and
version summaries. The tested-version schema freezes the approved brief
snapshot, build packet, passed trial, linked experiment/storyboard/test plan,
prototype/context, deployment record, and explicit non-validation/readiness
claims.

## Compatibility policy

- Readers and mutation commands accept only the current version of their
  family. They never interpret a legacy or unknown version as current.
- A supported legacy version fails with a migration command; an unknown,
  missing, or wrongly typed version lists the versions the engine understands.
- Artifact `1.0` and state `1.0`/`2.0` are the supported legacy versions. Artifact
  migration to `2.0` changes only `schemaVersion`. State migration also makes
  the formerly implicit one-human-plus-AI method explicit: it classifies the
  legacy run as `adaptive-design-sprint` and `live`, creates canonical fidelity
  records, records any already-selected route in `routeHistory`, translates
  route exclusions into `notApplicableSteps`, and records
  a compatibility note for human review. Existing user content, decisions,
  timestamps, and completed workflow history remain unchanged. Migration also creates an
  empty assignment manifest when one is absent, allowing pre-manifest
  workspaces to resume with explicit provenance for new assignments. Migration-derived
  timestamps reuse the source state's `updatedAt`, and object keys are
  serialized in canonical sorted order, so repeated migration inputs produce
  identical JSON.
- State migration from `2.0` adds `terminalState` and `skipRecords`. It derives
  terminal classification from the recorded mode, route, sessions, and process
  status. Existing skip actors were not recorded, so migration says
  `pre-3.0 actor unavailable` instead of inventing an identity; it reuses the
  recorded skip/fidelity reason and timestamp where available.
- A state migrating from `1.0` or `2.0` may contain the older gate-decision
  shape from before attestation provenance was introduced. `migrate` upgrades
  those records with a conservative legacy label and a digest of the prior
  record; it does not invent considered evidence. New decisions always use the
  attested shape.
- The assignment manifest, packaged artifact, role, and method-profile registries,
  public usage-evidence records, redacted usage records, pricing snapshots, and
  generated usage reports currently have no legacy line. Their loaders reject
  any version other than `1.0`.
- Adding required or otherwise incompatible fields to a strict document
  requires a new schema version. An optional capability marker and optional
  fields may extend a current schema only when every previously valid document
  remains valid and runtime enforcement is activated by that marker;
  undeclared properties are still rejected instead of being silently ignored.
- Loaders accept standards-compliant JSON only; non-finite extensions such as
  `NaN` and `Infinity` are rejected before schema evaluation.

Schema validation runs when state, assignment manifests, artifact specifications,
role contracts, artifact data, customer-session manifests, session records,
summaries, or immutable tested-version records are loaded;
immediately before mutations are persisted; before gate logic; before any
artifact or dashboard rendering; and as part of whole-workspace validation.
The publication checker validates usage evidence, redacted usage records,
pricing snapshots, and generated reports before evaluating them for release.
The usage report generator adds cross-record token reconciliation, scope,
billing, coverage, rate, exclusion, and scenario-label rules that JSON Schema
cannot express cleanly. Cross-record assignment validation additionally enforces immutable
digests, freshness, required memo sections, uniqueness, lifecycle linkage, and
independent-run boundaries. Cross-record session checks additionally enforce isolation, unique
counting, immutable version bindings, trace pointers, packet budgets, and stale
synthesis detection. The [transition model](transition-model.md) adds the
remaining cross-record rules that JSON Schema cannot express cleanly,
including route history, step ordering, skip eligibility and audit consistency,
artifact readiness, customer-session status consistency, and terminal
classification invariants.

## Migrating a workspace

Preview all eligible files without changing the workspace:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py migrate \
  --workspace <sprint-directory> \
  --dry-run
```

Apply the migration with the default sibling backup:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py migrate \
  --workspace <sprint-directory>
```

The default backup is
`<sprint-directory>.backup-before-schema-2.0`. Use `--backup <directory>` to
choose another location. A backup must be outside the workspace and must not
already exist; the command never overwrites one.

Before copying or writing anything, migration validates every legacy source,
builds every result in memory, and validates those results against the current
schemas. The backup is a byte-for-byte copy of the untouched workspace. The
migration then writes only the planned JSON documents using atomic file
replacement. Run `render` and `validate` after migration if generated HTML may
need refreshing.

Applying the same migration to the same legacy JSON produces the same JSON.
Running it again reports that the workspace is already current and writes no
backup.

## Resolving errors

Errors name the file and exact instance path:

```text
artifact-data/01-sprint-brief.json: $.sections[4].cards[0].status:
found "Rumour"; must be one of: "Observed", "Assumption", ...
```

Edit the canonical JSON field named by the path, use an allowed value or
documented shape, then rerun `render` or `validate`. Do not edit generated HTML
to work around a schema error.
