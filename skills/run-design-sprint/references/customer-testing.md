# Real-Customer Testing Protocol

Use this protocol for recruitment, consent, moderation, evidence capture, and synthesis. Customer testing is directional research, not statistical proof.

## Contents

1. Evidence boundary
2. Recruitment
3. Consent and privacy
4. Interview structure
5. Moderation rules
6. Session record
7. Synthesis readiness
8. When testing cannot proceed

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

## Session record

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

## Synthesis readiness

Before synthesis, confirm:

- at least one suitable real session exists;
- session records are complete enough to audit;
- participant identity is anonymised;
- prototype versions are known;
- deviations are visible;
- synthetic rehearsal is excluded;
- the original sprint questions and scorecard have not been rewritten after seeing results.

Small samples reveal directional patterns and failure modes. They do not establish population-level prevalence.

## When testing cannot proceed

Set the workspace to `waiting-for-customers` when suitable sessions cannot occur. The skill may still produce:

- a test-ready prototype;
- recruitment criteria and screener;
- consent language;
- interview script;
- evidence-capture structure;
- a clear customer-testing blocker.

Do not create customer findings, synthesis, or a proceed/iterate/pivot outcome until real sessions exist. The human may choose `Investigate` or `Stop` if the sprint must close without testing.
