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

    def write_result_memo(self, relative_path: str, marker: str) -> None:
        path = self.workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        sections = [
            "Findings",
            "Evidence and provenance",
            "Assumptions and inferences",
            "Recommendation",
            "Risks or disagreements",
            "Open questions",
            "Stop condition reached",
        ]
        path.write_text(
            "# Specialist result\n\n"
            + "\n\n".join(
                f"## {section}\n\n{marker}: {section}." for section in sections
            )
            + "\n",
            encoding="utf-8",
        )

    def complete_required_assignments(self, step_id: str) -> None:
        roles = WORKSPACE_MODULE.REQUIRED_ROLES_BY_STEP.get(step_id, ())
        assignment_ids = []
        for index, role in enumerate(roles, start=1):
            run_id = f"{step_id}-{role}-run-{index}"
            assignment_id = f"{step_id}-{role}-assignment"
            assignment_ids.append((assignment_id, role))
            self.run_cli(
                "role-packet",
                "--workspace",
                str(self.workspace),
                "--role",
                role,
                "--task",
                f"Return the bounded {role} analysis for {step_id}.",
                "--assignee",
                f"Synthetic {role}",
                "--run-id",
                run_id,
                "--assignment-id",
                assignment_id,
                "--output",
                f"working/{step_id}/{role}.packet.md",
            )
        for assignment_id, role in assignment_ids:
            memo = f"working/{step_id}/{role}.result.md"
            self.write_result_memo(memo, assignment_id)
            self.run_cli(
                "role-result",
                "--workspace",
                str(self.workspace),
                "--assignment",
                assignment_id,
                "--memo",
                memo,
            )

    def advance_to_qualify(self) -> None:
        self.initialise()
        self.complete_artifact("01-sprint-brief")
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "01-intake",
        )

    def create_qualify_packets(self, *, include_brief: bool = False) -> list[str]:
        assignment_ids = []
        for index, role in enumerate(
            WORKSPACE_MODULE.REQUIRED_ROLES_BY_STEP["02-qualify"], start=1
        ):
            assignment_id = f"02-qualify-{role}-test"
            arguments = [
                "role-packet",
                "--workspace",
                str(self.workspace),
                "--role",
                role,
                "--task",
                f"Assess qualification from the {role} boundary.",
                "--assignee",
                f"Synthetic {role}",
                "--run-id",
                f"isolated-run-{index}",
                "--assignment-id",
                assignment_id,
                "--output",
                f"working/02-qualify/{role}.packet.md",
            ]
            if include_brief:
                arguments.extend(["--input", "artifact-data/01-sprint-brief.json"])
            self.run_cli(*arguments)
            assignment_ids.append(assignment_id)
        return assignment_ids


    def prepare_customer_session_inputs(self) -> None:
        prototype = self.workspace / "prototype" / "index.html"
        prototype.parent.mkdir(parents=True, exist_ok=True)
        if not prototype.exists():
            prototype.write_text(
                "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Prototype</title></head><body><main><h1>Prototype</h1></main></body></html>\n",
                encoding="utf-8",
            )
        shared = self.workspace / "working" / "11-customer-sessions" / "shared"
        shared.mkdir(parents=True, exist_ok=True)
        (shared / "prototype-context.md").write_text(
            "Test the onboarding decision flow. Mocked actions do not persist.\n",
            encoding="utf-8",
        )
        (shared / "interview-guide.md").write_text(
            "Ask for recent context, present TASK-1, then use neutral follow-up prompts.\n",
            encoding="utf-8",
        )
        (shared / "scorecard.md").write_text(
            "Q1: Can the participant complete TASK-1 without help?\n",
            encoding="utf-8",
        )

    def set_customer_plan(self, planned: int, target: str = "Qualified participants") -> None:
        self.run_cli(
            "customer",
            "--workspace",
            str(self.workspace),
            "--status",
            "scheduled",
            "--target",
            target,
            "--planned",
            str(planned),
        )

    def initialise_customer_session(
        self,
        session_id: str,
        participant_id: str,
        *,
        session_date: str = "2026-08-17",
    ) -> None:
        self.prepare_customer_session_inputs()
        self.run_cli(
            "session-init",
            "--workspace",
            str(self.workspace),
            "--session-id",
            session_id,
            "--participant-id",
            participant_id,
            "--session-date",
            session_date,
            "--prototype-version",
            "proto-v1",
            "--questions-version",
            "questions-v1",
            "--prototype",
            "prototype/index.html",
            "--prototype-context",
            "working/11-customer-sessions/shared/prototype-context.md",
            "--interview-guide",
            "working/11-customer-sessions/shared/interview-guide.md",
            "--scorecard",
            "working/11-customer-sessions/shared/scorecard.md",
            "--consent-status",
            "granted",
            "--consent-scope",
            "Notes and anonymized research summary",
            "--consent-reference",
            f"consent-register:{session_id}",
            "--redaction-status",
            "complete",
        )

    def populate_customer_summary(self, session_id: str, observation: str) -> None:
        path = f"customer-testing/sessions/{session_id}/summary.json"
        summary = self.read_json(path)
        summary["qualificationSummary"] = "Matches the approved behavioural criteria."
        summary["sourceReferences"] = [
            {
                "id": "SRC1",
                "kind": "notes",
                "reference": f"private://{session_id}/moderator-notes#N1",
                "redactionStatus": "complete",
            }
        ]
        summary["observations"] = [
            {
                "id": "OBS1",
                "label": "Observed",
                "text": observation,
                "sourceReferenceIds": ["SRC1"],
            }
        ]
        summary["inferences"] = [
            {
                "id": "INF1",
                "label": "Inference",
                "text": "The first decision point may need clearer framing.",
                "observationIds": ["OBS1"],
            }
        ]
        summary["quoteReferences"] = [
            {"id": "QUOTE1", "sourceReferenceId": "SRC1", "locator": "N1"}
        ]
        summary["taskOutcomes"] = [
            {
                "taskId": "TASK-1",
                "outcome": "partial",
                "observationIds": ["OBS1"],
                "notes": "Needed one neutral prompt.",
            }
        ]
        summary["questionEvidence"] = [
            {
                "questionId": "Q1",
                "assessment": "mixed",
                "observationIds": ["OBS1"],
                "notes": "The core route was found, with hesitation.",
            }
        ]
        summary["surprises"] = ["The participant first inspected the secondary action."]
        summary["moderatorDeviations"] = []
        summary["limitations"] = ["One directional session; no prevalence claim."]
        summary["uncertainties"] = ["Whether repeated use removes the hesitation."]
        self.write_json(path, summary)

    def complete_customer_session(self, session_id: str, observation: str) -> None:
        record = self.read_json(f"customer-testing/sessions/{session_id}/session.json")
        if record["packet"]["path"] is None:
            self.run_cli(
                "session-packet",
                "--workspace",
                str(self.workspace),
                "--session-id",
                session_id,
            )
        self.populate_customer_summary(session_id, observation)
        self.run_cli(
            "session-complete",
            "--workspace",
            str(self.workspace),
            "--session-id",
            session_id,
            "--usage-unavailable-reason",
            "The test runtime did not expose token or request measurements.",
        )

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
        manifest = self.read_json("customer-testing/session-manifest.json")
        self.assertEqual(manifest["recordType"], "customer-session-manifest")
        self.assertEqual(manifest["sessions"], [])
        self.assertEqual(manifest["currentVersions"]["prototype"], None)
        result = self.run_cli("validate", "--workspace", str(self.workspace))
        self.assertIn("Sprint workspace is valid", result.stdout)

    def test_published_schemas_accept_representative_valid_fixtures(self) -> None:
        (self.workspace / "artifact-data").mkdir(parents=True)
        self.write_json(
            "sprint-state.json",
            self.fixture_document("schemas/valid/workspace-state-v2.synthetic.json"),
        )
        self.write_json(
            "assignment-manifest.json",
            self.fixture_document(
                "schemas/valid/assignment-manifest-v1.synthetic.json"
            ),
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
        methods = json.loads(
            (references / "method-profiles.json").read_text(encoding="utf-8")
        )
        methods["nonNegotiablePrinciples"][0]["statement"] = (
            "AI may make consequential choices."
        )
        method_issues = validator.validate(
            methods, SCHEMAS / "method-profiles-v1.schema.json"
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
        self.assertTrue(
            any(
                issue.json_path == "$.nonNegotiablePrinciples[0].statement"
                for issue in method_issues
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
        self.write_json(
            "assignment-manifest.json",
            self.fixture_document(
                "schemas/valid/assignment-manifest-v1.synthetic.json"
            ),
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
            self.workspace / "assignment-manifest.json",
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

    def test_book_profile_defaults_to_five_and_records_explicit_adaptations(self) -> None:
        self.run_cli(
            "init",
            "--title",
            "Book Sprint",
            "--challenge",
            "Test the riskiest assumption",
            "--method-profile",
            "sprint-book",
            "--execution-mode",
            "live",
            "--selected-by",
            "human Decider",
            "--profile-reason",
            "Use the canonical five-day profile.",
            "--mode-reason",
            "Suitable real customers are available.",
            "--output",
            str(self.workspace),
        )
        state = self.read_json("sprint-state.json")
        self.assertEqual(state["schemaVersion"], "2.0")
        self.assertEqual(state["methodProfile"], "sprint-book")
        self.assertEqual(state["executionMode"], "live")
        self.assertEqual(state["route"], "undecided")
        self.assertEqual(state["customerTesting"]["sessionsPlanned"], 5)
        self.assertEqual(len(state["fidelity"]["steps"]), 13)
        explore = state["fidelity"]["steps"]["07-explore"]
        self.assertIn("canonicalPurpose", explore)
        self.assertIn("human", explore["participants"])
        self.assertIn("ai", explore["participants"])
        self.assertIn("suggestedMinutes", explore["timebox"])
        self.assertIsNone(explore["timebox"]["actualMinutes"])
        self.assertEqual(len(explore["deviations"]), 2)
        for deviation in explore["deviations"]:
            self.assertTrue(deviation["preservedPurpose"])
            self.assertTrue(deviation["reason"])
            self.assertEqual(
                set(deviation["impact"]),
                {"methodFidelity", "evidence", "decisionReadiness"},
            )
        self.assertEqual(
            state["fidelity"]["summary"]["assessment"],
            "adapted-with-documented-substitutions",
        )
        dashboard = (self.workspace / "index.html").read_text(encoding="utf-8")
        self.assertIn("Method: Sprint Book", dashboard)
        self.assertIn("Mode: Live", dashboard)
        self.assertIn("Method fidelity", dashboard)
        self.assertIn("One human Decider plus bounded AI specialists", dashboard)
        self.assertIn("Show current-step method, participants, and timebox", dashboard)
        self.assertIn("Pre-sprint challenge intake and Decider alignment", dashboard)
        status = self.run_cli("status", "--workspace", str(self.workspace))
        self.assertIn("Canonical purpose:", status.stdout)
        self.assertIn("30 minutes suggested", status.stdout)
        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "full-design-sprint",
            "--rationale",
            "The strategic foundation is ready.",
        )
        no_reason = self.run_cli(
            "customer",
            "--workspace",
            str(self.workspace),
            "--status",
            "recruiting",
            "--target",
            "Qualified buyers",
            "--planned",
            "3",
            check=False,
        )
        self.assertEqual(no_reason.returncode, 2)
        self.assertIn("target from five requires --rationale", no_reason.stderr)
        self.run_cli(
            "customer",
            "--workspace",
            str(self.workspace),
            "--status",
            "recruiting",
            "--target",
            "Qualified buyers",
            "--planned",
            "3",
            "--rationale",
            "Only three suitable buyers can attend this week.",
        )
        changed = self.read_json("sprint-state.json")
        target_deviation = next(
            item
            for item in changed["fidelity"]["steps"]["11-customer-sessions"][
                "deviations"
            ]
            if item["id"] == "customer-target"
        )
        self.assertEqual(target_deviation["type"], "compression")
        self.assertTrue(target_deviation["impact"]["decisionReadiness"])
        self.run_cli("validate", "--workspace", str(self.workspace))

    def test_profile_mode_route_combinations_reject_only_method_mismatch(self) -> None:
        self.run_cli(
            "init",
            "--title",
            "Book Rehearsal",
            "--challenge",
            "Rehearse the full process",
            "--method-profile",
            "sprint-book",
            "--execution-mode",
            "self-test",
            "--output",
            str(self.workspace),
        )
        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "full-design-sprint",
            "--rationale",
            "Rehearse the complete route.",
        )
        valid = self.read_json("sprint-state.json")
        self.assertEqual(valid["executionMode"], "self-test")
        self.assertEqual(valid["route"], "full-design-sprint")
        self.assertEqual(
            valid["fidelity"]["summary"]["assessment"],
            "self-test-rehearsal",
        )

        result = self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "focused-design-sprint",
            "--rationale",
            "Try a shorter route.",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("incompatible", result.stderr)
        unchanged = self.read_json("sprint-state.json")
        self.assertEqual(unchanged["route"], "full-design-sprint")

    def test_adaptive_planning_research_route_is_valid(self) -> None:
        self.run_cli(
            "init",
            "--title",
            "Research Plan",
            "--challenge",
            "Plan research into an unclear problem",
            "--method-profile",
            "adaptive-design-sprint",
            "--execution-mode",
            "planning-rehearsal",
            "--output",
            str(self.workspace),
        )
        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "research-first",
            "--rationale",
            "The customer and problem are not understood.",
        )
        self.run_cli("validate", "--workspace", str(self.workspace))

    def test_self_test_rejects_customer_sessions_and_misleading_observed_claims(self) -> None:
        self.run_cli(
            "init",
            "--title",
            "Self Test",
            "--challenge",
            "Exercise the workflow",
            "--execution-mode",
            "self-test",
            "--output",
            str(self.workspace),
        )
        customer_result = self.run_cli(
            "customer",
            "--workspace",
            str(self.workspace),
            "--status",
            "complete",
            "--target",
            "Founders",
            "--planned",
            "5",
            "--completed",
            "5",
            check=False,
        )
        self.assertEqual(customer_result.returncode, 2)
        self.assertIn("cannot record live customer sessions", customer_result.stderr)

        self.run_cli(
            "new-artifact",
            "--workspace",
            str(self.workspace),
            "--id",
            "11-customer-evidence",
        )
        data = self.read_json("artifact-data/11-customer-evidence.json")
        data["status"] = "complete"
        data["summary"] = ["The product was customer-validated with real customers."]
        for section in data["sections"]:
            section["paragraphs"] = ["Five real customer sessions were completed."]
        data["evidence"] = [
            {
                "status": "Observed",
                "claim": "Five customers validated the product.",
                "source": "Synthetic rehearsal",
            }
        ]
        self.write_json("artifact-data/11-customer-evidence.json", data)
        render_result = self.run_cli(
            "render", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(render_result.returncode, 2)
        self.assertIn("cannot complete a customer-evidence artifact", render_result.stderr)
        self.assertIn("claims live customer evidence", render_result.stderr)
        self.assertIn("labels a customer claim Observed", render_result.stderr)

    def test_directional_evidence_cannot_claim_statistical_validation(self) -> None:
        self.initialise()
        self.set_customer_plan(2, "Founders")
        self.initialise_customer_session("S01", "P01")
        self.complete_customer_session("S01", "The participant paused before TASK-1.")
        data = self.read_json("artifact-data/01-sprint-brief.json")
        data["evidence"].append(
            {
                "status": "Inference",
                "claim": "The product is statistically validated by customers.",
                "source": "One directional session",
            }
        )
        self.write_json("artifact-data/01-sprint-brief.json", data)
        result = self.run_cli(
            "render", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("directional", result.stderr)

    def test_fidelity_updates_require_compression_impacts(self) -> None:
        self.initialise()
        invalid = self.run_cli(
            "record-fidelity",
            "--workspace",
            str(self.workspace),
            "--step",
            "01-intake",
            "--actual-minutes",
            "15",
            check=False,
        )
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("compression deviation", invalid.stderr)

        self.run_cli(
            "record-fidelity",
            "--workspace",
            str(self.workspace),
            "--step",
            "01-intake",
            "--selected-method",
            "Focused challenge intake",
            "--actual-minutes",
            "15",
            "--deviation-type",
            "compression",
            "--reason",
            "The brief and evidence inventory already existed.",
            "--method-impact",
            "The intake used half of the suggested timebox.",
            "--evidence-impact",
            "Existing material reduced collection time, but hidden constraints may remain.",
            "--decision-impact",
            "The Decider must reopen intake if qualification exposes a missing constraint.",
        )
        state = self.read_json("sprint-state.json")
        intake = state["fidelity"]["steps"]["01-intake"]
        self.assertEqual(intake["timebox"]["actualMinutes"], 15)
        self.assertEqual(intake["deviations"][-1]["type"], "compression")
        self.run_cli("validate", "--workspace", str(self.workspace))

    def test_non_negotiable_learning_principles_cannot_be_weakened(self) -> None:
        self.initialise()
        state = self.read_json("sprint-state.json")
        state["fidelity"]["nonNegotiablePrinciples"][0]["statement"] = (
            "AI may make consequential choices."
        )
        self.write_json("sprint-state.json", state)
        result = self.run_cli(
            "validate", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot be weakened", result.stderr)

    def test_schema_one_state_migrates_compatibly_with_protected_command(self) -> None:
        self.initialise()
        state = self.read_json("sprint-state.json")
        state["schemaVersion"] = "1.0"
        state["route"] = "full-design-sprint"
        state["skippedSteps"] = ["04-foundation"]
        state["skipReasons"] = {
            "04-foundation": "The strategic foundation already exists."
        }
        legacy_decided_at = state["updatedAt"]
        state["decisions"] = [
            {
                "gate": "gate-1",
                "decision": "Approve full route",
                "rationale": "The legacy record approved this route.",
                "reservations": "",
                "decidedAt": legacy_decided_at,
            }
        ]
        state["humanGates"][0].update(
            {
                "status": "complete",
                "decision": "Approve full route",
                "rationale": "The legacy record approved this route.",
                "decidedAt": legacy_decided_at,
            }
        )
        for key in (
            "methodProfile",
            "executionMode",
            "methodProfileSelection",
            "executionModeSelection",
            "fidelity",
            "notApplicableSteps",
        ):
            state.pop(key)
        self.write_json("sprint-state.json", state)

        blocked_render = self.run_cli(
            "render", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(blocked_render.returncode, 2)
        self.assertIn("migrate --workspace", blocked_render.stderr)
        backup = Path(self.temporary_directory.name) / "compatibility-backup"
        self.run_cli(
            "migrate",
            "--workspace",
            str(self.workspace),
            "--backup",
            str(backup),
        )
        self.run_cli("render", "--workspace", str(self.workspace))
        migrated = self.read_json("sprint-state.json")
        self.assertEqual(migrated["schemaVersion"], "2.0")
        self.assertEqual(migrated["methodProfile"], "adaptive-design-sprint")
        self.assertEqual(migrated["executionMode"], "live")
        self.assertEqual(migrated["notApplicableSteps"], ["04-foundation"])
        self.assertEqual(migrated["skippedSteps"], [])
        self.assertEqual(
            migrated["compatibility"]["migratedFromSchemaVersion"], "1.0"
        )
        self.assertIn("review", migrated["compatibility"]["migrationNote"])
        self.assertEqual(
            migrated["humanGates"][0]["decisionId"], "gate-1-decision-1"
        )
        self.assertEqual(
            migrated["decisions"][0]["deciderLabel"],
            "human Decider (legacy label unavailable)",
        )
        self.assertEqual(migrated["decisions"][0]["status"], "active")
        self.run_cli("validate", "--workspace", str(self.workspace))

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
            "--assignee",
            "Evidence worker",
            "--run-id",
            "evidence-run-1",
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
        dashboard = (self.workspace / "index.html").read_text(encoding="utf-8")
        self.assertIn("Evidence Researcher", dashboard)
        self.assertIn("Assigned", dashboard)

        result = self.run_cli(
            "role-packet",
            "--workspace",
            str(self.workspace),
            "--role",
            "product-strategist",
            "--task",
            "Read an undeclared file.",
            "--assignee",
            "Evidence worker",
            "--run-id",
            "evidence-run-2",
            "--input",
            "../outside.txt",
            "--output",
            "working/01-intake/escape.packet.md",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("escapes the sprint workspace", result.stderr)

    def test_missing_assignment_and_required_output_fail_before_convergence(self) -> None:
        self.advance_to_qualify()
        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "full-design-sprint",
            "--rationale",
            "Qualification recommends a complete route.",
        )

        missing = self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "02-qualify",
            check=False,
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("missing required evidence-researcher assignment", missing.stderr)

        assignment_ids = self.create_qualify_packets()
        incomplete_memo = "working/02-qualify/incomplete.result.md"
        self.write_result_memo(incomplete_memo, "missing-output-test")
        memo_path = self.workspace / incomplete_memo
        memo_path.write_text(
            memo_path.read_text(encoding="utf-8").replace(
                "## Open questions", "## Questions omitted"
            ),
            encoding="utf-8",
        )
        incomplete = self.run_cli(
            "role-result",
            "--workspace",
            str(self.workspace),
            "--assignment",
            assignment_ids[0],
            "--memo",
            incomplete_memo,
            check=False,
        )
        self.assertEqual(incomplete.returncode, 2)
        self.assertIn("missing required section 'Open questions'", incomplete.stderr)

    def test_stale_assignment_input_is_rejected(self) -> None:
        self.advance_to_qualify()
        assignment_ids = self.create_qualify_packets(include_brief=True)
        brief = self.read_json("artifact-data/01-sprint-brief.json")
        brief["summary"] = ["Material research changed after packet assignment."]
        self.write_json("artifact-data/01-sprint-brief.json", brief)
        memo = "working/02-qualify/evidence-researcher.result.md"
        self.write_result_memo(memo, "stale-result")

        result = self.run_cli(
            "role-result",
            "--workspace",
            str(self.workspace),
            "--assignment",
            assignment_ids[0],
            "--memo",
            memo,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("is stale because input", result.stderr)
        self.run_cli(
            "assignment-status",
            "--workspace",
            str(self.workspace),
            "--assignment",
            assignment_ids[0],
            "--status",
            "rejected",
            "--note",
            "The packet input changed before the run returned.",
        )
        self.run_cli(
            "assignment-status",
            "--workspace",
            str(self.workspace),
            "--assignment",
            assignment_ids[1],
            "--status",
            "rejected",
            "--note",
            "The shared packet input changed before the run returned.",
        )
        self.run_cli(
            "role-packet",
            "--workspace",
            str(self.workspace),
            "--role",
            "evidence-researcher",
            "--task",
            "Re-run qualification against the refreshed brief.",
            "--assignee",
            "Replacement evidence worker",
            "--run-id",
            "isolated-run-replacement",
            "--assignment-id",
            "02-qualify-evidence-researcher-replacement",
            "--input",
            "artifact-data/01-sprint-brief.json",
            "--output",
            "working/02-qualify/evidence-researcher-replacement.packet.md",
        )

    def test_duplicate_and_cross_contaminated_assignments_are_rejected(self) -> None:
        self.advance_to_qualify()
        assignment_ids = self.create_qualify_packets()
        duplicate = self.run_cli(
            "role-packet",
            "--workspace",
            str(self.workspace),
            "--role",
            "evidence-researcher",
            "--task",
            "Duplicate the qualification analysis.",
            "--assignee",
            "Another worker",
            "--run-id",
            "isolated-run-3",
            "--assignment-id",
            "02-qualify-evidence-researcher-duplicate",
            "--output",
            "working/02-qualify/evidence-researcher-duplicate.packet.md",
            check=False,
        )
        self.assertEqual(duplicate.returncode, 2)
        self.assertIn("Duplicate assignment for 02-qualify/evidence-researcher", duplicate.stderr)

        contaminated_memo = "working/02-qualify/evidence-researcher.result.md"
        self.write_result_memo(contaminated_memo, assignment_ids[1])
        contaminated = self.run_cli(
            "role-result",
            "--workspace",
            str(self.workspace),
            "--assignment",
            assignment_ids[0],
            "--memo",
            contaminated_memo,
            check=False,
        )
        self.assertEqual(contaminated.returncode, 2)
        self.assertIn("references peer assignment", contaminated.stderr)

    def test_duplicate_result_content_does_not_satisfy_required_roles(self) -> None:
        self.advance_to_qualify()
        assignment_ids = self.create_qualify_packets()
        first_memo = "working/02-qualify/first.result.md"
        second_memo = "working/02-qualify/second.result.md"
        self.write_result_memo(first_memo, "shared-duplicate-content")
        (self.workspace / second_memo).write_bytes(
            (self.workspace / first_memo).read_bytes()
        )
        self.run_cli(
            "role-result",
            "--workspace",
            str(self.workspace),
            "--assignment",
            assignment_ids[0],
            "--memo",
            first_memo,
        )
        duplicate = self.run_cli(
            "role-result",
            "--workspace",
            str(self.workspace),
            "--assignment",
            assignment_ids[1],
            "--memo",
            second_memo,
            check=False,
        )
        self.assertEqual(duplicate.returncode, 2)
        self.assertIn("duplicate result memo digest", duplicate.stderr)
        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "full-design-sprint",
            "--rationale",
            "Test duplicate-result gate enforcement.",
        )
        blocked = self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "02-qualify",
            check=False,
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("validated returned result memo is required", blocked.stderr)

    def test_valid_assignments_are_traceable_without_rendering_private_memos(self) -> None:
        self.advance_to_qualify()
        assignment_ids = self.create_qualify_packets()
        private_marker = "RAW-PRIVATE-EVIDENCE-MUST-NOT-RENDER"
        for assignment_id, role in zip(
            assignment_ids,
            WORKSPACE_MODULE.REQUIRED_ROLES_BY_STEP["02-qualify"],
        ):
            memo = f"working/02-qualify/{role}.result.md"
            self.write_result_memo(memo, f"{assignment_id}-{private_marker}")
            self.run_cli(
                "role-result",
                "--workspace",
                str(self.workspace),
                "--assignment",
                assignment_id,
                "--memo",
                memo,
            )
        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "full-design-sprint",
            "--rationale",
            "The returned role results support the route.",
        )
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "02-qualify",
        )

        manifest = self.read_json("assignment-manifest.json")
        self.assertEqual(
            {item["status"] for item in manifest["assignments"]}, {"returned"}
        )
        self.assertTrue(
            all(item["resultMemo"]["sourceAssignmentId"] == item["id"] for item in manifest["assignments"])
        )
        dashboard = (self.workspace / "index.html").read_text(encoding="utf-8")
        self.assertIn("Specialist assignments", dashboard)
        self.assertIn("Synthetic evidence-researcher", dashboard)
        self.assertNotIn(private_marker, dashboard)
        self.assertNotIn("working/02-qualify", dashboard)
        self.assertNotIn("isolated-run-1", dashboard)
        self.run_cli("validate", "--workspace", str(self.workspace))

    def test_human_decisions_are_attested_and_material_changes_require_new_records(self) -> None:
        self.advance_to_qualify()
        assignment_ids = self.create_qualify_packets()
        for assignment_id, role in zip(
            assignment_ids,
            WORKSPACE_MODULE.REQUIRED_ROLES_BY_STEP["02-qualify"],
        ):
            memo = f"working/02-qualify/{role}.result.md"
            self.write_result_memo(memo, assignment_id)
            self.run_cli(
                "role-result",
                "--workspace",
                str(self.workspace),
                "--assignment",
                assignment_id,
                "--memo",
                memo,
            )
        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "full-design-sprint",
            "--rationale",
            "Initial research supports the full route.",
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
            "Approve full route",
            "--decider",
            "Founder Decider",
            "--considered-input",
            f"assignment:{assignment_ids[0]}",
        )
        first = self.read_json("sprint-state.json")
        first_decision = first["decisions"][-1]
        self.assertEqual(first_decision["deciderLabel"], "Founder Decider")
        self.assertGreaterEqual(len(first_decision["consideredInputs"]), 3)
        self.assertEqual(first["humanGates"][0]["decisionId"], first_decision["id"])

        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "focused-design-sprint",
            "--rationale",
            "Material research narrowed the uncertainty.",
        )
        reopened = self.read_json("sprint-state.json")
        self.assertEqual(reopened["pendingGate"], "gate-1")
        self.assertEqual(reopened["decisions"][0]["status"], "superseded")
        self.assertEqual(reopened["humanGates"][0]["status"], "pending")
        self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-1",
            "--decision",
            "Approve focused route",
            "--decider",
            "Founder Decider",
        )

        self.run_cli(
            "new-artifact",
            "--workspace",
            str(self.workspace),
            "--id",
            "07-decision",
        )
        self.complete_artifact("07-decision")
        state = self.read_json("sprint-state.json")
        state["currentStep"] = "08-decide"
        state["pendingGate"] = "gate-3"
        self.write_json("sprint-state.json", state)
        self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-3",
            "--decision",
            "Choose concept alpha",
            "--concept",
            "concept-alpha",
            "--decider",
            "Founder Decider",
        )
        self.run_cli(
            "set-concept",
            "--workspace",
            str(self.workspace),
            "--concept",
            "concept-beta",
            "--rationale",
            "Material research invalidated concept alpha.",
        )
        changed = self.read_json("sprint-state.json")
        self.assertEqual(changed["pendingGate"], "gate-3")
        self.assertEqual(changed["humanGates"][2]["status"], "pending")
        self.assertEqual(changed["decisions"][-1]["status"], "superseded")

        duplicate_state = changed
        duplicate_state["decisions"].append(dict(duplicate_state["decisions"][1]))
        self.write_json("sprint-state.json", duplicate_state)
        duplicate = self.run_cli(
            "validate", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(duplicate.returncode, 1)
        self.assertIn("Duplicate decision id", duplicate.stderr)

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
        self.complete_required_assignments("02-qualify")
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
        self.assertIn("04-foundation", routed["notApplicableSteps"])
        self.assertNotIn("04-foundation", routed["skippedSteps"])

        self.run_cli(
            "new-artifact",
            "--workspace",
            str(self.workspace),
            "--id",
            "02-evidence-ledger",
        )
        self.complete_artifact("02-evidence-ledger")
        self.complete_required_assignments("03-evidence")
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
        self.complete_artifact("10-test-plan")
        self.complete_required_assignments("11-customer-sessions")

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

        self.set_customer_plan(1, "Homeschooling parents")
        self.initialise_customer_session("S01", "P01")
        self.complete_customer_session(
            "S01", "The participant completed TASK-1 after a short pause."
        )
        self.complete_artifact("11-customer-evidence")
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "11-customer-sessions",
        )
        completed = self.read_json("sprint-state.json")
        self.assertEqual(completed["currentStep"], "12-synthesis")

    def test_per_session_packets_are_isolated_versioned_and_bounded(self) -> None:
        self.initialise()
        self.set_customer_plan(2)
        self.initialise_customer_session("S01", "P01")
        self.run_cli(
            "session-packet",
            "--workspace",
            str(self.workspace),
            "--session-id",
            "S01",
        )
        raw_path = (
            self.workspace
            / "customer-testing"
            / "sessions"
            / "S01"
            / "raw"
            / "transcript.txt"
        )
        raw_path.parent.mkdir(parents=True)
        raw_path.write_text("S01-RAW-TRANSCRIPT-MARKER\n" * 5000, encoding="utf-8")

        self.initialise_customer_session("S02", "P02")
        self.run_cli(
            "session-packet",
            "--workspace",
            str(self.workspace),
            "--session-id",
            "S02",
        )
        packet_one = (
            self.workspace / "customer-testing" / "sessions" / "S01" / "handoff.md"
        ).read_text(encoding="utf-8")
        packet_two = (
            self.workspace / "customer-testing" / "sessions" / "S02" / "handoff.md"
        ).read_text(encoding="utf-8")
        self.assertIn("complete operating context for one fresh chat", packet_two)
        self.assertNotIn("S01-RAW-TRANSCRIPT-MARKER", packet_two)
        self.assertNotIn("customer-testing/sessions/S01", packet_two)
        self.assertLess(abs(len(packet_one) - len(packet_two)), 20)

        manifest = self.read_json("customer-testing/session-manifest.json")
        self.assertEqual(len(manifest["versionCatalog"]["prototypes"]), 1)
        self.assertEqual(len(manifest["versionCatalog"]["questions"]), 1)
        for entry in manifest["sessions"]:
            record = self.read_json(entry["recordPath"])
            self.assertLessEqual(
                record["packet"]["characters"],
                manifest["contextBudget"]["perSessionMaximum"],
            )
            self.assertTrue(record["packet"]["freshChatRequired"])
        scorecard = (
            self.workspace
            / "working"
            / "11-customer-sessions"
            / "shared"
            / "scorecard.md"
        )
        original_scorecard = scorecard.read_text(encoding="utf-8")
        scorecard.write_text("Q1 changed without a version bump.\n", encoding="utf-8")
        drifted = self.run_cli(
            "session-packet",
            "--workspace",
            str(self.workspace),
            "--session-id",
            "S02",
            check=False,
        )
        self.assertEqual(drifted.returncode, 2)
        self.assertIn("changed after its version was recorded", drifted.stderr)
        scorecard.write_text(original_scorecard, encoding="utf-8")
        self.run_cli("validate", "--workspace", str(self.workspace))

    def test_completion_reopen_and_resume_use_persisted_structured_state(self) -> None:
        self.initialise()
        self.set_customer_plan(1)
        self.initialise_customer_session("S01", "P01")
        direct_count = self.run_cli(
            "customer",
            "--workspace",
            str(self.workspace),
            "--status",
            "complete",
            "--target",
            "Qualified participants",
            "--planned",
            "1",
            "--completed",
            "1",
            check=False,
        )
        self.assertEqual(direct_count.returncode, 2)
        self.assertIn("derived from the canonical session manifest", direct_count.stderr)
        self.run_cli(
            "session-packet",
            "--workspace",
            str(self.workspace),
            "--session-id",
            "S01",
        )
        self.run_cli(
            "session-checkpoint",
            "--workspace",
            str(self.workspace),
            "--session-id",
            "S01",
            "--status",
            "in-progress",
            "--phase",
            "follow-up",
            "--completed-phase",
            "prototype-tasks",
            "--next-action",
            "Finish follow-up and persist the summary.",
        )
        self.populate_customer_summary(
            "S01", "The participant paused, then completed TASK-1 without instruction."
        )
        self.run_cli(
            "session-complete",
            "--workspace",
            str(self.workspace),
            "--session-id",
            "S01",
            "--usage-input-tokens",
            "1200",
            "--usage-output-tokens",
            "450",
            "--usage-total-tokens",
            "1650",
            "--usage-requests",
            "3",
            "--usage-source",
            "runtime response metadata",
        )
        state = self.read_json("sprint-state.json")
        manifest = self.read_json("customer-testing/session-manifest.json")
        record = self.read_json("customer-testing/sessions/S01/session.json")
        self.assertEqual(state["customerTesting"]["sessionsCompleted"], 1)
        self.assertTrue(manifest["sessions"][0]["counted"])
        self.assertTrue(record["usage"]["available"])
        self.assertEqual(record["usage"]["measurementContext"], "customer-session")

        duplicate = self.run_cli(
            "session-complete",
            "--workspace",
            str(self.workspace),
            "--session-id",
            "S01",
            check=False,
        )
        self.assertEqual(duplicate.returncode, 2)
        self.assertIn("counted once", duplicate.stderr)
        self.assertEqual(
            self.read_json("sprint-state.json")["customerTesting"]["sessionsCompleted"],
            1,
        )

        self.run_cli(
            "session-reopen",
            "--workspace",
            str(self.workspace),
            "--session-id",
            "S01",
            "--reason",
            "Clarify the task-outcome classification.",
        )
        self.assertEqual(
            self.read_json("sprint-state.json")["customerTesting"]["sessionsCompleted"],
            0,
        )
        self.run_cli(
            "session-packet",
            "--workspace",
            str(self.workspace),
            "--session-id",
            "S01",
        )
        resume_packet = (
            self.workspace / "customer-testing" / "sessions" / "S01" / "handoff.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Persisted resume checkpoint", resume_packet)
        self.assertIn("completed TASK-1", resume_packet)
        self.assertNotIn("private://S01/moderator-notes", resume_packet)
        self.assertIn("This replaces conversation replay", resume_packet)

    def test_synthesis_packet_excludes_raw_evidence_and_preserves_trace_ids(self) -> None:
        self.initialise()
        self.set_customer_plan(2)
        for session_id, participant_id, observation in (
            ("S01", "P01", "The participant found TASK-1 without help."),
            ("S02", "P02", "The participant needed a neutral prompt on TASK-1."),
        ):
            self.initialise_customer_session(session_id, participant_id)
            raw_path = (
                self.workspace
                / "customer-testing"
                / "sessions"
                / session_id
                / "raw"
                / "transcript.txt"
            )
            raw_path.parent.mkdir(parents=True)
            raw_path.write_text(
                f"RAW-{session_id}-SECRET-CONTENT\n" * 3000, encoding="utf-8"
            )
            self.complete_customer_session(session_id, observation)

        self.run_cli("synthesis-packet", "--workspace", str(self.workspace))
        packet = (
            self.workspace
            / "customer-testing"
            / "synthesis"
            / "synthesis-packet.md"
        ).read_text(encoding="utf-8")
        self.assertIn('"traceId": "S01/OBS1"', packet)
        self.assertIn("The participant found TASK-1", packet)
        self.assertIn("The participant needed a neutral prompt", packet)
        self.assertNotIn("RAW-S01-SECRET-CONTENT", packet)
        self.assertNotIn("RAW-S02-SECRET-CONTENT", packet)
        self.assertNotIn("private://S01", packet)
        self.assertNotIn("private://S02", packet)
        manifest = self.read_json("customer-testing/session-manifest.json")
        self.assertFalse(manifest["synthesis"]["rawEvidenceIncluded"])
        self.assertEqual(manifest["synthesis"]["sessionIds"], ["S01", "S02"])
        self.run_cli(
            "new-artifact",
            "--workspace",
            str(self.workspace),
            "--id",
            "12-synthesis",
        )
        self.complete_artifact("12-synthesis")
        synthesis_artifact = self.read_json("artifact-data/12-synthesis.json")
        synthesis_artifact["evidence"] = [
            {
                "status": "Inference",
                "claim": "Both participants completed the task.",
                "source": "S01/OBS1; S02/NOT-A-REAL-TRACE",
            }
        ]
        self.write_json("artifact-data/12-synthesis.json", synthesis_artifact)
        self.run_cli("render", "--workspace", str(self.workspace))
        untraceable = self.run_cli(
            "validate", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(untraceable.returncode, 1)
        self.assertIn("unknown trace IDs: S02/NOT-A-REAL-TRACE", untraceable.stderr)
        synthesis_artifact["evidence"][0]["source"] = "S01/OBS1; S02/OBS1"
        self.write_json("artifact-data/12-synthesis.json", synthesis_artifact)
        self.run_cli("render", "--workspace", str(self.workspace))
        self.run_cli("validate", "--workspace", str(self.workspace))

        summary = self.read_json("customer-testing/sessions/S02/summary.json")
        summary["taskOutcomes"][0]["observationIds"] = ["MISSING"]
        self.write_json("customer-testing/sessions/S02/summary.json", summary)
        invalid = self.run_cli(
            "validate", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(invalid.returncode, 1)
        self.assertIn("unknown observation MISSING", invalid.stderr)
        self.assertIn("Synthesis packet is stale for session S02", invalid.stderr)

    def test_packet_generation_refuses_to_exceed_declared_context_budget(self) -> None:
        self.run_cli(
            "init",
            "--title",
            "Budgeted Sprint",
            "--challenge",
            "Test bounded handoffs",
            "--session-context-maximum",
            "1000",
            "--output",
            str(self.workspace),
        )
        self.set_customer_plan(1)
        self.initialise_customer_session("S01", "P01")
        result = self.run_cli(
            "session-packet",
            "--workspace",
            str(self.workspace),
            "--session-id",
            "S01",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("would use", result.stderr)
        self.assertFalse(
            (
                self.workspace
                / "customer-testing"
                / "sessions"
                / "S01"
                / "handoff.md"
            ).exists()
        )
        record = self.read_json("customer-testing/sessions/S01/session.json")
        self.assertEqual(record["packet"]["budgetStatus"], "not-generated")

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
        self.complete_required_assignments("02-qualify")
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
            self.complete_required_assignments(step_id)
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
        self.complete_required_assignments("09-experiment")
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
        self.complete_required_assignments("10-prototype")
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
        self.complete_artifact("10-test-plan")
        self.set_customer_plan(2, "Solo founders")
        self.initialise_customer_session("S01", "P01")
        self.complete_customer_session(
            "S01", "The participant found the primary action without help."
        )
        self.initialise_customer_session("S02", "P02")
        self.complete_customer_session(
            "S02", "The participant hesitated at the confirmation step."
        )
        self.complete_artifact("11-customer-evidence")
        self.complete_required_assignments("11-customer-sessions")
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
            if step_id == "12-synthesis":
                self.run_cli(
                    "synthesis-packet", "--workspace", str(self.workspace)
                )
            self.run_cli(
                "new-artifact",
                "--workspace",
                str(self.workspace),
                "--id",
                artifact_id,
            )
            self.complete_artifact(artifact_id)
            self.complete_required_assignments(step_id)
            if step_id == "12-synthesis":
                synthesis = self.read_json("artifact-data/12-synthesis.json")
                synthesis["evidence"] = [
                    {
                        "status": "Inference",
                        "claim": "TASK-1 was understandable but hesitation varied by session.",
                        "source": "S01/OBS1; S02/OBS1; S01/Q1; S02/Q1",
                    }
                ]
                self.write_json("artifact-data/12-synthesis.json", synthesis)
                self.run_cli("render", "--workspace", str(self.workspace))
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
        outcome = (self.workspace / "artifacts" / "13-outcome.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("Method-fidelity summary", outcome)
        self.assertIn("Method: Adaptive Design Sprint", outcome)

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
        self.complete_required_assignments("02-qualify")
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
        self.assertEqual(len(routed["notApplicableSteps"]), 10)
        self.assertEqual(routed["skippedSteps"], [])

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
