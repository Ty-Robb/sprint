# Support Policy

## Supported releases

| Release line | Status | Runtime and schema support |
|---|---|---|
| `1.x` | Supported after `v1.0.0` is published | Python 3.10-3.14 and the schema families in `release-contract.json` |
| `main` | Development only | May contain unreleased changes; use a release tag for reproducible work |
| Untagged pre-1.0 commits | Unsupported | Migrate with a supported 1.x release where its schema is listed as migratable |

The current machine-readable support matrix is
[`release-contract.json`](skills/run-design-sprint/references/release-contract.json).
Release compatibility and deprecation rules are in the
[release and compatibility contract](skills/run-design-sprint/references/release-compatibility.md).

## Runtime support

The installed skill supports dependency-free Python 3.10 through 3.14 on
Ubuntu 24.04, macOS 14 or newer, and Windows Server 2022 or newer. CI runs the
full suite on every supported Python minor on Ubuntu and release smoke coverage
on each supported OS family. Other Unix-like systems and Python pre-releases
are best effort.

The verified installation path uses `skills@1.5.22` with Node.js 22 or 24. Node
and network access are not required after installation unless a user separately
chooses a workflow action that needs them.

## Getting help

Use a [GitHub issue](https://github.com/Ty-Robb/sprint/issues/new) for a
reproducible bug, documentation gap, or compatibility question. Include the
skill version, Python version, operating system, command, expected result, and a
minimal synthetic reproduction. Never attach a private sprint workspace,
customer evidence, transcripts, credentials, account identifiers, or private
usage data.

Support is provided on a best-effort basis with no guaranteed response or fix
time. Security concerns must use the private process in [SECURITY.md](SECURITY.md),
not a public issue.
