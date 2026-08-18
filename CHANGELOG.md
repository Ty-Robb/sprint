# Changelog

All notable changes to `run-design-sprint` are recorded here. Skill releases
follow [Semantic Versioning](https://semver.org/); persisted JSON schema
families are versioned independently as described in the
[compatibility contract](skills/run-design-sprint/references/release-compatibility.md).

## [Unreleased]

No changes yet.

## [1.0.0] - Unreleased

This entry is prepared for the initial release. Replace `Unreleased` with the
UTC release date only after a human approves tagging.

### Added

- Installable `run-design-sprint` Agent Skill with bounded specialist roles,
  explicit human gates, resumable workflow state, and accessible deterministic
  HTML output.
- Sprint-book and adaptive method profiles; live, self-test, and
  planning/rehearsal execution modes; and explicit route, fidelity, evidence,
  readiness, and terminal-state semantics.
- Dependency-free Python workspace, schema validation, safe rendering,
  migration, prototype lifecycle, isolated customer-session, usage-reporting,
  and privacy-checked export commands.
- Machine-readable skill release/runtime/schema compatibility contract,
  supported-platform policy, deprecation rules, contribution guidance, private
  security-reporting path, and maintainer release runbook.
- Clean public install/discovery verification and a minimal synthetic
  end-to-end release fixture.

### Compatibility

- Skill version: `1.0.0` (`v1.0.0` once approved and tagged).
- Python: 3.10 through 3.14 with no third-party runtime packages.
- Platforms: Ubuntu 24.04, macOS 14+, and Windows Server 2022+.
- Installer verification: `skills@1.5.22` on Node.js 22 and 24.
- Current schemas: workspace state `4.0`, artifact data `3.0`, session manifest
  `2.0`, customer-session record `2.0`; all other families are listed in
  `release-contract.json`.
- Migratable schemas: workspace state `1.0`/`2.0`/`3.0`, artifact data
  `1.0`/`2.0`, and session manifest/customer-session record `1.0`.
- Workflow contracts: method profiles, progressive guidance, fidelity, role
  packets, and test-artifact workflow are all `1.0`.

[Unreleased]: https://github.com/Ty-Robb/sprint/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Ty-Robb/sprint/releases/tag/v1.0.0
