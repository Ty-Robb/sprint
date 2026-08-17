#!/usr/bin/env python3
"""Warn about likely private evidence before files are published."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS_DIR = REPO_ROOT / "skills" / "run-design-sprint" / "scripts"
if str(SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS_DIR))

from schema_validation import SchemaValidator, strict_json_loads


USAGE_EVIDENCE_SCHEMA = (
    REPO_ROOT
    / "skills"
    / "run-design-sprint"
    / "references"
    / "schemas"
    / "usage-evidence-v1.schema.json"
)
USAGE_EVIDENCE_VERSION = "1.0"
SCHEMA_VALIDATOR = SchemaValidator()

PRIVATE_DIRECTORY_NAMES = {
    "account-evidence",
    "participant-data",
    "participant-identities",
    "private-evidence",
    "raw-evidence",
    "recordings",
    "transcripts",
}
PRIVATE_PATH_SEQUENCES = {
    ("usage-evidence", "private"),
}
PRIVATE_SESSION_PATH_SEQUENCES = {
    ("customer-testing", "sessions"),
    ("customer-testing", "synthesis"),
}
PRIVATE_MEDIA_MARKERS = {
    "account-screenshot",
    "billing-dashboard",
    "plan-screenshot",
    "usage-dashboard",
}
GENERATED_WORKSPACE_PREFIXES = (
    "design-sprint-",
    "generated-sprint-",
)
SAFE_EMAIL_DOMAINS = {"example.com", "example.net", "example.org"}
SAFE_IDENTIFIER_MARKERS = {
    "example",
    "not-collected",
    "placeholder",
    "redacted",
    "removed",
    "synthetic",
    "test",
    "unknown",
}
TEXT_SUFFIXES = {
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])([A-Z0-9._%+-]+)@([A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])",
    re.IGNORECASE,
)
IDENTIFIER_PATTERN = re.compile(
    r'''(?ix)
    ["']?
    (?:
      account[_-]?(?:id|identifier)
      |customer[_-]?id
      |org(?:anization)?[_-]?id
      |project[_-]?id
      |request[_-]?id
      |subscription[_-]?id
      |user[_-]?id
      |workspace[_-]?id
    )
    ["']?\s*[:=]\s*["']([^"'\r\n]+)["']
    ''',
)
SECRET_PATTERNS = (
    ("OpenAI-style secret key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("GitHub token", re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[A-Z0-9]{16}\b")),
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
)

@dataclass(frozen=True)
class Finding:
    path: Path
    message: str
    line: int | None = None

    def display(self, base: Path) -> str:
        try:
            name = self.path.resolve().relative_to(base.resolve())
        except ValueError:
            name = self.path
        location = f"{name}:{self.line}" if self.line else str(name)
        return f"{location}: {self.message}"


def tracked_and_untracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item.decode() for item in result.stdout.split(b"\0") if item]


def files_below(paths: Iterable[Path]) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved.is_dir():
            files.update(
                candidate
                for candidate in resolved.rglob("*")
                if candidate.is_file() and ".git" not in candidate.parts
            )
        elif resolved.is_file():
            files.add(resolved)
    return sorted(files)


def relative_parts(path: Path, base: Path) -> tuple[str, ...]:
    try:
        relative = path.resolve().relative_to(base.resolve())
    except ValueError:
        relative = path.resolve()
    return tuple(part.lower() for part in relative.parts)


def path_findings(path: Path, base: Path) -> list[Finding]:
    parts = relative_parts(path, base)
    findings: list[Finding] = []
    if set(parts) & PRIVATE_DIRECTORY_NAMES:
        findings.append(Finding(path, "private-evidence directory must not be published"))
    for sequence in PRIVATE_PATH_SEQUENCES:
        if any(parts[index : index + len(sequence)] == sequence for index in range(len(parts))):
            findings.append(Finding(path, "private usage/account evidence must not be published"))
    for sequence in PRIVATE_SESSION_PATH_SEQUENCES:
        if any(parts[index : index + len(sequence)] == sequence for index in range(len(parts))):
            findings.append(Finding(path, "private customer-session material must not be published"))
    if any(part.startswith(GENERATED_WORKSPACE_PREFIXES) for part in parts[:-1]):
        findings.append(Finding(path, "generated sprint workspace must remain private"))
    if path.name.lower() == "sprint-state.json":
        findings.append(Finding(path, "generated sprint state must remain private"))
    if path.name.lower() == "session-manifest.json":
        findings.append(Finding(path, "generated customer-session manifest must remain private"))
    if (
        path.name == ".env"
        or (path.name.startswith(".env.") and path.name != ".env.example")
        or path.suffix.lower() in {".key", ".pem"}
    ):
        findings.append(Finding(path, "credential-bearing file must not be published"))
    stem = path.stem.lower()
    if any(marker in stem for marker in PRIVATE_MEDIA_MARKERS):
        findings.append(Finding(path, "likely private account or dashboard capture"))
    return findings


def safe_identifier(value: str) -> bool:
    normalized = value.strip().lower().replace("_", "-")
    return not normalized or any(marker in normalized for marker in SAFE_IDENTIFIER_MARKERS)


def content_findings(path: Path) -> list[Finding]:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".gitignore":
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in EMAIL_PATTERN.finditer(line):
            if match.group(2).lower() not in SAFE_EMAIL_DOMAINS:
                findings.append(
                    Finding(path, "email address is not from a reserved example domain", line_number)
                )
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(path, f"likely {label}", line_number))
        for match in IDENTIFIER_PATTERN.finditer(line):
            if not safe_identifier(match.group(1)):
                findings.append(
                    Finding(path, "likely account, organisation, customer, or subscription identifier", line_number)
                )
    return findings


def fixture_findings(path: Path, base: Path) -> list[Finding]:
    parts = relative_parts(path, base)
    if len(parts) < 2 or parts[:2] != ("tests", "fixtures") or path.name == "README.md":
        return []
    findings: list[Finding] = []
    if ".synthetic." not in path.name:
        findings.append(Finding(path, "public fixture filename must include .synthetic."))
    if path.suffix.lower() == ".json":
        try:
            data = strict_json_loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return findings
        if not isinstance(data, dict) or data.get("fixtureKind") != "synthetic":
            findings.append(Finding(path, "public JSON fixture must declare fixtureKind as synthetic"))
        if not isinstance(data, dict) or data.get("containsRealCustomerData") is not False:
            findings.append(
                Finding(path, "public JSON fixture must declare containsRealCustomerData as false")
            )
    return findings


def usage_record_findings(path: Path) -> list[Finding]:
    if not path.name.endswith(".usage-evidence.json"):
        return []
    try:
        data = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return [Finding(path, f"usage-evidence record is not valid JSON: {error}")]
    if not isinstance(data, dict):
        return [Finding(path, "usage-evidence record must be a JSON object")]
    version = data.get("schemaVersion")
    if version is not None and version != USAGE_EVIDENCE_VERSION:
        return [
            Finding(
                path,
                f"$.schemaVersion: unsupported version {version!r}; "
                f"supported current version: {USAGE_EVIDENCE_VERSION!r}",
            )
        ]
    return [
        Finding(path, str(issue))
        for issue in SCHEMA_VALIDATOR.validate(data, USAGE_EVIDENCE_SCHEMA)
    ]


def scan_files(files: Iterable[Path], base: Path = REPO_ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(set(files)):
        findings.extend(path_findings(path, base))
        findings.extend(content_findings(path))
        findings.extend(fixture_findings(path, base))
        findings.extend(usage_record_findings(path))
    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check publication candidates for likely private evidence."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to scan; defaults to tracked and non-ignored untracked files.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        files = (
            files_below(Path(value) for value in args.paths)
            if args.paths
            else tracked_and_untracked_files(REPO_ROOT)
        )
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Could not enumerate repository files: {error}") from error
    findings = scan_files(files)
    if findings:
        print("Publication check found likely private or incomplete evidence:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding.display(REPO_ROOT)}", file=sys.stderr)
        print(
            "Review every finding and the publication checklist; do not publish until resolved.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"Publication check passed ({len(files)} files scanned)")


if __name__ == "__main__":
    main()
