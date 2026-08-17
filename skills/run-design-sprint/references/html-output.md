# HTML Output Standard

Create every user-facing sprint artifact as a portable, accessible HTML document. Use JSON only for internal sprint state. Do not require a web server, build step, framework, CDN, web font, analytics script, or external asset.

## Contents

1. Start from the kit
2. Artifact data schema
3. Required document structure
4. Dashboard requirements
5. Artifact requirements
6. Evidence presentation
7. Accessibility and safety
8. Completion checks

## Start from the kit

Use `scripts/sprint_workspace.py` to initialise and render the workspace. The engine uses the files from `assets/html-kit/`:

- use `index-template.html` to create the living `index.html` dashboard;
- use `artifact-template.html` for each sprint artifact;
- copy `sprint.css` to `assets/sprint.css` and preserve its class names.

Write structured content to JSON below `artifact-data/` and run `render`. The renderer escapes text, replaces template tokens, registers artifacts, copies the stylesheet, and updates `index.html`.

Do not edit generated HTML below `artifacts/` directly. Do not insert raw HTML into artifact data.

The renderer sets the dashboard `<progress>` element's numeric value from sprint state.

## Artifact data schema

Create an artifact with `new-artifact`, then replace its draft values. Keep this top-level shape:

```json
{
  "schemaVersion": "1.0",
  "id": "05-sprint-questions",
  "status": "draft",
  "updatedAt": "2026-01-01T12:00:00Z",
  "summary": ["A concise conclusion."],
  "sections": [],
  "evidence": [],
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
    <main id="main">...</main>
    <footer>...</footer>
  </body>
</html>
```

Include a unique page title, UTF-8 charset, responsive viewport, link to the local stylesheet, visible sprint name, artifact status, last-updated date, and navigation back to the dashboard.

## Dashboard requirements

Make `index.html` the control centre, not a decorative cover. Show:

- sprint title, route, status, and current step;
- overall progress and completed stages;
- the exact next action;
- human decisions and unresolved questions;
- customer-testing status and session count;
- links to every created artifact and prototype;
- prominent blockers;
- evidence-status legend.

Never show a later stage as complete merely because a placeholder file exists.

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
- Use landmarks, labels, table headers, captions, and descriptive links.
- Preserve visible keyboard focus.
- Do not rely on colour alone to communicate status.
- Meet readable contrast and support narrow screens.
- Add meaningful alternative text to informative images; use empty alternative text for decorative images.
- Use reduced-motion preferences and avoid continuous animation.
- Include print styles.
- Escape user-supplied or researched text before inserting it into HTML.
- Do not insert untrusted HTML, remote scripts, tracking, or event handlers.
- Anonymise customer data and exclude unnecessary personal information.

Use inline SVG only when it materially clarifies a map or flow. Give it an accessible name and text equivalent.

## Completion checks

Before handing off an artifact:

1. Confirm that all template tokens are replaced.
2. Confirm that local links resolve.
3. Confirm that headings are ordered and tables have headers.
4. Confirm that the page works without JavaScript and external network access.
5. Confirm that status claims match `sprint-state.json`.
6. Confirm that observed evidence is not mixed with assumptions.
7. Confirm that customer testing is labelled complete, partial, or not conducted.
8. Confirm that the dashboard points to the latest artifact version.
9. Before any public release, complete the [publication checklist](privacy-and-publication.md#publication-checklist); workspace validation alone is not publication approval.
