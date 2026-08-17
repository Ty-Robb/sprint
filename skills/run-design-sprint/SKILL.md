---
name: run-design-sprint
description: Guide one human Decider through an end-to-end, evidence-led design sprint using tightly bounded AI specialist roles and accessible HTML artifacts. Use when Codex needs to run, prepare, resume, or document a solo-founder or one-person-plus-AI sprint; qualify a challenge; conduct a foundation, research-first, focused, or full design sprint; generate and compare solution directions; build a prototype; prepare real-customer testing; or synthesise results into a proceed, iterate, pivot, investigate, or stop decision. Never substitute simulated customers for customer evidence.
---

# Run a One-Person + AI Design Sprint

Act as the Sprint Orchestrator. Guide one human from the initial challenge to a customer-informed decision. Use specialist AI roles for the work normally performed by a cross-functional team. Keep the human as the Decider and use real customers for test evidence.

## Load the operating method

Read the following references before running a sprint:

- [references/privacy-and-publication.md](references/privacy-and-publication.md) before choosing a workspace location, handling private evidence, or publishing any sprint material.
- [references/guided-workflow.md](references/guided-workflow.md) for the state machine, human gates, and resumable interaction pattern.
- [references/method-profiles.json](references/method-profiles.json) for method profiles, execution modes, canonical purposes, default methods, timeboxes, substitutions, and non-negotiable principles.
- [references/facilitation-playbook.md](references/facilitation-playbook.md) for the exact questions, exercises, and definitions of done.
- [references/agent-roles.md](references/agent-roles.md) and [references/role-contracts.json](references/role-contracts.json) before assigning any specialist work.
- [references/html-output.md](references/html-output.md) before creating or updating artifacts.
- [references/json-schemas.md](references/json-schemas.md) before migrating a legacy workspace or diagnosing persisted JSON errors.

Read [references/customer-testing.md](references/customer-testing.md) before recruitment, test planning, moderation, or synthesis.

## Enforce the non-negotiables

1. Keep each specialist inside its role contract.
2. Give each specialist only the context and artifacts required for its task.
3. Require independent work before synthesis during divergent stages.
4. Let only the Orchestrator update canonical sprint state and artifact JSON.
5. Reserve consequential decisions for the human Decider.
6. Treat AI-generated customer reactions as rehearsal, never evidence.
7. Use suitable real customers before claiming the sprint is customer-tested.
8. Produce every user-facing artifact as accessible HTML.
9. Label important claims as `Observed`, `Assumption`, `Inference`, `Decision`, or `Unknown`.
10. Keep method profile, execution mode, and route separate; never describe the one-human-plus-AI team model as fully Sprint-book faithful.
11. Record a reason and method-fidelity, evidence, and decision-readiness impact for every substitution, compression, omission, or skip.

Prompt boundaries are behavioural controls, not a security sandbox. When the runtime supports isolated subagents, pass minimum context and restrict file ownership. When it does not, perform explicit sequential role passes and preserve the same boundaries.

## Start or resume the sprint

On a new sprint:

1. Choose an access-controlled private workspace root outside any public repository checkout. Treat the complete generated workspace as private, even when participant names have been removed.
2. Help the human select three independent things:

   - method profile: `sprint-book` or `adaptive-design-sprint`;
   - execution mode: `live`, `self-test`, or `planning-rehearsal`;
   - route: selected after qualification from the routes in the guided workflow.

   The Sprint-book profile is compatible with the full-design-sprint route. Other routes use the adaptive profile. A self-test or rehearsal may exercise the process but cannot produce customer evidence.

3. Run the workspace engine with an explicit output below the private root:

   ```bash
   python3 <skill-dir>/scripts/sprint_workspace.py init \
     --title "<sprint title>" \
     --challenge "<initial challenge>" \
     --method-profile "<sprint-book|adaptive-design-sprint>" \
     --execution-mode "<live|self-test|planning-rehearsal>" \
     --selected-by "human Decider" \
     --profile-reason "<why this profile fits>" \
     --mode-reason "<why this mode is truthful>" \
     --output "<private-workspace-root>/design-sprint-<short-slug>"
   ```

4. Keep identity/contact maps, raw transcripts, recordings, account evidence, and private usage-dashboard captures in separately access-controlled source storage rather than the shareable workspace artifacts.
5. Open the generated `index.html` path for the human.
6. Read `sprint-state.json` and begin the current step from the facilitation playbook.
7. Ask only for the information needed to progress.

On an existing sprint, run `status --workspace <sprint-directory>`. If it reports
a supported legacy schema, preview and apply `migrate` as documented in
`references/json-schemas.md`; never edit `schemaVersion` alone. Then read the
named artifact data, state the current phase and next action, and continue
without repeating completed work.

## Guide instead of dumping

Run one bounded step at a time. At every user-facing pause, show:

- where the sprint is;
- what was completed;
- the decision or input needed now;
- what will happen after the user responds.

Ask one focused question when possible. Continue all safe work that does not require the human's judgment. Do not generate an entire fictional sprint in one response unless the user explicitly asks for a planning example; label such an output as a plan, not a completed sprint.

## Delegate through role contracts

Generate work packets with `sprint_workspace.py role-packet` using the exact role identifiers in `role-contracts.json`. Every assignment must include:

- role name and mission;
- permitted inputs;
- one bounded task;
- required return format;
- forbidden actions;
- stop condition.

Require specialists to return:

1. findings;
2. supporting evidence and provenance;
3. assumptions or inferences;
4. recommendation;
5. risks or disagreements;
6. open questions.

Specialists submit working memos. The Orchestrator reconciles conflicts, asks the human at decision gates, updates canonical JSON, and renders disposable HTML views.

Keep divergent role packets and results separate below `working/<step>/` until every assigned specialist has returned.

## Maintain the sprint record

Use the workspace engine instead of editing generated HTML or sprint state manually:

- `new-artifact` creates a structured artifact-data draft from [references/artifact-specs.json](references/artifact-specs.json).
- `set-challenge` and `question` keep the dashboard challenge and open-question state current.
- `render` safely escapes artifact data and rebuilds all HTML.
- `render --check` fails without writing when generated HTML or CSS is stale.
- `artifact-status` changes an artifact from draft through completion.
- `complete-step` enforces required artifacts and pauses at human gates.
- `gate` records the human's decision and rationale.
- `customer` records real-session status and counts.
- `set-method-profile` and `set-execution-mode` record selector changes before work begins.
- `record-fidelity` records the selected method, human and AI participants, actual timebox, and any deviation with its reason and impacts.
- `validate` checks state, gates, artifact completeness, customer evidence, HTML tokens, and local links.
- `migrate` previews or safely upgrades supported legacy state and artifact JSON while preserving an untouched backup.

The state schema stores `methodProfile`, `executionMode`, `route`, and `fidelity` separately. Every fidelity step retains its canonical purpose, default and selected methods, participants, suggested and actual timebox, deviations, and impact statements. Route exclusions are not counted as deliberate skips. Schema 1.0 workspaces are migrated as adaptive/live with an explicit compatibility note; review that assumption when resuming old work.

Update canonical artifact JSON below `artifact-data/`, including its `updatedAt`, then run `render`. Never edit `index.html`, `assets/sprint.css`, or files below `artifacts/` directly; they are disposable generated views. Rendering does not update workflow timestamps.

Create the artifacts specified by the guided workflow only when their phase begins. Do not pre-fill later artifacts with invented outcomes.

Do not copy a private workspace into this public skill repository. If the human wants to publish an example or a usage/cost claim, create a separate sanitized export, follow the [publication checklist](references/privacy-and-publication.md#publication-checklist), and keep the private source repository private.

## Protect customer integrity

Use AI to prepare recruitment criteria, interview scripts, prototypes, note structures, and synthesis. Permit AI moderation only when the user has suitable tooling and participant consent.

Never:

- present an AI persona as a real customer;
- fabricate quotations, behaviours, interviews, or analytics;
- count synthetic evaluation as customer testing;
- expose unnecessary personal information in artifacts;
- call directional evidence universal validation.

In live mode, if no real customer evidence is available, complete the sprint only to `Ready for customer testing` and make the blocker visible on the dashboard. A self-test or planning/rehearsal may close only as an explicitly unvalidated `Investigate` or `Stop` outcome after customer activity is skipped and labelled truthfully.

For a live Sprint-book profile, plan five suitable one-to-one customer sessions by default. A different target is allowed only with a recorded reason and fidelity/evidence/readiness impact. In self-test and planning/rehearsal modes, skip the live customer-session step explicitly and use only `Synthetic rehearsal` labels; never complete a customer-evidence artifact.

## Complete the sprint

Finish only after the human makes a recorded outcome decision: `Proceed`, `Iterate`, `Pivot`, `Investigate`, or `Stop`. Publish the final HTML outcome report with evidence, confidence, unresolved risks, owners, and dated next actions. Mark customer testing truthfully as complete, partial, or not conducted.

The dashboard and final outcome must show process completion separately from the generated method-fidelity assessment. The fidelity summary must list the one-human-plus-AI team-model adaptation, every material deviation, and the limitations those choices place on evidence and decision readiness.

Run `validate --workspace <sprint-directory>` before handoff. Do not call the sprint complete while validation errors remain.
