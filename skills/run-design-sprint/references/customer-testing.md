# Real-Customer Testing Protocol

Use this protocol for recruitment, consent, moderation, evidence capture, and synthesis. Customer testing is directional research, not statistical proof.

## Contents

1. Evidence boundary
2. Recruitment
3. Consent and privacy
4. Interview structure
5. Moderation rules
6. Session workspace and versions
7. Session lifecycle commands
8. Structured summary and traceability
9. Bounded synthesis
10. Context and usage measurements
11. When testing cannot proceed

## Evidence boundary

Count a session only when:

- the participant is a real person;
- they plausibly match the approved recruitment criteria;
- they knowingly agree to participate;
- they encounter the prototype or stimulus under the planned conditions;
- their behaviour or words are recorded accurately;
- the record distinguishes observation from interpretation.

Do not count colleagues who know the desired answer, AI personas, unlabelled synthetic data, second-hand anecdotes, or customer comments unrelated to the tested hypothesis.

## Recruitment

Define:

- required behaviours or circumstances;
- disqualifying conditions;
- relevant experience level;
- geography or language where material;
- accessibility needs;
- conflicts of interest;
- desired session count;
- backup participants.

For a live Sprint-book profile, default to five suitable one-to-one sessions plus appropriate backups. An adaptive profile may set a different target for the challenge, but must record the target and rationale. Changing the Sprint-book target requires an explicit fidelity deviation with its effect on the method, available evidence, and decision readiness; it must never be presented as equivalent to the five-session default.

Use behavioural screener questions rather than asking whether someone identifies with a marketing persona. Avoid revealing the preferred product or answer in the screener.

Example structure:

1. “Tell me about the last time you [relevant behaviour].”
2. “How frequently have you done that in the last [period]?”
3. “Which tools or workarounds did you use?”
4. “Were you personally responsible for the decision?”
5. “Is there anything that would make participating difficult?”

Recruitment must begin during the evidence phase because participants are usually the longest-lead dependency.

## Consent and privacy

Before recording:

- explain the session purpose without priming the desired result;
- state what will be recorded and how it will be used;
- obtain explicit consent;
- explain that the prototype is being tested, not the participant;
- allow withdrawal;
- avoid collecting unnecessary personal or sensitive data.

Use participant IDs such as `P01`. Store contact details separately from the shareable sprint bundle. Never put secrets, full names, email addresses, or unnecessary personal attributes into HTML artifacts.

The shareable sprint bundle is still private by default because combinations of dates, quotations, company context, and behaviour can re-identify a participant. Store identity/contact maps, raw transcripts, audio/video, consent records, and recruitment exports in separately access-controlled source storage. Do not publish session material until it passes the [publication checklist](privacy-and-publication.md#publication-checklist).

## Interview structure

Use a consistent five-part session:

### 1. Welcome and consent

Confirm consent, explain think-aloud expectations, and establish that honest confusion is useful.

### 2. Context

Ask about recent real behaviour before showing the prototype. Prefer “Tell me about the last time...” over general opinions.

### 3. Prototype tasks

Give realistic goals rather than instructions that reveal interface labels. Present one task at a time. Do not teach the interface.

### 4. Follow-up

Ask open questions about expectations, interpretation, trust, uncertainty, alternatives, and missing information. Probe observed behaviour rather than defending the design.

### 5. Close

Ask what the participant expected to happen next, invite final comments, explain what happens with their data, and thank them.

## Moderation rules

- Ask open, neutral questions.
- Leave silence rather than rescuing the participant.
- Do not explain a confusing element during the task.
- Do not praise desired behaviour.
- Ask “What are you thinking?” instead of “Do you like it?”
- Separate a usability failure from a proposition failure.
- Record deviations from the script.
- Do not modify the prototype between sessions without marking a new test version.

AI may help transcribe or moderate only when the participant has consented and suitable tools are available. The Research Lead remains responsible for neutral prompts and evidence integrity.

## Session workspace and versions

Every new workspace has one canonical
`customer-testing/session-manifest.json`. It is the only source for session
membership and counted completion; the aggregate count in `sprint-state.json`
is derived from it. Do not edit `sessionsCompleted` directly.

Each participant/test session is isolated:

```text
customer-testing/
├── session-manifest.json
├── sessions/
│   └── S01/
│       ├── session.json             Canonical status, checkpoint, metadata, and pointers
│       ├── summary.json             Anonymized structured summary
│       └── handoff.md               Generated fresh-chat packet
└── synthesis/
    └── synthesis-packet.md          Generated summaries-only packet
```

Use a session ID such as `S01` and a separate anonymized participant ID such
as `P01`. Keep the reversible identity/contact map outside the workspace.
Raw notes, transcripts, recordings, and consent documents should also remain
in separately access-controlled source storage. `session.json` and
`summary.json` retain opaque audit references, not the raw content.

Prototype, prototype-context, interview-guide, and scorecard files become
immutable when a version is catalogued: the manifest records each path,
character count, and SHA-256 hash. After Gate 4, preserve the approved
`prototype/index.html` at a stable test-version path such as
`prototype/proto-v1/index.html`. Use similarly versioned paths such as
`working/11-customer-sessions/versions/questions-v1/scorecard.md` for the guide
and scorecard.
Never overwrite a file already bound to a version. Create a new path and
version ID, then use `session-init --activate-versions` for the first session
on the new pair. A session cannot silently use content that differs from its
recorded prototype or questions version.

## Session lifecycle commands

First record the audience and planned total; completion remains manifest-derived:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py customer \
  --workspace <sprint-directory> \
  --status scheduled \
  --target "People matching the approved behavioural criteria" \
  --planned 5
```

Initialize one isolated record. `--prior-decision` may be repeated and should
name only decisions required to run this session:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py session-init \
  --workspace <sprint-directory> \
  --session-id S01 \
  --participant-id P01 \
  --session-date 2026-08-17 \
  --run-mode human-run \
  --prototype-version proto-v1 \
  --questions-version questions-v1 \
  --prototype prototype/proto-v1/index.html \
  --prototype-context working/11-customer-sessions/versions/proto-v1/context.md \
  --interview-guide working/11-customer-sessions/versions/questions-v1/interview-guide.md \
  --scorecard working/11-customer-sessions/versions/questions-v1/scorecard.md \
  --prior-decision artifact-data/07-decision.json
```

Generate exactly one canonical packet path for that session, then start a new
chat with `handoff.md` as its complete operating context:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py session-packet \
  --workspace <sprint-directory> --session-id S01
```

The packet embeds only the declared prototype context, interview guide,
scorecard, required prior decisions, and—after a reopen—the persisted
checkpoint and anonymized structured state. It references the prototype to
open but does not embed the prototype implementation, sprint history, another
participant's data, or any raw evidence.

For a long or interrupted session, persist a checkpoint before the chat ends:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py session-checkpoint \
  --workspace <sprint-directory> \
  --session-id S01 \
  --status in-progress \
  --phase follow-up \
  --completed-phase welcome-and-consent \
  --completed-phase prototype-tasks \
  --next-action "Finish neutral follow-up questions, then close."
```

Update `summary.json`, then complete the session. Completion requires granted
consent, a completed or not-required redaction review, traceable observations,
task outcomes, and question evidence. Runtime usage flags are optional; when
the runtime exposes none, preserve the explicit unavailable reason:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py session-complete \
  --workspace <sprint-directory> \
  --session-id S01 \
  --consent-status granted \
  --consent-scope "Notes and anonymized research summary" \
  --consent-reference "restricted-consent-register:S01" \
  --redaction-status complete \
  --removed-category direct-identifiers \
  --limitation "Remote session; cursor movement was not captured" \
  --usage-unavailable-reason "The runtime did not expose request usage."
```

`session-complete` counts a unique record once. Calling it again fails rather
than incrementing the aggregate. To revise a completed/blocked/withdrawn
record, reopen it; this removes its counted and synthesis-eligible status until
it passes completion again:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py session-reopen \
  --workspace <sprint-directory> \
  --session-id S01 \
  --reason "Clarify the TASK-2 outcome classification"

python3 <skill-dir>/scripts/sprint_workspace.py session-packet \
  --workspace <sprint-directory> --session-id S01
```

The regenerated packet carries the checkpoint and structured summary, so a
fresh chat can resume without replaying the prior conversation.

## Structured summary and traceability

For each anonymised participant, capture:

- participant ID and qualification summary;
- session date and prototype version;
- relevant context;
- tasks attempted;
- observable actions and pauses;
- verbatim quotations where accurately captured;
- task outcomes;
- evidence for or against each sprint question;
- moderator deviations;
- interpretation in a separate field;
- data-quality limitations.

Label observations `Observed`. Label any explanation of what the behaviour may mean `Inference`.

The strict `summary.json` record separates raw-source pointers, observations,
and inferences. Give source pointers IDs such as `SRC1`, observation IDs such
as `OBS1`, task IDs such as `TASK-1`, and question IDs matching the unchanged
scorecard. Every observation must point to one or more source IDs. Every task
outcome, inference, and question assessment must point to known observation
IDs. Store moderator deviations explicitly. Store a quote locator and source
ID rather than copying a quotation into the synthesis input. `validate`
rejects broken pointers, duplicate session identities,
version/hash drift, stale packets, direct email addresses in summaries,
or aggregate counts that disagree with the manifest.

## Bounded synthesis

Before synthesis, confirm:

- at least one suitable real session exists;
- session records are complete enough to audit;
- participant identity is anonymised;
- prototype versions are known;
- deviations are visible;
- synthetic rehearsal is excluded;
- the original sprint questions and scorecard have not been rewritten after seeing results.

Small samples reveal directional patterns and failure modes. They do not establish population-level prevalence.

Generate synthesis only after the selected summaries are complete and use the
same questions version:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py synthesis-packet \
  --workspace <sprint-directory>
```

By default the command selects every complete, counted,
`includeInSynthesis` session. Repeat `--session-id` to select a subset. It
refuses to mix questions versions. The generated packet contains the shared
scorecard and sanitized structured summaries only. It removes raw-reference
locations while preserving source/quote pointer IDs, record paths, summary
hashes, and explicit trace IDs such as `S01/OBS1` and `S01/Q1`.

Run synthesis in another fresh chat using only
`customer-testing/synthesis/synthesis-packet.md`. Every returned claim must
cite one or more included trace IDs. In `artifact-data/12-synthesis.json`, put
each synthesized claim in the `evidence` claim registry and place those trace
IDs in its `source`; `complete-step` and `validate` reject missing or unknown
trace IDs. Opening raw evidence is a separate, human-authorized audit pass,
never the default synthesis context. Any session
completion, reopen, or summary change makes the recorded synthesis input stale;
regenerate it before completing the synthesis step.

## Context and usage measurements

New workspaces default to a 24,000-character participant-packet limit, a
48,000-character synthesis-packet limit, and an 80% warning threshold. These
are transparent guardrails, not model-token guarantees. Override them at
workspace creation with `--session-context-maximum`,
`--synthesis-context-maximum`, and `--context-warning-percent`.

Packet generation reports actual characters, warns at the configured
threshold, refuses to write an over-budget packet, and always states that a
fresh chat is required. Raw evidence size never contributes because raw files
are not read. Session records can store input, output, and total tokens,
request count, and duration when response metadata exposes them. They use the
`customer-session` measurement context compatible with the usage evidence
work; an unavailable reason is required otherwise. Packet characters and
runtime token usage are distinct measurements. Internal development/test usage
must never be presented as customer-runtime capacity evidence.

When a session contributes to a public usage or capacity statement, export its
counts to a separate redacted `customer-session` usage record and calculate the
cross-run report as documented in [usage-reporting.md](usage-reporting.md). Do
not publish the private session record itself. Keep synthesis in its own scope,
and preserve missing request/model/cache/tool/credit data as warnings and
exclusions rather than filling it with zeroes.

## When testing cannot proceed

Set the workspace to `waiting-for-customers` when suitable sessions cannot occur. The skill may still produce:

- a test-ready prototype;
- recruitment criteria and screener;
- consent language;
- interview script;
- evidence-capture structure;
- a clear customer-testing blocker.

Do not create customer findings, synthesis, or a proceed/iterate/pivot outcome until real sessions exist. The human may choose `Investigate` or `Stop` if the sprint must close without testing.

In `self-test` or `planning-rehearsal` execution mode, no customer evidence is expected or permitted. Rehearsed interviews, AI personas, and synthetic reactions must use the `Synthetic rehearsal` label, stay outside the customer-evidence artifact, and never increment session counts. A non-live final outcome must remain explicitly unvalidated and cannot use `Proceed`, `Iterate`, or `Pivot` as though customer evidence supported it.
