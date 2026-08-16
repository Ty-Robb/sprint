# Agent Role Isolation

Use specialist roles as bounded workers, not as a fictional committee. The human remains the Decider, and the Sprint Orchestrator remains the only role with a whole-sprint view.

## Contents

1. Source of truth
2. Runtime isolation model
3. Role routing
4. Independent divergence
5. Convergence and canonical writes
6. Fallback without subagents
7. Customer boundary

## Source of truth

Read [role-contracts.json](role-contracts.json) before assigning specialist work. It is the machine-readable source of truth for every role's mission, permitted work, prohibited work, and deliverable.

Generate assignments with the workspace engine rather than writing free-form role prompts:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py role-packet \
  --workspace <sprint-directory> \
  --role evidence-researcher \
  --task "Inventory the supplied evidence without proposing solutions." \
  --input artifact-data/01-sprint-brief.json \
  --output working/03-evidence/evidence-researcher.md
```

The command rejects inputs outside the sprint workspace and only writes packets below `working/`.

## Runtime isolation model

For every specialist assignment:

- name exactly one role;
- assign one bounded objective;
- include only declared input files;
- exclude unrelated conversation and artifacts;
- prohibit canonical writes;
- require the standard evidence-and-assumption return format;
- stop the specialist after the deliverable.

Treat these controls as behavioural containment. When the host supports isolated subagents or tool permissions, also enforce the boundary mechanically. Never claim prompt instructions provide a security sandbox.

## Role routing

| Step | Lead roles | Required independence |
|---|---|---|
| Intake | Sprint Orchestrator | No specialist needed unless evidence is supplied |
| Qualify | Evidence Researcher, Product Strategist | Assess evidence and strategic fit separately |
| Evidence | Evidence Researcher, Research Lead | Separate evidence inventory from recruitment planning |
| Foundation | Product Strategist, Evidence Researcher, Critical Reviewer | Critique only after the strategy draft exists |
| Map | Experience Designer, Technical Lead | Map experience and dependencies separately before merging |
| Questions | Product Strategist, Technical Lead, Critical Reviewer | Rank risks independently before convergence |
| Explore | Product Strategist, Experience Designer, Technical Lead, Critical Reviewer | Blind independent directions are mandatory |
| Decide | Sprint Orchestrator | Compare completed memos; human chooses |
| Experiment | Experience Designer, Research Lead, Technical Lead | Align scenes, evidence, and feasibility after separate drafts |
| Prototype | Prototype Builder, Critical Reviewer, Research Lead | Builder cannot mark its own work test-ready |
| Customer sessions | Research Lead | No synthetic participant evidence |
| Synthesis | Synthesis Analyst, Critical Reviewer | Reviewer challenges the completed synthesis |
| Outcome | Sprint Orchestrator | Human chooses the outcome |

## Independent divergence

During qualification, risk ranking, exploration, and prototype critique:

1. Generate all role packets before sharing any recommendation.
2. Give every specialist the same approved evidence base where relevant.
3. Keep each response in `working/<step>/<role>.md` or an equivalent isolated result.
4. Do not ask a specialist to react to another specialist until all independent work is complete.
5. Preserve minority recommendations and disagreements during synthesis.

This prevents the AI team from repeating the first plausible answer and calling it consensus.

## Convergence and canonical writes

Specialists produce working memos only. They must not edit:

- `sprint-state.json`;
- `index.html`;
- files below `artifacts/`;
- another role's working memo.

The Sprint Orchestrator must:

1. verify that every memo stayed in scope;
2. separate evidence from inference;
3. show material disagreements;
4. ask the human at the applicable gate;
5. update artifact data below `artifact-data/`;
6. render canonical HTML with the workspace engine.

## Fallback without subagents

When the host cannot create isolated subagents, perform explicit sequential role passes:

1. announce the role being entered;
2. load only the role packet and permitted inputs;
3. produce the required memo;
4. end the role pass;
5. clear its recommendation from the next divergent role's prompt;
6. return to the Sprint Orchestrator for synthesis.

Do not collapse roles into an unlabeled general analysis.

## Customer boundary

No AI role may act as customer evidence. Synthetic personas and adversarial role-play may be used only to rehearse a prototype or interview. Label those outputs `Synthetic rehearsal`, keep them out of `11-customer-evidence`, and never increment the real session count for them.
