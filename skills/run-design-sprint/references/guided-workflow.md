# Guided Sprint Workflow

Run the sprint as a resumable state machine. Do not make the user understand the methodology before beginning. Explain only the current step, why it matters, and what is needed next.

## Contents

1. Interaction contract
2. Workspace engine
3. Sprint state
4. Output structure
5. End-to-end workflow
6. Human decision gates
7. Resuming and stopping

## Interaction contract

At each user-facing pause, use this compact structure:

```text
Current step: <number and name>
Completed: <short result>
Need from you: <one focused decision or input>
Next: <what the AI team will do after the response>
```

Ask one focused question when possible. Offer a draft recommendation when the user may not know the terminology. Allow `approve`, `revise`, `go back`, `show evidence`, and `pause` at every gate.

Do not ask the user for information that can be derived safely from supplied material or public evidence. Do not advance through a human gate using an assumed answer.

## Workspace engine

Use `scripts/sprint_workspace.py` for deterministic state and rendering. Run:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py --help
```

The key commands are `init`, `set-method-profile`, `set-execution-mode`, `set-challenge`, `question`, `new-artifact`, `artifact-status`, `set-route`, `set-concept`, `record-fidelity`, `complete-step`, `skip-step`, `gate`, `customer`, `session-init`, `session-packet`, `session-checkpoint`, `session-complete`, `session-reopen`, `synthesis-packet`, `next-action`, `role-packet`, `role-result`, `assignment-status`, `render`, `render --check`, `status`, `validate`, and `migrate`.

Read [json-schemas.md](json-schemas.md) when a workspace reports a legacy or unsupported schema version. Do not render or mutate legacy JSON before a protected migration.

Edit canonical structured files below `artifact-data/`, update their `updatedAt`, then run `render`. Use workflow commands for canonical `sprint-state.json` and `assignment-manifest.json` changes. Do not hand-edit packet or result digests, and do not edit disposable `index.html`, `assets/sprint.css`, or generated files below `artifacts/` manually. Rendering never advances state-transition timestamps; run `render --check` to detect drift without writing.

Before initialising a workspace, read [privacy-and-publication.md](privacy-and-publication.md). Put the workspace below an access-controlled private root outside any public repository checkout. The workspace is private by default; anonymisation makes it safer to work with but does not make the whole bundle suitable for publication.

## Sprint state

Maintain a machine-readable `sprint-state.json` next to `index.html`. The
current strict schema is linked above. This abridged illustration shows field
ownership; it is not a complete schema-valid record because `init` supplies all
13 fidelity entries, exact non-negotiable principles, and derived summaries:

```json
{
  "schemaVersion": "2.0",
  "title": "Example Sprint",
  "slug": "example-sprint",
  "challenge": "Improve the example journey",
  "methodProfile": "adaptive-design-sprint",
  "executionMode": "live",
  "route": "undecided",
  "routeHistory": [],
  "methodProfileSelection": {"selectedBy": "", "reason": "", "selectedAt": ""},
  "executionModeSelection": {"selectedBy": "", "reason": "", "selectedAt": ""},
  "fidelity": {
    "schemaVersion": "1.0",
    "teamModel": "one-human-plus-AI",
    "nonNegotiablePrinciples": [],
    "steps": {},
    "routeExclusions": [],
    "summary": {}
  },
  "status": "active",
  "currentStep": "01-intake",
  "completedSteps": [],
  "skippedSteps": [],
  "notApplicableSteps": [],
  "skipReasons": {},
  "pendingGate": null,
  "humanGates": [
    {"id": "gate-1", "name": "Challenge and sprint route", "status": "pending"},
    {"id": "gate-2", "name": "Target and top risks", "status": "pending"},
    {"id": "gate-3", "name": "Selected solution direction", "status": "pending"},
    {"id": "gate-4", "name": "Prototype readiness", "status": "pending"},
    {"id": "gate-5", "name": "Final outcome", "status": "pending"}
  ],
  "decisions": [],
  "artifacts": [],
  "customerTesting": {
    "status": "not-planned",
    "target": "",
    "sessionsPlanned": 0,
    "sessionsCompleted": 0
  },
  "openQuestions": [],
  "nextAction": {
    "title": "Complete the sprint intake",
    "body": "Clarify the customer, desired outcome, constraints, and evidence.",
    "humanInput": "Answer the intake questions."
  },
  "createdAt": "2026-08-17T12:00:00Z",
  "updatedAt": "2026-08-17T12:00:00Z"
}
```

Use only these top-level statuses: `active`, `waiting-for-human`, `waiting-for-customers`, `paused`, or `complete`. Keep method profile, execution mode, and route independent. The Sprint-book profile may use the full-design-sprint route; research-first, foundation, focused, and no-sprint routes require the adaptive profile. Keep route-driven `notApplicableSteps` separate from deliberate `skippedSteps`, because skips weaken process completion and method fidelity.

Follow the normative [transition model](transition-model.md) for every route
change, step disposition, skip, gate, artifact-readiness state, customer-session
update, and terminal transition. `routeHistory` is append-only: select the
initial route during qualification, and allow one further transition only after
a completed research-first stage.

## Assignment manifest

`assignment-manifest.json` is the canonical machine-checkable link between each immutable role packet and its assignee/run, packet and input digests, independence group, lifecycle timestamps/status, required outputs, and returned result memo. The step-role requirements follow the primary specialist roles below. Every required assignment must reach `returned` or `accepted` before its step can complete.

For independence-required qualification, risk ranking, exploration, and prototype critique, create all packets before registering any result. Each role uses a distinct run ID, receives no `working/` input, and cannot include a sibling assignment result. Packet input changes make an open assignment stale; packet or memo edits invalidate their registered digests. Duplicate assignment IDs, step-role assignments, packet/result paths, independent run IDs, and result content digests fail validation.

Every entry in `fidelity.steps` records canonical purpose, default method, selected method, human and AI participants, suggested and actual minutes, and deviations. Each substitution, compression, omission, or skip requires a reason, an explanation of the preserved purpose, and separate impacts on method fidelity, evidence, and decision readiness. The engine derives the method-fidelity summary from those records.

Record actual delivery with the workspace engine, for example:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py record-fidelity \
  --workspace <sprint-directory> \
  --step 07-explore \
  --selected-method "Independent concrete solution flows" \
  --human-participant "Human Decider" \
  --ai-participant "Experience Designer" \
  --actual-minutes 120 \
  --deviation-type substitution \
  --preserved-purpose "Create concrete independent directions before convergence." \
  --reason "A multi-person sketching workshop was unavailable." \
  --method-impact "The contributor model differs from the canonical team exercise." \
  --evidence-impact "The directions are proposals, not customer evidence." \
  --decision-impact "Missing human disciplines may leave options underrepresented."
```

Schema 1.0 state is accepted only by the protected `migrate` command. Preview the migration, create the required untouched backup, then migrate it to 2.0 as adaptive/live, matching the old engine's implicit behavior. The migrated state carries a compatibility note so the Orchestrator can verify the historical assumption instead of silently inventing a profile.

## Output structure

Canonical JSON and disposable user-facing views have distinct locations:

```text
design-sprint-<slug>/
├── .gitignore                       # sensitive-source fallback rules
├── index.html                       # generated view
├── sprint-state.json                # canonical workflow state
├── assignment-manifest.json         # canonical specialist provenance
├── assets/
│   └── sprint.css                   # generated view
├── artifact-data/
│   └── 01-sprint-brief.json         # canonical artifact content
├── artifacts/
│   ├── 01-sprint-brief.html         # generated views
│   ├── 02-evidence-ledger.html
│   ├── 03-foundation.html
│   ├── 04-journey-map.html
│   ├── 05-sprint-questions.html
│   ├── 06-solution-directions.html
│   ├── 07-decision.html
│   ├── 08-experiment.html
│   ├── 09-storyboard.html
│   ├── 10-prototype-brief.html
│   ├── 10-test-plan.html
│   ├── 11-customer-evidence.html
│   ├── 12-synthesis.html
│   └── 13-outcome.html
├── working/
│   ├── <step>/<role>.packet.md       # immutable bounded assignment
│   └── <step>/<role>.result.md       # private specialist memo
├── prototype/
│   └── <version>/
│       ├── index.html
│       ├── context.md
│       └── tested-version.json
└── customer-testing/
    ├── session-manifest.json
    ├── sessions/
    │   └── S01/
    │       ├── session.json
    │       ├── summary.json
    │       └── handoff.md
    └── synthesis/
        └── synthesis-packet.md
```

Create only artifacts required by the selected route. Omit `03-foundation.html` when a foundation stage is unnecessary. Store identity/contact maps, raw transcripts, recordings, account evidence, and usage-dashboard captures in separately access-controlled source storage, not in the workspace. Session records keep opaque audit references to those sources. Keep every version-bound prototype, context, guide, and scorecard file immutable; create a new path and version rather than overwriting it. The generated `.gitignore` is a fallback for common sensitive paths, not permission to put the workspace in a public repository.

## End-to-end workflow

### Step 1: Intake

Ask the human to describe the challenge, who it affects, the desired outcome, important constraints, available evidence, and deadline. Accept partial information. Create the dashboard and initial brief.

**Primary role:** Sprint Orchestrator

**Artifact:** `01-sprint-brief.html`

### Step 2: Qualify and route

Decide whether the work needs:

- `research-first` when the customer or problem is not understood;
- `foundation-plus-design` when a new product lacks a coherent strategic hypothesis;
- `full-design-sprint` when an important hypothesis needs realistic testing;
- `focused-design-sprint` when the question is narrow and evidence is sufficient;
- `no-sprint` when direction is settled and execution is the only remaining work.

Explain the recommendation, trade-offs, proposed duration, customer needs, and required human time.

Confirm the method profile and execution mode separately from the route. Use `sprint-book` only for the full-design-sprint route. Make the one-human-plus-AI team-model limitation visible even when canonical book exercises are otherwise followed.

**Primary roles:** Sprint Orchestrator, Evidence Researcher, Product Strategist

**Human gate:** Gate 1 — approve the challenge and route.

### Step 3: Build the evidence base

Collect supplied research, public evidence when permitted, analytics, customer feedback, alternatives, technical constraints, and business context. Start customer recruitment now rather than waiting for the prototype.

**Primary roles:** Evidence Researcher, Research Lead

**Artifacts:** `02-evidence-ledger.html`, recruitment section in `10-test-plan.html`

### Step 4: Establish the foundation when required

Define the target customer, important problem, advantage, alternatives, differentiation, practical principles, approach options, and founding hypothesis. Mark each element by evidence status.

**Primary roles:** Product Strategist, Evidence Researcher, Critical Reviewer

**Artifact:** `03-foundation.html`

### Step 5: Map the experience

Map the current journey or system from trigger to outcome. Identify actors, failure points, target moments, operational dependencies, and relevant edge cases.

**Primary roles:** Experience Designer, Technical Lead

**Artifact:** `04-journey-map.html`

### Step 6: Define sprint questions

Set the long-term goal, target moment, riskiest assumptions, sprint questions, observable signals, and failure criteria. Rank risks by consequence and uncertainty.

**Primary roles:** Product Strategist, Technical Lead, Critical Reviewer

**Artifact:** `05-sprint-questions.html`

**Human gate:** Gate 2 — approve the target and top risks.

### Step 7: Explore independently

Commission distinct solution directions without sharing one specialist's recommendation with another. Include strategic, experiential, technical, operational, and critical perspectives. Reject cosmetic variations.

**Primary roles:** Product Strategist, Experience Designer, Technical Lead, Critical Reviewer

**Artifact:** `06-solution-directions.html`

### Step 8: Compare and decide

Define decision criteria before revealing recommendations. Compare directions using evidence, differentiation, feasibility, accessibility, risk, and testability. Preserve dissent. The human chooses the direction and may combine compatible elements deliberately.

**Primary role:** Sprint Orchestrator

**Artifact:** `07-decision.html`

**Human gate:** Gate 3 — select the direction.

### Step 9: Design the experiment

Translate the selected direction into a hypothesis, scorecard, four-to-six test scenes, storyboard, prototype fidelity, and explicit success and failure signals.

Choose the lowest rung on the test-artifact ladder capable of producing
authentic evidence. Complete the typed prototype/MVP brief, provider-neutral
tool assessment, safety and simulation boundaries, deployment/cleanup/rollback
plan, and explicit human approvals before any AI build packet is generated.
Read [prototype-mvp-testing.md](prototype-mvp-testing.md).

**Primary roles:** Experience Designer, Research Lead, Technical Lead

**Artifacts:** `08-experiment.html`, `09-storyboard.html`, `10-prototype-brief.html`

### Step 10: Build and review the prototype

Generate the bounded build packet from only the approved brief and assets, then
build only what is required for the experiment. Review it for fidelity, broken
paths, accessibility, feasibility, bias, security, data exposure, and interview
readiness. Record mocked behaviour and limitations. Complete the canonical test
plan, conduct a moderated trial using its actual interview script, and freeze a
trial-passed version with deployment, expiry, cleanup, rollback, experiment,
storyboard, and test-plan links. A live URL is neither validation nor production
readiness.

**Primary roles:** Prototype Builder, Critical Reviewer, Research Lead

**Artifacts:** `10-test-plan.html`, `prototype/<version>/index.html`, and `prototype/<version>/tested-version.json`, all linked from the dashboard

**Human gate:** Gate 4 — approve the prototype for customer testing.

### Step 11: Run real-customer sessions

Confirm recruitment criteria, consent, tasks, neutral prompts, note capture, and privacy. Conduct sessions with suitable customers. Record behaviour before interpretation and anonymise participants.

**Primary role:** Research Lead

**Artifact:** `11-customer-evidence.html`

Use the canonical session workflow in [customer-testing.md](customer-testing.md):
plan the target with `customer`, create one `session-init` record per test,
generate one `session-packet` per participant, persist checkpoints when needed,
then use `session-complete` only after its structured summary, consent, and
redaction metadata pass validation. A generated handoff is the complete input
to one fresh session chat; it must not be supplemented with earlier participant
chats or unrelated sprint history. `sessionsCompleted` is derived from unique
complete manifest entries and cannot be set directly.

If sessions cannot occur, set the state to `waiting-for-customers`. Do not skip forward to a customer-tested conclusion.

For a live Sprint-book profile, five suitable one-to-one sessions are the default target. A different target requires a reason and a fidelity/evidence/readiness impact record. Self-test and planning/rehearsal modes cannot complete this step or the customer-evidence artifact; they may skip it explicitly and may only rehearse later mechanics with synthetic material clearly labelled `Synthetic rehearsal`.

### Step 12: Synthesise

Compare all session evidence against the sprint questions and scorecard. Show patterns, contradictions, outliers, confidence, and unanswered questions. Keep findings traceable to anonymised session evidence.

**Primary roles:** Synthesis Analyst, Critical Reviewer

**Artifact:** `12-synthesis.html`

Run `synthesis-packet` before synthesis. Use the generated packet in a separate
fresh chat. Its default inputs are the shared scorecard and complete anonymized
summaries; raw evidence and raw-reference locations are excluded. Require every
synthesized claim to cite included trace IDs such as `S01/OBS1`, and record each
claim in the synthesis artifact's `evidence` list with those IDs in `source`.
Any session completion, reopen, or summary edit makes an earlier synthesis
packet stale.

### Step 13: Decide and hand off

Present `Proceed`, `Iterate`, `Pivot`, `Investigate`, and `Stop` as explicit options with evidence and trade-offs. The human selects the outcome. Assign owners and dates to the smallest next actions.

**Primary role:** Sprint Orchestrator

**Artifact:** `13-outcome.html`

**Human gate:** Gate 5 — make the final outcome decision.

## Human decision gates

Do not bypass these gates:

1. Challenge and sprint route
2. Target and top risks
3. Selected solution direction
4. Prototype readiness
5. Final outcome

Record each gate through `gate`, with the human's exact decision, a human-safe decider identity/label, timestamp, considered artifact or assignment-result references and their content digests, optional rationale, reservations, and overridden recommendations. Each completed `humanGates` entry references the explicit active decision ID. A vote or AI consensus cannot replace the human decision.

Gate 1 attests the selected route and Gate 3 attests the selected concept. If material research changes either value, use `set-route` or `set-concept`; the engine marks the earlier decision `superseded`, reopens the relevant gate, and blocks silent reuse until a new human decision is recorded. Historical decisions remain in the log.

At each completed or adapted step, update the fidelity record with actual participants, actual timebox, and any deviation before advancing. An AI-assisted substitute must preserve the canonical learning purpose, not merely produce an artifact with a similar name.

## Publication gate

Completing a sprint does not approve its artifacts for public release. Before publishing any excerpt, fixture, screenshot, usage number, or cost claim, create a separate sanitized export and complete the [publication checklist](privacy-and-publication.md#publication-checklist). Keep the source workspace and any private case-study repository private.

## Resuming and stopping

On resume, read state, the assignment manifest, artifacts, and, when testing has begun, the customer-session manifest; verify that linked files and digests are current; then continue from `nextAction`. For an interrupted customer session, read its canonical checkpoint and regenerate `session-packet`; do not replay the chat. Do not reopen approved gates unless new evidence materially challenges them or the human asks. Use the route/concept commands for material changes so the superseded and replacement decisions remain traceable.

The sprint may end early when the route is `no-sprint`, evidence disproves the premise, recruitment is impossible, a material safety issue emerges, or the human chooses `Stop`. Produce an honest outcome artifact explaining why.
