from __future__ import annotations

import copy
import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skills" / "run-design-sprint" / "scripts"
ENGINE_PATH = SCRIPT_DIR / "sprint_workspace.py"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "ci"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import sprint_workspace as ENGINE  # noqa: E402
from tests.support.build_ci_site import SECTION_TYPES, build_site  # noqa: E402


class CiContractMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)

    def initialise_state(self) -> tuple[Path, dict[str, Any]]:
        workspace = Path(self.temporary_directory.name) / "state-contract-workspace"
        result = subprocess.run(
            [
                sys.executable,
                str(ENGINE_PATH),
                "init",
                "--title",
                "Synthetic state contract",
                "--challenge",
                "Exercise malformed and contradictory state handling",
                "--execution-mode",
                "planning-rehearsal",
                "--selected-by",
                "Synthetic CI Decider",
                "--mode-reason",
                "This automated fixture does not represent completed sprint activity.",
                "--output",
                str(workspace),
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return workspace, ENGINE.load_state(workspace)

    def test_every_artifact_and_section_renderer_handles_adversarial_content(self) -> None:
        site = Path(self.temporary_directory.name) / "complete-renderer-site"
        build_site(site)
        manifest = ENGINE.read_json(site / ENGINE.SITE_MANIFEST_FILENAME)
        specs = ENGINE.load_artifact_specs()
        self.assertEqual(
            {page["id"] for page in manifest["pages"]},
            {"home", *specs},
        )
        self.assertEqual(ENGINE.site_crawl_errors(site, manifest), [])
        self.assertEqual(ENGINE.rendered_output_errors(site), [])

        canonical_types: set[str] = set()
        for path in sorted((site / "artifact-data").glob("*.json")):
            data = ENGINE.load_artifact_data(path)
            canonical_types.update(section["type"] for section in data["sections"])
        self.assertEqual(canonical_types, set(SECTION_TYPES))

        raw_attack = "<script>window.syntheticOnly = true</script>"
        for page in manifest["pages"]:
            html = (site / page["path"]).read_text(encoding="utf-8")
            with self.subTest(renderer=page["id"]):
                self.assertNotIn(raw_attack, html)
                self.assertNotIn("{{", html)
                self.assertEqual(html.count("<h1>"), 1)

        long_token = "syntheticlayoutpressure" * 180
        rendered_cases = {
            "paragraphs": ENGINE.render_paragraphs([raw_attack, long_token]),
            "list": ENGINE.render_list([raw_attack, long_token]),
            "ordered-list": ENGINE.render_list(
                [raw_attack, long_token], ordered=True
            ),
            "table": ENGINE.render_table(
                {
                    "title": raw_attack,
                    "columns": ["Synthetic", "Oversized"],
                    "rows": [[raw_attack, long_token, "truncated extra cell"]],
                }
            ),
            "cards": ENGINE.render_cards(
                {
                    "cards": [
                        {
                            "title": raw_attack,
                            "body": long_token,
                            "status": "Synthetic rehearsal",
                        }
                    ]
                }
            ),
            "key-value": ENGINE.render_key_values(
                {
                    "items": [
                        {"label": raw_attack, "value": long_token},
                    ]
                }
            ),
            "evidence": ENGINE.render_evidence(
                [
                    {
                        "status": "Synthetic rehearsal",
                        "claim": raw_attack,
                        "source": long_token,
                        "sourceUrl": "javascript:syntheticOnly()",
                    }
                ]
            ),
        }
        for renderer, html in rendered_cases.items():
            with self.subTest(adversarial_renderer=renderer):
                self.assertNotIn(raw_attack, html)
                self.assertIn("&lt;script&gt;", html)
                self.assertIn(long_token, html)
                self.assertNotIn("javascript:syntheticOnly", html)

        empty_contracts = {
            "paragraphs": (ENGINE.render_paragraphs([]), "Nothing recorded yet"),
            "list": (ENGINE.render_list([]), "Nothing recorded yet"),
            "ordered-list": (
                ENGINE.render_list([], ordered=True),
                "Nothing recorded yet",
            ),
            "table": (ENGINE.render_table({}), "No table columns recorded"),
            "cards": (ENGINE.render_cards({}), "No cards recorded"),
            "key-value": (ENGINE.render_key_values({}), "Nothing recorded yet"),
            "evidence": (ENGINE.render_evidence([]), "No evidence entries recorded"),
        }
        for renderer, (html, expected) in empty_contracts.items():
            with self.subTest(empty_renderer=renderer):
                self.assertIn(expected, html)

    def test_route_transition_skip_and_terminal_matrices_are_cartesian(self) -> None:
        for source, target in itertools.product(
            sorted(ENGINE.ROUTES), repeat=2
        ):
            state: dict[str, Any] = {
                "route": source,
                "routeHistory": [],
                "completedSteps": [],
                "currentStep": "02-qualify",
                "status": "active",
                "pendingGate": None,
                "humanGates": [
                    {"id": gate_id, "status": "pending"}
                    for gate_id in ENGINE.GATE_NAMES
                ],
            }
            if source == "undecided":
                state["completedSteps"] = ["01-intake"]
            elif source == "research-first":
                state.update(
                    {
                        "completedSteps": [
                            "01-intake",
                            "02-qualify",
                            "03-evidence",
                        ],
                        "currentStep": "03-evidence",
                        "status": "waiting-for-human",
                    }
                )
                state["humanGates"][0]["status"] = "complete"
            errors = ENGINE.route_change_errors(state, target)
            allowed = target in ENGINE.ROUTE_TRANSITION_TABLE[source]
            with self.subTest(contract="route-transition", source=source, target=target):
                if allowed:
                    self.assertEqual(errors, [])
                else:
                    self.assertTrue(errors)
                    self.assertIn(
                        f"Route transition {source} -> {target} is impossible",
                        errors[0],
                    )

        step_ids = [step["id"] for step in ENGINE.STEPS]
        customer_cases = {
            "not-planned": {
                "status": "not-planned",
                "sessionsCompleted": 0,
                "sessionsUsable": 0,
            },
            "blocked-zero": {
                "status": "blocked",
                "sessionsCompleted": 0,
                "sessionsUsable": 0,
            },
            "blocked-attempted": {
                "status": "blocked",
                "sessionsCompleted": 1,
                "sessionsUsable": 0,
            },
            "partial-unusable": {
                "status": "partial",
                "sessionsCompleted": 2,
                "sessionsUsable": 0,
            },
            "complete-usable": {
                "status": "complete",
                "sessionsCompleted": 2,
                "sessionsUsable": 1,
            },
        }
        for route, mode, customer_case, step_11_state, step_id in itertools.product(
            sorted(ENGINE.ROUTES),
            sorted(ENGINE.EXECUTION_MODES),
            customer_cases,
            ("unrecorded", "skipped", "completed"),
            step_ids,
        ):
            customer = customer_cases[customer_case]
            state = {
                "route": route,
                "routeHistory": [],
                "executionMode": mode,
                "completedSteps": (
                    ["11-customer-sessions"]
                    if step_11_state == "completed"
                    else []
                ),
                "skippedSteps": (
                    ["11-customer-sessions"]
                    if step_11_state == "skipped"
                    else []
                ),
                "customerTesting": customer,
            }
            error = ENGINE.skip_policy_error(state, step_id)
            required = (
                ENGINE.ROUTE_STEP_TRANSITIONS[route][step_id]
                == ENGINE.STEP_REQUIRED
            )
            blocked_without_sessions = (
                customer["status"] == "blocked"
                and customer["sessionsCompleted"] == 0
            )
            allowed = required and (
                (
                    step_id == "11-customer-sessions"
                    and (mode != "live" or blocked_without_sessions)
                )
                or (
                    step_id == "12-synthesis"
                    and (
                        (
                            step_11_state == "skipped"
                            and (mode != "live" or blocked_without_sessions)
                        )
                        or (
                            mode == "live"
                            and step_11_state == "completed"
                            and customer["status"] in {"partial", "blocked"}
                            and customer["sessionsCompleted"] > 0
                            and customer["sessionsUsable"] == 0
                        )
                    )
                )
            )
            with self.subTest(
                contract="skip-policy",
                route=route,
                mode=mode,
                customer_case=customer_case,
                step_11_state=step_11_state,
                step=step_id,
            ):
                if allowed:
                    self.assertIsNone(error)
                else:
                    self.assertIsNotNone(error)

        all_steps = [step["id"] for step in ENGINE.STEPS]
        route_steps = {
            "foundation-plus-design": all_steps,
            "full-design-sprint": [
                step for step in all_steps if step != "04-foundation"
            ],
            "focused-design-sprint": [
                step for step in all_steps if step != "04-foundation"
            ],
        }
        valid_terminals: list[dict[str, Any]] = []
        for route, required in route_steps.items():
            for scenario in ("tested-live", "blocked-live", "self-test", "planning"):
                if scenario == "tested-live":
                    mode = "live"
                    completed = required
                    skipped: list[str] = []
                    customer = {
                        "status": "complete",
                        "sessionsPlanned": 1,
                        "sessionsCompleted": 1,
                        "sessionsUsable": 1,
                    }
                    outcome = "Proceed"
                elif scenario == "blocked-live":
                    mode = "live"
                    completed = [
                        step
                        for step in required
                        if step not in {"11-customer-sessions", "12-synthesis"}
                    ]
                    skipped = ["11-customer-sessions", "12-synthesis"]
                    customer = {
                        "status": "blocked",
                        "sessionsPlanned": 1,
                        "sessionsCompleted": 0,
                        "sessionsUsable": 0,
                    }
                    outcome = "Stop"
                else:
                    mode = "self-test" if scenario == "self-test" else "planning-rehearsal"
                    completed = [
                        step
                        for step in required
                        if step not in {"11-customer-sessions", "12-synthesis"}
                    ]
                    skipped = ["11-customer-sessions", "12-synthesis"]
                    customer = {
                        "status": "not-planned",
                        "sessionsPlanned": 0,
                        "sessionsCompleted": 0,
                        "sessionsUsable": 0,
                    }
                    outcome = "Investigate"
                state = {
                    "route": route,
                    "routeHistory": [
                        {
                            "from": "undecided",
                            "to": route,
                            "reason": "Synthetic terminal matrix fixture.",
                            "selectedAt": "2026-08-18T10:00:00Z",
                        }
                    ],
                    "executionMode": mode,
                    "status": "complete",
                    "currentStep": "13-outcome",
                    "pendingGate": None,
                    "completedSteps": completed,
                    "skippedSteps": skipped,
                    "outcome": outcome,
                    "customerTesting": customer,
                }
                state["terminalState"] = ENGINE.expected_terminal_state(state)
                valid_terminals.append(state)

        for mode in sorted(ENGINE.EXECUTION_MODES):
            direct_no_sprint = {
                "route": "no-sprint",
                "routeHistory": [
                    {
                        "from": "undecided",
                        "to": "no-sprint",
                        "reason": "Synthetic no-sprint terminal fixture.",
                        "selectedAt": "2026-08-18T10:00:00Z",
                    }
                ],
                "executionMode": mode,
                "status": "complete",
                "currentStep": "13-outcome",
                "pendingGate": None,
                "completedSteps": ["01-intake", "02-qualify", "13-outcome"],
                "skippedSteps": [],
                "outcome": "Stop",
                "customerTesting": {
                    "status": "not-planned",
                    "sessionsPlanned": 0,
                    "sessionsCompleted": 0,
                    "sessionsUsable": 0,
                },
            }
            direct_no_sprint["terminalState"] = ENGINE.expected_terminal_state(
                direct_no_sprint
            )
            valid_terminals.append(direct_no_sprint)
        post_research_no_sprint = copy.deepcopy(valid_terminals[-1])
        post_research_no_sprint["routeHistory"] = [
            {
                "from": "undecided",
                "to": "research-first",
                "reason": "Synthetic research-first fixture.",
                "selectedAt": "2026-08-18T09:00:00Z",
            },
            {
                "from": "research-first",
                "to": "no-sprint",
                "reason": "Synthetic post-research stop fixture.",
                "selectedAt": "2026-08-18T10:00:00Z",
            },
        ]
        post_research_no_sprint["completedSteps"] = [
            "01-intake",
            "02-qualify",
            "03-evidence",
            "13-outcome",
        ]
        valid_terminals.append(post_research_no_sprint)

        for state in valid_terminals:
            contract = (
                state["route"],
                state["executionMode"],
                state["customerTesting"]["status"],
                len(state["routeHistory"]),
            )
            with self.subTest(contract="terminal", case=contract):
                self.assertEqual(ENGINE.terminal_state_errors(state), [])
                contradictory = copy.deepcopy(state)
                contradictory["terminalState"] = "not-terminal"
                errors = ENGINE.terminal_state_errors(contradictory)
                self.assertTrue(
                    any(
                        error.startswith("Terminal state must be ")
                        for error in errors
                    ),
                    errors,
                )

    def test_malformed_and_contradictory_states_name_the_violated_contract(self) -> None:
        workspace, initial = self.initialise_state()
        malformed_path = FIXTURE_DIR / "malformed-state.synthetic.json.txt"
        malformed_state = workspace / "malformed-state.json"
        malformed_state.write_text(
            malformed_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        with self.assertRaisesRegex(
            ENGINE.SprintError, "Invalid JSON in .*malformed-state.json"
        ):
            ENGINE.read_json(malformed_state)

        fixture = json.loads(
            (FIXTURE_DIR / "state-contract-cases.synthetic.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(fixture["fixtureKind"], "synthetic")
        self.assertIs(fixture["containsRealCustomerData"], False)

        for case in fixture["schemaCases"]:
            state = copy.deepcopy(initial)
            parent: Any = state
            for part in case["path"][:-1]:
                parent = parent[part]
            key = case["path"][-1]
            if case["operation"] == "remove":
                del parent[key]
            else:
                parent[key] = case["value"]
            issues = [
                str(issue)
                for issue in ENGINE.schema_issues(state, "workspace-state")
            ]
            with self.subTest(contract="schema", case=case["id"]):
                self.assertTrue(
                    any(case["expected"] in issue for issue in issues),
                    f"{case['id']} did not report {case['expected']!r}: {issues}",
                )

        validators: dict[str, Callable[[dict[str, Any]], list[str]]] = {
            "route_history_errors": ENGINE.route_history_errors,
            "validate_state": ENGINE.validate_state,
            "terminal_state_errors": ENGINE.terminal_state_errors,
            "customer_testing_errors": ENGINE.customer_testing_errors,
            "skip_record_errors": ENGINE.skip_record_errors,
        }
        for case in fixture["semanticCases"]:
            state = copy.deepcopy(initial)
            state.update(case["set"])
            errors = validators[case["validator"]](state)
            with self.subTest(contract="semantic", case=case["id"]):
                self.assertTrue(
                    any(case["expected"] in error for error in errors),
                    f"{case['id']} did not report {case['expected']!r}: {errors}",
                )


if __name__ == "__main__":
    unittest.main()
