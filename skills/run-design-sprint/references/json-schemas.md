# JSON Schemas and Workspace Migrations

Every JSON document read by the repository's runtime tools has a JSON Schema
Draft 2020-12 contract in [`schemas/`](schemas/). The validator is
dependency-free and reports instance locations as JSONPath, for example
`$.sections[2].rows[0][1]`.

## Persisted families

| Family | Files | Current version | Compatibility |
|---|---|---:|---|
| Workspace state | `sprint-state.json` | `2.0` | `1.0` is migratable |
| Artifact data | `artifact-data/*.json` | `2.0` | `1.0` is migratable |
| Artifact specifications | `references/artifact-specs.json` | `1.0` | Current only |
| Role contracts | `references/role-contracts.json` | `1.0` | Current only |
| Public usage evidence | `*.usage-evidence.json` publication records | `1.0` | Current only |

The state schema includes its nested gate, decision, artifact-registration,
customer-testing, resolved-question, and next-action records. The artifact
schema includes evidence records and the `paragraphs`, `list`, `ordered-list`,
`table`, `cards`, and `key-value` section families. Conditional schema rules
require every artifact ID's declared section titles and complete gate records'
decision fields.

There is no standalone customer-session JSON format or session-import command
in the current engine. Customer-testing counts remain a nested state record.
Any future persisted session family must receive its own versioned schema and
be validated before an import writes a file or changes those counts.

## Compatibility policy

- Readers and mutation commands accept only the current version of their
  family. They never interpret a legacy or unknown version as current.
- A supported legacy version fails with a migration command; an unknown,
  missing, or wrongly typed version lists the versions the engine understands.
- State and artifact `1.0` are the only supported legacy versions. Migration to
  `2.0` is deliberately structure-preserving: `2.0` makes the previously
  documented shape strict, while the migration changes only `schemaVersion`.
  User content, workflow history, array ordering, and timestamps remain
  unchanged. Object keys are serialized in canonical sorted order.
- The packaged artifact and role registries and public usage-evidence records
  currently have no legacy line. Their loaders reject any version other than
  `1.0`.
- Adding fields to a strict document requires a new compatible schema version;
  undeclared properties are rejected instead of being silently ignored.
- Loaders accept standards-compliant JSON only; non-finite extensions such as
  `NaN` and `Infinity` are rejected before schema evaluation.

Schema validation runs when state, artifact specifications, role contracts, or
artifact data are loaded; immediately before state or artifact mutations are
persisted; before gate logic; before any artifact or dashboard rendering; and
as part of whole-workspace validation. The publication checker validates usage
records before evaluating them for release. Completion and customer-evidence
checks remain separate cross-record rules. Route-history and skip-policy
invariants are intentionally not changed here.

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
