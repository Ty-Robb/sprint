#!/usr/bin/env python3
"""Build a synthetic generated site covering every artifact and section renderer."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "skills" / "run-design-sprint" / "scripts"
ENGINE_PATH = SCRIPT_DIR / "sprint_workspace.py"
FIXTURE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "ci" / "adversarial-content.synthetic.json"
)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import sprint_workspace as ENGINE  # noqa: E402


SECTION_TYPES = (
    "paragraphs",
    "list",
    "ordered-list",
    "table",
    "cards",
    "key-value",
)
EVIDENCE_STATUSES = (
    "Assumption",
    "Inference",
    "Decision",
    "Unknown",
    "Synthetic rehearsal",
)


class FixtureError(RuntimeError):
    """The public synthetic fixture or generated site violated its test contract."""


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if fixture.get("fixtureKind") != "synthetic":
        raise FixtureError("CI site fixture must declare fixtureKind as synthetic")
    if fixture.get("containsRealCustomerData") is not False:
        raise FixtureError(
            "CI site fixture must declare containsRealCustomerData as false"
        )
    return fixture


def run_engine(*arguments: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(ENGINE_PATH), *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FixtureError(
            f"Workspace command failed ({result.returncode}): {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def section_payload(
    title: str,
    section_type: str,
    escaped_text: str,
    long_token: str,
) -> dict[str, Any]:
    common = {
        "title": title,
        "eyebrow": f"Synthetic {section_type} renderer",
        "type": section_type,
    }
    value = f"{escaped_text} Oversized token: {long_token}"
    if section_type == "paragraphs":
        return {**common, "paragraphs": [value, "Second synthetic paragraph."]}
    if section_type in {"list", "ordered-list"}:
        return {**common, "items": [value, "Empty-edge behavior is tested separately."]}
    if section_type == "table":
        return {
            **common,
            "caption": f"{title} synthetic comparison",
            "columns": ["Synthetic source", "Escaped content", "Oversized content"],
            "rows": [["SYN-01", escaped_text, long_token]],
        }
    if section_type == "cards":
        return {
            **common,
            "cards": [
                {
                    "title": "Synthetic adversarial card",
                    "body": value,
                    "status": "Synthetic rehearsal",
                },
                {
                    "title": "Synthetic empty-edge companion",
                    "body": "Representative card content.",
                    "status": "Unknown",
                },
            ],
        }
    if section_type == "key-value":
        return {
            **common,
            "items": [
                {"label": "Escaped synthetic value", "value": escaped_text},
                {"label": "Oversized synthetic value", "value": long_token},
            ],
        }
    raise FixtureError(f"Unsupported synthetic section type: {section_type}")


def build_site(output: Path, fixture_path: Path = FIXTURE_PATH) -> Path:
    fixture = load_fixture(fixture_path)
    if output.exists():
        raise FixtureError(f"Synthetic site output already exists: {output}")
    long_token = fixture["longTokenSeed"] * int(fixture["longTokenRepeats"])
    title = fixture["titlePrefix"] + fixture["longTokenSeed"] * 5
    run_engine(
        "init",
        "--title",
        title,
        "--challenge",
        fixture["challenge"],
        "--method-profile",
        "adaptive-design-sprint",
        "--execution-mode",
        "planning-rehearsal",
        "--selected-by",
        "Synthetic CI Decider",
        "--profile-reason",
        "Exercise every generated renderer with a synthetic adaptive fixture.",
        "--mode-reason",
        "This fixture rehearses rendering and never represents customer evidence.",
        "--output",
        str(output),
    )

    state = ENGINE.load_state(output)
    specs = ENGINE.load_artifact_specs()
    rendered_types: set[str] = set()
    section_index = 0
    for artifact_index, (artifact_id, spec) in enumerate(specs.items()):
        path = output / "artifact-data" / f"{artifact_id}.json"
        if path.exists():
            data = ENGINE.load_artifact_data(path)
        else:
            data = ENGINE.new_artifact_data(
                artifact_id,
                spec,
                timestamp=state["updatedAt"],
                state=state,
            )
        sections = []
        for required_title in spec["requiredSections"]:
            section_type = SECTION_TYPES[section_index % len(SECTION_TYPES)]
            section_index += 1
            rendered_types.add(section_type)
            sections.append(
                section_payload(
                    required_title,
                    section_type,
                    fixture["escapedText"],
                    long_token,
                )
            )
        data.update(
            {
                "status": "in-review",
                "summary": [
                    f"Synthetic representative content for {spec['title']}.",
                    f"Escaping contract: {fixture['escapedText']}",
                ],
                "sections": sections,
                "evidence": [
                    {
                        "status": EVIDENCE_STATUSES[
                            artifact_index % len(EVIDENCE_STATUSES)
                        ],
                        "claim": "Invented evidence-label content for renderer verification.",
                        "source": "Synthetic CI fixture SYN-01",
                        "sourceUrl": "https://example.com/synthetic-ci-source",
                        "date": "2026-08-18",
                    }
                ],
                "unknowns": [
                    "No customer conclusion may be drawn from this generated fixture."
                ],
                "nextActions": [
                    "Use this page only to verify rendering, navigation, and accessibility."
                ],
            }
        )
        if artifact_id == "13-outcome":
            data["outcomeAssessment"] = {
                "processCompleted": "The synthetic render exercise generated every artifact type.",
                "methodAdaptations": "This is an automated planning rehearsal.",
                "evidenceSupports": "Only renderer and navigation behavior are exercised.",
                "evidenceCannotSupport": "No product, customer, or market conclusion.",
                "justifiedDecision": "Retain this fixture solely as a CI contract.",
                "decisionImpact": "investigate-or-retest",
                "smallestNextLearningAction": "Run the generated-site checks.",
            }
        ENGINE.require_valid_schema(data, "artifact-data", path)
        ENGINE.write_json(path, data)

    if rendered_types != set(SECTION_TYPES):
        raise FixtureError(
            "Synthetic site did not exercise every section renderer: "
            + ", ".join(sorted(set(SECTION_TYPES) - rendered_types))
        )
    run_engine("render", "--workspace", str(output))
    run_engine("render", "--workspace", str(output), "--check")
    run_engine("validate", "--workspace", str(output))

    manifest = ENGINE.read_json(output / ENGINE.SITE_MANIFEST_FILENAME)
    expected_pages = {"home", *specs}
    actual_pages = {page["id"] for page in manifest["pages"]}
    if actual_pages != expected_pages:
        raise FixtureError(
            f"Generated page matrix differs: {sorted(actual_pages)}; "
            f"expected {sorted(expected_pages)}"
        )
    crawl_errors = ENGINE.site_crawl_errors(output, manifest)
    if crawl_errors:
        raise FixtureError("Generated site crawl failed:\n" + "\n".join(crawl_errors))
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the privacy-safe generated-site CI fixture."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        output = build_site(args.output.resolve(), args.fixture.resolve())
    except (FixtureError, OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"Synthetic CI site generation failed: {error}") from error
    print(f"Synthetic CI site generated at {output}")


if __name__ == "__main__":
    main()
