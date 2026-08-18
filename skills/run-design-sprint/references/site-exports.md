# Site Exports and Self-Hosting

Use this process to prepare a portable sprint site or private archive. The
command never uploads, deploys, publishes, connects a hosting account, or treats
export approval as publication approval.

## Choose the output boundary

`private-archive` is an access-controlled preservation bundle. Its approval may
independently include canonical artifact/state data, working material, customer
testing records, and prototype versions. The generated site and its manifest
remain private.

`shareable-site` is a newly rendered allowlist, not a copy of the workspace. It
contains only approved complete artifacts, approved privacy-minimized session
pages, the shared local stylesheet, and optionally the current frozen prototype
artifact plus its contextual wrapper. It never contains `sprint-state.json`,
`assignment-manifest.json`, `artifact-data/`, `working/`,
`customer-testing/`, prototype context, build packets, or
`tested-version.json`.

Both outputs reject secret-like values, non-example email addresses, phone
details, account/customer identifiers, prohibited evidence/contact paths,
absolute local filesystem references, symlinks, remote executable assets,
broken links, stale page digests, and a changed tested prototype.

## Record explicit human approval

Create an approval JSON file outside the private workspace. Use exact artifact
and session IDs from the generated `site-manifest.json`. This shareable example
is synthetic; replace the allowlists and reviewer fields only after reviewing
the exact source material:

```json
{
  "schemaVersion": "1.0",
  "recordType": "sprint-export-approval",
  "kind": "shareable-site",
  "approvedBy": "Human publication reviewer",
  "approvedAt": "2026-08-17T12:00:00Z",
  "artifactIds": [
    "01-sprint-brief",
    "07-decision",
    "08-experiment",
    "09-storyboard",
    "10-prototype-brief",
    "10-test-plan",
    "11-customer-evidence",
    "12-synthesis",
    "13-outcome"
  ],
  "sessionIds": ["S01"],
  "includePrototype": true,
  "includeCanonicalData": false,
  "includeWorkingMaterial": false,
  "includeCustomerTesting": false,
  "redactionReview": {
    "completed": true,
    "secretsChecked": true,
    "contactDetailsChecked": true,
    "rawEvidenceChecked": true,
    "personalInformationChecked": true,
    "customerConfidentialChecked": true,
    "assetLicencesChecked": true,
    "consentAndRightsChecked": true,
    "notes": "Reviewed the exact allowlist and approved only the sanitized site preparation."
  }
}
```

For `private-archive`, set `kind` accordingly. The artifact and session arrays
are shareable-site allowlists, so use empty arrays for a private archive; its
manifest catalogs the full generated private site. The four `include...`
booleans control which private record categories are copied. Keep all required
redaction-review fields; an archive may still leak credentials or
contact/source evidence if it is handled carelessly.

## Prepare and verify

Validate the source, then prepare a new directory outside it:

```bash
python3 <skill-dir>/scripts/sprint_workspace.py validate \
  --workspace <private-sprint-directory>

python3 <skill-dir>/scripts/sprint_workspace.py export \
  --workspace <private-sprint-directory> \
  --approval <approval.json> \
  --output <new-export-directory> \
  --zip
```

The output path and optional sibling ZIP must not already exist. Preparation is
atomic: a failed redaction, version, schema, or crawl check leaves no partial
output. The ZIP uses the approval timestamp and portable permissions so the same
approved directory produces stable metadata.

Inspect the output's `site-manifest.json`. It records the export kind, reviewer,
approval digest, `published: false`, site version digest, every page and
relationship, page visibility, content/render digests, prototype version
context, and every packaged local asset. `humanPublicationRequired` remains
`true`.

Open at least one deep artifact, session page, prototype wrapper, and outcome
page directly from the filesystem. Then serve the parent directory locally and
repeat from a nested path:

```bash
python3 -m http.server 8000 --directory <parent-of-export>
```

For an output named `sprint-results`, test both
`http://localhost:8000/sprint-results/` and a deep URL such as
`http://localhost:8000/sprint-results/artifacts/13-outcome.html`. Home,
previous, next, related evidence, decision, prototype, outcome, manifest, and
local asset links must resolve without rewriting.

## Hand off to static hosting

The prepared shareable directory is ordinary static HTML/CSS and local assets.
A human may later choose GitHub Pages, Cloudflare Pages, Netlify, Vercel, an
object store, or a self-hosted static server and upload that directory using the
provider's documented controls. No framework, build command, CDN dependency,
server runtime, analytics, external font, or automatic deployment is required.

Before any upload, repeat the
[publication checklist](privacy-and-publication.md#publication-checklist)
against the exact prepared directory or ZIP and verify the intended host's
access, retention, preview, indexing, domain, and deletion settings. A
successful `export` means the package passed deterministic preparation checks;
it does not establish consent, legal authority, safety from re-identification,
or permission to publish.
