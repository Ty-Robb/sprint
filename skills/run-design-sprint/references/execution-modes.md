# Execution Modes, Closure, and Restart

Execution mode states what kind of activity is actually occurring. It is
independent of the method profile and route, and it must be chosen by a named
human with a non-blank reason.

| Mode | What may occur | Customer-evidence boundary |
|---|---|---|
| `live` | A real sprint with suitable real customers | Only counted, consented, traceable sessions may support customer findings |
| `self-test` | Exercise the workflow or the tool implementing it | No live or simulated customer activity may be recorded as customer evidence |
| `planning-rehearsal` | Prepare or rehearse future activity | Planned or role-played activity is not evidence that the activity occurred |

Initialize every workspace with explicit selection provenance:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py init \
  --title "<title>" \
  --challenge "<challenge>" \
  --execution-mode "<live|self-test|planning-rehearsal>" \
  --selected-by "<human-safe Decider label>" \
  --mode-reason "<why this mode truthfully describes the run>" \
  --output "<new-private-workspace>"
```

The canonical `executionModeSelection` record retains the selector, reason,
and timestamp. The dashboard, status output, and every rendered artifact repeat
the mode and validation boundary.

## Skipping customer-dependent steps

There is no general skip. Route exclusions remain `notApplicableSteps`, not
skips. In `self-test` and `planning-rehearsal`, explicitly skip both
`11-customer-sessions` and `12-synthesis`. In `live`, those steps may be skipped
only under the blocked zero-session rule in the transition model. Every skip
requires an approving actor and reason:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py skip-step \
  --workspace "<workspace>" \
  --step "11-customer-sessions" \
  --skipped-by "<human-safe Decider label>" \
  --reason "<why this mode and route permit the skip>"
```

`skipRecords` snapshots the step, actor, reason, execution mode, route, and
timestamp. `skipReasons` remains a compact lookup, and the fidelity record
retains the evidence and decision-readiness impact.

## Truthful terminal classifications

`status: complete` means only that the selected process route closed Gate 5.
The canonical `terminalState` carries the evidence truth:

| `terminalState` | Meaning |
|---|---|
| `live-customer-tested` | At least one suitable real-customer session and its synthesis completed in live mode |
| `self-test-complete-unvalidated` | The self-test process closed without customer validation |
| `planning-rehearsal-complete-unvalidated` | The plan or rehearsal closed without evidence that the planned activity occurred |
| `closed-unvalidated` | A blocked live or no-sprint route closed without customer validation |
| `not-terminal` | Gate 5 has not closed |

Non-live and otherwise unvalidated closures allow only `Investigate` or `Stop`.
They render a prominent `UNVALIDATED` or `CLOSED UNVALIDATED` banner in the
dashboard and every portable HTML artifact. A sanitized export must retain the
execution mode, terminal state, banner, and evidence labels.

Keep supplied hypotheses as `Assumption`, unanswered blanks as `Unknown`, and
AI role-play as `Synthetic rehearsal`. Never relabel those records `Observed`
when closing or exporting the workspace.

## Convert early or restart live

`set-execution-mode` may convert a workspace only before any step is completed
or skipped and before any customer-session record exists:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py set-execution-mode \
  --workspace "<untouched-workspace>" \
  --mode live \
  --selected-by "<human-safe Decider label>" \
  --reason "<what changed and why real customer work is now authorized>"
```

Once a rehearsal has progressed, keep it immutable and start a new live
workspace. Use a new output directory and select `live` explicitly. Carry
forward only reviewed challenge context, hypotheses, constraints, and plans;
preserve them as `Assumption`, `Unknown`, `Inference`, or `Synthetic rehearsal`
according to their original provenance. Do not copy completed steps, gates,
customer counts, terminal state, or `Observed` labels. Re-run qualification,
human gates, prototype readiness, suitable real-customer sessions, synthesis,
and the final decision in the new live workspace.
