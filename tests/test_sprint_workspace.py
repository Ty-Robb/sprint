from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "run-design-sprint" / "scripts" / "sprint_workspace.py"
SCHEMAS = REPO_ROOT / "skills" / "run-design-sprint" / "references" / "schemas"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
if str(SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT.parent))


def load_workspace_module():
    spec = importlib.util.spec_from_file_location("sprint_workspace_test_module", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


WORKSPACE_MODULE = load_workspace_module()


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

    def fixture_document(self, relative_path: str) -> dict:
        fixture = json.loads((FIXTURES / relative_path).read_text(encoding="utf-8"))
        self.assertEqual(fixture["fixtureKind"], "synthetic")
        self.assertIs(fixture["containsRealCustomerData"], False)
        return fixture["document"]

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

    def test_published_schemas_accept_representative_valid_fixtures(self) -> None:
        (self.workspace / "artifact-data").mkdir(parents=True)
        self.write_json(
            "sprint-state.json",
            self.fixture_document("schemas/valid/workspace-state-v2.synthetic.json"),
        )
        self.write_json(
            "artifact-data/01-sprint-brief.json",
            self.fixture_document("schemas/valid/artifact-data-v2.synthetic.json"),
        )

        self.run_cli("render", "--workspace", str(self.workspace))
        result = self.run_cli("validate", "--workspace", str(self.workspace))

        self.assertIn("Sprint workspace is valid", result.stdout)
        for schema_path in SCHEMAS.glob("*.schema.json"):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertEqual(
                schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
            )

    def test_reference_schemas_reject_invalid_nested_registry_fields(self) -> None:
        validator = WORKSPACE_MODULE.SchemaValidator()
        references = REPO_ROOT / "skills" / "run-design-sprint" / "references"
        specs = json.loads((references / "artifact-specs.json").read_text(encoding="utf-8"))
        specs["artifacts"]["01-sprint-brief"]["requiredSections"][0] = 7
        spec_issues = validator.validate(
            specs, SCHEMAS / "artifact-specs-v1.schema.json"
        )
        roles = json.loads((references / "role-contracts.json").read_text(encoding="utf-8"))
        roles["roles"]["evidence-researcher"]["may"].append(
            roles["roles"]["evidence-researcher"]["may"][0]
        )
        role_issues = validator.validate(
            roles, SCHEMAS / "role-contracts-v1.schema.json"
        )

        self.assertTrue(
            any(
                issue.json_path
                == "$.artifacts['01-sprint-brief'].requiredSections[0]"
                for issue in spec_issues
            )
        )
        self.assertTrue(
            any(
                issue.json_path == "$.roles['evidence-researcher'].may"
                for issue in role_issues
            )
        )

    def test_invalid_state_reports_the_exact_field_path_at_load(self) -> None:
        self.workspace.mkdir()
        self.write_json(
            "sprint-state.json",
            self.fixture_document("schemas/invalid/workspace-state-v2.synthetic.json"),
        )

        result = self.run_cli(
            "status", "--workspace", str(self.workspace), check=False
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("$.currentStep", result.stderr)
        self.assertIn("99-not-a-step", result.stderr)

    def test_nested_artifact_error_is_rejected_before_mutation_or_render(self) -> None:
        (self.workspace / "artifact-data").mkdir(parents=True)
        self.write_json(
            "sprint-state.json",
            self.fixture_document("schemas/valid/workspace-state-v2.synthetic.json"),
        )
        artifact_path = self.workspace / "artifact-data" / "01-sprint-brief.json"
        self.write_json(
            "artifact-data/01-sprint-brief.json",
            self.fixture_document(
                "schemas/nested-error/artifact-data-v2.synthetic.json"
            ),
        )
        original_artifact = artifact_path.read_bytes()
        original_state = (self.workspace / "sprint-state.json").read_bytes()

        mutation = self.run_cli(
            "artifact-status",
            "--workspace",
            str(self.workspace),
            "--id",
            "01-sprint-brief",
            "--status",
            "in-review",
            check=False,
        )
        render = self.run_cli(
            "render", "--workspace", str(self.workspace), check=False
        )
        state_mutation = self.run_cli(
            "question",
            "--workspace",
            str(self.workspace),
            "--add",
            "This must not be persisted.",
            check=False,
        )

        for result in (mutation, render, state_mutation):
            self.assertEqual(result.returncode, 2)
            self.assertIn("$.sections[4].cards[0].status", result.stderr)
            self.assertIn("Rumour", result.stderr)
        self.assertEqual(artifact_path.read_bytes(), original_artifact)
        self.assertEqual(
            (self.workspace / "sprint-state.json").read_bytes(), original_state
        )
        self.assertFalse((self.workspace / "index.html").exists())

    def test_unsupported_schema_version_fails_with_remediation(self) -> None:
        self.workspace.mkdir()
        state = self.fixture_document(
            "schemas/valid/workspace-state-v2.synthetic.json"
        )
        state["schemaVersion"] = "99.0"
        self.write_json("sprint-state.json", state)

        result = self.run_cli(
            "status", "--workspace", str(self.workspace), check=False
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("$.schemaVersion", result.stderr)
        self.assertIn("unsupported version '99.0'", result.stderr)
        self.assertIn("2.0 (current)", result.stderr)
        self.assertIn("1.0 (migratable)", result.stderr)

    def test_schema_rejects_bad_formats_and_undeclared_fields(self) -> None:
        self.workspace.mkdir()
        state = self.fixture_document(
            "schemas/valid/workspace-state-v2.synthetic.json"
        )
        state["updatedAt"] = "2026-08-17"
        state["undeclared"] = True
        self.write_json("sprint-state.json", state)

        result = self.run_cli(
            "status", "--workspace", str(self.workspace), check=False
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("$.updatedAt: must be a valid date-time", result.stderr)
        self.assertIn("$.undeclared: unexpected field", result.stderr)

    def test_loader_rejects_nonstandard_json_numbers(self) -> None:
        self.workspace.mkdir()
        state = self.fixture_document(
            "schemas/valid/workspace-state-v2.synthetic.json"
        )
        state["customerTesting"]["sessionsPlanned"] = float("nan")
        self.write_json("sprint-state.json", state)

        result = self.run_cli(
            "status", "--workspace", str(self.workspace), check=False
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("non-standard JSON numeric token 'NaN'", result.stderr)

    def test_gate_rejects_invalid_nested_state_before_decision_mutation(self) -> None:
        self.workspace.mkdir()
        state = self.fixture_document(
            "schemas/valid/workspace-state-v2.synthetic.json"
        )
        state["route"] = "full-design-sprint"
        state["currentStep"] = "02-qualify"
        state["pendingGate"] = "gate-1"
        state["humanGates"][0]["name"] = "Wrong gate name"
        self.write_json("sprint-state.json", state)
        original_state = (self.workspace / "sprint-state.json").read_bytes()

        result = self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-1",
            "--decision",
            "Approve",
            "--rationale",
            "This must not be recorded.",
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("$.humanGates[0].name", result.stderr)
        self.assertEqual(
            (self.workspace / "sprint-state.json").read_bytes(), original_state
        )

    def test_legacy_migration_is_deterministic_and_protected(self) -> None:
        (self.workspace / "artifact-data").mkdir(parents=True)
        self.write_json(
            "sprint-state.json",
            self.fixture_document("legacy-workspace/state.synthetic.json"),
        )
        self.write_json(
            "artifact-data/01-sprint-brief.json",
            self.fixture_document(
                "legacy-workspace/artifact-data/01-sprint-brief.synthetic.json"
            ),
        )
        state_path = self.workspace / "sprint-state.json"
        artifact_path = self.workspace / "artifact-data" / "01-sprint-brief.json"
        original_state = state_path.read_bytes()
        original_artifact = artifact_path.read_bytes()
        backup = Path(self.temporary_directory.name) / "legacy-backup"
        occupied_backup = Path(self.temporary_directory.name) / "occupied-backup"

        legacy_load = self.run_cli(
            "status", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(legacy_load.returncode, 2)
        self.assertIn("version '1.0' is legacy", legacy_load.stderr)
        self.assertIn("migrate --workspace", legacy_load.stderr)

        dry_run = self.run_cli(
            "migrate", "--workspace", str(self.workspace), "--dry-run"
        )
        self.assertIn("Dry run complete", dry_run.stdout)
        self.assertEqual(state_path.read_bytes(), original_state)
        self.assertEqual(artifact_path.read_bytes(), original_artifact)
        self.assertFalse(backup.exists())

        occupied_backup.mkdir()
        refused = self.run_cli(
            "migrate",
            "--workspace",
            str(self.workspace),
            "--backup",
            str(occupied_backup),
            check=False,
        )
        self.assertEqual(refused.returncode, 2)
        self.assertIn("refusing to overwrite", refused.stderr)
        self.assertEqual(state_path.read_bytes(), original_state)
        self.assertEqual(artifact_path.read_bytes(), original_artifact)

        migrated = self.run_cli(
            "migrate",
            "--workspace",
            str(self.workspace),
            "--backup",
            str(backup),
        )
        self.assertIn("Untouched backup", migrated.stdout)
        expected_state = self.fixture_document(
            "legacy-workspace-expected/state.synthetic.json"
        )
        expected_artifact = self.fixture_document(
            "legacy-workspace-expected/artifact-data/01-sprint-brief.synthetic.json"
        )
        self.assertEqual(self.read_json("sprint-state.json"), expected_state)
        self.assertEqual(
            self.read_json("artifact-data/01-sprint-brief.json"), expected_artifact
        )
        self.assertEqual(
            state_path.read_text(encoding="utf-8"),
            json.dumps(
                expected_state,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
        )
        self.assertEqual(
            artifact_path.read_text(encoding="utf-8"),
            json.dumps(
                expected_artifact,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
        )
        self.assertEqual((backup / "sprint-state.json").read_bytes(), original_state)
        self.assertEqual(
            (backup / "artifact-data" / "01-sprint-brief.json").read_bytes(),
            original_artifact,
        )
        unused_backup = Path(self.temporary_directory.name) / "unused-backup"
        no_op = self.run_cli(
            "migrate",
            "--workspace",
            str(self.workspace),
            "--backup",
            str(unused_backup),
        )
        self.assertIn("already uses schema version 2.0", no_op.stdout)
        self.assertFalse(unused_backup.exists())
        self.run_cli("render", "--workspace", str(self.workspace))
        self.run_cli("validate", "--workspace", str(self.workspace))

    def test_repeated_render_is_byte_and_timestamp_stable(self) -> None:
        self.initialise()
        paths = sorted(path for path in self.workspace.rglob("*") if path.is_file())
        before = {
            path.relative_to(self.workspace): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in paths
        }
        state_before = self.read_json("sprint-state.json")
        artifact_before = self.read_json("artifact-data/01-sprint-brief.json")

        self.run_cli("render", "--workspace", str(self.workspace))
        self.run_cli("render", "--workspace", str(self.workspace))

        after_paths = sorted(path for path in self.workspace.rglob("*") if path.is_file())
        after = {
            path.relative_to(self.workspace): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in after_paths
        }
        self.assertEqual(after, before)
        self.assertEqual(
            self.read_json("sprint-state.json")["updatedAt"], state_before["updatedAt"]
        )
        self.assertEqual(
            self.read_json("artifact-data/01-sprint-brief.json")["updatedAt"],
            artifact_before["updatedAt"],
        )

    @unittest.skipUnless(os.name == "posix", "POSIX permission bits are required")
    def test_generated_and_canonical_files_have_portable_permissions(self) -> None:
        previous_umask = os.umask(0o077)
        try:
            self.initialise()
        finally:
            os.umask(previous_umask)
        expected = [
            self.workspace / "sprint-state.json",
            self.workspace / "artifact-data" / "01-sprint-brief.json",
            self.workspace / "index.html",
            self.workspace / "artifacts" / "01-sprint-brief.html",
            self.workspace / "assets" / "sprint.css",
        ]

        for path in expected:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644, path)

        result = self.run_cli(
            "render", "--workspace", str(self.workspace), "--check"
        )
        self.assertIn("Rendered output is current", result.stdout)

    def test_render_check_and_validate_detect_and_repair_stale_views(self) -> None:
        self.initialise()
        artifact = self.workspace / "artifacts" / "01-sprint-brief.html"
        artifact.write_text(
            artifact.read_text(encoding="utf-8") + "<!-- manual drift -->\n",
            encoding="utf-8",
        )
        orphan = self.workspace / "artifacts" / "orphan.html"
        orphan.write_text("stale\n", encoding="utf-8")

        check_result = self.run_cli(
            "render", "--workspace", str(self.workspace), "--check", check=False
        )
        self.assertEqual(check_result.returncode, 1)
        self.assertIn("Stale rendered file: artifacts/01-sprint-brief.html", check_result.stderr)
        self.assertIn("artifacts/orphan.html", check_result.stderr)

        validate_result = self.run_cli(
            "validate", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(validate_result.returncode, 1)
        self.assertIn("Stale rendered file", validate_result.stderr)

        self.run_cli("render", "--workspace", str(self.workspace))
        self.assertFalse(orphan.exists())
        self.run_cli("render", "--workspace", str(self.workspace), "--check")
        self.run_cli("validate", "--workspace", str(self.workspace))

        canonical = self.read_json("artifact-data/01-sprint-brief.json")
        canonical["summary"] = ["Canonical content changed after the last render."]
        self.write_json("artifact-data/01-sprint-brief.json", canonical)
        canonical_result = self.run_cli(
            "render", "--workspace", str(self.workspace), "--check", check=False
        )
        self.assertEqual(canonical_result.returncode, 1)
        self.assertIn(
            "Stale rendered file: artifacts/01-sprint-brief.html",
            canonical_result.stderr,
        )
        self.run_cli("render", "--workspace", str(self.workspace))
        self.run_cli("render", "--workspace", str(self.workspace), "--check")

    def test_artifact_catalog_and_json_serialization_are_deterministic(self) -> None:
        self.initialise()
        for artifact_id in ("13-outcome", "02-evidence-ledger"):
            self.run_cli(
                "new-artifact",
                "--workspace",
                str(self.workspace),
                "--id",
                artifact_id,
            )
        data_dir = self.workspace / "artifact-data"
        (data_dir / "13-outcome.json").rename(data_dir / "a-outcome.json")
        (data_dir / "02-evidence-ledger.json").rename(data_dir / "z-evidence.json")

        self.run_cli("render", "--workspace", str(self.workspace))

        state = self.read_json("sprint-state.json")
        self.assertEqual(
            [item["id"] for item in state["artifacts"]],
            ["01-sprint-brief", "02-evidence-ledger", "13-outcome"],
        )
        dashboard = (self.workspace / "index.html").read_text(encoding="utf-8")
        self.assertLess(
            dashboard.index("02-evidence-ledger.html"),
            dashboard.index("13-outcome.html"),
        )
        self.assertEqual(
            WORKSPACE_MODULE.json_text({"z": 1, "a": "é"}),
            '{\n  "a": "é",\n  "z": 1\n}\n',
        )
        self.run_cli("render", "--workspace", str(self.workspace), "--check")

    def test_interrupted_atomic_batch_restores_prior_files(self) -> None:
        first = Path(self.temporary_directory.name) / "first.txt"
        second = Path(self.temporary_directory.name) / "second.txt"
        WORKSPACE_MODULE.write_text(first, "old first\n")
        WORKSPACE_MODULE.write_text(second, "old second\n")
        real_replace = os.replace
        replacement_count = 0

        def interrupt_second_replacement(source, destination):
            nonlocal replacement_count
            replacement_count += 1
            if replacement_count == 2:
                raise OSError("simulated interruption")
            return real_replace(source, destination)

        with mock.patch.object(
            WORKSPACE_MODULE.os,
            "replace",
            side_effect=interrupt_second_replacement,
        ):
            with self.assertRaisesRegex(
                WORKSPACE_MODULE.SprintError, "Atomic replacement failed"
            ):
                WORKSPACE_MODULE.write_texts_atomically(
                    {first: "new first\n", second: "new second\n"}
                )

        self.assertEqual(first.read_text(encoding="utf-8"), "old first\n")
        self.assertEqual(second.read_text(encoding="utf-8"), "old second\n")
        self.assertEqual(list(first.parent.glob(".first.txt.*")), [])
        self.assertEqual(list(second.parent.glob(".second.txt.*")), [])

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
