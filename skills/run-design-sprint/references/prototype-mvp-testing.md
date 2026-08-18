# Prototype and MVP test-artifact workflow

Use this workflow before building anything for a sprint experiment. A prototype
is the smallest realistic test artifact needed to answer the approved sprint
questions. A live MVP is a thin operational slice used only when the hypothesis
depends on real behavior, data, transactions, integrations, background work, or
repeated use. They are not interchangeable.

## Test-artifact ladder

Choose the lowest rung capable of producing authentic evidence:

1. `copy-concept` — copy, concept, or value-proposition stimulus;
2. `concierge` — concierge or Wizard-of-Oz service test;
3. `clickable` — clickable interaction prototype;
4. `coded-facade` — realistic coded facade with controlled or synthetic data;
5. `live-mvp` — thin live MVP or feature-flagged product slice;
6. `limited-pilot` — limited real-service pilot.

Move upward only when the lower rung cannot expose the behavior needed to answer
the sprint question. AI build speed is not a reason to increase scope. A URL,
including a live URL, is not customer validation and is not evidence of
production readiness.

`prototype-recommend` provides a deterministic starting recommendation:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py prototype-recommend \
  --interaction-required
```

Available need flags cover manual service, interaction, coded fidelity, real
behavior, a real-service pilot, an existing product, and a no-external-tool
constraint. Treat the result as guidance to record and review, not as a
consequential decision made by the engine.

## Canonical structured brief

The structured recruitment plan starts earlier, during Step 3 evidence
collection. Keep `artifact-data/10-test-plan.json` as its canonical source while
the typed prototype/MVP brief is developed; Step 9 must make the selected
artifact rung and test scenes answer the same target and signals, and Step 10
must use the approved screener, logistics, consent, and backup plan rather than
silently replacing them.

At Step 9, create `10-prototype-brief` with `new-artifact`. Its canonical JSON
contains a typed `prototypeBrief` record; its accessible HTML is generated at
`artifacts/10-prototype-brief.html`. Complete every field before approving it:

- sprint questions, hypothesis, ladder choice, rationale, and why more fidelity
  is unnecessary;
- target customer, entry context, exact task, journey, and four to six critical
  scenes;
- observable success, ambiguity, and failure signals;
- what must be real and what is simulated, manually operated, delayed, or
  omitted;
- content, synthetic sample data, and empty, loading, and error states;
- device, browser, language, accessibility, and environmental conditions;
- which real-data, authentication, payment, integration, notification,
  persistence, background-job, or repeated-use capabilities are genuinely
  required;
- privacy, consent, security, regulatory, and data-classification boundaries;
- evidence capture and whether analytics is enabled;
- build timebox, owner, budget ceiling, and approval points;
- provider-neutral tool route and category, selected example, evaluated
  criteria, constraints, supporting categories, cost, and export/self-hosting
  strategy;
- deployment target, access, URL if any, expiry, cleanup, and rollback;
- explicit approval decisions, build packets, moderated trials, and immutable
  tested versions.

Edit canonical JSON rather than generated HTML. `artifact-status --status
complete` refuses a brief with placeholders, fewer than four or more than six
scenes, real capabilities assigned to a non-live rung, inconsistent public
access, or unresolved approval boundaries.

## Provider-neutral tool selection

Evaluate categories against the experiment rather than maintaining a universal
ranking:

- time to a testable artifact or URL;
- required interaction and visual fidelity;
- real data, authentication, payments, integrations, persistence, or background
  work;
- compatibility with the existing stack;
- exportability and self-hosting;
- collaboration and version control;
- privacy and data-processing implications;
- accessibility and device support;
- cost and required human approval;
- maintainability if the experiment becomes product work.

Provider-neutral primary routes are `no-external-tool`, `interaction-design`,
`portable-coded-facade`, `ai-assisted-app-builder`, `existing-product-slice`,
and `live-service-pilot`. Supporting categories include static hosting and
backend/data services, but add them only when the hypothesis requires them.

Current examples are optional guidance, not dependencies: repository-native
HTML/CSS/JavaScript; Figma or an equivalent interaction-design tool; v0,
Lovable, Replit Agent, Base44, or equivalent coded builders; the user's existing
application stack; and GitHub Pages, Cloudflare Pages, Vercel, Netlify, or a
self-hosted server. The no-external-tool route must continue to work when none
of these services is available.

Reference documentation:

- [Figma prototyping](https://help.figma.com/hc/en-us/articles/360040314193-Guide-to-prototyping-in-Figma)
- [v0 deployments](https://api2.v0.dev/docs/deployments)
- [Lovable publishing](https://docs.lovable.dev/features/publish) and [GitHub export](https://docs.lovable.dev/integrations/github)
- [Replit Agent build and publishing](https://docs.replit.com/build/your-first-app)
- [Cloudflare Pages static HTML](https://developers.cloudflare.com/pages/framework-guides/deploy-anything/)
- [Vercel deployments](https://vercel.com/docs/deployments/overview)

## Approval boundaries

Record each decision through `prototype-approve` after the human has actually
made it:

- `experiment-boundary` and `tool-choice` must be explicitly approved;
- `external-account`, `cost`, `data-exposure`, and `public-deployment` must be
  explicitly approved when applicable, or recorded as `not-required` with a
  rationale;
- a declined boundary blocks the brief.

The command records a decision; it does not connect an account, incur a charge,
upload data, enable analytics, change production, or deploy. Those external
actions still require the human's separate explicit authorization at the point
of action.

Never put secrets, production customer data, private transcripts, account
material, or unapproved proprietary assets into the brief or build packet.
Prefer test accounts and synthetic operational data even when participants are
real.

## Build, trial, freeze, and session sequence

1. Complete and approve the brief.
2. Generate an immutable AI build packet from only the approved brief and
   explicitly named assets:

   ```bash
   python3 <skill-dir>/scripts/sprint_workspace.py prototype-build-packet \
     --workspace <sprint-directory> \
     --asset <approved-workspace-file>
   ```

   Sensitive-source paths and secret-bearing file types are rejected. The packet
   fixes the scope and timebox, labels simulation, and prohibits unapproved
   account, spend, analytics, production, data, or public deployment actions.

3. Build only the approved scenes. Review broken flows, misleading simulation,
   accessibility, content neutrality, security, and accidental data exposure.
4. Complete `10-test-plan` during Step 10, then run a moderated trial with the
   actual canonical test plan and record it:

   ```bash
   python3 <skill-dir>/scripts/sprint_workspace.py prototype-trial \
     --workspace <sprint-directory> \
     --trial-id trial-v1 \
     --status passed \
     --moderator "human-safe label" \
     --prototype prototype/proto-v1/index.html \
     --interview-script artifact-data/10-test-plan.json \
     --finding "The full script ran without explaining the concept."
   ```

5. A passed trial is required before freeze. Put the artifact and bounded
   context below a new version directory and record deployment, expiry, cleanup,
   and rollback:

   ```bash
   python3 <skill-dir>/scripts/sprint_workspace.py prototype-freeze \
     --workspace <sprint-directory> \
     --version proto-v1 \
     --trial-run trial-v1 \
     --prototype prototype/proto-v1/index.html \
     --prototype-context prototype/proto-v1/context.md \
     --deployment-target "Private versioned preview" \
     --access-model private-preview \
     --cleanup-plan "Remove the preview after synthesis." \
     --rollback-plan "Return sessions to the prior immutable version."
   ```

   The command writes `prototype/<version>/tested-version.json`. It freezes the
   approved brief snapshot, build packet, passed trial, prototype/context hashes,
   experiment, storyboard, test plan, deployment, cleanup, rollback, and the
   explicit statement that the version is not yet customer-validated or
   production-ready. It records a deployment that a human has already approved;
   it never performs one.

6. Complete Gate 4 only after the tested version is frozen. `session-init`
   refuses an unfrozen or changed version. Every session manifest entry,
   canonical session record, anonymized summary, and fresh-chat packet links the
   same immutable tested-version record.
7. If the artifact, brief, or script changes between sessions, create a new build
   packet where applicable, run a new moderated trial, freeze a new version, and
   initialize later sessions against that version. Never overwrite a bound file.
8. Archive or remove temporary deployments according to the approved cleanup
   plan. Preserve immutable records so synthesis can separate version effects.

The dashboard and final outcome link the approved brief, current tested artifact,
immutable deployment/version record, normal evidence artifacts, and outcome.
