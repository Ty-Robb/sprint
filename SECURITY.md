# Security Policy

## Supported versions

The latest published `1.x` release receives security fixes. `main`, untagged
commits, and older release lines are not security-supported distributions.
Runtime and schema details are recorded in the
[release contract](skills/run-design-sprint/references/release-contract.json).

## Report a vulnerability privately

Use GitHub's private vulnerability-reporting form:

https://github.com/Ty-Robb/sprint/security/advisories/new

Do not open a public issue or discussion for a suspected vulnerability. Do not
include real sprint workspaces, customer evidence, transcripts, credentials,
account identifiers, or private usage records. Create the smallest synthetic
reproduction that demonstrates the issue.

Include the affected skill version or commit, supported Python/OS environment,
impact, reproduction steps, and any known mitigation. The maintainer will
acknowledge a complete report on a best-effort basis, coordinate validation and
remediation privately, and agree on disclosure and credit before publication.

## Scope

Security reports may cover unsafe file handling, path traversal, untrusted HTML
or URL handling, privacy-boundary failures, secret/customer-data exposure,
schema-validation bypasses, installer/discovery integrity, or other behavior
that could compromise confidentiality, integrity, or availability.

Prompt boundaries and specialist role instructions are behavioral controls,
not a security sandbox. Reports that only demonstrate an agent ignoring text
instructions without crossing a code, file, data, or trust boundary may be
handled as product-safety or reliability bugs instead.
