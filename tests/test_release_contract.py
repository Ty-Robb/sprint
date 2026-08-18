from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "run-design-sprint"
REFERENCES = SKILL_DIR / "references"
CONTRACT_PATH = REFERENCES / "release-contract.json"
CONTRACT_SCHEMA = REFERENCES / "schemas" / "release-contract-v1.schema.json"
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "release"
    / "minimal-planning.synthetic.json"
)
SCRIPTS = SKILL_DIR / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCHEMA_VALIDATION = load_module(
    "release_contract_schema_validation", SCRIPTS / "schema_validation.py"
)
WORKSPACE = load_module("release_contract_workspace", SCRIPTS / "sprint_workspace.py")
USAGE_REPORT = load_module("release_contract_usage", SCRIPTS / "usage_report.py")
RELEASE_SMOKE = load_module(
    "release_contract_smoke", REPO_ROOT / "scripts" / "release_smoke_test.py"
)


def schema_version_constants(value: Any) -> set[str]:
    versions: set[str] = set()
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            schema_version = properties.get("schemaVersion")
            if isinstance(schema_version, dict) and isinstance(
                schema_version.get("const"), str
            ):
                versions.add(schema_version["const"])
        for nested in value.values():
            versions.update(schema_version_constants(nested))
    elif isinstance(value, list):
        for nested in value:
            versions.update(schema_version_constants(nested))
    return versions


class ReleaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_contract_is_strict_valid_and_all_policy_paths_exist(self) -> None:
        issues = SCHEMA_VALIDATION.SchemaValidator().validate(
            self.contract, CONTRACT_SCHEMA
        )
        self.assertEqual([str(issue) for issue in issues], [])

        for label, relative_path in self.contract["policies"].items():
            with self.subTest(policy=label):
                self.assertTrue((REPO_ROOT / relative_path).is_file(), relative_path)

    def test_skill_runtime_workflow_and_installer_versions_are_aligned(self) -> None:
        self.assertEqual(self.contract["skill"]["version"], WORKSPACE.SKILL_VERSION)
        self.assertEqual(
            self.contract["skill"]["releaseTag"], f"v{WORKSPACE.SKILL_VERSION}"
        )
        self.assertEqual(
            f"skills@{self.contract['runtime']['installer']['version']}",
            RELEASE_SMOKE.INSTALLER_PACKAGE,
        )
        self.assertEqual(
            self.contract["workflowContracts"],
            {
                "methodProfiles": WORKSPACE.REFERENCE_SCHEMA_VERSION,
                "stepGuidance": WORKSPACE.STEP_GUIDANCE_SCHEMA_VERSION,
                "fidelity": WORKSPACE.FIDELITY_SCHEMA_VERSION,
                "rolePackets": WORKSPACE.ROLE_PACKET_VERSION,
                "testArtifactWorkflow": WORKSPACE.TEST_ARTIFACT_WORKFLOW_VERSION,
            },
        )
        self.assertEqual(
            self.contract["schemaFamilies"]["usage-report"]["current"],
            USAGE_REPORT.REPORT_VERSION,
        )

    def test_every_declared_schema_file_exists_and_declares_its_version(self) -> None:
        for family, item in self.contract["schemaFamilies"].items():
            declared = {item["current"]: item["currentSchema"], **item["migratable"]}
            for version, relative_path in declared.items():
                with self.subTest(family=family, version=version):
                    schema_path = REFERENCES / relative_path
                    self.assertTrue(schema_path.is_file(), relative_path)
                    schema = json.loads(schema_path.read_text(encoding="utf-8"))
                    constants = schema_version_constants(schema)
                    if constants:
                        self.assertIn(version, constants)
                    else:
                        # Two legacy session schemas deliberately leave the
                        # version discriminator to the guarded runtime loader.
                        self.assertIn(version, str(schema.get("title", "")))

    def test_runtime_schema_families_match_the_release_contract(self) -> None:
        declared = self.contract["schemaFamilies"]
        for family, config in WORKSPACE.SCHEMA_FAMILIES.items():
            with self.subTest(family=family):
                self.assertIn(family, declared)
                self.assertEqual(declared[family]["current"], config["current"])
                self.assertEqual(
                    sorted(declared[family]["migratable"]),
                    sorted(config["migratable"]),
                )

    def test_skill_metadata_cli_docs_and_release_fixture_share_one_version(self) -> None:
        version = self.contract["skill"]["version"]
        release_tag = self.contract["skill"]["releaseTag"]
        skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(
            RELEASE_SMOKE.frontmatter_version(SKILL_DIR / "SKILL.md"), version
        )
        self.assertRegex(skill_text, r"(?m)^license: MIT$")
        self.assertRegex(skill_text, r"(?m)^compatibility: .*Python 3\.10-3\.14")

        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "sprint_workspace.py"), "--version"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"sprint_workspace.py {version}")

        fixture = RELEASE_SMOKE.load_fixture(FIXTURE_PATH)
        self.assertEqual(
            fixture["skill"],
            {"name": self.contract["skill"]["name"], "version": version},
        )
        self.assertEqual(
            fixture["expected"]["stateSchemaVersion"],
            self.contract["schemaFamilies"]["workspace-state"]["current"],
        )
        self.assertEqual(
            fixture["expected"]["assignmentManifestSchemaVersion"],
            self.contract["schemaFamilies"]["assignment-manifest"]["current"],
        )
        self.assertEqual(
            fixture["expected"]["siteManifestSchemaVersion"],
            self.contract["schemaFamilies"]["site-manifest"]["current"],
        )

        for relative_path in (
            "README.md",
            "CHANGELOG.md",
            "docs/releases/v1.0.0.md",
            "skills/run-design-sprint/references/release-compatibility.md",
        ):
            with self.subTest(document=relative_path):
                text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn(version, text)
        for relative_path in ("README.md", "docs/releases/v1.0.0.md"):
            text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn(f"skills@{self.contract['runtime']['installer']['version']}", text)
            self.assertIn(f"#{release_tag}", text)

    def test_public_source_guard_requires_an_explicit_github_ref_or_archive(self) -> None:
        self.assertTrue(
            RELEASE_SMOKE.is_public_github_source(
                "https://github.com/Ty-Robb/sprint.git#v1.0.0"
            )
        )
        self.assertTrue(
            RELEASE_SMOKE.is_public_github_source(
                "https://github.com/Ty-Robb/sprint/archive/"
                "9636558e9be51de07745609c35bc3c9c7f35dc5b.tar.gz"
            )
        )
        for source in (
            ".",
            "https://github.com/Ty-Robb/sprint",
            "https://github.com/Ty-Robb/sprint.git",
            "http://github.com/Ty-Robb/sprint.git#v1.0.0",
            "https://github.com/Ty-Robb/sprint/archive/main.tar.gz",
            "https://github.com/Ty-Robb/sprint/archive/9636558.tar.gz",
        ):
            with self.subTest(source=source):
                self.assertFalse(RELEASE_SMOKE.is_public_github_source(source))


if __name__ == "__main__":
    unittest.main()
