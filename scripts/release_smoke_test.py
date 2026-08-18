#!/usr/bin/env python3
"""Verify clean skill installation, discovery, and a synthetic workspace flow."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "release"
    / "minimal-planning.synthetic.json"
)
INSTALLER_PACKAGE = "skills@1.5.22"
PUBLIC_GITHUB_HOST = "github.com"


class SmokeTestError(RuntimeError):
    """A release installation or runtime assertion failed."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SmokeTestError(f"Could not read JSON fixture {path}: {error}") from error
    if not isinstance(value, dict):
        raise SmokeTestError(f"Expected a JSON object in {path}")
    return value


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = load_json(path)
    if fixture.get("fixtureKind") != "synthetic":
        raise SmokeTestError("Release fixture must declare fixtureKind as synthetic")
    if fixture.get("containsRealCustomerData") is not False:
        raise SmokeTestError("Release fixture must declare containsRealCustomerData as false")
    for key in ("fixtureVersion", "skill", "workspace", "expected"):
        if key not in fixture:
            raise SmokeTestError(f"Release fixture is missing {key!r}")
    return fixture


def is_public_github_ref(source: str) -> bool:
    repository, marker, ref = source.partition("#")
    parsed = urlsplit(repository)
    return (
        marker == "#"
        and bool(ref)
        and parsed.scheme == "https"
        and parsed.hostname == PUBLIC_GITHUB_HOST
        and parsed.path.endswith(".git")
    )


def display_command(command: Sequence[str]) -> str:
    return " ".join(json.dumps(part) if re.search(r"\s", part) else part for part in command)


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SmokeTestError(
            f"Command failed ({result.returncode}): {display_command(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def json_from_output(output: str, label: str) -> Any:
    stripped = output.strip()
    candidates = sorted(
        (start, opening, closing)
        for opening, closing in (("[", "]"), ("{", "}"))
        if (start := stripped.find(opening)) >= 0
    )
    for start, opening, closing in candidates:
        end = stripped.rfind(closing)
        if end >= start:
            try:
                return json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise SmokeTestError(f"{label} did not emit parseable JSON:\n{output}")


def frontmatter_version(skill_file: Path) -> str:
    text = skill_file.read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^metadata:\s*\n(?:^[ \t]+[^\n]+\n)*?^[ \t]+version:\s*[\"']?([^\"'\s]+)",
        text,
    )
    if not match:
        raise SmokeTestError(f"Could not find metadata.version in {skill_file}")
    return match.group(1)


def validate_installed_contract(skill_directory: Path) -> dict[str, Any]:
    contract_path = skill_directory / "references" / "release-contract.json"
    schema_path = (
        skill_directory
        / "references"
        / "schemas"
        / "release-contract-v1.schema.json"
    )
    validator_path = skill_directory / "scripts" / "schema_validation.py"
    spec = importlib.util.spec_from_file_location(
        "release_smoke_schema_validation", validator_path
    )
    if spec is None or spec.loader is None:
        raise SmokeTestError(f"Could not load installed validator {validator_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    contract = load_json(contract_path)
    issues = module.SchemaValidator().validate(contract, schema_path)
    if issues:
        raise SmokeTestError(
            "Installed release contract is invalid:\n"
            + "\n".join(f"- {issue}" for issue in issues)
        )
    return contract


def verify_release(source: str, fixture_path: Path, require_public_source: bool) -> None:
    if require_public_source and not is_public_github_ref(source):
        raise SmokeTestError(
            "--require-public-source needs an HTTPS GitHub .git URL with an explicit #ref"
        )
    if not is_public_github_ref(source):
        local_source = Path(source).expanduser()
        if local_source.exists():
            source = str(local_source.resolve())
    fixture = load_fixture(fixture_path)
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx is None:
        raise SmokeTestError("npx is required for clean install verification")

    environment = os.environ.copy()
    environment.update(
        {
            "CI": "true",
            "NO_COLOR": "1",
            "FORCE_COLOR": "0",
            "npm_config_update_notifier": "false",
        }
    )

    with tempfile.TemporaryDirectory(prefix="sprint-release-smoke-") as directory:
        project = Path(directory) / "project"
        project.mkdir()
        skill_name = fixture["skill"]["name"]
        expected_version = fixture["skill"]["version"]
        agent = "codex"
        install_command = [
            npx,
            "--yes",
            INSTALLER_PACKAGE,
            "add",
            source,
            "--skill",
            skill_name,
            "--agent",
            agent,
            "--copy",
            "--yes",
        ]
        run(install_command, cwd=project, environment=environment)

        discovered = json_from_output(
            run(
                [npx, "--yes", INSTALLER_PACKAGE, "list", "--json"],
                cwd=project,
                environment=environment,
            ).stdout,
            "skills list",
        )
        if not isinstance(discovered, list) or not any(
            isinstance(item, dict) and item.get("name") == skill_name
            for item in discovered
        ):
            raise SmokeTestError(f"Installed skill {skill_name!r} was not discovered")

        skill_directory = project / ".agents" / "skills" / skill_name
        for relative in fixture["expected"]["requiredSkillFiles"]:
            path = skill_directory / relative
            if not path.is_file():
                raise SmokeTestError(f"Installed skill is missing {relative}")

        metadata_version = frontmatter_version(skill_directory / "SKILL.md")
        contract = validate_installed_contract(skill_directory)
        if metadata_version != expected_version:
            raise SmokeTestError(
                f"Skill metadata version {metadata_version!r} does not match fixture {expected_version!r}"
            )
        if contract["skill"]["version"] != expected_version:
            raise SmokeTestError("Installed release contract and fixture versions differ")
        installer = contract["runtime"]["installer"]
        if f"{installer['package']}@{installer['version']}" != INSTALLER_PACKAGE:
            raise SmokeTestError("Smoke-test installer and installed release contract differ")

        engine = skill_directory / "scripts" / "sprint_workspace.py"
        version_result = run(
            [sys.executable, str(engine), "--version"],
            cwd=project,
            environment=environment,
        )
        expected_version_output = f"sprint_workspace.py {expected_version}"
        if version_result.stdout.strip() != expected_version_output:
            raise SmokeTestError(
                f"Unexpected runtime version output: {version_result.stdout.strip()!r}"
            )

        workspace = project / "synthetic-workspace"
        workspace_input = fixture["workspace"]
        run(
            [
                sys.executable,
                str(engine),
                "init",
                "--title",
                workspace_input["title"],
                "--challenge",
                workspace_input["challenge"],
                "--method-profile",
                workspace_input["methodProfile"],
                "--execution-mode",
                workspace_input["executionMode"],
                "--selected-by",
                workspace_input["selectedBy"],
                "--profile-reason",
                workspace_input["profileReason"],
                "--mode-reason",
                workspace_input["modeReason"],
                "--output",
                str(workspace),
            ],
            cwd=project,
            environment=environment,
        )
        for relative in fixture["expected"]["generatedFiles"]:
            if not (workspace / relative).is_file():
                raise SmokeTestError(f"Synthetic workspace is missing {relative}")

        state = load_json(workspace / "sprint-state.json")
        assignment_manifest = load_json(workspace / "assignment-manifest.json")
        site_manifest = load_json(workspace / "site-manifest.json")
        expected = fixture["expected"]
        assertions = {
            "state schema": (state.get("schemaVersion"), expected["stateSchemaVersion"]),
            "assignment schema": (
                assignment_manifest.get("schemaVersion"),
                expected["assignmentManifestSchemaVersion"],
            ),
            "site schema": (
                site_manifest.get("schemaVersion"),
                expected["siteManifestSchemaVersion"],
            ),
            "current step": (state.get("currentStep"), expected["currentStep"]),
            "status": (state.get("status"), expected["status"]),
            "execution mode": (
                state.get("executionMode"),
                workspace_input["executionMode"],
            ),
        }
        for label, (actual, wanted) in assertions.items():
            if actual != wanted:
                raise SmokeTestError(f"Unexpected {label}: {actual!r}; expected {wanted!r}")

        status = json_from_output(
            run(
                [sys.executable, str(engine), "status", "--workspace", str(workspace), "--json"],
                cwd=project,
                environment=environment,
            ).stdout,
            "workspace status",
        )
        if status.get("currentStep") != expected["currentStep"]:
            raise SmokeTestError("Status output did not discover the initialized workspace")
        guidance = json_from_output(
            run(
                [sys.executable, str(engine), "guidance", "--workspace", str(workspace), "--json"],
                cwd=project,
                environment=environment,
            ).stdout,
            "workspace guidance",
        )
        if guidance.get("step") != expected["currentStep"]:
            raise SmokeTestError("Guidance output did not resolve the initial step")

        run(
            [sys.executable, str(engine), "render", "--workspace", str(workspace), "--check"],
            cwd=project,
            environment=environment,
        )
        run(
            [sys.executable, str(engine), "validate", "--workspace", str(workspace)],
            cwd=project,
            environment=environment,
        )

    source_kind = "public ref" if is_public_github_ref(source) else "local source"
    print(
        f"Release smoke test passed for {skill_name} {expected_version} "
        f"from {source_kind}: install, discovery, init, status, guidance, render, validate"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run clean install/discovery and synthetic runtime release verification."
    )
    parser.add_argument("--source", required=True, help="Local skill repository or public Git ref")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Synthetic end-to-end fixture",
    )
    parser.add_argument(
        "--require-public-source",
        action="store_true",
        help="Reject local paths and require an HTTPS github.com .git URL with #ref",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        verify_release(args.source, args.fixture.resolve(), args.require_public_source)
    except SmokeTestError as error:
        raise SystemExit(f"Release smoke test failed: {error}") from error


if __name__ == "__main__":
    main()
