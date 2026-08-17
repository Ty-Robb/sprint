# Design Sprint for One

An installable skill that gives one human a tightly scoped AI sprint team and guides them from an ambiguous challenge to a real-customer-informed decision.

The human remains the Decider. Specialist AI roles handle research, strategy, experience design, feasibility, prototyping, test preparation, critique, and synthesis. Customers are always real people rather than simulated personas.

## Privacy boundary

This public repository contains only the reusable engine, documentation, and synthetic or minimal test fixtures. Generated sprint workspaces, customer evidence, company context, transcripts, screenshots, account information, and private usage evidence are private by default and do not belong here.

Before starting a sprint, choose an access-controlled workspace location outside this repository checkout. Read the [privacy and publication guide](skills/run-design-sprint/references/privacy-and-publication.md) for the storage pattern, safe examples, usage-evidence rules, and the [publication checklist](skills/run-design-sprint/references/privacy-and-publication.md#publication-checklist). A private case-study repository can remain private; it never needs to be copied into or exposed through this repository.

## Install

```bash
npx skills@latest add Ty-Robb/sprint
```

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
- Separate method-profile, execution-mode, and route selectors with a versioned fidelity contract
- Bounded AI roles with a versioned assignment manifest, immutable packet/input digests, result-memo lifecycle, and enforced independent runs
- A living HTML dashboard showing process completion separately from method fidelity, evidence, human decision attestations, privacy-safe specialist provenance, and next action
- HTML sprint artifacts, from the brief and evidence ledger through the outcome report
- Independent solution directions, a decision record, and a testable prototype
- A real-customer test plan and traceable synthesis
- A final proceed, iterate, pivot, investigate, or stop decision

## How it runs

The skill includes a dependency-free Python workspace engine. It creates and migrates sprint state, safely renders structured artifact data into HTML, registers bounded specialist role packets and returned memos, enforces required roles, freshness, independence, stage and human gates, tracks real-customer sessions, records canonical-purpose/method/timebox/participation deviations, and validates the final bundle.

Persisted JSON uses strict, versioned JSON Schema Draft 2020-12 contracts. See [JSON schemas and workspace migrations](skills/run-design-sprint/references/json-schemas.md) for compatibility, field-level validation errors, dry runs, and protected migrations.

The generated sprint directory contains:

```text
.gitignore          Sensitive-source fallback rules
index.html          Disposable generated dashboard
sprint-state.json   Canonical resumable workflow state
assignment-manifest.json  Canonical packet, assignee/run, digest, lifecycle, and result provenance
artifact-data/      Canonical structured artifact content
artifacts/          Disposable generated HTML documents
assets/sprint.css   Disposable generated stylesheet
working/            Private isolated specialist packet and result files
prototype/          Human-authored customer-test prototype
```

The whole generated directory is private by default, including its HTML and structured data. The dashboard renders only safe specialist labels, lifecycle states, and abbreviated digests; it never renders packet inputs or result-memo bodies.
Edit canonical JSON, never generated views. `render` deterministically rebuilds the
HTML and CSS without advancing workflow timestamps; `render --check` and `validate`
fail when those views do not match the current JSON and templates. Engine-written
shareable files use mode `0644` where the platform supports POSIX permissions.

Generated HTML is portable, accessible, printable, and does not require a server, JavaScript framework, CDN, tracking, or external assets.

Before publishing changes to this repository, run:

```bash
python3 scripts/check_publication.py
```

## Status

The skill supports a Sprint-book profile for full live sprints and an adaptive profile for research-first, foundation-plus-design, full, focused, and no-sprint routes. Live, self-test, and planning/rehearsal modes are explicit. One-human-plus-AI substitutions and their limitations remain visible; AI-generated customer reactions are rehearsal only and never count as validation. Live Sprint-book work defaults to five suitable customer sessions.

## License

MIT
