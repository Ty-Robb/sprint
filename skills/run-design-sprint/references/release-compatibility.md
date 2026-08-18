# Release and Compatibility Contract

The skill release, workflow contracts, and persisted JSON schemas have separate
version axes. The machine-readable source of truth is
[`release-contract.json`](release-contract.json); CI verifies it against skill
metadata, runtime constants, schema files, release notes, and the synthetic
release fixture. Policy paths in that contract are relative to the repository
root.

## Skill release version

`run-design-sprint` uses Semantic Versioning. The prepared initial release is
`1.0.0` and its tag is `v1.0.0`.

- **Major** releases may remove or incompatibly change documented commands,
  workflow behavior, supported runtime/platform ranges, or schema migration
  support.
- **Minor** releases add backward-compatible workflow capabilities, commands,
  or optional schema fields/capability markers.
- **Patch** releases fix behavior or documentation without intentionally
  changing accepted inputs or persisted contracts.

The Python scripts are supported as command-line interfaces. Their importable
functions and module internals are not a stable public Python API.

## Schema and workflow compatibility

Schema families use independent `major.minor` strings inside persisted JSON.
They do not inherit the skill's SemVer number. A skill release records the exact
current and migratable versions for every family in `release-contract.json`.

For skill `1.0.0`, workspace state `4.0`, artifact data `3.0`, session manifest
`2.0`, and customer-session record `2.0` are current. Workspace state `1.0`,
`2.0`, and `3.0`; artifact data `1.0` and `2.0`; and session manifest/customer
session `1.0` are migratable. Other listed schema families are current-only.
See [JSON schemas and workspace migrations](json-schemas.md) for the complete
family table and conservative migration behavior.

Adding a required field or otherwise rejecting a previously valid strict JSON
document requires a new schema version. Optional fields may be added to a
current schema only when old documents remain valid and any new runtime
enforcement is activated by an explicit capability marker. Runtime readers
never silently treat legacy or unknown documents as current.

The workflow contract for this release uses method profiles `1.0`, progressive
step guidance `1.0`, fidelity records `1.0`, role packets `1.0`, and the test
artifact workflow `1.0`. A release note must call out any change to those
versions or to route, transition, evidence, decision, or terminal-state
semantics.

## Runtime and platform support

The installed runtime is dependency-free Python and does not require network
access. Release CI covers Python 3.10, 3.11, 3.12, 3.13, and 3.14 on Ubuntu
24.04, plus smoke coverage on macOS 14 and Windows Server 2022. Newer compatible
OS releases are supported; other Unix-like platforms and Python pre-releases
are best effort.

Installing through the documented `skills` CLI is separate from runtime use.
The verified installer is `skills@1.5.22` on Node.js 22 and 24. Agent hosts must
support the Agent Skills directory format; clean discovery is verified for the
Codex project layout.

## Deprecation policy

A deprecation is announced in the changelog and release notes, names a
replacement and migration path, and emits a runtime warning when practical.
Except for an actively exploited security issue or an upstream end-of-life
constraint, a deprecated 1.x interface remains available for at least one minor
release and 90 days, whichever is longer.

Removing a documented command, raising the minimum Python or OS version, or
ending a listed schema migration path requires a new skill major release.
Security fixes may narrow unsafe behavior immediately; the release notes will
explain the exception and recovery path.

## Release verification

Every release candidate must pass the full unit suite, schema compilation,
publication-boundary check, HTML validation, supported-runtime matrix, and the
clean install/discovery smoke test. The smoke test installs a public repository
ref into a new temporary project, discovers `run-design-sprint`, checks its
version and contract, and creates, inspects, renders, and validates the minimal
synthetic planning workspace in
`tests/fixtures/release/minimal-planning.synthetic.json`.
