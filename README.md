# Design Sprint for One

An installable skill that gives one human a tightly scoped AI sprint team and guides them from an ambiguous challenge to a real-customer-informed decision.

The human remains the Decider. Specialist AI roles handle research, strategy, experience design, feasibility, prototyping, test preparation, critique, and synthesis. Customers are always real people rather than simulated personas.

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
- Bounded AI roles that cannot silently take over another role
- A living HTML dashboard showing progress, evidence, decisions, and next action
- HTML sprint artifacts, from the brief and evidence ledger through the outcome report
- Independent solution directions, a decision record, and a testable prototype
- A real-customer test plan and traceable synthesis
- A final proceed, iterate, pivot, investigate, or stop decision

## How it runs

The skill includes a dependency-free Python workspace engine. It creates the sprint state, safely renders structured artifact data into HTML, generates bounded specialist role packets, enforces stage and human gates, tracks real-customer sessions, and validates the final bundle.

The generated sprint directory contains:

```text
index.html          Living sprint dashboard
sprint-state.json   Resumable machine state
artifact-data/      Structured canonical content
artifacts/          Generated HTML documents
working/            Isolated specialist packets and memos
prototype/          The customer-test prototype
```

Generated HTML is portable, accessible, printable, and does not require a server, JavaScript framework, CDN, tracking, or external assets.

## Status

The skill supports a research-first route, a foundation-plus-design route, full and focused design sprints, and an explicit no-sprint recommendation. AI-generated customer reactions may be used only as rehearsal and never count as validation.

## License

MIT
