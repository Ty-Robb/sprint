from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_publication.py"
SPEC = importlib.util.spec_from_file_location("check_publication", CHECK_SCRIPT)
assert SPEC and SPEC.loader
CHECK_PUBLICATION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECK_PUBLICATION
SPEC.loader.exec_module(CHECK_PUBLICATION)


class PublicationCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def write(self, relative_path: str, content: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def messages(self, *paths: Path) -> list[str]:
        return [
            finding.message
            for finding in CHECK_PUBLICATION.scan_files(paths, base=self.root)
        ]

    def test_safe_synthetic_content_passes(self) -> None:
        path = self.write(
            "tests/fixtures/person.synthetic.json",
            json.dumps(
                {
                    "fixtureKind": "synthetic",
                    "containsRealCustomerData": False,
                    "participantId": "SYN-P01",
                    "contact": "researcher@example.com",
                }
            ),
        )
        self.assertEqual(self.messages(path), [])

    def test_generated_workspace_and_private_evidence_paths_are_flagged(self) -> None:
        workspace = self.write("design-sprint-demo/sprint-state.json", "{}")
        transcript = self.write("transcripts/session.txt", "Synthetic-looking text")
        messages = self.messages(workspace, transcript)
        self.assertTrue(any("generated sprint" in message for message in messages))
        self.assertIn("private-evidence directory must not be published", messages)

    def test_identifiers_emails_and_secrets_are_flagged(self) -> None:
        identifier_key = "account" + "_id"
        identifier_value = "acct" + "_" + ("7" * 20)
        address = "participant" + "@" + "customer.invalid"
        secret = "sk" + "-" + ("a" * 24)
        path = self.write(
            "candidate.json",
            json.dumps(
                {
                    identifier_key: identifier_value,
                    "contact": address,
                    "credential": secret,
                }
            ),
        )
        messages = self.messages(path)
        self.assertTrue(any("identifier" in message for message in messages))
        self.assertTrue(any("email address" in message for message in messages))
        self.assertTrue(any("secret key" in message for message in messages))

        credential_file = self.write(".env", "SAFE_LOOKING_PLACEHOLDER=true")
        self.assertIn(
            "credential-bearing file must not be published",
            self.messages(credential_file),
        )

    def test_incomplete_usage_record_is_flagged(self) -> None:
        path = self.write(
            "claim.usage-evidence.json",
            json.dumps(
                {
                    "recordType": "public-usage-evidence",
                    "evidenceClassification": "sanitized-observed",
                }
            ),
        )
        messages = self.messages(path)
        self.assertTrue(any("usage-evidence record is missing" in message for message in messages))
        self.assertTrue(any("sanitized source" in message for message in messages))

    def test_repository_publication_check_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CHECK_SCRIPT)],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Publication check passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
