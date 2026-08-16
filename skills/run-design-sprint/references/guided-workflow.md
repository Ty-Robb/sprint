# Guided Sprint Workflow

Run the sprint as a resumable state machine. Do not make the user understand the methodology before beginning. Explain only the current step, why it matters, and what is needed next.

## Contents

1. Interaction contract
2. Sprint state
3. Output structure
4. End-to-end workflow
5. Human decision gates
6. Resuming and stopping

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

## Sprint state

Maintain a machine-readable `sprint-state.json` next to `index.html`. Use this minimum shape:

```json
{
  "schemaVersion": "1.0",
  "title": "",
  "slug": "",
  "route": "undecided",
  "status": "active",
  "currentStep": "01-intake",
  "completedSteps": [],
  "humanGates": [],
  "artifacts": [],
  "customerTesting": {
    "status": "not-planned",
    "target": "",
    "sessionsPlanned": 0,
    "sessionsCompleted": 0
  },
  "openQuestions": [],
  "nextAction": ""
}
```

Use only these top-level statuses: `active`, `waiting-for-human`, `waiting-for-customers`, `paused`, or `complete`. Keep detailed notes in artifacts rather than bloating the state file.

## Output structure

Create user-facing artifacts as HTML:

```text
design-sprint-<slug>/
├── index.html
├── sprint-state.json
├── assets/
│   └── sprint.css
├── artifacts/
│   ├── 01-sprint-brief.html
│   ├── 02-evidence-ledger.html
│   ├── 03-foundation.html
│   ├── 04-journey-map.html
│   ├── 05-sprint-questions.html
│   ├── 06-solution-directions.html
│   ├── 07-decision.html
│   ├── 08-experiment.html
│   ├── 09-storyboard.html
│   ├── 10-test-plan.html
│   ├── 11-customer-evidence.html
│   ├── 12-synthesis.html
│   └── 13-outcome.html
└── prototype/
    └── index.html
```

Create only artifacts required by the selected route. Omit `03-foundation.html` when a foundation stage is unnecessary. Store raw sensitive participant data outside the shareable artifact bundle or anonymise it.

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

**Primary roles:** Experience Designer, Research Lead, Technical Lead

**Artifacts:** `08-experiment.html`, `09-storyboard.html`

### Step 10: Build and review the prototype

Build only what is required for the experiment. Review it for fidelity, broken paths, accessibility, feasibility, bias, and interview readiness. Record mocked behaviour and limitations.

**Primary roles:** Prototype Builder, Critical Reviewer, Research Lead

**Artifact:** `prototype/index.html` or another suitable prototype linked from the dashboard

**Human gate:** Gate 4 — approve the prototype for customer testing.

### Step 11: Run real-customer sessions

Confirm recruitment criteria, consent, tasks, neutral prompts, note capture, and privacy. Conduct sessions with suitable customers. Record behaviour before interpretation and anonymise participants.

**Primary role:** Research Lead

**Artifacts:** `10-test-plan.html`, `11-customer-evidence.html`

If sessions cannot occur, set the state to `waiting-for-customers`. Do not skip forward to a customer-tested conclusion.

### Step 12: Synthesise

Compare all session evidence against the sprint questions and scorecard. Show patterns, contradictions, outliers, confidence, and unanswered questions. Keep findings traceable to anonymised session evidence.

**Primary roles:** Synthesis Analyst, Critical Reviewer

**Artifact:** `12-synthesis.html`

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

Record the human's exact decision, date, rationale, reservations, and overridden recommendations. A vote or AI consensus cannot replace the human decision.

## Resuming and stopping

On resume, read state and artifacts, verify that linked files exist, and continue from `nextAction`. Do not reopen approved gates unless new evidence materially challenges them or the human asks.

The sprint may end early when the route is `no-sprint`, evidence disproves the premise, recruitment is impossible, a material safety issue emerges, or the human chooses `Stop`. Produce an honest outcome artifact explaining why.
