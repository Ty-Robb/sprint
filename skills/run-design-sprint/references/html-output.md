# HTML Output Standard

Create every user-facing sprint artifact as a portable, accessible HTML document. Use JSON only for internal sprint state. Do not require a web server, build step, framework, CDN, web font, analytics script, or external asset.

## Contents

1. Start from the kit
2. Required document structure
3. Dashboard requirements
4. Artifact requirements
5. Evidence presentation
6. Accessibility and safety
7. Completion checks

## Start from the kit

Copy the files from `assets/html-kit/` into the sprint output directory:

- use `index-template.html` to create the living `index.html` dashboard;
- use `artifact-template.html` for each sprint artifact;
- copy `sprint.css` to `assets/sprint.css` and preserve its class names.

Replace all `{{TOKEN}}` placeholders. Remove unused example blocks instead of leaving empty UI. Update `index.html` after every material change.

Set the dashboard `<progress>` element's numeric `value` attribute to the same percentage shown in its visible text.

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
