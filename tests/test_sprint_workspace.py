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
            "--selected-by",
            "Test Decider",
            "--mode-reason",
            "Run the automated live-mode fixture.",
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

    def current_state_fixture(self, relative_path: str) -> dict:
        return WORKSPACE_MODULE.migrate_workspace_state_v3_to_v4(
            self.fixture_document(relative_path)
        )

    def current_artifact_fixture(self, relative_path: str) -> dict:
        return WORKSPACE_MODULE.migrate_artifact_data_to_v3(
            self.fixture_document(relative_path)
        )

    def complete_artifact(self, artifact_id: str) -> None:
        path = f"artifact-data/{artifact_id}.json"
        data = self.read_json(path)
        data["status"] = "complete"
        data["summary"] = ["Established for the automated test."]
        for section in data["sections"]:
            if (
                artifact_id == "11-customer-evidence"
                and section["title"] == "Session register"
                and section.get("type") == "table"
            ):
                continue
            section["type"] = "paragraphs"
            section["paragraphs"] = [f"{section['title']} established for the test."]
            for key in ("items", "rows", "cards", "body"):
                section.pop(key, None)
        data["nextActions"] = ["Continue to the next sprint step."]
        if artifact_id in {"12-synthesis", "13-outcome"}:
            manifest_path = self.workspace / "customer-testing" / "session-manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                usable = [
                    item
                    for item in manifest["sessions"]
                    if item.get("counted") and item.get("usable")
                ]
                if usable:
                    entry = usable[0]
                    summary = self.read_json(entry["summaryPath"])
                    data["materialFindings"] = [
                        {
                            "id": "FINDING-1",
                            "statement": "The observed task flow caused hesitation.",
                            "directness": "direct-observation",
                            "support": [
                                {
                                    "sessionId": entry["sessionId"],
                                    "participantId": entry["participantId"],
                                    "prototypeVersion": entry["prototypeVersion"],
                                    "questionsVersion": entry["questionsVersion"],
                                    "sourceType": "direct-observation",
                                    "evidenceIds": [summary["observations"][0]["id"]],
                                }
                            ],
                            "contradictions": [],
                            "outliers": [],
                            "limitations": [
                                "Directional observed sample; prevalence is unknown."
                            ],
                            "remainingUncertainty": [
                                "Whether a corrected version removes the hesitation."
                            ],
                            "nextDecision": {
                                "impact": "correct-observed-failure",
                                "action": "Correct the observed hesitation point and retest.",
                                "rationale": "A traceable observation identifies a bounded failure.",
                                "smallestNextLearningAction": "Retest the corrected task with one qualified participant.",
                            },
                        }
                    ]
        if artifact_id == "13-outcome":
            data["outcomeAssessment"] = {
                "processCompleted": "The applicable workflow steps and human gates were completed.",
                "methodAdaptations": "Recorded route, team-model, and customer-testing adaptations remain visible.",
                "evidenceSupports": "The observed sample supports the bounded recorded finding.",
                "evidenceCannotSupport": "It cannot establish prevalence, representativeness, or statistical confidence.",
                "justifiedDecision": "Take the recorded bounded next action.",
                "decisionImpact": "correct-observed-failure",
                "smallestNextLearningAction": "Correct the observed issue and run the next qualified session.",
            }
        self.write_json(path, data)
        self.run_cli("render", "--workspace", str(self.workspace))

    def complete_prototype_brief(
        self,
        *,
        artifact_level: str = "coded-facade",
        tool_route: str = "no-external-tool",
        tool_category: str = "native-repository",
        selected_tool: str = "Repository-native HTML, CSS, and JavaScript",
        requires_external_account: bool = False,
        public: bool = False,
    ) -> None:
        path = "artifact-data/10-prototype-brief.json"
        if not (self.workspace / path).exists():
            self.run_cli(
                "new-artifact",
                "--workspace",
                str(self.workspace),
                "--id",
                "10-prototype-brief",
            )
        data = self.read_json(path)
        now = data["updatedAt"]
        brief = data["prototypeBrief"]
        brief.update(
            {
                "artifactLevel": artifact_level,
                "selection": {
                    "sprintQuestions": ["Can the participant complete the target decision without help?"],
                    "hypothesis": "A qualified participant can understand and complete the target flow.",
                    "rationale": "This is the lowest-cost artifact that preserves the behavior required by the test.",
                    "whyHigherFidelityIsUnnecessary": "Operational systems are outside the approved sprint questions.",
                },
                "customer": {
                    "target": "Qualified solo founders",
                    "entryContext": "Arriving from the approved onboarding entry point",
                },
                "experience": {
                    "task": "Complete the primary onboarding decision.",
                    "journey": ["Enter", "Review", "Choose", "Confirm"],
                    "criticalScenes": [
                        {
                            "id": f"SCENE-{index}",
                            "title": title,
                            "sprintQuestion": "Can the participant complete the target decision without help?",
                            "description": description,
                        }
                        for index, (title, description) in enumerate(
                            (
                                ("Entry", "Participant arrives with realistic context."),
                                ("Review", "Participant interprets the available choices."),
                                ("Decision", "Participant chooses the primary route."),
                                ("Confirmation", "Participant understands the result."),
                            ),
                            start=1,
                        )
                    ],
                },
                "signals": {
                    "success": ["Completes the target task without explanation"],
                    "ambiguity": ["Completes only after a neutral prompt"],
                    "failure": ["Cannot identify the primary action"],
                },
                "realityBoundary": {
                    "mustBeReal": ["Task wording and decision sequence"],
                    "simulated": ["Persistence and downstream processing"],
                    "manuallyOperated": [],
                    "delayed": [],
                    "omitted": ["Account creation and payment"],
                },
                "content": {
                    "required": ["Neutral task copy and realistic choice labels"],
                    "sampleData": ["Synthetic founder workspace data"],
                    "states": {
                        "empty": ["No prior choices"],
                        "loading": ["Short loading state"],
                        "error": ["Recoverable synthetic error"],
                    },
                },
                "environment": {
                    "devices": ["Laptop"],
                    "browsers": ["Current Chromium or Safari"],
                    "languages": ["English"],
                    "accessibility": ["Keyboard operation and visible focus"],
                    "conditions": ["Moderated remote session"],
                },
                "capabilities": {
                    "realData": artifact_level in {"live-mvp", "limited-pilot"},
                    "authentication": False,
                    "payments": False,
                    "integrations": False,
                    "notifications": False,
                    "dataPersistence": artifact_level in {"live-mvp", "limited-pilot"},
                    "backgroundJobs": False,
                    "repeatedUse": False,
                    "notes": ["All non-required capabilities remain simulated."],
                },
                "safety": {
                    "privacy": ["Use synthetic operational data"],
                    "consent": ["Confirm participant consent before the session"],
                    "security": ["Do not include secrets or production access"],
                    "regulatory": [],
                    "dataClassification": "synthetic-only",
                },
                "evidenceCapture": {
                    "methods": ["Moderator notes and structured task outcomes"],
                    "analytics": {
                        "enabled": False,
                        "rationale": "Moderated observation is sufficient and analytics are not approved.",
                    },
                },
                "build": {
                    "timeboxMinutes": 240,
                    "owner": "Prototype Builder",
                    "budgetCeiling": "Zero incremental spend",
                    "approvalPoints": [
                        "Experiment boundary",
                        "Tool and account choice",
                        "Cost, data exposure, and deployment",
                    ],
                },
                "toolSelection": {
                    "route": tool_route,
                    "category": tool_category,
                    "selectedTool": selected_tool,
                    "rationale": "The selected category meets the fidelity need with the least operational exposure.",
                    "constraints": ["No account connection, spend, real customer data, or public deploy"],
                    "criteria": {
                        "timeToTestableArtifact": "Fits the four-hour build timebox",
                        "fidelity": "Supports the approved scenes",
                        "realCapabilities": "Only explicitly listed capabilities are real",
                        "stackCompatibility": "Uses portable files or the approved existing stack",
                        "exportability": "Files remain exportable",
                        "collaborationVersionControl": "Versioned through immutable workspace records",
                        "privacyDataProcessing": "Synthetic data only",
                        "accessibilityDeviceSupport": "Keyboard and target browser support required",
                        "costApproval": "No incremental spend without another approval",
                        "maintainability": "Discardable unless a later product decision adopts it",
                    },
                    "supportingTools": [],
                    "requiresExternalAccount": requires_external_account,
                    "estimatedCost": "Zero incremental spend",
                    "exportSelfHosting": {
                        "available": True,
                        "strategy": "Retain portable source files in the private repository.",
                    },
                },
                "deploymentPlan": {
                    "required": False,
                    "target": "Private local versioned files",
                    "accessModel": "public" if public else "private-local",
                    "public": public,
                    "url": "https://example.test/prototype" if public else None,
                    "expiresAt": None,
                    "cleanupPlan": "Remove any temporary preview after synthesis.",
                    "rollbackPlan": "Return sessions to the prior immutable version.",
                },
            }
        )
        for key in brief["approvals"]:
            requires_approval = key in {"experimentBoundary", "toolChoice"}
            if key == "externalAccount" and requires_external_account:
                requires_approval = True
            if key == "publicDeployment" and public:
                requires_approval = True
            brief["approvals"][key] = {
                "status": "approved" if requires_approval else "not-required",
                "deciderLabel": "Fixture Decider",
                "rationale": "Explicitly decided for this synthetic test fixture.",
                "decidedAt": now,
            }
        data["status"] = "complete"
        data["summary"] = ["The smallest valid artifact and its boundaries are approved."]
        data["nextActions"] = ["Generate the bounded build packet."]
        self.write_json(path, data)
        self.run_cli("render", "--workspace", str(self.workspace))

    def prepare_tested_prototype_version(self) -> None:
        for artifact_id in ("08-experiment", "09-storyboard", "10-test-plan"):
            path = self.workspace / "artifact-data" / f"{artifact_id}.json"
            if not path.exists():
                self.run_cli(
                    "new-artifact",
                    "--workspace",
                    str(self.workspace),
                    "--id",
                    artifact_id,
                )
            if self.read_json(f"artifact-data/{artifact_id}.json")["status"] != "complete":
                self.complete_artifact(artifact_id)
        if not (self.workspace / "artifact-data" / "10-prototype-brief.json").exists():
            self.complete_prototype_brief()
        brief_data = self.read_json("artifact-data/10-prototype-brief.json")
        if brief_data["status"] != "complete":
            self.complete_prototype_brief()
            brief_data = self.read_json("artifact-data/10-prototype-brief.json")
        version_directory = self.workspace / "prototype" / "proto-v1"
        version_directory.mkdir(parents=True, exist_ok=True)
        prototype = version_directory / "index.html"
        if not prototype.exists():
            prototype.write_text(
                "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Prototype</title></head><body><main><h1>Prototype</h1></main></body></html>\n",
                encoding="utf-8",
            )
        context = version_directory / "context.md"
        if not context.exists():
            context.write_text(
                "Test the onboarding decision flow. Mocked actions do not persist.\n",
                encoding="utf-8",
            )
        brief = brief_data["prototypeBrief"]
        if not brief["buildPackets"]:
            self.run_cli(
                "prototype-build-packet",
                "--workspace",
                str(self.workspace),
            )
            brief = self.read_json("artifact-data/10-prototype-brief.json")["prototypeBrief"]
        if not brief["trialRuns"]:
            self.run_cli(
                "prototype-trial",
                "--workspace",
                str(self.workspace),
                "--trial-id",
                "trial-v1",
                "--status",
                "passed",
                "--moderator",
                "Fixture moderator",
                "--prototype",
                "prototype/proto-v1/index.html",
                "--interview-script",
                "artifact-data/10-test-plan.json",
                "--finding",
                "The full interview script and target task ran without explanation.",
            )
            brief = self.read_json("artifact-data/10-prototype-brief.json")["prototypeBrief"]
        if not brief["versions"]:
            self.run_cli(
                "prototype-freeze",
                "--workspace",
                str(self.workspace),
                "--version",
                "proto-v1",
                "--trial-run",
                "trial-v1",
                "--prototype",
                "prototype/proto-v1/index.html",
                "--prototype-context",
                "prototype/proto-v1/context.md",
                "--deployment-target",
                "Private local versioned files",
                "--access-model",
                "private-local",
                "--cleanup-plan",
                "Remove temporary files after synthesis.",
                "--rollback-plan",
                "Use the prior immutable version record.",
            )

    def complete_intake(self) -> None:
        self.complete_artifact("01-sprint-brief")
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "01-intake",
        )

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
        self.complete_intake()

    def set_valid_state_at_customer_step(self) -> None:
        state = self.read_json("sprint-state.json")
        now = state["updatedAt"]
        state.update(
            {
                "route": "full-design-sprint",
                "routeRationale": "The strategic foundation already exists.",
                "selectedConcept": "Approved transition-fixture concept",
                "selectedConceptRationale": "Selected for the transition fixture.",
                "routeHistory": [
                    {
                        "from": "undecided",
                        "to": "full-design-sprint",
                        "reason": "The strategic foundation already exists.",
                        "selectedAt": now,
                    }
                ],
                "notApplicableSteps": ["04-foundation"],
                "completedSteps": [
                    "01-intake",
                    "02-qualify",
                    "03-evidence",
                    "05-map",
                    "06-questions",
                    "07-explore",
                    "08-decide",
                    "09-experiment",
                    "10-prototype",
                ],
                "currentStep": "11-customer-sessions",
                "status": "active",
                "pendingGate": None,
            }
        )
        state["fidelity"]["routeExclusions"] = [
            {
                "step": "04-foundation",
                "reason": "The approved route starts from an existing strategic foundation.",
            }
        ]
        decisions = []
        for gate in state["humanGates"]:
            if gate["id"] == "gate-5":
                continue
            decision_id = f"{gate['id']}-decision-1"
            input_reference = f"{gate['id']}-fixture"
            decision = {
                "id": decision_id,
                "gate": gate["id"],
                "decision": "Approve",
                "deciderLabel": "Fixture Decider",
                "consideredInputs": [
                    {
                        "kind": "record",
                        "reference": input_reference,
                        "digest": WORKSPACE_MODULE.value_digest(
                            "record", input_reference
                        ),
                    }
                ],
                "subject": WORKSPACE_MODULE.decision_subject(
                    state, gate["id"], "Approve"
                ),
                "rationale": "Approved for the transition fixture.",
                "reservations": "",
                "status": "active",
                "decidedAt": now,
            }
            decisions.append(decision)
            gate.update(
                {
                    "status": "complete",
                    "decisionId": decision_id,
                    "decision": decision["decision"],
                    "deciderLabel": decision["deciderLabel"],
                    "rationale": decision["rationale"],
                    "decidedAt": now,
                }
            )
        state["decisions"] = decisions
        self.write_json("sprint-state.json", state)

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
        self.prepare_tested_prototype_version()
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
            "--invited",
            str(planned),
        )

    def initialise_customer_session(
        self,
        session_id: str,
        participant_id: str,
        *,
        session_date: str = "2026-08-17",
        participant_segment: str = "Target segment",
        participant_fit: str = "qualified",
        fit_rationale: str = "Matches the approved behavioural recruitment criteria.",
        prototype_version: str = "proto-v1",
        questions_version: str = "questions-v1",
        activate_versions: bool = False,
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
            "--participant-segment",
            participant_segment,
            "--participant-fit",
            participant_fit,
            "--fit-rationale",
            fit_rationale,
            "--session-date",
            session_date,
            "--prototype-version",
            prototype_version,
            "--questions-version",
            questions_version,
            "--prototype",
            "prototype/proto-v1/index.html",
            "--prototype-context",
            "prototype/proto-v1/context.md",
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
            *(["--activate-versions"] if activate_versions else []),
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

    def complete_customer_session(
        self,
        session_id: str,
        observation: str,
        *,
        protocol_fidelity: str = "consistent",
        usable: bool = True,
        exclusion_reason: str = "",
    ) -> None:
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
            "--protocol-fidelity",
            protocol_fidelity,
            *(
                ["--critical-scenario", "TASK-1", "--usable"]
                if usable
                else ["--exclude-from-evidence", "--exclusion-reason", exclusion_reason]
            ),
            "--usage-unavailable-reason",
            "The test runtime did not expose token or request measurements.",
        )

    def finding_source(
        self, session_id: str, *, source_type: str = "direct-observation"
    ) -> dict:
        manifest = self.read_json("customer-testing/session-manifest.json")
        entry = next(
            item for item in manifest["sessions"] if item["sessionId"] == session_id
        )
        summary = self.read_json(entry["summaryPath"])
        collection = (
            summary["observations"]
            if source_type == "direct-observation"
            else summary["inferences"]
        )
        return {
            "sessionId": session_id,
            "participantId": entry["participantId"],
            "prototypeVersion": entry["prototypeVersion"],
            "questionsVersion": entry["questionsVersion"],
            "sourceType": source_type,
            "evidenceIds": [collection[0]["id"]],
        }

    def material_finding(
        self,
        support_session_ids: list[str],
        *,
        contradiction_session_ids: list[str] | None = None,
        impact: str = "investigate-or-retest",
    ) -> dict:
        return {
            "id": "FINDING-TEST",
            "statement": "Participants encountered the bounded observed failure.",
            "directness": "direct-observation",
            "support": [self.finding_source(value) for value in support_session_ids],
            "contradictions": [
                self.finding_source(value)
                for value in (contradiction_session_ids or [])
            ],
            "outliers": [],
            "limitations": ["Observed sprint sample; prevalence remains unknown."],
            "remainingUncertainty": ["Whether the next prototype corrects the failure."],
            "nextDecision": {
                "impact": impact,
                "action": "Take the bounded action named by this test finding.",
                "rationale": "The action is explicitly tied to traceable observations.",
                "smallestNextLearningAction": "Retest the changed prototype with a qualified participant.",
            },
        }

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

    def test_init_requires_explicit_execution_mode_selector_and_reason(self) -> None:
        result = self.run_cli(
            "init",
            "--title",
            "Unaudited Sprint",
            "--challenge",
            "Attempt an implicit mode selection",
            "--output",
            str(self.workspace),
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--selected-by", result.stderr)
        self.assertIn("--mode-reason", result.stderr)
        self.assertFalse(self.workspace.exists())

    def test_test_artifact_recommendations_cover_required_routes(self) -> None:
        scenarios = {
            "clickable": (
                ("--interaction-required",),
                ("clickable", "interaction-design"),
            ),
            "coded": (
                ("--code-fidelity-required",),
                ("coded-facade", "portable-coded-facade"),
            ),
            "live-mvp": (
                ("--real-behavior-required",),
                ("live-mvp", "ai-assisted-app-builder"),
            ),
            "existing-product": (
                ("--real-behavior-required", "--existing-product"),
                ("live-mvp", "existing-product-slice"),
            ),
            "no-external-tool": (
                ("--interaction-required", "--no-external-tools"),
                ("coded-facade", "no-external-tool"),
            ),
        }
        for label, (arguments, expected) in scenarios.items():
            with self.subTest(label=label):
                result = self.run_cli("prototype-recommend", *arguments)
                recommendation = json.loads(result.stdout)
                self.assertEqual(
                    (recommendation["artifactLevel"], recommendation["toolRoute"]),
                    expected,
                )
                self.assertIn("live URL", recommendation["readinessBoundary"])
                self.assertEqual(len(recommendation["approvalBoundaries"]), 6)

    def test_prototype_lifecycle_requires_approvals_trial_and_immutable_session_links(self) -> None:
        self.initialise()
        self.complete_prototype_brief()
        brief_path = "artifact-data/10-prototype-brief.json"
        data = self.read_json(brief_path)
        data["status"] = "in-review"
        for approval in data["prototypeBrief"]["approvals"].values():
            approval.update(
                {
                    "status": "pending",
                    "deciderLabel": "",
                    "rationale": "",
                    "decidedAt": None,
                }
            )
        self.write_json(brief_path, data)
        self.run_cli("render", "--workspace", str(self.workspace))

        blocked = self.run_cli(
            "artifact-status",
            "--workspace",
            str(self.workspace),
            "--id",
            "10-prototype-brief",
            "--status",
            "complete",
            check=False,
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("requires a human decision", blocked.stderr)
        for boundary in WORKSPACE_MODULE.PROTOTYPE_APPROVAL_BOUNDARIES:
            status = (
                "approved"
                if boundary in {"experiment-boundary", "tool-choice"}
                else "not-required"
            )
            self.run_cli(
                "prototype-approve",
                "--workspace",
                str(self.workspace),
                "--boundary",
                boundary,
                "--status",
                status,
                "--decider",
                "Fixture Decider",
                "--rationale",
                f"Explicit {boundary} decision for the synthetic fixture.",
            )
        self.run_cli(
            "artifact-status",
            "--workspace",
            str(self.workspace),
            "--id",
            "10-prototype-brief",
            "--status",
            "complete",
        )
        public_data = self.read_json(brief_path)
        public_data["prototypeBrief"]["deploymentPlan"].update(
            {
                "required": True,
                "target": "Public preview",
                "accessModel": "public",
                "public": True,
                "url": "https://example.test/public-preview",
            }
        )
        self.write_json(brief_path, public_data)
        unapproved_public = self.run_cli(
            "render", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(unapproved_public.returncode, 2)
        self.assertIn("public deployment requires explicit approval", unapproved_public.stderr)
        public_data["prototypeBrief"]["deploymentPlan"].update(
            {
                "required": False,
                "target": "Private local versioned files",
                "accessModel": "private-local",
                "public": False,
                "url": None,
            }
        )
        self.write_json(brief_path, public_data)
        self.run_cli("render", "--workspace", str(self.workspace))

        for artifact_id in ("08-experiment", "09-storyboard", "10-test-plan"):
            self.run_cli(
                "new-artifact",
                "--workspace",
                str(self.workspace),
                "--id",
                artifact_id,
            )
            self.complete_artifact(artifact_id)
        forbidden = self.workspace / "raw-evidence" / "secret.txt"
        forbidden.parent.mkdir(parents=True)
        forbidden.write_text("synthetic secret marker\n", encoding="utf-8")
        rejected_asset = self.run_cli(
            "prototype-build-packet",
            "--workspace",
            str(self.workspace),
            "--asset",
            "raw-evidence/secret.txt",
            check=False,
        )
        self.assertEqual(rejected_asset.returncode, 2)
        self.assertIn("cannot enter an AI build packet", rejected_asset.stderr)
        self.run_cli(
            "prototype-build-packet", "--workspace", str(self.workspace)
        )
        version_dir = self.workspace / "prototype" / "proto-v1"
        version_dir.mkdir(parents=True)
        (version_dir / "index.html").write_text(
            "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Test</title></head><body><main><h1>Test</h1></main></body></html>\n",
            encoding="utf-8",
        )
        (version_dir / "context.md").write_text(
            "The target task is real; persistence is simulated.\n",
            encoding="utf-8",
        )
        self.run_cli(
            "prototype-trial",
            "--workspace",
            str(self.workspace),
            "--trial-id",
            "failed-trial",
            "--status",
            "failed",
            "--moderator",
            "Fixture moderator",
            "--prototype",
            "prototype/proto-v1/index.html",
            "--interview-script",
            "artifact-data/10-test-plan.json",
            "--finding",
            "The moderator had to explain the primary task.",
        )
        refused_freeze = self.run_cli(
            "prototype-freeze",
            "--workspace",
            str(self.workspace),
            "--version",
            "proto-v1",
            "--trial-run",
            "failed-trial",
            "--prototype",
            "prototype/proto-v1/index.html",
            "--prototype-context",
            "prototype/proto-v1/context.md",
            "--deployment-target",
            "Private local files",
            "--access-model",
            "private-local",
            "--cleanup-plan",
            "Remove after synthesis.",
            "--rollback-plan",
            "Use the previous immutable version.",
            check=False,
        )
        self.assertEqual(refused_freeze.returncode, 2)
        self.assertIn("passed moderated trial", refused_freeze.stderr)
        self.run_cli(
            "prototype-trial",
            "--workspace",
            str(self.workspace),
            "--trial-id",
            "passed-trial",
            "--status",
            "passed",
            "--moderator",
            "Fixture moderator",
            "--prototype",
            "prototype/proto-v1/index.html",
            "--interview-script",
            "artifact-data/10-test-plan.json",
            "--finding",
            "The complete interview script ran without explaining the concept.",
        )
        self.run_cli(
            "prototype-freeze",
            "--workspace",
            str(self.workspace),
            "--version",
            "proto-v1",
            "--trial-run",
            "passed-trial",
            "--prototype",
            "prototype/proto-v1/index.html",
            "--prototype-context",
            "prototype/proto-v1/context.md",
            "--deployment-target",
            "Private local files",
            "--access-model",
            "private-local",
            "--cleanup-plan",
            "Remove after synthesis.",
            "--rollback-plan",
            "Use the previous immutable version.",
        )

        self.set_customer_plan(1)
        self.initialise_customer_session("S01", "P01")
        manifest = self.read_json("customer-testing/session-manifest.json")
        entry = manifest["sessions"][0]
        record = self.read_json(entry["recordPath"])
        summary = self.read_json(entry["summaryPath"])
        self.assertEqual(entry["testedVersion"], record["artifacts"]["testedVersion"])
        self.assertEqual(entry["testedVersion"], summary["testedVersion"])
        tested = self.read_json(entry["testedVersion"]["path"])
        self.assertEqual(
            set(tested["linkedArtifacts"]), {"experiment", "storyboard", "testPlan"}
        )
        self.assertIs(tested["claims"]["customerValidated"], False)
        self.assertIs(tested["claims"]["productionReady"], False)
        dashboard = (self.workspace / "index.html").read_text(encoding="utf-8")
        brief_html = (
            self.workspace / "artifacts" / "10-prototype-brief.html"
        ).read_text(encoding="utf-8")
        self.assertIn("Immutable deployment and version record", dashboard)
        self.assertIn("Provider-neutral tool selection", brief_html)
        self.assertIn("A live URL", brief_html)
        self.run_cli("validate", "--workspace", str(self.workspace))

        (version_dir / "index.html").write_text(
            "<!DOCTYPE html><html lang=\"en\"><body>silently changed</body></html>\n",
            encoding="utf-8",
        )
        drifted = self.run_cli(
            "validate", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(drifted.returncode, 1, drifted.stderr)
        self.assertIn("changed after it was recorded", drifted.stderr)

    def test_published_schemas_accept_representative_valid_fixtures(self) -> None:
        (self.workspace / "artifact-data").mkdir(parents=True)
        self.write_json(
            "sprint-state.json",
            self.current_state_fixture("schemas/valid/workspace-state-v3.synthetic.json"),
        )
        self.write_json(
            "assignment-manifest.json",
            self.fixture_document(
                "schemas/valid/assignment-manifest-v1.synthetic.json"
            ),
        )
        self.write_json(
            "artifact-data/01-sprint-brief.json",
            self.current_artifact_fixture("schemas/valid/artifact-data-v2.synthetic.json"),
        )
        (self.workspace / "customer-testing").mkdir()
        state = self.read_json("sprint-state.json")
        self.write_json(
            "customer-testing/session-manifest.json",
            WORKSPACE_MODULE.initial_session_manifest(
                state["slug"], state["updatedAt"]
            ),
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
            self.current_state_fixture("schemas/invalid/workspace-state-v3.synthetic.json"),
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
            self.current_state_fixture("schemas/valid/workspace-state-v3.synthetic.json"),
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
            self.current_artifact_fixture(
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
        state = self.current_state_fixture(
            "schemas/valid/workspace-state-v3.synthetic.json"
        )
        state["schemaVersion"] = "99.0"
        self.write_json("sprint-state.json", state)

        result = self.run_cli(
            "status", "--workspace", str(self.workspace), check=False
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("$.schemaVersion", result.stderr)
        self.assertIn("unsupported version '99.0'", result.stderr)
        self.assertIn("4.0 (current)", result.stderr)
        self.assertIn("1.0 (migratable)", result.stderr)
        self.assertIn("2.0 (migratable)", result.stderr)

    def test_schema_rejects_bad_formats_and_undeclared_fields(self) -> None:
        self.workspace.mkdir()
        state = self.current_state_fixture(
            "schemas/valid/workspace-state-v3.synthetic.json"
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
        state = self.current_state_fixture(
            "schemas/valid/workspace-state-v3.synthetic.json"
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
        state = self.current_state_fixture(
            "schemas/valid/workspace-state-v3.synthetic.json"
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
        expected_state = self.current_state_fixture(
            "legacy-workspace-expected/state.synthetic.json"
        )
        expected_artifact = self.current_artifact_fixture(
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
        self.assertIn("already uses state schema version 4.0", no_op.stdout)
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

    def test_schema_two_state_migrates_to_explicit_terminal_and_skip_records(self) -> None:
        self.initialise()
        state = self.read_json("sprint-state.json")
        state["schemaVersion"] = "2.0"
        state.pop("terminalState")
        state.pop("skipRecords")
        self.write_json("sprint-state.json", state)

        blocked = self.run_cli(
            "status", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("version '2.0' is legacy", blocked.stderr)

        backup = Path(self.temporary_directory.name) / "schema-two-backup"
        self.run_cli(
            "migrate",
            "--workspace",
            str(self.workspace),
            "--backup",
            str(backup),
        )
        migrated = self.read_json("sprint-state.json")
        self.assertEqual(migrated["schemaVersion"], "4.0")
        self.assertEqual(migrated["terminalState"], "not-terminal")
        self.assertEqual(migrated["skipRecords"], [])
        self.run_cli("render", "--workspace", str(self.workspace))
        self.run_cli("validate", "--workspace", str(self.workspace))

    def test_schema_three_state_migrates_independent_evidence_counts(self) -> None:
        self.initialise()
        state = self.read_json("sprint-state.json")
        state["schemaVersion"] = "3.0"
        for key in (
            "sessionsInvited",
            "sessionsAttempted",
            "sessionsQualified",
            "sessionsExcluded",
            "sessionsUsable",
        ):
            state["customerTesting"].pop(key)
        self.write_json("sprint-state.json", state)

        blocked = self.run_cli(
            "status", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("version '3.0' is legacy", blocked.stderr)

        backup = Path(self.temporary_directory.name) / "schema-three-backup"
        self.run_cli(
            "migrate",
            "--workspace",
            str(self.workspace),
            "--backup",
            str(backup),
        )
        migrated = self.read_json("sprint-state.json")
        self.assertEqual(migrated["schemaVersion"], "4.0")
        self.assertEqual(
            {
                key: migrated["customerTesting"][key]
                for key in (
                    "sessionsInvited",
                    "sessionsAttempted",
                    "sessionsQualified",
                    "sessionsExcluded",
                    "sessionsUsable",
                )
            },
            {
                "sessionsInvited": 0,
                "sessionsAttempted": 0,
                "sessionsQualified": 0,
                "sessionsExcluded": 0,
                "sessionsUsable": 0,
            },
        )
        self.run_cli("render", "--workspace", str(self.workspace))
        self.run_cli("validate", "--workspace", str(self.workspace))

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
        self.assertEqual(state["schemaVersion"], "4.0")
        self.assertEqual(state["methodProfile"], "sprint-book")
        self.assertEqual(state["executionMode"], "live")
        self.assertEqual(
            state["executionModeSelection"]["selectedBy"], "human Decider"
        )
        self.assertEqual(
            state["executionModeSelection"]["reason"],
            "Suitable real customers are available.",
        )
        self.assertTrue(state["executionModeSelection"]["selectedAt"])
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
        self.complete_intake()
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
            "--selected-by",
            "Test Decider",
            "--mode-reason",
            "Exercise the process without customer validation.",
            "--output",
            str(self.workspace),
        )
        self.complete_intake()
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

        errors = WORKSPACE_MODULE.profile_mode_route_errors(
            "sprint-book", "self-test", "focused-design-sprint"
        )
        self.assertTrue(any("incompatible" in item for item in errors))

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
            "--selected-by",
            "Test Decider",
            "--mode-reason",
            "Plan the process without claiming it occurred.",
            "--output",
            str(self.workspace),
        )
        self.complete_intake()
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
            "--selected-by",
            "Test Decider",
            "--mode-reason",
            "Exercise the workflow without customer sessions.",
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
        self.assertIn("cannot label a synthetic", render_result.stderr)

    def test_invalid_cross_mode_transitions_preserve_auditable_history(self) -> None:
        self.initialise()
        self.set_customer_plan(1)
        self.initialise_customer_session("S01", "P01")
        recorded_session = self.run_cli(
            "set-execution-mode",
            "--workspace",
            str(self.workspace),
            "--mode",
            "self-test",
            "--selected-by",
            "Test Decider",
            "--reason",
            "Attempt to relabel a live-session workspace.",
            check=False,
        )
        self.assertEqual(recorded_session.returncode, 2)
        self.assertIn("live customer-session record exists", recorded_session.stderr)
        self.assertEqual(
            self.read_json("sprint-state.json")["executionMode"], "live"
        )

        self.workspace = Path(self.temporary_directory.name) / "early-conversion"
        self.run_cli(
            "init",
            "--title",
            "Convertible Rehearsal",
            "--challenge",
            "Decide whether to start live work",
            "--execution-mode",
            "self-test",
            "--selected-by",
            "Initial Decider",
            "--mode-reason",
            "Check the workflow before beginning the sprint.",
            "--output",
            str(self.workspace),
        )
        self.run_cli(
            "set-execution-mode",
            "--workspace",
            str(self.workspace),
            "--mode",
            "live",
            "--selected-by",
            "Conversion Decider",
            "--reason",
            "Suitable real customers and approval are now available.",
        )
        converted = self.read_json("sprint-state.json")
        self.assertEqual(converted["executionMode"], "live")
        self.assertEqual(
            converted["executionModeSelection"]["selectedBy"],
            "Conversion Decider",
        )
        self.assertEqual(converted["terminalState"], "not-terminal")

        self.complete_intake()
        after_work = self.run_cli(
            "set-execution-mode",
            "--workspace",
            str(self.workspace),
            "--mode",
            "planning-rehearsal",
            "--selected-by",
            "Conversion Decider",
            "--reason",
            "Attempt to relabel completed live work.",
            check=False,
        )
        self.assertEqual(after_work.returncode, 2)
        self.assertIn("cannot change after a step is complete", after_work.stderr)
        self.assertEqual(
            self.read_json("sprint-state.json")["executionMode"], "live"
        )

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
        self.advance_to_qualify()
        self.complete_required_assignments("02-qualify")
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
        self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-1",
            "--decision",
            "Approve full route",
            "--rationale",
            "The legacy record approved this route.",
        )
        state = self.read_json("sprint-state.json")
        state["schemaVersion"] = "1.0"
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
        state["humanGates"][0].pop("decisionId", None)
        state["humanGates"][0].pop("deciderLabel", None)
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
        migration = self.run_cli(
            "migrate",
            "--workspace",
            str(self.workspace),
            "--backup",
            str(backup),
            check=False,
        )
        self.assertEqual(migration.returncode, 0, migration.stderr)
        self.run_cli("render", "--workspace", str(self.workspace))
        migrated = self.read_json("sprint-state.json")
        self.assertEqual(migrated["schemaVersion"], "4.0")
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

    def test_session_quality_migration_requires_honest_reassessment(self) -> None:
        self.initialise()
        self.set_customer_plan(1)
        self.initialise_customer_session("S01", "P01")
        self.complete_customer_session(
            "S01", "The participant encountered the bounded test flow."
        )
        state = self.read_json("sprint-state.json")
        state["schemaVersion"] = "2.0"
        for key in (
            "sessionsInvited",
            "sessionsAttempted",
            "sessionsQualified",
            "sessionsExcluded",
            "sessionsUsable",
        ):
            state["customerTesting"].pop(key)
        self.write_json("sprint-state.json", state)
        manifest = self.read_json("customer-testing/session-manifest.json")
        manifest["schemaVersion"] = "1.0"
        for key in (
            "participantSegment",
            "participantFit",
            "protocolFidelity",
            "criticalScenariosCovered",
            "attempted",
            "usable",
            "exclusionReason",
        ):
            manifest["sessions"][0].pop(key)
        self.write_json("customer-testing/session-manifest.json", manifest)
        record = self.read_json("customer-testing/sessions/S01/session.json")
        record["schemaVersion"] = "1.0"
        record.pop("participant")
        record.pop("evidenceQuality")
        self.write_json("customer-testing/sessions/S01/session.json", record)

        backup = Path(self.temporary_directory.name) / "quality-migration-backup"
        self.run_cli(
            "migrate",
            "--workspace",
            str(self.workspace),
            "--backup",
            str(backup),
        )
        migrated_state = self.read_json("sprint-state.json")
        migrated_manifest = self.read_json("customer-testing/session-manifest.json")
        migrated_record = self.read_json("customer-testing/sessions/S01/session.json")
        self.assertEqual(migrated_state["customerTesting"]["sessionsCompleted"], 1)
        self.assertEqual(migrated_state["customerTesting"]["sessionsUsable"], 0)
        self.assertEqual(migrated_state["customerTesting"]["status"], "partial")
        self.assertFalse(migrated_manifest["sessions"][0]["usable"])
        self.assertFalse(migrated_manifest["sessions"][0]["includeInSynthesis"])
        self.assertEqual(migrated_record["participant"]["fit"], "unassessed")
        self.assertEqual(
            migrated_record["evidenceQuality"]["protocolFidelity"],
            "not-assessed",
        )
        self.run_cli("render", "--workspace", str(self.workspace))
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
            "research-first",
            "--rationale",
            "Initial uncertainty requires a bounded research stage.",
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
            "Approve research-first route",
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

        for step_id, artifact_ids in (
            ("05-map", ("04-journey-map",)),
            ("06-questions", ("05-sprint-questions",)),
            ("07-explore", ("06-solution-directions",)),
            ("08-decide", ("07-decision",)),
        ):
            for artifact_id in artifact_ids:
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
            if step_id == "06-questions":
                self.run_cli(
                    "gate",
                    "--workspace",
                    str(self.workspace),
                    "--gate",
                    "gate-2",
                    "--decision",
                    "Approve target and risks",
                    "--decider",
                    "Founder Decider",
                )
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

    def test_transition_tables_cover_every_route_step_and_route_change(self) -> None:
        step_ids = {step["id"] for step in WORKSPACE_MODULE.STEPS}
        self.assertEqual(
            set(WORKSPACE_MODULE.ROUTE_STEP_TRANSITIONS),
            WORKSPACE_MODULE.ROUTES,
        )
        self.assertEqual(
            set(WORKSPACE_MODULE.ROUTE_TRANSITION_TABLE),
            WORKSPACE_MODULE.ROUTES,
        )
        for route, policy in WORKSPACE_MODULE.ROUTE_STEP_TRANSITIONS.items():
            with self.subTest(route=route):
                self.assertEqual(set(policy), step_ids)
                self.assertLessEqual(
                    set(policy.values()),
                    {
                        WORKSPACE_MODULE.STEP_REQUIRED,
                        WORKSPACE_MODULE.STEP_NOT_APPLICABLE,
                        WORKSPACE_MODULE.STEP_DEFERRED,
                    },
                )
        required_by_route = {
            "undecided": {"01-intake", "02-qualify"},
            "research-first": {
                "01-intake",
                "02-qualify",
                "03-evidence",
            },
            "foundation-plus-design": step_ids,
            "full-design-sprint": step_ids - {"04-foundation"},
            "focused-design-sprint": step_ids - {"04-foundation"},
            "no-sprint": {"01-intake", "02-qualify", "13-outcome"},
        }
        not_applicable_by_route = {
            "undecided": set(),
            "research-first": set(),
            "foundation-plus-design": set(),
            "full-design-sprint": {"04-foundation"},
            "focused-design-sprint": {"04-foundation"},
            "no-sprint": step_ids
            - {"01-intake", "02-qualify", "13-outcome"},
        }
        for route, policy in WORKSPACE_MODULE.ROUTE_STEP_TRANSITIONS.items():
            with self.subTest(exact_policy=route):
                required = {
                    step_id
                    for step_id, disposition in policy.items()
                    if disposition == WORKSPACE_MODULE.STEP_REQUIRED
                }
                not_applicable = {
                    step_id
                    for step_id, disposition in policy.items()
                    if disposition == WORKSPACE_MODULE.STEP_NOT_APPLICABLE
                }
                deferred = {
                    step_id
                    for step_id, disposition in policy.items()
                    if disposition == WORKSPACE_MODULE.STEP_DEFERRED
                }
                self.assertEqual(required, required_by_route[route])
                self.assertEqual(
                    not_applicable, not_applicable_by_route[route]
                )
                self.assertEqual(
                    deferred, step_ids - required - not_applicable
                )
        post_research_no_sprint = {
            "route": "no-sprint",
            "routeHistory": [
                {
                    "from": "undecided",
                    "to": "research-first",
                },
                {
                    "from": "research-first",
                    "to": "no-sprint",
                },
            ],
        }
        effective = WORKSPACE_MODULE.effective_route_step_policy(
            post_research_no_sprint
        )
        self.assertEqual(
            {
                step_id
                for step_id, disposition in effective.items()
                if disposition == WORKSPACE_MODULE.STEP_REQUIRED
            },
            {"01-intake", "02-qualify", "03-evidence", "13-outcome"},
        )

        self.assertEqual(
            WORKSPACE_MODULE.ROUTE_TRANSITION_TABLE["undecided"],
            WORKSPACE_MODULE.ROUTES - {"undecided"},
        )
        self.assertEqual(
            WORKSPACE_MODULE.ROUTE_TRANSITION_TABLE["research-first"],
            {
                "foundation-plus-design",
                "full-design-sprint",
                "focused-design-sprint",
                "no-sprint",
            },
        )

        self.initialise()
        pre_qualification = self.read_json("sprint-state.json")
        self.complete_intake()
        qualification = self.read_json("sprint-state.json")
        for route in sorted(
            WORKSPACE_MODULE.ROUTE_TRANSITION_TABLE["undecided"]
        ):
            with self.subTest(initial_route=route):
                self.assertEqual(
                    WORKSPACE_MODULE.route_change_errors(qualification, route),
                    [],
                )
        self.assertTrue(
            WORKSPACE_MODULE.route_change_errors(qualification, "undecided")
        )
        early_error = WORKSPACE_MODULE.route_change_errors(
            pre_qualification, "full-design-sprint"
        )
        self.assertTrue(any("during 02-qualify" in item for item in early_error))

        research = json.loads(json.dumps(qualification))
        research.update(
            {
                "route": "research-first",
                "routeRationale": "Research is required first.",
                "routeHistory": [
                    {
                        "from": "undecided",
                        "to": "research-first",
                        "reason": "Research is required first.",
                        "selectedAt": research["updatedAt"],
                    }
                ],
                "currentStep": "03-evidence",
                "completedSteps": [
                    "01-intake",
                    "02-qualify",
                    "03-evidence",
                ],
                "status": "waiting-for-human",
            }
        )
        gate_1 = research["humanGates"][0]
        gate_1.update(
            {
                "status": "complete",
                "decision": "Approve research",
                "rationale": "Evidence is needed.",
                "decidedAt": research["updatedAt"],
            }
        )
        for route in sorted(
            WORKSPACE_MODULE.ROUTE_TRANSITION_TABLE["research-first"]
        ):
            with self.subTest(post_research_route=route):
                self.assertEqual(
                    WORKSPACE_MODULE.route_change_errors(research, route), []
                )
        self.assertTrue(
            WORKSPACE_MODULE.route_change_errors(research, "research-first")
        )
        for route in (
            "foundation-plus-design",
            "full-design-sprint",
            "focused-design-sprint",
            "no-sprint",
        ):
            locked = dict(qualification, route=route)
            with self.subTest(locked_route=route):
                self.assertTrue(
                    WORKSPACE_MODULE.route_change_errors(
                        locked, "full-design-sprint"
                    )
                )

    def test_contradictory_route_step_and_gate_histories_are_rejected(self) -> None:
        self.initialise()
        initial = self.read_json("sprint-state.json")

        missing_history = json.loads(json.dumps(initial))
        missing_history.update(
            {
                "route": "full-design-sprint",
                "routeRationale": "Run a design sprint.",
                "notApplicableSteps": ["04-foundation"],
            }
        )
        route_errors = WORKSPACE_MODULE.route_history_errors(missing_history)
        self.assertTrue(
            any("requires routeHistory" in item for item in route_errors)
        )

        discontinuous = json.loads(json.dumps(missing_history))
        discontinuous["routeHistory"] = [
            {
                "from": "research-first",
                "to": "full-design-sprint",
                "reason": "This cannot be the first transition.",
                "selectedAt": initial["updatedAt"],
            }
        ]
        route_errors = WORKSPACE_MODULE.route_history_errors(discontinuous)
        self.assertTrue(
            any("continuous route history" in item for item in route_errors)
        )

        missing_prior_step = json.loads(json.dumps(missing_history))
        missing_prior_step.update(
            {
                "route": "foundation-plus-design",
                "routeHistory": [
                    {
                        "from": "undecided",
                        "to": "foundation-plus-design",
                        "reason": "Build the foundation first.",
                        "selectedAt": initial["updatedAt"],
                    }
                ],
                "notApplicableSteps": [],
                "currentStep": "03-evidence",
                "completedSteps": ["02-qualify"],
            }
        )
        step_errors = WORKSPACE_MODULE.step_history_errors(
            missing_prior_step
        )
        self.assertTrue(
            any("missing required step 01-intake" in item for item in step_errors)
        )

        closed_gate = json.loads(json.dumps(initial))
        closed_gate["humanGates"][0].update(
            {
                "status": "complete",
                "decision": "Approve",
                "rationale": "Impossible fixture.",
                "decidedAt": initial["updatedAt"],
            }
        )
        gate_errors = WORKSPACE_MODULE.gate_history_errors(closed_gate)
        self.assertTrue(
            any("before completed step 02-qualify" in item for item in gate_errors)
        )
        self.assertTrue(
            any("exactly one active decision" in item for item in gate_errors)
        )

    def test_skip_policy_matrix_allows_only_customer_dependent_paths(self) -> None:
        base = {
            "route": "full-design-sprint",
            "routeHistory": [
                {
                    "from": "undecided",
                    "to": "full-design-sprint",
                    "reason": "Use the full route.",
                    "selectedAt": "2026-08-17T10:00:00Z",
                }
            ],
            "executionMode": "live",
            "skippedSteps": [],
            "customerTesting": {
                "status": "not-planned",
                "sessionsPlanned": 0,
                "sessionsCompleted": 0,
            },
        }
        for step in WORKSPACE_MODULE.STEPS:
            with self.subTest(mode="live", step=step["id"]):
                self.assertIsNotNone(
                    WORKSPACE_MODULE.skip_policy_error(base, step["id"])
                )

        blocked = json.loads(json.dumps(base))
        blocked["customerTesting"]["status"] = "blocked"
        self.assertIsNone(
            WORKSPACE_MODULE.skip_policy_error(
                blocked, "11-customer-sessions"
            )
        )
        blocked["skippedSteps"] = ["11-customer-sessions"]
        self.assertIsNone(
            WORKSPACE_MODULE.skip_policy_error(blocked, "12-synthesis")
        )

        for mode in ("self-test", "planning-rehearsal"):
            non_live = json.loads(json.dumps(base))
            non_live["executionMode"] = mode
            with self.subTest(mode=mode, step="11-customer-sessions"):
                self.assertIsNone(
                    WORKSPACE_MODULE.skip_policy_error(
                        non_live, "11-customer-sessions"
                    )
                )
            non_live["skippedSteps"] = ["11-customer-sessions"]
            with self.subTest(mode=mode, step="12-synthesis"):
                self.assertIsNone(
                    WORKSPACE_MODULE.skip_policy_error(
                        non_live, "12-synthesis"
                    )
                )
            for step_id in (
                "01-intake",
                "02-qualify",
                "03-evidence",
                "05-map",
                "06-questions",
                "07-explore",
                "08-decide",
                "09-experiment",
                "10-prototype",
                "13-outcome",
            ):
                with self.subTest(mode=mode, required_step=step_id):
                    self.assertIsNotNone(
                        WORKSPACE_MODULE.skip_policy_error(non_live, step_id)
                    )

        no_sprint = json.loads(json.dumps(base))
        no_sprint["route"] = "no-sprint"
        no_sprint["routeHistory"][0]["to"] = "no-sprint"
        for step in WORKSPACE_MODULE.STEPS:
            with self.subTest(route="no-sprint", step=step["id"]):
                self.assertIsNotNone(
                    WORKSPACE_MODULE.skip_policy_error(
                        no_sprint, step["id"]
                    )
                )

    def test_customer_status_and_manifest_consistency_matrix(self) -> None:
        def customer_state(
            status: str,
            planned: int,
            invited: int,
            attempted: int,
            completed: int,
            qualified: int,
            excluded: int,
            usable: int,
            mode: str = "live",
        ) -> dict:
            state = {
                "executionMode": mode,
                "customerTesting": {
                    "status": status,
                    "target": "Qualified participants" if planned else "",
                    "targetRationale": "Selected for the test." if planned else "",
                    "sessionsPlanned": planned,
                    "sessionsInvited": invited,
                    "sessionsAttempted": attempted,
                    "sessionsCompleted": completed,
                    "sessionsQualified": qualified,
                    "sessionsExcluded": excluded,
                    "sessionsUsable": usable,
                },
            }
            state["terminalState"] = WORKSPACE_MODULE.expected_terminal_state(state)
            return state

        valid = [
            ("not-planned", 0, 0, 0, 0, 0, 0, 0),
            ("not-planned", 5, 0, 0, 0, 0, 0, 0),
            ("recruiting", 3, 2, 0, 0, 1, 1, 0),
            ("scheduled", 3, 3, 0, 0, 3, 0, 0),
            ("in-progress", 3, 3, 1, 0, 2, 0, 0),
            ("in-progress", 3, 3, 2, 1, 2, 0, 1),
            ("complete", 3, 4, 4, 4, 3, 1, 3),
            ("partial", 3, 3, 2, 1, 2, 0, 1),
            ("blocked", 3, 2, 1, 0, 1, 0, 0),
        ]
        for values in valid:
            status = values[0]
            with self.subTest(valid=status):
                self.assertEqual(
                    WORKSPACE_MODULE.customer_testing_errors(
                        customer_state(*values)
                    ),
                    [],
                )

        invalid = [
            ("not-planned", 1, 1, 0, 0, 1, 0, 0),
            ("recruiting", 0, 0, 0, 0, 0, 0, 0),
            ("scheduled", 3, 3, 0, 1, 1, 0, 1),
            ("in-progress", 3, 3, 0, 0, 2, 0, 0),
            ("complete", 3, 3, 3, 3, 2, 1, 2),
            ("partial", 3, 3, 0, 0, 2, 0, 0),
            ("blocked", 3, 3, 3, 3, 3, 0, 3),
            ("partial", 3, 2, 3, 2, 2, 0, 2),
            ("partial", 3, 3, 2, 2, 1, 2, 2),
        ]
        for values in invalid:
            with self.subTest(invalid=values[0], planned=values[1]):
                self.assertTrue(
                    WORKSPACE_MODULE.customer_testing_errors(
                        customer_state(*values)
                    )
                )
        for mode in ("self-test", "planning-rehearsal"):
            self.assertEqual(
                WORKSPACE_MODULE.customer_testing_errors(
                    customer_state("not-planned", 0, 0, 0, 0, 0, 0, 0, mode)
                ),
                [],
            )
            self.assertTrue(
                WORKSPACE_MODULE.customer_testing_errors(
                    customer_state("recruiting", 1, 1, 0, 0, 1, 0, 0, mode)
                )
            )

        self.initialise()
        state = self.read_json("sprint-state.json")
        state["customerTesting"] = {
            "status": "complete",
            "target": "Qualified participants",
            "targetRationale": "Selected for the test.",
            "sessionsPlanned": 1,
            "sessionsInvited": 1,
            "sessionsAttempted": 1,
            "sessionsCompleted": 1,
            "sessionsQualified": 1,
            "sessionsExcluded": 0,
            "sessionsUsable": 1,
        }
        self.write_json("sprint-state.json", state)
        result = self.run_cli(
            "validate", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "customer completed count does not match the session manifest",
            result.stderr,
        )

    def test_terminal_state_matrix_covers_supported_and_impossible_closures(self) -> None:
        all_steps = [step["id"] for step in WORKSPACE_MODULE.STEPS]

        def terminal(
            *,
            route: str,
            mode: str,
            completed: list[str],
            skipped: list[str],
            outcome: str,
            customer_status: str,
            planned: int,
            session_count: int,
            usable_count: int | None = None,
        ) -> dict:
            state = {
                "route": route,
                "routeHistory": [
                    {
                        "from": "undecided",
                        "to": route,
                        "reason": "Terminal matrix fixture.",
                        "selectedAt": "2026-08-17T10:00:00Z",
                    }
                ],
                "executionMode": mode,
                "status": "complete",
                "currentStep": "13-outcome",
                "pendingGate": None,
                "completedSteps": completed,
                "skippedSteps": skipped,
                "outcome": outcome,
                "customerTesting": {
                    "status": customer_status,
                    "sessionsPlanned": planned,
                    "sessionsCompleted": session_count,
                    "sessionsUsable": (
                        session_count if usable_count is None else usable_count
                    ),
                },
            }
            state["terminalState"] = WORKSPACE_MODULE.expected_terminal_state(state)
            return state

        full_steps = [item for item in all_steps if item != "04-foundation"]
        valid = [
            terminal(
                route="full-design-sprint",
                mode="live",
                completed=full_steps,
                skipped=[],
                outcome="Proceed",
                customer_status="complete",
                planned=2,
                session_count=2,
            ),
            terminal(
                route="full-design-sprint",
                mode="live",
                completed=[
                    item
                    for item in full_steps
                    if item not in {"11-customer-sessions", "12-synthesis"}
                ],
                skipped=["11-customer-sessions", "12-synthesis"],
                outcome="Stop",
                customer_status="blocked",
                planned=2,
                session_count=0,
            ),
            terminal(
                route="full-design-sprint",
                mode="self-test",
                completed=[
                    item
                    for item in full_steps
                    if item not in {"11-customer-sessions", "12-synthesis"}
                ],
                skipped=["11-customer-sessions", "12-synthesis"],
                outcome="Investigate",
                customer_status="not-planned",
                planned=0,
                session_count=0,
            ),
            terminal(
                route="full-design-sprint",
                mode="live",
                completed=[item for item in full_steps if item != "12-synthesis"],
                skipped=["12-synthesis"],
                outcome="Investigate",
                customer_status="partial",
                planned=2,
                session_count=1,
                usable_count=0,
            ),
            terminal(
                route="no-sprint",
                mode="live",
                completed=["01-intake", "02-qualify", "13-outcome"],
                skipped=[],
                outcome="Stop",
                customer_status="not-planned",
                planned=0,
                session_count=0,
            ),
        ]
        for index, state in enumerate(valid):
            with self.subTest(valid_terminal=index):
                self.assertEqual(
                    WORKSPACE_MODULE.terminal_state_errors(state), []
                )
        self.assertEqual(valid[0]["terminalState"], "live-customer-tested")
        self.assertEqual(valid[3]["terminalState"], "closed-unvalidated")

        invalid = [
            terminal(
                route="research-first",
                mode="live",
                completed=["01-intake", "02-qualify", "03-evidence", "13-outcome"],
                skipped=[],
                outcome="Stop",
                customer_status="not-planned",
                planned=0,
                session_count=0,
            ),
            terminal(
                route="full-design-sprint",
                mode="self-test",
                completed=full_steps,
                skipped=[],
                outcome="Investigate",
                customer_status="not-planned",
                planned=0,
                session_count=0,
            ),
            terminal(
                route="full-design-sprint",
                mode="self-test",
                completed=[
                    item
                    for item in full_steps
                    if item not in {"11-customer-sessions", "12-synthesis"}
                ],
                skipped=["11-customer-sessions", "12-synthesis"],
                outcome="Proceed",
                customer_status="not-planned",
                planned=0,
                session_count=0,
            ),
            terminal(
                route="full-design-sprint",
                mode="live",
                completed=[
                    item
                    for item in full_steps
                    if item not in {"11-customer-sessions", "12-synthesis"}
                ],
                skipped=["11-customer-sessions", "12-synthesis"],
                outcome="Proceed",
                customer_status="blocked",
                planned=2,
                session_count=0,
            ),
            terminal(
                route="full-design-sprint",
                mode="live",
                completed=[item for item in full_steps if item != "12-synthesis"],
                skipped=["12-synthesis"],
                outcome="Proceed",
                customer_status="partial",
                planned=2,
                session_count=1,
                usable_count=0,
            ),
            terminal(
                route="full-design-sprint",
                mode="live",
                completed=["13-outcome"],
                skipped=[],
                outcome="Stop",
                customer_status="not-planned",
                planned=0,
                session_count=0,
            ),
        ]
        for index, state in enumerate(invalid):
            with self.subTest(invalid_terminal=index):
                self.assertTrue(
                    WORKSPACE_MODULE.terminal_state_errors(state)
                )

        misclassified = json.loads(json.dumps(valid[0]))
        misclassified["terminalState"] = "closed-unvalidated"
        self.assertTrue(
            any(
                "Terminal state must be live-customer-tested" in item
                for item in WORKSPACE_MODULE.terminal_state_errors(misclassified)
            )
        )

    def test_empty_nested_content_never_satisfies_artifact_readiness(self) -> None:
        empty_values = [
            "",
            "   ",
            [],
            {},
            [[], {}],
            {"outer": {"inner": []}},
        ]
        for value in empty_values:
            with self.subTest(value=value):
                self.assertFalse(WORKSPACE_MODULE.nested_has_content(value))
        sections = [
            {"type": "paragraphs", "paragraphs": ["  "]},
            {
                "type": "table",
                "columns": ["Evidence"],
                "rows": [[]],
            },
            {"type": "cards", "cards": []},
            {
                "type": "cards",
                "cards": [
                    {"title": "Structural label", "body": "   "}
                ],
            },
            {
                "type": "key-value",
                "items": [{"label": "Evidence", "value": "  "}],
            },
        ]
        for section in sections:
            with self.subTest(section_type=section["type"]):
                self.assertFalse(
                    WORKSPACE_MODULE.section_has_content(section)
                )

        self.initialise()
        data = self.read_json("artifact-data/01-sprint-brief.json")
        data["status"] = "complete"
        data["summary"] = ["   "]
        for section in data["sections"]:
            section["type"] = "paragraphs"
            section["paragraphs"] = ["   "]
            for key in ("items", "rows", "cards", "body", "columns", "caption"):
                section.pop(key, None)
        self.write_json("artifact-data/01-sprint-brief.json", data)
        result = self.run_cli(
            "render", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("non-empty summary", result.stderr)
        self.assertIn("Required section is still empty", result.stderr)

    def test_gate_closure_requires_complete_not_ready_artifact(self) -> None:
        self.initialise()
        self.complete_intake()
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
        self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-1",
            "--decision",
            "Approve",
            "--rationale",
            "Proceed.",
        )
        for step_id, artifact_id in (
            ("03-evidence", "02-evidence-ledger"),
            ("05-map", "04-journey-map"),
        ):
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
        self.run_cli(
            "new-artifact",
            "--workspace",
            str(self.workspace),
            "--id",
            "05-sprint-questions",
        )
        questions = self.read_json(
            "artifact-data/05-sprint-questions.json"
        )
        questions["status"] = "ready-for-decision"
        questions["summary"] = ["Questions ready for the human gate."]
        for section in questions["sections"]:
            section["paragraphs"] = [
                f"{section['title']} is ready for review."
            ]
        self.write_json(
            "artifact-data/05-sprint-questions.json", questions
        )
        self.run_cli("render", "--workspace", str(self.workspace))
        self.run_cli("validate", "--workspace", str(self.workspace))
        self.complete_required_assignments("06-questions")
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "06-questions",
        )
        self.run_cli("validate", "--workspace", str(self.workspace))
        result = self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-2",
            "--decision",
            "Approve",
            "--rationale",
            "The questions are accepted.",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be complete", result.stderr)
        self.assertIn("ready-for-decision", result.stderr)

    def test_ready_artifact_is_rejected_outside_its_current_gate(self) -> None:
        self.initialise()
        self.run_cli(
            "new-artifact",
            "--workspace",
            str(self.workspace),
            "--id",
            "05-sprint-questions",
        )
        questions = self.read_json(
            "artifact-data/05-sprint-questions.json"
        )
        questions["summary"] = ["Questions prepared too early."]
        for section in questions["sections"]:
            section["paragraphs"] = [
                f"{section['title']} has meaningful content."
            ]
        self.write_json(
            "artifact-data/05-sprint-questions.json", questions
        )
        result = self.run_cli(
            "artifact-status",
            "--workspace",
            str(self.workspace),
            "--id",
            "05-sprint-questions",
            "--status",
            "ready-for-decision",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("only while 06-questions is the current step", result.stderr)

    def test_research_first_can_close_only_after_recorded_final_route(self) -> None:
        self.initialise()
        self.complete_intake()
        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "research-first",
            "--rationale",
            "Evidence is needed before selecting a sprint route.",
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
            "Approve research",
            "--rationale",
            "Reduce problem uncertainty.",
        )
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
        waiting = self.read_json("sprint-state.json")
        waiting["status"] = "complete"
        waiting["outcome"] = "Stop"
        self.assertTrue(
            WORKSPACE_MODULE.terminal_state_errors(waiting)
        )
        self.run_cli(
            "set-route",
            "--workspace",
            str(self.workspace),
            "--route",
            "no-sprint",
            "--rationale",
            "The evidence shows no design sprint is warranted.",
        )
        rerouted = self.read_json("sprint-state.json")
        self.assertEqual(
            [item["to"] for item in rerouted["routeHistory"]],
            ["research-first", "no-sprint"],
        )
        self.assertIn("03-evidence", rerouted["completedSteps"])
        self.assertNotIn("03-evidence", rerouted["notApplicableSteps"])
        self.assertEqual(rerouted["currentStep"], "03-evidence")
        self.assertEqual(rerouted["pendingGate"], "gate-1")
        self.assertEqual(rerouted["decisions"][0]["status"], "superseded")
        self.run_cli(
            "gate",
            "--workspace",
            str(self.workspace),
            "--gate",
            "gate-1",
            "--decision",
            "Approve no-sprint route",
            "--rationale",
            "The evidence shows no design sprint is warranted.",
        )
        approved = self.read_json("sprint-state.json")
        self.assertEqual(approved["currentStep"], "13-outcome")

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

    def test_self_test_closes_as_explicitly_unvalidated_without_customer_evidence(self) -> None:
        self.run_cli(
            "init",
            "--title",
            "Process Self Test",
            "--challenge",
            "Exercise the full sprint workflow safely",
            "--execution-mode",
            "self-test",
            "--selected-by",
            "Test Decider",
            "--mode-reason",
            "Verify the workflow without involving or simulating customers.",
            "--output",
            str(self.workspace),
        )
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
            "Exercise every non-customer stage of the full route.",
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
            "Approve self-test route",
            "--rationale",
            "The process mechanics need rehearsal before live use.",
        )

        steps = [
            ("03-evidence", ["02-evidence-ledger"], None),
            ("05-map", ["04-journey-map"], None),
            ("06-questions", ["05-sprint-questions"], ("gate-2", "Approve rehearsal questions")),
            ("07-explore", ["06-solution-directions"], None),
            ("08-decide", ["07-decision"], ("gate-3", "Select rehearsal direction")),
            ("09-experiment", ["08-experiment", "09-storyboard"], None),
        ]
        for step_id, artifact_ids, gate in steps:
            for artifact_id in artifact_ids:
                self.run_cli(
                    "new-artifact",
                    "--workspace",
                    str(self.workspace),
                    "--id",
                    artifact_id,
                )
                self.complete_artifact(artifact_id)
            if step_id == "09-experiment":
                self.complete_prototype_brief()
            self.complete_required_assignments(step_id)
            self.run_cli(
                "complete-step",
                "--workspace",
                str(self.workspace),
                "--step",
                step_id,
            )
            if gate:
                gate_id, decision = gate
                self.run_cli(
                    "gate",
                    "--workspace",
                    str(self.workspace),
                    "--gate",
                    gate_id,
                    "--decision",
                    decision,
                    "--rationale",
                    "Approve the bounded process-rehearsal output only.",
                )

        self.prepare_tested_prototype_version()
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
            "Approve prototype for process rehearsal only",
            "--rationale",
            "No customer-readiness or validation claim is being made.",
        )

        for step_id, reason in (
            (
                "11-customer-sessions",
                "Self-test mode prohibits live sessions; no customers were simulated or observed.",
            ),
            (
                "12-synthesis",
                "There is no customer evidence to synthesize in this self-test.",
            ),
        ):
            self.run_cli(
                "skip-step",
                "--workspace",
                str(self.workspace),
                "--step",
                step_id,
                "--reason",
                reason,
                "--skipped-by",
                "Test Decider",
            )

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
            "Investigate",
            "--rationale",
            "The process test completed; live customer validation remains future work.",
        )
        self.run_cli("validate", "--workspace", str(self.workspace))

        state = self.read_json("sprint-state.json")
        self.assertEqual(state["status"], "complete")
        self.assertEqual(
            state["terminalState"], "self-test-complete-unvalidated"
        )
        self.assertEqual(
            state["skippedSteps"],
            ["11-customer-sessions", "12-synthesis"],
        )
        self.assertEqual(
            [item["skippedBy"] for item in state["skipRecords"]],
            ["Test Decider", "Test Decider"],
        )
        self.assertTrue(
            all(item["executionMode"] == "self-test" for item in state["skipRecords"])
        )
        self.assertEqual(state["customerTesting"]["sessionsCompleted"], 0)
        self.assertFalse(
            (self.workspace / "artifact-data" / "11-customer-evidence.json").exists()
        )
        for relative in ("index.html", "artifacts/13-outcome.html"):
            rendered = (self.workspace / relative).read_text(encoding="utf-8")
            self.assertIn("UNVALIDATED — self-test complete", rendered)
            self.assertIn("no customer validation was conducted", rendered.lower())
        status = self.run_cli("status", "--workspace", str(self.workspace))
        self.assertIn(
            "Terminal state: self-test-complete-unvalidated", status.stdout
        )
        exported_status = json.loads(
            self.run_cli(
                "status", "--workspace", str(self.workspace), "--json"
            ).stdout
        )
        self.assertEqual(
            exported_status["terminalState"],
            "self-test-complete-unvalidated",
        )
        self.assertEqual(exported_status["executionMode"], "self-test")

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
        self.set_valid_state_at_customer_step()
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
        packet_state = self.read_json("sprint-state.json")
        self.assertEqual(packet_state["customerTesting"]["status"], "scheduled")
        self.assertEqual(packet_state["customerTesting"]["sessionsCompleted"], 0)
        self.run_cli("validate", "--workspace", str(self.workspace))
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
        validation = self.run_cli(
            "validate", "--workspace", str(self.workspace), check=False
        )
        self.assertEqual(validation.returncode, 0, validation.stderr)

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
            "--protocol-fidelity",
            "consistent",
            "--critical-scenario",
            "TASK-1",
            "--usable",
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
            "--selected-by",
            "Test Decider",
            "--mode-reason",
            "Run the automated live-mode fixture.",
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
        self.complete_prototype_brief()
        self.complete_required_assignments("09-experiment")
        self.run_cli(
            "complete-step",
            "--workspace",
            str(self.workspace),
            "--step",
            "09-experiment",
        )

        self.prepare_tested_prototype_version()
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

        for artifact_id in ("11-customer-evidence",):
            self.run_cli(
                "new-artifact",
                "--workspace",
                str(self.workspace),
                "--id",
                artifact_id,
            )
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
        self.assertEqual(state["terminalState"], "live-customer-tested")
        self.assertEqual(state["outcome"], "Proceed")
        dashboard = (self.workspace / "index.html").read_text(encoding="utf-8")
        self.assertIn("100%", dashboard)
        self.assertIn("Live customer testing completed", dashboard)
        outcome = (self.workspace / "artifacts" / "13-outcome.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("Method-fidelity summary", outcome)
        self.assertIn("Method: Adaptive Design Sprint", outcome)
        self.assertIn("Immutable deployment and version record", outcome)
        self.assertIn("A live URL", outcome)

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
        self.assertEqual(state["terminalState"], "closed-unvalidated")
        dashboard = (self.workspace / "index.html").read_text(encoding="utf-8")
        self.assertIn("CLOSED UNVALIDATED", dashboard)
        contradictory = json.loads(json.dumps(state))
        contradictory["outcome"] = "Investigate"
        self.assertTrue(
            any(
                "must match the recorded Gate 5 decision" in item
                for item in WORKSPACE_MODULE.terminal_state_errors(
                    contradictory
                )
            )
        )
        reopen = self.run_cli(
            "next-action",
            "--workspace",
            str(self.workspace),
            "--title",
            "Resume work",
            "--body",
            "This must not reopen the terminal state.",
            "--human-input",
            "Continue.",
            "--status",
            "active",
            check=False,
        )
        self.assertEqual(reopen.returncode, 2)
        self.assertIn("terminal state cannot be reopened", reopen.stderr)

    def test_session_counts_and_descriptive_bands_reach_extended_without_confidence_claims(self) -> None:
        self.run_cli(
            "init",
            "--title",
            "Band Test",
            "--challenge",
            "Keep method coverage separate from confidence",
            "--method-profile",
            "sprint-book",
            "--execution-mode",
            "live",
            "--selected-by",
            "Test Decider",
            "--profile-reason",
            "Use the Sprint-book testing target.",
            "--mode-reason",
            "Qualified real-customer sessions are planned.",
            "--output",
            str(self.workspace),
        )
        self.run_cli(
            "customer",
            "--workspace",
            str(self.workspace),
            "--status",
            "scheduled",
            "--target",
            "Qualified target-segment participants",
            "--planned",
            "5",
            "--invited",
            "7",
        )
        expected_bands = {
            1: "early-limited",
            2: "early-limited",
            3: "partial-directional",
            4: "partial-directional",
            5: "book-target-met",
            6: "extended",
        }
        for index in range(1, 7):
            session_id = f"S{index:02d}"
            participant_id = f"P{index:02d}"
            self.initialise_customer_session(session_id, participant_id)
            self.complete_customer_session(
                session_id,
                f"Participant {participant_id} encountered the same bounded failure.",
            )
            status = json.loads(
                self.run_cli(
                    "status", "--workspace", str(self.workspace), "--json"
                ).stdout
            )
            assessment = status["completionAssessment"]
            self.assertEqual(
                assessment["evidenceStrength"]["band"], expected_bands[index]
            )
            if index < 5:
                self.assertEqual(
                    assessment["methodFidelity"]["status"], "partial"
                )
            if index == 3:
                outcome = WORKSPACE_MODULE.new_artifact_data(
                    "13-outcome",
                    WORKSPACE_MODULE.load_artifact_specs()["13-outcome"],
                )
                outcome["materialFindings"] = [
                    self.material_finding(
                        ["S01", "S02", "S03"],
                        impact="correct-observed-failure",
                    )
                ]
                outcome["outcomeAssessment"]["justifiedDecision"] = (
                    "Correct the observed critical failure and retest."
                )
                outcome["outcomeAssessment"]["decisionImpact"] = (
                    "correct-observed-failure"
                )
                directional = WORKSPACE_MODULE.build_completion_assessment(
                    self.workspace,
                    self.read_json("sprint-state.json"),
                    [(Path("outcome.json"), outcome)],
                )
                self.assertEqual(
                    directional["decisionReadiness"]["status"],
                    "sufficient-to-correct-an-observed-failure",
                )
                self.assertTrue(
                    any("3/5" in item for item in directional["limitations"])
                )
            if index == 5:
                outcome = WORKSPACE_MODULE.new_artifact_data(
                    "13-outcome",
                    WORKSPACE_MODULE.load_artifact_specs()["13-outcome"],
                )
                outcome["materialFindings"] = [
                    self.material_finding(
                        ["S01", "S02", "S03", "S04", "S05"],
                        impact="bounded-reversible-investment",
                    )
                ]
                outcome["outcomeAssessment"]["justifiedDecision"] = (
                    "Make a bounded reversible investment."
                )
                outcome["outcomeAssessment"]["decisionImpact"] = (
                    "bounded-reversible-investment"
                )
                target_met = WORKSPACE_MODULE.build_completion_assessment(
                    self.workspace,
                    self.read_json("sprint-state.json"),
                    [(Path("outcome.json"), outcome)],
                )
                self.assertEqual(
                    target_met["decisionReadiness"]["status"],
                    "sufficient-for-a-bounded-reversible-investment",
                )
                outcome["outcomeAssessment"]["decisionImpact"] = (
                    "defer-large-or-irreversible-investment"
                )
                large_decision = WORKSPACE_MODULE.build_completion_assessment(
                    self.workspace,
                    self.read_json("sprint-state.json"),
                    [(Path("outcome.json"), outcome)],
                )
                self.assertEqual(
                    large_decision["decisionReadiness"]["status"],
                    "insufficient-for-large-or-irreversible-investment",
                )

        counts = assessment["sessionCounts"]
        self.assertEqual(
            counts,
            {
                "planned": 5,
                "invited": 7,
                "attempted": 6,
                "completed": 6,
                "qualified": 6,
                "excluded": 0,
                "usable": 6,
            },
        )
        self.assertEqual(assessment["methodFidelity"]["status"], "adapted-with-documented-substitutions")
        dashboard = (self.workspace / "index.html").read_text(encoding="utf-8")
        self.assertIn("Extended", dashboard)
        self.assertIn("do not establish statistical confidence", dashboard)
        self.assertNotIn("statistically validated", dashboard.lower())

    def test_quality_segments_versions_and_decision_impact_remain_independent(self) -> None:
        self.initialise()
        self.run_cli(
            "customer",
            "--workspace",
            str(self.workspace),
            "--status",
            "scheduled",
            "--target",
            "Qualified participants in the primary segment",
            "--planned",
            "5",
            "--invited",
            "6",
        )
        for index in range(1, 7):
            excluded = index == 6
            second_segment = index >= 4 and not excluded
            version_two = index >= 4
            session_id = f"S{index:02d}"
            self.initialise_customer_session(
                session_id,
                f"P{index:02d}",
                participant_segment=(
                    "Adjacent segment" if second_segment else "Primary segment"
                ),
                participant_fit="excluded" if excluded else "qualified",
                fit_rationale=(
                    "Does not meet the approved behavioural criteria."
                    if excluded
                    else "Meets the approved behavioural criteria."
                ),
                prototype_version="proto-v1",
                questions_version="questions-v2" if version_two else "questions-v1",
                activate_versions=index == 4,
            )
            self.complete_customer_session(
                session_id,
                f"Observed bounded result for P{index:02d}.",
                protocol_fidelity=("minor-deviation" if index == 5 else "consistent"),
                usable=not excluded,
                exclusion_reason=(
                    "Participant was outside the approved target criteria."
                    if excluded
                    else ""
                ),
            )

        finding = self.material_finding(
            ["S01", "S02", "S03", "S04", "S05"],
            impact="bounded-reversible-investment",
        )
        outcome = WORKSPACE_MODULE.new_artifact_data(
            "13-outcome",
            WORKSPACE_MODULE.load_artifact_specs()["13-outcome"],
        )
        outcome["materialFindings"] = [finding]
        outcome["outcomeAssessment"]["justifiedDecision"] = (
            "Make a bounded reversible investment."
        )
        outcome["outcomeAssessment"]["decisionImpact"] = (
            "bounded-reversible-investment"
        )
        state = self.read_json("sprint-state.json")
        assessment = WORKSPACE_MODULE.build_completion_assessment(
            self.workspace, state, [(Path("outcome.json"), outcome)]
        )

        self.assertEqual(assessment["evidenceStrength"]["band"], "book-target-met")
        self.assertEqual(assessment["evidenceStrength"]["quality"], "mixed-segment")
        self.assertTrue(assessment["evidenceStrength"]["mixedVersions"])
        self.assertTrue(assessment["evidenceStrength"]["mixedQuality"])
        self.assertEqual(
            assessment["sessionCounts"],
            {
                "planned": 5,
                "invited": 6,
                "attempted": 6,
                "completed": 6,
                "qualified": 5,
                "excluded": 1,
                "usable": 5,
            },
        )
        self.assertEqual(
            assessment["decisionReadiness"]["status"],
            "sufficient-to-investigate-or-run-another-test",
        )
        self.assertTrue(
            any("multiple customer segments" in item for item in assessment["limitations"])
        )
        finding_errors = WORKSPACE_MODULE.material_finding_errors(
            self.workspace, outcome, assessment
        )
        self.assertTrue(
            any("does not support a bounded investment" in item for item in finding_errors)
        )

    def test_material_findings_validate_provenance_and_render_mixed_evidence_limitations(self) -> None:
        self.initialise()
        self.set_customer_plan(2)
        for index in (1, 2):
            session_id = f"S{index:02d}"
            self.initialise_customer_session(session_id, f"P{index:02d}")
            self.complete_customer_session(
                session_id, f"Observed result for participant P{index:02d}."
            )
        finding = self.material_finding(
            ["S01"],
            contradiction_session_ids=["S02"],
            impact="correct-observed-failure",
        )
        synthesis = WORKSPACE_MODULE.new_artifact_data(
            "12-synthesis",
            WORKSPACE_MODULE.load_artifact_specs()["12-synthesis"],
        )
        synthesis["materialFindings"] = [finding]
        state = self.read_json("sprint-state.json")
        documents = [(Path("synthesis.json"), synthesis)]
        assessment = WORKSPACE_MODULE.build_completion_assessment(
            self.workspace, state, documents
        )

        self.assertEqual(
            WORKSPACE_MODULE.material_finding_errors(
                self.workspace, synthesis, assessment
            ),
            [],
        )
        rendered = WORKSPACE_MODULE.render_material_findings(assessment)
        self.assertIn("1/2 usable support", rendered)
        self.assertIn("P01 / S01", rendered)
        self.assertIn("prototype proto-v1", rendered)
        self.assertIn("contradictory provenance record", rendered)
        self.assertIn("prevalence", rendered)
        self.assertEqual(
            assessment["decisionReadiness"]["status"],
            "sufficient-to-correct-an-observed-failure",
        )

        early_investment = json.loads(json.dumps(synthesis))
        early_investment["materialFindings"][0]["nextDecision"]["impact"] = (
            "bounded-reversible-investment"
        )
        early_assessment = WORKSPACE_MODULE.build_completion_assessment(
            self.workspace, state, [(Path("synthesis.json"), early_investment)]
        )
        self.assertEqual(
            early_assessment["decisionReadiness"]["status"],
            "sufficient-to-investigate-or-run-another-test",
        )
        self.assertTrue(
            any(
                "does not support a bounded investment" in item
                for item in WORKSPACE_MODULE.material_finding_errors(
                    self.workspace, early_investment, early_assessment
                )
            )
        )

        tampered = json.loads(json.dumps(synthesis))
        tampered["materialFindings"][0]["support"][0]["participantId"] = "P99"
        tampered["materialFindings"][0]["support"][0]["prototypeVersion"] = "proto-v99"
        errors = WORKSPACE_MODULE.material_finding_errors(
            self.workspace, tampered, assessment
        )
        self.assertTrue(any("participantId does not match" in item for item in errors))
        self.assertTrue(any("prototypeVersion does not match" in item for item in errors))

    def test_non_live_modes_keep_fidelity_evidence_and_readiness_unvalidated(self) -> None:
        for mode in ("self-test", "planning-rehearsal"):
            workspace = Path(self.temporary_directory.name) / mode
            self.run_cli(
                "init",
                "--title",
                f"{mode} assessment",
                "--challenge",
                "Exercise the four-dimensional model",
                "--execution-mode",
                mode,
                "--selected-by",
                "Test Decider",
                "--mode-reason",
                "Exercise the explicit non-live assessment boundary.",
                "--output",
                str(workspace),
            )
            payload = json.loads(
                self.run_cli(
                    "status", "--workspace", str(workspace), "--json"
                ).stdout
            )["completionAssessment"]
            with self.subTest(mode=mode):
                self.assertEqual(
                    payload["methodFidelity"]["status"], "self-test-rehearsal"
                )
                self.assertEqual(payload["evidenceStrength"]["band"], "not-tested")
                self.assertEqual(
                    payload["decisionReadiness"]["status"],
                    "insufficient-to-decide",
                )
                self.assertEqual(payload["sessionCounts"]["usable"], 0)


if __name__ == "__main__":
    unittest.main()
