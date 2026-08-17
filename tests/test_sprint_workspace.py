from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "run-design-sprint" / "scripts" / "sprint_workspace.py"


class SprintWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.workspace = Path(self.temporary_directory.name) / "sprint"

    def run_cli(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            cwd=REPO_ROOT,
            check=check,
            capture_output=True,
            text=True,
        )

    def initialise(self, challenge: str = "Improve onboarding") -> None:
        self.run_cli(
            "init",
            "--title",
            "Test Sprint",
            "--challenge",
            challenge,
            "--output",
            str(self.workspace),
        )

    def read_json(self, relative_path: str) -> dict:
        return json.loads((self.workspace / relative_path).read_text(encoding="utf-8"))

    def write_json(self, relative_path: str, data: dict) -> None:
        (self.workspace / relative_path).write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )

    def complete_artifact(self, artifact_id: str) -> None:
        path = f"artifact-data/{artifact_id}.json"
        data = self.read_json(path)
        data["status"] = "complete"
        data["summary"] = ["Established for the automated test."]
        for section in data["sections"]:
            section["type"] = "paragraphs"
            section["paragraphs"] = [f"{section['title']} established for the test."]
            for key in ("items", "rows", "cards", "body"):
                section.pop(key, None)
        data["nextActions"] = ["Continue to the next sprint step."]
        self.write_json(path, data)
        self.run_cli("render", "--workspace", str(self.workspace))

    def test_init_renders_valid_escaped_workspace(self) -> None:
        challenge = "Help <parents> avoid <script>alert('x')</script>"
        self.initialise(challenge)

        dashboard = (self.workspace / "index.html").read_text(encoding="utf-8")
        brief = (self.workspace / "artifacts" / "01-sprint-brief.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("Help &lt;parents&gt;", dashboard)
        self.assertNotIn("<script>alert", dashboard)
        self.assertNotIn("<script>alert", brief)
        self.assertIn("Private by default", dashboard)
        workspace_ignore = (self.workspace / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("**/transcripts/", workspace_ignore)
        self.assertIn("**/account-evidence/", workspace_ignore)
        result = self.run_cli("validate", "--workspace", str(self.workspace))
        self.assertIn("Sprint workspace is valid", result.stdout)

    def test_role_packet_is_bounded_to_declared_inputs(self) -> None:
        self.initialise()
        self.run_cli(
            "role-packet",
            "--workspace",
            str(self.workspace),
            "--role",
            "evidence-researcher",
            "--task",
            "Inventory the evidence without proposing a solution.",
            "--input",
            "artifact-data/01-sprint-brief.json",
            "--output",
            "working/01-intake/evidence-researcher.md",
        )

        packet = (
            self.workspace / "working" / "01-intake" / "evidence-researcher.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Evidence Researcher", packet)
        self.assertIn("artifact-data/01-sprint-brief.json", packet)
        self.assertIn("Do not read other sprint files", packet)
        self.assertIn("Must not", packet)

        result = self.run_cli(
            "role-packet",
            "--workspace",
            str(self.workspace),
            "--role",
            "evidence-researcher",
            "--task",
            "Read an undeclared file.",
            "--input",
            "../outside.txt",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("escapes the sprint workspace", result.stderr)

    def test_challenge_and_questions_update_through_commands(self) -> None:
        self.initialise()
        refined = "Help solo founders choose what to build next"
        self.run_cli(
            "set-challenge",
            "--workspace",
            str(self.workspace),
            "--challenge",
            refined,
        )
        self.run_cli(
            "question",
            "--workspace",
            str(self.workspace),
            "--add",
            "Can we recruit suitable founders this week?",
        )
        self.run_cli(
            "question",
            "--workspace",
            str(self.workspace),
            "--resolve",
            "Can we recruit suitable founders this week?",
        )

        state = self.read_json("sprint-state.json")
        brief = self.read_json("artifact-data/01-sprint-brief.json")
        dashboard = (self.workspace / "index.html").read_text(encoding="utf-8")
        self.assertEqual(state["challenge"], refined)
        self.assertEqual(brief["summary"][0], refined)
        self.assertIn(refined, dashboard)
        self.assertNotIn("Can we recruit suitable founders this week?", state["openQuestions"])
        self.assertEqual(
            state["resolvedQuestions"][-1]["question"],
            "Can we recruit suitable founders this week?",
        )

    def test_full_route_enforces_gate_and_skips_foundation(self) -> None:
        self.initialise()
        self.complete_artifact("01-sprint-brief")
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "01-intake",
        )
        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "full-design-sprint",
            "--rationale",
            "The strategic foundation already exists.",
        )
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "02-qualify",
        )

        waiting = self.read_json("sprint-state.json")
        self.assertEqual(waiting["pendingGate"], "gate-1")
        self.assertEqual(waiting["status"], "waiting-for-human")

        self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-1",
            "--decision",
            "Approve",
            "--rationale",
            "Proceed with the recommended route.",
        )
        routed = self.read_json("sprint-state.json")
        self.assertEqual(routed["currentStep"], "03-evidence")
        self.assertIn("04-foundation", routed["skippedSteps"])

        self.run_cli(
            "new-artifact",
            "--workspace",
            str(self.workspace),
            "--id",
            "02-evidence-ledger",
        )
        self.complete_artifact("02-evidence-ledger")
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "03-evidence",
        )
        advanced = self.read_json("sprint-state.json")
        self.assertEqual(advanced["currentStep"], "05-map")
        self.run_cli("validate", "--workspace", str(self.workspace))

    def test_completed_artifact_cannot_keep_placeholder_sections(self) -> None:
        self.initialise()
        data = self.read_json("artifact-data/01-sprint-brief.json")
        data["status"] = "complete"
        self.write_json("artifact-data/01-sprint-brief.json", data)

        result = self.run_cli("render", "--workspace", str(self.workspace), check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Required section is still empty", result.stderr)

    def test_customer_step_requires_real_session(self) -> None:
        self.initialise()
        state = self.read_json("sprint-state.json")
        state["route"] = "full-design-sprint"
        state["status"] = "active"
        state["currentStep"] = "11-customer-sessions"
        self.write_json("sprint-state.json", state)
        for artifact_id in ("10-test-plan", "11-customer-evidence"):
            self.run_cli(
                "new-artifact",
                "--workspace",
                str(self.workspace),
                "--id",
                artifact_id,
            )
            self.complete_artifact(artifact_id)

        result = self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "11-customer-sessions",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("real customer session", result.stderr)
        blocked = self.read_json("sprint-state.json")
        self.assertEqual(blocked["status"], "waiting-for-customers")

        self.run_cli(
            "customer",
            "--workspace",
            str(self.workspace),
            "--status",
            "complete",
            "--target",
            "Homeschooling parents",
            "--planned",
            "1",
            "--completed",
            "1",
        )
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "11-customer-sessions",
        )
        completed = self.read_json("sprint-state.json")
        self.assertEqual(completed["currentStep"], "12-synthesis")

    def test_foundation_route_runs_end_to_end(self) -> None:
        self.initialise("Help solo founders test a product idea with an AI team")
        self.complete_artifact("01-sprint-brief")
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "01-intake",
        )
        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "foundation-plus-design",
            "--rationale",
            "The product needs a founding hypothesis before prototyping.",
        )
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "02-qualify",
        )
        self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-1",
            "--decision",
            "Approve",
            "--rationale",
            "Run the foundation and design stages.",
        )

        single_artifact_steps = [
            ("03-evidence", "02-evidence-ledger"),
            ("04-foundation", "03-foundation"),
            ("05-map", "04-journey-map"),
            ("06-questions", "05-sprint-questions"),
            ("07-explore", "06-solution-directions"),
            ("08-decide", "07-decision"),
        ]
        gates = {
            "06-questions": ("gate-2", "Approve target and risks"),
            "08-decide": ("gate-3", "Choose direction A"),
        }
        for step_id, artifact_id in single_artifact_steps:
            self.run_cli(
                "new-artifact",
                "--workspace",
                str(self.workspace),
                "--id",
                artifact_id,
            )
            self.complete_artifact(artifact_id)
            self.run_cli(
                "complete-step",
                "--workspace",
                str(self.workspace),
                "--step",
                step_id,
            )
            if step_id in gates:
                gate_id, decision = gates[step_id]
                self.run_cli(
                    "gate",
                    "--workspace",
                    str(self.workspace),
                    "--gate",
                    gate_id,
                    "--decision",
                    decision,
                    "--rationale",
                    "The fixture approves the evidence-backed recommendation.",
                )

        for artifact_id in ("08-experiment", "09-storyboard"):
            self.run_cli(
                "new-artifact",
                "--workspace",
                str(self.workspace),
                "--id",
                artifact_id,
            )
            self.complete_artifact(artifact_id)
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "09-experiment",
        )

        (self.workspace / "prototype" / "index.html").write_text(
            "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Prototype</title></head><body><main><h1>Prototype</h1></main></body></html>\n",
            encoding="utf-8",
        )
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "10-prototype",
        )
        self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-4",
            "--decision",
            "Approve for testing",
            "--rationale",
            "The prototype covers the approved experiment scenes.",
        )

        for artifact_id in ("10-test-plan", "11-customer-evidence"):
            self.run_cli(
                "new-artifact",
                "--workspace",
                str(self.workspace),
                "--id",
                artifact_id,
            )
            self.complete_artifact(artifact_id)
        self.run_cli(
            "customer",
            "--workspace",
            str(self.workspace),
            "--status",
            "complete",
            "--target",
            "Solo founders",
            "--planned",
            "2",
            "--completed",
            "2",
        )
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "11-customer-sessions",
        )

        for step_id, artifact_id in (
            ("12-synthesis", "12-synthesis"),
            ("13-outcome", "13-outcome"),
        ):
            self.run_cli(
                "new-artifact",
                "--workspace",
                str(self.workspace),
                "--id",
                artifact_id,
            )
            self.complete_artifact(artifact_id)
            self.run_cli(
                "complete-step",
                "--workspace",
                str(self.workspace),
                "--step",
                step_id,
            )

        self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-5",
            "--decision",
            "Proceed",
            "--rationale",
            "The directional customer evidence supports the next investment.",
        )
        result = self.run_cli("validate", "--workspace", str(self.workspace))
        self.assertIn("Sprint workspace is valid", result.stdout)
        state = self.read_json("sprint-state.json")
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["outcome"], "Proceed")
        dashboard = (self.workspace / "index.html").read_text(encoding="utf-8")
        self.assertIn("100%", dashboard)

    def test_no_sprint_route_closes_without_customer_claims(self) -> None:
        self.initialise("Ship an already approved copy change")
        self.complete_artifact("01-sprint-brief")
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "01-intake",
        )
        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "no-sprint",
            "--rationale",
            "The direction is settled and only delivery remains.",
        )
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "02-qualify",
        )
        self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-1",
            "--decision",
            "Approve no-sprint route",
            "--rationale",
            "A sprint would add ceremony without reducing uncertainty.",
        )
        routed = self.read_json("sprint-state.json")
        self.assertEqual(routed["currentStep"], "13-outcome")
        self.assertEqual(len(routed["skippedSteps"]), 10)

        self.run_cli(
            "new-artifact",
            "--workspace",
            str(self.workspace),
            "--id",
            "13-outcome",
        )
        self.complete_artifact("13-outcome")
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "13-outcome",
        )
        self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-5",
            "--decision",
            "Stop",
            "--rationale",
            "Hand the approved work directly to delivery.",
        )
        self.run_cli("validate", "--workspace", str(self.workspace))
        state = self.read_json("sprint-state.json")
        self.assertEqual(state["customerTesting"]["sessionsCompleted"], 0)
        self.assertEqual(state["outcome"], "Stop")


if __name__ == "__main__":
    unittest.main()
