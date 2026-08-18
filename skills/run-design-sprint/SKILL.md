---
name: run-design-sprint
description: Guide one human Decider through an end-to-end, evidence-led design sprint using tightly bounded AI specialist roles and accessible HTML artifacts. Use when Codex needs to run, prepare, resume, or document a solo-founder or one-person-plus-AI sprint; qualify a challenge; conduct a foundation, research-first, focused, or full design sprint; generate and compare solution directions; build a prototype; prepare real-customer testing; or synthesise results into a proceed, iterate, pivot, investigate, or stop decision. Never substitute simulated customers for customer evidence.
license: MIT
compatibility: Requires Python 3.10-3.14 on Ubuntu 24.04, macOS 14+, or Windows Server 2022+. Installing with skills@1.5.22 requires Node.js 22 or 24; the installed runtime has no third-party Python or network dependency.
metadata:
  author: Ty-Robb
  version: "1.0.0"
  release-contract: references/release-contract.json
---

# Run a One-Person + AI Design Sprint

Act as the Sprint Orchestrator. Guide one human from the initial challenge to a customer-informed decision. Use specialist AI roles for the work normally performed by a cross-functional team. Keep the human as the Decider and use real customers for test evidence.

## Load the operating method

Read the following references before running a sprint:

- [references/privacy-and-publication.md](references/privacy-and-publication.md) before choosing a workspace location, handling private evidence, or publishing any sprint material.
- [references/guided-workflow.md](references/guided-workflow.md) for the state machine, human gates, and resumable interaction pattern.
- [references/transition-model.md](references/transition-model.md) for the executable route/step matrix, skip policy, readiness rules, and terminal invariants.
- [references/execution-modes.md](references/execution-modes.md) for mode selection, audited customer-step skips, truthful closure labels, and rehearsal-to-live restart rules.
- [references/method-profiles.json](references/method-profiles.json) for method profiles, execution modes, canonical purposes, default methods, timeboxes, substitutions, and non-negotiable principles.
- [references/step-guidance.json](references/step-guidance.json) for the validated compact and on-demand guidance contract for every workflow step.
- [references/facilitation-playbook.md](references/facilitation-playbook.md) for the exact questions, exercises, and definitions of done.
- [references/agent-roles.md](references/agent-roles.md) and [references/role-contracts.json](references/role-contracts.json) before assigning any specialist work.
- [references/html-output.md](references/html-output.md) before creating or updating artifacts.
- [references/site-exports.md](references/site-exports.md) before preparing a private archive, shareable site, ZIP, or static-hosting handoff.
- [references/prototype-mvp-testing.md](references/prototype-mvp-testing.md) before selecting, briefing, building, trialling, deploying, or versioning a test artifact.
- [references/json-schemas.md](references/json-schemas.md) before migrating a legacy workspace or diagnosing persisted JSON errors.
- [references/release-compatibility.md](references/release-compatibility.md) when checking the installed skill version, runtime support, schema compatibility, or deprecation policy.
- [references/usage-reporting.md](references/usage-reporting.md) before measuring, calculating, or publishing usage, cost, subscription, or capacity evidence.

Read [references/recruitment-playbook.md](references/recruitment-playbook.md) during evidence collection and [references/customer-testing.md](references/customer-testing.md) before recruitment, test planning, moderation, or synthesis.

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
7. Run `guidance --workspace <sprint-directory>` and use its compact current-step card.
8. Ask only for the information needed to progress.

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

Use `guidance --workspace <sprint-directory>` for the default compact card. It
shows why the step matters, canonical purpose, selected method and timebox, AI
role, one human action, and the definition of done without dumping examples or
the full rationale. Offer these actions:
`show-example`, `explain-why`, `show-canonical-method`, `show-checklist`,
`compare-substitutes`, `i-am-blocked`, and `pause`. Run the matching
`guidance --action <action>` only when requested or when its specific detail is
needed to unblock the current step. Never paste the full guidance registry into
normal conversation or specialist packets.

## Delegate through role contracts

Generate work packets with `sprint_workspace.py role-packet` using the exact role identifiers in `role-contracts.json`. Every assignment must include:

- role name and mission;
- permitted inputs;
- one bounded task;
- required return format;
- forbidden actions;
- stop condition.

Also provide a human-safe assignee label, a unique run ID, and a separate packet output path. The command atomically writes the immutable packet and registers its version, SHA-256 digest, input snapshots, timestamps, lifecycle state, required outputs, and independence group in `assignment-manifest.json`.

Require specialists to return:

1. findings;
2. supporting evidence and provenance;
3. assumptions or inferences;
4. recommendation;
5. risks or disagreements;
6. open questions.
7. stop condition reached.

Specialists submit working memos. The Orchestrator reconciles conflicts, asks the human at decision gates, updates canonical JSON, and renders disposable HTML views.

Save each memo separately from its packet, then register it with `role-result`. The engine verifies all required sections, its content digest, freshness against packet inputs, duplicate paths/content, and declared or detectable peer-result inclusion. Use `assignment-status` to mark a run in progress or accept/reject a returned memo. A step cannot complete until every required specialist role has a valid returned or accepted memo.

Keep divergent role packets and results separate below `working/<step>/` until every assigned specialist has returned.

## Maintain the sprint record

Use the workspace engine instead of editing generated HTML or sprint state manually:

- `new-artifact` creates a structured artifact-data draft from [references/artifact-specs.json](references/artifact-specs.json).
- `prototype-recommend` recommends the lowest-cost test-artifact rung and a provider-neutral tool route from the declared reality needs.
- `prototype-approve` records the human's experiment, tool, account, cost, data, and deployment boundary decisions without performing any external action.
- `prototype-build-packet` creates an immutable packet from only the approved structured brief and explicitly approved assets.
- `prototype-trial` records a moderated run using the actual canonical interview script; `prototype-freeze` writes the immutable trial-passed deployment/version record.
- `set-challenge` and `question` keep the dashboard challenge and open-question state current.
- `render` safely escapes artifact data and rebuilds all HTML.
- `render --check` fails without writing when generated HTML or CSS is stale.
- `artifact-status` changes an artifact from draft through completion.
- `complete-step` enforces required artifacts and pauses at human gates.
- `gate` records an explicit human attestation: decision, decider label, considered-input digests, timestamp, optional rationale, and reservations.
- `set-concept` records the selected concept; changing an attested route or concept supersedes the prior gate decision and requires a new decision event.
- `role-packet` registers bounded assignments; `role-result` and `assignment-status` validate returned memos and advance lifecycle state.
- `customer` records the suitable audience, target, rationale, and planning status; completed counts are manifest-derived.
- `recruitment-status` keeps the early recruitment owner, status, next action, deadline, candidate/booking counts, and seven milestones visible; it does not send outreach, spend money, or engage a vendor.
- `guidance` renders the compact current-step contract or one requested deeper-help action in text or JSON.
- `session-init` creates one isolated participant record and anonymized summary draft bound to an immutable trial-passed tested-version record.
- `session-packet` generates that participant's bounded fresh-chat handoff from declared inputs only.
- `session-checkpoint`, `session-complete`, and `session-reopen` persist resumable state and derive counted completion from the canonical manifest.
- `synthesis-packet` creates a separate bounded fresh-chat input from the shared scorecard and structured summaries, excluding raw transcripts by default.
- `set-method-profile` and `set-execution-mode` record selector changes before work begins.
- `record-fidelity` records the selected method, human and AI participants, actual timebox, and any deviation with its reason and impacts.
- `validate` checks state, gates, artifact completeness, customer evidence, HTML tokens, and local links.
- `export` prepares either an explicitly approved private archive or a redaction-checked shareable static site outside the source workspace; `--zip` adds an optional deterministic archive, and the command never uploads or publishes.
- `migrate` previews or safely upgrades supported legacy state and artifact JSON while preserving an untouched backup.

The state schema stores `methodProfile`, `executionMode`, `route`, and `fidelity` separately. Every fidelity step retains its canonical purpose, default and selected methods, participants, suggested and actual timebox, deviations, and impact statements. Route exclusions are not counted as deliberate skips. Schema 1.0 workspaces are migrated as adaptive/live with an explicit compatibility note; review that assumption when resuming old work.

Update canonical artifact JSON below `artifact-data/`, including its `updatedAt`, then run `render`. Never edit `index.html`, `assets/sprint.css`, or files below `artifacts/` directly; they are disposable generated views. Rendering does not update workflow timestamps.

Treat `assignment-manifest.json` and role packets as engine-owned canonical provenance. Do not hand-edit their digests or lifecycle records. The dashboard deliberately omits packet inputs, objectives, memo paths, and memo bodies; safe labels, lifecycle status, and abbreviated digests are provenance, not permission to publish the private workspace.

Create the artifacts specified by the guided workflow only when their phase begins, except for `10-test-plan`: create its structured `recruitmentPlan` during `03-evidence`, then complete the interview tasks and protocol during `10-prototype`. Do not pre-fill later outcomes with invented evidence.

Do not copy a private workspace into this public skill repository. If the human wants to publish an example or a usage/cost claim, prepare a separate explicitly approved export using [the site-export workflow](references/site-exports.md), follow the [publication checklist](references/privacy-and-publication.md#publication-checklist), and keep the private source repository private. Export preparation is not publication approval and must not trigger an upload.

For a usage or cost claim, create one strict redacted usage record per internal,
customer-runtime, customer-session, or synthesis scope and run
`scripts/usage_report.py` with an immutable dated pricing snapshot. Keep
observations, base-rate equivalents, excluded charges, and hypothetical planning
scenarios separately labelled. Never add reasoning tokens twice, silently treat
missing request/model/cache/tool/credit data as zero, map subscription counters
to API line items, or describe an untested plan as a minimum.

## Protect customer integrity

Use AI to prepare recruitment criteria, interview scripts, prototypes, note structures, and synthesis. Permit AI moderation only when the user has suitable tooling and participant consent.

Never:

- present an AI persona as a real customer;
- fabricate quotations, behaviours, interviews, or analytics;
- count synthetic evaluation as customer testing;
- expose unnecessary personal information in artifacts;
- call directional evidence universal validation.

In live mode, if no real customer evidence is available, stop at `Ready for customer testing` when testing can still proceed. If testing is genuinely blocked or the route is `no-sprint`, Gate 5 may close only as `closed-unvalidated` with an `Investigate` or `Stop` outcome. A self-test or planning/rehearsal may close only in its explicit unvalidated terminal state, also as `Investigate` or `Stop`, after both customer sessions and customer-evidence synthesis are skipped and audited truthfully.

For a live Sprint-book profile, plan five suitable one-to-one customer sessions by default. A different target is allowed only with a recorded reason and fidelity/evidence/readiness impact. In self-test and planning/rehearsal modes, auditably skip the live customer-session and customer-evidence synthesis steps, use only `Synthetic rehearsal` labels for role-play, and never complete a customer-evidence artifact.

During `03-evidence` on every live route, create `10-test-plan` and tailor its
structured recruitment plan. Define qualifying and disqualifying behavior,
approve a neutral screener, choose from existing customers, networks,
communities, panels, partners, or direct outreach, and prepare invitation,
confirmation, reminder, cancellation, schedule, consent, and backup material.
Record an owner, status, next action, deadline, and partial-recruitment path
before completing evidence. A paid panel is an optional route, never a
requirement, and spending always needs explicit human approval. Keep the
original target visible after cancellations; connect any shortfall to the
separate evidence-strength and decision-readiness assessment instead of
silently lowering it.

Keep planned, invited, attempted, completed, qualified, excluded, and usable counts separate. Report zero usable as not tested, one or two as early/limited, three or four as partial directional, five as the book target met, and more than five as extended. These are method-coverage descriptions, never statistical confidence or population validation. A completed session enters synthesis only when participant fit, protocol fidelity, critical-scenario coverage, and explicit usability support it.

For every live participant, follow the full command sequence in
`references/customer-testing.md`. Never set a completed count directly: the
session manifest derives it from unique validated records. Start the participant
and synthesis packets in fresh chats, respect their recorded character budgets,
and preserve immutable files for every prototype/questions version.

## Complete the sprint

Finish only after the human makes a recorded outcome decision: `Proceed`, `Iterate`, `Pivot`, `Investigate`, or `Stop`. Publish the final HTML outcome report with process status, method fidelity, descriptive evidence strength, decision readiness, limitations, unresolved risks, owners, and dated next actions. Mark customer testing truthfully as complete, partial, or not conducted; never translate participant count into statistical confidence.

The dashboard, every rendered artifact, status output, and any sanitized export must show process completion separately from `terminalState`, customer validation, and the generated method-fidelity assessment. The fidelity summary must list the one-human-plus-AI team-model adaptation, every material deviation, and the limitations those choices place on evidence and decision readiness.

Every material finding must retain `n/N` support, contradictions, anonymized participant/session IDs, prototype and question versions, exact observation/inference IDs, limitations, remaining uncertainty, and an action-specific next decision with the smallest next learning action. Keep mixed segments, mixed versions, moderator deviations, excluded sessions, and automatic partial-evidence limitations visible.

Run `validate --workspace <sprint-directory>` before handoff. Do not call the sprint complete while validation errors remain.
