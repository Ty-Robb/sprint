# Usage, Cost, and Capacity Evidence

Use this process when measuring a sprint, publishing a usage or cost statement,
or preparing a capacity scenario. Usage claims follow the same provenance and
privacy rules as customer findings.

## Evidence boundary

Keep raw response objects, request identifiers, account and organisation
identifiers, subscription details, invoice exports, dashboard captures,
prompts, outputs, tool payloads, and private workspace paths in
access-controlled source storage. They do not belong in this public repository
or a publication record.

A public record is a purpose-built redacted export. It contains only counts,
safe model and phase labels, an opaque source reference, the redactions applied,
coverage declarations, and exclusions. Use `sanitized-observed` only when the
retained private source really supports the exported values. Use
`hypothetical-unverified` for plans, invented examples, or records without
observed source evidence.

The strict contracts are:

- [`usage-record-v1.schema.json`](schemas/usage-record-v1.schema.json) for each
  redacted measurement;
- [`pricing-snapshot-v1.schema.json`](schemas/pricing-snapshot-v1.schema.json)
  for the dated rates used by a calculation; and
- [`usage-report-v1.schema.json`](schemas/usage-report-v1.schema.json) for the
  deterministic generated report.

All three formats start at schema `1.0`. They have no legacy interpretation or
migration path. Unknown versions fail instead of being read loosely.

## Measurement scopes

Create separate records for these scopes:

| Scope | Meaning |
|---|---|
| `internal-development` | Building, debugging, evaluating, or rehearsing the skill. It must use `internal-rehearsal` and is never part of customer capacity. |
| `customer-runtime` | Customer-facing orchestration outside a participant session or synthesis. |
| `customer-session` | One redacted individual-session measurement. It requires a safe session label. |
| `synthesis` | The bounded cross-session synthesis run. |

The generated `customerOnly` figure combines `customer-runtime`,
`customer-session`, and `synthesis` once. Individual sessions and synthesis are
also displayed as non-additive subgroups; do not add them to `customerOnly`
again. Internal development remains disjoint.

At least one real internal-flow record and one real customer-only execution are
required before making a production capacity claim. The repository's synthetic
fixtures exercise those shapes but are not measurements and do not satisfy that
evidence requirement.

## Record what the runtime actually exposes

For every observation, record its granularity, phase, model, request count,
context tier, token fields, tool quantities, and source. Response APIs commonly
report reasoning tokens as detail within output tokens. The calculator therefore
checks:

```text
totalTokens = inputTokens + outputTokens
reasoningTokens <= outputTokens
```

It never adds reasoning tokens to output or total a second time.

Input categories are priced without overlap:

```text
uncachedInputTokens = inputTokens - cachedInputTokens - cacheWriteInputTokens
token equivalent =
  uncachedInputTokens * input rate
  + cachedInputTokens * cached-input rate
  + cacheWriteInputTokens * cache-write rate
  + outputTokens * output rate
```

Each rate is divided by its pricing unit, normally one million tokens. Tool
components use their own dated rate and unit. Calculations use decimal
arithmetic with no intermediate rounding, retain six decimal places with
`ROUND_HALF_UP`, and show a two-decimal `ROUND_HALF_UP` display amount.

Declare coverage explicitly for request-level metadata, long-context pricing,
cache writes, tools, credits, and model mix. `unavailable` never means zero. A
missing model, token category, or context tier makes that component unpriceable;
the generator moves it to `excludedCharges`, emits a warning, and marks the
base-rate equivalent incomplete. Known aggregate token counts remain visible as
partial observations.

## Charges, equivalents, and billing modes

The calculator produces a base-rate equivalent, not an actual charge. It keeps
four concepts separate:

1. observations: measured or synthetic usage fields without a price claim;
2. base-rate equivalents: token and included-tool quantities multiplied by a
   dated API price snapshot;
3. excluded charges: missing or deliberately out-of-scope long-context,
   cache-write, tool, credit, subscription, and invoice-reconciliation items;
4. hypothetical scenarios: labelled multipliers over the customer-only
   base-rate equivalent.

Credits never reduce a base-rate equivalent. Reconcile financial claims against
the provider's cost or invoice source separately. API usage aggregates and cost
line items can differ, so a usage-derived equivalent must not be relabelled as
an invoice amount.

Set billing mode to `api`, `subscription`, `mixed`, or `unknown`. A subscription
counter may be recorded with its native unit, but it cannot be mapped one-to-one
to API tokens, tool calls, or line items without reproducible evidence. Do not
infer an API bill from it. Subscription guidance is a dated planning baseline,
not proof of a minimum plan. This repository deliberately contains no permanent
"minimum plan" claim.

## Dated pricing snapshots

Never fetch live prices during report generation. Commit a new immutable pricing
snapshot, including public URLs and access dates, whenever a report needs a new
rate date. Re-running an old report then uses the same inputs even after public
prices change. Re-verify official sources before calling any snapshot current.

The synthetic snapshot in
[`tests/fixtures/usage/official-2026-08-17.synthetic.pricing-snapshot.json`](../../../tests/fixtures/usage/official-2026-08-17.synthetic.pricing-snapshot.json)
was checked on 2026-08-17 against the official
[OpenAI API pricing page](https://developers.openai.com/api/docs/pricing). It
records the displayed standard short- and long-context GPT-5.6 Luna and Terra
token rates, the separate cache-write rates, and the displayed web-search and
file-search call rates. The fixture also links the official
[API usage-field reference](https://developers.openai.com/api/reference/resources/responses),
whose usage shape separates cached and cache-write input details and reports
reasoning as output-token detail. The official
[organisation usage and cost reference](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage)
is the reconciliation source for API financial claims.

Those values are a historical snapshot only. They are not a claim about another
provider, service tier, region, subscription, current price, tax, credit, or
future rate.

## Reproduce the synthetic report

From the repository root, run:

```bash
python3 skills/run-design-sprint/scripts/usage_report.py \
  --record tests/fixtures/usage/internal-development.synthetic.usage-record.json \
  --record tests/fixtures/usage/customer-runtime.synthetic.usage-record.json \
  --record tests/fixtures/usage/session-s01.synthetic.usage-record.json \
  --record tests/fixtures/usage/session-s02-missing.synthetic.usage-record.json \
  --record tests/fixtures/usage/synthesis.synthetic.usage-record.json \
  --pricing tests/fixtures/usage/official-2026-08-17.synthetic.pricing-snapshot.json \
  --scenario "3x planning scenario=3" \
  --output /tmp/synthetic-usage-report.json
```

The output is canonical sorted JSON and contains no generation timestamp, so
identical inputs produce identical bytes. The synthetic customer-only total is
`USD 0.229710`, displayed as `USD 0.23`; the 3x planning scenario is
`USD 0.689130`, displayed as `USD 0.69`. One synthetic session intentionally
lacks request-level model, cache-write, tool, credit, reasoning, and context-tier
data, so both figures are labelled hypothetical and the base-rate/scenario basis
is marked incomplete.

Scenario arguments use `LABEL=MULTIPLIER`. Labels must contain `planning
scenario`; labels claiming a minimum or maximum are rejected. A scenario remains
hypothetical even when its basis is an observed base-rate equivalent.

Before publication, run the report, inspect every warning and exclusion, then
complete the [publication checklist](privacy-and-publication.md#publication-checklist)
and run `python3 scripts/check_publication.py`.
