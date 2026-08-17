# Sprint Transition Model

This is the normative workflow contract enforced by
`scripts/sprint_workspace.py`. JSON Schema validates document shape; this model
validates whether the recorded history can truthfully represent the selected
route.

## Route transitions

| Current route | Allowed next route | Gate |
|---|---|---|
| `undecided` | `research-first`, `foundation-plus-design`, `full-design-sprint`, `focused-design-sprint`, or `no-sprint` | Select during `02-qualify`, after `01-intake` and before Gate 1 |
| `research-first` | `foundation-plus-design`, `full-design-sprint`, `focused-design-sprint`, or `no-sprint` | Reroute only after Gate 1 and completed `03-evidence` |
| Any final route | None | Start a new workspace rather than rewriting approved history |

`routeHistory` starts at `undecided`, is continuous, and ends at the current
route. It contains one initial transition and, only for `research-first`, one
post-research transition. Every transition records a non-blank reason and
timestamp. A workspace cannot finish while its route is `undecided` or
`research-first`. A post-research transition supersedes the original Gate 1
attestation and cannot advance beyond `03-evidence` until the human records a
new Gate 1 decision for the final route.

## Route and step matrix

`R` means required, `N/A` means excluded by the route, and `D` means deferred
until the required route transition. An exclusion is not a skip and does not
weaken method fidelity.

| Route | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `undecided` | R | R | D | D | D | D | D | D | D | D | D | D | D |
| `research-first` | R | R | R | D | D | D | D | D | D | D | D | D | D |
| `foundation-plus-design` | R | R | R | R | R | R | R | R | R | R | R | R | R |
| `full-design-sprint` | R | R | R | N/A | R | R | R | R | R | R | R | R | R |
| `focused-design-sprint` | R | R | R | N/A | R | R | R | R | R | R | R | R | R |
| `no-sprint` | R | R | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | R |
| `research-first` to `no-sprint` | R | R | R | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | R |

Required prior steps must appear exactly once in workflow order as completed or
as an eligible deliberate skip. A current or future step cannot appear in
history early. A gated completed step remains current until its gate closes.
The completed research step remains current until a final route is recorded
and re-attested at Gate 1.

## Skip policy

No general skip exists. `skip-step` accepts only the following deliberate
omissions; all other required steps must complete, and route exclusions remain
in `notApplicableSteps`.

| Execution mode | Step 11 | Step 12 | Other steps |
|---|---|---|---|
| `live` | May skip only when customer status is `blocked` and zero sessions completed | May skip only after step 11 was validly skipped under the same blocked condition | Never skippable |
| `self-test` | May skip because live sessions are prohibited | May skip only after step 11 was skipped | Never skippable |
| `planning-rehearsal` | May skip because live sessions are prohibited | May skip only after step 11 was skipped | Never skippable |

Each skip needs a non-blank reason and a fidelity deviation containing method,
evidence, and decision-readiness impacts.

## Gates and artifact readiness

Gates close in order after their owning step: Gate 1 after 02, Gate 2 after 06,
Gate 3 after 08, Gate 4 after 10, and Gate 5 after 13. A direct `no-sprint`
route closes Gate 1, marks Gates 2–4 not applicable, and continues at step 13.
Every completed gate references exactly one active, content-digested human
decision record; superseded decisions remain historical and cannot authorize
the current route or concept. A material concept change similarly supersedes
and reopens Gate 3.

Every role required for a step must have a current returned or accepted result
memo before the step can complete. Assignment presence does not replace route,
artifact, customer-session, or gate readiness.

An artifact may be `ready-for-decision` only for the current gated step while
that gate is still pending. This status can open review and lets the gated step
be marked complete, but it cannot close the gate. Every artifact owned by the
gated step must be `complete` before the decision is recorded. Ungated steps
always require complete artifacts.

A ready or complete artifact needs a meaningful summary and meaningful content
in every required section. Blank or whitespace-only strings, empty nested
arrays or objects, draft placeholders, label-only cards, and blank evidence
claims or sources do not count as content.

## Customer-session consistency

| Status | Count invariant |
|---|---|
| `not-planned` | invited, attempted, completed, qualified, excluded, and usable are zero; a Sprint-book live target may already be configured |
| `recruiting` | `sessionsPlanned > 0`, with no attempted or completed sessions |
| `scheduled` | planned and invited are positive, with zero completed sessions |
| `in-progress` | at least one session is attempted and usable remains below the planned target |
| `complete` | `sessionsPlanned > 0` and usable meets or exceeds the target; extended sessions do not rewrite the plan |
| `partial` | at least one session completed and usable remains below the planned target |
| `blocked` | usable remains below the planned target; zero activity is allowed before a target is secured |

Positive plans require a non-blank audience and rationale. Counts cannot be
negative; attempted cannot exceed invited, completed cannot exceed attempted,
qualified plus excluded cannot exceed invited, and usable cannot exceed either
completed or qualified. Completed and usable may exceed the planned target so
extended testing remains visible. Non-live modes require `not-planned` and all
seven counts at zero.
Every completed live session must be a counted entry in the canonical session
manifest with an isolated session record and a complete anonymized summary.
Completed records require granted consent, completed or unnecessary redaction,
immutable prototype/question version bindings, a unique participant/session
identity, and non-empty traceable evidence. The manifest lifecycle and quality
fields must reconcile the attempted, completed, qualified, excluded, and usable
state counts. Only completed, qualified, explicitly usable sessions may enter
synthesis; the rendered `11-customer-evidence` artifact presents the evidence
but is not the source of truth for any count.

Customer-session bands are descriptive: zero usable is `not-tested`, one or two
is `early-limited`, three or four is `partial-directional`, five is
`book-target-met`, and more than five is `extended`. These labels report method
coverage, never statistical confidence, representativeness, or prevalence.

When real sessions were completed but none are usable, step 11 may be completed
as partial and step 12 must be explicitly skipped with the evidence-quality
reason. That terminal path is still `not-tested` for evidence strength and may
close only as `Investigate` or `Stop`.

## Terminal states

Every terminal state has all of these invariants:

- a final route with continuous `routeHistory`;
- `currentStep` equal to completed `13-outcome`, no pending gate, and Gate 5
  complete with exactly one matching active human decision;
- every route-required step accounted for in order, with only policy-eligible
  skips and exact route exclusions;
- all required specialist results returned or accepted, all required artifacts
  complete, and all recorded sessions consistent;
- an outcome of `Proceed`, `Iterate`, `Pivot`, `Investigate`, or `Stop`.

The terminal evidence modes are:

| Terminal mode | Additional invariants | Allowed outcome |
|---|---|---|
| Tested live sprint | Steps 11 and 12 complete; customer status `complete` or `partial`; at least one recorded session | Any final outcome |
| Blocked live sprint | Step 11 validly skipped with customer status `blocked` and zero sessions; step 12 either truthfully completes without customer findings or is validly skipped | `Investigate` or `Stop` |
| Non-live rehearsal | Zero customer sessions and step 11 skipped | `Investigate` or `Stop` |
| `no-sprint` | Only the direct or post-research no-sprint history; Gates 2–4 not applicable | `Investigate` or `Stop` |

The `complete` status can be entered only by closing Gate 5. Updating a generic
next action cannot manufacture a terminal state.
