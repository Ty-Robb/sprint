from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "run-design-sprint" / "scripts"
REPORT_SCRIPT = SCRIPT_DIR / "usage_report.py"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("usage_report", REPORT_SCRIPT)
assert SPEC and SPEC.loader
USAGE_REPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = USAGE_REPORT
SPEC.loader.exec_module(USAGE_REPORT)

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "usage"
RECORD_NAMES = (
    "internal-development.synthetic.usage-record.json",
    "customer-runtime.synthetic.usage-record.json",
    "session-s01.synthetic.usage-record.json",
    "session-s02-missing.synthetic.usage-record.json",
    "synthesis.synthetic.usage-record.json",
)
PRICING_NAME = "official-2026-08-17.synthetic.pricing-snapshot.json"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class UsageReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [load_fixture(name) for name in RECORD_NAMES]
        self.pricing = load_fixture(PRICING_NAME)

    def report(self, *scenarios: tuple[str, Decimal]) -> dict:
        return USAGE_REPORT.build_report(self.records, self.pricing, scenarios)

    def test_summation_keeps_internal_customer_sessions_and_synthesis_separate(self) -> None:
        report = self.report()

        internal = report["observations"]["internalDevelopment"]
        customer = report["observations"]["customerOnly"]
        synthesis = report["observations"]["synthesis"]
        sessions = report["observations"]["individualSessions"]

        self.assertEqual(internal["tokenTotals"]["totalTokens"], 19000)
        self.assertEqual(customer["tokenTotals"]["totalTokens"], 374500)
        self.assertEqual(customer["tokenTotals"]["inputTokens"], 343000)
        self.assertEqual(customer["tokenTotals"]["outputTokens"], 31500)
        self.assertNotIn("SYN-INTERNAL-01", customer["recordIds"])
        self.assertIn("SYN-SYNTHESIS-01", customer["recordIds"])
        self.assertEqual(synthesis["tokenTotals"]["totalTokens"], 10500)
        self.assertEqual(
            [item["sessionLabel"] for item in sessions], ["SYN-S01", "SYN-S02"]
        )
        self.assertEqual(sessions[0]["summary"]["tokenTotals"]["totalTokens"], 13000)
        self.assertIn("must not be added", report["scopeRelationship"])

    def test_reasoning_tokens_are_reported_but_never_double_counted(self) -> None:
        report = self.report()
        internal = report["observations"]["internalDevelopment"]["tokenTotals"]

        self.assertEqual(internal["inputTokens"], 15000)
        self.assertEqual(internal["outputTokens"], 4000)
        self.assertEqual(internal["reasoningTokens"], 1400)
        self.assertEqual(internal["totalTokens"], 19000)
        self.assertTrue(internal["reasoningIncludedInOutputTokens"])
        self.assertEqual(
            report["baseRateEquivalents"]["internalDevelopment"]["amountUsdExact"],
            "0.027490",
        )

        invalid = copy.deepcopy(self.records[0])
        invalid["observations"][0]["usage"]["totalTokens"] += invalid[
            "observations"
        ][0]["usage"]["reasoningTokens"]
        with self.assertRaisesRegex(
            USAGE_REPORT.UsageReportError, "reasoningTokens is already included"
        ):
            USAGE_REPORT.validate_usage_record(invalid)

    def test_base_rate_uses_model_mix_long_context_cache_writes_and_tools(self) -> None:
        customer_runtime = self.records[1]
        report = USAGE_REPORT.build_report([customer_runtime], self.pricing)
        amount = report["baseRateEquivalents"]["customerOnly"]

        self.assertEqual(amount["amountUsdExact"], "0.215000")
        self.assertEqual(amount["amountUsdRounded"], "0.22")
        self.assertTrue(amount["complete"])
        self.assertIn(
            "SYN-CUSTOMER-RUNTIME-01/CUSTOMER-REQ-02/tool-1-web-search",
            amount["includedComponents"],
        )
        self.assertEqual(
            report["observations"]["customerOnly"]["models"],
            ["gpt-5.6-luna", "gpt-5.6-terra"],
        )

        short_context = copy.deepcopy(customer_runtime)
        short_context["observations"][1]["contextTier"] = "short"
        with self.assertRaisesRegex(
            USAGE_REPORT.UsageReportError, "dated threshold is 272000"
        ):
            USAGE_REPORT.build_report([short_context], self.pricing)

    def test_rounding_is_decimal_half_up_at_documented_precision(self) -> None:
        self.assertEqual(USAGE_REPORT.exact_money(Decimal("0.1234565")), "0.123457")
        self.assertEqual(USAGE_REPORT.display_money(Decimal("0.005")), "0.01")
        self.assertEqual(USAGE_REPORT.display_money(Decimal("0.004")), "0.00")

        report = self.report(("3x planning scenario", Decimal("3")))
        self.assertEqual(
            report["baseRateEquivalents"]["customerOnly"]["amountUsdExact"],
            "0.229710",
        )
        self.assertEqual(
            report["baseRateEquivalents"]["customerOnly"]["amountUsdRounded"],
            "0.23",
        )
        self.assertEqual(report["hypotheticalScenarios"][0]["amountUsdExact"], "0.689130")
        self.assertEqual(report["hypotheticalScenarios"][0]["amountUsdRounded"], "0.69")

    def test_missing_data_is_partial_warned_and_excluded_not_zero_filled(self) -> None:
        report = self.report()
        customer_usage = report["observations"]["customerOnly"]
        customer_cost = report["baseRateEquivalents"]["customerOnly"]
        warning_text = "\n".join(report["warnings"])

        self.assertFalse(customer_usage["requestCountComplete"])
        self.assertFalse(customer_usage["tokenTotalsComplete"])
        self.assertFalse(customer_cost["complete"])
        self.assertIn("request-level coverage is unavailable", warning_text)
        self.assertIn("cache-write usage is unavailable", warning_text)
        self.assertIn("long-context pricing is unavailable", warning_text)
        self.assertIn("model mix is unavailable", warning_text)
        self.assertIn("tool usage or charges is unavailable", warning_text)
        self.assertTrue(
            any(
                item["category"] == "missing-token-data"
                and item["recordId"] == "SYN-SESSION-S02-MISSING"
                for item in report["excludedCharges"]
            )
        )

    def test_subscription_and_credits_are_never_presented_as_api_charges(self) -> None:
        report = self.report()
        session = report["baseRateEquivalents"]["individualSessions"][0]["summary"]
        warning_text = "\n".join(report["warnings"])

        self.assertFalse(session["actualCharge"])
        self.assertTrue(session["complete"])
        self.assertIn("subscription counters do not map one-to-one", warning_text)
        self.assertIn("Credits are reported separately", warning_text)
        self.assertTrue(
            any(item["category"] == "credit" for item in report["excludedCharges"])
        )

    def test_scenario_labels_require_planning_language_and_reject_extrema(self) -> None:
        label, multiplier = USAGE_REPORT.parse_scenario("3x planning scenario=3")
        self.assertEqual(label, "3x planning scenario")
        self.assertEqual(multiplier, Decimal("3"))

        for value in (
            "minimum plan=1",
            "maximum planning scenario=4",
            "production case=2",
            "3x planning scenario=0",
        ):
            with self.subTest(value=value):
                with self.assertRaises(USAGE_REPORT.UsageReportError):
                    USAGE_REPORT.parse_scenario(value)

        with self.assertRaises(USAGE_REPORT.UsageReportError):
            USAGE_REPORT.build_report(
                self.records,
                self.pricing,
                (("minimum planning scenario", Decimal("1")),),
            )

        observed = copy.deepcopy(self.records[0])
        observed["evidenceClassification"] = "sanitized-observed"
        self.assertEqual(
            USAGE_REPORT.classification_label(
                [observed], "base-rate equivalent"
            ),
            "Observed base-rate equivalent",
        )
        observed["provenance"]["sourceType"] = "sanitized-runtime-metadata"
        observed["provenance"]["redactions"] = ["Synthetic test redaction marker"]
        with self.assertRaisesRegex(
            USAGE_REPORT.UsageReportError, "synthetic cannot be combined"
        ):
            USAGE_REPORT.validate_usage_record(observed)

    def test_cli_is_reproducible_and_emits_the_documented_totals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            base_command = [sys.executable, str(REPORT_SCRIPT)]
            for name in RECORD_NAMES:
                base_command.extend(["--record", str(FIXTURE_DIR / name)])
            base_command.extend(
                [
                    "--pricing",
                    str(FIXTURE_DIR / PRICING_NAME),
                    "--scenario",
                    "3x planning scenario=3",
                ]
            )
            for output in (first, second):
                result = subprocess.run(
                    [*base_command, "--output", str(output)],
                    cwd=REPO_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            report = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(
                report["baseRateEquivalents"]["customerOnly"]["amountUsdRounded"],
                "0.23",
            )
            self.assertEqual(report["hypotheticalScenarios"][0]["label"], "3x planning scenario")
            self.assertNotIn("generatedAt", report)

        forward = self.report(("3x planning scenario", Decimal("3")))
        reverse = USAGE_REPORT.build_report(
            list(reversed(self.records)),
            self.pricing,
            (("3x planning scenario", Decimal("3")),),
        )
        self.assertEqual(USAGE_REPORT.json_text(forward), USAGE_REPORT.json_text(reverse))


if __name__ == "__main__":
    unittest.main()
