# Contributing

Contributions should preserve the skill's evidence boundaries, deterministic
runtime behavior, schema compatibility, and installability from a clean public
source.

## Development setup

Use a branch and worktree based on the latest `origin/main`. The runtime and
tests need only a supported Python version (3.10-3.14). Node.js 22 or 24 is
needed for the same installer, JSON Schema compiler, and HTML validator used by
CI.

From a clean checkout, run:

```bash
python3 -m py_compile skills/run-design-sprint/scripts/*.py scripts/*.py
python3 scripts/check_publication.py
python3 -m unittest discover -s tests -v
```

Run the local clean-install fixture before opening a pull request:

```bash
python3 scripts/release_smoke_test.py --source "$(pwd)"
```

After pushing, the equivalent public-ref check is:

```bash
python3 scripts/release_smoke_test.py \
  --source "https://github.com/Ty-Robb/sprint/archive/<40-character-commit-sha>.tar.gz" \
  --require-public-source
```

CI also compiles every published schema and validates generated HTML.

The generated-site browser checks use pinned development-only dependencies;
they do not change the skill's dependency-free Python runtime. Install Chromium
once, then run the checks with:

```bash
npm ci
npx playwright install chromium
npm run test:browser
```

The browser suite builds a complete synthetic site in a temporary directory
and checks navigation, narrow-screen overflow, keyboard behavior, and automated
accessibility rules across every generated page.

## Change requirements

- Keep the Agent Skills frontmatter valid and keep its version aligned with
  `release-contract.json`, the runtime `--version`, changelog, and release notes.
- Treat documented commands and persisted JSON as public contracts. Do not
  change a `schemaVersion` field without adding the matching schema and loader
  or protected migration behavior.
- For a schema or workflow change, update runtime constants, schemas,
  `json-schemas.md`, `release-contract.json`, compatibility documentation,
  changelog/release notes, fixtures, and positive and negative tests together.
- Preserve deterministic serialization/rendering and dependency-free runtime
  operation. Explain any proposed dependency before adding it.
- Keep generated sprint workspaces and real customer/company evidence outside
  this repository. Public fixtures must be purpose-written, use `.synthetic.`
  in data filenames, declare `fixtureKind: synthetic` and
  `containsRealCustomerData: false`, and pass the publication checker.
- Add tests that fail before the change and pass after it. Keep error messages
  actionable and field-specific.

## Pull requests

Describe the user-visible behavior, compatibility impact, verification run,
and any migration or deprecation. Link the issue with `Closes #<number>` when
the pull request fully resolves it. Keep unrelated changes separate and do not
include private evidence in commits, logs, screenshots, or PR discussion.

Only maintainers create tags and GitHub releases. A contributor should prepare
release notes and checks when requested, but must not tag or publish without
explicit human approval. The maintainer procedure is in
[`docs/releasing.md`](docs/releasing.md).
