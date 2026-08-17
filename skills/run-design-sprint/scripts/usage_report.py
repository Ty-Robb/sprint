#!/usr/bin/env python3
"""Build a deterministic usage and base-rate-equivalent report.

The calculator consumes deliberately redacted usage records and a dated pricing
snapshot.  It never presents calculated API base rates as invoices or maps a
subscription allowance to API line items.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Sequence

from schema_validation import SchemaValidator, strict_json_loads


SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = SKILL_DIR / "references" / "schemas"
USAGE_RECORD_SCHEMA = SCHEMAS_DIR / "usage-record-v1.schema.json"
PRICING_SNAPSHOT_SCHEMA = SCHEMAS_DIR / "pricing-snapshot-v1.schema.json"
USAGE_REPORT_SCHEMA = SCHEMAS_DIR / "usage-report-v1.schema.json"
REPORT_VERSION = "1.0"
CALCULATION_VERSION = "1.0"
MILLION = Decimal("1000000")
EXACT_QUANTUM = Decimal("0.000001")
DISPLAY_QUANTUM = Decimal("0.01")
SCHEMA_VALIDATOR = SchemaValidator()


class UsageReportError(ValueError):
    """A usage record, pricing snapshot, or scenario cannot be calculated."""


@dataclass(frozen=True)
class CostComponent:
    record_id: str
    observation_id: str
    component: str
    amount: Decimal

    @property
    def key(self) -> str:
        return f"{self.record_id}/{self.observation_id}/{self.component}"


@dataclass(frozen=True)
class Exclusion:
    record_id: str
    component: str
    category: str
    description: str
    affects_base_rate: bool

    def report_value(self) -> dict[str, str]:
        return {
            "recordId": self.record_id,
            "component": self.component,
            "category": self.category,
            "description": self.description,
        }


def load_json(path: Path) -> Any:
    try:
        return strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise UsageReportError(f"{path}: invalid JSON: {error}") from error


def schema_validate(document: Any, schema: Path, label: str) -> None:
    issues = SCHEMA_VALIDATOR.validate(document, schema)
    if issues:
        raise UsageReportError(
            f"{label} does not match {schema.name}:\n"
            + "\n".join(f"- {issue}" for issue in issues)
        )


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def cross_record_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    record_id = record["recordId"]
    measurement = record["measurement"]
    if parse_timestamp(measurement["periodStart"]) > parse_timestamp(
        measurement["periodEnd"]
    ):
        errors.append("$.measurement.periodStart must not be after periodEnd")

    context = record["context"]
    scope = context["scope"]
    expected_kind = (
        "internal-rehearsal" if scope == "internal-development" else "customer-facing"
    )
    if context["runKind"] != expected_kind:
        errors.append(
            f"$.context.runKind must be {expected_kind!r} for scope {scope!r}"
        )
    if scope == "customer-session" and context["sessionLabel"] is None:
        errors.append("$.context.sessionLabel is required for a customer-session record")
    if scope != "customer-session" and context["sessionLabel"] is not None:
        errors.append("$.context.sessionLabel is only allowed for customer-session records")

    billing = context["billing"]
    if billing["mode"] == "api":
        if billing["subscriptionCounterMapping"] != "not-applicable-api":
            errors.append(
                "$.context.billing.subscriptionCounterMapping must be "
                "'not-applicable-api' for API records"
            )
        if billing["subscriptionCounters"]:
            errors.append("$.context.billing.subscriptionCounters must be empty for API records")
    elif billing["mode"] in {"subscription", "mixed"}:
        if billing["subscriptionCounterMapping"] != "not-one-to-one":
            errors.append(
                "$.context.billing.subscriptionCounterMapping must be 'not-one-to-one' "
                "for subscription or mixed records"
            )

    coverage = record["coverage"]
    if (
        record["evidenceClassification"] == "sanitized-observed"
        and record.get("fixtureKind") == "synthetic"
    ):
        errors.append(
            "$.fixtureKind synthetic cannot be combined with sanitized-observed evidence"
        )
    if coverage["requestLevel"] == "complete" and coverage[
        "missingRequestLevelReason"
    ].strip():
        errors.append(
            "$.coverage.missingRequestLevelReason must be empty when requestLevel is complete"
        )
    if coverage["requestLevel"] != "complete" and not coverage[
        "missingRequestLevelReason"
    ].strip():
        errors.append(
            "$.coverage.missingRequestLevelReason is required when request-level data is incomplete"
        )

    observations = record["observations"]
    observation_ids = [item["observationId"] for item in observations]
    if len(observation_ids) != len(set(observation_ids)):
        errors.append("$.observations contains duplicate observationId values")
    if coverage["requestLevel"] == "complete" and any(
        item["granularity"] != "request" for item in observations
    ):
        errors.append(
            "$.observations must all use request granularity when requestLevel is complete"
        )

    for index, observation in enumerate(observations):
        prefix = f"$.observations[{index}]"
        if observation["granularity"] == "request" and observation["requestCount"] != 1:
            errors.append(f"{prefix}.requestCount must equal 1 at request granularity")
        usage = observation["usage"]
        input_tokens = usage["inputTokens"]
        cached_tokens = usage["cachedInputTokens"]
        write_tokens = usage["cacheWriteInputTokens"]
        output_tokens = usage["outputTokens"]
        reasoning_tokens = usage["reasoningTokens"]
        total_tokens = usage["totalTokens"]
        if input_tokens is not None:
            if cached_tokens is not None and cached_tokens > input_tokens:
                errors.append(f"{prefix}.usage.cachedInputTokens exceeds inputTokens")
            if write_tokens is not None and write_tokens > input_tokens:
                errors.append(f"{prefix}.usage.cacheWriteInputTokens exceeds inputTokens")
            if cached_tokens is not None and write_tokens is not None:
                if cached_tokens + write_tokens > input_tokens:
                    errors.append(
                        f"{prefix}.usage cached and cache-write tokens exceed inputTokens"
                    )
        if (
            reasoning_tokens is not None
            and output_tokens is not None
            and reasoning_tokens > output_tokens
        ):
            errors.append(f"{prefix}.usage.reasoningTokens exceeds outputTokens")
        if None not in (input_tokens, output_tokens, total_tokens):
            if input_tokens + output_tokens != total_tokens:
                errors.append(
                    f"{prefix}.usage.totalTokens must equal inputTokens plus outputTokens; "
                    "reasoningTokens is already included in outputTokens"
                )
        for tool_index, tool in enumerate(observation["tools"]):
            tool_prefix = f"{prefix}.tools[{tool_index}]"
            if tool["chargeTreatment"] == "included-in-base-rate-equivalent":
                if tool["pricingKey"] is None:
                    errors.append(f"{tool_prefix}.pricingKey is required when included")
                if tool["excludedReason"].strip():
                    errors.append(f"{tool_prefix}.excludedReason must be empty when included")
            elif not tool["excludedReason"].strip():
                errors.append(
                    f"{tool_prefix}.excludedReason is required when a tool charge is not included"
                )

    if coverage["cacheWrites"] == "known-zero" and any(
        item["usage"]["cacheWriteInputTokens"] != 0 for item in observations
    ):
        errors.append(
            "$.coverage.cacheWrites is known-zero but an observation is null or non-zero"
        )
    if coverage["cacheWrites"] == "recorded" and any(
        item["usage"]["cacheWriteInputTokens"] is None for item in observations
    ):
        errors.append(
            "$.coverage.cacheWrites is recorded but an observation is missing cache-write tokens"
        )
    if coverage["tools"] == "known-zero" and any(
        item["tools"] for item in observations
    ):
        errors.append("$.coverage.tools is known-zero but tool usage is present")
    if coverage["tools"] == "recorded" and not any(
        item["tools"] for item in observations
    ):
        errors.append("$.coverage.tools is recorded but no tool usage is present")
    if coverage["credits"] == "known-zero" and record["credits"]:
        errors.append("$.coverage.credits is known-zero but credits are present")
    if coverage["credits"] == "recorded" and not record["credits"]:
        errors.append("$.coverage.credits is recorded but credits is empty")
    if coverage["longContextPricing"] == "known-zero" and any(
        item["contextTier"] != "short" for item in observations
    ):
        errors.append(
            "$.coverage.longContextPricing is known-zero but a context tier is not short"
        )
    if coverage["longContextPricing"] == "recorded" and any(
        item["contextTier"] == "unknown" for item in observations
    ):
        errors.append(
            "$.coverage.longContextPricing is recorded but a context tier is unknown"
        )
    non_null_models = {item["model"] for item in observations if item["model"]}
    if coverage["modelMix"] == "single-model" and (
        len(non_null_models) != 1 or any(item["model"] is None for item in observations)
    ):
        errors.append("$.coverage.modelMix is single-model but model data is incomplete or mixed")
    if coverage["modelMix"] == "recorded" and any(
        item["model"] is None for item in observations
    ):
        errors.append("$.coverage.modelMix is recorded but an observation model is null")

    declared_categories = {item["category"] for item in record["excludedCharges"]}
    coverage_categories = {
        "cacheWrites": "cache-write",
        "longContextPricing": "long-context",
        "tools": "tool",
        "credits": "credit",
    }
    for coverage_key, category in coverage_categories.items():
        if coverage[coverage_key] == "unavailable" and category not in declared_categories:
            errors.append(
                f"$.excludedCharges must declare category {category!r} when "
                f"$.coverage.{coverage_key} is unavailable"
            )
    if billing["mode"] in {"subscription", "mixed"} and "subscription" not in declared_categories:
        errors.append(
            "$.excludedCharges must declare subscription mapping limits for subscription or mixed billing"
        )
    for index, exclusion in enumerate(record["excludedCharges"]):
        observation_id = exclusion["observationId"]
        if observation_id is not None and observation_id not in observation_ids:
            errors.append(
                f"$.excludedCharges[{index}].observationId does not name an observation in {record_id}"
            )
    return errors


def validate_usage_record(record: Any, label: str = "usage record") -> dict[str, Any]:
    schema_validate(record, USAGE_RECORD_SCHEMA, label)
    errors = cross_record_errors(record)
    if errors:
        raise UsageReportError(
            f"{label} violates usage-record reconciliation rules:\n"
            + "\n".join(f"- {error}" for error in errors)
        )
    return record


def validate_pricing_snapshot(snapshot: Any, label: str = "pricing snapshot") -> dict[str, Any]:
    schema_validate(snapshot, PRICING_SNAPSHOT_SCHEMA, label)
    errors: list[str] = []
    models = [item["model"] for item in snapshot["models"]]
    if len(models) != len(set(models)):
        errors.append("$.models contains duplicate model entries")
    tools = [item["pricingKey"] for item in snapshot["tools"]]
    if len(tools) != len(set(tools)):
        errors.append("$.tools contains duplicate pricingKey entries")
    for index, model in enumerate(snapshot["models"]):
        has_long_context = model["longContext"] is not None
        threshold = model["longContextThresholdInputTokens"]
        application = model["longContextApplication"]
        if has_long_context and (threshold is None or application == "not-applicable"):
            errors.append(
                f"$.models[{index}] long-context rates require a threshold and application"
            )
        if not has_long_context and (threshold is not None or application != "not-applicable"):
            errors.append(
                f"$.models[{index}] without long-context rates must mark them not-applicable"
            )
    if errors:
        raise UsageReportError(
            f"{label} violates pricing-snapshot reconciliation rules:\n"
            + "\n".join(f"- {error}" for error in errors)
        )
    return snapshot


def validate_context_tiers(
    records: Sequence[dict[str, Any]], snapshot: dict[str, Any]
) -> None:
    """Reconcile request-level tiers with deterministic pricing thresholds."""

    model_prices = {item["model"]: item for item in snapshot["models"]}
    errors: list[str] = []
    for record in records:
        for index, observation in enumerate(record["observations"]):
            model_price = model_prices.get(observation["model"])
            input_tokens = observation["usage"]["inputTokens"]
            if (
                model_price is None
                or observation["granularity"] != "request"
                or input_tokens is None
                or model_price["longContextApplication"] != "full-request"
            ):
                continue
            threshold = model_price["longContextThresholdInputTokens"]
            assert threshold is not None
            expected = "long" if input_tokens > threshold else "short"
            if observation["contextTier"] != expected:
                errors.append(
                    f"{record['recordId']}: $.observations[{index}].contextTier must be "
                    f"{expected!r} for {input_tokens} input tokens using {observation['model']!r}; "
                    f"the dated threshold is {threshold}"
                )
    if errors:
        raise UsageReportError(
            "Usage records conflict with the dated long-context pricing rules:\n"
            + "\n".join(f"- {error}" for error in errors)
        )


def decimal_value(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise UsageReportError(f"Invalid decimal value {value!r}") from error
    if not parsed.is_finite():
        raise UsageReportError(f"Decimal value must be finite: {value!r}")
    return parsed


def exact_money(value: Decimal) -> str:
    return format(value.quantize(EXACT_QUANTUM, rounding=ROUND_HALF_UP), ".6f")


def display_money(value: Decimal) -> str:
    return format(value.quantize(DISPLAY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")


def normalized_decimal(value: Decimal) -> str:
    output = format(value, "f")
    if "." in output:
        output = output.rstrip("0").rstrip(".")
    return output or "0"


def classification_label(records: Sequence[dict[str, Any]], suffix: str) -> str:
    classifications = {item["evidenceClassification"] for item in records}
    if not records:
        return f"No {suffix.lower()} records"
    if classifications == {"sanitized-observed"}:
        return f"Observed {suffix}"
    if classifications == {"hypothetical-unverified"}:
        return f"Hypothetical/unverified {suffix}"
    return f"Mixed-classification {suffix}"


TOKEN_FIELDS = (
    "inputTokens",
    "cachedInputTokens",
    "cacheWriteInputTokens",
    "outputTokens",
    "reasoningTokens",
    "totalTokens",
)


def usage_summary(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    totals = {field: 0 for field in TOKEN_FIELDS}
    token_complete = bool(records)
    request_complete = bool(records)
    request_count = 0
    observation_ids: list[str] = []
    models: set[str] = set()
    classifications: set[str] = set()
    for record in records:
        classifications.add(record["evidenceClassification"])
        for observation in record["observations"]:
            observation_ids.append(
                f"{record['recordId']}/{observation['observationId']}"
            )
            if observation["model"] is None:
                models.add("unknown")
            else:
                models.add(observation["model"])
            if observation["requestCount"] is None:
                request_complete = False
            else:
                request_count += observation["requestCount"]
            for field in TOKEN_FIELDS:
                value = observation["usage"][field]
                if value is None:
                    token_complete = False
                else:
                    totals[field] += value
    totals["reasoningIncludedInOutputTokens"] = True
    return {
        "label": classification_label(records, "usage"),
        "recordIds": sorted(record["recordId"] for record in records),
        "observationIds": sorted(observation_ids),
        "evidenceClassifications": sorted(classifications),
        "requestCountObserved": request_count,
        "requestCountComplete": request_complete,
        "tokenTotals": totals,
        "tokenTotalsComplete": token_complete,
        "models": sorted(models),
    }


def declared_exclusions(record: dict[str, Any]) -> list[Exclusion]:
    output: list[Exclusion] = []
    base_rate_neutral = {"credit", "subscription", "api-reconciliation"}
    for item in record["excludedCharges"]:
        observation = item["observationId"] or "record"
        output.append(
            Exclusion(
                record_id=record["recordId"],
                component=observation,
                category=item["category"],
                description=item["description"],
                affects_base_rate=item["category"] not in base_rate_neutral,
            )
        )
    for index, credit in enumerate(record["credits"], start=1):
        amount = (
            "unknown amount"
            if credit["amountUsd"] is None
            else f"USD {credit['amountUsd']}"
        )
        output.append(
            Exclusion(
                record_id=record["recordId"],
                component=f"credit-{index}",
                category="credit",
                description=(
                    f"Credit ({amount}) excluded from the base-rate equivalent: "
                    f"{credit['reason']}"
                ),
                affects_base_rate=False,
            )
        )
    return output


def calculate_components(
    records: Sequence[dict[str, Any]], snapshot: dict[str, Any]
) -> tuple[list[CostComponent], list[Exclusion]]:
    model_prices = {item["model"]: item for item in snapshot["models"]}
    tool_prices = {item["pricingKey"]: item for item in snapshot["tools"]}
    components: list[CostComponent] = []
    exclusions: list[Exclusion] = []
    for record in records:
        exclusions.extend(declared_exclusions(record))
        record_id = record["recordId"]
        for observation in record["observations"]:
            observation_id = observation["observationId"]
            usage = observation["usage"]
            token_component = f"{observation_id}/tokens"
            required = (
                usage["inputTokens"],
                usage["cachedInputTokens"],
                usage["cacheWriteInputTokens"],
                usage["outputTokens"],
            )
            token_exclusion: tuple[str, str] | None = None
            if any(value is None for value in required):
                token_exclusion = (
                    "missing-token-data",
                    "Input, cached-input, cache-write, or output tokens are unavailable.",
                )
            elif observation["model"] is None:
                token_exclusion = (
                    "model-mix",
                    "The model is unavailable, so aggregate tokens cannot be assigned a rate.",
                )
            elif observation["model"] not in model_prices:
                token_exclusion = (
                    "model-price",
                    f"No dated price exists for model {observation['model']!r}.",
                )
            elif observation["contextTier"] == "unknown":
                token_exclusion = (
                    "long-context",
                    "The context tier is unknown, so the applicable token rates cannot be selected.",
                )
            if token_exclusion is None:
                model_price = model_prices[observation["model"]]
                tier_key = (
                    "longContext" if observation["contextTier"] == "long" else "shortContext"
                )
                rates = model_price[tier_key]
                if rates is None:
                    token_exclusion = (
                        "long-context",
                        f"No {observation['contextTier']}-context rate is available for "
                        f"model {observation['model']!r}.",
                    )
            if token_exclusion is not None:
                exclusions.append(
                    Exclusion(
                        record_id,
                        token_component,
                        token_exclusion[0],
                        token_exclusion[1],
                        True,
                    )
                )
            else:
                assert rates is not None
                input_tokens = Decimal(usage["inputTokens"])
                cached_tokens = Decimal(usage["cachedInputTokens"])
                write_tokens = Decimal(usage["cacheWriteInputTokens"])
                output_tokens = Decimal(usage["outputTokens"])
                uncached_tokens = input_tokens - cached_tokens - write_tokens
                amount = (
                    uncached_tokens * decimal_value(rates["inputPerMillion"])
                    + cached_tokens * decimal_value(rates["cachedInputPerMillion"])
                    + write_tokens * decimal_value(rates["cacheWritePerMillion"])
                    + output_tokens * decimal_value(rates["outputPerMillion"])
                ) / MILLION
                components.append(
                    CostComponent(record_id, observation_id, "tokens", amount)
                )

            for tool_index, tool in enumerate(observation["tools"], start=1):
                component_name = f"tool-{tool_index}-{tool['name']}"
                if tool["chargeTreatment"] != "included-in-base-rate-equivalent":
                    exclusions.append(
                        Exclusion(
                            record_id,
                            f"{observation_id}/{component_name}",
                            "tool",
                            tool["excludedReason"],
                            True,
                        )
                    )
                    continue
                price = tool_prices.get(tool["pricingKey"])
                if price is None:
                    exclusions.append(
                        Exclusion(
                            record_id,
                            f"{observation_id}/{component_name}",
                            "tool-price",
                            f"No dated tool rate exists for {tool['pricingKey']!r}.",
                            True,
                        )
                    )
                    continue
                if price["unit"] != tool["unit"]:
                    exclusions.append(
                        Exclusion(
                            record_id,
                            f"{observation_id}/{component_name}",
                            "tool-unit",
                            f"Observed unit {tool['unit']!r} does not match pricing unit {price['unit']!r}.",
                            True,
                        )
                    )
                    continue
                quantity = decimal_value(tool["quantity"])
                rate = decimal_value(price["rateUsd"])
                per_quantity = decimal_value(price["perQuantity"])
                components.append(
                    CostComponent(
                        record_id,
                        observation_id,
                        component_name,
                        quantity * rate / per_quantity,
                    )
                )
    return components, exclusions


def money_summary(
    records: Sequence[dict[str, Any]],
    components: Sequence[CostComponent],
    exclusions: Sequence[Exclusion],
) -> dict[str, Any]:
    record_ids = {record["recordId"] for record in records}
    selected_components = [item for item in components if item.record_id in record_ids]
    selected_exclusions = [item for item in exclusions if item.record_id in record_ids]
    amount = sum((item.amount for item in selected_components), Decimal("0"))
    return {
        "label": classification_label(records, "base-rate equivalent"),
        "currency": "USD",
        "amountUsdExact": exact_money(amount),
        "amountUsdRounded": display_money(amount),
        "actualCharge": False,
        "complete": bool(records)
        and not any(item.affects_base_rate for item in selected_exclusions),
        "includedComponents": sorted(item.key for item in selected_components),
        "excludedComponents": sorted(
            {
                f"{item.record_id}/{item.component}"
                for item in selected_exclusions
            }
        ),
    }


def report_warnings(
    records: Sequence[dict[str, Any]], exclusions: Sequence[Exclusion]
) -> list[str]:
    warnings: set[str] = {
        "Base-rate equivalents are dated API illustrations, not observed invoices or subscription charges.",
        "Pricing is a historical snapshot; re-verify official sources before making a current claim.",
        "Reasoning tokens are a subset of output tokens and are not added again to total tokens or cost.",
    }
    if all(
        record["evidenceClassification"] == "hypothetical-unverified"
        for record in records
    ):
        warnings.add(
            "Every input record is hypothetical/unverified; this report does not support a production capacity claim."
        )
    for record in records:
        record_id = record["recordId"]
        coverage = record["coverage"]
        if coverage["requestLevel"] != "complete":
            warnings.add(
                f"{record_id}: request-level coverage is {coverage['requestLevel']}; "
                f"{coverage['missingRequestLevelReason']}"
            )
        coverage_labels = {
            "longContextPricing": "long-context pricing",
            "cacheWrites": "cache-write usage",
            "tools": "tool usage or charges",
            "credits": "credits",
            "modelMix": "model mix",
        }
        for key, label in coverage_labels.items():
            if coverage[key] == "unavailable":
                warnings.add(f"{record_id}: {label} is unavailable and is not assumed to be zero.")
        billing = record["context"]["billing"]
        if billing["mode"] in {"subscription", "mixed"}:
            warnings.add(
                f"{record_id}: subscription counters do not map one-to-one to API token, tool, or cost line items."
            )
        if any(
            observation["requestCount"] is None
            for observation in record["observations"]
        ):
            warnings.add(f"{record_id}: at least one request count is unknown.")
        if any(
            value is None
            for observation in record["observations"]
            for value in observation["usage"].values()
        ):
            warnings.add(f"{record_id}: token totals contain missing fields; known values are partial.")
    if any(item.affects_base_rate for item in exclusions):
        warnings.add(
            "At least one component is excluded from a base-rate equivalent; inspect excludedCharges before using a total."
        )
    if any(item.category == "credit" for item in exclusions):
        warnings.add("Credits are reported separately and never reduce a base-rate equivalent.")
    return sorted(warnings)


def validate_scenario(label: str, multiplier: Decimal) -> tuple[str, Decimal]:
    label = label.strip()
    if not label:
        raise UsageReportError("Scenario label cannot be empty")
    if re.search(r"\b(?:minimum|maximum|min|max)\b", label, re.IGNORECASE):
        raise UsageReportError(
            "Scenario labels must not claim a minimum or maximum without supporting evidence"
        )
    if re.search(r"planning scenario", label, re.IGNORECASE) is None:
        raise UsageReportError("Scenario labels must include 'planning scenario'")
    if not multiplier.is_finite() or multiplier <= 0:
        raise UsageReportError("Scenario multiplier must be greater than zero")
    return label, multiplier


def parse_scenario(value: str) -> tuple[str, Decimal]:
    label, separator, raw_multiplier = value.rpartition("=")
    raw_multiplier = raw_multiplier.strip()
    if not separator or not label.strip() or not raw_multiplier:
        raise UsageReportError(
            "Scenario must use LABEL=MULTIPLIER, for example '3x planning scenario=3'"
        )
    return validate_scenario(label, decimal_value(raw_multiplier))


def build_report(
    records: Sequence[dict[str, Any]],
    snapshot: dict[str, Any],
    scenarios: Sequence[tuple[str, Decimal]] = (),
) -> dict[str, Any]:
    if not records:
        raise UsageReportError("At least one usage record is required")
    validated_records = [
        validate_usage_record(record, f"usage record {index}")
        for index, record in enumerate(records, start=1)
    ]
    record_ids = [record["recordId"] for record in validated_records]
    if len(record_ids) != len(set(record_ids)):
        raise UsageReportError("Usage records contain duplicate recordId values")
    validated_snapshot = validate_pricing_snapshot(snapshot)
    validate_context_tiers(validated_records, validated_snapshot)
    components, exclusions = calculate_components(validated_records, validated_snapshot)

    internal_records = [
        record
        for record in validated_records
        if record["context"]["scope"] == "internal-development"
    ]
    customer_records = [
        record
        for record in validated_records
        if record["context"]["scope"] != "internal-development"
    ]
    synthesis_records = [
        record
        for record in validated_records
        if record["context"]["scope"] == "synthesis"
    ]
    session_labels = sorted(
        {
            record["context"]["sessionLabel"]
            for record in validated_records
            if record["context"]["scope"] == "customer-session"
        }
    )
    session_groups = [
        (
            label,
            [
                record
                for record in validated_records
                if record["context"]["scope"] == "customer-session"
                and record["context"]["sessionLabel"] == label
            ],
        )
        for label in session_labels
    ]

    customer_money = money_summary(customer_records, components, exclusions)
    customer_record_ids = {record["recordId"] for record in customer_records}
    customer_amount = sum(
        (
            component.amount
            for component in components
            if component.record_id in customer_record_ids
        ),
        Decimal("0"),
    )
    scenario_values = []
    for raw_label, raw_multiplier in scenarios:
        label, multiplier = validate_scenario(raw_label, raw_multiplier)
        amount = customer_amount * multiplier
        scenario_values.append(
            {
                "label": label,
                "classification": "hypothetical",
                "basis": "customer-only base-rate equivalent",
                "basisComplete": customer_money["complete"],
                "multiplier": normalized_decimal(multiplier),
                "amountUsdExact": exact_money(amount),
                "amountUsdRounded": display_money(amount),
                "currency": "USD",
            }
        )

    report: dict[str, Any] = {
        "schemaVersion": REPORT_VERSION,
        "recordType": "usage-report",
        "calculationVersion": CALCULATION_VERSION,
        "inputs": {
            "pricingSnapshotId": validated_snapshot["snapshotId"],
            "pricingValidAsOf": validated_snapshot["validAsOf"],
            "recordIds": sorted(record_ids),
        },
        "rounding": {
            "intermediate": "No intermediate rounding; decimal arithmetic",
            "exactAmounts": "Six decimal places, ROUND_HALF_UP",
            "displayAmounts": "Two decimal places, ROUND_HALF_UP",
        },
        "scopeRelationship": (
            "customerOnly aggregates customer-runtime, customer-session, and synthesis records; "
            "individualSessions and synthesis repeat those customer-only subgroups for inspection "
            "and must not be added to customerOnly again. Internal development is disjoint."
        ),
        "observations": {
            "internalDevelopment": usage_summary(internal_records),
            "customerOnly": usage_summary(customer_records),
            "individualSessions": [
                {"sessionLabel": label, "summary": usage_summary(group)}
                for label, group in session_groups
            ],
            "synthesis": usage_summary(synthesis_records),
        },
        "baseRateEquivalents": {
            "internalDevelopment": money_summary(
                internal_records, components, exclusions
            ),
            "customerOnly": customer_money,
            "individualSessions": [
                {
                    "sessionLabel": label,
                    "summary": money_summary(group, components, exclusions),
                }
                for label, group in session_groups
            ],
            "synthesis": money_summary(synthesis_records, components, exclusions),
        },
        "excludedCharges": [
            item.report_value()
            for item in sorted(
                exclusions,
                key=lambda value: (
                    value.record_id,
                    value.component,
                    value.category,
                    value.description,
                ),
            )
        ],
        "hypotheticalScenarios": scenario_values,
        "warnings": report_warnings(validated_records, exclusions),
        "pricingSources": [
            {
                "title": source["title"],
                "url": source["url"],
                "accessedAt": source["accessedAt"],
            }
            for source in validated_snapshot["sources"]
        ],
    }
    if all(record.get("fixtureKind") == "synthetic" for record in validated_records):
        report["fixtureKind"] = "synthetic"
        report["containsRealCustomerData"] = False
    schema_validate(report, USAGE_REPORT_SCHEMA, "generated usage report")
    return report


def json_text(document: Any) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_text_atomic(path: Path, text: str) -> None:
    """Replace a report atomically with portable shareable permissions."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "posix":
            os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a deterministic usage, base-rate-equivalent, exclusion, and scenario report"
        )
    )
    parser.add_argument(
        "--record",
        action="append",
        required=True,
        help="Redacted usage-record JSON; repeat for every run or scope",
    )
    parser.add_argument("--pricing", required=True, help="Dated pricing-snapshot JSON")
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Hypothetical LABEL=MULTIPLIER, for example '3x planning scenario=3'",
    )
    parser.add_argument("--output", help="Write canonical report JSON instead of stdout")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        records = [load_json(Path(value)) for value in args.record]
        snapshot = load_json(Path(args.pricing))
        scenarios = [parse_scenario(value) for value in args.scenario]
        report = build_report(records, snapshot, scenarios)
        output = json_text(report)
        if args.output:
            output_path = Path(args.output)
            write_text_atomic(output_path, output)
            print(f"Wrote usage report: {output_path}")
        else:
            print(output, end="")
    except UsageReportError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
