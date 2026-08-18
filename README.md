# Design Sprint for One

An installable skill that gives one human a tightly scoped AI sprint team and guides them from an ambiguous challenge to a real-customer-informed decision.

The current skill version is `1.0.0`. Skill releases follow Semantic
Versioning independently from persisted workspace schema families. See the
[release and compatibility contract](skills/run-design-sprint/references/release-compatibility.md),
[changelog](CHANGELOG.md), and [support policy](SUPPORT.md).

The human remains the Decider. Specialist AI roles handle research, strategy, experience design, feasibility, prototyping, test preparation, critique, and synthesis. Customers are always real people rather than simulated personas.

## Privacy boundary

This public repository contains only the reusable engine, documentation, and synthetic or minimal test fixtures. Generated sprint workspaces, customer evidence, company context, transcripts, screenshots, account information, and private usage evidence are private by default and do not belong here.

Before starting a sprint, choose an access-controlled workspace location outside this repository checkout. Read the [privacy and publication guide](skills/run-design-sprint/references/privacy-and-publication.md) for the storage pattern, safe examples, usage-evidence rules, and the [publication checklist](skills/run-design-sprint/references/privacy-and-publication.md#publication-checklist). A private case-study repository can remain private; it never needs to be copied into or exposed through this repository.

## Install

Install the current public development version interactively:

```bash
npx skills@latest add Ty-Robb/sprint
```

After the `v1.0.0` tag is approved and published, this is the reproducible
Codex project install used by release verification:

```bash
npx --yes skills@1.5.22 add \
  "https://github.com/Ty-Robb/sprint.git#v1.0.0" \
  --skill run-design-sprint \
  --agent codex \
  --copy \
  --yes
```

The installer requires Node.js 22 or 24. Once installed, the skill's workspace
engine is dependency-free Python and needs no network access. Confirm discovery
and the installed runtime version from the project directory:

```bash
npx --yes skills@1.5.22 list --json
python3 .agents/skills/run-design-sprint/scripts/sprint_workspace.py --version
```

Expected skill runtime output for this release is
`sprint_workspace.py 1.0.0`. Other Agent Skills clients may use a different
installation directory; select their supported agent identifier in place of
`codex`.

Then ask your agent:

```text
Use $run-design-sprint to guide me from step one through a complete design sprint for this challenge: [describe the challenge].
```

To resume:

```text
Use $run-design-sprint to resume the sprint in [output directory].
```

To prepare without claiming the sprint occurred:

```text
Use $run-design-sprint to prepare an end-to-end sprint plan and HTML workspace for this challenge.
```

## What it produces

- A guided, resumable workflow with explicit human decision gates
- Compact just-in-time guidance for every step, with examples, rationale, canonical methods, checklists, substitutes, blockers, and pause help available on demand
- Separate method-profile, execution-mode, and route selectors with named selection provenance and a versioned fidelity contract
- Bounded AI roles with a versioned assignment manifest, immutable packet/input digests, result-memo lifecycle, and enforced independent runs
- A living HTML dashboard showing process status, method fidelity, descriptive evidence strength, and action-specific decision readiness independently
- One machine-readable site manifest and a shared relative navigation shell across the dashboard, artifacts, session-evidence views, and tested-prototype wrapper
- HTML sprint artifacts, from the brief and evidence ledger through the outcome report
- Independent solution directions, a decision record, and a testable prototype
- A test-artifact ladder and typed prototype/MVP brief with provider-neutral tool selection, explicit approvals, bounded build packets, moderated trials, and immutable deployment/version records
- An early practical recruitment plan with behavioral target, neutral screener, optional channels, outreach/reminder/scheduling/consent/backup templates, owner, deadline, milestones, and honest partial handling without requiring a paid vendor
- A real-customer test plan with separate planned, invited, attempted, completed, qualified, excluded, and usable counts plus traceable material findings
- A final proceed, iterate, pivot, investigate, or stop decision
- Separately approved private-archive and privacy-checked shareable-site preparation, with optional deterministic ZIP output and no automatic publication

## How it runs

The skill includes a dependency-free Python workspace engine. It creates and migrates sprint state, safely renders structured artifact data into HTML, registers bounded specialist role packets and returned memos, enforces required roles, freshness, independence, stage and human gates, tracks real-customer sessions, records canonical-purpose/method/timebox/participation deviations, and validates the final bundle.

Persisted JSON uses strict, versioned JSON Schema Draft 2020-12 contracts. See [JSON schemas and workspace migrations](skills/run-design-sprint/references/json-schemas.md) for compatibility, field-level validation errors, dry runs, and protected migrations.

The generated sprint directory contains:

```text
.gitignore          Sensitive-source fallback rules
index.html          Disposable generated dashboard
site-manifest.json  Generated page, relationship, visibility, version, and digest catalog
sprint-state.json   Canonical resumable workflow state
assignment-manifest.json  Canonical packet, assignee/run, digest, lifecycle, and result provenance
artifact-data/      Canonical structured artifact content
artifacts/          Disposable generated HTML documents
session-evidence/   Generated privacy-minimized per-session HTML views
prototype-launch.html  Generated context wrapper for the current frozen prototype
assets/sprint.css   Disposable generated stylesheet
working/            Private isolated specialist packet and result files
prototype/          Versioned test artifacts and immutable tested-version records
customer-testing/   Canonical manifest, isolated sessions, and bounded packets
```

The whole generated directory is private by default, including its HTML and structured data. The dashboard renders only safe specialist labels, lifecycle states, and abbreviated digests; it never renders packet inputs or result-memo bodies.
Edit canonical JSON, never generated views. `render` deterministically rebuilds the
HTML and CSS without advancing workflow timestamps; `render --check` and `validate`
fail when those views do not match the current JSON and templates. Engine-written
shareable files use mode `0644` where the platform supports POSIX permissions.

Generated HTML is portable, accessible, printable, and does not require a server, JavaScript framework, CDN, tracking, or external assets.

Every generated page uses relative Home, previous, next, related-evidence,
decision, prototype, outcome, and manifest links derived from
`site-manifest.json`. The same files work when opened directly, served on
localhost, or hosted below a nested static-site path.

Do not publish the workspace itself. To prepare a private archive or an
explicitly approved shareable site, create a strict export-approval JSON record
and run `sprint_workspace.py export`. The command validates the source,
prototype version, redaction review, local assets, manifest digests, and every
local link, then writes a new directory outside the workspace. `--zip` adds a
deterministic sibling archive. It never uploads or publishes. See
[site exports and self-hosting](skills/run-design-sprint/references/site-exports.md).

Customer testing uses one versioned record and one generated minimal handoff
per participant, intended for a fresh chat. Sessions persist checkpoints and
anonymized structured summaries, while synthesis receives a separate bounded
packet without raw transcripts by default. See the
[real-customer testing protocol](skills/run-design-sprint/references/customer-testing.md)
for operating commands, context budgets, usage fields, and audit traceability.

Published usage and cost evidence uses separate strict, redacted records for
internal development, customer runtime, individual sessions, and synthesis. A
dependency-free Decimal calculator reproduces observation totals, dated API
base-rate equivalents, excluded charges, warnings, and explicitly hypothetical
planning scenarios without treating subscription counters as API billing. See
[usage, cost, and capacity evidence](skills/run-design-sprint/references/usage-reporting.md)
for the formats, synthetic fixtures, verified source dates, and rerunnable command.

Before publishing changes to this repository, run:

```bash
python3 scripts/check_publication.py
```

Contributors should also read [CONTRIBUTING.md](CONTRIBUTING.md). Security
reports must follow [SECURITY.md](SECURITY.md) and must not include sensitive
details in a public issue.

## Status

The skill supports a Sprint-book profile for full live sprints and an adaptive profile for research-first, foundation-plus-design, full, focused, and no-sprint routes. Live, self-test, and planning/rehearsal modes are explicit and auditable. Terminal state distinguishes live customer-tested work from self-test completion, planning/rehearsal completion, and other unvalidated closure in canonical JSON, dashboards, portable artifacts, and status exports. One-human-plus-AI substitutions and their limitations remain visible; AI-generated customer reactions are rehearsal only and never count as validation. Live Sprint-book work defaults to five suitable customer sessions. One or two usable sessions are reported as early/limited, three or four as partial directional, five as the book target met, and more than five as extended—never as statistical confidence or population validation. See [execution modes, closure, and restart](skills/run-design-sprint/references/execution-modes.md) before converting or restarting a rehearsal as live work.

## License

MIT
