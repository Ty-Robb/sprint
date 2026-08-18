# Maintainer Release Procedure

This repository prepares release material in pull requests but does not create
a tag or GitHub release until a human explicitly approves that irreversible
publication step.

## Release candidate checks

For `v1.0.0`, confirm that the release PR is merged and every required check on
`main` is green. Then use a clean checkout:

```bash
git clone https://github.com/Ty-Robb/sprint.git sprint-release
cd sprint-release
git fetch --prune origin
git checkout main
git pull --ff-only origin main
test -z "$(git status --porcelain)"
```

If `CHANGELOG.md` still says `## [1.0.0] - Unreleased`, replace only that
heading with the actual UTC date in `YYYY-MM-DD` form, open and merge a small
release-finalization PR, then repeat the clean-checkout commands above.

Run all local release checks:

```bash
python3 -m py_compile skills/run-design-sprint/scripts/*.py scripts/*.py
python3 scripts/check_publication.py
python3 -m unittest discover -s tests -v
release_sha="$(git rev-parse HEAD)"
printf 'VERIFIED_RELEASE_SHA=%s\n' "${release_sha}"
python3 scripts/release_smoke_test.py \
  --source "https://github.com/Ty-Robb/sprint/archive/${release_sha}.tar.gz" \
  --require-public-source
```

The immutable commit archive is intentional: `skills@1.5.22` accepts branch or
tag names after `#`, but it cannot clone a raw commit SHA as a ref. The archive
keeps pre-tag verification pinned to the exact candidate commit.

Confirm `release_sha` is the exact green `main` commit and that it still
contains skill version `1.0.0`, tag contract `v1.0.0`, and the final release
notes:

```bash
python3 skills/run-design-sprint/scripts/sprint_workspace.py --version
git grep '"releaseTag": "v1.0.0"' -- \
  skills/run-design-sprint/references/release-contract.json
test -f docs/releases/v1.0.0.md
test "$(gh api repos/Ty-Robb/sprint/private-vulnerability-reporting --jq .enabled)" = "true"
gh run list --repo Ty-Robb/sprint --branch main --limit 5
```

## Human approval boundary

Stop here and obtain explicit human approval to publish `v1.0.0`. The following
commands create the public tag and release; do not run them as part of a
preparation PR.

After approval, replace `<verified-release-sha>` with the exact value printed by
the candidate check. From the verified clean checkout:

```bash
release_sha="<verified-release-sha>"
test "$(git rev-parse HEAD)" = "${release_sha}"
test -z "$(git status --porcelain)"
test -z "$(git tag --list v1.0.0)"
test -z "$(git ls-remote --tags origin refs/tags/v1.0.0)"
! gh release view v1.0.0 --repo Ty-Robb/sprint >/dev/null 2>&1
git tag -a v1.0.0 "${release_sha}" -m "run-design-sprint v1.0.0"
git push origin refs/tags/v1.0.0
gh release create v1.0.0 \
  --repo Ty-Robb/sprint \
  --verify-tag \
  --title "run-design-sprint v1.0.0" \
  --notes-file docs/releases/v1.0.0.md
```

Verify the published tag through the public installer rather than the checkout:

```bash
python3 scripts/release_smoke_test.py \
  --source "https://github.com/Ty-Robb/sprint.git#v1.0.0" \
  --require-public-source
gh release view v1.0.0 --repo Ty-Robb/sprint --json tagName,targetCommitish,url
```

If verification fails after the tag is public, do not move or overwrite the
tag. Document the failure, fix forward with the appropriate patch release, and
explain the impact in the changelog and release notes.
