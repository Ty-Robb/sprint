# HTML Output Standard

Create every user-facing sprint artifact as a portable, accessible HTML document backed by canonical JSON. Do not require a web server, build step, framework, CDN, web font, analytics script, or external asset.

## Contents

1. Canonical data and generated views
2. Start from the kit
3. Site manifest and shared navigation
4. Deterministic output rules
5. Artifact data schema
6. Required document structure
7. Dashboard requirements
8. Artifact requirements
9. Evidence presentation
10. Accessibility and safety
11. Completion checks

## Canonical data and generated views

The ownership boundary is deliberate:

- `sprint-state.json` is the canonical workflow record. Workflow commands own its
  transition fields and `updatedAt`; the renderer owns only its derived `artifacts`
  catalog.
- JSON below `artifact-data/` is the canonical content for each sprint artifact.
  The Orchestrator owns it and must update the artifact's `updatedAt` when its
  content or status changes.
- `index.html`, HTML below `artifacts/` and `session-evidence/`,
  `prototype-launch.html`, `site-manifest.json`, and `assets/sprint.css` are
  disposable generated views. Never edit or review them as an independent
  source of truth.
- `working/` contains non-canonical specialist material. `prototype/` is separately
  authored test material and is not overwritten by the renderer. The typed
  `prototypeBrief` within `artifact-data/10-prototype-brief.json` is canonical;
  the typed `recruitmentPlan` within `artifact-data/10-test-plan.json` is the
  early recruitment source of truth;
  `prototype/<version>/tested-version.json` is an immutable canonical record,
  while `artifacts/10-prototype-brief.html` is its accessible generated view.

If a view is missing or stale, repair it with `render`; do not copy changes back
from HTML into JSON. Rendering never advances a workflow or artifact timestamp.

## Start from the kit

Use `scripts/sprint_workspace.py` to initialise and render the workspace. The engine uses the files from `assets/html-kit/`:

- use `index-template.html` to create the living `index.html` dashboard;
- use `artifact-template.html` for each sprint artifact;
- use `site-page-template.html` for privacy-minimized session evidence and the
  tested-prototype launch wrapper;
- copy `sprint.css` to `assets/sprint.css` and preserve its class names.

Write structured content to JSON below `artifact-data/` and run `render`. The renderer validates and escapes the content, replaces template tokens, synchronises the derived artifact catalog, copies the stylesheet, and updates `index.html`.

Do not edit generated HTML below `artifacts/` directly. Do not insert raw HTML into artifact data.

The renderer sets the dashboard `<progress>` element's numeric value from sprint state.

## Site manifest and shared navigation

`site-manifest.json` is the sole generated catalog for site pages and their
relationships. Each entry records a stable page ID, type, title, relative path,
phase, status, route disposition, visibility, source version, content digest,
render digest, and Home/previous/next/related-evidence/decision/prototype/outcome
relationships. It also records the site version digest, export boundary, local
assets, and current prototype version context when applicable.

Every manifest page must render exactly one accessible `Sprint site` navigation
landmark and an `aria-current="page"` indication. The shell shows sprint title,
method profile, execution mode, route, current artifact/phase/status, and links
derived from the manifest. Previous and next skip `skipped` and
`not-applicable` pages; those pages remain directly addressable and visible from
the dashboard when present.

All local references are path-relative. Do not add root-relative URLs, absolute
filesystem paths, remote scripts, remote styles, web fonts, analytics, or
framework assets. A deep-linked artifact must return to Home when opened as a
`file:` URL, on localhost, at a domain root, or below a nested static-hosting
prefix.

Use `render --check` in CI or before review. It performs no writes and fails if a
generated file is missing, unexpected, has non-portable permissions, or differs
byte-for-byte from the current canonical JSON and templates. `validate` includes
the same freshness check.

## Deterministic output rules

- Engine-written JSON is UTF-8, uses two-space indentation, sorts object keys,
  preserves Unicode, rejects non-finite numbers, and ends with one LF newline.
- JSON object key order has no semantic meaning. Authored arrays preserve their
  canonical order, including sections, evidence, decisions, questions, and actions.
- Artifact JSON files are discovered by filename, then the artifact catalog and
  dashboard links are sorted by artifact ID. Duplicate IDs or output paths fail.
- HTML and CSS are UTF-8 copies of a deterministic render from canonical data and
  the checked-in templates. Rendering does not consult the clock.
- Engine-written JSON, HTML, CSS, and role packets use mode `0644` on POSIX
  platforms. Other platforms use their native permission model.
- Each target is written to a synced temporary file in the target directory and
  atomically replaced, so an interruption cannot expose a truncated file. An
  in-process batch failure restores already replaced targets when the platform
  permits, temporary files are cleaned up, and `render --check` detects any
  incomplete externally interrupted batch.

## Artifact data schema

Create an artifact with `new-artifact`, then replace its draft values. Keep this top-level shape:

```json
{
  "schemaVersion": "3.0",
  "id": "05-sprint-questions",
  "status": "draft",
  "updatedAt": "2026-01-01T12:00:00Z",
  "summary": ["A concise conclusion."],
  "sections": [],
  "evidence": [],
  "materialFindings": [],
  "unknowns": [],
  "nextActions": []
}
```

Use the exact required section titles from `artifact-specs.json`. The renderer supports:

- `paragraphs`: `{"type":"paragraphs","paragraphs":["..."]}`
- `list`: `{"type":"list","items":["..."]}`
- `ordered-list`: `{"type":"ordered-list","items":["..."]}`
- `table`: `{"type":"table","columns":["A","B"],"rows":[["...","..."]]}`
- `cards`: `{"type":"cards","cards":[{"title":"...","body":"...","status":"Assumption"}]}`
- `key-value`: `{"type":"key-value","items":[{"label":"...","value":"..."}]}`

Every section also needs a `title` and may include a short `eyebrow`. Do not place HTML in values; the renderer treats all content as text.

Use evidence entries shaped as:

```json
{
  "status": "Observed",
  "claim": "What the evidence supports",
  "source": "Source name or participant ID",
  "sourceUrl": "https://example.com/optional",
  "date": "2026-01-01"
}
```

Only use the evidence statuses defined below. Mark an artifact `ready-for-decision` or `complete` only after every required section contains meaningful content; the renderer rejects completed draft placeholders.

## Required document structure

Use semantic HTML:

```html
<!doctype html>
<html lang="en">
  <head>...</head>
  <body>
    <a class="skip-link" href="#main">Skip to content</a>
    <header>...</header>
    <main id="main" tabindex="-1">...</main>
    <footer>...</footer>
  </body>
</html>
```

Include a unique page title, UTF-8 charset, responsive viewport, link to the local stylesheet, visible sprint name, artifact status, last-updated date, and navigation back to the dashboard.

## Dashboard requirements

Make `index.html` the control centre, not a decorative cover. Show:

- in the first desktop viewport: sprint title, method profile, execution mode and
  its selector/reason, route, current step, current or final human decision, exact
  next action, process status, method fidelity, evidence strength, and decision
  readiness;
- a prominent customer-validation boundary in that same operational summary, so
  a self-test, rehearsal, skipped test, blocked test, or unvalidated closure can
  never inherit success styling from process completion;
- process status with completed, skipped, blocked, not-applicable, and not-started stages;
- method fidelity as a separate assessment with adaptations and limitations;
- descriptive evidence strength based on usable sessions, participant fit, protocol fidelity, tested versions, segment/scenario coverage, contradiction, directness, and uncertainty;
- decision readiness for the specific proposed action, with a plain-language reason rather than a numeric score;
- a compact current-step card with purpose, selected method/timebox, AI role,
  human action, and definition of done, with examples, rationale, canonical
  method, checklist, substitutes, blockers, and pause help collapsed on demand;
- the exact next action;
- human decisions and unresolved questions;
- customer-testing status plus separate planned, invited, attempted, completed, qualified, excluded, and usable counts;
- recruitment owner, status, next action, deadline, seven milestones, and a
  stalled/due prompt without requiring a paid vendor;
- links to every created artifact and prototype;
- links to the approved prototype/MVP brief, current tested artifact, and
  immutable deployment/version record without implying that a live URL is
  validated or production-ready;
- prominent blockers;
- a prominent customer-validation banner that says `UNVALIDATED` on every
  self-test, planning/rehearsal, blocked-live, and no-sprint export;
- evidence-status legend.

Derive every status label and status class from the same canonical state or
derived completion assessment. Do not hardcode an optimistic style beside a
dynamic label. Completion percentage counts only completed applicable steps;
skipped steps remain visible and never increase it.

Never show a later stage as complete merely because a placeholder file exists.

Do not describe the one-human-plus-AI Sprint-book profile as fully book-faithful. Render its team-model adaptation and every per-step substitution. Show the same four-dimensional assessment, execution mode, terminal state, validation notice, and automatically generated limitations in the final outcome artifact so exported conclusions cannot lose their method or evidence boundaries. Five suitable usable sessions means the book target was met; it never means statistically validated or representative. Separately sanitized exports must preserve those labels rather than copying conclusions without their boundary.

## Artifact requirements

Every artifact must answer:

- What is this artifact for?
- What was established?
- What evidence supports it?
- What remains assumed or unknown?
- What decision or next action follows?

Use concise sections, cards, tables, ordered steps, and callouts. Prefer text that can be printed and understood without the agent conversation. Include source links when external research is used.

## Evidence presentation

Use consistent status labels:

- `Observed` for supplied or directly collected evidence;
- `Assumption` for an untested belief;
- `Inference` for an interpretation of evidence;
- `Decision` for a deliberate human choice;
- `Unknown` when the current evidence cannot answer the question;
- `Synthetic rehearsal` for AI role-play that must not affect customer findings.

Keep quotations attributable to an anonymised participant or source. Separate observation from interpretation in customer-session material.

## Accessibility and safety

- Maintain logical heading order.
- Use landmarks, labels, exactly one page `h1`, a shared manifest-driven
  breadcrumb, table headers, captions, and descriptive links.
- Preserve visible keyboard focus.
- Do not rely on colour alone to communicate status.
- Meet readable contrast and support narrow screens.
- Wrap dense tables in a labelled, keyboard-focusable horizontal scroll region;
  the table may scroll, but the page itself must not overflow horizontally.
- Add meaningful alternative text to informative images; use empty alternative text for decorative images.
- Use reduced-motion preferences and avoid continuous animation.
- Include print styles.
- Escape user-supplied or researched text before inserting it into HTML.
- Do not insert untrusted HTML, remote scripts, tracking, or event handlers.
- Anonymise customer data and exclude unnecessary personal information.

Use inline SVG only when it materially clarifies a map or flow. Give it an accessible name and text equivalent.

## Completion checks

Before handing off an artifact:

1. Run `render --check` and `validate`.
2. Confirm that all template tokens are replaced.
3. Confirm that the manifest crawler resolves every page, asset, fragment, and
   deep link; rejects escaping or root-absolute paths; and reaches every
   manifest page from `index.html`.
4. Confirm that headings are ordered and tables have headers.
5. Confirm that the page works without JavaScript and external network access.
6. Confirm that status claims match `sprint-state.json`.
7. Confirm that observed evidence is not mixed with assumptions.
8. Confirm that customer testing is labelled complete, partial, or not conducted.
9. Confirm that the dashboard points to the latest artifact version.
10. Confirm that profile, mode, route, process completion, and method fidelity are separate and consistent with state.
11. Confirm that every displayed adaptation has a reason and method-fidelity, evidence, and decision-readiness impact in state.
12. Before any public release, complete the [publication checklist](privacy-and-publication.md#publication-checklist); workspace validation alone is not publication approval.
13. For any archive or shareable handoff, use the explicit process in
    [site exports and self-hosting](site-exports.md); never copy or publish the
    source workspace directly.
