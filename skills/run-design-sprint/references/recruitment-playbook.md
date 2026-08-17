# Practical Recruitment Playbook

Start this playbook during `03-evidence`, before the prototype is built. Store
the canonical plan in `artifact-data/10-test-plan.json` under
`recruitmentPlan`; render it into the dashboard and test-plan artifact. Keep
identities, contact details, consent records, recordings, and recruitment
exports in separately access-controlled source storage.

## Contents

1. Definition of ready
2. Target and screener
3. Channels and incentives
4. Outreach and scheduling
5. Consent and privacy
6. Backups and partial recruitment
7. Tracking and stalled recruitment
8. Hard-to-recruit participants
9. Templates

## Definition of ready

Before completing evidence on a live testing route, require:

- an audience defined by recent qualifying behaviours or circumstances and
  explicit disqualifiers;
- five planned suitable sessions plus suitable backups for a Sprint-book live
  run, or an adaptive target and rationale;
- a neutral approved screener that does not disclose the desired answer;
- at least one selected recruitment channel with its trade-off;
- usable invitation, confirmation, reminder, cancellation, and backup messages;
- session windows, timezone, accessibility route, and recruitment deadline;
- a consent checklist covering recording, anonymisation, withdrawal, use, and
  retention;
- an explicit recruitment owner, status, next action, and deadline;
- a backup and partial-recruitment plan that keeps the original target visible.

The plan can be ready before outreach is live. Do not claim that participants
are recruited until screening and booking actually occur.

## Target and screener

Translate the approved customer target into behavior, not a persona label.
Record what a suitable person has recently done, how recently, how often, and
whether they personally experienced or decided the relevant work. Exclude:

- colleagues or close collaborators who know the preferred answer;
- people with a material conflict of interest;
- professional respondents who cannot pass the behavioral screener;
- people outside the approved language, geography, role, or experience bounds
  when those bounds are material;
- participants whose accessibility needs cannot be supported in the current
  test setup; treat this as a test-accessibility blocker, not participant fault.

Use neutral prompts such as:

1. “Tell me about the last time you completed [relevant behavior].”
2. “How often have you done that in the last [period]?”
3. “Which tools, services, or workarounds did you use?”
4. “What part of that decision or task was personally yours?”
5. “What would help you participate comfortably in a remote session?”

Each question needs qualifying and disqualifying signals in the structured
plan. Do not name the prototype, preferred feature, desired sentiment, or
answer needed to qualify. The human approves the screener before it is sent.

## Channels and incentives

Present routes and let the human choose; never require a paid vendor:

| Channel | Useful when | Main trade-off |
|---|---|---|
| Existing customers | A reachable approved segment exists | Relationship and account context can bias candor |
| Founder/team networks | Speed matters and suitable second-degree contacts exist | Close contacts and colleagues must be excluded |
| Communities | The behavior maps to an active group | Follow community rules and avoid public collection of personal data |
| Research panels | Screening speed or specialist reach justifies spend | Cost and professional-respondent quality require approval and checks |
| Partners | A trusted intermediary reaches the segment | Partner selection can bias the sample |
| Direct outreach | Named roles or organizations are identifiable | More manual work and lower response rates |

An incentive compensates time and inconvenience; it does not buy a positive
answer. Choose an amount appropriate to session length, specialist scarcity,
local norms, and company policy. Record `pending` until the human approves any
spend. The engine records approval but never purchases incentives, engages a
vendor, connects an account, or sends a message without separate authorization.

## Outreach and scheduling

Keep the invitation short and neutral: why this person's recent experience is
relevant, what they will do, duration, format, incentive if approved, privacy
summary, and a clear response or booking action. Avoid pitching the preferred
solution.

Offer concrete windows with timezone labels. Confirm the participant's
timezone, device or environment needs, accessibility needs, recording choice,
and contact route. Leave enough space between sessions for notes and version
checks. Send a confirmation when booked and a brief reminder at the agreed
interval. A cancellation message should make withdrawal easy and say whether a
backup will be invited.

## Consent and privacy

Before a session:

- explain the research purpose without priming the desired result;
- say the prototype is being tested, not the participant;
- state what is recorded, who can access it, how it will be used, and when it
  will be deleted;
- obtain explicit consent for the actual recording and agent-assistance scope;
- provide a withdrawal route;
- use anonymized participant IDs in the sprint workspace;
- keep contact maps, raw media, transcripts, consent records, and recruitment
  exports outside the shareable workspace.

Regulated or sensitive research may require the user's legal, privacy,
security, ethics, or compliance process. The skill cannot determine legal
compliance or replace those approvals.

## Backups and partial recruitment

Book suitable backups where practical and state the activation trigger, such
as a cancellation, missed confirmation deadline, or insufficient screened
candidates. The smallest fallback sequence is:

1. contact already-qualified backups;
2. widen to another approved channel without changing the target criteria;
3. extend session windows or accessibility options;
4. review whether a criterion is truly required, recording any change and its
   evidence impact;
5. if the deadline arrives, run all suitable booked sessions and report the
   shortfall honestly.

Do not silently lower a five-session or adaptive target after cancellations.
Use the #11 completion/evidence model: zero usable is not tested; one or two is
early/limited; three or four is partial directional; five meets the Sprint-book
target; more than five is extended. These labels are not statistical
confidence. Record the remaining uncertainty and the smallest next learning
action. If no suitable session can proceed, use `waiting-for-customers` or the
audited blocked path; never invent findings.

## Tracking and stalled recruitment

Keep these milestones visible:

- target defined;
- screener approved;
- outreach live;
- candidates screened;
- sessions booked;
- backups booked;
- consent ready.

Update the owner, status, next action, deadline, counts, and completed
milestones with `recruitment-status`. Recruitment is stalled when its next
deadline has arrived while a required milestone remains incomplete, or when it
is explicitly blocked. Show the first incomplete milestone and the recorded
next action; do not respond by lowering suitability criteria automatically.

```bash
python3 <skill-dir>/scripts/sprint_workspace.py recruitment-status \
  --workspace <sprint-directory> \
  --owner "Research owner" \
  --status recruiting \
  --next-action "Send the approved invitation to the first 12 candidates." \
  --deadline 2026-08-20 \
  --complete-milestone target-defined \
  --complete-milestone screener-approved \
  --complete-milestone consent-ready
```

## Hard-to-recruit participants

- **B2B:** screen for personal responsibility, company size or operating
  context only when material, procurement conflicts, and permission to discuss
  the workflow without revealing confidential information.
- **Experts:** budget more lead time, prefer specific direct or partner
  outreach, and compensate specialist time when approved.
- **Regulated or sensitive groups:** complete required organizational review,
  minimize data, avoid unapproved recording, and define an incident/escalation
  owner before outreach.
- **Low-incidence targets:** use multiple approved channels, more backups, and
  earlier screening. Do not relax the defining behavior merely to fill slots.
- **Accessibility needs:** offer compatible formats, assistive-technology
  support, breaks, captions or interpreters where approved, and an alternative
  participation route.

## Templates

Replace brackets before use. The structured plan cannot be marked ready while
these placeholders remain.

### Invitation

> We are speaking with people who recently [neutral behavior]. This is a
> [duration]-minute research session about that experience and a prototype;
> we are testing the prototype, not you. [Approved incentive.] If interested,
> please complete [neutral screener or response route].

### Confirmation

> You are booked for [date, time, timezone] for [duration]. We will use
> [format/tool]. We will confirm consent before [recording/notes]. Please tell
> us about accessibility or technical needs. You may cancel at any time via
> [route].

### Reminder

> Reminder: your research session is [date, time, timezone] at [link/location].
> It lasts [duration]. Please join from [required device/environment]. Reply if
> you need an accessibility adjustment or need to reschedule.

### Cancellation

> Thanks for letting us know. Your session is cancelled and there is no penalty.
> [State what happens to already collected scheduling or screener data.] We may
> invite a qualified backup for the slot.

### Backup invitation

> A session window has opened at [date, time, timezone]. You previously passed
> the neutral screener for research about [behavior]. Participation remains
> optional; please confirm by [deadline] if the window works.
