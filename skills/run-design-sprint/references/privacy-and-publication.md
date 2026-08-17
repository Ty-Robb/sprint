# Privacy and Publication Boundary

Use this policy before creating a sprint workspace and before publishing any material derived from one.

## The boundary

This public skill repository may contain:

- the reusable workflow engine, templates, role contracts, and documentation;
- minimal fixtures that are explicitly marked as synthetic;
- sanitized publication records that meet this policy; and
- public facts whose sources and dates are recorded.

Keep these materials private by default:

- every generated sprint workspace, including `artifact-data/`, `artifacts/`, `working/`, `prototype/`, `sprint-state.json`, and rendered HTML;
- raw or lightly edited transcripts, recordings, notes, quotations, consent records, recruitment exports, and participant identity/contact maps;
- customer, prospect, partner, employee, or company-confidential data;
- generated client work, prototypes, screenshots, filenames, URLs, and metadata that reveal private context;
- analytics exports, usage-dashboard captures, billing details, plan entitlements, account or organisation identifiers, and credentials; and
- private usage/cost source evidence that has not been deliberately sanitized for publication.

Anonymised does not automatically mean public. A combination of a participant ID, date, quotation, job detail, and company context can still identify someone. Keep a private case-study repository private; neither this skill nor its tests require that repository to be public or copied here.

The generated dashboard's specialist provenance view is deliberately narrow: role, human-safe assignee label, hashed run reference, lifecycle status, and abbreviated packet/result digests. It does not render the raw run ID, objective, permitted-input paths, packet body, or result-memo contents. That minimisation reduces accidental exposure but does not make the dashboard or assignment manifest public; both remain private by default.

## Storage before starting a sprint

Choose an access-controlled private root outside the checkout of any public repository. Confirm that its sharing, backup, encryption, retention, and deletion settings are appropriate for the evidence before collecting it.

Use an explicit output path:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py init \
  --title "Synthetic checkout study" \
  --challenge "Test whether the proposed flow is understandable" \
  --output "/path/to/private-sprints/design-sprint-checkout"
```

A practical private layout is:

```text
<private-root>/
├── workspaces/
│   └── design-sprint-<slug>/       Generated workspace; private by default
├── source-evidence/
│   └── <slug>/
│       ├── transcripts/           Raw session material
│       ├── recordings/            Audio, video, and screen captures
│       └── account-evidence/      Usage, plan, billing, and dashboard sources
├── identities/
│   └── <slug>/participant-map     Names and contact details, separately restricted
└── publication-staging/
    └── <slug>/                         New sanitized exports only
```

Do not initialise a real sprint under this public repository. Its root `.gitignore` covers common workspace and evidence directory names, and generated workspaces contain fallback ignore rules, but ignore rules are not a privacy control: already tracked files, renamed folders, screenshots, and custom paths can still be committed.

Use least-privilege access and apply the shortest practical retention period to raw evidence. Keep participant contact data separate from the working evidence so an anonymised participant ID cannot be casually reversed.

## Safe public fixtures and examples

Public fixtures must be purpose-written, not transformed copies of a real case. Give them unmistakable markers such as:

```json
{
  "fixtureKind": "synthetic",
  "containsRealCustomerData": false,
  "participantId": "SYN-P01",
  "evidenceStatus": "Synthetic rehearsal",
  "observation": "Invented for a parser test; not customer evidence."
}
```

Use reserved domains such as `example.com`, fictional organisations, non-real IDs, invented dates, and deliberately generic scenarios. Synthetic rehearsal never increments a real-session count or supports a customer claim.

When an authorised real observation must be summarized publicly, create a new record rather than editing a copy of the raw transcript. A safe pattern is:

```text
Participant: P01 (identity map remains private)
Date: 2026-01 (coarsened)
Observation: [PARAPHRASED AND REDACTED] The participant did not find the next step.
Provenance: Sanitized extract SR-001 in private source storage
Removed: name, employer, exact date, quotation, product data, and session URL
```

This pattern is not permission to publish. Confirm consent, contractual obligations, applicable law, and re-identification risk first. Prefer paraphrase or aggregate findings when the exact quotation is unnecessary.

## Usage and cost evidence

Treat usage, cost, and capacity claims as evidence, not marketing copy. Every public claim must be either:

1. `sanitized-observed`: traceable to a retained, safely redacted source record; or
2. `hypothetical-unverified`: prominently labelled as hypothetical or unverified wherever the claim appears.

At minimum, retain with the public claim:

- evidence classification;
- measurement date and measured period;
- measurement context;
- relevant sprint/skill version and route when known;
- sanitized source-record reference, or a statement that no observed source exists;
- calculation formula, inputs, result, units, and rounding;
- assumptions, missing data, excluded charges, credits, and tool costs; and
- a public dated source for any external price or plan-limit assumption.

Use distinct measurement contexts:

- `internal-development` for building, debugging, rehearsing, or evaluating the skill; and
- `customer-facing-runtime` for an actual or representative sprint execution.

Never combine those contexts into one runtime or capacity claim. Customer-session and synthesis measurements may be split further, but they must still remain distinguishable from internal development. Subscription counters are not API billing line items unless reproducible evidence establishes that mapping.

The repository's [synthetic usage fixture](../../../tests/fixtures/hypothetical.synthetic.usage-evidence.json) demonstrates the `hypothetical-unverified` record shape, which is declared by the strict [usage-evidence JSON Schema](schemas/usage-evidence-v1.schema.json). It contains invented numbers and cannot substantiate a production claim. An observed record may use `sanitized-observed` only after account IDs, organisation IDs, private plan details, dashboard captures, private URLs, customer context, and credentials have been removed.

## Publication checklist

Complete this checklist against the exact staged diff and every file to be published:

- [ ] The export was created separately from the private workspace; no workspace directory or private repository was copied wholesale.
- [ ] Raw transcripts, recordings, session notes, consent records, recruitment exports, and participant identity/contact maps are absent.
- [ ] Participant names, email addresses, handles, voices, faces, precise dates, unique quotations, job details, and other re-identification clues are absent or explicitly authorised and necessary.
- [ ] Customer, company, product, commercial, technical, analytics, and contractual data is synthetic, public, or safely redacted with permission.
- [ ] Generated artifacts, prototypes, HTML, working memos, filenames, local paths, URLs, and document metadata do not expose private case details.
- [ ] Screenshots and media contain no private tabs, browser chrome, notifications, faces, names, account data, hidden layers, comments, or identifying metadata.
- [ ] Usage dashboards, billing or invoice captures, private plan/allowance details, account and organisation identifiers, subscription IDs, request IDs, credentials, and private console URLs are absent.
- [ ] Every usage or cost claim is linked to a safely redacted source record or labelled `hypothetical-unverified` at the point of use.
- [ ] Usage records include the measurement date, classification, context, calculation, units, rounding, assumptions, omissions, and dated price sources.
- [ ] Internal-development and customer-facing runtime measurements are reported separately.
- [ ] Public test fixtures are purpose-written, named and marked as synthetic, and contain no transformed real customer or case-study data.
- [ ] Consent, contract, licence, retention, and deletion obligations permit the intended publication.
- [ ] `python3 scripts/check_publication.py` passes from the public repository root.
- [ ] A human reviewed `git diff --cached --check`, the complete staged diff, and newly added binary files.

The automated check catches only high-signal mistakes. It cannot determine consent, recognize every person or company, inspect external private storage, or prove that a sophisticated redaction is safe. Human review remains required.
