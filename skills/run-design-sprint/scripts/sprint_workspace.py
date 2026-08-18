#!/usr/bin/env python3
"""Create, render, advance, and validate a Design Sprint for One workspace."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import os
import posixpath
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse, urlsplit

from schema_validation import SchemaValidator, ValidationIssue, strict_json_loads


SKILL_DIR = Path(__file__).resolve().parent.parent
REFERENCES_DIR = SKILL_DIR / "references"
HTML_KIT_DIR = SKILL_DIR / "assets" / "html-kit"
SCHEMAS_DIR = REFERENCES_DIR / "schemas"

STATE_FILENAME = "sprint-state.json"
ASSIGNMENT_MANIFEST_FILENAME = "assignment-manifest.json"
STATE_SCHEMA_VERSION = "4.0"
LEGACY_STATE_SCHEMA_VERSION = "1.0"
PREVIOUS_STATE_SCHEMA_VERSION = "2.0"
INTERMEDIATE_STATE_SCHEMA_VERSION = "3.0"
ARTIFACT_SCHEMA_VERSION = "3.0"
LEGACY_ARTIFACT_SCHEMA_VERSION = "1.0"
PREVIOUS_ARTIFACT_SCHEMA_VERSION = "2.0"
REFERENCE_SCHEMA_VERSION = "1.0"
FIDELITY_SCHEMA_VERSION = "1.0"
STEP_GUIDANCE_SCHEMA_VERSION = "1.0"
RECRUITMENT_PLAN_VERSION = "1.0"
ASSIGNMENT_MANIFEST_SCHEMA_VERSION = "1.0"
ROLE_PACKET_VERSION = "1.0"
SESSION_MANIFEST_SCHEMA_VERSION = "2.0"
CUSTOMER_SESSION_SCHEMA_VERSION = "2.0"
LEGACY_SESSION_SCHEMA_VERSION = "1.0"
SESSION_SUMMARY_SCHEMA_VERSION = "1.0"
TEST_ARTIFACT_WORKFLOW_VERSION = "1.0"
SITE_MANIFEST_SCHEMA_VERSION = "1.0"
EXPORT_APPROVAL_SCHEMA_VERSION = "1.0"
SITE_MANIFEST_FILENAME = "site-manifest.json"
PORTABLE_FILE_MODE = 0o644
CUSTOMER_TESTING_DIR = "customer-testing"
SESSION_MANIFEST_FILENAME = "session-manifest.json"
DEFAULT_SESSION_CONTEXT_MAXIMUM = 24000
DEFAULT_SYNTHESIS_CONTEXT_MAXIMUM = 48000
DEFAULT_CONTEXT_WARNING_PERCENT = 80

SCHEMA_FAMILIES = {
    "workspace-state": {
        "label": "workspace state",
        "current": STATE_SCHEMA_VERSION,
        "schemas": {
            LEGACY_STATE_SCHEMA_VERSION: SCHEMAS_DIR / "workspace-state-v1.schema.json",
            PREVIOUS_STATE_SCHEMA_VERSION: SCHEMAS_DIR / "workspace-state-v2.schema.json",
            INTERMEDIATE_STATE_SCHEMA_VERSION: SCHEMAS_DIR / "workspace-state-v3.schema.json",
            STATE_SCHEMA_VERSION: SCHEMAS_DIR / "workspace-state-v4.schema.json",
        },
        "migratable": {
            LEGACY_STATE_SCHEMA_VERSION,
            PREVIOUS_STATE_SCHEMA_VERSION,
            INTERMEDIATE_STATE_SCHEMA_VERSION,
        },
    },
    "artifact-data": {
        "label": "artifact data",
        "current": ARTIFACT_SCHEMA_VERSION,
        "schemas": {
            LEGACY_ARTIFACT_SCHEMA_VERSION: SCHEMAS_DIR / "artifact-data-v1.schema.json",
            PREVIOUS_ARTIFACT_SCHEMA_VERSION: SCHEMAS_DIR / "artifact-data-v2.schema.json",
            ARTIFACT_SCHEMA_VERSION: SCHEMAS_DIR / "artifact-data-v3.schema.json",
        },
        "migratable": {
            LEGACY_ARTIFACT_SCHEMA_VERSION,
            PREVIOUS_ARTIFACT_SCHEMA_VERSION,
        },
    },
    "artifact-specs": {
        "label": "artifact specifications",
        "current": REFERENCE_SCHEMA_VERSION,
        "schemas": {
            REFERENCE_SCHEMA_VERSION: SCHEMAS_DIR / "artifact-specs-v1.schema.json"
        },
        "migratable": set(),
    },
    "role-contracts": {
        "label": "role contracts",
        "current": REFERENCE_SCHEMA_VERSION,
        "schemas": {
            REFERENCE_SCHEMA_VERSION: SCHEMAS_DIR / "role-contracts-v1.schema.json"
        },
        "migratable": set(),
    },
    "method-profiles": {
        "label": "method profiles",
        "current": REFERENCE_SCHEMA_VERSION,
        "schemas": {
            REFERENCE_SCHEMA_VERSION: SCHEMAS_DIR / "method-profiles-v1.schema.json"
        },
        "migratable": set(),
    },
    "step-guidance": {
        "label": "progressive step guidance",
        "current": STEP_GUIDANCE_SCHEMA_VERSION,
        "schemas": {
            STEP_GUIDANCE_SCHEMA_VERSION: SCHEMAS_DIR / "step-guidance-v1.schema.json"
        },
        "migratable": set(),
    },
    "assignment-manifest": {
        "label": "assignment manifest",
        "current": ASSIGNMENT_MANIFEST_SCHEMA_VERSION,
        "schemas": {
            ASSIGNMENT_MANIFEST_SCHEMA_VERSION: (
                SCHEMAS_DIR / "assignment-manifest-v1.schema.json"
            )
        },
        "migratable": set(),
    },
    "session-manifest": {
        "label": "customer-session manifest",
        "current": SESSION_MANIFEST_SCHEMA_VERSION,
        "schemas": {
            LEGACY_SESSION_SCHEMA_VERSION: SCHEMAS_DIR / "session-manifest-v1.schema.json",
            SESSION_MANIFEST_SCHEMA_VERSION: SCHEMAS_DIR / "session-manifest-v2.schema.json",
        },
        "migratable": {LEGACY_SESSION_SCHEMA_VERSION},
    },
    "customer-session": {
        "label": "customer-session record",
        "current": CUSTOMER_SESSION_SCHEMA_VERSION,
        "schemas": {
            LEGACY_SESSION_SCHEMA_VERSION: SCHEMAS_DIR / "customer-session-v1.schema.json",
            CUSTOMER_SESSION_SCHEMA_VERSION: SCHEMAS_DIR / "customer-session-v2.schema.json",
        },
        "migratable": {LEGACY_SESSION_SCHEMA_VERSION},
    },
    "session-summary": {
        "label": "customer-session summary",
        "current": SESSION_SUMMARY_SCHEMA_VERSION,
        "schemas": {
            SESSION_SUMMARY_SCHEMA_VERSION: SCHEMAS_DIR / "session-summary-v1.schema.json"
        },
        "migratable": set(),
    },
    "tested-version": {
        "label": "immutable tested prototype version",
        "current": TEST_ARTIFACT_WORKFLOW_VERSION,
        "schemas": {
            TEST_ARTIFACT_WORKFLOW_VERSION: (
                SCHEMAS_DIR / "tested-version-v1.schema.json"
            )
        },
        "migratable": set(),
    },
    "site-manifest": {
        "label": "sprint results site manifest",
        "current": SITE_MANIFEST_SCHEMA_VERSION,
        "schemas": {
            SITE_MANIFEST_SCHEMA_VERSION: (
                SCHEMAS_DIR / "site-manifest-v1.schema.json"
            )
        },
        "migratable": set(),
    },
    "export-approval": {
        "label": "sprint export approval",
        "current": EXPORT_APPROVAL_SCHEMA_VERSION,
        "schemas": {
            EXPORT_APPROVAL_SCHEMA_VERSION: (
                SCHEMAS_DIR / "export-approval-v1.schema.json"
            )
        },
        "migratable": set(),
    },
}
SCHEMA_VALIDATOR = SchemaValidator()

ROUTES = {
    "undecided",
    "research-first",
    "foundation-plus-design",
    "full-design-sprint",
    "focused-design-sprint",
    "no-sprint",
}
WORKSPACE_STATUSES = {
    "active",
    "waiting-for-human",
    "waiting-for-customers",
    "paused",
    "complete",
}
TERMINAL_STATES = {
    "not-terminal",
    "live-customer-tested",
    "self-test-complete-unvalidated",
    "planning-rehearsal-complete-unvalidated",
    "closed-unvalidated",
}
ARTIFACT_STATUSES = {
    "draft",
    "in-review",
    "ready-for-decision",
    "complete",
    "blocked",
}
CUSTOMER_STATUSES = {
    "not-planned",
    "recruiting",
    "scheduled",
    "in-progress",
    "complete",
    "partial",
    "blocked",
}
FINAL_OUTCOMES = {"proceed", "iterate", "pivot", "investigate", "stop"}
METHOD_PROFILES = {"sprint-book", "adaptive-design-sprint"}
EXECUTION_MODES = {"live", "self-test", "planning-rehearsal"}
DEVIATION_TYPES = {"substitution", "compression", "omission", "skip"}
FIDELITY_ASSESSMENTS = {
    "profile-followed",
    "adapted-with-documented-substitutions",
    "partial",
    "self-test-rehearsal",
    "not-applicable",
}
PARTICIPANT_FITS = {"unassessed", "qualified", "excluded"}
PROTOCOL_FIDELITIES = {
    "not-assessed",
    "consistent",
    "minor-deviation",
    "material-deviation",
}
EVIDENCE_BANDS = {
    0: ("not-tested", "Not tested"),
    1: ("early-limited", "Early / limited"),
    2: ("early-limited", "Early / limited"),
    3: ("partial-directional", "Partial directional"),
    4: ("partial-directional", "Partial directional"),
    5: ("book-target-met", "Book target met"),
}
DECISION_IMPACTS = {
    "investigate-or-retest",
    "correct-observed-failure",
    "bounded-reversible-investment",
    "defer-large-or-irreversible-investment",
}
PROTOTYPE_BRIEF_ID = "10-prototype-brief"
TEST_PLAN_ID = "10-test-plan"
GUIDANCE_ACTIONS = {
    "show-example",
    "explain-why",
    "show-canonical-method",
    "show-checklist",
    "compare-substitutes",
    "i-am-blocked",
    "pause",
}
RECRUITMENT_STATUSES = {
    "draft",
    "ready",
    "recruiting",
    "scheduled",
    "partial",
    "complete",
    "blocked",
}
RECRUITMENT_MILESTONES = {
    "target-defined": "targetDefined",
    "screener-approved": "screenerApproved",
    "outreach-live": "outreachLive",
    "candidates-screened": "candidatesScreened",
    "sessions-booked": "sessionsBooked",
    "backups-booked": "backupsBooked",
    "consent-ready": "consentReady",
}
ARTIFACT_LADDER = (
    "copy-concept",
    "concierge",
    "clickable",
    "coded-facade",
    "live-mvp",
    "limited-pilot",
)
PROTOTYPE_APPROVAL_BOUNDARIES = {
    "experiment-boundary": "experimentBoundary",
    "tool-choice": "toolChoice",
    "external-account": "externalAccount",
    "cost": "cost",
    "data-exposure": "dataExposure",
    "public-deployment": "publicDeployment",
}
SENSITIVE_BUILD_ASSET_PARTS = {
    ".env",
    "account-evidence",
    "participant-data",
    "private-evidence",
    "raw-evidence",
    "recordings",
    "transcripts",
}

STEPS = [
    {"id": "01-intake", "name": "Intake"},
    {"id": "02-qualify", "name": "Qualify and route"},
    {"id": "03-evidence", "name": "Build the evidence base"},
    {"id": "04-foundation", "name": "Establish the foundation"},
    {"id": "05-map", "name": "Map the experience"},
    {"id": "06-questions", "name": "Define sprint questions"},
    {"id": "07-explore", "name": "Explore independently"},
    {"id": "08-decide", "name": "Compare and decide"},
    {"id": "09-experiment", "name": "Design the experiment"},
    {"id": "10-prototype", "name": "Build and review the prototype"},
    {"id": "11-customer-sessions", "name": "Run real-customer sessions"},
    {"id": "12-synthesis", "name": "Synthesise evidence"},
    {"id": "13-outcome", "name": "Decide and hand off"},
]
STEP_INDEX = {step["id"]: index for index, step in enumerate(STEPS)}
GATE_BY_STEP = {
    "02-qualify": "gate-1",
    "06-questions": "gate-2",
    "08-decide": "gate-3",
    "10-prototype": "gate-4",
    "13-outcome": "gate-5",
}
GATE_NAMES = {
    "gate-1": "Challenge and sprint route",
    "gate-2": "Target and top risks",
    "gate-3": "Selected solution direction",
    "gate-4": "Prototype readiness",
    "gate-5": "Final outcome",
}

STEP_REQUIRED = "required"
STEP_NOT_APPLICABLE = "not-applicable"
STEP_DEFERRED = "deferred-until-reroute"

# This is the executable route/step matrix.  Every route names every step so a
# new step or route cannot silently inherit permissive behavior.
ROUTE_STEP_TRANSITIONS = {
    "undecided": {
        "01-intake": STEP_REQUIRED,
        "02-qualify": STEP_REQUIRED,
        "03-evidence": STEP_DEFERRED,
        "04-foundation": STEP_DEFERRED,
        "05-map": STEP_DEFERRED,
        "06-questions": STEP_DEFERRED,
        "07-explore": STEP_DEFERRED,
        "08-decide": STEP_DEFERRED,
        "09-experiment": STEP_DEFERRED,
        "10-prototype": STEP_DEFERRED,
        "11-customer-sessions": STEP_DEFERRED,
        "12-synthesis": STEP_DEFERRED,
        "13-outcome": STEP_DEFERRED,
    },
    "research-first": {
        "01-intake": STEP_REQUIRED,
        "02-qualify": STEP_REQUIRED,
        "03-evidence": STEP_REQUIRED,
        "04-foundation": STEP_DEFERRED,
        "05-map": STEP_DEFERRED,
        "06-questions": STEP_DEFERRED,
        "07-explore": STEP_DEFERRED,
        "08-decide": STEP_DEFERRED,
        "09-experiment": STEP_DEFERRED,
        "10-prototype": STEP_DEFERRED,
        "11-customer-sessions": STEP_DEFERRED,
        "12-synthesis": STEP_DEFERRED,
        "13-outcome": STEP_DEFERRED,
    },
    "foundation-plus-design": {
        step["id"]: STEP_REQUIRED for step in STEPS
    },
    "full-design-sprint": {
        **{step["id"]: STEP_REQUIRED for step in STEPS},
        "04-foundation": STEP_NOT_APPLICABLE,
    },
    "focused-design-sprint": {
        **{step["id"]: STEP_REQUIRED for step in STEPS},
        "04-foundation": STEP_NOT_APPLICABLE,
    },
    "no-sprint": {
        **{step["id"]: STEP_NOT_APPLICABLE for step in STEPS},
        "01-intake": STEP_REQUIRED,
        "02-qualify": STEP_REQUIRED,
        "13-outcome": STEP_REQUIRED,
    },
}

ROUTE_TRANSITION_TABLE = {
    "undecided": {
        "research-first",
        "foundation-plus-design",
        "full-design-sprint",
        "focused-design-sprint",
        "no-sprint",
    },
    "research-first": {
        "foundation-plus-design",
        "full-design-sprint",
        "focused-design-sprint",
        "no-sprint",
    },
    "foundation-plus-design": set(),
    "full-design-sprint": set(),
    "focused-design-sprint": set(),
    "no-sprint": set(),
}

NO_SPRINT_NOT_APPLICABLE_GATES = {"gate-2", "gate-3", "gate-4"}

REQUIRED_RESULT_SECTIONS = (
    "Findings",
    "Evidence and provenance",
    "Assumptions and inferences",
    "Recommendation",
    "Risks or disagreements",
    "Open questions",
    "Stop condition reached",
)
INDEPENDENT_ASSIGNMENT_STEPS = {
    "02-qualify",
    "06-questions",
    "07-explore",
    "10-prototype",
}
REQUIRED_ROLES_BY_STEP = {
    "02-qualify": ("evidence-researcher", "product-strategist"),
    "03-evidence": ("evidence-researcher", "research-lead"),
    "04-foundation": (
        "product-strategist",
        "evidence-researcher",
        "critical-reviewer",
    ),
    "05-map": ("experience-designer", "technical-lead"),
    "06-questions": (
        "product-strategist",
        "technical-lead",
        "critical-reviewer",
    ),
    "07-explore": (
        "product-strategist",
        "experience-designer",
        "technical-lead",
        "critical-reviewer",
    ),
    "09-experiment": ("experience-designer", "research-lead", "technical-lead"),
    "10-prototype": ("prototype-builder", "critical-reviewer", "research-lead"),
    "11-customer-sessions": ("research-lead",),
    "12-synthesis": ("synthesis-analyst", "critical-reviewer"),
}
ASSIGNMENT_TRANSITIONS = {
    "assigned": {"in-progress", "rejected"},
    "in-progress": {"rejected"},
    "returned": {"accepted", "rejected"},
    "accepted": set(),
    "rejected": set(),
}
GATE_DEFAULT_INPUTS = {
    "gate-1": ("artifact", "01-sprint-brief"),
    "gate-2": ("artifact", "05-sprint-questions"),
    "gate-3": ("artifact", "07-decision"),
    "gate-4": ("prototype", "prototype"),
    "gate-5": ("artifact", "13-outcome"),
}
WORKSPACE_GITIGNORE = """# This generated workspace is private by default.
# Keep sensitive source material outside the workspace; these rules are a fallback.
**/account-evidence/
**/participant-data/
**/private-evidence/
**/raw-evidence/
**/recordings/
**/transcripts/
customer-testing/sessions/*/raw/
**/usage-evidence/private/
.env
.env.*
!.env.example
*.key
*.pem
"""


class SprintError(Exception):
    """A user-correctable sprint workspace error."""


@dataclass
class RenderPlan:
    """A complete, deterministic render prepared before any files are replaced."""

    registrations: list[dict[str, Any]]
    generated_files: dict[Path, str]
    state_update: dict[str, Any] | None
    stale_files: list[Path]
    canonical_files: list[Path]
    site_manifest: dict[str, Any]


class LocalLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.references: list[tuple[str, str, str]] = []
        self.ids: set[str] = set()
        self.site_navigation_landmarks = 0
        self.current_page_indicators = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        element_id = attr_map.get("id")
        if element_id:
            self.ids.add(element_id)
        if tag == "nav" and attr_map.get("aria-label") == "Sprint site":
            self.site_navigation_landmarks += 1
        if attr_map.get("aria-current") == "page":
            self.current_page_indicators += 1
        reference_attributes = {
            "a": ("href",),
            "audio": ("src",),
            "base": ("href",),
            "embed": ("src",),
            "form": ("action",),
            "iframe": ("src",),
            "img": ("src",),
            "input": ("src",),
            "link": ("href",),
            "object": ("data",),
            "script": ("src",),
            "source": ("src",),
            "track": ("src",),
            "use": ("href", "xlink:href"),
            "video": ("src", "poster"),
        }
        for attribute in reference_attributes.get(tag, ()):
            value = attr_map.get(attribute)
            if value:
                self.links.append(value)
                self.references.append((tag, attribute, value))
        srcset = attr_map.get("srcset")
        if tag in {"img", "source"} and srcset:
            for candidate in srcset.split(","):
                value = candidate.strip().split()[0] if candidate.strip() else ""
                if value:
                    self.links.append(value)
                    self.references.append((tag, "srcset", value))


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def display_date(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return value
    return parsed.strftime("%d %b %Y, %H:%M UTC")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64].rstrip("-") or "sprint"


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = strict_json_loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SprintError(f"Missing required file: {path}") from error
    except (json.JSONDecodeError, ValueError) as error:
        raise SprintError(f"Invalid JSON in {path}: {error}") from error
    if not isinstance(data, dict):
        raise SprintError(f"Expected a JSON object in {path}")
    return data


def schema_issues(
    data: dict[str, Any], family: str, *, accept_legacy: bool = False
) -> list[ValidationIssue]:
    """Return version and schema failures for one persisted JSON document."""

    config = SCHEMA_FAMILIES[family]
    version = data.get("schemaVersion")
    current = config["current"]
    schemas = config["schemas"]
    migratable = config["migratable"]
    if not isinstance(version, str):
        return [
            ValidationIssue(
                ("schemaVersion",),
                f"must declare a string version; current {config['label']} version is {current!r}",
            )
        ]
    if version != current and not (accept_legacy and version in migratable):
        if version in migratable:
            message = (
                f"version {version!r} is legacy; current version is {current!r}. "
                "Run `migrate --workspace <workspace> --dry-run`, then migrate with a backup."
            )
        else:
            supported = [f"{current} (current)"] + [
                f"{item} (migratable)" for item in sorted(migratable)
            ]
            message = (
                f"unsupported version {version!r}; supported versions: "
                + ", ".join(supported)
            )
        return [ValidationIssue(("schemaVersion",), message)]
    schema_path = schemas.get(version)
    if schema_path is None:
        return [
            ValidationIssue(
                ("schemaVersion",),
                f"unsupported version {version!r}; current version is {current!r}",
            )
        ]
    return SCHEMA_VALIDATOR.validate(data, schema_path)


def formatted_schema_errors(
    data: dict[str, Any], family: str, path: Path, *, accept_legacy: bool = False
) -> list[str]:
    return [
        f"{path}: {issue}"
        for issue in schema_issues(data, family, accept_legacy=accept_legacy)
    ]


def require_valid_schema(
    data: dict[str, Any], family: str, path: Path, *, accept_legacy: bool = False
) -> None:
    errors = formatted_schema_errors(
        data, family, path, accept_legacy=accept_legacy
    )
    if errors:
        label = SCHEMA_FAMILIES[family]["label"]
        detail = "\n".join(f"- {item}" for item in errors)
        raise SprintError(f"Invalid {label}:\n{detail}")


def json_text(data: dict[str, Any]) -> str:
    try:
        return (
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
    except (TypeError, ValueError) as error:
        raise SprintError(f"Cannot serialize canonical JSON: {error}") from error


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def portable_permissions_supported() -> bool:
    return os.name == "posix"


def file_mode(path: Path) -> int | None:
    if not portable_permissions_supported():
        return None
    return stat.S_IMODE(path.stat().st_mode)


def stage_bytes(path: Path, payload: bytes, mode: int = PORTABLE_FILE_MODE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if portable_permissions_supported():
            os.chmod(temp_path, mode)
        return temp_path
    except OSError as error:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise SprintError(f"Could not stage atomic write for {path}: {error}") from error


def write_texts_atomically(outputs: dict[Path, str]) -> None:
    """Publish a set of files without exposing partial writes.

    Every payload is staged and synced before replacement begins. Existing targets
    are backed up so an in-process replacement failure can restore files already
    published during the same batch. Individual replacements are atomic, so an
    interruption never exposes a partially written target.
    """

    staged: list[tuple[Path, Path, Path | None]] = []
    try:
        ordered_outputs = sorted(
            outputs.items(),
            key=lambda item: (item[0].name == STATE_FILENAME, item[0].as_posix()),
        )
        for path, text in ordered_outputs:
            payload = text.encode("utf-8")
            temp_path: Path | None = None
            backup: Path | None = None
            if path.exists():
                same_content = path.read_bytes() == payload
                same_mode = (
                    not portable_permissions_supported()
                    or file_mode(path) == PORTABLE_FILE_MODE
                )
                if same_content and same_mode:
                    continue
                previous_mode = file_mode(path)
                if previous_mode is None:
                    previous_mode = PORTABLE_FILE_MODE
                try:
                    backup = stage_bytes(path, path.read_bytes(), previous_mode)
                    temp_path = stage_bytes(path, payload)
                except SprintError:
                    if backup is not None:
                        backup.unlink(missing_ok=True)
                    raise
            else:
                temp_path = stage_bytes(path, payload)
            staged.append((path, temp_path, backup))
    except (OSError, SprintError) as error:
        for _, temp_path, backup in staged:
            temp_path.unlink(missing_ok=True)
            if backup is not None:
                backup.unlink(missing_ok=True)
        if isinstance(error, SprintError):
            raise
        raise SprintError(f"Could not prepare rendered files: {error}") from error

    committed: list[tuple[Path, Path | None]] = []
    preserved_backups: set[Path] = set()
    try:
        for path, temp_path, backup in staged:
            os.replace(temp_path, path)
            committed.append((path, backup))
    except OSError as error:
        rollback_errors: list[str] = []
        for path, backup in reversed(committed):
            try:
                if backup is None:
                    path.unlink(missing_ok=True)
                else:
                    os.replace(backup, path)
            except OSError as rollback_error:
                if backup is not None:
                    preserved_backups.add(backup)
                rollback_errors.append(
                    f"{path}: {rollback_error} (backup kept at {backup})"
                )
        detail = ""
        if rollback_errors:
            detail = f"; rollback also failed for {', '.join(rollback_errors)}"
        raise SprintError(f"Atomic replacement failed: {error}{detail}") from error
    finally:
        for _, temp_path, backup in staged:
            temp_path.unlink(missing_ok=True)
            if backup is not None and backup not in preserved_backups:
                backup.unlink(missing_ok=True)


def write_json(path: Path, data: dict[str, Any]) -> None:
    write_text(path, json_text(data))


def write_text(path: Path, text: str) -> None:
    write_texts_atomically({path: text})


def ensure_portable_permissions(paths: list[Path]) -> None:
    if not portable_permissions_supported():
        return
    for path in paths:
        if path.exists() and file_mode(path) != PORTABLE_FILE_MODE:
            try:
                os.chmod(path, PORTABLE_FILE_MODE)
            except OSError as error:
                raise SprintError(
                    f"Could not set portable permissions on {path}: {error}"
                ) from error


def load_artifact_specs() -> dict[str, dict[str, Any]]:
    path = REFERENCES_DIR / "artifact-specs.json"
    data = read_json(path)
    require_valid_schema(data, "artifact-specs", path)
    artifacts = data.get("artifacts")
    assert isinstance(artifacts, dict)
    return artifacts


def load_role_contracts() -> dict[str, dict[str, Any]]:
    path = REFERENCES_DIR / "role-contracts.json"
    data = read_json(path)
    require_valid_schema(data, "role-contracts", path)
    roles = data.get("roles")
    assert isinstance(roles, dict)
    return roles


def load_method_contract() -> dict[str, Any]:
    path = REFERENCES_DIR / "method-profiles.json"
    data = read_json(path)
    require_valid_schema(data, "method-profiles", path)
    profiles = data.get("methodProfiles")
    modes = data.get("executionModes")
    principles = data.get("nonNegotiablePrinciples")
    steps = data.get("steps")
    if not isinstance(profiles, dict) or set(profiles) != METHOD_PROFILES:
        raise SprintError("method-profiles.json has invalid method profiles")
    if not isinstance(modes, dict) or set(modes) != EXECUTION_MODES:
        raise SprintError("method-profiles.json has invalid execution modes")
    if not isinstance(principles, list):
        raise SprintError("method-profiles.json must define non-negotiable principles")
    if not isinstance(steps, dict) or set(steps) != set(STEP_INDEX):
        raise SprintError("method-profiles.json must define every workflow step")
    return data


def load_step_guidance() -> dict[str, Any]:
    """Load the complete user-facing guidance registry and detect method drift."""

    path = REFERENCES_DIR / "step-guidance.json"
    data = read_json(path)
    require_valid_schema(data, "step-guidance", path)
    actions = data.get("actions")
    steps = data.get("steps")
    if not isinstance(actions, dict) or set(actions) != GUIDANCE_ACTIONS:
        raise SprintError("step-guidance.json must define every supported help action")
    if not isinstance(steps, dict) or set(steps) != set(STEP_INDEX):
        raise SprintError("step-guidance.json must define every workflow step")

    method_contract = load_method_contract()
    for step_id, guidance in steps.items():
        method_step = method_contract["steps"][step_id]
        expected_methods = {
            "sprint-book": method_step["bookDefaultMethod"],
            "adaptive-design-sprint": method_step["adaptiveDefaultMethod"],
        }
        if guidance["purpose"] != method_step["canonicalPurpose"]:
            raise SprintError(
                f"step-guidance.json purpose drifted from method-profiles.json for {step_id}"
            )
        if guidance["methods"] != expected_methods:
            raise SprintError(
                f"step-guidance.json methods drifted from method-profiles.json for {step_id}"
            )
        if guidance["timeboxMinutes"] != method_step["suggestedTimeboxMinutes"]:
            raise SprintError(
                f"step-guidance.json timeboxes drifted from method-profiles.json for {step_id}"
            )
        for help_link in guidance["deeperHelp"]:
            reference = str(help_link["reference"])
            reference_path = REFERENCES_DIR / reference.removeprefix("references/").split("#", 1)[0]
            if not reference_path.is_file():
                raise SprintError(
                    f"step-guidance.json has a missing deeper-help reference for {step_id}: {reference}"
                )
    return data


def workspace_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def workspace_relative_file(workspace: Path, value: str, label: str) -> Path:
    workspace = workspace.resolve()
    candidate = (workspace / value).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as error:
        raise SprintError(f"{label} escapes the sprint workspace: {value}") from error
    if not candidate.is_file():
        raise SprintError(f"{label} does not exist or is not a file: {value}")
    return candidate


def source_descriptor(workspace: Path, value: str, label: str) -> dict[str, Any]:
    path = workspace_relative_file(workspace, value, label)
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise SprintError(f"{label} must be a readable UTF-8 text file: {value}") from error
    return {
        "path": path.relative_to(workspace).as_posix(),
        "sha256": sha256_bytes(payload),
        "characters": len(text),
    }


def file_source_descriptor(
    workspace: Path, value: str, label: str, *, reject_sensitive: bool = False
) -> dict[str, Any]:
    """Describe an explicitly selected workspace file without assuming it is text."""

    path = workspace_relative_file(workspace, value, label)
    relative = path.relative_to(workspace).as_posix()
    if reject_sensitive:
        lowered_parts = {part.lower() for part in Path(relative).parts}
        name = path.name.lower()
        if (
            lowered_parts & SENSITIVE_BUILD_ASSET_PARTS
            or name.startswith(".env")
            or path.suffix.lower() in {".key", ".pem", ".p12", ".pfx"}
        ):
            raise SprintError(
                f"{label} appears to contain secrets or private source material and "
                f"cannot enter an AI build packet: {relative}"
            )
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise SprintError(f"Could not read {label}: {relative}") from error
    return {
        "path": relative,
        "sha256": sha256_bytes(payload),
        "bytes": len(payload),
    }


def validate_file_descriptor(
    workspace: Path, descriptor: dict[str, Any], label: str
) -> str | None:
    try:
        current = file_source_descriptor(
            workspace, str(descriptor.get("path", "")), label
        )
    except SprintError as error:
        return str(error)
    if current != descriptor:
        return (
            f"{label} changed after it was recorded: {descriptor.get('path')}. "
            "Create a new trial or tested version instead of overwriting immutable evidence."
        )
    return None


def descriptor_text(
    workspace: Path, descriptor: dict[str, Any], label: str
) -> str:
    path_value = str(descriptor.get("path", ""))
    path = workspace_relative_file(workspace, path_value, label)
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise SprintError(
            f"{label} must remain a readable UTF-8 text file: {path_value}"
        ) from error
    if sha256_bytes(payload) != descriptor.get("sha256"):
        raise SprintError(
            f"{label} changed after its version was recorded: {path_value}. "
            "Record a new prototype/questions version before generating another packet."
        )
    if len(text) != descriptor.get("characters"):
        raise SprintError(f"{label} character count no longer matches: {path_value}")
    return text


def state_path(workspace: Path) -> Path:
    return workspace / STATE_FILENAME


def assignment_manifest_path(workspace: Path) -> Path:
    return workspace / ASSIGNMENT_MANIFEST_FILENAME


def empty_assignment_manifest(timestamp: str | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": ASSIGNMENT_MANIFEST_SCHEMA_VERSION,
        "assignments": [],
        "updatedAt": timestamp or utc_now(),
    }


def load_assignment_manifest(workspace: Path) -> dict[str, Any]:
    path = assignment_manifest_path(workspace)
    manifest = read_json(path)
    require_valid_schema(manifest, "assignment-manifest", path)
    return manifest


def save_assignment_manifest(
    workspace: Path, manifest: dict[str, Any], timestamp: str | None = None
) -> None:
    manifest["updatedAt"] = timestamp or utc_now()
    path = assignment_manifest_path(workspace)
    require_valid_schema(manifest, "assignment-manifest", path)
    write_json(path, manifest)


def digest_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def file_digest(path: Path) -> str:
    try:
        return digest_bytes(path.read_bytes())
    except FileNotFoundError as error:
        raise SprintError(f"Missing provenance file: {path}") from error
    except OSError as error:
        raise SprintError(f"Could not read provenance file {path}: {error}") from error


def resolved_workspace_file(
    workspace: Path, value: str, *, below: str | None = None
) -> tuple[Path, str]:
    candidate = (workspace / value).resolve()
    root = (workspace / below).resolve() if below else workspace.resolve()
    try:
        relative = candidate.relative_to(workspace.resolve()).as_posix()
        candidate.relative_to(root)
    except ValueError as error:
        if below:
            message = f"Path must stay below {below}/: {value}"
        else:
            message = f"Path escapes the sprint workspace: {value}"
        raise SprintError(message) from error
    return candidate, relative


def manifest_path(workspace: Path) -> Path:
    return workspace / CUSTOMER_TESTING_DIR / SESSION_MANIFEST_FILENAME


def session_directory(workspace: Path, session_id: str) -> Path:
    return workspace / CUSTOMER_TESTING_DIR / "sessions" / session_id


def load_session_manifest(workspace: Path) -> dict[str, Any]:
    path = manifest_path(workspace)
    manifest = read_json(path)
    require_valid_schema(manifest, "session-manifest", path)
    return manifest


def load_session_record(path: Path) -> dict[str, Any]:
    record = read_json(path)
    require_valid_schema(record, "customer-session", path)
    return record


def load_session_summary(path: Path) -> dict[str, Any]:
    summary = read_json(path)
    require_valid_schema(summary, "session-summary", path)
    return summary


def load_tested_version(path: Path) -> dict[str, Any]:
    record = read_json(path)
    require_valid_schema(record, "tested-version", path)
    return record


def load_state(workspace: Path) -> dict[str, Any]:
    path = state_path(workspace)
    state = read_json(path)
    require_valid_schema(state, "workspace-state", path)
    refresh_fidelity_summary(state)
    return state


def load_artifact_data(path: Path) -> dict[str, Any]:
    data = read_json(path)
    require_valid_schema(data, "artifact-data", path)
    return data


def save_state(
    workspace: Path, state: dict[str, Any], timestamp: str | None = None
) -> None:
    refresh_fidelity_summary(state)
    state["updatedAt"] = timestamp or utc_now()
    path = state_path(workspace)
    require_valid_schema(state, "workspace-state", path)
    write_json(path, state)


def save_artifact_data(path: Path, data: dict[str, Any]) -> None:
    require_valid_schema(data, "artifact-data", path)
    write_json(path, data)


def selection_record(
    selected_by: str, reason: str, timestamp: str | None = None
) -> dict[str, str]:
    return {
        "selectedBy": selected_by,
        "reason": reason,
        "selectedAt": timestamp or utc_now(),
    }


def expected_terminal_state(state: dict[str, Any]) -> str:
    """Derive the only truthful terminal classification for the recorded run."""

    if state.get("status") != "complete":
        return "not-terminal"
    if state.get("route") == "no-sprint":
        return "closed-unvalidated"
    mode = state.get("executionMode")
    if mode == "self-test":
        return "self-test-complete-unvalidated"
    if mode == "planning-rehearsal":
        return "planning-rehearsal-complete-unvalidated"
    customer = state.get("customerTesting", {})
    if mode == "live" and int(customer.get("sessionsUsable", 0)) > 0:
        return "live-customer-tested"
    return "closed-unvalidated"


def validation_truth(state: dict[str, Any]) -> tuple[str, str, str]:
    """Return a prominent label, explanation, and render class."""

    terminal_state = str(state.get("terminalState", "not-terminal"))
    mode = str(state.get("executionMode", "live"))
    customer = state.get("customerTesting", {})
    completed = int(customer.get("sessionsCompleted", 0))
    usable = int(customer.get("sessionsUsable", 0))
    if terminal_state == "live-customer-tested":
        return (
            "Live customer testing completed",
            f"This live sprint includes {usable} usable of {completed} completed real-customer session(s). Findings are directional, not statistical proof.",
            "section--accent",
        )
    if terminal_state == "self-test-complete-unvalidated":
        return (
            "UNVALIDATED — self-test complete",
            "The sprint process was exercised, but no customer validation was conducted. Assumptions, placeholders, and synthetic rehearsal remain non-observed inputs.",
            "section--warning",
        )
    if terminal_state == "planning-rehearsal-complete-unvalidated":
        return (
            "UNVALIDATED — planning/rehearsal complete",
            "This is a completed plan or rehearsal, not evidence that customer sessions or the planned sprint activities occurred.",
            "section--warning",
        )
    if terminal_state == "closed-unvalidated":
        return (
            "CLOSED UNVALIDATED",
            "This workspace closed without customer validation. Its hypotheses and decisions must not be represented as customer-tested evidence.",
            "section--warning",
        )
    if mode == "self-test":
        return (
            "UNVALIDATED SELF-TEST",
            "No customer validation is being conducted in self-test mode. Synthetic rehearsal may test the process but cannot create customer evidence.",
            "section--warning",
        )
    if mode == "planning-rehearsal":
        return (
            "UNVALIDATED PLANNING/REHEARSAL",
            "This workspace describes or rehearses planned activity; it does not establish that the activity or customer validation occurred.",
            "section--warning",
        )
    if usable > 0:
        return (
            "Live customer evidence recorded",
            f"{usable} usable of {completed} completed real-customer session(s) are recorded; the sprint has not yet reached its terminal decision.",
            "section--accent",
        )
    if completed > 0:
        return (
            "UNVALIDATED — no usable customer evidence",
            f"{completed} real-customer session(s) were completed, but none are usable for synthesis or a customer-dependent decision.",
            "section--warning",
        )
    return (
        "Live mode — customer validation pending",
        "No suitable real-customer session has been completed yet, so the current work remains unvalidated by customers.",
        "section--warning",
    )


def profile_mode_route_errors(
    method_profile: Any, execution_mode: Any, route: Any
) -> list[str]:
    errors: list[str] = []
    if method_profile not in METHOD_PROFILES:
        errors.append(f"Invalid method profile: {method_profile}")
    if execution_mode not in EXECUTION_MODES:
        errors.append(f"Invalid execution mode: {execution_mode}")
    if route not in ROUTES:
        errors.append(f"Invalid route: {route}")
    if errors:
        return errors
    contract = load_method_contract()
    compatible = contract["methodProfiles"][method_profile]["compatibleRoutes"]
    if route not in compatible:
        errors.append(
            f"Method profile {method_profile} is incompatible with route {route}; "
            "use full-design-sprint for the Sprint-book profile or select the adaptive profile"
        )
    return errors


def impact_record(
    method_fidelity: str, evidence: str, decision_readiness: str
) -> dict[str, str]:
    return {
        "methodFidelity": method_fidelity,
        "evidence": evidence,
        "decisionReadiness": decision_readiness,
    }


def build_fidelity(
    method_profile: str, execution_mode: str, timestamp: str | None = None
) -> dict[str, Any]:
    contract = load_method_contract()
    recorded_at = timestamp or utc_now()
    steps: dict[str, Any] = {}
    method_key = (
        "bookDefaultMethod"
        if method_profile == "sprint-book"
        else "adaptiveDefaultMethod"
    )
    for step_id, spec in contract["steps"].items():
        default_method = str(spec[method_key])
        deviations: list[dict[str, Any]] = []
        selected_methods: list[str] = []
        if method_profile == "sprint-book":
            for index, substitution in enumerate(spec.get("bookSubstitutions", []), 1):
                selected_methods.append(str(substitution["selectedMethod"]))
                deviations.append(
                    {
                        "id": f"default-book-substitution-{index}",
                        "type": "substitution",
                        "canonicalMethod": substitution["canonicalMethod"],
                        "selectedMethod": substitution["selectedMethod"],
                        "preservedPurpose": substitution["preservedPurpose"],
                        "reason": substitution["reason"],
                        "impact": dict(substitution["impact"]),
                        "recordedAt": recorded_at,
                    }
                )
        participants = {
            "human": list(spec.get("humanParticipants", [])),
            "ai": list(spec.get("aiParticipants", [])),
        }
        if execution_mode != "live" and step_id == "11-customer-sessions":
            participants["human"] = [
                item
                for item in participants["human"]
                if item != "Suitable real customers"
            ]
        steps[step_id] = {
            "canonicalPurpose": spec["canonicalPurpose"],
            "defaultMethod": default_method,
            "selectedMethod": "; ".join(selected_methods) or default_method,
            "participants": participants,
            "timebox": {
                "suggestedMinutes": int(
                    spec["suggestedTimeboxMinutes"][method_profile]
                ),
                "actualMinutes": None,
            },
            "deviations": deviations,
        }
    principles = [
        {
            "id": item["id"],
            "statement": item["statement"],
            "requirement": "non-negotiable",
        }
        for item in contract["nonNegotiablePrinciples"]
    ]
    profile = contract["methodProfiles"][method_profile]
    return {
        "schemaVersion": FIDELITY_SCHEMA_VERSION,
        "teamModel": profile["teamModel"],
        "teamModelLimitation": profile["teamModelLimitation"],
        "nonNegotiablePrinciples": principles,
        "steps": steps,
        "routeExclusions": [],
        "summary": {},
    }


def route_transition_record(
    from_route: str,
    to_route: str,
    reason: str,
    timestamp: str | None = None,
) -> dict[str, str]:
    return {
        "from": from_route,
        "to": to_route,
        "reason": reason,
        "selectedAt": timestamp or utc_now(),
    }


def followed_research_first(state: dict[str, Any]) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("from") == "undecided"
        and item.get("to") == "research-first"
        for item in state.get("routeHistory", [])
    )


def effective_route_step_policy(state: dict[str, Any]) -> dict[str, str]:
    route = str(state.get("route", "undecided"))
    policy = dict(ROUTE_STEP_TRANSITIONS.get(route, {}))
    if route == "no-sprint" and followed_research_first(state):
        policy["03-evidence"] = STEP_REQUIRED
    return policy


def route_not_applicable_steps(
    route: str, route_history: list[dict[str, Any]] | None = None
) -> dict[str, str]:
    state = {"route": route, "routeHistory": route_history or []}
    policy = effective_route_step_policy(state)
    if route in {"full-design-sprint", "focused-design-sprint"}:
        reason = "The approved route starts from an existing strategic foundation."
    elif route == "no-sprint" and followed_research_first(state):
        reason = "The Decider ended after the research-first evidence stage without running a design sprint."
    else:
        reason = "The Decider approved a no-sprint route after qualification."
    return {
        step_id: reason
        for step_id, disposition in policy.items()
        if disposition == STEP_NOT_APPLICABLE
    }


def route_change_errors(state: dict[str, Any], new_route: str) -> list[str]:
    current_route = str(state.get("route", "undecided"))
    errors: list[str] = []
    if new_route not in ROUTE_TRANSITION_TABLE.get(current_route, set()):
        allowed = sorted(ROUTE_TRANSITION_TABLE.get(current_route, set()))
        detail = ", ".join(allowed) if allowed else "none"
        errors.append(
            f"Route transition {current_route} -> {new_route} is impossible; allowed next routes: {detail}"
        )
        return errors
    completed = set(state.get("completedSteps", []))
    if current_route == "undecided":
        if state.get("currentStep") != "02-qualify" or "01-intake" not in completed:
            errors.append(
                "Select the initial route during 02-qualify after completing 01-intake"
            )
        if "02-qualify" in completed or state.get("pendingGate") is not None:
            errors.append(
                "The initial route cannot change after 02-qualify has completed or a gate is pending"
            )
    elif current_route == "research-first":
        gate_1 = next(
            (
                gate
                for gate in state.get("humanGates", [])
                if isinstance(gate, dict) and gate.get("id") == "gate-1"
            ),
            {},
        )
        if (
            state.get("currentStep") != "03-evidence"
            or "03-evidence" not in completed
            or state.get("status") != "waiting-for-human"
            or gate_1.get("status") != "complete"
        ):
            errors.append(
                "A research-first route may change only after 03-evidence completes and Gate 1 is approved"
            )
    return errors


def add_fidelity_deviation(
    state: dict[str, Any],
    step_id: str,
    deviation: dict[str, Any],
) -> None:
    record = state["fidelity"]["steps"][step_id]
    deviations = record.setdefault("deviations", [])
    deviation_id = deviation.get("id")
    if deviation_id and any(item.get("id") == deviation_id for item in deviations):
        return
    deviations.append(deviation)


def add_skip_deviation(
    state: dict[str, Any],
    step_id: str,
    reason: str,
    source: str = "explicit-skip",
    timestamp: str | None = None,
) -> None:
    add_fidelity_deviation(
        state,
        step_id,
        {
            "id": source,
            "type": "skip",
            "canonicalMethod": state["fidelity"]["steps"][step_id]["defaultMethod"],
            "selectedMethod": "Skipped",
            "preservedPurpose": "Not preserved; the recorded impacts describe the resulting gap.",
            "reason": reason,
            "impact": impact_record(
                f"Skipping {step_name(step_id).lower()} makes the selected method partial.",
                "No evidence or learning from this step was produced.",
                "Any decision depending on this step is less ready and must retain the gap as a limitation.",
            ),
            "recordedAt": timestamp or utc_now(),
        },
    )


def migrate_legacy_state(state: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(state)
    migration_timestamp = str(
        migrated.get("updatedAt") or migrated.get("createdAt") or utc_now()
    )
    migrated["schemaVersion"] = STATE_SCHEMA_VERSION
    migrated["methodProfile"] = "adaptive-design-sprint"
    migrated["executionMode"] = "live"
    migrated["methodProfileSelection"] = selection_record(
        "compatibility migration",
        "Schema 1.0 represented the adaptive one-human-plus-AI workflow implicitly.",
        migration_timestamp,
    )
    migrated["executionModeSelection"] = selection_record(
        "compatibility migration",
        "Schema 1.0 enforced real-customer evidence and is therefore migrated as live mode.",
        migration_timestamp,
    )
    migrated["fidelity"] = build_fidelity(
        migrated["methodProfile"], migrated["executionMode"], migration_timestamp
    )
    route = str(migrated.get("route", "undecided"))
    route_reason = str(migrated.get("routeRationale", "")).strip()
    if route != "undecided" and not route_reason:
        route_reason = (
            "Preserved selected route from the schema 1.0 workspace during "
            "compatibility migration."
        )
        migrated["routeRationale"] = route_reason
    migrated["routeHistory"] = (
        []
        if route == "undecided"
        else [
            route_transition_record(
                "undecided",
                route,
                route_reason,
                migration_timestamp,
            )
        ]
    )
    route_exclusions = route_not_applicable_steps(route, migrated["routeHistory"])
    previous_skips = list(migrated.get("skippedSteps", []))
    migrated["notApplicableSteps"] = sorted(route_exclusions)
    migrated["skippedSteps"] = [
        step_id for step_id in previous_skips if step_id not in route_exclusions
    ]
    migrated["skipReasons"] = {
        step_id: reason
        for step_id, reason in migrated.get("skipReasons", {}).items()
        if step_id in migrated["skippedSteps"]
    }
    migrated["skipRecords"] = [
        {
            "step": step_id,
            "skippedBy": "legacy actor unavailable",
            "reason": migrated["skipReasons"].get(
                step_id, "Legacy skip reason unavailable."
            ),
            "executionMode": migrated["executionMode"],
            "route": route,
            "skippedAt": migration_timestamp,
        }
        for step_id in migrated["skippedSteps"]
    ]
    migrated["fidelity"]["routeExclusions"] = [
        {"step": step_id, "reason": reason}
        for step_id, reason in route_exclusions.items()
    ]
    for step_id in migrated["skippedSteps"]:
        if step_id in STEP_INDEX:
            reason = migrated.get("skipReasons", {}).get(
                step_id, "Skipped before the schema 2.0 fidelity contract was added."
            )
            add_skip_deviation(
                migrated, step_id, reason, "legacy-skip", migration_timestamp
            )
    migrate_legacy_decisions(migrated, migration_timestamp)
    migrated["compatibility"] = {
        "migratedFromSchemaVersion": LEGACY_STATE_SCHEMA_VERSION,
        "migrationNote": "Legacy state was classified as adaptive/live; review and revise the selectors if that historical assumption is inaccurate.",
        "migratedAt": migration_timestamp,
    }
    migrated["terminalState"] = expected_terminal_state(migrated)
    refresh_fidelity_summary(migrated)
    return migrated


def migrate_legacy_decisions(
    state: dict[str, Any], migration_timestamp: str
) -> None:
    """Add conservative attestations to legacy decisions without inventing evidence."""

    legacy_decisions = state.get("decisions", [])
    if not isinstance(legacy_decisions, list) or not legacy_decisions:
        return
    migrated_decisions: list[dict[str, Any]] = []
    gate_counts: dict[str, int] = {}
    for legacy in legacy_decisions:
        if not isinstance(legacy, dict):
            continue
        gate_id = str(legacy.get("gate", ""))
        gate_counts[gate_id] = gate_counts.get(gate_id, 0) + 1
        decision_id = f"{gate_id}-decision-{gate_counts[gate_id]}"
        decision_text = str(legacy.get("decision", "Legacy decision"))
        if gate_id == "gate-1":
            subject_kind = "route"
            subject_value = str(state.get("route", "undecided"))
        elif gate_id == "gate-3":
            subject_kind = "concept"
            subject_value = str(state.get("selectedConcept") or decision_text)
            state.setdefault("selectedConcept", subject_value)
        else:
            subject_kind = "gate"
            subject_value = gate_id
        legacy_reference = f"legacy-{gate_id}-decision-{gate_counts[gate_id]}"
        migrated_decisions.append(
            {
                "id": decision_id,
                "gate": gate_id,
                "decision": decision_text,
                "deciderLabel": "human Decider (legacy label unavailable)",
                "consideredInputs": [
                    provenance_record(
                        "record",
                        legacy_reference,
                        digest_bytes(json_text(legacy).encode("utf-8")),
                    )
                ],
                "subject": {
                    "kind": subject_kind,
                    "value": subject_value,
                    "digest": value_digest(subject_kind, subject_value),
                },
                "rationale": str(legacy.get("rationale", "")),
                "reservations": str(legacy.get("reservations", "")),
                "status": "active",
                "decidedAt": str(
                    legacy.get("decidedAt") or migration_timestamp
                ),
            }
        )
    for gate_id in gate_counts:
        same_gate = [
            item for item in migrated_decisions if item.get("gate") == gate_id
        ]
        for superseded in same_gate[:-1]:
            superseded["status"] = "superseded"
            superseded["supersededAt"] = migration_timestamp
            superseded["supersededReason"] = (
                "A later legacy decision for this gate was active at migration."
            )
    state["decisions"] = migrated_decisions
    active_by_gate = {
        item["gate"]: item
        for item in migrated_decisions
        if item.get("status") == "active"
    }
    for gate in state.get("humanGates", []):
        if not isinstance(gate, dict) or gate.get("status") != "complete":
            continue
        decision = active_by_gate.get(gate.get("id"))
        if decision:
            gate["decisionId"] = decision["id"]
            gate["deciderLabel"] = decision["deciderLabel"]


def refresh_fidelity_summary(state: dict[str, Any]) -> None:
    fidelity = state.get("fidelity")
    if not isinstance(fidelity, dict):
        return
    adaptations: list[dict[str, str]] = []
    limitations: list[str] = []
    if state.get("methodProfile") == "sprint-book":
        limitations.append(str(fidelity.get("teamModelLimitation", "")))
        adaptations.append(
            {
                "step": "Whole sprint",
                "type": "team-model adaptation",
                "description": "One human Decider plus bounded AI specialists replaces the canonical cross-functional human sprint team.",
            }
        )
    for step_id, record in fidelity.get("steps", {}).items():
        for deviation in record.get("deviations", []):
            adaptations.append(
                {
                    "step": step_id,
                    "type": str(deviation.get("type", "adaptation")),
                    "description": str(
                        deviation.get("selectedMethod")
                        or deviation.get("reason")
                        or "Documented adaptation"
                    ),
                }
            )
            impact = deviation.get("impact", {})
            for key in ("evidence", "decisionReadiness"):
                value = str(impact.get(key, "")).strip()
                if value and value not in limitations:
                    limitations.append(value)
    contract = load_method_contract()
    mode = state.get("executionMode")
    if mode in EXECUTION_MODES:
        mode_limitation = str(contract["executionModes"][mode]["limitation"])
        if mode_limitation not in limitations:
            limitations.insert(0, mode_limitation)
    skipped = state.get("skippedSteps", [])
    route = state.get("route")
    customer = state.get("customerTesting", {})
    customer_method_partial = (
        mode == "live"
        and isinstance(customer, dict)
        and int(customer.get("sessionsPlanned", 0)) > 0
        and int(customer.get("sessionsUsable", 0))
        < int(customer.get("sessionsPlanned", 0))
        and (
            customer.get("status") in {"partial", "blocked"}
            or "11-customer-sessions" in state.get("completedSteps", [])
            or state.get("status") == "complete"
        )
    )
    if customer_method_partial:
        shortfall = int(customer.get("sessionsPlanned", 0)) - int(
            customer.get("sessionsUsable", 0)
        )
        adaptations.append(
            {
                "step": "11-customer-sessions",
                "type": "partial",
                "description": (
                    f"{customer.get('sessionsUsable', 0)}/{customer.get('sessionsPlanned', 0)} "
                    "planned sessions are currently usable."
                ),
            }
        )
        limitation = (
            f"{shortfall} planned customer session(s) are not usable; findings remain "
            "bounded to the observed sample and cannot establish prevalence."
        )
        if limitation not in limitations:
            limitations.append(limitation)
    if route == "no-sprint":
        assessment = "not-applicable"
    elif mode != "live":
        assessment = "self-test-rehearsal"
    elif skipped or customer_method_partial:
        assessment = "partial"
    elif adaptations:
        assessment = "adapted-with-documented-substitutions"
    else:
        assessment = "profile-followed"
    fidelity["summary"] = {
        "assessment": assessment,
        "adaptations": adaptations,
        "limitations": [item for item in limitations if item],
    }


def excluded_steps(state: dict[str, Any]) -> set[str]:
    return set(state.get("skippedSteps", [])) | set(
        state.get("notApplicableSteps", [])
    )


def next_step(current: str, excluded: set[str]) -> str | None:
    index = STEP_INDEX[current]
    for step in STEPS[index + 1 :]:
        if step["id"] not in excluded:
            return step["id"]
    return None


def add_skip(
    state: dict[str, Any],
    step_id: str,
    reason: str,
    skipped_by: str,
    timestamp: str | None = None,
) -> None:
    completed = set(state.get("completedSteps", []))
    if step_id in completed:
        return
    recorded_at = timestamp or utc_now()
    skipped = state.setdefault("skippedSteps", [])
    if step_id not in skipped:
        skipped.append(step_id)
    state.setdefault("skipReasons", {})[step_id] = reason
    records = state.setdefault("skipRecords", [])
    records[:] = [item for item in records if item.get("step") != step_id]
    records.append(
        {
            "step": step_id,
            "skippedBy": skipped_by,
            "reason": reason,
            "executionMode": state["executionMode"],
            "route": state["route"],
            "skippedAt": recorded_at,
        }
    )
    add_skip_deviation(state, step_id, reason, timestamp=recorded_at)


def apply_route(state: dict[str, Any], route: str) -> None:
    errors = profile_mode_route_errors(
        state.get("methodProfile"), state.get("executionMode"), route
    )
    if errors:
        raise SprintError("; ".join(errors))
    state["route"] = route
    exclusions = route_not_applicable_steps(route, state.get("routeHistory", []))
    state["notApplicableSteps"] = sorted(exclusions)
    state["fidelity"]["routeExclusions"] = [
        {"step": step_id, "reason": reason}
        for step_id, reason in exclusions.items()
    ]
    for step_id in exclusions:
        if step_id in state.setdefault("skippedSteps", []):
            state["skippedSteps"].remove(step_id)
        state.setdefault("skipReasons", {}).pop(step_id, None)
        state["skipRecords"] = [
            item
            for item in state.setdefault("skipRecords", [])
            if item.get("step") != step_id
        ]
    refresh_fidelity_summary(state)


def step_name(step_id: str) -> str:
    if step_id not in STEP_INDEX:
        return step_id
    return STEPS[STEP_INDEX[step_id]]["name"]


def class_for_status(status: str) -> str:
    normalized = status.lower().replace(" ", "-")
    mapping = {
        "active": "status--active",
        "waiting-for-human": "status--assumption",
        "waiting-for-customers": "status--assumption",
        "paused": "status--unknown",
        "complete": "status--complete",
        "live-customer-tested": "status--observed",
        "self-test-complete-unvalidated": "status--risk",
        "planning-rehearsal-complete-unvalidated": "status--risk",
        "closed-unvalidated": "status--risk",
        "not-terminal": "status--unknown",
        "draft": "status--unknown",
        "in-review": "status--active",
        "ready-for-decision": "status--decision",
        "assigned": "status--unknown",
        "in-progress": "status--active",
        "returned": "status--decision",
        "accepted": "status--complete",
        "rejected": "status--risk",
        "blocked": "status--risk",
        "passed": "status--complete",
        "failed": "status--risk",
        "observed": "status--observed",
        "assumption": "status--assumption",
        "inference": "status--inference",
        "decision": "status--decision",
        "unknown": "status--unknown",
        "synthetic-rehearsal": "status--synthetic",
    }
    return mapping.get(normalized, "status--unknown")


def replace_tokens(template: str, values: dict[str, Any]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    unresolved = sorted(set(re.findall(r"\{\{[A-Z0-9_]+\}\}", rendered)))
    if unresolved:
        raise SprintError(f"Unresolved template tokens: {', '.join(unresolved)}")
    return rendered


def safe_url(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return escape(value)
    return None


def render_paragraphs(values: Any) -> str:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list) or not values:
        return "<p>Nothing recorded yet.</p>"
    return "\n".join(f"<p>{escape(value)}</p>" for value in values)


def render_list(values: Any, ordered: bool = False) -> str:
    if not isinstance(values, list) or not values:
        return "<p>Nothing recorded yet.</p>"
    tag = "ol" if ordered else "ul"
    items = "\n".join(f"<li>{escape(value)}</li>" for value in values)
    return f"<{tag}>\n{items}\n</{tag}>"


def render_table(section: dict[str, Any]) -> str:
    columns = section.get("columns", [])
    rows = section.get("rows", [])
    if not isinstance(columns, list) or not columns:
        return "<p>No table columns recorded.</p>"
    headers = "".join(f"<th scope=\"col\">{escape(column)}</th>" for column in columns)
    body_rows = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, list):
            continue
        cells = "".join(f"<td>{escape(cell)}</td>" for cell in row[: len(columns)])
        cells += "<td></td>" * max(0, len(columns) - len(row))
        body_rows.append(f"<tr>{cells}</tr>")
    caption = escape(section.get("caption", section.get("title", "Data table")))
    return (
        "<table>"
        f"<caption>{caption}</caption>"
        f"<thead><tr>{headers}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )


def render_cards(section: dict[str, Any]) -> str:
    cards = section.get("cards", [])
    if not isinstance(cards, list) or not cards:
        return "<p>No cards recorded.</p>"
    output = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        status = str(card.get("status", "Unknown"))
        output.append(
            "<article class=\"metric\">"
            f"<span class=\"status {class_for_status(status)}\">{escape(status)}</span>"
            f"<h3>{escape(card.get('title', 'Untitled'))}</h3>"
            f"<p>{escape(card.get('body', ''))}</p>"
            "</article>"
        )
    return f"<div class=\"three-column\">{''.join(output)}</div>"


def render_key_values(section: dict[str, Any]) -> str:
    items = section.get("items", [])
    if not isinstance(items, list) or not items:
        return "<p>Nothing recorded yet.</p>"
    cards = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cards.append(
            "<div class=\"metric\">"
            f"<span class=\"metric__label\">{escape(item.get('label', 'Item'))}</span>"
            f"<span class=\"metric__value\">{escape(item.get('value', ''))}</span>"
            "</div>"
        )
    return f"<div class=\"three-column\">{''.join(cards)}</div>"


def render_section(section: dict[str, Any], index: int) -> str:
    title = escape(section.get("title", f"Section {index}"))
    eyebrow = escape(section.get("eyebrow", "Sprint artifact"))
    section_type = section.get("type", "paragraphs")
    if section_type == "list":
        body = render_list(section.get("items"))
    elif section_type == "ordered-list":
        body = render_list(section.get("items"), ordered=True)
    elif section_type == "table":
        body = render_table(section)
    elif section_type == "cards":
        body = render_cards(section)
    elif section_type == "key-value":
        body = render_key_values(section)
    else:
        body = render_paragraphs(section.get("paragraphs", section.get("body", [])))
    section_id = f"section-{index}-{slugify(str(section.get('title', index)))}"
    return (
        f"<section class=\"section\" aria-labelledby=\"{section_id}\">"
        f"<p class=\"eyebrow\">{eyebrow}</p>"
        f"<h2 id=\"{section_id}\">{title}</h2>"
        f"{body}"
        "</section>"
    )


def render_prototype_brief(
    brief: dict[str, Any],
    *,
    export_view: bool = False,
    shareable: bool = False,
    prototype_included: bool = True,
) -> str:
    selection = brief["selection"]
    customer = brief["customer"]
    experience = brief["experience"]
    content = brief["content"]
    environment = brief["environment"]
    capabilities = brief["capabilities"]
    safety = brief["safety"]
    evidence_capture = brief["evidenceCapture"]
    build = brief["build"]
    tool = brief["toolSelection"]
    deployment = brief["deploymentPlan"]
    approvals = brief["approvals"]

    def joined(values: list[str]) -> str:
        return "; ".join(values) or "None"

    def yes_no(value: bool) -> str:
        return "Yes" if value else "No"

    sections: list[str] = []
    sections.append(
        render_section(
            {
                "title": "Smallest valid test artifact",
                "eyebrow": "Test-artifact ladder",
                "type": "key-value",
                "items": [
                    {"label": "Selected level", "value": display_label(brief["artifactLevel"])},
                    {"label": "Target customer", "value": customer["target"]},
                    {"label": "Entry context", "value": customer["entryContext"]},
                    {
                        "label": "Sprint questions",
                        "value": joined(selection["sprintQuestions"]),
                    },
                    {"label": "Hypothesis", "value": selection["hypothesis"]},
                    {"label": "Selection rationale", "value": selection["rationale"]},
                    {
                        "label": "Why no larger artifact",
                        "value": selection["whyHigherFidelityIsUnnecessary"],
                    },
                ],
            },
            101,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Exact task and journey",
                "eyebrow": "Participant path",
                "type": "key-value",
                "items": [
                    {"label": "Task", "value": experience["task"]},
                    {"label": "Journey", "value": joined(experience["journey"])},
                ],
            },
            102,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Critical scenes",
                "eyebrow": "Four to six test moments",
                "type": "table",
                "caption": "Critical scenes mapped to sprint questions",
                "columns": ["Scene", "Sprint question", "What happens"],
                "rows": [
                    [f"{item['id']}: {item['title']}", item["sprintQuestion"], item["description"]]
                    for item in experience["criticalScenes"]
                ],
            },
            103,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Observable signals",
                "eyebrow": "Predefined interpretation boundary",
                "type": "table",
                "caption": "Success, ambiguity, and failure signals",
                "columns": ["Signal class", "Observable evidence"],
                "rows": [
                    [display_label(label), "; ".join(brief["signals"][label])]
                    for label in ("success", "ambiguity", "failure")
                ],
            },
            104,
        )
    )
    reality = brief["realityBoundary"]
    sections.append(
        render_section(
            {
                "title": "Reality and scope boundary",
                "eyebrow": "Clearly label every simulation",
                "type": "table",
                "caption": "What is real, simulated, manual, delayed, or omitted",
                "columns": ["Boundary", "Approved treatment"],
                "rows": [
                    [display_label(key), "; ".join(reality[key]) or "None"]
                    for key in ("mustBeReal", "simulated", "manuallyOperated", "delayed", "omitted")
                ],
            },
            105,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Content and interface states",
                "eyebrow": "Realistic test material",
                "type": "key-value",
                "items": [
                    {
                        "label": "Required content",
                        "value": joined(content["required"]),
                    },
                    {
                        "label": "Realistic sample data",
                        "value": joined(content["sampleData"]),
                    },
                    {
                        "label": "Empty states",
                        "value": joined(content["states"]["empty"]),
                    },
                    {
                        "label": "Loading states",
                        "value": joined(content["states"]["loading"]),
                    },
                    {
                        "label": "Error states",
                        "value": joined(content["states"]["error"]),
                    },
                ],
            },
            106,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Environment and capabilities",
                "eyebrow": "Test conditions",
                "type": "key-value",
                "items": [
                    {"label": "Devices", "value": joined(environment["devices"])},
                    {"label": "Browsers", "value": joined(environment["browsers"])},
                    {"label": "Languages", "value": joined(environment["languages"])},
                    {
                        "label": "Accessibility",
                        "value": joined(environment["accessibility"]),
                    },
                    {
                        "label": "Environmental conditions",
                        "value": joined(environment["conditions"]),
                    },
                ],
            },
            107,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Capability requirements",
                "eyebrow": "Only what must be operational",
                "type": "key-value",
                "items": [
                    {
                        "label": display_label(key),
                        "value": yes_no(value),
                    }
                    for key, value in capabilities.items()
                    if key != "notes"
                ]
                + [
                    {
                        "label": "Notes",
                        "value": joined(capabilities["notes"]),
                    }
                ],
            },
            108,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Safety and evidence capture",
                "eyebrow": "Privacy, consent, and learning boundary",
                "type": "key-value",
                "items": [
                    {"label": "Privacy", "value": joined(safety["privacy"])},
                    {"label": "Consent", "value": joined(safety["consent"])},
                    {"label": "Security", "value": joined(safety["security"])},
                    {"label": "Regulatory", "value": joined(safety["regulatory"])},
                    {
                        "label": "Data classification",
                        "value": display_label(safety["dataClassification"]),
                    },
                    {
                        "label": "Evidence methods",
                        "value": joined(evidence_capture["methods"]),
                    },
                    {
                        "label": "Analytics enabled",
                        "value": yes_no(evidence_capture["analytics"]["enabled"]),
                    },
                    {
                        "label": "Analytics rationale",
                        "value": evidence_capture["analytics"]["rationale"],
                    },
                ],
            },
            109,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Build boundary",
                "eyebrow": "Time, ownership, cost, and checkpoints",
                "type": "key-value",
                "items": [
                    {"label": "Timebox", "value": f'{build["timeboxMinutes"]} minutes'},
                    {"label": "Owner", "value": build["owner"]},
                    {"label": "Budget ceiling", "value": build["budgetCeiling"]},
                    {"label": "Approval points", "value": joined(build["approvalPoints"])},
                ],
            },
            110,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Provider-neutral tool selection",
                "eyebrow": "Needs and constraints, not a universal ranking",
                "type": "key-value",
                "items": [
                    {"label": "Route", "value": display_label(tool["route"])},
                    {"label": "Category", "value": display_label(tool["category"])},
                    {"label": "Selected tool", "value": tool["selectedTool"]},
                    {"label": "Rationale", "value": tool["rationale"]},
                    {"label": "Constraints", "value": joined(tool["constraints"])},
                    {
                        "label": "External account required",
                        "value": yes_no(tool["requiresExternalAccount"]),
                    },
                    {"label": "Estimated cost", "value": tool["estimatedCost"]},
                    {
                        "label": "Export / self-host available",
                        "value": yes_no(tool["exportSelfHosting"]["available"]),
                    },
                    {
                        "label": "Export / self-host",
                        "value": tool["exportSelfHosting"]["strategy"],
                    },
                ],
            },
            111,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Tool-selection assessment",
                "eyebrow": "Every criterion considered",
                "type": "table",
                "caption": "Provider-neutral selection criteria and assessment",
                "columns": ["Criterion", "Assessment"],
                "rows": [
                    [display_label(criterion), assessment]
                    for criterion, assessment in tool["criteria"].items()
                ],
            },
            112,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Supporting tool categories",
                "eyebrow": "Only when the experiment requires them",
                "type": "table",
                "caption": "Approved supporting tools and their purpose",
                "columns": ["Category", "Selected tool", "Rationale"],
                "rows": [
                    [
                        display_label(item["category"]),
                        item["selectedTool"],
                        item["rationale"],
                    ]
                    for item in tool["supportingTools"]
                ]
                or [["None", "None", "No supporting tool is required."]],
            },
            113,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Approval boundaries",
                "eyebrow": "Human-owned decisions",
                "type": "table",
                "caption": "Experiment, tool, account, cost, data, and deployment approvals",
                "columns": ["Boundary", "Status", "Decider", "Rationale", "Decided at"],
                "rows": [
                    [
                        display_label(boundary),
                        display_label(item["status"]),
                        (
                            "Human reviewer recorded"
                            if shareable and item["deciderLabel"]
                            else item["deciderLabel"] or "Pending"
                        ),
                        item["rationale"] or "Pending",
                        item["decidedAt"] or "Pending",
                    ]
                    for boundary, item in approvals.items()
                ],
            },
            114,
        )
    )
    sections.append(
        render_section(
            {
                "title": "Deployment, cleanup, and rollback",
                "eyebrow": "A URL is not validation",
                "type": "key-value",
                "items": [
                    {
                        "label": "Deployment required",
                        "value": yes_no(deployment["required"]),
                    },
                    {"label": "Target", "value": deployment["target"]},
                    {"label": "Access", "value": display_label(deployment["accessModel"])},
                    {"label": "Public", "value": yes_no(deployment["public"])},
                    {"label": "Planned URL", "value": deployment["url"] or "No URL planned"},
                    {"label": "Expiry", "value": deployment["expiresAt"] or "No automatic expiry"},
                    {"label": "Cleanup", "value": deployment["cleanupPlan"]},
                    {"label": "Rollback", "value": deployment["rollbackPlan"]},
                ],
            },
            115,
        )
    )
    operation_rows: list[str] = []
    for packet in brief["buildPackets"]:
        if export_view:
            operation_rows.append(
                '<li><strong>Build packet:</strong> approved private build boundary recorded '
                f'· digest {escape(packet["sha256"][:12])}</li>'
            )
        else:
            operation_rows.append(
                '<li><strong>Build packet:</strong> '
                f'<a href="../{escape(packet["path"])}">{escape(packet["path"])}</a> '
                f'· {escape(packet["sha256"][:12])}</li>'
            )
    for trial in brief["trialRuns"]:
        operation_rows.append(
            f'<li><strong>Trial {escape(trial["id"])}:</strong> '
            f'<span class="status {class_for_status(trial["status"])}">{escape(display_label(trial["status"]))}</span> '
            + (
                '· moderator label omitted from this shareable view</li>'
                if shareable
                else f'· moderated by {escape(trial["moderator"])}</li>'
            )
        )
    for version in brief["versions"]:
        url = safe_url(str(version.get("deploymentUrl") or ""))
        url_link = f' · <a href="{url}">deployment</a>' if url else ""
        if export_view:
            context_link = (
                ' · <a href="../prototype-launch.html">approved launch context</a>'
                if prototype_included
                and version["version"] == brief.get("currentVersion")
                else ""
            )
            operation_rows.append(
                f'<li><strong>Tested version {escape(version["version"])}:</strong> '
                f'immutable private record verified{context_link}{url_link}</li>'
            )
        else:
            operation_rows.append(
                f'<li><strong>Tested version {escape(version["version"])}:</strong> '
                f'<a href="../{escape(version["prototypePath"])}">artifact</a> · '
                f'<a href="../{escape(version["recordPath"])}">immutable record</a>'
                f'{url_link}</li>'
            )
    sections.append(
        '<section class="section" aria-labelledby="prototype-operations">'
        '<p class="eyebrow">Build and test history</p>'
        '<h2 id="prototype-operations">Packets, trials, and immutable versions</h2>'
        f'<ul>{"".join(operation_rows) if operation_rows else "<li>No build packet, trial, or frozen version yet.</li>"}</ul>'
        '<div class="callout"><strong>Readiness boundary:</strong> A live URL and a passed trial do not establish customer validation or production readiness.</div>'
        '</section>'
    )
    return "\n".join(sections)


def recruitment_stall(plan: dict[str, Any]) -> tuple[bool, str]:
    tracking = plan.get("tracking", {})
    milestones = tracking.get("milestones", {})
    pending = [
        key for key, value in milestones.items() if value != "complete"
    ]
    if not pending:
        return False, "All recruitment milestones are complete."
    deadline = datetime.fromisoformat(str(tracking["deadline"])).date()
    status = tracking.get("status")
    stalled = status == "blocked" or (
        status in {"ready", "recruiting", "scheduled", "partial"}
        and deadline < datetime.now(timezone.utc).date()
    )
    smallest_actions = {
        "targetDefined": "Approve the behavioral target and disqualifiers.",
        "screenerApproved": "Review and approve the next neutral screener question.",
        "outreachLive": "Send the approved invitation through one selected channel.",
        "candidatesScreened": "Screen the next candidate against the approved criteria.",
        "sessionsBooked": "Offer concrete timezone-labelled windows to the next qualified candidate.",
        "backupsBooked": "Invite the next qualified backup.",
        "consentReady": "Approve the consent and data-retention checklist.",
    }
    return stalled, smallest_actions[pending[0]]


def render_recruitment_plan(plan: dict[str, Any]) -> str:
    target = plan["targetDefinition"]
    screener = plan["screener"]
    incentive = plan["incentive"]
    outreach = plan["outreach"]
    scheduling = plan["scheduling"]
    consent = plan["consent"]
    backup = plan["backupPlan"]
    tracking = plan["tracking"]
    stalled, smallest_action = recruitment_stall(plan)
    sections = [
        render_section(
            {
                "title": "Recruitment owner and progress",
                "eyebrow": "Started during evidence collection",
                "type": "key-value",
                "items": [
                    {"label": "Owner", "value": tracking["owner"]},
                    {"label": "Status", "value": display_label(tracking["status"])},
                    {"label": "Next action", "value": tracking["nextAction"]},
                    {"label": "Deadline", "value": tracking["deadline"]},
                    {"label": "Candidates screened", "value": str(tracking["candidatesScreened"])},
                    {"label": "Sessions booked", "value": str(tracking["sessionsBooked"])},
                    {"label": "Backups booked", "value": str(tracking["backupsBooked"])},
                ],
            },
            201,
        ),
        render_section(
            {
                "title": "Recruitment milestones",
                "eyebrow": "Visible operational state",
                "type": "table",
                "caption": "Progress from target definition through consent readiness",
                "columns": ["Milestone", "Status"],
                "rows": [
                    [display_label(key), display_label(value)]
                    for key, value in tracking["milestones"].items()
                ],
            },
            202,
        ),
        render_section(
            {
                "title": "Behavioral target",
                "eyebrow": "Suitability before volume",
                "type": "key-value",
                "items": [
                    {"label": "Audience", "value": target["audience"]},
                    {"label": "Target sessions", "value": str(target["targetSessions"])},
                    {"label": "Suitable backups", "value": str(target["backupParticipants"])},
                    {"label": "Rationale", "value": target["rationale"]},
                    {"label": "Qualifying behaviors", "value": "; ".join(target["qualifyingBehaviours"])},
                    {"label": "Disqualifiers", "value": "; ".join(target["disqualifyingConditions"])},
                    {"label": "Special considerations", "value": "; ".join(target["specialConsiderations"])},
                ],
            },
            203,
        ),
        render_section(
            {
                "title": "Neutral screener",
                "eyebrow": display_label(screener["status"]),
                "type": "table",
                "caption": screener["introduction"],
                "columns": ["Question", "Qualifies", "Disqualifies", "Reveals preferred answer"],
                "rows": [
                    [
                        item["prompt"],
                        item["qualifyingSignal"],
                        item["disqualifyingSignal"],
                        "No" if item["revealsPreferredAnswer"] is False else "Yes",
                    ]
                    for item in screener["questions"]
                ],
            },
            204,
        ),
        render_section(
            {
                "title": "Channels and trade-offs",
                "eyebrow": "No paid vendor required",
                "type": "table",
                "caption": "Available routes remain optional; the human chooses the mix.",
                "columns": ["Channel", "Selected", "May require spend", "Trade-off"],
                "rows": [
                    [
                        display_label(item["name"]),
                        "Yes" if item["selected"] else "No",
                        "Yes" if item["requiresSpend"] else "No",
                        item["tradeOff"],
                    ]
                    for item in plan["channels"]
                ],
            },
            205,
        ),
        render_section(
            {
                "title": "Incentive and approval",
                "eyebrow": "Human approval before spend",
                "type": "key-value",
                "items": [
                    {"label": "Guidance", "value": incentive["guidance"]},
                    {"label": "Offer", "value": incentive["offer"]},
                    {"label": "Spending required", "value": "Yes" if incentive["spendingRequired"] else "No"},
                    {"label": "Approval", "value": display_label(incentive["approvalStatus"])},
                    {"label": "Approved by", "value": incentive["approvedBy"] or "Not applicable"},
                    {"label": "Approval note", "value": incentive["approvalNote"]},
                ],
            },
            206,
        ),
        render_section(
            {
                "title": "Outreach templates",
                "eyebrow": "Neutral and ready to send after approval",
                "type": "key-value",
                "items": [
                    {"label": display_label(key), "value": value}
                    for key, value in outreach.items()
                ],
            },
            207,
        ),
        render_section(
            {
                "title": "Schedule and accessible participation",
                "eyebrow": "Timezone explicit",
                "type": "key-value",
                "items": [
                    {"label": "Timezone", "value": scheduling["timezone"]},
                    {"label": "Session length", "value": f'{scheduling["sessionLengthMinutes"]} minutes'},
                    {"label": "Windows", "value": "; ".join(scheduling["windows"])},
                    {"label": "Booking method", "value": scheduling["bookingMethod"]},
                    {"label": "Accessibility", "value": "; ".join(scheduling["accessibility"])},
                    {"label": "Recruitment deadline", "value": scheduling["recruitmentDeadline"]},
                ],
            },
            208,
        ),
        render_section(
            {
                "title": "Consent and data handling",
                "eyebrow": "Private by default",
                "type": "key-value",
                "items": [
                    {"label": "Introduction", "value": consent["introduction"]},
                    {"label": "Recording", "value": consent["recordingPlan"]},
                    {"label": "Anonymisation", "value": consent["anonymisation"]},
                    {"label": "Retention", "value": consent["dataRetention"]},
                    {"label": "Withdrawal", "value": consent["withdrawal"]},
                    {"label": "Checklist", "value": "; ".join(consent["checklist"])},
                ],
            },
            209,
        ),
        render_section(
            {
                "title": "Backups and partial recruitment",
                "eyebrow": "Keep the original target visible",
                "type": "key-value",
                "items": [
                    {"label": "Activation trigger", "value": backup["activationTrigger"]},
                    {"label": "Backup actions", "value": "; ".join(backup["actions"])},
                    {"label": "Partial handling", "value": backup["partialRecruitmentHandling"]},
                ],
            },
            210,
        ),
    ]
    if stalled:
        sections.insert(
            0,
            '<section class="section section--warning" aria-labelledby="recruitment-stalled">'
            '<p class="eyebrow">Recruitment needs attention</p>'
            '<h2 id="recruitment-stalled">Stalled or due</h2>'
            f'<p><strong>Next smallest action:</strong> {escape(smallest_action)}</p>'
            '</section>',
        )
    return "\n".join(sections)


def render_recruitment_summary(plan: dict[str, Any] | None) -> str:
    if not isinstance(plan, dict):
        return (
            '<p>No structured recruitment plan yet. Create the customer test plan during evidence collection.</p>'
        )
    tracking = plan["tracking"]
    stalled, smallest_action = recruitment_stall(plan)
    completed = sum(
        value == "complete" for value in tracking["milestones"].values()
    )
    warning = (
        '<div class="callout"><strong>Stalled or due:</strong> '
        f'{escape(smallest_action)}</div>'
        if stalled
        else ""
    )
    return (
        '<div class="guidance-grid">'
        f'<div><span class="metric__label">Owner</span><p>{escape(tracking["owner"])}</p></div>'
        f'<div><span class="metric__label">Status</span><p>{escape(display_label(tracking["status"]))}</p></div>'
        f'<div><span class="metric__label">Deadline</span><p>{escape(tracking["deadline"])}</p></div>'
        f'<div><span class="metric__label">Milestones</span><p>{completed}/7 complete</p></div>'
        f'</div><p><strong>Next action:</strong> {escape(tracking["nextAction"])}</p>'
        '<p><strong>Channels:</strong> No paid vendor required; use the approved route and trade-off.</p>'
        f'{warning}<p><a href="artifacts/10-test-plan.html">Open recruitment plan and templates</a></p>'
    )


def render_evidence(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "<p>No evidence entries recorded yet.</p>"
    output = []
    for item in values:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "Unknown"))
        source = escape(item.get("source", "No source recorded"))
        source_url = safe_url(str(item.get("sourceUrl", "")))
        if source_url:
            source = f'<a href="{source_url}">{source}</a>'
        date = item.get("date")
        date_html = f" · {escape(date)}" if date else ""
        output.append(
            "<article class=\"provenance\">"
            f"<span class=\"status {class_for_status(status)}\">{escape(status)}</span>"
            f"<p><strong>{escape(item.get('claim', 'No claim recorded'))}</strong></p>"
            f"<p>Source: {source}{date_html}</p>"
            "</article>"
        )
    return "\n".join(output)


def display_label(value: Any) -> str:
    return str(value or "unknown").replace("-", " ").title()


def guidance_for_state(
    state: dict[str, Any], step_id: str | None = None
) -> dict[str, Any]:
    registry = load_step_guidance()
    selected_step = step_id or str(state.get("currentStep", "01-intake"))
    if selected_step not in STEP_INDEX:
        raise SprintError(f"Unknown guidance step: {selected_step}")
    profile = str(state.get("methodProfile", "adaptive-design-sprint"))
    guidance = copy.deepcopy(registry["steps"][selected_step])
    fidelity = state.get("fidelity", {}).get("steps", {}).get(selected_step, {})
    timebox = fidelity.get("timebox", {})
    deviations = copy.deepcopy(fidelity.get("deviations", []))
    deviation_reasons = [
        str(item.get("reason", "")).strip()
        for item in deviations
        if isinstance(item, dict) and str(item.get("reason", "")).strip()
    ]
    method_rationale = (
        "; ".join(deviation_reasons)
        or str(state.get("methodProfileSelection", {}).get("reason", "")).strip()
        or "No method-selection rationale has been recorded."
    )
    guidance.update(
        {
            "step": selected_step,
            "profile": profile,
            "canonicalMethod": guidance["methods"][profile],
            "selectedMethod": fidelity.get(
                "selectedMethod", guidance["methods"][profile]
            ),
            "selectedMethodRationale": method_rationale,
            "suggestedTimeboxMinutes": guidance["timeboxMinutes"][profile],
            "actualTimeboxMinutes": timebox.get("actualMinutes"),
            "recordedDeviations": deviations,
            "availableActions": copy.deepcopy(registry["actions"]),
        }
    )
    return guidance


def render_step_guidance(state: dict[str, Any]) -> str:
    guidance = guidance_for_state(state)
    ai_role = "; ".join(guidance["aiRole"])
    good = "; ".join(guidance["whatGoodLooksLike"])
    done = "; ".join(guidance["definitionOfDone"])
    dependencies = "; ".join(guidance["dependencies"])
    actual = guidance["actualTimeboxMinutes"]
    actual_text = (
        "not recorded" if actual is None else f"{actual} minutes actual"
    )
    substitute_items = "".join(
        "<li>"
        f'<strong>{escape(item["name"])}:</strong> {escape(item["useWhen"])} '
        f'Method impact: {escape(item["methodFidelityImpact"])} '
        f'Evidence impact: {escape(item["evidenceImpact"])}'
        "</li>"
        for item in guidance["substitutes"]
    )
    action_items = "".join(
        f'<li><strong>{escape(item["label"])}:</strong> {escape(item["description"])}</li>'
        for item in guidance["availableActions"].values()
    )
    help_items = "".join(
        f'<li><strong>{escape(item["label"])}:</strong> <code>{escape(item["reference"])}</code></li>'
        for item in guidance["deeperHelp"]
    )
    return (
        '<section class="section section--accent" aria-labelledby="step-guidance-title">'
        '<p class="eyebrow">Just-in-time guidance</p>'
        f'<h2 id="step-guidance-title">{escape(guidance["step"])} — {escape(guidance["title"])}</h2>'
        f'<p>{escape(guidance["whyItMatters"])}</p>'
        f'<p><strong>Canonical purpose:</strong> {escape(guidance["purpose"])}</p>'
        '<div class="guidance-grid">'
        '<div><span class="metric__label">Method and timebox</span>'
        f'<p>{escape(guidance["selectedMethod"])} · {guidance["suggestedTimeboxMinutes"]} minutes suggested · {escape(actual_text)}</p>'
        f'<p>{escape(guidance["selectedMethodRationale"])}</p></div>'
        '<div><span class="metric__label">Need from you</span>'
        f'<p>{escape(guidance["humanAction"])}</p></div>'
        '<div><span class="metric__label">AI can</span>'
        f'<p>{escape(ai_role)}</p></div>'
        '<div><span class="metric__label">Done when</span>'
        f'<p>{escape(done)}</p></div>'
        '</div>'
        '<details class="guidance"><summary>Show examples, checklist, substitutes, and troubleshooting</summary>'
        f'<h3>Expected human effort</h3><p>{escape(guidance["humanEffort"])}</p>'
        f'<h3>Dependencies</h3><p>{escape(dependencies)}</p>'
        f'<h3>What good looks like</h3><p>{escape(good)}</p>'
        f'<h3>Example</h3>{render_list(guidance["examples"])}'
        f'<h3>Failure modes</h3>{render_list(guidance["failureModes"])}'
        f'<h3>Limitations</h3>{render_list(guidance["limitations"])}'
        f'<h3>Approved substitutes</h3><ul>{substitute_items}</ul>'
        f'<h3>Available actions</h3><ul>{action_items}</ul>'
        f'<h3>Deeper help</h3><ul>{help_items}</ul>'
        '</details></section>'
    )


def render_fidelity_adaptations(state: dict[str, Any]) -> str:
    summary = state.get("fidelity", {}).get("summary", {})
    adaptations = summary.get("adaptations", [])
    if not isinstance(adaptations, list) or not adaptations:
        return "<li>No material adaptations recorded.</li>"
    output = []
    for item in adaptations:
        if not isinstance(item, dict):
            continue
        step_id = str(item.get("step", "Sprint"))
        step = step_name(step_id) if step_id in STEP_INDEX else step_id
        output.append(
            f"<li><strong>{escape(step)} — {escape(display_label(item.get('type')))}:</strong> "
            f"{escape(item.get('description', 'Documented adaptation'))}</li>"
        )
    return "\n".join(output) or "<li>No material adaptations recorded.</li>"


def render_fidelity_limitations(state: dict[str, Any]) -> str:
    summary = state.get("fidelity", {}).get("summary", {})
    limitations = summary.get("limitations", [])
    if not isinstance(limitations, list) or not limitations:
        return "<li>No additional limitations recorded.</li>"
    return "\n".join(f"<li>{escape(item)}</li>" for item in limitations)


def render_method_fidelity_section(state: dict[str, Any]) -> str:
    assessment = display_label(
        state.get("fidelity", {}).get("summary", {}).get("assessment")
    )
    validation_label, validation_notice, _validation_class = validation_truth(state)
    return (
        '<section class="section" aria-labelledby="method-fidelity-title">'
        '<p class="eyebrow">Method record</p>'
        '<h2 id="method-fidelity-title">Method-fidelity summary</h2>'
        '<div class="three-column">'
        '<div class="metric"><span class="metric__label">Method profile</span>'
        f'<span class="metric__value">{escape(display_label(state.get("methodProfile")))}</span></div>'
        '<div class="metric"><span class="metric__label">Execution mode</span>'
        f'<span class="metric__value">{escape(display_label(state.get("executionMode")))}</span></div>'
        '<div class="metric"><span class="metric__label">Terminal state</span>'
        f'<span class="metric__value">{escape(display_label(state.get("terminalState")))}</span></div>'
        '<div class="metric"><span class="metric__label">Method fidelity</span>'
        f'<span class="metric__value">{escape(assessment)}</span></div>'
        f'</div><h3>{escape(validation_label)}</h3><p>{escape(validation_notice)}</p>'
        '<h3>Adaptations</h3><ul>'
        f'{render_fidelity_adaptations(state)}</ul>'
        '<h3>Limitations</h3><ul>'
        f'{render_fidelity_limitations(state)}</ul></section>'
    )


def render_current_fidelity_guidance(state: dict[str, Any]) -> str:
    current = str(state.get("currentStep", "01-intake"))
    record = state.get("fidelity", {}).get("steps", {}).get(current, {})
    participants = record.get("participants", {})
    timebox = record.get("timebox", {})
    actual = timebox.get("actualMinutes")
    actual_text = "Not recorded yet" if actual is None else f"{actual} minutes"
    human = ", ".join(participants.get("human", [])) or "None recorded"
    ai = ", ".join(participants.get("ai", [])) or "None recorded"
    return (
        '<div class="guidance-grid">'
        '<div><span class="metric__label">Canonical purpose</span>'
        f'<p>{escape(record.get("canonicalPurpose", "Not recorded"))}</p></div>'
        '<div><span class="metric__label">Default method</span>'
        f'<p>{escape(record.get("defaultMethod", "Not recorded"))}</p></div>'
        '<div><span class="metric__label">Selected method</span>'
        f'<p>{escape(record.get("selectedMethod", "Not recorded"))}</p></div>'
        '<div><span class="metric__label">Timebox</span>'
        f'<p>Suggested: {escape(timebox.get("suggestedMinutes", "Unknown"))} minutes · '
        f'Actual: {escape(actual_text)}</p></div>'
        '<div><span class="metric__label">Human participants</span>'
        f'<p>{escape(human)}</p></div>'
        '<div><span class="metric__label">AI participants</span>'
        f'<p>{escape(ai)}</p></div></div>'
    )


def selected_material_findings(
    artifact_documents: list[tuple[Path, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Return the most decision-proximate material-finding set without duplicating it."""

    by_id = {str(data.get("id")): data for _path, data in artifact_documents}
    for artifact_id in ("13-outcome", "12-synthesis"):
        findings = by_id.get(artifact_id, {}).get("materialFindings", [])
        if isinstance(findings, list) and findings:
            return [item for item in findings if isinstance(item, dict)]
    findings: list[dict[str, Any]] = []
    for _path, data in artifact_documents:
        values = data.get("materialFindings", [])
        if isinstance(values, list):
            findings.extend(item for item in values if isinstance(item, dict))
    return findings


def outcome_assessment_from_documents(
    artifact_documents: list[tuple[Path, dict[str, Any]]],
) -> dict[str, Any]:
    for _path, data in artifact_documents:
        if data.get("id") == "13-outcome":
            outcome = data.get("outcomeAssessment", {})
            return outcome if isinstance(outcome, dict) else {}
    return {}


def evidence_band(usable: int) -> tuple[str, str]:
    if usable > 5:
        return "extended", "Extended"
    return EVIDENCE_BANDS.get(usable, EVIDENCE_BANDS[0])


def build_completion_assessment(
    workspace: Path,
    state: dict[str, Any],
    artifact_documents: list[tuple[Path, dict[str, Any]]],
) -> dict[str, Any]:
    """Derive four independent, descriptive dimensions from canonical records."""

    customer = state.get("customerTesting", {})
    if not isinstance(customer, dict):
        customer = {}
    manifest = load_session_manifest(workspace)
    entries = [
        item for item in manifest.get("sessions", []) if isinstance(item, dict)
    ]
    completed_steps = set(state.get("completedSteps", []))
    skipped_steps = set(state.get("skippedSteps", []))
    not_applicable_steps = set(state.get("notApplicableSteps", []))
    blocked_steps = {
        str(load_artifact_specs().get(str(data.get("id")), {}).get("step"))
        for _path, data in artifact_documents
        if data.get("status") == "blocked"
    }
    blocked_steps.discard("None")
    if customer.get("status") == "blocked":
        blocked_steps.add("11-customer-sessions")
    current = str(state.get("currentStep", "01-intake"))
    if state.get("status") == "complete" and str(state.get("outcome", "")).lower() == "stop":
        process_status = "stopped-deliberately"
    elif state.get("status") == "complete":
        process_status = "completed"
    elif blocked_steps or state.get("status") == "paused":
        process_status = "blocked"
    elif not completed_steps and current == "01-intake":
        process_status = "not-started"
    elif skipped_steps and current == "13-outcome":
        process_status = "partially-completed"
    else:
        process_status = "active"
    accounted = completed_steps | skipped_steps | not_applicable_steps | blocked_steps
    not_started_count = max(0, len(STEPS) - len(accounted) - (0 if current in accounted else 1))
    process = {
        "status": process_status,
        "label": display_label(process_status),
        "steps": {
            "completed": len(completed_steps),
            "skipped": len(skipped_steps),
            "blocked": len(blocked_steps),
            "notApplicable": len(not_applicable_steps),
            "notStarted": not_started_count,
        },
        "explanation": (
            "Workflow lifecycle and step dispositions are reported independently of "
            "method adherence and customer evidence."
        ),
    }

    usable_entries = [
        item
        for item in entries
        if item.get("counted") is True and item.get("usable") is True
    ]
    usable = int(customer.get("sessionsUsable", len(usable_entries)))
    attempted = int(customer.get("sessionsAttempted", 0))
    completed = int(customer.get("sessionsCompleted", 0))
    planned = int(customer.get("sessionsPlanned", 0))
    band, band_label = evidence_band(usable)
    segments = sorted(
        {
            str(item.get("participantSegment"))
            for item in usable_entries
            if str(item.get("participantSegment", "")).strip()
        }
    )
    prototype_versions = sorted(
        {str(item.get("prototypeVersion")) for item in usable_entries}
    )
    questions_versions = sorted(
        {str(item.get("questionsVersion")) for item in usable_entries}
    )
    critical_scenarios = sorted(
        {
            str(scenario)
            for item in usable_entries
            for scenario in item.get("criticalScenariosCovered", [])
        }
    )
    protocol_deviations = [
        str(item.get("sessionId"))
        for item in usable_entries
        if item.get("protocolFidelity") != "consistent"
    ]
    findings = selected_material_findings(artifact_documents)
    contradiction_count = sum(
        len(item.get("contradictions", []))
        for item in findings
        if isinstance(item.get("contradictions", []), list)
    )
    outlier_count = sum(
        len(item.get("outliers", []))
        for item in findings
        if isinstance(item.get("outliers", []), list)
    )
    inferred_findings = sum(
        item.get("directness") in {"inference", "mixed"} for item in findings
    )
    remaining_uncertainty_count = sum(
        len(item.get("remainingUncertainty", []))
        for item in findings
        if isinstance(item.get("remainingUncertainty", []), list)
    )
    moderator_deviation_sessions: list[str] = []
    for entry in usable_entries:
        try:
            summary_path = workspace_relative_file(
                workspace,
                str(entry["summaryPath"]),
                f"Evidence assessment summary {entry['sessionId']}",
            )
            summary = load_session_summary(summary_path)
        except SprintError:
            continue
        if summary.get("moderatorDeviations"):
            moderator_deviation_sessions.append(str(entry["sessionId"]))
    mixed_segments = len(segments) > 1
    mixed_versions = len(prototype_versions) > 1 or len(questions_versions) > 1
    unusable_completed = max(0, completed - usable)
    mixed_quality = bool(
        protocol_deviations
        or moderator_deviation_sessions
        or unusable_completed
        or int(customer.get("sessionsExcluded", 0))
    )
    mixed_evidence = contradiction_count > 0 or outlier_count > 0
    if usable == 0:
        quality = "not-tested"
    elif mixed_segments:
        quality = "mixed-segment"
    elif mixed_quality or mixed_versions or mixed_evidence:
        quality = "mixed-quality"
    else:
        quality = "consistent-directional"
    factors = [
        f"{usable} usable of {attempted} attempted session(s).",
        f"Participant fit: {customer.get('sessionsQualified', 0)} qualified and {customer.get('sessionsExcluded', 0)} excluded.",
        (
            f"Target-segment coverage: {', '.join(segments)}."
            if segments
            else "No usable target-segment coverage is recorded."
        ),
        (
            f"Tested versions: prototype {', '.join(prototype_versions)}; questions {', '.join(questions_versions)}."
            if usable_entries
            else "No usable prototype or question version is tested."
        ),
        (
            f"Critical-scenario coverage: {', '.join(critical_scenarios)}."
            if critical_scenarios
            else "No usable critical-scenario coverage is recorded."
        ),
        f"Material findings retain {contradiction_count} contradiction record(s), {outlier_count} outlier record(s), {inferred_findings} inferred or mixed finding(s), and {remaining_uncertainty_count} remaining uncertainty item(s).",
    ]
    limitations: list[str] = []
    if state.get("executionMode") != "live":
        limitations.append(
            "This is a rehearsal mode; synthetic activity is not customer evidence."
        )
    elif usable == 0:
        limitations.append(
            "No usable real-customer session exists, so customer-dependent decisions remain untested."
        )
    if planned and usable < planned:
        limitations.append(
            f"Only {usable}/{planned} planned sessions are usable; the remaining sample and prevalence are unknown."
        )
    if unusable_completed:
        limitations.append(
            f"{unusable_completed} completed session(s) are not usable because participant fit or evidence quality was insufficient."
        )
    if mixed_segments:
        limitations.append(
            "Usable sessions span multiple customer segments; counts cannot be treated as within-segment convergence."
        )
    if mixed_versions:
        limitations.append(
            "Usable sessions used different prototype or question versions, so apparent differences may be version effects."
        )
    if protocol_deviations:
        limitations.append(
            "Usable sessions include documented protocol deviations: "
            + ", ".join(protocol_deviations)
            + "."
        )
    if moderator_deviation_sessions:
        limitations.append(
            "Usable summaries contain moderator deviations: "
            + ", ".join(moderator_deviation_sessions)
            + "."
        )
    if contradiction_count:
        limitations.append(
            "Material findings contain contradictory observations that remain unresolved."
        )
    if outlier_count:
        limitations.append(
            "Material findings retain outlying observations that should be investigated rather than averaged away."
        )
    if usable:
        limitations.append(
            "These descriptive bands report method coverage only; they do not establish statistical confidence, representativeness, or population prevalence."
        )
    evidence = {
        "band": band,
        "label": band_label,
        "quality": quality,
        "description": (
            f"{band_label}: {usable} suitable usable session(s), assessed with participant fit, "
            "protocol consistency, versions, segment coverage, contradictions, directness, and uncertainty."
        ),
        "factors": factors,
        "limitations": limitations,
        "mixedSegments": mixed_segments,
        "mixedVersions": mixed_versions,
        "mixedQuality": mixed_quality,
        "mixedEvidence": mixed_evidence,
    }

    outcome = outcome_assessment_from_documents(artifact_documents)
    proposed_impact = str(outcome.get("decisionImpact", ""))
    if proposed_impact not in DECISION_IMPACTS:
        finding_impacts = {
            str(item.get("nextDecision", {}).get("impact"))
            for item in findings
            if isinstance(item.get("nextDecision"), dict)
        }
        if "correct-observed-failure" in finding_impacts:
            proposed_impact = "correct-observed-failure"
        elif "bounded-reversible-investment" in finding_impacts:
            proposed_impact = "bounded-reversible-investment"
        else:
            proposed_impact = "investigate-or-retest"
    proposed_action = str(outcome.get("justifiedDecision", "")).strip() or (
        "Record the specific proposed action in the outcome assessment."
    )
    if state.get("executionMode") != "live" or usable == 0:
        readiness = "insufficient-to-decide"
        reason = "No usable real-customer evidence supports a customer-dependent decision."
    elif proposed_impact == "defer-large-or-irreversible-investment":
        readiness = "insufficient-for-large-or-irreversible-investment"
        reason = (
            "Directional sprint evidence cannot justify population claims or a large, irreversible commitment."
        )
    elif proposed_impact == "correct-observed-failure" and any(
        item.get("directness") in {"direct-observation", "mixed"}
        for item in findings
    ):
        readiness = "sufficient-to-correct-an-observed-failure"
        reason = (
            "Traceable direct observations justify correcting the bounded failure and retesting; they do not prove prevalence."
        )
    elif (
        proposed_impact == "bounded-reversible-investment"
        and planned > 0
        and usable >= planned
        and band not in {"not-tested", "early-limited"}
        and findings
        and not (mixed_segments or mixed_versions or mixed_quality or mixed_evidence)
    ):
        readiness = "sufficient-for-a-bounded-reversible-investment"
        reason = (
            "The planned method target is met with consistent, qualified, traceable evidence; the investment must remain bounded and reversible."
        )
    else:
        readiness = "sufficient-to-investigate-or-run-another-test"
        reason = (
            "The observed sample can direct the next learning step, but remaining coverage or quality limitations constrain a stronger action."
        )
    decision = {
        "status": readiness,
        "label": display_label(readiness),
        "proposedAction": proposed_action,
        "reason": reason,
    }
    fidelity_summary = state.get("fidelity", {}).get("summary", {})
    return {
        "processStatus": process,
        "methodFidelity": {
            "status": str(fidelity_summary.get("assessment", "unknown")),
            "label": display_label(fidelity_summary.get("assessment")),
            "adaptations": fidelity_summary.get("adaptations", []),
            "limitations": fidelity_summary.get("limitations", []),
        },
        "evidenceStrength": evidence,
        "decisionReadiness": decision,
        "sessionCounts": {
            "planned": planned,
            "invited": int(customer.get("sessionsInvited", 0)),
            "attempted": attempted,
            "completed": completed,
            "qualified": int(customer.get("sessionsQualified", 0)),
            "excluded": int(customer.get("sessionsExcluded", 0)),
            "usable": usable,
        },
        "materialFindings": findings,
        "limitations": limitations,
    }


def render_completion_dimensions(assessment: dict[str, Any]) -> str:
    cards = []
    for key, title, detail_key in (
        ("processStatus", "Process status", "explanation"),
        ("methodFidelity", "Method fidelity", "status"),
        ("evidenceStrength", "Evidence strength", "description"),
        ("decisionReadiness", "Decision readiness", "reason"),
    ):
        value = assessment[key]
        detail = value.get(detail_key, "")
        if key == "methodFidelity":
            detail = (
                "Method adherence is derived from the selected profile, route, mode, "
                "documented adaptations, omissions, and testing shortfall."
            )
        cards.append(
            '<article class="assessment-card">'
            f'<span class="metric__label">{escape(title)}</span>'
            f'<strong>{escape(value.get("label", "Unknown"))}</strong>'
            f'<p>{escape(detail)}</p>'
            "</article>"
        )
    return "\n".join(cards)


def render_session_counts(assessment: dict[str, Any]) -> str:
    counts = assessment["sessionCounts"]
    return "\n".join(
        '<div class="metric metric--compact">'
        f'<span class="metric__label">{escape(display_label(name))}</span>'
        f'<span class="metric__value">{escape(value)}</span></div>'
        for name, value in counts.items()
    )


def render_assessment_limitations(assessment: dict[str, Any]) -> str:
    limitations = assessment.get("limitations", [])
    if not limitations:
        return "<li>No automatic evidence limitations apply yet.</li>"
    return "\n".join(f"<li>{escape(item)}</li>" for item in limitations)


def render_material_findings(assessment: dict[str, Any]) -> str:
    findings = assessment.get("materialFindings", [])
    if not findings:
        return (
            '<p>No material customer finding is recorded. Rehearsal and untested claims '
            "do not appear as customer evidence.</p>"
        )
    usable = int(assessment.get("sessionCounts", {}).get("usable", 0))
    output: list[str] = []
    for finding in findings:
        support = finding.get("support", [])
        contradictions = finding.get("contradictions", [])
        outliers = finding.get("outliers", [])
        supporting_sessions = {
            str(item.get("sessionId")) for item in support if isinstance(item, dict)
        }
        provenance_items = []
        for label, sources in (
            ("Supports", support),
            ("Contradicts", contradictions),
            ("Outlier", outliers),
        ):
            for source in sources:
                if not isinstance(source, dict):
                    continue
                provenance_items.append(
                    "<li>"
                    f"<strong>{escape(label)}:</strong> {escape(source.get('participantId'))} / "
                    f"{escape(source.get('sessionId'))} · prototype {escape(source.get('prototypeVersion'))} · "
                    f"questions {escape(source.get('questionsVersion'))} · {escape(display_label(source.get('sourceType')))} "
                    f"({escape(', '.join(source.get('evidenceIds', [])))})</li>"
                )
        automatic = list(finding.get("limitations", []))
        if contradictions:
            automatic.append(
                f"{len(contradictions)} contradictory provenance record(s) remain visible."
            )
        if outliers:
            automatic.append(
                f"{len(outliers)} outlier provenance record(s) remain visible."
            )
        if len(supporting_sessions) < usable:
            automatic.append(
                f"This finding is supported by {len(supporting_sessions)} of {usable} usable sessions; non-supporting sessions are not silently counted as agreement."
            )
        for item in assessment.get("limitations", []):
            if item not in automatic:
                automatic.append(item)
        decision = finding.get("nextDecision", {})
        output.append(
            '<article class="finding-card">'
            f'<p class="eyebrow">{escape(finding.get("id"))} · {len(supporting_sessions)}/{usable} usable support</p>'
            f'<h3>{escape(finding.get("statement"))}</h3>'
            f'<p><strong>Directness:</strong> {escape(display_label(finding.get("directness")))}</p>'
            '<h4>Support, contradictions, and provenance</h4><ul>'
            + ("\n".join(provenance_items) or "<li>No provenance recorded.</li>")
            + "</ul><h4>Limitations and remaining uncertainty</h4><ul>"
            + "\n".join(f"<li>{escape(item)}</li>" for item in automatic)
            + "\n"
            + "\n".join(
                f"<li>{escape(item)}</li>"
                for item in finding.get("remainingUncertainty", [])
            )
            + "</ul><h4>Next decision</h4>"
            f'<p><strong>{escape(display_label(decision.get("impact")))}</strong>: '
            f'{escape(decision.get("action"))}</p>'
            f'<p>{escape(decision.get("rationale"))}</p>'
            f'<p><strong>Smallest next learning action:</strong> {escape(decision.get("smallestNextLearningAction"))}</p>'
            "</article>"
        )
    return "\n".join(output)


def render_outcome_statements(data: dict[str, Any]) -> str:
    outcome = data.get("outcomeAssessment", {})
    if not isinstance(outcome, dict):
        return ""
    labels = (
        ("Process completed", "processCompleted"),
        ("Method adaptations", "methodAdaptations"),
        ("Evidence supports", "evidenceSupports"),
        ("Evidence cannot support", "evidenceCannotSupport"),
        ("Justified decision", "justifiedDecision"),
        ("Smallest next learning action", "smallestNextLearningAction"),
    )
    return (
        '<section class="section" aria-labelledby="outcome-statements-title">'
        '<p class="eyebrow">Explicit handoff</p>'
        '<h2 id="outcome-statements-title">Outcome boundaries and next learning</h2>'
        '<dl class="definition-list">'
        + "\n".join(
            f"<dt>{escape(label)}</dt><dd>{escape(outcome.get(key) or 'Not established yet.')}</dd>"
            for label, key in labels
        )
        + "</dl></section>"
    )


def text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            output.extend(text_values(item))
        return output
    if isinstance(value, dict):
        output = []
        for item in value.values():
            output.extend(text_values(item))
        return output
    return []


def negates_customer_claim(value: str) -> bool:
    lowered = value.lower()
    return bool(
        re.search(
            r"\b(?:no|not|never|without|cannot|did not|was not|were not|unvalidated)\b[^.]{0,80}\b(?:customer|session|interview|validation|evidence)",
            lowered,
        )
    )


def evidence_claim_errors(data: dict[str, Any], state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    artifact_id = data.get("id")
    mode = state.get("executionMode")
    customer = state.get("customerTesting", {})
    completed_value = customer.get("sessionsCompleted", 0)
    completed = completed_value if isinstance(completed_value, int) else 0
    live_evidence_available = mode == "live" and completed > 0
    if artifact_id == "11-customer-evidence":
        if mode != "live" and data.get("status") in {
            "ready-for-decision",
            "complete",
        }:
            errors.append(
                f"Execution mode {mode} cannot complete a customer-evidence artifact"
            )
        if mode == "live" and completed == 0 and data.get("status") in {
            "ready-for-decision",
            "complete",
        }:
            errors.append(
                "Customer evidence cannot be completed before a real session is recorded"
            )
    customer_claim_pattern = re.compile(
        r"\b(?:customer[- ]validated|validated\s+(?:by|with)\s+(?:real\s+)?customers?|live\s+customer\s+evidence|real\s+customer\s+sessions?\s+(?:were\s+)?(?:completed|conducted)|tested\s+with\s+(?:real\s+)?customers?)\b",
        re.IGNORECASE,
    )
    overclaim_pattern = re.compile(
        r"\b(?:statistically\s+(?:validated|significant|proven)|universally\s+validated|proven\s+(?:by|with)\s+customers?|guaranteed\s+customer\s+validation)\b",
        re.IGNORECASE,
    )
    for value in text_values(data):
        if overclaim_pattern.search(value) and not negates_customer_claim(value):
            errors.append(
                "Customer evidence is directional and cannot be described as statistical, universal, or proven validation"
            )
            break
    if not live_evidence_available:
        for value in text_values(data):
            if customer_claim_pattern.search(value) and not negates_customer_claim(value):
                errors.append(
                    "Artifact claims live customer evidence that the execution mode and recorded sessions do not support"
                )
                break
    evidence = data.get("evidence", [])
    if isinstance(evidence, list):
        for index, item in enumerate(evidence, 1):
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim", ""))
            source = str(item.get("source", ""))
            combined = f"{claim} {source}"
            if (
                item.get("status") == "Observed"
                and re.search(r"\b(?:customers?|participants?|sessions?|interviews?)\b", combined, re.I)
                and not live_evidence_available
                and not negates_customer_claim(claim)
            ):
                errors.append(
                    f"Evidence entry {index} labels a customer claim Observed without a recorded live customer session"
                )
            if item.get("status") == "Observed" and re.search(
                r"\b(?:synthetic rehearsal|placeholder|assumption|hypothesis)\b",
                source,
                re.I,
            ):
                errors.append(
                    f"Evidence entry {index} cannot label a synthetic, placeholder, assumed, or hypothetical source as Observed"
                )
    return errors


def approved_prototype_brief_snapshot(brief: dict[str, Any]) -> dict[str, Any]:
    """Return the approved build boundary without later operational history."""

    snapshot = copy.deepcopy(brief)
    snapshot["buildPackets"] = []
    snapshot["trialRuns"] = []
    snapshot["versions"] = []
    snapshot["currentVersion"] = None
    return snapshot


def prototype_brief_digest(brief: dict[str, Any]) -> str:
    return sha256_bytes(json_text(approved_prototype_brief_snapshot(brief)).encode("utf-8"))


def prototype_brief_errors(
    brief: dict[str, Any], *, require_approved: bool
) -> list[str]:
    errors: list[str] = []
    level = str(brief.get("artifactLevel", ""))
    scenes = brief.get("experience", {}).get("criticalScenes", [])
    scene_ids = [item.get("id") for item in scenes if isinstance(item, dict)]
    if len(scene_ids) != len(set(scene_ids)):
        errors.append("$.prototypeBrief.experience.criticalScenes: scene IDs must be unique")

    capabilities = brief.get("capabilities", {})
    real_capabilities = sorted(
        key
        for key, value in capabilities.items()
        if key != "notes" and value is True
    )
    if real_capabilities and level in ARTIFACT_LADDER[:4]:
        errors.append(
            "$.prototypeBrief.artifactLevel: real capabilities require live-mvp or limited-pilot; "
            f"found {level} with {', '.join(real_capabilities)}"
        )

    tool = brief.get("toolSelection", {})
    if tool.get("route") == "no-external-tool":
        if tool.get("requiresExternalAccount"):
            errors.append(
                "$.prototypeBrief.toolSelection: a no-external-tool route cannot require an external account"
            )
        if tool.get("category") not in {"none", "native-repository"}:
            errors.append(
                "$.prototypeBrief.toolSelection.category: a no-external-tool route must use none or native-repository"
            )

    deployment = brief.get("deploymentPlan", {})
    if deployment.get("public") != (deployment.get("accessModel") == "public"):
        errors.append(
            "$.prototypeBrief.deploymentPlan: public must agree with accessModel"
        )
    if deployment.get("public") and not deployment.get("url"):
        errors.append(
            "$.prototypeBrief.deploymentPlan.url: a planned public deployment requires an approved URL"
        )

    trial_ids = [
        item.get("id") for item in brief.get("trialRuns", []) if isinstance(item, dict)
    ]
    if len(trial_ids) != len(set(trial_ids)):
        errors.append("$.prototypeBrief.trialRuns: trial-run IDs must be unique")
    version_ids = [
        item.get("version") for item in brief.get("versions", []) if isinstance(item, dict)
    ]
    if len(version_ids) != len(set(version_ids)):
        errors.append("$.prototypeBrief.versions: tested-version IDs must be unique")
    current = brief.get("currentVersion")
    if current is not None and current not in version_ids:
        errors.append(
            "$.prototypeBrief.currentVersion: current version is absent from the immutable version catalog"
        )

    if require_approved:
        if any(
            value.strip().lower() == "not established yet."
            for value in text_values(approved_prototype_brief_snapshot(brief))
            if isinstance(value, str)
        ):
            errors.append(
                "$.prototypeBrief: an approved brief cannot contain draft placeholders"
            )
        approvals = brief.get("approvals", {})
        for boundary, key in PROTOTYPE_APPROVAL_BOUNDARIES.items():
            approval = approvals.get(key, {})
            status = approval.get("status")
            if status == "pending":
                errors.append(
                    f"$.prototypeBrief.approvals.{key}: {boundary} requires a human decision"
                )
                continue
            if not str(approval.get("deciderLabel", "")).strip():
                errors.append(
                    f"$.prototypeBrief.approvals.{key}.deciderLabel: approval requires a human-safe Decider label"
                )
            if not str(approval.get("rationale", "")).strip():
                errors.append(
                    f"$.prototypeBrief.approvals.{key}.rationale: approval requires a rationale"
                )
            if not approval.get("decidedAt"):
                errors.append(
                    f"$.prototypeBrief.approvals.{key}.decidedAt: approval requires a timestamp"
                )
        for key in ("experimentBoundary", "toolChoice"):
            if approvals.get(key, {}).get("status") != "approved":
                errors.append(
                    f"$.prototypeBrief.approvals.{key}: this boundary must be explicitly approved"
                )
        if tool.get("requiresExternalAccount") and approvals.get(
            "externalAccount", {}
        ).get("status") != "approved":
            errors.append(
                "$.prototypeBrief.approvals.externalAccount: an external account cannot be connected without explicit approval"
            )
        if deployment.get("public") and approvals.get(
            "publicDeployment", {}
        ).get("status") != "approved":
            errors.append(
                "$.prototypeBrief.approvals.publicDeployment: public deployment requires explicit approval"
            )
        if brief.get("evidenceCapture", {}).get("analytics", {}).get("enabled") and approvals.get(
            "dataExposure", {}
        ).get("status") != "approved":
            errors.append(
                "$.prototypeBrief.approvals.dataExposure: analytics cannot be enabled without explicit approval"
            )
    return errors


def recruitment_plan_errors(
    plan: Any,
    *,
    require_ready: bool,
    state: dict[str, Any] | None = None,
) -> list[str]:
    """Enforce operational recruitment readiness above the nested JSON shape."""

    if not isinstance(plan, dict):
        return (
            ["$.recruitmentPlan: create the structured recruitment plan during 03-evidence"]
            if require_ready
            else []
        )
    errors: list[str] = []
    if plan.get("paidVendorRequired") is not False:
        errors.append(
            "$.recruitmentPlan.paidVendorRequired: recruitment must retain a no-paid-vendor route"
        )
    if not require_ready:
        return errors

    def text_items(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            values: list[str] = []
            for item in value.values():
                values.extend(text_items(item))
            return values
        if isinstance(value, list):
            values = []
            for item in value:
                values.extend(text_items(item))
            return values
        return []

    placeholders = [
        value
        for value in text_items(plan)
        if value.strip().lower() == "not established yet."
        or re.search(r"\[[^\]]+\]", value)
    ]
    if placeholders:
        errors.append(
            "$.recruitmentPlan: replace every draft or bracketed template placeholder before evidence completes"
        )

    target = plan.get("targetDefinition", {})
    if int(target.get("backupParticipants", 0) or 0) < 1:
        errors.append(
            "$.recruitmentPlan.targetDefinition.backupParticipants: plan at least one suitable backup"
        )
    screener = plan.get("screener", {})
    if screener.get("status") != "approved":
        errors.append(
            "$.recruitmentPlan.screener.status: the human must approve the neutral screener"
        )
    if any(
        item.get("revealsPreferredAnswer") is not False
        for item in screener.get("questions", [])
        if isinstance(item, dict)
    ):
        errors.append(
            "$.recruitmentPlan.screener.questions: every question must remain neutral"
        )
    channels = plan.get("channels", [])
    if not any(item.get("selected") is True for item in channels if isinstance(item, dict)):
        errors.append(
            "$.recruitmentPlan.channels: select at least one route and retain its trade-off"
        )
    incentive = plan.get("incentive", {})
    if incentive.get("spendingRequired") and incentive.get("approvalStatus") != "approved":
        errors.append(
            "$.recruitmentPlan.incentive.approvalStatus: human approval is required before spending"
        )
    if incentive.get("approvalStatus") == "approved" and not str(
        incentive.get("approvedBy", "")
    ).strip():
        errors.append(
            "$.recruitmentPlan.incentive.approvedBy: name a human-safe approver label"
        )
    partial = str(
        plan.get("backupPlan", {}).get("partialRecruitmentHandling", "")
    ).lower()
    if "partial" not in partial or "target" not in partial:
        errors.append(
            "$.recruitmentPlan.backupPlan.partialRecruitmentHandling: keep the target visible and describe partial evidence handling"
        )

    tracking = plan.get("tracking", {})
    if tracking.get("status") == "draft":
        errors.append(
            "$.recruitmentPlan.tracking.status: mark the tailored plan ready, recruiting, scheduled, partial, complete, or blocked"
        )
    milestones = tracking.get("milestones", {})
    for key in ("targetDefined", "screenerApproved", "consentReady"):
        if milestones.get(key) != "complete":
            errors.append(
                f"$.recruitmentPlan.tracking.milestones.{key}: complete this evidence-stage milestone"
            )

    if state is not None and state.get("executionMode") == "live":
        customer = state.get("customerTesting", {})
        planned = int(customer.get("sessionsPlanned", 0) or 0)
        plan_target = int(target.get("targetSessions", 0) or 0)
        if planned != plan_target:
            errors.append(
                "$.recruitmentPlan.targetDefinition.targetSessions: match the canonical customer-testing plan"
            )
        if str(customer.get("target", "")).strip() != str(
            target.get("audience", "")
        ).strip():
            errors.append(
                "$.recruitmentPlan.targetDefinition.audience: match the canonical customer-testing target"
            )
        if not str(customer.get("targetRationale", "")).strip():
            errors.append(
                "$.customerTesting.targetRationale: record why this live target fits the challenge"
            )
    return errors


def load_recruitment_plan_artifact(
    workspace: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    path = workspace / "artifact-data" / f"{TEST_PLAN_ID}.json"
    if not path.is_file():
        raise SprintError(
            "Create 10-test-plan during 03-evidence so recruitment can start before prototyping"
        )
    data = load_artifact_data(path)
    plan = data.get("recruitmentPlan")
    if not isinstance(plan, dict):
        raise SprintError(
            "10-test-plan is missing its structured recruitmentPlan; create or migrate the plan before continuing"
        )
    return path, data, plan


def artifact_data_errors(
    data: dict[str, Any], specs: dict[str, dict[str, Any]]
) -> list[str]:
    """Return artifact completion rules that are intentionally above schema shape."""

    errors: list[str] = []
    if data.get("schemaVersion") != ARTIFACT_SCHEMA_VERSION:
        errors.append(f"Unsupported artifact schema: {data.get('schemaVersion')}")
    artifact_id = data.get("id")
    if artifact_id not in specs:
        errors.append(f"$.id: unknown artifact id {artifact_id!r}")
        return errors
    if artifact_id == PROTOTYPE_BRIEF_ID:
        brief = data.get("prototypeBrief")
        if isinstance(brief, dict):
            errors.extend(
                prototype_brief_errors(
                    brief,
                    require_approved=data.get("status")
                    in {"ready-for-decision", "complete"},
                )
            )
    if artifact_id == TEST_PLAN_ID:
        errors.extend(
            recruitment_plan_errors(
                data.get("recruitmentPlan"),
                require_ready=False,
            )
        )
    sections = data.get("sections")
    assert isinstance(sections, list)
    section_indexes: dict[str, int] = {}
    for index, section in enumerate(sections):
        if not isinstance(section, dict) or not isinstance(
            section.get("title"), str
        ):
            continue
        title = section["title"]
        if title in section_indexes:
            errors.append(
                f"$.sections[{index}].title: duplicate section title {title!r}"
            )
        section_indexes[title] = index
    for required in specs[artifact_id].get("requiredSections", []):
        if required not in section_indexes:
            errors.append(f"$.sections: missing required section {required!r}")
    if data.get("status") in {"ready-for-decision", "complete"}:
        if not nested_has_content(data.get("summary")):
            errors.append(
                "$.summary: ready or complete artifacts require a non-empty summary"
            )
        for required in specs[artifact_id].get("requiredSections", []):
            section = next(
                (
                    item
                    for item in sections
                    if isinstance(item, dict) and item.get("title") == required
                ),
                None,
            )
            if section is None or not section_has_content(section):
                section_path = (
                    f"$.sections[{section_indexes[required]}]"
                    if required in section_indexes
                    else "$.sections"
                )
                errors.append(
                    f"{section_path}: Required section is still empty: {required}"
                )
        if any(
            str(item).strip().lower() == "this artifact is in progress."
            for item in data.get("summary", [])
        ):
            errors.append("$.summary: completed artifact still has the draft summary")
    for index, item in enumerate(data.get("evidence", [])):
        if not isinstance(item, dict):
            continue
        for field in ("claim", "source"):
            if not meaningful_text(item.get(field)):
                errors.append(
                    f"$.evidence[{index}].{field}: evidence text cannot be blank"
                )
    findings = data.get("materialFindings", [])
    finding_ids = [
        item.get("id") for item in findings if isinstance(item, dict)
    ]
    if len(finding_ids) != len(set(finding_ids)):
        errors.append("$.materialFindings: material finding IDs must be unique")
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            continue
        support_keys = [
            (
                item.get("sessionId"),
                item.get("sourceType"),
                tuple(item.get("evidenceIds", [])),
            )
            for item in finding.get("support", [])
            if isinstance(item, dict)
        ]
        contradiction_keys = [
            (
                item.get("sessionId"),
                item.get("sourceType"),
                tuple(item.get("evidenceIds", [])),
            )
            for item in finding.get("contradictions", [])
            if isinstance(item, dict)
        ]
        outlier_keys = [
            (
                item.get("sessionId"),
                item.get("sourceType"),
                tuple(item.get("evidenceIds", [])),
            )
            for item in finding.get("outliers", [])
            if isinstance(item, dict)
        ]
        if len(support_keys) != len(set(support_keys)):
            errors.append(
                f"$.materialFindings[{index}].support: duplicate provenance records"
            )
        if len(contradiction_keys) != len(set(contradiction_keys)):
            errors.append(
                f"$.materialFindings[{index}].contradictions: duplicate provenance records"
            )
        if len(outlier_keys) != len(set(outlier_keys)):
            errors.append(
                f"$.materialFindings[{index}].outliers: duplicate provenance records"
            )
        if (
            set(support_keys) & set(contradiction_keys)
            or set(support_keys) & set(outlier_keys)
            or set(contradiction_keys) & set(outlier_keys)
        ):
            errors.append(
                f"$.materialFindings[{index}]: the same evidence cannot be support, contradiction, or outlier more than once"
            )
    if artifact_id == "13-outcome" and data.get("status") in {
        "ready-for-decision",
        "complete",
    }:
        outcome = data.get("outcomeAssessment", {})
        for field in (
            "processCompleted",
            "methodAdaptations",
            "evidenceSupports",
            "evidenceCannotSupport",
            "justifiedDecision",
            "smallestNextLearningAction",
        ):
            if not meaningful_text(outcome.get(field)):
                errors.append(
                    f"$.outcomeAssessment.{field}: a ready outcome must state this explicitly"
                )
    return errors


EMPTY_CONTENT_MARKERS = {
    "not established yet.",
    "nothing recorded yet.",
    "no evidence entries recorded yet.",
}


def meaningful_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value.strip().lower() not in EMPTY_CONTENT_MARKERS
    )


def nested_has_content(value: Any) -> bool:
    if isinstance(value, str):
        return meaningful_text(value)
    if isinstance(value, dict):
        return any(nested_has_content(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(nested_has_content(item) for item in value)
    return value is not None


def section_has_content(section: dict[str, Any]) -> bool:
    section_type = section.get("type", "paragraphs")
    if section_type in {"list", "ordered-list"}:
        return nested_has_content(section.get("items", []))
    if section_type == "table":
        rows = section.get("rows", [])
        return isinstance(rows, list) and any(
            isinstance(row, list) and nested_has_content(row) for row in rows
        )
    if section_type == "cards":
        cards = section.get("cards", [])
        return isinstance(cards, list) and any(
            isinstance(card, dict)
            and meaningful_text(card.get("title"))
            and meaningful_text(card.get("body"))
            for card in cards
        )
    if section_type == "key-value":
        items = section.get("items", [])
        return isinstance(items, list) and any(
            isinstance(item, dict) and meaningful_text(item.get("value"))
            for item in items
        )
    return nested_has_content(
        section.get("paragraphs", section.get("body", []))
    )


def site_page_disposition(state: dict[str, Any], step_id: str | None) -> str:
    if step_id is None:
        return "supporting"
    if step_id in state.get("notApplicableSteps", []):
        return "not-applicable"
    if step_id in state.get("skippedSteps", []):
        return "skipped"
    if step_id in state.get("completedSteps", []):
        return "completed"
    if step_id == state.get("currentStep"):
        return "current"
    return "upcoming"


def site_relative_href(current_path: str, target_path: str) -> str:
    current_parent = PurePosixPath(current_path).parent.as_posix()
    start = "." if current_parent == "." else current_parent
    return posixpath.relpath(target_path, start=start)


def build_site_manifest(
    workspace: Path,
    state: dict[str, Any],
    specs: dict[str, dict[str, Any]],
    artifact_documents: list[tuple[Path, dict[str, Any]]],
    *,
    visibility: str = "private",
    artifact_ids: set[str] | None = None,
    session_ids: set[str] | None = None,
    include_prototype: bool = True,
    export_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the sole page and relationship model used by every rendered view."""

    if visibility not in {"private", "shareable"}:
        raise SprintError(f"Unsupported site visibility: {visibility}")
    artifact_order = {
        artifact_id: (index + 1) * 100
        for index, artifact_id in enumerate(specs)
    }
    pages: list[dict[str, Any]] = []
    page_order: dict[str, int] = {"home": 0}
    zero_digest = "0" * 64
    pages.append(
        {
            "id": "home",
            "type": "dashboard",
            "title": "Sprint dashboard",
            "path": "index.html",
            "phase": "Overview",
            "status": str(state.get("status", "active")),
            "disposition": "current" if state.get("currentStep") == "01-intake" else "supporting",
            "visibility": visibility,
            "sourceVersion": f"workspace-state:{state.get('schemaVersion')}",
            "contentDigest": zero_digest,
            "renderDigest": zero_digest,
            "relationships": {},
        }
    )

    included_artifacts: list[tuple[Path, dict[str, Any]]] = []
    for data_path, data in artifact_documents:
        artifact_id = str(data["id"])
        if artifact_ids is not None and artifact_id not in artifact_ids:
            continue
        included_artifacts.append((data_path, data))
    included_artifacts.sort(key=lambda item: artifact_order[str(item[1]["id"])])
    for data_path, data in included_artifacts:
        artifact_id = str(data["id"])
        spec = specs[artifact_id]
        page_order[artifact_id] = artifact_order[artifact_id]
        pages.append(
            {
                "id": artifact_id,
                "type": "artifact",
                "title": str(spec["title"]),
                "path": f"artifacts/{spec['filename']}",
                "phase": str(spec["phase"]),
                "status": str(data.get("status", "draft")),
                "disposition": site_page_disposition(state, str(spec["step"])),
                "visibility": visibility,
                "sourceVersion": f"artifact-data:{data.get('schemaVersion')}",
                "contentDigest": sha256_bytes(data_path.read_bytes()),
                "renderDigest": zero_digest,
                "relationships": {},
            }
        )

    prototype_brief = next(
        (
            data.get("prototypeBrief")
            for _path, data in artifact_documents
            if data.get("id") == PROTOTYPE_BRIEF_ID
        ),
        None,
    )
    if include_prototype and isinstance(prototype_brief, dict):
        current_version = prototype_brief.get("currentVersion")
        version_summary = next(
            (
                item
                for item in prototype_brief.get("versions", [])
                if isinstance(item, dict) and item.get("version") == current_version
            ),
            None,
        )
        if version_summary is not None:
            record_path = workspace_relative_file(
                workspace,
                str(version_summary["recordPath"]),
                "Current tested-version record",
            )
            record = load_tested_version(record_path)
            page_order["prototype"] = artifact_order.get("10-test-plan", 1050) + 50
            pages.append(
                {
                    "id": "prototype",
                    "type": "prototype-launch",
                    "title": f"Tested prototype {current_version}",
                    "path": "prototype-launch.html",
                    "phase": "Prototype",
                    "status": "frozen",
                    "disposition": "supporting",
                    "visibility": visibility,
                    "sourceVersion": f"tested-version:{record.get('schemaVersion')}",
                    "contentDigest": sha256_bytes(record_path.read_bytes()),
                    "renderDigest": zero_digest,
                    "relationships": {},
                    "prototype": {
                        "version": str(current_version),
                        "artifactPath": str(record["prototypeArtifact"]["path"]),
                        "accessModel": str(record["deployment"]["accessModel"]),
                        "deploymentUrl": record["deployment"].get("url"),
                    },
                }
            )

    customer_manifest_path = manifest_path(workspace)
    if customer_manifest_path.exists():
        customer_manifest = load_session_manifest(workspace)
        for index, entry in enumerate(customer_manifest.get("sessions", []), start=1):
            session_id = str(entry["sessionId"])
            if session_ids is not None and session_id not in session_ids:
                continue
            summary_path = workspace_relative_file(
                workspace, str(entry["summaryPath"]), f"Session {session_id} summary"
            )
            summary = load_session_summary(summary_path)
            page_id = f"session:{session_id}"
            page_order[page_id] = artifact_order.get("11-customer-evidence", 1200) + index
            pages.append(
                {
                    "id": page_id,
                    "type": "session-evidence",
                    "title": f"Session {session_id} evidence",
                    "path": f"session-evidence/{session_id}.html",
                    "phase": "Customer evidence",
                    "status": str(summary.get("status", "draft")),
                    "disposition": "supporting",
                    "visibility": visibility,
                    "sourceVersion": f"session-summary:{summary.get('schemaVersion')}",
                    "contentDigest": sha256_bytes(summary_path.read_bytes()),
                    "renderDigest": zero_digest,
                    "relationships": {},
                }
            )

    pages.sort(key=lambda page: (page_order[page["id"]], page["id"]))
    by_id = {page["id"]: page for page in pages}
    eligible = [
        page
        for page in pages
        if page["id"] == "home"
        or page["disposition"] not in {"skipped", "not-applicable"}
    ]
    eligible_ids = {page["id"] for page in eligible}

    def relationship_if_available(page_id: str, current_id: str) -> str | None:
        return page_id if page_id in eligible_ids and page_id != current_id else None

    for page in pages:
        page_id = str(page["id"])
        order = page_order[page_id]
        previous_candidates = [
            item for item in eligible if page_order[item["id"]] < order
        ]
        next_candidates = [
            item for item in eligible if page_order[item["id"]] > order
        ]
        related: list[str]
        if page["type"] == "artifact":
            related = [
                item
                for item in specs[page_id].get("relatedEvidence", [])
                if item in eligible_ids and item != page_id
            ]
            if page_id == "11-customer-evidence":
                related.extend(
                    item["id"]
                    for item in pages
                    if item["type"] == "session-evidence"
                )
        elif page["type"] == "session-evidence":
            related = [
                item
                for item in ("11-customer-evidence", "12-synthesis")
                if item in eligible_ids
            ]
        elif page["type"] == "prototype-launch":
            related = [
                item
                for item in (
                    "08-experiment",
                    "09-storyboard",
                    PROTOTYPE_BRIEF_ID,
                    "10-test-plan",
                    "11-customer-evidence",
                )
                if item in eligible_ids
            ]
        else:
            related = []
        page["relationships"] = {
            "home": "home",
            "previous": previous_candidates[-1]["id"] if previous_candidates else None,
            "next": next_candidates[0]["id"] if next_candidates else None,
            "relatedEvidence": list(dict.fromkeys(related)),
            "decision": relationship_if_available("07-decision", page_id),
            "prototype": relationship_if_available("prototype", page_id),
            "outcome": relationship_if_available("13-outcome", page_id),
        }

    assignment_digest = (
        sha256_bytes(assignment_manifest_path(workspace).read_bytes())
        if assignment_manifest_path(workspace).exists()
        else zero_digest
    )
    home_source = {
        "state": state,
        "assignmentManifestDigest": assignment_digest,
        "pages": [
            {"id": page["id"], "contentDigest": page["contentDigest"]}
            for page in pages
            if page["id"] != "home"
        ],
    }
    by_id["home"]["contentDigest"] = sha256_bytes(
        json_text(home_source).encode("utf-8")
    )
    export_record = export_metadata or {
        "kind": "workspace",
        "approvedBy": None,
        "approvedAt": None,
        "approvalDigest": None,
        "selection": None,
        "humanPublicationRequired": True,
        "published": False,
    }
    version_source = {
        "stateDigest": sha256_bytes(json_text(state).encode("utf-8")),
        "pageDigests": [
            {"id": page["id"], "contentDigest": page["contentDigest"]}
            for page in pages
        ],
        "export": export_record,
    }
    css_payload = (HTML_KIT_DIR / "sprint.css").read_bytes()
    return {
        "schemaVersion": SITE_MANIFEST_SCHEMA_VERSION,
        "recordType": "sprint-results-site-manifest",
        "site": {
            "title": str(state["title"]),
            "slug": str(state["slug"]),
            "methodProfile": str(state["methodProfile"]),
            "executionMode": str(state["executionMode"]),
            "route": str(state["route"]),
            "terminalState": str(state["terminalState"]),
            "sourceUpdatedAt": str(state["updatedAt"]),
            "versionDigest": sha256_bytes(json_text(version_source).encode("utf-8")),
        },
        "export": export_record,
        "pages": pages,
        "assets": [
            {
                "path": "assets/sprint.css",
                "sha256": sha256_bytes(css_payload),
                "bytes": len(css_payload),
            }
        ],
    }


def render_site_navigation(site_manifest: dict[str, Any], current_page_id: str) -> str:
    pages = {page["id"]: page for page in site_manifest["pages"]}
    current = pages[current_page_id]
    relationships = current["relationships"]
    links: list[tuple[str, str]] = [("Home", "home")]
    if current_page_id != "home":
        links.append(("Current", current_page_id))
    for label, key in (
        ("Previous", "previous"),
        ("Next", "next"),
        ("Decision", "decision"),
        ("Prototype", "prototype"),
        ("Outcome", "outcome"),
    ):
        target_id = relationships.get(key)
        if target_id:
            links.append((label, target_id))
    links.extend(
        ("Related evidence", target_id)
        for target_id in relationships.get("relatedEvidence", [])
    )
    rendered_links: list[str] = []
    seen: set[tuple[str, str]] = set()
    for label, target_id in links:
        link_key = (label, target_id)
        if link_key in seen or target_id not in pages:
            continue
        seen.add(link_key)
        target = pages[target_id]
        href = site_relative_href(str(current["path"]), str(target["path"]))
        aria_current = ' aria-current="page"' if target_id == current_page_id else ""
        rendered_links.append(
            f'<li><a href="{escape(href)}"{aria_current}>'
            f'{escape(label)}: {escape(target["title"])}</a></li>'
        )
    manifest_href = site_relative_href(str(current["path"]), SITE_MANIFEST_FILENAME)
    rendered_links.append(
        f'<li><a href="{escape(manifest_href)}" download>Site manifest</a></li>'
    )
    site = site_manifest["site"]
    return (
        '<nav class="site-navigation" aria-label="Sprint site">'
        '<div class="shell site-navigation__inner">'
        '<p class="site-navigation__context">'
        f'<strong>{escape(site["title"])}</strong>'
        f'<span>Current: {escape(current["title"])} · {escape(current["phase"])} · '
        f'{escape(display_label(current["status"]))}</span>'
        f'<span>{escape(display_label(site["route"]))} · '
        f'{escape(display_label(site["executionMode"]))} · '
        f'{escape(display_label(site["methodProfile"]))}</span>'
        '</p>'
        f'<ul class="site-navigation__links">{"".join(rendered_links)}</ul>'
        '</div></nav>'
    )


def render_supporting_site_page(
    site_manifest: dict[str, Any],
    page: dict[str, Any],
    state: dict[str, Any],
    description: str,
    content_html: str,
) -> str:
    template = (HTML_KIT_DIR / "site-page-template.html").read_text(encoding="utf-8")
    return replace_tokens(
        template,
        {
            "PAGE_DESCRIPTION": escape(description),
            "PAGE_TITLE": escape(page["title"]),
            "SPRINT_TITLE": escape(state["title"]),
            "STYLESHEET_HREF": escape(
                site_relative_href(str(page["path"]), "assets/sprint.css")
            ),
            "SITE_NAVIGATION_HTML": render_site_navigation(
                site_manifest, str(page["id"])
            ),
            "PAGE_PHASE": escape(page["phase"]),
            "STATUS_CLASS": class_for_status(str(page["status"])),
            "PAGE_STATUS": escape(display_label(page["status"])),
            "METHOD_PROFILE": escape(display_label(state["methodProfile"])),
            "EXECUTION_MODE": escape(display_label(state["executionMode"])),
            "SPRINT_ROUTE": escape(display_label(state["route"])),
            "PAGE_CONTENT_HTML": content_html,
            "HOME_HREF": escape(
                site_relative_href(str(page["path"]), "index.html")
            ),
        },
    )


def render_session_evidence_page(
    workspace: Path,
    site_manifest: dict[str, Any],
    page: dict[str, Any],
    state: dict[str, Any],
) -> str:
    session_id = str(page["id"]).split(":", 1)[1]
    customer_manifest = load_session_manifest(workspace)
    entry = next(
        item for item in customer_manifest["sessions"] if item["sessionId"] == session_id
    )
    summary_path = workspace_relative_file(
        workspace, entry["summaryPath"], f"Session {session_id} summary"
    )
    summary = load_session_summary(summary_path)

    def evidence_cards(values: list[dict[str, Any]], label: str) -> str:
        if not values:
            return "<p>Nothing recorded yet.</p>"
        return "".join(
            '<article class="provenance">'
            f'<p class="eyebrow">{escape(label)} · {escape(item.get("id", "unlabelled"))}</p>'
            f'<p>{escape(item.get("text", "Nothing recorded yet."))}</p>'
            '</article>'
            for item in values
        )

    task_rows = [
        [
            item.get("taskId", ""),
            display_label(item.get("outcome")),
            item.get("notes", ""),
        ]
        for item in summary.get("taskOutcomes", [])
    ]
    question_rows = [
        [
            item.get("questionId", ""),
            display_label(item.get("assessment")),
            item.get("notes", ""),
        ]
        for item in summary.get("questionEvidence", [])
    ]
    content = (
        '<section class="section section--warning" aria-labelledby="session-privacy-title">'
        '<p class="eyebrow">Privacy-minimized view</p>'
        '<h2 id="session-privacy-title">Anonymized session evidence</h2>'
        '<p>Participant identity, contact details, exact session date, raw-source locations, and quote locators are intentionally omitted. This page remains private unless the exact export receives a separate human publication approval.</p>'
        '</section>'
        '<section class="section" aria-labelledby="session-context-title">'
        '<p class="eyebrow">Version context</p>'
        '<h2 id="session-context-title">Session context</h2>'
        '<dl>'
        f'<dt>Segment</dt><dd>{escape(entry.get("participantSegment", "Not recorded"))}</dd>'
        f'<dt>Participant fit</dt><dd>{escape(display_label(entry.get("participantFit")))}</dd>'
        f'<dt>Protocol fidelity</dt><dd>{escape(display_label(entry.get("protocolFidelity")))}</dd>'
        f'<dt>Prototype version</dt><dd>{escape(summary["prototypeVersion"])}</dd>'
        f'<dt>Questions version</dt><dd>{escape(summary["questionsVersion"])}</dd>'
        '</dl>'
        f'<p>{escape(summary.get("qualificationSummary") or "Qualification not recorded yet.")}</p>'
        '</section>'
        '<section class="section" aria-labelledby="session-observations-title">'
        '<p class="eyebrow">Before interpretation</p>'
        '<h2 id="session-observations-title">Observed behavior</h2>'
        f'{evidence_cards(summary.get("observations", []), "Observed")}'
        '</section>'
        '<section class="section" aria-labelledby="session-inferences-title">'
        '<p class="eyebrow">Interpretation</p>'
        '<h2 id="session-inferences-title">Inferences</h2>'
        f'{evidence_cards(summary.get("inferences", []), "Inference")}'
        '</section>'
        '<section class="section" aria-labelledby="session-tasks-title">'
        '<p class="eyebrow">Task evidence</p>'
        '<h2 id="session-tasks-title">Task outcomes</h2>'
        f'{render_table({"title": "Task outcomes", "columns": ["Task", "Outcome", "Notes"], "rows": task_rows})}'
        '</section>'
        '<section class="section" aria-labelledby="session-questions-title">'
        '<p class="eyebrow">Question evidence</p>'
        '<h2 id="session-questions-title">Sprint-question evidence</h2>'
        f'{render_table({"title": "Sprint-question evidence", "columns": ["Question", "Assessment", "Notes"], "rows": question_rows})}'
        '</section>'
        '<section class="section" aria-labelledby="session-limits-title">'
        '<p class="eyebrow">Boundaries</p>'
        '<h2 id="session-limits-title">Limitations and uncertainties</h2>'
        f'{render_list([*summary.get("limitations", []), *summary.get("uncertainties", [])])}'
        '</section>'
    )
    return render_supporting_site_page(
        site_manifest,
        page,
        state,
        "Privacy-minimized evidence from one version-bound customer session.",
        content,
    )


def render_prototype_launch_page(
    workspace: Path,
    site_manifest: dict[str, Any],
    page: dict[str, Any],
    state: dict[str, Any],
) -> str:
    prototype = page["prototype"]
    record_path = workspace_relative_file(
        workspace,
        f"prototype/{prototype['version']}/tested-version.json",
        "Prototype launch tested-version record",
    )
    record = load_tested_version(record_path)
    artifact_href = site_relative_href(str(page["path"]), prototype["artifactPath"])
    launch_links = [
        f'<a class="launch-link" href="{escape(artifact_href)}">Open the packaged tested artifact</a>'
    ]
    deployment_url = safe_url(str(prototype.get("deploymentUrl") or ""))
    if deployment_url:
        launch_links.append(
            f'<a class="launch-link" href="{deployment_url}">Open the versioned external deployment</a>'
        )
    expires_at = record["deployment"].get("expiresAt")
    content = (
        '<section class="section section--accent" aria-labelledby="prototype-launch-title">'
        '<p class="eyebrow">Frozen test version</p>'
        '<h2 id="prototype-launch-title">Launch the tested artifact</h2>'
        f'<div class="tag-row">{"".join(launch_links)}</div>'
        '<div class="callout"><strong>Evidence boundary:</strong> '
        f'{escape(record["claims"]["statement"])}</div>'
        '</section>'
        '<section class="section" aria-labelledby="prototype-context-title">'
        '<p class="eyebrow">Access and version context</p>'
        '<h2 id="prototype-context-title">Before opening</h2>'
        '<dl>'
        f'<dt>Version</dt><dd>{escape(record["version"])}</dd>'
        f'<dt>Artifact level</dt><dd>{escape(display_label(record["artifactLevel"]))}</dd>'
        f'<dt>Access model</dt><dd>{escape(display_label(record["deployment"]["accessModel"]))}</dd>'
        f'<dt>Deployment target</dt><dd>{escape(record["deployment"]["target"])}</dd>'
        f'<dt>Expiry</dt><dd>{escape(display_date(expires_at) if expires_at else "No expiry recorded")}</dd>'
        '</dl>'
        f'<p><strong>Cleanup:</strong> {escape(record["deployment"]["cleanupPlan"])}</p>'
        f'<p><strong>Rollback:</strong> {escape(record["deployment"]["rollbackPlan"])}</p>'
        '</section>'
    )
    return render_supporting_site_page(
        site_manifest,
        page,
        state,
        "Contextual launch page for the immutable prototype version used in customer evidence.",
        content,
    )


def render_artifact(
    workspace: Path,
    data: dict[str, Any],
    state: dict[str, Any],
    specs: dict[str, dict[str, Any]],
    assessment: dict[str, Any],
    site_manifest: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    require_valid_schema(
        data,
        "artifact-data",
        workspace / "artifact-data" / f"{data.get('id', 'unknown')}.json",
    )
    errors = artifact_data_errors(data, specs)
    errors.extend(evidence_claim_errors(data, state))
    errors.extend(material_finding_errors(workspace, data, assessment))
    if errors:
        raise SprintError(f"Artifact {data.get('id')} is invalid: {'; '.join(errors)}")
    artifact_id = str(data["id"])
    spec = specs[artifact_id]
    updated_at = str(data["updatedAt"])
    sections = data.get("sections", [])
    primary_content = "\n".join(
        render_section(section, index)
        for index, section in enumerate(sections, start=1)
        if isinstance(section, dict)
    )
    if artifact_id == PROTOTYPE_BRIEF_ID:
        export_kind = site_manifest["export"]["kind"]
        primary_content += "\n" + render_prototype_brief(
            data["prototypeBrief"],
            export_view=export_kind != "workspace",
            shareable=export_kind == "shareable-site",
            prototype_included=any(
                page["id"] == "prototype" for page in site_manifest["pages"]
            ),
        )
    if artifact_id == TEST_PLAN_ID and isinstance(data.get("recruitmentPlan"), dict):
        primary_content += "\n" + render_recruitment_plan(data["recruitmentPlan"])
    prototype_data_path = workspace / "artifact-data" / f"{PROTOTYPE_BRIEF_ID}.json"
    prototype_brief = None
    if artifact_id == "13-outcome" and prototype_data_path.exists():
        prototype_brief = load_artifact_data(prototype_data_path).get("prototypeBrief")
    template = (HTML_KIT_DIR / "artifact-template.html").read_text(encoding="utf-8")
    status = str(data.get("status", "draft"))
    validation_label, validation_notice, validation_class = validation_truth(state)
    mode_selection = state.get("executionModeSelection", {})
    rendered = replace_tokens(
        template,
        {
            "ARTIFACT_PURPOSE": escape(spec["purpose"]),
            "ARTIFACT_TITLE": escape(spec["title"]),
            "SPRINT_TITLE": escape(state["title"]),
            "SITE_NAVIGATION_HTML": render_site_navigation(
                site_manifest, artifact_id
            ),
            "SPRINT_PHASE": escape(spec["phase"]),
            "STATUS_CLASS": class_for_status(status),
            "ARTIFACT_STATUS": escape(status.replace("-", " ").title()),
            "METHOD_PROFILE": escape(display_label(state.get("methodProfile"))),
            "EXECUTION_MODE": escape(display_label(state.get("executionMode"))),
            "SPRINT_ROUTE": escape(display_label(state.get("route"))),
            "TERMINAL_STATE": escape(display_label(state.get("terminalState"))),
            "VALIDATION_LABEL": escape(validation_label),
            "VALIDATION_NOTICE": escape(validation_notice),
            "VALIDATION_SECTION_CLASS": validation_class,
            "MODE_SELECTED_BY": escape(mode_selection.get("selectedBy", "unknown")),
            "MODE_SELECTION_REASON": escape(mode_selection.get("reason", "unknown")),
            "UPDATED_ISO": escape(updated_at),
            "UPDATED_DISPLAY": escape(display_date(updated_at)),
            "SUMMARY_HTML": render_paragraphs(data.get("summary", [])),
            "PRIMARY_CONTENT_HTML": primary_content,
            "OUTCOME_STATEMENTS_HTML": (
                render_outcome_statements(data) if artifact_id == "13-outcome" else ""
            ),
            "COMPLETION_ASSESSMENT_HTML": (
                '<section class="section" aria-labelledby="completion-assessment-title">'
                '<p class="eyebrow">Four-dimensional assessment</p>'
                '<h2 id="completion-assessment-title">Completion, evidence, and decision readiness</h2>'
                '<div class="assessment-grid">'
                f'{render_completion_dimensions(assessment)}</div>'
                '<h3>Automatically generated limitations</h3><ul>'
                f'{render_assessment_limitations(assessment)}</ul></section>'
                if artifact_id == "13-outcome"
                else ""
            ),
            "MATERIAL_FINDINGS_HTML": (
                '<section class="section" aria-labelledby="material-findings-title">'
                '<p class="eyebrow">Decision evidence</p>'
                '<h2 id="material-findings-title">Material findings</h2>'
                f'{render_material_findings(assessment)}</section>'
                if artifact_id in {"12-synthesis", "13-outcome"}
                else ""
            ),
            "EVIDENCE_HTML": render_evidence(data.get("evidence", [])),
            "UNKNOWNS_HTML": render_list(data.get("unknowns", [])),
            "NEXT_ACTION_HTML": render_list(data.get("nextActions", []), ordered=True),
            "METHOD_FIDELITY_HTML": (
                render_method_fidelity_section(state)
                if artifact_id == "13-outcome"
                else ""
            ),
            "PROTOTYPE_TRACEABILITY_HTML": (
                render_prototype_traceability(
                    prototype_brief,
                    prefix="../",
                    available_page_ids={
                        page["id"] for page in site_manifest["pages"]
                    },
                )
                if isinstance(prototype_brief, dict)
                else ""
            ),
        },
    )
    output_path = workspace / "artifacts" / spec["filename"]
    return (
        {
            "id": artifact_id,
            "title": spec["title"],
            "path": str(output_path.relative_to(workspace)),
            "status": status,
            "step": spec["step"],
            "updatedAt": updated_at,
        },
        rendered,
    )


def render_steps(state: dict[str, Any]) -> str:
    completed = set(state.get("completedSteps", []))
    skipped = set(state.get("skippedSteps", []))
    not_applicable = set(state.get("notApplicableSteps", []))
    skip_records = {
        item.get("step"): item
        for item in state.get("skipRecords", [])
        if isinstance(item, dict)
    }
    current = state.get("currentStep")
    output = []
    for number, step in enumerate(STEPS, start=1):
        step_id = step["id"]
        if step_id in not_applicable:
            css = "step"
            marker = "·"
            detail = "Not applicable to the selected route"
            status = '<span class="status status--unknown">Not applicable</span>'
        elif step_id in skipped:
            css = "step"
            marker = "–"
            record = skip_records.get(step_id, {})
            detail = (
                f"Skipped by {record.get('skippedBy', 'unknown')}: "
                f"{record.get('reason', state.get('skipReasons', {}).get(step_id, 'No reason recorded'))}"
            )
            status = '<span class="status status--unknown">Skipped</span>'
        elif step_id in completed:
            css = "step step--complete"
            marker = "✓"
            detail = "Completed"
            status = '<span class="status status--complete">Complete</span>'
        elif step_id == current:
            css = "step step--active"
            marker = "→"
            detail = "Current step"
            status = '<span class="status status--active">Active</span>'
        else:
            css = "step"
            marker = str(number)
            detail = "Not started"
            status = '<span class="status status--unknown">Upcoming</span>'
        output.append(
            f'<li class="{css}">'
            f'<span class="step__marker">{marker}</span>'
            f'<div><strong>{escape(step["name"])}</strong><p>{escape(detail)}</p></div>'
            f"{status}</li>"
        )
    return "\n".join(output)


def render_artifact_links(artifacts: list[dict[str, Any]]) -> str:
    if not artifacts:
        return '<li class="artifact"><div><strong>No artifacts yet</strong><p>Artifacts appear as the sprint progresses.</p></div></li>'
    output = []
    for artifact in artifacts:
        status = str(artifact.get("status", "draft"))
        output.append(
            '<li class="artifact">'
            '<span class="step__marker" aria-hidden="true">↗</span>'
            f'<div><a href="{escape(artifact["path"])}">{escape(artifact["title"])}</a>'
            f'<p>{escape(step_name(str(artifact.get("step", ""))))}</p></div>'
            f'<span class="status {class_for_status(status)}">{escape(status.replace("-", " ").title())}</span>'
            "</li>"
        )
    return "\n".join(output)


def render_prototype_traceability(
    brief: dict[str, Any] | None,
    *,
    prefix: str = "",
    available_page_ids: set[str] | None = None,
) -> str:
    if not isinstance(brief, dict):
        return (
            '<p>No approved prototype/MVP brief or immutable tested version has been recorded.</p>'
        )
    versions = brief.get("versions", [])
    current = brief.get("currentVersion")
    current_record = next(
        (
            item
            for item in versions
            if isinstance(item, dict) and item.get("version") == current
        ),
        None,
    )
    available = available_page_ids or {PROTOTYPE_BRIEF_ID, "prototype"}
    links: list[str] = []
    if PROTOTYPE_BRIEF_ID in available:
        brief_href = f"{prefix}artifacts/10-prototype-brief.html" if prefix else "artifacts/10-prototype-brief.html"
        links.append(
            f'<li><a href="{escape(brief_href)}">Approved prototype / MVP brief</a></li>'
        )
    if current_record is not None and "prototype" in available:
        launch_path = f"{prefix}prototype-launch.html"
        links.append(
            f'<li><a href="{escape(launch_path)}">Immutable deployment and version record — tested artifact {escape(current)}</a></li>'
        )
        url = safe_url(str(current_record.get("deploymentUrl") or ""))
        if url:
            links.append(f'<li><a href="{url}">Versioned deployment URL</a></li>')
    elif current_record is None:
        links.append("<li>No tested version is frozen yet.</li>")
    if not links:
        links.append("<li>Prototype records are not included in this site export.</li>")
    return (
        '<section class="section" aria-labelledby="test-artifact-traceability">'
        '<p class="eyebrow">Version-bound evidence</p>'
        '<h2 id="test-artifact-traceability">Test artifact traceability</h2>'
        f'<ul>{"".join(links)}</ul>'
        '<div class="callout"><strong>Readiness boundary:</strong> A live URL does not establish customer validation or production readiness.</div>'
        '</section>'
    )


def short_digest(value: Any) -> str:
    text = str(value)
    return text.removeprefix("sha256:")[:12] if text else "pending"


def render_assignment_provenance(manifest: dict[str, Any]) -> str:
    assignments = manifest.get("assignments", [])
    if not isinstance(assignments, list) or not assignments:
        return (
            '<li class="artifact"><div><strong>No specialist assignments yet</strong>'
            '<p>Registered packets and result-memo provenance will appear here.</p></div></li>'
        )
    roles = load_role_contracts()
    output = []
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        role_id = str(assignment.get("role", "specialist"))
        role_label = roles.get(role_id, {}).get("displayName", display_label(role_id))
        assignee = assignment.get("assignee", {})
        safe_run_reference = short_digest(
            value_digest("run", str(assignee.get("runId", "unknown run")))
        )
        result = assignment.get("resultMemo", {})
        provenance = (
            f"Packet {short_digest(assignment.get('packet', {}).get('digest'))}"
            + (
                f" · result {short_digest(result.get('digest'))}"
                if isinstance(result, dict) and result
                else " · result pending"
            )
        )
        output.append(
            '<li class="artifact">'
            '<span class="step__marker" aria-hidden="true">#</span>'
            f'<div><strong>{escape(role_label)}</strong>'
            f'<p>{escape(step_name(str(assignment.get("step", ""))))} · '
            f'{escape(assignee.get("label", "unassigned"))} / '
            f'run {escape(safe_run_reference)}</p>'
            f'<p>{escape(provenance)}</p></div>'
            f'<span class="status {class_for_status(str(assignment.get("status", "assigned")))}">'
            f'{escape(display_label(assignment.get("status")))}</span>'
            '</li>'
        )
    return "\n".join(output)


def render_decisions(decisions: Any) -> str:
    if not isinstance(decisions, list) or not decisions:
        return '<li class="decision"><div><strong>No decisions yet</strong><p>Human gate decisions will appear here.</p></div></li>'
    output = []
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        considered = decision.get("consideredInputs", [])
        input_summary = ", ".join(
            f"{item.get('kind')}:{item.get('reference')}@{short_digest(item.get('digest'))}"
            for item in considered
            if isinstance(item, dict)
        )
        status = str(decision.get("status", "active"))
        output.append(
            '<li class="decision">'
            f'<span class="step__marker" aria-hidden="true">{"✓" if status == "active" else "↺"}</span>'
            f'<div><strong>{escape(decision.get("decision", "Decision"))}</strong>'
            f'<p>{escape(GATE_NAMES.get(str(decision.get("gate")), str(decision.get("gate", "Gate"))))}: '
            f'{escape(decision.get("rationale") or "No rationale recorded")}</p>'
            f'<p>Decider: {escape(decision.get("deciderLabel", "unrecorded"))} · '
            f'{escape(display_date(str(decision.get("decidedAt", ""))))}</p>'
            f'<p>Considered: {escape(input_summary or "No inputs recorded")}</p></div>'
            f'<span class="status {"status--decision" if status == "active" else "status--unknown"}">'
            f'{escape(display_label(status))}</span>'
            "</li>"
        )
    return "\n".join(output)


def render_dashboard(
    state: dict[str, Any],
    artifacts: list[dict[str, Any]],
    manifest: dict[str, Any],
    assessment: dict[str, Any],
    prototype_brief: dict[str, Any] | None,
    recruitment_plan: dict[str, Any] | None,
    site_manifest: dict[str, Any],
) -> str:
    template = (HTML_KIT_DIR / "index-template.html").read_text(encoding="utf-8")
    skipped = set(state.get("skippedSteps", []))
    not_applicable = set(state.get("notApplicableSteps", []))
    denominator = max(1, len(STEPS) - len(not_applicable))
    completed = len(
        set(state.get("completedSteps", [])) - skipped - not_applicable
    )
    progress = min(100, round((completed / denominator) * 100))
    current = str(state.get("currentStep", "01-intake"))
    next_action = state.get("nextAction", {})
    if not isinstance(next_action, dict):
        next_action = {"title": "Continue the sprint", "body": str(next_action)}
    customer = state.get("customerTesting", {})
    if not isinstance(customer, dict):
        customer = {}
    open_questions = state.get("openQuestions", [])
    if isinstance(open_questions, list) and open_questions:
        questions_html = "\n".join(f"<li>{escape(item)}</li>" for item in open_questions)
    else:
        questions_html = "<li>No open questions recorded.</li>"
    updated_at = str(state.get("updatedAt") or state.get("createdAt") or "")
    fidelity_summary = state.get("fidelity", {}).get("summary", {})
    validation_label, validation_notice, validation_class = validation_truth(state)
    mode_selection = state.get("executionModeSelection", {})
    if state.get("executionMode") == "live":
        evidence_boundary = "Only suitable real-customer sessions count as customer evidence."
    else:
        evidence_boundary = (
            "This non-live run cannot claim customer evidence; synthetic work is rehearsal only."
        )
    rendered = replace_tokens(
        template,
        {
            "SPRINT_TITLE": escape(state.get("title", "Untitled sprint")),
            "SITE_NAVIGATION_HTML": render_site_navigation(site_manifest, "home"),
            "SPRINT_CHALLENGE": escape(state.get("challenge", "No challenge recorded")),
            "SPRINT_STATUS": escape(str(state.get("status", "active")).replace("-", " ").title()),
            "SPRINT_STATUS_CLASS": class_for_status(str(state.get("status", "active"))),
            "SPRINT_ROUTE": escape(str(state.get("route", "undecided")).replace("-", " ").title()),
            "METHOD_PROFILE": escape(display_label(state.get("methodProfile"))),
            "EXECUTION_MODE": escape(display_label(state.get("executionMode"))),
            "TERMINAL_STATE": escape(display_label(state.get("terminalState"))),
            "TERMINAL_STATE_CLASS": class_for_status(str(state.get("terminalState"))),
            "VALIDATION_LABEL": escape(validation_label),
            "VALIDATION_NOTICE": escape(validation_notice),
            "VALIDATION_SECTION_CLASS": validation_class,
            "MODE_SELECTED_BY": escape(mode_selection.get("selectedBy", "unknown")),
            "MODE_SELECTION_REASON": escape(mode_selection.get("reason", "unknown")),
            "METHOD_FIDELITY": escape(
                display_label(fidelity_summary.get("assessment"))
            ),
            "UPDATED_ISO": escape(updated_at),
            "UPDATED_DISPLAY": escape(display_date(updated_at)),
            "PROGRESS_PERCENT": progress,
            "PROCESS_STATUS": escape(assessment["processStatus"]["label"]),
            "COMPLETION_DIMENSIONS": render_completion_dimensions(assessment),
            "SESSION_COUNTS": render_session_counts(assessment),
            "EVIDENCE_STRENGTH": escape(assessment["evidenceStrength"]["label"]),
            "EVIDENCE_QUALITY": escape(display_label(assessment["evidenceStrength"]["quality"])),
            "DECISION_READINESS": escape(assessment["decisionReadiness"]["label"]),
            "DECISION_READINESS_REASON": escape(assessment["decisionReadiness"]["reason"]),
            "ASSESSMENT_LIMITATIONS": render_assessment_limitations(assessment),
            "MATERIAL_FINDINGS": render_material_findings(assessment),
            "CURRENT_STEP": escape(f"{current}: {step_name(current)}"),
            "COMPLETED_STEPS": completed,
            "SKIPPED_STEPS": len(skipped),
            "NOT_APPLICABLE_STEPS": len(not_applicable),
            "NEXT_ACTION_TITLE": escape(next_action.get("title", "Continue the sprint")),
            "NEXT_ACTION_BODY": escape(next_action.get("body", "Review the current step.")),
            "HUMAN_INPUT_NEEDED": escape(next_action.get("humanInput", "None right now")),
            "STEP_GUIDANCE_HTML": render_step_guidance(state),
            "SPRINT_STEPS": render_steps(state),
            "TEST_STATUS": escape(str(customer.get("status", "not-planned")).replace("-", " ").title()),
            "SESSIONS_PLANNED": escape(customer.get("sessionsPlanned", 0)),
            "SESSIONS_COMPLETED": escape(customer.get("sessionsCompleted", 0)),
            "EVIDENCE_BOUNDARY": escape(evidence_boundary),
            "RECRUITMENT_SUMMARY": render_recruitment_summary(recruitment_plan),
            "FIDELITY_ADAPTATIONS": render_fidelity_adaptations(state),
            "FIDELITY_LIMITATIONS": render_fidelity_limitations(state),
            "CURRENT_FIDELITY_GUIDANCE": render_current_fidelity_guidance(state),
            "ARTIFACT_COUNT": len(artifacts),
            "ARTIFACT_LINKS": render_artifact_links(artifacts),
            "TEST_ARTIFACT_TRACEABILITY": render_prototype_traceability(
                prototype_brief,
                available_page_ids={page["id"] for page in site_manifest["pages"]},
            ),
            "ASSIGNMENT_COUNT": len(manifest.get("assignments", [])),
            "ASSIGNMENT_SUMMARY": render_assignment_provenance(manifest),
            "DECISION_SUMMARY": render_decisions(state.get("decisions", [])),
            "OPEN_QUESTIONS": questions_html,
        },
    )
    rendered = rendered.replace('value="0" max="100"', f'value="{progress}" max="100"', 1)
    return rendered


def load_workspace_documents(
    workspace: Path,
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    list[tuple[Path, dict[str, Any]]],
]:
    """Validate all persisted workspace JSON before a mutation or render."""

    state = load_state(workspace)
    state_errors = validate_state(state)
    if state_errors:
        raise SprintError(
            "Invalid workflow state:\n"
            + "\n".join(f"- {item}" for item in state_errors)
        )
    manifest = load_assignment_manifest(workspace)
    manifest_errors = assignment_manifest_errors(workspace, manifest, state)
    if manifest_errors:
        raise SprintError(
            "Assignment manifest is invalid:\n"
            + "\n".join(f"- {item}" for item in manifest_errors)
        )
    specs = load_artifact_specs()
    data_dir = workspace / "artifact-data"
    artifact_documents = (
        [
            (data_path, load_artifact_data(data_path))
            for data_path in sorted(data_dir.glob("*.json"))
        ]
        if data_dir.exists()
        else []
    )
    for data_path, data in artifact_documents:
        errors = artifact_data_errors(data, specs)
        if errors:
            raise SprintError(
                f"Artifact {data.get('id')} in {data_path} is invalid: "
                + "; ".join(errors)
            )
    artifact_paths_by_id: dict[str, Path] = {}
    for data_path, data in artifact_documents:
        artifact_id = str(data["id"])
        previous_path = artifact_paths_by_id.get(artifact_id)
        if previous_path is not None:
            raise SprintError(
                f"Duplicate artifact id {artifact_id!r} in {previous_path} and {data_path}"
            )
        artifact_paths_by_id[artifact_id] = data_path
    return state, specs, artifact_documents


def build_render_plan(
    workspace: Path,
    *,
    visibility: str = "private",
    artifact_ids: set[str] | None = None,
    session_ids: set[str] | None = None,
    include_prototype: bool = True,
    export_metadata: dict[str, Any] | None = None,
) -> RenderPlan:
    source_state = read_json(state_path(workspace))
    state, specs, artifact_documents = load_workspace_documents(workspace)
    manifest = load_assignment_manifest(workspace)
    all_registrations: list[dict[str, Any]] = []
    generated_files: dict[Path, str] = {
        workspace / "assets" / "sprint.css": (
            HTML_KIT_DIR / "sprint.css"
        ).read_text(encoding="utf-8")
    }
    data_paths = [path for path, _data in artifact_documents]
    seen_ids: set[str] = set()
    for data_path, data in artifact_documents:
        artifact_id = str(data["id"])
        if artifact_id in seen_ids:
            raise SprintError(f"Duplicate artifact id: {artifact_id}")
        seen_ids.add(artifact_id)
        spec = specs[artifact_id]
        all_registrations.append(
            {
                "id": artifact_id,
                "title": spec["title"],
                "path": f"artifacts/{spec['filename']}",
                "status": str(data.get("status", "draft")),
                "step": spec["step"],
                "updatedAt": str(data["updatedAt"]),
            }
        )
    all_registrations.sort(key=lambda item: item["id"])
    normalized_state = dict(state)
    normalized_state["artifacts"] = all_registrations
    require_valid_schema(normalized_state, "workspace-state", state_path(workspace))
    render_state = normalized_state
    assessment = build_completion_assessment(
        workspace, render_state, artifact_documents
    )
    registrations = [
        item
        for item in all_registrations
        if artifact_ids is None or item["id"] in artifact_ids
    ]
    prototype_brief = next(
        (
            data.get("prototypeBrief")
            for _path, data in artifact_documents
            if data.get("id") == PROTOTYPE_BRIEF_ID
        ),
        None,
    )
    recruitment_plan = next(
        (
            data.get("recruitmentPlan")
            for _path, data in artifact_documents
            if data.get("id") == TEST_PLAN_ID
        ),
        None,
    )
    site_manifest = build_site_manifest(
        workspace,
        render_state,
        specs,
        artifact_documents,
        visibility=visibility,
        artifact_ids=artifact_ids,
        session_ids=session_ids,
        include_prototype=include_prototype,
        export_metadata=export_metadata,
    )
    for data_path, data in artifact_documents:
        artifact_id = str(data["id"])
        if artifact_ids is not None and artifact_id not in artifact_ids:
            continue
        registration, rendered = render_artifact(
            workspace, data, render_state, specs, assessment, site_manifest
        )
        output_path = workspace / str(registration["path"])
        if output_path in generated_files:
            raise SprintError(f"Duplicate rendered output path: {output_path}")
        generated_files[output_path] = rendered
    for page in site_manifest["pages"]:
        output_path = workspace / str(page["path"])
        if page["type"] == "session-evidence":
            generated_files[output_path] = render_session_evidence_page(
                workspace, site_manifest, page, render_state
            )
        elif page["type"] == "prototype-launch":
            generated_files[output_path] = render_prototype_launch_page(
                workspace, site_manifest, page, render_state
            )
    generated_files[workspace / "index.html"] = render_dashboard(
        render_state,
        registrations,
        manifest,
        assessment,
        prototype_brief,
        recruitment_plan,
        site_manifest,
    )

    for page in site_manifest["pages"]:
        rendered = generated_files.get(workspace / str(page["path"]))
        if rendered is None:
            raise SprintError(f"Site manifest page has no rendered output: {page['path']}")
        page["renderDigest"] = sha256_text(rendered)
    require_valid_schema(
        site_manifest, "site-manifest", workspace / SITE_MANIFEST_FILENAME
    )
    generated_files[workspace / SITE_MANIFEST_FILENAME] = json_text(site_manifest)

    filtered_render = (
        artifact_ids is not None
        or session_ids is not None
        or not include_prototype
        or visibility != "private"
        or export_metadata is not None
    )
    state_update = (
        None
        if filtered_render
        else (normalized_state if source_state != normalized_state else None)
    )
    stale_files: list[Path] = []
    if not filtered_render:
        expected_html_files = {
            path for path in generated_files if path.suffix.lower() == ".html"
        }
        managed_html_files = set((workspace / "artifacts").glob("*.html"))
        managed_html_files.update((workspace / "session-evidence").glob("*.html"))
        prototype_launch = workspace / "prototype-launch.html"
        if prototype_launch.exists():
            managed_html_files.add(prototype_launch)
        stale_files = sorted(managed_html_files - expected_html_files)
    return RenderPlan(
        registrations=registrations,
        generated_files=generated_files,
        state_update=state_update,
        stale_files=stale_files,
        canonical_files=[
            state_path(workspace),
            assignment_manifest_path(workspace),
            *data_paths,
        ],
        site_manifest=site_manifest,
    )


def render_workspace(workspace: Path) -> RenderPlan:
    plan = build_render_plan(workspace)
    outputs = dict(plan.generated_files)
    if plan.state_update is not None:
        outputs[state_path(workspace)] = json_text(plan.state_update)
    write_texts_atomically(outputs)
    for stale_path in plan.stale_files:
        try:
            stale_path.unlink()
        except OSError as error:
            raise SprintError(
                f"Could not remove stale rendered file {stale_path}: {error}"
            ) from error
    ensure_portable_permissions(plan.canonical_files)
    return plan


def empty_section(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "eyebrow": "To establish",
        "type": "paragraphs",
        "paragraphs": ["Not established yet."],
    }


def pending_prototype_approval() -> dict[str, Any]:
    return {
        "status": "pending",
        "deciderLabel": "",
        "rationale": "",
        "decidedAt": None,
    }


def initial_prototype_brief() -> dict[str, Any]:
    placeholder = "Not established yet."
    return {
        "schemaVersion": TEST_ARTIFACT_WORKFLOW_VERSION,
        "artifactLevel": "clickable",
        "selection": {
            "sprintQuestions": [placeholder],
            "hypothesis": placeholder,
            "rationale": placeholder,
            "whyHigherFidelityIsUnnecessary": placeholder,
        },
        "customer": {"target": placeholder, "entryContext": placeholder},
        "experience": {
            "task": placeholder,
            "journey": [placeholder],
            "criticalScenes": [
                {
                    "id": f"SCENE-{index}",
                    "title": placeholder,
                    "sprintQuestion": placeholder,
                    "description": placeholder,
                }
                for index in range(1, 5)
            ],
        },
        "signals": {
            "success": [placeholder],
            "ambiguity": [placeholder],
            "failure": [placeholder],
        },
        "realityBoundary": {
            "mustBeReal": [placeholder],
            "simulated": [],
            "manuallyOperated": [],
            "delayed": [],
            "omitted": [],
        },
        "content": {
            "required": [placeholder],
            "sampleData": [placeholder],
            "states": {"empty": [], "loading": [], "error": []},
        },
        "environment": {
            "devices": [placeholder],
            "browsers": [placeholder],
            "languages": [placeholder],
            "accessibility": [placeholder],
            "conditions": [],
        },
        "capabilities": {
            "realData": False,
            "authentication": False,
            "payments": False,
            "integrations": False,
            "notifications": False,
            "dataPersistence": False,
            "backgroundJobs": False,
            "repeatedUse": False,
            "notes": [],
        },
        "safety": {
            "privacy": [placeholder],
            "consent": [placeholder],
            "security": [placeholder],
            "regulatory": [],
            "dataClassification": "synthetic-only",
        },
        "evidenceCapture": {
            "methods": [placeholder],
            "analytics": {
                "enabled": False,
                "rationale": "No analytics will be enabled without explicit human approval.",
            },
        },
        "build": {
            "timeboxMinutes": 1,
            "owner": placeholder,
            "budgetCeiling": placeholder,
            "approvalPoints": [placeholder],
        },
        "toolSelection": {
            "route": "interaction-design",
            "category": "interaction-design",
            "selectedTool": placeholder,
            "rationale": placeholder,
            "constraints": [placeholder],
            "criteria": {
                "timeToTestableArtifact": placeholder,
                "fidelity": placeholder,
                "realCapabilities": placeholder,
                "stackCompatibility": placeholder,
                "exportability": placeholder,
                "collaborationVersionControl": placeholder,
                "privacyDataProcessing": placeholder,
                "accessibilityDeviceSupport": placeholder,
                "costApproval": placeholder,
                "maintainability": placeholder,
            },
            "supportingTools": [],
            "requiresExternalAccount": False,
            "estimatedCost": placeholder,
            "exportSelfHosting": {"available": False, "strategy": placeholder},
        },
        "deploymentPlan": {
            "required": False,
            "target": "Private local file",
            "accessModel": "private-local",
            "public": False,
            "url": None,
            "expiresAt": None,
            "cleanupPlan": placeholder,
            "rollbackPlan": placeholder,
        },
        "approvals": {
            key: pending_prototype_approval()
            for key in PROTOTYPE_APPROVAL_BOUNDARIES.values()
        },
        "buildPackets": [],
        "trialRuns": [],
        "versions": [],
        "currentVersion": None,
    }


def initial_recruitment_plan(
    state: dict[str, Any] | None = None, timestamp: str | None = None
) -> dict[str, Any]:
    """Return a complete draft shape that must be tailored during evidence work."""

    state = state or {}
    customer = state.get("customerTesting", {})
    method_profile = state.get("methodProfile", "adaptive-design-sprint")
    planned = int(customer.get("sessionsPlanned", 0) or 0)
    if planned < 1:
        planned = 5 if method_profile == "sprint-book" else 1
    target = str(customer.get("target") or "Not established yet.")
    rationale = str(customer.get("targetRationale") or "Not established yet.")
    now = timestamp or utc_now()
    return {
        "schemaVersion": RECRUITMENT_PLAN_VERSION,
        "paidVendorRequired": False,
        "targetDefinition": {
            "audience": target,
            "qualifyingBehaviours": ["Not established yet."],
            "disqualifyingConditions": [
                "Colleagues, conflicted participants, and respondents who cannot describe the required recent behavior."
            ],
            "targetSessions": planned,
            "backupParticipants": 2 if method_profile == "sprint-book" else 1,
            "rationale": rationale,
            "specialConsiderations": [
                "Confirm whether B2B, expert, regulated, low-incidence, language, geography, or accessibility constraints apply."
            ],
        },
        "screener": {
            "status": "draft",
            "introduction": "We are recruiting people based on recent behavior for a research conversation; this screener does not name the preferred solution.",
            "questions": [
                {
                    "prompt": "Tell me about the last time you [relevant behavior].",
                    "qualifyingSignal": "A recent first-person example within the approved target bounds.",
                    "disqualifyingSignal": "No relevant first-person example or only hypothetical familiarity.",
                    "revealsPreferredAnswer": False,
                },
                {
                    "prompt": "How often have you done that in the last [period]?",
                    "qualifyingSignal": "Frequency matches the approved behavioral criterion.",
                    "disqualifyingSignal": "Frequency is outside the approved criterion.",
                    "revealsPreferredAnswer": False,
                },
                {
                    "prompt": "Which tools, services, or workarounds did you use, and what part was personally yours?",
                    "qualifyingSignal": "The person performed or owned the relevant decision.",
                    "disqualifyingSignal": "The experience is second-hand or the decision belonged to someone else.",
                    "revealsPreferredAnswer": False,
                },
            ],
        },
        "channels": [
            {
                "name": "existing-customers",
                "tradeOff": "Fast when a suitable segment is reachable, but relationship context can bias candor.",
                "selected": False,
                "requiresSpend": False,
            },
            {
                "name": "founder-team-networks",
                "tradeOff": "Fast second-degree reach, but colleagues and close contacts must be excluded.",
                "selected": False,
                "requiresSpend": False,
            },
            {
                "name": "communities",
                "tradeOff": "Reaches behavior-based groups, but community rules and privacy must be respected.",
                "selected": False,
                "requiresSpend": False,
            },
            {
                "name": "research-panels",
                "tradeOff": "Can improve speed or specialist reach, but may cost money and requires professional-respondent quality checks.",
                "selected": False,
                "requiresSpend": True,
            },
            {
                "name": "partners",
                "tradeOff": "A trusted intermediary can reach the segment, but partner selection may bias the sample.",
                "selected": False,
                "requiresSpend": False,
            },
            {
                "name": "direct-outreach",
                "tradeOff": "Precise and provider-independent, but manual work and response time are higher.",
                "selected": False,
                "requiresSpend": False,
            },
        ],
        "incentive": {
            "guidance": "Compensate time and inconvenience without buying a preferred answer; consider session length, scarcity, local norms, and company policy.",
            "offer": "No incentive proposed yet.",
            "spendingRequired": False,
            "approvalStatus": "not-required",
            "approvedBy": "",
            "approvalNote": "No spending is approved or required in this draft.",
        },
        "outreach": {
            "invitation": "We are speaking with people who recently [neutral behavior] for a [duration]-minute research session. We are testing a prototype, not you. Respond via [route].",
            "reminder": "Reminder: your research session is [date, time, timezone] at [link or location]. Reply if you need an accessibility adjustment or must reschedule.",
            "confirmation": "You are booked for [date, time, timezone] for [duration]. We will confirm consent before recording or note capture. You may cancel via [route].",
            "cancellation": "Your session is cancelled with no penalty. [State what happens to scheduling and screener data.] We may invite a qualified backup.",
            "backupInvitation": "A session window has opened at [date, time, timezone]. Participation is optional; confirm by [deadline] if it works.",
        },
        "scheduling": {
            "timezone": "Not established yet.",
            "sessionLengthMinutes": 45,
            "windows": ["Not established yet."],
            "bookingMethod": "Not established yet.",
            "accessibility": [
                "Offer a clear route to request compatible format, captioning, assistive-technology, break, device, or scheduling support."
            ],
            "recruitmentDeadline": now[:10],
        },
        "consent": {
            "introduction": "Explain the neutral research purpose and that the prototype, not the participant, is being tested.",
            "recordingPlan": "Confirm the exact notes, recording, transcription, and agent-assistance scope before capture.",
            "anonymisation": "Use participant IDs in the workspace and keep the identity/contact map separately access-controlled.",
            "dataRetention": "Not established yet.",
            "withdrawal": "Allow withdrawal before or during the session and state how to request deletion where applicable.",
            "checklist": [
                "Purpose explained without revealing the preferred answer",
                "Prototype-not-participant framing stated",
                "Recording and agent-assistance scope approved",
                "Anonymisation, access, use, retention, and withdrawal explained",
            ],
        },
        "backupPlan": {
            "activationTrigger": "A booked participant cancels, misses the confirmation deadline, or the qualified pipeline cannot meet the recorded target.",
            "actions": [
                "Contact already-qualified backups.",
                "Add another approved channel without changing the target behavior.",
                "Extend accessible session windows before relaxing a material criterion.",
            ],
            "partialRecruitmentHandling": "Keep the original target visible, run every suitable booked session, report the usable count as partial evidence through the #11 four-dimensional completion/evidence model, state remaining uncertainty, and record the smallest next learning action; never silently lower the target.",
        },
        "tracking": {
            "owner": "Not established yet.",
            "status": "draft",
            "nextAction": "Not established yet.",
            "deadline": now[:10],
            "lastActivityAt": now,
            "candidatesScreened": 0,
            "sessionsBooked": 0,
            "backupsBooked": 0,
            "milestones": {
                "targetDefined": "not-started",
                "screenerApproved": "not-started",
                "outreachLive": "not-started",
                "candidatesScreened": "not-started",
                "sessionsBooked": "not-started",
                "backupsBooked": "not-started",
                "consentReady": "not-started",
            },
        },
    }


def new_artifact_data(
    artifact_id: str,
    spec: dict[str, Any],
    timestamp: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = timestamp or utc_now()
    data: dict[str, Any] = {
        "schemaVersion": ARTIFACT_SCHEMA_VERSION,
        "id": artifact_id,
        "status": "draft",
        "updatedAt": now,
        "summary": ["This artifact is in progress."],
        "sections": [empty_section(title) for title in spec["requiredSections"]],
        "evidence": [],
        "materialFindings": [],
        "unknowns": [],
        "nextActions": ["Replace draft entries with evidence-backed content."],
    }
    if artifact_id == "13-outcome":
        data["outcomeAssessment"] = {
            "processCompleted": "",
            "methodAdaptations": "",
            "evidenceSupports": "",
            "evidenceCannotSupport": "",
            "justifiedDecision": "",
            "decisionImpact": "investigate-or-retest",
            "smallestNextLearningAction": "",
        }
    if artifact_id == PROTOTYPE_BRIEF_ID:
        data["prototypeBrief"] = initial_prototype_brief()
        data["sections"] = [
            {
                "title": "Structured prototype/MVP brief",
                "eyebrow": "Canonical machine-readable record",
                "type": "paragraphs",
                "paragraphs": [
                    "The typed brief below is the approved source for build, trial, deployment, and tested-version records."
                ],
            }
        ]
    if artifact_id == TEST_PLAN_ID:
        data["recruitmentPlan"] = initial_recruitment_plan(state, now)
    return data


def initial_brief_data(
    challenge: str, timestamp: str | None = None
) -> dict[str, Any]:
    spec = load_artifact_specs()["01-sprint-brief"]
    now = timestamp or utc_now()
    data = new_artifact_data("01-sprint-brief", spec, now)
    data["summary"] = [challenge]
    data["sections"] = [
        {
            "title": "Challenge",
            "eyebrow": "Starting point",
            "type": "paragraphs",
            "paragraphs": [challenge],
        },
        empty_section("Desired outcome"),
        empty_section("Constraints"),
        empty_section("Available evidence"),
        {
            "title": "Unknowns",
            "eyebrow": "To clarify",
            "type": "list",
            "items": [
                "Who is the specific target customer?",
                "What outcome must this sprint enable?",
                "What evidence and constraints already exist?",
            ],
        },
    ]
    data["evidence"] = [
        {
            "status": "Observed",
            "claim": "The human Decider supplied the initial challenge statement.",
            "source": "Sprint intake",
            "date": now[:10],
        }
    ]
    data["unknowns"] = [
        "Target customer is not yet confirmed.",
        "Desired outcome and constraints are not yet confirmed.",
    ]
    data["nextActions"] = ["Complete the intake with the human Decider."]
    return data


def initial_session_manifest(
    workspace_slug: str,
    timestamp: str,
    per_session_maximum: int = DEFAULT_SESSION_CONTEXT_MAXIMUM,
    synthesis_maximum: int = DEFAULT_SYNTHESIS_CONTEXT_MAXIMUM,
    warning_percent: int = DEFAULT_CONTEXT_WARNING_PERCENT,
) -> dict[str, Any]:
    return {
        "schemaVersion": SESSION_MANIFEST_SCHEMA_VERSION,
        "recordType": "customer-session-manifest",
        "testArtifactWorkflowVersion": TEST_ARTIFACT_WORKFLOW_VERSION,
        "workspaceSlug": workspace_slug,
        "currentVersions": {"prototype": None, "questions": None},
        "versionCatalog": {"prototypes": [], "questions": []},
        "contextBudget": {
            "unit": "characters",
            "perSessionMaximum": per_session_maximum,
            "synthesisMaximum": synthesis_maximum,
            "warningPercent": warning_percent,
        },
        "sessions": [],
        "synthesis": {
            "status": "not-generated",
            "packetPath": None,
            "generatedAt": None,
            "questionsVersion": None,
            "sessionIds": [],
            "summaryHashes": [],
            "packetSha256": None,
            "characters": None,
            "budgetStatus": "not-generated",
            "rawEvidenceIncluded": False,
        },
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }


def require_session_identifier(value: str, label: str) -> str:
    normalized = value.strip().upper()
    prefix = "S" if "session" in label.lower() else "P"
    if re.fullmatch(rf"{prefix}[0-9][A-Z0-9-]{{0,30}}", normalized) is None:
        raise SprintError(
            f"{label} must be a 3-32 character anonymized code starting with "
            f"{prefix} and a digit"
        )
    return normalized


def budget_status(characters: int, maximum: int, warning_percent: int) -> str:
    if characters > maximum:
        raise SprintError(
            f"Generated packet would use {characters}/{maximum} characters. "
            "Reduce the declared inputs; do not carry prior chats or raw transcripts forward."
        )
    if characters * 100 >= maximum * warning_percent:
        return "approaching-limit"
    return "within-budget"


def mark_synthesis_stale(manifest: dict[str, Any]) -> None:
    synthesis = manifest.get("synthesis", {})
    if isinstance(synthesis, dict) and synthesis.get("status") == "packet-generated":
        synthesis["status"] = "stale"


def find_session_entry(
    manifest: dict[str, Any], session_id: str
) -> dict[str, Any]:
    entry = next(
        (
            item
            for item in manifest.get("sessions", [])
            if isinstance(item, dict) and item.get("sessionId") == session_id
        ),
        None,
    )
    if entry is None:
        raise SprintError(f"Session is not registered in the manifest: {session_id}")
    return entry


def load_session_bundle(
    workspace: Path, session_id: str
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    Path,
    Path,
]:
    manifest = load_session_manifest(workspace)
    entry = find_session_entry(manifest, session_id)
    record_path = workspace_relative_file(
        workspace, str(entry["recordPath"]), "Session record"
    )
    summary_path = workspace_relative_file(
        workspace, str(entry["summaryPath"]), "Session summary"
    )
    record = load_session_record(record_path)
    summary = load_session_summary(summary_path)
    return manifest, entry, record, summary, record_path, summary_path


def sync_customer_testing_from_manifest(
    state: dict[str, Any], manifest: dict[str, Any]
) -> None:
    customer = state.setdefault("customerTesting", {})
    sessions = [
        item for item in manifest.get("sessions", []) if isinstance(item, dict)
    ]
    invited = max(int(customer.get("sessionsInvited", 0)), len(sessions))
    attempted = sum(item.get("attempted") is True for item in sessions)
    completed = sum(item.get("counted") is True for item in sessions)
    qualified = sum(item.get("participantFit") == "qualified" for item in sessions)
    excluded = sum(item.get("participantFit") == "excluded" for item in sessions)
    usable = sum(
        item.get("counted") is True and item.get("usable") is True
        for item in sessions
    )
    planned = int(customer.get("sessionsPlanned", 0))
    customer["sessionsPlanned"] = planned
    customer["sessionsInvited"] = invited
    customer["sessionsAttempted"] = attempted
    customer["sessionsCompleted"] = completed
    customer["sessionsQualified"] = qualified
    customer["sessionsExcluded"] = excluded
    customer["sessionsUsable"] = usable
    if customer.get("status") == "blocked" and (not planned or usable < planned):
        pass
    elif planned and usable >= planned:
        customer["status"] = "complete"
    elif completed:
        customer["status"] = "partial"
    elif attempted:
        customer["status"] = "in-progress"
    elif any(item.get("status") == "blocked" for item in sessions):
        customer["status"] = "blocked"
    elif sessions:
        customer["status"] = "scheduled"
    elif invited:
        customer["status"] = (
            "scheduled" if customer.get("status") == "scheduled" else "recruiting"
        )
    if sessions and not str(customer.get("target", "")).strip():
        customer["target"] = "Participants matching the approved recruitment criteria"
        customer["targetRationale"] = (
            "The session workflow was initialized before a more specific target was recorded."
        )


def persist_customer_documents(
    workspace: Path,
    state: dict[str, Any] | None,
    manifest: dict[str, Any],
    *,
    record_path: Path | None = None,
    record: dict[str, Any] | None = None,
    summary_path: Path | None = None,
    summary: dict[str, Any] | None = None,
    extra_texts: dict[Path, str] | None = None,
    timestamp: str | None = None,
) -> None:
    now = timestamp or utc_now()
    manifest["updatedAt"] = now
    require_valid_schema(
        manifest, "session-manifest", manifest_path(workspace)
    )
    outputs: dict[Path, str] = {
        manifest_path(workspace): json_text(manifest)
    }
    if record is not None:
        if record_path is None:
            raise SprintError("Internal error: a session record path is required")
        record["updatedAt"] = now
        require_valid_schema(record, "customer-session", record_path)
        outputs[record_path] = json_text(record)
    if summary is not None:
        if summary_path is None:
            raise SprintError("Internal error: a session summary path is required")
        summary["updatedAt"] = now
        require_valid_schema(summary, "session-summary", summary_path)
        outputs[summary_path] = json_text(summary)
    if state is not None:
        refresh_fidelity_summary(state)
        state["updatedAt"] = now
        require_valid_schema(state, "workspace-state", state_path(workspace))
        outputs[state_path(workspace)] = json_text(state)
    outputs.update(extra_texts or {})
    write_texts_atomically(outputs)


def catalog_version(
    manifest: dict[str, Any],
    catalog_name: str,
    version: str,
    candidate: dict[str, Any],
    *,
    activate: bool,
) -> None:
    entries = manifest["versionCatalog"][catalog_name]
    existing = next((item for item in entries if item["version"] == version), None)
    if existing is not None:
        comparable_existing = {key: value for key, value in existing.items() if key != "recordedAt"}
        comparable_candidate = {key: value for key, value in candidate.items() if key != "recordedAt"}
        if comparable_existing != comparable_candidate:
            raise SprintError(
                f"{catalog_name} version {version!r} is already bound to different content; "
                "use a new version identifier"
            )
    else:
        entries.append(candidate)
        entries.sort(key=lambda item: item["version"])
    current_key = "prototype" if catalog_name == "prototypes" else "questions"
    current = manifest["currentVersions"][current_key]
    if current is None or activate:
        manifest["currentVersions"][current_key] = version
    elif current != version:
        raise SprintError(
            f"Current {current_key} version is {current!r}; use --activate-versions "
            f"to make {version!r} current for new sessions"
        )


def session_summary_errors(
    summary: dict[str, Any], record: dict[str, Any], *, require_complete: bool
) -> list[str]:
    errors: list[str] = []
    for key in (
        "sessionId",
        "participantId",
        "sessionDate",
        "prototypeVersion",
        "questionsVersion",
    ):
        if summary.get(key) != record.get(key):
            errors.append(f"Summary {key} does not match the session record")
    serialized = json.dumps(summary, ensure_ascii=False)
    if re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", serialized, re.I):
        errors.append("Summary contains an email address; remove direct identifiers")
    sources = summary.get("sourceReferences", [])
    source_ids = [item.get("id") for item in sources if isinstance(item, dict)]
    if len(source_ids) != len(set(source_ids)):
        errors.append("Summary source-reference IDs must be unique")
    observations = summary.get("observations", [])
    observation_ids = [
        item.get("id") for item in observations if isinstance(item, dict)
    ]
    if len(observation_ids) != len(set(observation_ids)):
        errors.append("Summary observation IDs must be unique")
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        for source_id in observation.get("sourceReferenceIds", []):
            if source_id not in source_ids:
                errors.append(
                    f"Observation {observation.get('id')} references unknown source {source_id}"
                )
    for quote in summary.get("quoteReferences", []):
        if isinstance(quote, dict) and quote.get("sourceReferenceId") not in source_ids:
            errors.append(
                f"Quote pointer {quote.get('id')} references an unknown source"
            )
    inference_ids = [
        item.get("id")
        for item in summary.get("inferences", [])
        if isinstance(item, dict)
    ]
    quote_ids = [
        item.get("id")
        for item in summary.get("quoteReferences", [])
        if isinstance(item, dict)
    ]
    question_ids = [
        item.get("questionId")
        for item in summary.get("questionEvidence", [])
        if isinstance(item, dict)
    ]
    trace_ids = [*observation_ids, *inference_ids, *quote_ids, *question_ids]
    if len(trace_ids) != len(set(trace_ids)):
        errors.append("Summary synthesis trace IDs must be unique")
    task_ids = [
        item.get("taskId")
        for item in summary.get("taskOutcomes", [])
        if isinstance(item, dict)
    ]
    if len(task_ids) != len(set(task_ids)):
        errors.append("Summary task IDs must be unique")
    for collection_name in ("taskOutcomes", "questionEvidence"):
        for item in summary.get(collection_name, []):
            if not isinstance(item, dict):
                continue
            for observation_id in item.get("observationIds", []):
                if observation_id not in observation_ids:
                    errors.append(
                        f"{collection_name} entry references unknown observation {observation_id}"
                    )
    for inference in summary.get("inferences", []):
        if not isinstance(inference, dict):
            continue
        for observation_id in inference.get("observationIds", []):
            if observation_id not in observation_ids:
                errors.append(
                    f"Inference {inference.get('id')} references unknown observation {observation_id}"
                )
    if require_complete:
        if not str(summary.get("qualificationSummary", "")).strip():
            errors.append("Completed summary requires a qualification summary")
        if not sources:
            errors.append("Completed summary requires at least one audit source reference")
        for source in sources:
            if isinstance(source, dict) and source.get("redactionStatus") not in {
                "complete",
                "not-required",
            }:
                errors.append(
                    f"Completed summary source {source.get('id')} requires redaction review"
                )
        if not observations:
            errors.append("Completed summary requires at least one Observed item")
        if not summary.get("taskOutcomes"):
            errors.append("Completed summary requires task outcomes")
        if not summary.get("questionEvidence"):
            errors.append("Completed summary requires question-by-question evidence")
    return errors


def material_finding_errors(
    workspace: Path,
    data: dict[str, Any],
    assessment: dict[str, Any],
) -> list[str]:
    """Validate finding support, contradiction, participant, and version provenance."""

    errors: list[str] = []
    findings = data.get("materialFindings", [])
    usable = int(assessment.get("sessionCounts", {}).get("usable", 0))
    if (
        data.get("id") in {"12-synthesis", "13-outcome"}
        and data.get("status") in {"ready-for-decision", "complete"}
        and usable > 0
        and not findings
    ):
        errors.append(
            "A ready synthesis or outcome with usable sessions requires traceable materialFindings"
        )
    if not findings:
        return errors
    manifest = load_session_manifest(workspace)
    entries = {
        str(item["sessionId"]): item
        for item in manifest["sessions"]
        if isinstance(item, dict)
    }
    summary_cache: dict[str, dict[str, Any]] = {}
    for finding_index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            continue
        direct_support = False
        for collection_name in ("support", "contradictions", "outliers"):
            for source_index, source in enumerate(finding.get(collection_name, [])):
                if not isinstance(source, dict):
                    continue
                prefix = (
                    f"materialFindings[{finding_index}].{collection_name}[{source_index}]"
                )
                session_id = str(source.get("sessionId", ""))
                entry = entries.get(session_id)
                if entry is None:
                    errors.append(f"{prefix} references unknown session {session_id}")
                    continue
                for source_key, entry_key in (
                    ("participantId", "participantId"),
                    ("prototypeVersion", "prototypeVersion"),
                    ("questionsVersion", "questionsVersion"),
                ):
                    if source.get(source_key) != entry.get(entry_key):
                        errors.append(
                            f"{prefix}.{source_key} does not match session {session_id}"
                        )
                if collection_name == "support" and not entry.get("usable"):
                    errors.append(
                        f"{prefix} uses non-usable session {session_id} as finding support"
                    )
                if collection_name in {"contradictions", "outliers"} and not entry.get("counted"):
                    errors.append(
                        f"{prefix} uses a non-complete session as retained evidence"
                    )
                summary = summary_cache.get(session_id)
                if summary is None:
                    summary_path = workspace_relative_file(
                        workspace,
                        str(entry["summaryPath"]),
                        f"Finding provenance summary {session_id}",
                    )
                    summary = load_session_summary(summary_path)
                    summary_cache[session_id] = summary
                source_type = source.get("sourceType")
                if source_type == "direct-observation":
                    known_ids = {
                        str(item["id"])
                        for item in summary["observations"]
                        if isinstance(item, dict)
                    }
                    if collection_name == "support":
                        direct_support = True
                else:
                    known_ids = {
                        str(item["id"])
                        for item in summary["inferences"]
                        if isinstance(item, dict)
                    }
                unknown = sorted(set(source.get("evidenceIds", [])) - known_ids)
                if unknown:
                    errors.append(
                        f"{prefix}.evidenceIds contains unknown {source_type} IDs: {', '.join(unknown)}"
                    )
        if finding.get("directness") == "direct-observation" and not direct_support:
            errors.append(
                f"materialFindings[{finding_index}] claims direct observation without direct support"
            )
        impact = finding.get("nextDecision", {}).get("impact")
        if impact == "correct-observed-failure" and not direct_support:
            errors.append(
                f"materialFindings[{finding_index}] cannot justify a correction without direct observed support"
            )
        evidence = assessment.get("evidenceStrength", {})
        if impact == "bounded-reversible-investment" and (
            evidence.get("band") in {"not-tested", "early-limited"}
            or evidence.get("mixedSegments")
            or evidence.get("mixedQuality")
            or evidence.get("mixedVersions")
            or evidence.get("mixedEvidence")
        ):
            errors.append(
                f"materialFindings[{finding_index}] does not support a bounded investment under the current evidence limitations"
            )
    return errors


def command_init(args: argparse.Namespace) -> None:
    title = args.title.strip()
    challenge = args.challenge.strip()
    if not title or not challenge:
        raise SprintError("Both --title and --challenge are required")
    load_artifact_specs()
    load_step_guidance()
    now = utc_now()
    method_profile = args.method_profile
    execution_mode = args.execution_mode
    selected_by = args.selected_by.strip()
    mode_reason = args.mode_reason.strip()
    if not selected_by or not mode_reason:
        raise SprintError(
            "Execution-mode selection requires explicit --selected-by and --mode-reason values"
        )
    combination_errors = profile_mode_route_errors(
        method_profile, execution_mode, "undecided"
    )
    if combination_errors:
        raise SprintError("; ".join(combination_errors))
    if args.session_context_maximum < 1000:
        raise SprintError("--session-context-maximum must be at least 1000 characters")
    if args.synthesis_context_maximum < 1000:
        raise SprintError("--synthesis-context-maximum must be at least 1000 characters")
    if not 1 <= args.context_warning_percent <= 99:
        raise SprintError("--context-warning-percent must be between 1 and 99")
    fidelity = build_fidelity(method_profile, execution_mode)
    contract = load_method_contract()
    session_target = 0
    if method_profile == "sprint-book" and execution_mode == "live":
        session_target = int(
            contract["methodProfiles"][method_profile][
                "defaultCustomerSessionTarget"
            ]
        )
    output = workspace_path(args.output or f"design-sprint-{slugify(title)}")
    if output.exists():
        if not output.is_dir():
            raise SprintError(f"Output path is not a directory: {output}")
        if any(output.iterdir()):
            raise SprintError(f"Output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for directory in (
        "artifact-data",
        "artifacts",
        "assets",
        "prototype",
        "working",
        f"{CUSTOMER_TESTING_DIR}/sessions",
        f"{CUSTOMER_TESTING_DIR}/synthesis",
    ):
        (output / directory).mkdir(parents=True, exist_ok=True)
    write_text(output / ".gitignore", WORKSPACE_GITIGNORE)
    state = {
        "schemaVersion": STATE_SCHEMA_VERSION,
        "title": title,
        "slug": slugify(title),
        "challenge": challenge,
        "methodProfile": method_profile,
        "executionMode": execution_mode,
        "route": "undecided",
        "methodProfileSelection": selection_record(
            selected_by,
            args.profile_reason
            or "Selected when the workspace was initialised.",
        ),
        "executionModeSelection": selection_record(
            selected_by,
            mode_reason,
        ),
        "fidelity": fidelity,
        "routeHistory": [],
        "status": "waiting-for-human",
        "terminalState": "not-terminal",
        "currentStep": "01-intake",
        "completedSteps": [],
        "skippedSteps": [],
        "notApplicableSteps": [],
        "skipReasons": {},
        "skipRecords": [],
        "pendingGate": None,
        "humanGates": [
            {"id": gate_id, "name": name, "status": "pending"}
            for gate_id, name in GATE_NAMES.items()
        ],
        "decisions": [],
        "artifacts": [],
        "customerTesting": {
            "status": "not-planned",
            "target": (
                "Five suitable customers matching the approved recruitment criteria"
                if session_target == 5
                else ""
            ),
            "targetRationale": (
                "The Sprint-book live profile defaults to five suitable one-to-one sessions."
                if session_target == 5
                else ""
            ),
            "sessionsPlanned": session_target,
            "sessionsInvited": 0,
            "sessionsAttempted": 0,
            "sessionsCompleted": 0,
            "sessionsQualified": 0,
            "sessionsExcluded": 0,
            "sessionsUsable": 0,
        },
        "openQuestions": [
            "Who is the specific target customer?",
            "What outcome must this sprint enable?",
            "What evidence and constraints already exist?",
        ],
        "nextAction": {
            "title": "Complete the sprint intake",
            "body": "Clarify the customer, desired outcome, constraints, evidence, and deadline.",
            "humanInput": "Answer the intake questions or approve a proposed draft.",
        },
        "createdAt": now,
        "updatedAt": now,
    }
    save_state(output, state, timestamp=now)
    save_assignment_manifest(output, empty_assignment_manifest(now), timestamp=now)
    save_artifact_data(
        output / "artifact-data" / "01-sprint-brief.json",
        initial_brief_data(challenge, now),
    )
    manifest = initial_session_manifest(
        state["slug"],
        now,
        args.session_context_maximum,
        args.synthesis_context_maximum,
        args.context_warning_percent,
    )
    require_valid_schema(
        manifest, "session-manifest", manifest_path(output)
    )
    write_json(manifest_path(output), manifest)
    render_workspace(output)
    print(f"Created sprint workspace: {output}")
    print(f"Dashboard: {output / 'index.html'}")


def command_new_artifact(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, specs, artifacts = load_workspace_documents(workspace)
    if args.id not in specs:
        raise SprintError(f"Unknown artifact id: {args.id}")
    data_path = workspace / "artifact-data" / f"{args.id}.json"
    if data_path.exists():
        raise SprintError(f"Artifact data already exists: {data_path}")
    existing = next(
        (path for path, data in artifacts if data["id"] == args.id), None
    )
    if existing is not None:
        raise SprintError(f"Artifact data for {args.id!r} already exists: {existing}")
    now = utc_now()
    save_artifact_data(
        data_path, new_artifact_data(args.id, specs[args.id], now, state)
    )
    save_state(workspace, state, timestamp=now)
    render_workspace(workspace)
    print(f"Created artifact draft: {data_path}")


def command_set_artifact_status(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, specs, _artifacts = load_workspace_documents(workspace)
    state_errors = validate_state(state)
    if state_errors:
        raise SprintError(
            "Cannot change artifact status from an invalid workflow state: "
            + "; ".join(state_errors)
        )
    if args.status not in ARTIFACT_STATUSES:
        raise SprintError(f"Invalid artifact status: {args.status}")
    data_path = workspace / "artifact-data" / f"{args.id}.json"
    data = load_artifact_data(data_path)
    now = utc_now()
    data["status"] = args.status
    data["updatedAt"] = now
    errors = artifact_data_errors(data, specs)
    errors.extend(evidence_claim_errors(data, state))
    errors.extend(
        artifact_status_context_errors(state, specs, args.id, args.status)
    )
    if errors:
        raise SprintError(f"Artifact {args.id} is invalid: {'; '.join(errors)}")
    save_artifact_data(data_path, data)
    save_state(workspace, state, timestamp=now)
    render_workspace(workspace)
    print(f"Updated {args.id} to {args.status}")


def command_set_route(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    if args.route not in ROUTES - {"undecided"}:
        raise SprintError(f"Invalid sprint route: {args.route}")
    state, _specs, _artifacts = load_workspace_documents(workspace)
    existing_decision_errors = decision_record_errors(state)
    if existing_decision_errors:
        raise SprintError(
            "Decision provenance is invalid: " + "; ".join(existing_decision_errors)
        )
    previous_route = state.get("route")
    rationale = args.rationale.strip()
    if not rationale:
        raise SprintError("A route transition requires a non-empty rationale")
    transition_errors = route_change_errors(state, args.route)
    if transition_errors:
        raise SprintError("; ".join(transition_errors))
    now = utc_now()
    state.setdefault("routeHistory", []).append(
        route_transition_record(str(previous_route), args.route, rationale, now)
    )
    apply_route(state, args.route)
    state["routeRationale"] = rationale
    route_changed_after_decision = (
        previous_route != args.route
        and active_gate_decision(state, "gate-1") is not None
    )
    if route_changed_after_decision:
        supersede_gate_decision(
            state,
            "gate-1",
            f"Material research changed the sprint route from {previous_route} to {args.route}.",
            now,
        )
        if "03-evidence" in state.get("completedSteps", []):
            state["currentStep"] = "03-evidence"
        state["nextAction"] = {
            "title": "Re-approve the post-research route",
            "body": "Material research changed the route, so the earlier Gate 1 attestation was superseded.",
            "humanInput": "Record a new human decision for the changed route.",
        }
    if (
        not route_changed_after_decision
        and previous_route == "research-first"
        and "03-evidence" in state.get("completedSteps", [])
    ):
        following = next_step("03-evidence", excluded_steps(state))
        if args.route == "no-sprint":
            following = "13-outcome"
            for gate in state.get("humanGates", []):
                if gate.get("id") in NO_SPRINT_NOT_APPLICABLE_GATES:
                    gate["status"] = "not-applicable"
        if following:
            state["currentStep"] = following
            state["status"] = "active"
            state["nextAction"] = {
                "title": step_name(following),
                "body": "The route was updated after the research-first stage.",
                "humanInput": "None unless the next step requires a decision.",
            }
    elif not route_changed_after_decision:
        state["nextAction"] = {
            "title": "Approve the sprint route",
            "body": f"Review the recommendation for {args.route.replace('-', ' ')}.",
            "humanInput": "Approve the challenge and route, or request a revision.",
        }
    transition_errors = validate_state(state)
    if transition_errors:
        raise SprintError(
            "Route transition would create an invalid workspace: "
            + "; ".join(transition_errors)
        )
    save_state(workspace, state, timestamp=now)
    render_workspace(workspace)
    print(f"Set sprint route: {args.route}")


def command_set_concept(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    existing_decision_errors = decision_record_errors(state)
    if existing_decision_errors:
        raise SprintError(
            "Decision provenance is invalid: " + "; ".join(existing_decision_errors)
        )
    concept = args.concept.strip()
    if not concept:
        raise SprintError("Selected concept cannot be empty")
    previous = state.get("selectedConcept")
    state["selectedConcept"] = concept
    state["selectedConceptRationale"] = args.rationale.strip()
    now = utc_now()
    if previous and previous != concept and active_gate_decision(state, "gate-3"):
        supersede_gate_decision(
            state,
            "gate-3",
            "Material research changed the selected concept from "
            f"{previous!r} to {concept!r}.",
            now,
        )
        state["currentStep"] = "08-decide"
        state["nextAction"] = {
            "title": "Re-approve the selected concept",
            "body": "Material research changed the concept, so the earlier Gate 3 attestation was superseded.",
            "humanInput": "Record a new human decision for the changed concept.",
        }
    else:
        state["nextAction"] = {
            "title": "Approve the selected concept",
            "body": "Review the selected direction and its evidence-backed rationale.",
            "humanInput": "Approve the concept at Gate 3 or request a revision.",
        }
    transition_errors = validate_state(state)
    if transition_errors:
        raise SprintError(
            "Concept update would create an invalid workspace: "
            + "; ".join(transition_errors)
        )
    save_state(workspace, state, timestamp=now)
    render_workspace(workspace)
    print(f"Set selected concept: {concept}")


def command_set_method_profile(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state = load_state(workspace)
    if state.get("completedSteps"):
        raise SprintError(
            "Method profile cannot change after a step is complete; start a new workspace or revise the legacy state deliberately"
        )
    errors = profile_mode_route_errors(
        args.profile, state.get("executionMode"), state.get("route")
    )
    if errors:
        raise SprintError("; ".join(errors))
    selected_by = args.selected_by.strip()
    reason = args.reason.strip()
    if not selected_by or not reason:
        raise SprintError("Method-profile selection requires a selector and reason")
    state["methodProfile"] = args.profile
    state["methodProfileSelection"] = selection_record(
        selected_by, reason
    )
    state["fidelity"] = build_fidelity(
        args.profile, str(state["executionMode"])
    )
    customer = state.setdefault("customerTesting", {})
    if args.profile == "sprint-book" and state["executionMode"] == "live":
        customer.update(
            {
                "status": "not-planned",
                "target": "Five suitable customers matching the approved recruitment criteria",
                "targetRationale": "The Sprint-book live profile defaults to five suitable one-to-one sessions.",
                "sessionsPlanned": 5,
                "sessionsCompleted": 0,
            }
        )
    elif int(customer.get("sessionsCompleted", 0)) == 0:
        customer.update(
            {
                "status": "not-planned",
                "target": "",
                "targetRationale": "",
                "sessionsPlanned": 0,
            }
        )
    apply_route(state, str(state["route"]))
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Set method profile: {args.profile}")


def command_set_execution_mode(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state = load_state(workspace)
    if state.get("completedSteps") or state.get("skippedSteps"):
        raise SprintError(
            "Execution mode cannot change after a step is complete; create or restart a workspace so evidence history stays truthful"
        )
    if manifest_path(workspace).exists():
        session_manifest = load_session_manifest(workspace)
        if session_manifest.get("sessions"):
            raise SprintError(
                "Execution mode cannot change after a live customer-session record exists; restart in a new workspace so the session history stays truthful"
            )
    customer = state.get("customerTesting", {})
    if args.mode != "live" and int(customer.get("sessionsCompleted", 0)) > 0:
        raise SprintError(
            "Cannot switch a workspace with recorded live customer sessions to a non-live mode"
        )
    errors = profile_mode_route_errors(
        state.get("methodProfile"), args.mode, state.get("route")
    )
    if errors:
        raise SprintError("; ".join(errors))
    selected_by = args.selected_by.strip()
    reason = args.reason.strip()
    if not selected_by or not reason:
        raise SprintError("Execution-mode selection requires a selector and reason")
    state["executionMode"] = args.mode
    state["terminalState"] = "not-terminal"
    state["executionModeSelection"] = selection_record(
        selected_by, reason
    )
    state["fidelity"] = build_fidelity(
        str(state["methodProfile"]), args.mode
    )
    if state["methodProfile"] == "sprint-book" and args.mode == "live":
        customer.update(
            {
                "status": "not-planned",
                "target": "Five suitable customers matching the approved recruitment criteria",
                "targetRationale": "The Sprint-book live profile defaults to five suitable one-to-one sessions.",
                "sessionsPlanned": 5,
                "sessionsCompleted": 0,
            }
        )
    elif args.mode != "live":
        customer.update(
            {
                "status": "not-planned",
                "target": "No live customer sessions in this execution mode",
                "targetRationale": "Non-live execution modes cannot produce customer evidence.",
                "sessionsPlanned": 0,
                "sessionsCompleted": 0,
            }
        )
    apply_route(state, str(state["route"]))
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Set execution mode: {args.mode}")


def command_record_fidelity(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state = load_state(workspace)
    record = state["fidelity"]["steps"][args.step]
    changed = False
    if args.selected_method is not None:
        selected_method = args.selected_method.strip()
        if not selected_method:
            raise SprintError("Selected method cannot be empty")
        record["selectedMethod"] = selected_method
        changed = True
    if args.human_participant is not None:
        record["participants"]["human"] = args.human_participant
        changed = True
    if args.ai_participant is not None:
        record["participants"]["ai"] = args.ai_participant
        changed = True
    if args.actual_minutes is not None:
        if args.actual_minutes < 0:
            raise SprintError("Actual timebox cannot be negative")
        record["timebox"]["actualMinutes"] = args.actual_minutes
        changed = True
    if args.deviation_type:
        required_values = {
            "reason": args.reason,
            "method impact": args.method_impact,
            "evidence impact": args.evidence_impact,
            "decision-readiness impact": args.decision_impact,
        }
        missing = [name for name, value in required_values.items() if not value]
        if missing:
            raise SprintError(
                "A fidelity deviation requires " + ", ".join(missing)
            )
        if args.deviation_type == "substitution" and not args.preserved_purpose:
            raise SprintError(
                "A substitution requires --preserved-purpose to show how the learning purpose survives"
            )
        selected_method = str(record["selectedMethod"])
        if (
            args.deviation_type in {"substitution", "omission", "skip"}
            and selected_method == str(record["defaultMethod"])
        ):
            raise SprintError(
                "Record the substituted, compressed, omitted, or skipped method with --selected-method"
            )
        add_fidelity_deviation(
            state,
            args.step,
            {
                "id": f"manual-{len(record.get('deviations', [])) + 1}",
                "type": args.deviation_type,
                "canonicalMethod": args.canonical_method
                or record["defaultMethod"],
                "selectedMethod": selected_method,
                "preservedPurpose": args.preserved_purpose
                or "The purpose is only partially preserved; see the impacts.",
                "reason": args.reason.strip(),
                "impact": impact_record(
                    args.method_impact.strip(),
                    args.evidence_impact.strip(),
                    args.decision_impact.strip(),
                ),
                "recordedAt": utc_now(),
            },
        )
        changed = True
    if not changed:
        raise SprintError("No fidelity update was supplied")
    errors = fidelity_errors(state)
    if errors:
        raise SprintError("; ".join(errors))
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Updated fidelity record: {args.step}")


def command_set_challenge(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    challenge = args.challenge.strip()
    if not challenge:
        raise SprintError("Challenge cannot be empty")
    now = utc_now()
    state, _specs, _artifacts = load_workspace_documents(workspace)
    state["challenge"] = challenge
    brief_path = workspace / "artifact-data" / "01-sprint-brief.json"
    brief = load_artifact_data(brief_path)
    for section in brief.get("sections", []):
        if isinstance(section, dict) and section.get("title") == "Challenge":
            section["type"] = "paragraphs"
            section["paragraphs"] = [challenge]
            for key in ("items", "rows", "cards", "body"):
                section.pop(key, None)
    if brief.get("summary"):
        brief["summary"][0] = challenge
    else:
        brief["summary"] = [challenge]
    brief["updatedAt"] = now
    save_artifact_data(brief_path, brief)
    save_state(workspace, state, timestamp=now)
    render_workspace(workspace)
    print("Updated the sprint challenge")


def command_question(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    questions = state.setdefault("openQuestions", [])
    if args.add:
        question = args.add.strip()
        if not question:
            raise SprintError("Question cannot be empty")
        if question not in questions:
            questions.append(question)
        action = "Added"
    else:
        question = args.resolve.strip()
        if question not in questions:
            raise SprintError(f"Open question not found: {question}")
        questions.remove(question)
        state.setdefault("resolvedQuestions", []).append(
            {"question": question, "resolvedAt": utc_now()}
        )
        action = "Resolved"
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"{action} question: {question}")


def required_artifacts_for_step(step_id: str) -> list[str]:
    specs = load_artifact_specs()
    return sorted(
        artifact_id for artifact_id, spec in specs.items() if spec.get("step") == step_id
    )


def artifact_status(workspace: Path, artifact_id: str) -> str | None:
    path = workspace / "artifact-data" / f"{artifact_id}.json"
    if not path.exists():
        return None
    return str(load_artifact_data(path).get("status"))


def artifact_documents_by_id(
    artifacts: list[tuple[Path, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    return {str(data["id"]): data for _path, data in artifacts}


def artifact_status_context_errors(
    state: dict[str, Any],
    specs: dict[str, dict[str, Any]],
    artifact_id: str,
    status: str,
) -> list[str]:
    """Enforce the workflow context represented by an artifact status."""

    spec = specs.get(artifact_id)
    if spec is None:
        return [f"Unknown artifact id: {artifact_id}"]
    step_id = str(spec["step"])
    gate_id = GATE_BY_STEP.get(step_id)
    completed = step_id in state.get("completedSteps", [])
    gates = {
        gate.get("id"): gate
        for gate in state.get("humanGates", [])
        if isinstance(gate, dict)
    }
    errors: list[str] = []
    if status == "ready-for-decision":
        if gate_id is None:
            errors.append(
                f"Artifact {artifact_id} cannot be ready-for-decision because "
                f"step {step_id} has no human decision gate; mark it complete"
            )
        elif state.get("currentStep") != step_id:
            errors.append(
                f"Artifact {artifact_id} may be ready-for-decision only while "
                f"{step_id} is the current step"
            )
        elif gates.get(gate_id, {}).get("status") != "pending":
            errors.append(
                f"Artifact {artifact_id} cannot be ready-for-decision after "
                f"{gate_id} has closed"
            )
        elif completed and state.get("pendingGate") != gate_id:
            errors.append(
                f"Completed step {step_id} requires pendingGate {gate_id} while "
                f"artifact {artifact_id} is ready-for-decision"
            )
        elif not completed and state.get("pendingGate") is not None:
            errors.append(
                f"Artifact {artifact_id} cannot begin {gate_id} review while "
                f"another gate is pending"
            )
    if completed:
        allowed = (
            {"ready-for-decision", "complete"}
            if gate_id
            and gates.get(gate_id, {}).get("status") == "pending"
            and state.get("pendingGate") == gate_id
            else {"complete"}
        )
        if status not in allowed:
            errors.append(
                f"Completed step {step_id} requires artifact {artifact_id} "
                f"status {' or '.join(sorted(allowed))}; found {status}"
            )
    return errors


def gate_artifact_errors(
    gate_id: str,
    artifacts: dict[str, dict[str, Any]],
) -> list[str]:
    step_id = next(step for step, gate in GATE_BY_STEP.items() if gate == gate_id)
    errors: list[str] = []
    for artifact_id in required_artifacts_for_step(step_id):
        artifact = artifacts.get(artifact_id)
        status = artifact.get("status") if artifact else "missing"
        if status != "complete":
            errors.append(
                f"Cannot close {gate_id}: artifact {artifact_id} must be complete; "
                f"found {status}. ready-for-decision only permits the gate review to begin"
            )
    return errors


def artifact_workflow_errors(
    state: dict[str, Any],
    specs: dict[str, dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
) -> list[str]:
    """Cross-check artifact status against step, gate, and session state."""

    errors: list[str] = []
    gates = {
        gate.get("id"): gate
        for gate in state.get("humanGates", [])
        if isinstance(gate, dict)
    }
    for step_id in state.get("completedSteps", []):
        for artifact_id in required_artifacts_for_step(step_id):
            artifact = artifacts.get(artifact_id)
            status = artifact.get("status") if artifact else None
            gate_id = GATE_BY_STEP.get(step_id)
            gate_status = gates.get(gate_id, {}).get("status")
            allowed = (
                {"ready-for-decision", "complete"}
                if gate_id and gate_status == "pending"
                else {"complete"}
            )
            if status not in allowed:
                errors.append(
                    f"Completed step {step_id} requires artifact {artifact_id} "
                    f"status {' or '.join(sorted(allowed))}; found "
                    f"{status or 'missing'}"
                )
    for artifact_id, artifact in artifacts.items():
        status = str(artifact.get("status"))
        if status == "ready-for-decision":
            errors.extend(
                artifact_status_context_errors(
                    state, specs, artifact_id, status
                )
            )
    return errors


def command_complete_step(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    existing_errors = validate_state(state)
    if existing_errors:
        raise SprintError(
            "Cannot complete a step from an invalid workflow state: "
            + "; ".join(existing_errors)
        )
    assignment_manifest = load_assignment_manifest(workspace)
    step_id = args.step
    if step_id not in STEP_INDEX:
        raise SprintError(f"Unknown step: {step_id}")
    if state.get("currentStep") != step_id:
        raise SprintError(
            f"Current step is {state.get('currentStep')}; cannot complete {step_id}"
        )
    if step_id in state.get("completedSteps", []):
        raise SprintError(f"Step is already complete: {step_id}")
    disposition = effective_route_step_policy(state).get(step_id)
    if disposition != STEP_REQUIRED:
        raise SprintError(
            f"Step {step_id} is {disposition or 'undefined'} for route "
            f"{state.get('route')} and cannot be completed"
        )
    if step_id == "02-qualify" and state.get("route") == "undecided":
        raise SprintError("Set the sprint route before completing 02-qualify")
    if step_id == "03-evidence" and state.get("executionMode") == "live":
        try:
            _plan_path, _plan_data, recruitment_plan = load_recruitment_plan_artifact(
                workspace
            )
        except SprintError as error:
            raise SprintError(
                "Live evidence work requires an early structured recruitment plan: "
                f"{error}"
            ) from error
        readiness_errors = recruitment_plan_errors(
            recruitment_plan, require_ready=True, state=state
        )
        if readiness_errors:
            raise SprintError(
                "Recruitment is not ready to leave the evidence step:\n"
                + "\n".join(f"- {item}" for item in readiness_errors)
            )
    if step_id == "10-prototype":
        _brief_path, brief_data, brief = load_prototype_brief_artifact(workspace)
        if brief_data.get("status") != "complete":
            raise SprintError(
                "The approved structured prototype/MVP brief must remain complete"
            )
        if not brief.get("currentVersion"):
            raise SprintError(
                "Freeze a trial-passed immutable tested version before completing 10-prototype"
            )
        record_errors = prototype_record_errors(workspace, brief_data)
        if record_errors:
            raise SprintError(
                "Prototype build, trial, or version records are invalid:\n"
                + "\n".join(f"- {item}" for item in record_errors)
            )
    if step_id == "11-customer-sessions":
        if state.get("executionMode") != "live":
            raise SprintError(
                "Non-live execution modes cannot complete real-customer sessions; skip the step with an explicit reason and fidelity impact"
            )
        customer = state.get("customerTesting", {})
        try:
            session_manifest = load_session_manifest(workspace)
        except SprintError as error:
            raise SprintError(
                "A canonical customer-session manifest is required before completing testing"
            ) from error
        record_errors = customer_testing_record_errors(workspace, state)
        if record_errors:
            raise SprintError(
                "Customer-session records are not valid:\n"
                + "\n".join(f"- {item}" for item in record_errors)
            )
        canonical_completed = sum(
            item["counted"] for item in session_manifest["sessions"]
        )
        if canonical_completed != int(customer.get("sessionsCompleted", 0)):
            raise SprintError(
                "Customer-session count does not match the canonical manifest"
            )
        if canonical_completed < 1:
            state["status"] = "waiting-for-customers"
            state["nextAction"] = {
                "title": "Run real-customer sessions",
                "body": "Customer testing cannot be completed without at least one real session.",
                "humanInput": "Complete and record suitable customer sessions.",
            }
            save_state(workspace, state)
            render_workspace(workspace)
            raise SprintError("At least one real customer session is required")
        customer_status = state.get("customerTesting", {}).get("status")
        if customer_status not in {"complete", "partial"}:
            raise SprintError(
                "Customer sessions may complete only when customerTesting.status "
                "is complete or partial"
            )
    if step_id == "12-synthesis":
        session_manifest = load_session_manifest(workspace)
        if session_manifest["synthesis"]["status"] != "packet-generated":
            raise SprintError(
                "Generate a current bounded synthesis packet before completing synthesis"
            )
        record_errors = customer_testing_record_errors(workspace, state)
        if record_errors:
            raise SprintError(
                "Synthesis inputs are not current and traceable:\n"
                + "\n".join(f"- {item}" for item in record_errors)
            )
        synthesis_data_path = workspace / "artifact-data" / "12-synthesis.json"
        if synthesis_data_path.exists():
            trace_errors = synthesis_artifact_trace_errors(
                workspace, load_artifact_data(synthesis_data_path)
            )
            if trace_errors:
                raise SprintError(
                    "Synthesis claims are not traceable:\n"
                    + "\n".join(f"- {item}" for item in trace_errors)
                )
    for artifact_id in required_artifacts_for_step(step_id):
        status = artifact_status(workspace, artifact_id)
        allowed = {"ready-for-decision", "complete"} if step_id in GATE_BY_STEP else {"complete"}
        if status not in allowed:
            raise SprintError(
                f"Artifact {artifact_id} must have status {' or '.join(sorted(allowed))}; found {status or 'missing'}"
            )
    assignment_errors = required_assignment_errors(assignment_manifest, step_id)
    if assignment_errors:
        raise SprintError(
            f"Required specialist results are incomplete for {step_id}: "
            + "; ".join(assignment_errors)
        )
    state.setdefault("completedSteps", []).append(step_id)
    gate_id = GATE_BY_STEP.get(step_id)
    if gate_id:
        state["pendingGate"] = gate_id
        state["status"] = "waiting-for-human"
        state["nextAction"] = {
            "title": GATE_NAMES[gate_id],
            "body": f"Review the completed {step_name(step_id).lower()} work.",
            "humanInput": "Record the Decider's decision and rationale.",
        }
    else:
        if step_id == "03-evidence" and state.get("route") == "research-first":
            state["status"] = "waiting-for-human"
            state["nextAction"] = {
                "title": "Choose the post-research route",
                "body": "Review the evidence and decide whether to run a foundation sprint, design sprint, focused sprint, or no sprint.",
                "humanInput": "Approve the next route.",
            }
        else:
            following = next_step(step_id, excluded_steps(state))
            if following:
                state["currentStep"] = following
                state["status"] = "active"
                state["nextAction"] = {
                    "title": step_name(following),
                    "body": "Begin the next sprint step.",
                    "humanInput": "None unless the Orchestrator identifies a required decision.",
                }
    transition_errors = validate_state(state)
    if transition_errors:
        raise SprintError(
            "Completing the step would create an invalid transition: "
            + "; ".join(transition_errors)
        )
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Completed step: {step_id}")


def command_skip_step(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    existing_errors = validate_state(state)
    if existing_errors:
        raise SprintError(
            "Cannot skip from an invalid workflow state: "
            + "; ".join(existing_errors)
        )
    step_id = args.step
    if state.get("currentStep") != step_id:
        raise SprintError(f"Only the current step may be skipped: {state.get('currentStep')}")
    reason = args.reason.strip()
    skipped_by = args.skipped_by.strip()
    if not reason or not skipped_by:
        raise SprintError("A skipped step requires a reason and the person who approved it")
    policy_error = skip_policy_error(state, step_id)
    if policy_error:
        raise SprintError(policy_error)
    add_skip(state, step_id, reason, skipped_by)
    following = next_step(step_id, excluded_steps(state))
    if following is None:
        raise SprintError("Cannot skip the final remaining step")
    state["currentStep"] = following
    state["status"] = "active"
    state["nextAction"] = {
        "title": step_name(following),
        "body": f"Step {step_id} was skipped: {reason}",
        "humanInput": "None unless the next step requires a decision.",
    }
    transition_errors = validate_state(state)
    if transition_errors:
        raise SprintError(
            "Skipping the step would create an invalid transition: "
            + "; ".join(transition_errors)
        )
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Skipped step: {step_id}")


def active_gate_decision(
    state: dict[str, Any], gate_id: str
) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in reversed(state.get("decisions", []))
            if isinstance(item, dict)
            and item.get("gate") == gate_id
            and item.get("status") == "active"
        ),
        None,
    )


def clear_gate_attestation(gate: dict[str, Any]) -> None:
    for key in (
        "decisionId",
        "decision",
        "deciderLabel",
        "rationale",
        "decidedAt",
    ):
        gate.pop(key, None)


def supersede_gate_decision(
    state: dict[str, Any], gate_id: str, reason: str, timestamp: str
) -> None:
    decision = active_gate_decision(state, gate_id)
    if decision is None:
        return
    decision["status"] = "superseded"
    decision["supersededAt"] = timestamp
    decision["supersededReason"] = reason
    for gate in state.get("humanGates", []):
        if isinstance(gate, dict) and gate.get("id") == gate_id:
            clear_gate_attestation(gate)
            gate["status"] = "pending"
            break
    state["pendingGate"] = gate_id
    state["status"] = "waiting-for-human"


def provenance_record(kind: str, reference: str, digest: str) -> dict[str, str]:
    return {"kind": kind, "reference": reference, "digest": digest}


def value_digest(kind: str, value: str) -> str:
    return digest_bytes(f"{kind}\0{value}".encode("utf-8"))


def resolve_decision_input(
    workspace: Path,
    state: dict[str, Any],
    manifest: dict[str, Any],
    value: str,
) -> dict[str, str]:
    raw = value.strip()
    if not raw:
        raise SprintError("Considered input cannot be empty")
    if ":" in raw:
        requested_kind, reference = raw.split(":", 1)
    elif assignment_by_id(manifest, raw):
        requested_kind, reference = "assignment", raw
    elif (workspace / "artifact-data" / f"{raw}.json").is_file():
        requested_kind, reference = "artifact", raw
    else:
        raise SprintError(
            f"Unknown considered input {raw!r}; use artifact:<id>, assignment:<id>, "
            "route:<route>, concept:<label>, or record:<label>"
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", reference):
        raise SprintError(
            "Considered-input references must be safe labels, not paths or raw evidence"
        )
    if requested_kind == "artifact":
        path = workspace / "artifact-data" / f"{reference}.json"
        if not path.is_file():
            raise SprintError(f"Unknown considered artifact: {reference}")
        return provenance_record("artifact", reference, file_digest(path))
    if requested_kind in {"assignment", "assignment-result"}:
        assignment = assignment_by_id(manifest, reference)
        result = assignment.get("resultMemo") if assignment else None
        if (
            not isinstance(result, dict)
            or assignment.get("status") not in {"returned", "accepted"}
        ):
            raise SprintError(
                f"Considered assignment {reference} has no valid returned result memo"
            )
        return provenance_record(
            "assignment-result", reference, str(result["digest"])
        )
    if requested_kind == "prototype":
        if reference != "prototype":
            raise SprintError("Prototype provenance reference must be prototype")
        _brief_path, _brief_data, brief = load_prototype_brief_artifact(workspace)
        current = brief.get("currentVersion")
        summary = next(
            (
                item
                for item in brief.get("versions", [])
                if item.get("version") == current
            ),
            None,
        )
        if summary is None:
            raise SprintError(
                "Prototype provenance requires a frozen immutable tested version"
            )
        path = workspace_relative_file(
            workspace, summary["recordPath"], "Immutable tested-version record"
        )
        return provenance_record(
            "prototype", f"prototype:{current}", file_digest(path)
        )
    if requested_kind == "route":
        if reference != state.get("route"):
            raise SprintError(
                f"Considered route {reference!r} does not match the current route"
            )
        return provenance_record("route", reference, value_digest("route", reference))
    if requested_kind == "concept":
        selected_concept = str(state.get("selectedConcept", ""))
        if reference not in {selected_concept, "selected-concept"}:
            raise SprintError(
                f"Considered concept {reference!r} does not match the selected concept"
            )
        return provenance_record(
            "concept", "selected-concept", value_digest("concept", selected_concept)
        )
    if requested_kind == "record":
        return provenance_record("record", reference, value_digest("record", reference))
    raise SprintError(f"Unsupported considered-input kind: {requested_kind}")


def gate_considered_inputs(
    workspace: Path,
    state: dict[str, Any],
    manifest: dict[str, Any],
    gate_id: str,
    supplied: list[str],
) -> list[dict[str, str]]:
    default_kind, default_reference = GATE_DEFAULT_INPUTS[gate_id]
    records = [
        resolve_decision_input(
            workspace,
            state,
            manifest,
            f"{default_kind}:{default_reference}",
        )
    ]
    if gate_id == "gate-1":
        records.append(
            resolve_decision_input(
                workspace, state, manifest, f"route:{state['route']}"
            )
        )
    elif gate_id == "gate-3":
        records.append(
            resolve_decision_input(
                workspace,
                state,
                manifest,
                "concept:selected-concept",
            )
        )
    records.extend(
        resolve_decision_input(workspace, state, manifest, value)
        for value in supplied
    )
    unique = {
        (item["kind"], item["reference"], item["digest"]): item
        for item in records
    }
    return [unique[key] for key in sorted(unique)]


def decision_subject(
    state: dict[str, Any], gate_id: str, decision: str
) -> dict[str, str]:
    if gate_id == "gate-1":
        kind = "route"
        value = str(state["route"])
    elif gate_id == "gate-3":
        kind = "concept"
        value = str(state.get("selectedConcept") or decision)
    else:
        kind = "gate"
        value = gate_id
    return {"kind": kind, "value": value, "digest": value_digest(kind, value)}


def command_gate(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, artifacts = load_workspace_documents(workspace)
    existing_errors = validate_state(state)
    if existing_errors:
        raise SprintError(
            "Cannot close a gate from an invalid workflow state: "
            + "; ".join(existing_errors)
        )
    manifest = load_assignment_manifest(workspace)
    existing_decision_errors = decision_record_errors(state)
    if existing_decision_errors:
        raise SprintError(
            "Decision provenance is invalid: " + "; ".join(existing_decision_errors)
        )
    gate_id = args.gate
    if gate_id not in GATE_NAMES:
        raise SprintError(f"Unknown gate: {gate_id}")
    if state.get("pendingGate") != gate_id:
        raise SprintError(f"Pending gate is {state.get('pendingGate')}; cannot record {gate_id}")
    if gate_id == "gate-1" and state.get("route") == "undecided":
        raise SprintError("Gate 1 requires an approved sprint route")
    decision_text = args.decision.strip()
    rationale = (args.rationale or "").strip()
    if not decision_text:
        raise SprintError("A gate decision cannot be empty")
    artifact_map = artifact_documents_by_id(artifacts)
    readiness_errors = gate_artifact_errors(gate_id, artifact_map)
    if readiness_errors:
        raise SprintError("; ".join(readiness_errors))
    if gate_id == "gate-3":
        concept = (args.concept or state.get("selectedConcept") or decision_text).strip()
        if not concept:
            raise SprintError("Gate 3 requires a selected concept")
        state["selectedConcept"] = concept
    normalized = decision_text.lower()
    customer = state.get("customerTesting", {})
    if gate_id == "gate-5":
        if normalized not in FINAL_OUTCOMES:
            raise SprintError(
                "Gate 5 decision must be Proceed, Iterate, Pivot, Investigate, or Stop"
            )
        if normalized in {"proceed", "iterate", "pivot"} and int(
            customer.get("sessionsCompleted", 0)
        ) < 1:
            raise SprintError(
                "Proceed, Iterate, or Pivot requires at least one real customer session; use Investigate or Stop otherwise"
            )
    now = utc_now()
    decision_count = sum(
        1
        for item in state.get("decisions", [])
        if isinstance(item, dict) and item.get("gate") == gate_id
    )
    decision = {
        "id": f"{gate_id}-decision-{decision_count + 1}",
        "gate": gate_id,
        "decision": decision_text,
        "deciderLabel": args.decider.strip(),
        "consideredInputs": gate_considered_inputs(
            workspace, state, manifest, gate_id, args.considered_input
        ),
        "subject": decision_subject(state, gate_id, decision_text),
        "rationale": rationale,
        "reservations": args.reservations.strip() if args.reservations else "",
        "status": "active",
        "decidedAt": now,
    }
    if not decision["decision"] or not decision["deciderLabel"]:
        raise SprintError("Decision and decider label cannot be empty")
    state.setdefault("decisions", []).append(decision)
    for gate in state.get("humanGates", []):
        if gate.get("id") == gate_id:
            gate.update(
                {
                    "status": "complete",
                    "decisionId": decision["id"],
                    "decision": decision["decision"],
                    "deciderLabel": decision["deciderLabel"],
                    "rationale": decision["rationale"],
                    "decidedAt": decision["decidedAt"],
                }
            )
    state["pendingGate"] = None
    current = str(state["currentStep"])
    if gate_id == "gate-5":
        state["status"] = "complete"
        state["outcome"] = decision_text
        state["terminalState"] = expected_terminal_state(state)
        validation_label, validation_notice, _validation_class = validation_truth(
            state
        )
        state["nextAction"] = {
            "title": f"{validation_label}: {decision_text}",
            "body": validation_notice
            + " Use the outcome artifact and owned next actions for the handoff.",
            "humanInput": "None.",
        }
    else:
        if gate_id == "gate-1":
            apply_route(state, str(state["route"]))
        following = next_step(current, excluded_steps(state))
        if gate_id == "gate-1" and state.get("route") == "no-sprint":
            following = "13-outcome"
            for gate in state.get("humanGates", []):
                if gate.get("id") in {"gate-2", "gate-3", "gate-4"}:
                    gate["status"] = "not-applicable"
        if following is None:
            raise SprintError("No next step exists after this gate")
        state["currentStep"] = following
        state["status"] = "active"
        state["nextAction"] = {
            "title": step_name(following),
            "body": "The human gate is complete. Begin the next sprint step.",
            "humanInput": "None unless the Orchestrator identifies a required decision.",
        }
    if gate_id == "gate-5":
        session_errors = customer_testing_record_errors(workspace, state)
        if session_errors:
            raise SprintError(
                "Customer-session records are not valid:\n"
                + "\n".join(f"- {item}" for item in session_errors)
            )
    transition_errors = validate_state(state)
    if transition_errors:
        raise SprintError(
            f"Closing {gate_id} would create an invalid transition: "
            + "; ".join(transition_errors)
        )
    save_state(workspace, state, timestamp=now)
    render_workspace(workspace)
    print(f"Recorded {gate_id}: {decision_text}")


def command_prototype_recommend(args: argparse.Namespace) -> None:
    """Recommend the lowest ladder rung and provider-neutral route from test needs."""

    if args.real_service_required:
        level = "limited-pilot"
        rationale = "The hypothesis depends on a limited real service, not a simulated interaction."
    elif args.real_behavior_required:
        level = "live-mvp"
        rationale = "The hypothesis depends on real behavior, persistence, transactions, integrations, or repeated use."
    elif args.code_fidelity_required:
        level = "coded-facade"
        rationale = "Realistic coded behavior is required, while operational capabilities may remain controlled or mocked."
    elif args.interaction_required:
        level = "clickable"
        rationale = "A clickable flow can produce authentic interaction evidence without operational product code."
    elif args.manual_service:
        level = "concierge"
        rationale = "A manually operated service test can answer the question before software is built."
    else:
        level = "copy-concept"
        rationale = "Copy or a concept stimulus is sufficient to answer the current sprint question."

    if args.existing_product and level in {"live-mvp", "limited-pilot"}:
        route = "existing-product-slice"
        category = "existing-application-stack"
        tool_reason = "Use a feature-flagged or access-limited slice in the existing stack."
    elif args.no_external_tools:
        if level in {"live-mvp", "limited-pilot"}:
            raise SprintError(
                "A new live behavior or real-service test cannot use the no-external-tool route unless --existing-product is supplied"
            )
        if level == "clickable":
            level = "coded-facade"
            rationale += " With external interaction tools unavailable, use a small native coded facade."
        route = "no-external-tool"
        category = "native-repository" if level == "coded-facade" else "none"
        tool_reason = "Use repository-native files or manual materials without an external service."
    elif level == "clickable":
        route = "interaction-design"
        category = "interaction-design"
        tool_reason = "Use an interaction-design category; provider examples are optional guidance."
    elif level == "coded-facade":
        route = "portable-coded-facade"
        category = "native-repository"
        tool_reason = "Use portable repository-native HTML, CSS, and JavaScript."
    elif level in {"live-mvp", "limited-pilot"}:
        route = "live-service-pilot" if level == "limited-pilot" else "ai-assisted-app-builder"
        category = "ai-app-builder"
        tool_reason = "Select a coded builder or stack only after account, cost, data, and deployment approval."
    else:
        route = "no-external-tool"
        category = "none"
        tool_reason = "No external product-building tool is required."

    print(
        json.dumps(
            {
                "artifactLevel": level,
                "toolRoute": route,
                "toolCategory": category,
                "rationale": rationale,
                "toolRationale": tool_reason,
                "approvalBoundaries": list(PROTOTYPE_APPROVAL_BOUNDARIES),
                "readinessBoundary": (
                    "A live URL does not establish customer validation or production readiness."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


def load_prototype_brief_artifact(
    workspace: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    path = workspace / "artifact-data" / f"{PROTOTYPE_BRIEF_ID}.json"
    if not path.exists():
        raise SprintError(
            "Create and complete 10-prototype-brief before building a test artifact"
        )
    data = load_artifact_data(path)
    brief = data.get("prototypeBrief")
    if not isinstance(brief, dict):
        raise SprintError("The prototype/MVP artifact is missing its structured brief")
    return path, data, brief


def command_prototype_approve(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, specs, _artifacts = load_workspace_documents(workspace)
    path, data, brief = load_prototype_brief_artifact(workspace)
    key = PROTOTYPE_APPROVAL_BOUNDARIES[args.boundary]
    now = utc_now()
    brief["approvals"][key] = {
        "status": args.status,
        "deciderLabel": args.decider.strip(),
        "rationale": args.rationale.strip(),
        "decidedAt": now,
    }
    if not args.decider.strip() or not args.rationale.strip():
        raise SprintError("Prototype approvals require a Decider label and rationale")
    if args.status == "declined":
        data["status"] = "blocked"
    elif data.get("status") == "blocked":
        data["status"] = "in-review"
    data["updatedAt"] = now
    errors = artifact_data_errors(data, specs)
    if errors:
        raise SprintError("Prototype approval is invalid: " + "; ".join(errors))
    save_artifact_data(path, data)
    save_state(workspace, state, timestamp=now)
    render_workspace(workspace)
    print(f"Recorded prototype boundary {args.boundary}: {args.status}")


def command_prototype_build_packet(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, specs, _artifacts = load_workspace_documents(workspace)
    path, data, brief = load_prototype_brief_artifact(workspace)
    if data.get("status") != "complete":
        raise SprintError("The structured prototype/MVP brief must be complete and approved before generating a build packet")
    errors = prototype_brief_errors(brief, require_approved=True)
    if errors:
        raise SprintError("The approved prototype/MVP brief is invalid: " + "; ".join(errors))
    assets = [
        file_source_descriptor(
            workspace, value, f"Approved build asset {index}", reject_sensitive=True
        )
        for index, value in enumerate(args.asset, 1)
    ]
    snapshot = approved_prototype_brief_snapshot(brief)
    snapshot_text = json_text(snapshot)
    brief_sha = sha256_bytes(snapshot_text.encode("utf-8"))
    asset_blocks = []
    for descriptor in assets:
        asset_path = workspace_relative_file(
            workspace, descriptor["path"], "Approved build asset"
        )
        try:
            asset_text = asset_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            asset_text = "[Binary asset: use only the explicitly approved file at the recorded path.]"
        asset_blocks.append(
            f"## Approved asset — `{descriptor['path']}`\n\n"
            f"SHA-256: `{descriptor['sha256']}`  \nBytes: `{descriptor['bytes']}`\n\n"
            f"<approved-asset path=\"{descriptor['path']}\">\n{asset_text.rstrip()}\n</approved-asset>"
        )
    packet = f"""# Approved AI build packet

This packet is the complete build boundary. Do not load sprint history, private transcripts, secrets, production customer data, account material, or any file not listed below. Do not connect accounts, incur cost, enable analytics, change production, or deploy publicly unless the matching human approval is recorded in the approved brief.

Build only the smallest approved artifact and stop at the recorded timebox. Clearly label mocked and manually operated behavior. Generated output still requires accessibility, flow, content, security, and data-exposure review.

## Approved structured brief

SHA-256: `{brief_sha}`

```json
{snapshot_text.rstrip()}
```

{chr(10).join(asset_blocks) if asset_blocks else "## Approved assets\n\nNo additional assets were approved."}

## Stop condition

Return the bounded artifact, changed-file list, review notes, and unresolved issues when the approved scenes work or the timebox expires. Do not expand scope.
"""
    output_value = args.output or f"working/10-prototype/build-packet-{brief_sha[:12]}.md"
    output_path, output_relative = resolved_workspace_file(
        workspace, output_value, below="working/10-prototype"
    )
    if output_path.exists():
        raise SprintError(f"Build packet path already exists; packets are immutable: {output_relative}")
    now = utc_now()
    brief["buildPackets"].append(
        {
            "path": output_relative,
            "sha256": sha256_text(packet),
            "briefSha256": brief_sha,
            "assets": assets,
            "generatedAt": now,
        }
    )
    data["updatedAt"] = now
    errors = artifact_data_errors(data, specs)
    if errors:
        raise SprintError("Build packet record is invalid: " + "; ".join(errors))
    write_text(output_path, packet)
    save_artifact_data(path, data)
    save_state(workspace, state, timestamp=now)
    render_workspace(workspace)
    print(f"Wrote approved AI build packet: {output_path}")


def command_prototype_trial(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, specs, _artifacts = load_workspace_documents(workspace)
    path, data, brief = load_prototype_brief_artifact(workspace)
    if data.get("status") != "complete" or not brief["buildPackets"]:
        raise SprintError("A complete approved brief and immutable build packet are required before the moderated trial")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", args.trial_id) is None:
        raise SprintError("--trial-id has an invalid identifier")
    if any(item["id"] == args.trial_id for item in brief["trialRuns"]):
        raise SprintError(f"Trial-run ID already exists: {args.trial_id}")
    test_plan_path = workspace / "artifact-data" / "10-test-plan.json"
    test_plan = load_artifact_data(test_plan_path)
    if test_plan.get("status") != "complete":
        raise SprintError("The actual customer test plan and interview guide must be complete before the trial")
    script_path = workspace_relative_file(
        workspace, args.interview_script, "Trial interview script"
    )
    if script_path != test_plan_path.resolve():
        raise SprintError("The moderated trial must use artifact-data/10-test-plan.json as the actual interview script")
    script_text = script_path.read_text(encoding="utf-8")
    script_payload = script_text.encode("utf-8")
    script_snapshot_path = (
        workspace
        / "working"
        / "10-prototype"
        / "trials"
        / args.trial_id
        / "interview-script.json"
    )
    if script_snapshot_path.exists():
        raise SprintError(
            f"Immutable trial script snapshot already exists: {script_snapshot_path}"
        )
    script_descriptor = {
        "path": script_snapshot_path.relative_to(workspace).as_posix(),
        "sha256": sha256_bytes(script_payload),
        "bytes": len(script_payload),
    }
    tested = file_source_descriptor(workspace, args.prototype, "Trial prototype")
    prototype_parts = Path(tested["path"]).parts
    if not prototype_parts or prototype_parts[0] != "prototype":
        raise SprintError("The trial prototype must be stored below prototype/")
    findings = [item.strip() for item in args.finding if item.strip()]
    if not findings:
        raise SprintError("A moderated trial requires at least one recorded finding")
    now = utc_now()
    brief["trialRuns"].append(
        {
            "id": args.trial_id,
            "status": args.status,
            "moderator": args.moderator.strip(),
            "interviewScript": script_descriptor,
            "testedArtifact": tested,
            "findings": findings,
            "issues": [item.strip() for item in args.issue if item.strip()],
            "ranAt": now,
        }
    )
    data["updatedAt"] = now
    errors = artifact_data_errors(data, specs)
    if errors:
        raise SprintError("Trial-run record is invalid: " + "; ".join(errors))
    write_text(script_snapshot_path, script_text)
    save_artifact_data(path, data)
    save_state(workspace, state, timestamp=now)
    render_workspace(workspace)
    print(f"Recorded moderated trial {args.trial_id}: {args.status}")


def command_prototype_freeze(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, specs, _artifacts = load_workspace_documents(workspace)
    path, data, brief = load_prototype_brief_artifact(workspace)
    if data.get("status") != "complete":
        raise SprintError("The approved structured brief must be complete before freezing a tested version")
    version = args.version.strip()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version) is None:
        raise SprintError("--version has an invalid version identifier")
    if any(item["version"] == version for item in brief["versions"]):
        raise SprintError(f"Tested version already exists and is immutable: {version}")
    trial = next((item for item in brief["trialRuns"] if item["id"] == args.trial_run), None)
    if trial is None or trial.get("status") != "passed":
        raise SprintError("A passed moderated trial is required before freezing a tested version")
    prototype = file_source_descriptor(workspace, args.prototype, "Tested prototype")
    context = file_source_descriptor(workspace, args.prototype_context, "Tested prototype context")
    for descriptor, label in ((prototype, "prototype"), (context, "context")):
        parts = Path(descriptor["path"]).parts
        if len(parts) < 3 or parts[0] != "prototype" or parts[1] != version:
            raise SprintError(
                f"The tested {label} must use the immutable version directory prototype/{version}/"
            )
    if prototype != trial["testedArtifact"]:
        raise SprintError("The artifact changed after the passed trial; run a new moderated trial")
    linked: dict[str, Any] = {}
    linked_outputs: dict[Path, str] = {}
    for artifact_id, key in (
        ("08-experiment", "experiment"),
        ("09-storyboard", "storyboard"),
        ("10-test-plan", "testPlan"),
    ):
        artifact_path = workspace / "artifact-data" / f"{artifact_id}.json"
        artifact = load_artifact_data(artifact_path)
        if artifact.get("status") != "complete":
            raise SprintError(f"{artifact_id} must be complete before a tested version is frozen")
        artifact_text = artifact_path.read_text(encoding="utf-8")
        artifact_payload = artifact_text.encode("utf-8")
        snapshot_path = (
            workspace / "prototype" / version / "sources" / f"{artifact_id}.json"
        )
        if snapshot_path.exists():
            raise SprintError(
                f"Immutable tested-version source already exists: {snapshot_path}"
            )
        linked_outputs[snapshot_path] = artifact_text
        linked[key] = {
            "path": snapshot_path.relative_to(workspace).as_posix(),
            "sha256": sha256_bytes(artifact_payload),
            "bytes": len(artifact_payload),
        }
    if trial["interviewScript"]["sha256"] != linked["testPlan"]["sha256"]:
        raise SprintError(
            "The customer test plan changed after the moderated trial; run a new trial with the actual current script"
        )
    packet_summary = brief["buildPackets"][-1]
    packet = file_source_descriptor(
        workspace, packet_summary["path"], "Approved AI build packet"
    )
    is_public = args.access_model == "public"
    if (
        args.access_model != "private-local"
        and brief["approvals"]["externalAccount"]["status"] != "approved"
    ):
        raise SprintError(
            "A hosted deployment record requires explicit human approval for any external account"
        )
    if is_public and brief["approvals"]["publicDeployment"]["status"] != "approved":
        raise SprintError("A public deployment cannot be recorded without explicit human approval")
    if is_public and not args.url:
        raise SprintError("A public deployment record requires --url")
    if args.url and safe_url(args.url) is None:
        raise SprintError("--url must be an absolute http or https URL")
    now = utc_now()
    snapshot = approved_prototype_brief_snapshot(brief)
    brief_sha = sha256_bytes(json_text(snapshot).encode("utf-8"))
    if packet_summary["briefSha256"] != brief_sha:
        raise SprintError(
            "The approved brief changed after the latest AI build packet; generate a new bounded packet and rebuild"
        )
    record = {
        "schemaVersion": TEST_ARTIFACT_WORKFLOW_VERSION,
        "recordType": "tested-prototype-version",
        "version": version,
        "artifactLevel": brief["artifactLevel"],
        "prototypeArtifact": prototype,
        "prototypeContext": context,
        "approvedBrief": {"sha256": brief_sha, "snapshot": snapshot},
        "buildPacket": packet,
        "trialRun": copy.deepcopy(trial),
        "linkedArtifacts": linked,
        "deployment": {
            "target": args.deployment_target.strip(),
            "accessModel": args.access_model,
            "public": is_public,
            "url": args.url,
            "expiresAt": args.expires_at,
            "cleanupPlan": args.cleanup_plan.strip(),
            "rollbackPlan": args.rollback_plan.strip(),
            "recordedAt": now,
        },
        "claims": {
            "customerValidated": False,
            "productionReady": False,
            "statement": "A live URL and a passed trial do not establish customer validation or production readiness.",
        },
        "frozenAt": now,
    }
    record_path = workspace / "prototype" / version / "tested-version.json"
    if record_path.exists():
        raise SprintError(f"Immutable tested-version record already exists: {record_path}")
    require_valid_schema(record, "tested-version", record_path)
    record_text = json_text(record)
    summary = {
        "version": version,
        "recordPath": record_path.relative_to(workspace).as_posix(),
        "recordSha256": sha256_bytes(record_text.encode("utf-8")),
        "prototypePath": prototype["path"],
        "trialRunId": trial["id"],
        "deploymentUrl": args.url,
        "frozenAt": now,
    }
    brief["versions"].append(summary)
    brief["versions"].sort(key=lambda item: item["version"])
    brief["currentVersion"] = version
    data["updatedAt"] = now
    errors = artifact_data_errors(data, specs)
    if errors:
        raise SprintError("Tested-version record is invalid: " + "; ".join(errors))
    write_texts_atomically({**linked_outputs, record_path: record_text})
    save_artifact_data(path, data)
    save_state(workspace, state, timestamp=now)
    render_workspace(workspace)
    print(f"Frozen immutable tested version: {version}")
    print(f"Version record: {record_path}")


def session_tested_version(
    workspace: Path, version: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    _path, data, brief = load_prototype_brief_artifact(workspace)
    if data.get("status") != "complete":
        raise SprintError("Customer sessions require a complete approved prototype/MVP brief")
    summary = next(
        (item for item in brief["versions"] if item["version"] == version), None
    )
    if summary is None:
        raise SprintError(
            f"Prototype version {version!r} is not a frozen, trial-passed tested version"
        )
    record_path = workspace_relative_file(
        workspace, summary["recordPath"], "Immutable tested-version record"
    )
    payload = record_path.read_bytes()
    if sha256_bytes(payload) != summary["recordSha256"]:
        raise SprintError(
            f"Immutable tested-version record changed after freeze: {summary['recordPath']}"
        )
    record = load_tested_version(record_path)
    if record["version"] != version:
        raise SprintError("Tested-version summary and immutable record disagree")
    return record, source_descriptor(
        workspace, summary["recordPath"], "Immutable tested-version record"
    )


def command_session_init(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    if state.get("executionMode") != "live":
        raise SprintError("Customer sessions may only be initialized in live mode")
    if int(state.get("customerTesting", {}).get("sessionsPlanned", 0)) < 1:
        raise SprintError(
            "Record a positive planned customer-session target before initializing sessions"
        )
    now = utc_now()
    if manifest_path(workspace).exists():
        manifest = load_session_manifest(workspace)
    else:
        if int(state.get("customerTesting", {}).get("sessionsCompleted", 0)):
            raise SprintError(
                "Cannot bootstrap a manifest around aggregate completed sessions; "
                "reconstruct and validate the isolated records first"
            )
        manifest = initial_session_manifest(str(state["slug"]), now)
    session_id = require_session_identifier(args.session_id, "--session-id")
    participant_id = require_session_identifier(
        args.participant_id, "--participant-id"
    )
    if any(item.get("sessionId") == session_id for item in manifest["sessions"]):
        raise SprintError(f"Session already exists: {session_id}")
    prototype_version = args.prototype_version.strip()
    questions_version = args.questions_version.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", prototype_version):
        raise SprintError("--prototype-version has an invalid version identifier")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", questions_version):
        raise SprintError("--questions-version has an invalid version identifier")
    try:
        datetime.fromisoformat(args.session_date)
    except ValueError as error:
        raise SprintError("--session-date must be an ISO date (YYYY-MM-DD)") from error
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.session_date):
        raise SprintError("--session-date must be an ISO date (YYYY-MM-DD)")

    prototype_artifact = source_descriptor(
        workspace, args.prototype, "Prototype artifact"
    )
    prototype_context = source_descriptor(
        workspace, args.prototype_context, "Prototype context"
    )
    tested_version: dict[str, Any] | None = None
    if manifest.get("testArtifactWorkflowVersion") == TEST_ARTIFACT_WORKFLOW_VERSION:
        tested_record, tested_version = session_tested_version(
            workspace, prototype_version
        )
        for label, supplied, frozen in (
            ("prototype", prototype_artifact, tested_record["prototypeArtifact"]),
            ("prototype context", prototype_context, tested_record["prototypeContext"]),
        ):
            if (
                supplied["path"] != frozen["path"]
                or supplied["sha256"] != frozen["sha256"]
            ):
                raise SprintError(
                    f"Session {label} does not match immutable tested version {prototype_version}"
                )
    interview_guide = source_descriptor(
        workspace, args.interview_guide, "Interview guide"
    )
    scorecard = source_descriptor(workspace, args.scorecard, "Scorecard")
    prior_decisions = [
        source_descriptor(workspace, value, "Required prior decision")
        for value in args.prior_decision
    ]
    prototype_candidate = {
        "version": prototype_version,
        "prototypeArtifact": prototype_artifact,
        "prototypeContext": prototype_context,
        "recordedAt": now,
    }
    if tested_version is not None:
        prototype_candidate["testedVersion"] = tested_version
    catalog_version(
        manifest,
        "prototypes",
        prototype_version,
        prototype_candidate,
        activate=args.activate_versions,
    )
    catalog_version(
        manifest,
        "questions",
        questions_version,
        {
            "version": questions_version,
            "interviewGuide": interview_guide,
            "scorecard": scorecard,
            "recordedAt": now,
        },
        activate=args.activate_versions,
    )
    duplicate = next(
        (
            item
            for item in manifest["sessions"]
            if item["participantId"] == participant_id
            and item["sessionDate"] == args.session_date
            and item["prototypeVersion"] == prototype_version
            and item["questionsVersion"] == questions_version
        ),
        None,
    )
    if duplicate is not None:
        raise SprintError(
            "The same participant/date/version combination is already registered "
            f"as {duplicate['sessionId']}; refusing a possible double-count"
        )

    directory = session_directory(workspace, session_id)
    if directory.exists() and any(directory.iterdir()):
        raise SprintError(f"Session directory is not empty: {directory}")
    record_path = directory / "session.json"
    summary_path = directory / "summary.json"
    record_relative = record_path.relative_to(workspace).as_posix()
    summary_relative = summary_path.relative_to(workspace).as_posix()
    consent_status = args.consent_status
    consent_recorded_at = now if consent_status != "pending" else None
    participant_fit = args.participant_fit
    participant_segment = args.participant_segment.strip()
    fit_rationale = args.fit_rationale.strip()
    if not participant_segment:
        raise SprintError("--participant-segment cannot be empty")
    if participant_fit != "unassessed" and not fit_rationale:
        raise SprintError(
            "A qualified or excluded participant requires --fit-rationale"
        )
    record = {
        "schemaVersion": CUSTOMER_SESSION_SCHEMA_VERSION,
        "recordType": "customer-session",
        "sessionId": session_id,
        "participantId": participant_id,
        "sessionDate": args.session_date,
        "runMode": args.run_mode,
        "status": "initialized",
        "participant": {
            "segment": participant_segment,
            "fit": participant_fit,
            "fitRationale": fit_rationale,
        },
        "evidenceQuality": {
            "attemptedAt": None,
            "protocolFidelity": "not-assessed",
            "criticalScenariosCovered": [],
            "usable": False,
            "exclusionReason": "",
        },
        "prototypeVersion": prototype_version,
        "questionsVersion": questions_version,
        "artifacts": {
            "prototypeArtifact": prototype_artifact,
            "prototypeContext": prototype_context,
            "interviewGuide": interview_guide,
            "scorecard": scorecard,
            "priorDecisions": prior_decisions,
            "summaryPath": summary_relative,
        },
        "packet": {
            "path": None,
            "generatedAt": None,
            "sourceCharacters": None,
            "characters": None,
            "sha256": None,
            "budgetStatus": "not-generated",
            "freshChatRequired": True,
        },
        "checkpoint": {
            "phase": "ready-for-packet",
            "nextAction": "Generate the participant handoff packet and start a fresh chat.",
            "completedPhases": ["session-initialized"],
            "lastPersistedAt": now,
        },
        "consent": {
            "status": consent_status,
            "recordedAt": consent_recorded_at,
            "scope": (args.consent_scope or "").strip(),
            "reference": (args.consent_reference or "").strip(),
        },
        "redaction": {
            "status": args.redaction_status,
            "reviewedAt": (
                now
                if args.redaction_status in {"complete", "not-required"}
                else None
            ),
            "removedCategories": [],
        },
        "rawEvidence": [],
        "limitations": [],
        "usage": {
            "measurementContext": "customer-session",
            "available": False,
            "measurements": [],
            "unavailableReason": "The runtime has not exposed session usage measurements.",
        },
        "reopenHistory": [],
        "createdAt": now,
        "updatedAt": now,
    }
    if tested_version is not None:
        record["artifacts"]["testedVersion"] = tested_version
    summary = {
        "schemaVersion": SESSION_SUMMARY_SCHEMA_VERSION,
        "recordType": "customer-session-summary",
        "sessionId": session_id,
        "participantId": participant_id,
        "sessionDate": args.session_date,
        "prototypeVersion": prototype_version,
        "questionsVersion": questions_version,
        "status": "draft",
        "anonymized": True,
        "containsDirectIdentifiers": False,
        "qualificationSummary": "",
        "sourceReferences": [],
        "observations": [],
        "inferences": [],
        "quoteReferences": [],
        "taskOutcomes": [],
        "questionEvidence": [],
        "surprises": [],
        "moderatorDeviations": [],
        "limitations": [],
        "uncertainties": [],
        "createdAt": now,
        "updatedAt": now,
    }
    if tested_version is not None:
        summary["testedVersion"] = tested_version
    entry = {
        "sessionId": session_id,
        "participantId": participant_id,
        "sessionDate": args.session_date,
        "prototypeVersion": prototype_version,
        "questionsVersion": questions_version,
        "participantSegment": participant_segment,
        "participantFit": participant_fit,
        "protocolFidelity": "not-assessed",
        "criticalScenariosCovered": [],
        "attempted": False,
        "usable": False,
        "exclusionReason": "",
        "status": "initialized",
        "recordPath": record_relative,
        "summaryPath": summary_relative,
        "summarySha256": None,
        "packetPath": None,
        "includeInSynthesis": False,
        "counted": False,
        "createdAt": now,
        "updatedAt": now,
    }
    if tested_version is not None:
        entry["testedVersion"] = tested_version
    manifest["sessions"].append(entry)
    manifest["sessions"].sort(key=lambda item: item["sessionId"])
    mark_synthesis_stale(manifest)
    sync_customer_testing_from_manifest(state, manifest)
    persist_customer_documents(
        workspace,
        state,
        manifest,
        record_path=record_path,
        record=record,
        summary_path=summary_path,
        summary=summary,
        timestamp=now,
    )
    render_workspace(workspace)
    print(f"Initialized isolated customer session: {session_id}")
    print(f"Record: {record_path}")
    print(f"Next: session-packet --workspace {workspace} --session-id {session_id}")


def packet_document_block(title: str, descriptor: dict[str, Any], text: str) -> str:
    return (
        f"## {title}\n\n"
        f"Source: `{descriptor['path']}`  \n"
        f"SHA-256: `{descriptor['sha256']}`\n\n"
        f"<declared-input name=\"{title}\">\n{text.rstrip()}\n</declared-input>\n"
    )


def summary_for_handoff(summary: dict[str, Any]) -> dict[str, Any]:
    sanitized = copy.deepcopy(summary)
    sanitized["sourceReferences"] = [
        {
            "id": item["id"],
            "kind": item["kind"],
            "redactionStatus": item["redactionStatus"],
        }
        for item in summary.get("sourceReferences", [])
    ]
    return sanitized


def command_session_packet(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    manifest, entry, record, summary, record_path, summary_path = load_session_bundle(
        workspace, require_session_identifier(args.session_id, "--session-id")
    )
    if record["status"] == "complete":
        raise SprintError("Completed sessions must be reopened before generating a new packet")
    if record["status"] == "withdrawn":
        raise SprintError("A withdrawn session cannot receive another participant packet")
    if record["consent"]["status"] in {"declined", "withdrawn"}:
        raise SprintError("A participant who declined or withdrew consent cannot receive a session packet")
    artifacts = record["artifacts"]
    prototype_context = descriptor_text(
        workspace, artifacts["prototypeContext"], "Prototype context"
    )
    interview_guide = descriptor_text(
        workspace, artifacts["interviewGuide"], "Interview guide"
    )
    scorecard = descriptor_text(workspace, artifacts["scorecard"], "Scorecard")
    tested_version_line = (
        f"- Immutable tested-version record: `{artifacts['testedVersion']['path']}` "
        f"(SHA-256 `{artifacts['testedVersion']['sha256']}`)"
        if "testedVersion" in artifacts
        else "- Immutable tested-version record: legacy session without a version record"
    )
    prior_blocks: list[str] = []
    source_characters = len(prototype_context) + len(interview_guide) + len(scorecard)
    for index, descriptor in enumerate(artifacts["priorDecisions"], 1):
        value = descriptor_text(workspace, descriptor, f"Prior decision {index}")
        source_characters += len(value)
        prior_blocks.append(packet_document_block(f"Required prior decision {index}", descriptor, value))

    resume_block = ""
    if record["status"] in {"reopened", "in-progress", "blocked", "packet-generated"} and (
        summary.get("observations")
        or summary.get("taskOutcomes")
        or record["checkpoint"]["completedPhases"] != ["session-initialized"]
    ):
        persisted = {
            "checkpoint": record["checkpoint"],
            "structuredSummary": summary_for_handoff(summary),
        }
        resume_text = json.dumps(persisted, indent=2, ensure_ascii=False, sort_keys=True)
        source_characters += len(resume_text)
        resume_block = (
            "## Persisted resume checkpoint\n\n"
            "This replaces conversation replay. It contains no raw transcript content.\n\n"
            f"```json\n{resume_text}\n```\n\n"
        )

    prior_text = "\n".join(prior_blocks) or (
        "## Required prior decisions\n\nNo additional prior-decision documents were declared.\n"
    )
    packet = f"""# Fresh-chat customer-session handoff — {record['sessionId']}

Use this packet as the complete operating context for one fresh chat. Do not load the sprint history, another participant's files, or any raw transcript. Open only the prototype path named below while running the session.

## Session identity and versions

- Session ID: `{record['sessionId']}`
- Participant ID: `{record['participantId']}` (anonymized; keep the identity map elsewhere)
- Session date: `{record['sessionDate']}`
- Run mode: `{record['runMode']}`
- Prototype version: `{record['prototypeVersion']}`
- Questions version: `{record['questionsVersion']}`
- Prototype to open: `{artifacts['prototypeArtifact']['path']}`
{tested_version_line}
- Canonical session record: `{record_path.relative_to(workspace).as_posix()}`
- Structured summary to update: `{summary_path.relative_to(workspace).as_posix()}`

## Operating instructions

1. Confirm consent before recording or using agent assistance. Test the prototype, not the participant.
2. Follow the interview guide neutrally, present one task at a time, and record behaviour before interpretation.
3. Keep raw notes/transcripts in this session's separately protected source location. Never inspect another session.
4. Update the structured summary with separate `Observed` and `Inference` items, moderator deviations, and audit pointers; do not copy raw transcript passages into it.
5. Persist the checkpoint and summary before the chat ends. If context becomes crowded, stop and resume in another fresh chat from a regenerated packet.
6. Do not change the prototype or sprint questions under these version IDs. Initialize a new version when either changes.

{packet_document_block('Prototype context', artifacts['prototypeContext'], prototype_context)}

{packet_document_block('Interview guide', artifacts['interviewGuide'], interview_guide)}

{packet_document_block('Shared scorecard', artifacts['scorecard'], scorecard)}

{prior_text}

{resume_block}## Required return state

- Persist a structured, anonymized summary with observations, separate inferences, source/quote pointers, task outcomes, question evidence, moderator deviations, surprises, limitations, and uncertainties.
- Persist the checkpoint phase, completed phases, and next action.
- Record consent/redaction status and runtime usage when the runtime exposes it; otherwise preserve the unavailable reason.
- End without synthesizing across participants. Cross-session synthesis happens only in its separate packet.
"""
    budget = manifest["contextBudget"]
    packet_status = budget_status(
        len(packet), budget["perSessionMaximum"], budget["warningPercent"]
    )
    now = utc_now()
    packet_path = session_directory(workspace, record["sessionId"]) / "handoff.md"
    packet_relative = packet_path.relative_to(workspace).as_posix()
    record["packet"] = {
        "path": packet_relative,
        "generatedAt": now,
        "sourceCharacters": source_characters,
        "characters": len(packet),
        "sha256": sha256_text(packet),
        "budgetStatus": packet_status,
        "freshChatRequired": True,
    }
    record["status"] = "packet-generated"
    record["checkpoint"]["phase"] = "ready-to-run"
    record["checkpoint"]["nextAction"] = "Start a fresh chat using only handoff.md."
    record["checkpoint"]["lastPersistedAt"] = now
    entry["status"] = "packet-generated"
    entry["packetPath"] = packet_relative
    entry["updatedAt"] = now
    sync_customer_testing_from_manifest(state, manifest)
    persist_customer_documents(
        workspace,
        state,
        manifest,
        record_path=record_path,
        record=record,
        summary_path=summary_path,
        summary=summary,
        extra_texts={packet_path: packet},
        timestamp=now,
    )
    render_workspace(workspace)
    print(
        f"Wrote fresh-chat packet: {packet_path} "
        f"({len(packet)}/{budget['perSessionMaximum']} characters)"
    )
    if packet_status == "approaching-limit":
        print("Warning: participant packet is approaching its context budget")
    print("Fresh chat required: yes")


def command_session_checkpoint(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    manifest, entry, record, summary, record_path, summary_path = load_session_bundle(
        workspace, require_session_identifier(args.session_id, "--session-id")
    )
    if record["status"] == "complete":
        raise SprintError("Reopen a completed session before changing its checkpoint")
    now = utc_now()
    record["status"] = args.status
    record["checkpoint"]["phase"] = args.phase.strip()
    record["checkpoint"]["nextAction"] = args.next_action.strip()
    for phase in args.completed_phase:
        value = phase.strip()
        if value and value not in record["checkpoint"]["completedPhases"]:
            record["checkpoint"]["completedPhases"].append(value)
    record["checkpoint"]["lastPersistedAt"] = now
    entry["status"] = args.status
    entry["updatedAt"] = now
    if args.status == "in-progress":
        record["evidenceQuality"]["attemptedAt"] = (
            record["evidenceQuality"].get("attemptedAt") or now
        )
        entry["attempted"] = True
    if args.status == "withdrawn":
        entry["counted"] = False
        entry["includeInSynthesis"] = False
        entry["usable"] = False
        record["evidenceQuality"]["usable"] = False
        mark_synthesis_stale(manifest)
    sync_customer_testing_from_manifest(state, manifest)
    persist_customer_documents(
        workspace,
        state,
        manifest,
        record_path=record_path,
        record=record,
        summary_path=summary_path,
        summary=summary,
        timestamp=now,
    )
    render_workspace(workspace)
    print(f"Persisted checkpoint for {record['sessionId']}: {args.status}")


def usage_measurements_from_args(args: argparse.Namespace) -> list[dict[str, Any]]:
    definitions = (
        ("inputTokens", args.usage_input_tokens, "tokens"),
        ("outputTokens", args.usage_output_tokens, "tokens"),
        ("totalTokens", args.usage_total_tokens, "tokens"),
        ("requests", args.usage_requests, "requests"),
        ("durationSeconds", args.usage_duration_seconds, "seconds"),
    )
    measurements: list[dict[str, Any]] = []
    if any(value is not None for _name, value, _unit in definitions) and not args.usage_source.strip():
        raise SprintError("--usage-source cannot be empty when usage is recorded")
    for name, value, unit in definitions:
        if value is None:
            continue
        if value < 0:
            raise SprintError(f"Usage measurement {name} cannot be negative")
        measurements.append(
            {
                "name": name,
                "value": value,
                "unit": unit,
                "source": args.usage_source.strip(),
            }
        )
    values = {item["name"]: item["value"] for item in measurements}
    if all(name in values for name in ("inputTokens", "outputTokens", "totalTokens")):
        if values["inputTokens"] + values["outputTokens"] != values["totalTokens"]:
            raise SprintError("totalTokens must equal inputTokens plus outputTokens")
    return measurements


def command_session_complete(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    manifest, entry, record, summary, record_path, summary_path = load_session_bundle(
        workspace, require_session_identifier(args.session_id, "--session-id")
    )
    if record["status"] == "complete" or entry["counted"]:
        raise SprintError(
            f"Session {record['sessionId']} is already complete and counted once"
        )
    if record["packet"]["path"] is None:
        raise SprintError("Generate the participant packet before completing the session")
    now = utc_now()
    if args.consent_status:
        record["consent"]["status"] = args.consent_status
        record["consent"]["recordedAt"] = now
    if args.consent_scope is not None:
        record["consent"]["scope"] = args.consent_scope.strip()
    if args.consent_reference is not None:
        record["consent"]["reference"] = args.consent_reference.strip()
    if record["consent"]["status"] != "granted":
        raise SprintError("A counted completed session requires granted consent")
    if not record["consent"]["scope"].strip():
        raise SprintError("A counted completed session requires the consent scope")
    if not record["consent"]["reference"].strip():
        raise SprintError(
            "A counted completed session requires an opaque consent-record reference"
        )
    if args.redaction_status:
        record["redaction"]["status"] = args.redaction_status
        record["redaction"]["reviewedAt"] = now
    for value in args.removed_category:
        normalized = value.strip()
        if normalized and normalized not in record["redaction"]["removedCategories"]:
            record["redaction"]["removedCategories"].append(normalized)
    if record["redaction"]["status"] not in {"complete", "not-required"}:
        raise SprintError(
            "A completed session requires redaction status complete or not-required"
        )
    for value in args.limitation:
        normalized = value.strip()
        if normalized and normalized not in record["limitations"]:
            record["limitations"].append(normalized)
        if normalized and normalized not in summary["limitations"]:
            summary["limitations"].append(normalized)
    if args.protocol_fidelity is None:
        raise SprintError("Completing a session requires --protocol-fidelity")
    if not args.usable and not args.exclude_from_evidence:
        raise SprintError(
            "Completing a session requires either --usable or --exclude-from-evidence"
        )
    if summary.get("moderatorDeviations") and args.protocol_fidelity == "consistent":
        raise SprintError(
            "A session with moderator deviations cannot claim a consistent protocol; classify the deviation"
        )
    critical_scenarios = sorted(
        {value.strip() for value in args.critical_scenario if value.strip()}
    )
    exclusion_reason = args.exclusion_reason.strip()
    participant = record["participant"]
    if participant["fit"] == "unassessed":
        raise SprintError(
            "Classify participant fit as qualified or excluded before completing the session"
        )
    if not participant["fitRationale"].strip():
        raise SprintError("Completed participant fit requires a rationale")
    if args.usable:
        if participant["fit"] != "qualified":
            raise SprintError("Only a qualified participant session can be usable")
        if args.protocol_fidelity == "material-deviation":
            raise SprintError(
                "A materially deviated protocol cannot be marked usable; exclude it and explain why"
            )
        if not critical_scenarios:
            raise SprintError(
                "A usable session must name at least one covered critical scenario"
            )
        if exclusion_reason:
            raise SprintError("A usable session cannot have an exclusion reason")
    elif not exclusion_reason:
        raise SprintError(
            "--exclude-from-evidence requires a non-empty --exclusion-reason"
        )
    summary_errors = session_summary_errors(summary, record, require_complete=True)
    if summary_errors:
        raise SprintError(
            "Session summary is not completion-ready:\n"
            + "\n".join(f"- {item}" for item in summary_errors)
        )
    measurements = usage_measurements_from_args(args)
    if measurements:
        record["usage"] = {
            "measurementContext": "customer-session",
            "available": True,
            "measurements": measurements,
            "unavailableReason": "",
        }
    elif args.usage_unavailable_reason:
        record["usage"] = {
            "measurementContext": "customer-session",
            "available": False,
            "measurements": [],
            "unavailableReason": args.usage_unavailable_reason.strip(),
        }
    record["rawEvidence"] = copy.deepcopy(summary["sourceReferences"])
    record["evidenceQuality"] = {
        "attemptedAt": record["evidenceQuality"].get("attemptedAt") or now,
        "protocolFidelity": args.protocol_fidelity,
        "criticalScenariosCovered": critical_scenarios,
        "usable": bool(args.usable),
        "exclusionReason": exclusion_reason,
    }
    record["status"] = "complete"
    record["completedAt"] = now
    record["checkpoint"] = {
        "phase": "complete",
        "nextAction": "Use this session's structured summary in a separate synthesis packet.",
        "completedPhases": sorted(
            set(
                [
                    *record["checkpoint"]["completedPhases"],
                    "session-run",
                    "summary-completed",
                ]
            )
        ),
        "lastPersistedAt": now,
    }
    summary["status"] = "complete"
    summary["updatedAt"] = now
    entry["status"] = "complete"
    entry["counted"] = True
    entry["attempted"] = True
    entry["participantSegment"] = participant["segment"]
    entry["participantFit"] = participant["fit"]
    entry["protocolFidelity"] = args.protocol_fidelity
    entry["criticalScenariosCovered"] = critical_scenarios
    entry["usable"] = bool(args.usable)
    entry["exclusionReason"] = exclusion_reason
    entry["includeInSynthesis"] = bool(args.usable)
    entry["summarySha256"] = sha256_text(json_text(summary))
    entry["completedAt"] = now
    entry["updatedAt"] = now
    if args.protocol_fidelity != "consistent":
        add_fidelity_deviation(
            state,
            "11-customer-sessions",
            {
                "id": f"session-protocol-{record['sessionId']}",
                "type": (
                    "omission"
                    if args.protocol_fidelity == "material-deviation"
                    else "substitution"
                ),
                "canonicalMethod": "Run a consistent neutral one-to-one customer protocol",
                "selectedMethod": (
                    f"Session {record['sessionId']} completed with {args.protocol_fidelity.replace('-', ' ')}"
                ),
                "preservedPurpose": (
                    "The session remains traceable; its usability and limitations are assessed explicitly."
                ),
                "reason": (
                    exclusion_reason
                    or "The session record documents a protocol deviation."
                ),
                "impact": impact_record(
                    "The customer-session protocol was not followed consistently.",
                    "The deviation can introduce moderator or protocol effects and is retained in evidence quality.",
                    "Any decision must remain bounded to findings robust to the documented deviation.",
                ),
                "recordedAt": now,
            },
        )
    mark_synthesis_stale(manifest)
    sync_customer_testing_from_manifest(state, manifest)
    planned = state["customerTesting"]["sessionsPlanned"]
    counted = state["customerTesting"]["sessionsCompleted"]
    persist_customer_documents(
        workspace,
        state,
        manifest,
        record_path=record_path,
        record=record,
        summary_path=summary_path,
        summary=summary,
        timestamp=now,
    )
    render_workspace(workspace)
    print(f"Completed and counted session once: {record['sessionId']}")
    print(f"Customer sessions: {counted}/{planned}")


def command_session_reopen(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    manifest, entry, record, summary, record_path, summary_path = load_session_bundle(
        workspace, require_session_identifier(args.session_id, "--session-id")
    )
    if record["status"] not in {"complete", "blocked", "withdrawn"}:
        raise SprintError(
            f"Session status is {record['status']}; only complete, blocked, or withdrawn sessions can be reopened"
        )
    reason = args.reason.strip()
    if not reason:
        raise SprintError("--reason cannot be empty")
    now = utc_now()
    record["status"] = "reopened"
    record.pop("completedAt", None)
    record["reopenHistory"].append({"reason": reason, "reopenedAt": now})
    record["checkpoint"] = {
        "phase": "reopened",
        "nextAction": "Regenerate handoff.md and resume from the persisted structured state.",
        "completedPhases": record["checkpoint"]["completedPhases"],
        "lastPersistedAt": now,
    }
    summary["status"] = "draft"
    record["evidenceQuality"]["usable"] = False
    entry["status"] = "reopened"
    entry["counted"] = False
    entry["includeInSynthesis"] = False
    entry["usable"] = False
    entry["summarySha256"] = None
    entry.pop("completedAt", None)
    entry["updatedAt"] = now
    mark_synthesis_stale(manifest)
    sync_customer_testing_from_manifest(state, manifest)
    persist_customer_documents(
        workspace,
        state,
        manifest,
        record_path=record_path,
        record=record,
        summary_path=summary_path,
        summary=summary,
        timestamp=now,
    )
    render_workspace(workspace)
    print(f"Reopened session from persisted state: {record['sessionId']}")
    print("Regenerate its packet; no prior conversation replay is required")


def synthesis_summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    payload = summary_for_handoff(summary)
    payload.pop("createdAt", None)
    payload.pop("updatedAt", None)
    session_id = str(summary["sessionId"])
    for observation in payload["observations"]:
        observation["traceId"] = f"{session_id}/{observation['id']}"
    for inference in payload["inferences"]:
        inference["traceId"] = f"{session_id}/{inference['id']}"
    for question in payload["questionEvidence"]:
        question["traceId"] = f"{session_id}/{question['questionId']}"
    for quote in payload["quoteReferences"]:
        quote["traceId"] = f"{session_id}/{quote['id']}"
    return payload


def command_synthesis_packet(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    manifest = load_session_manifest(workspace)
    requested_ids = [
        require_session_identifier(value, "--session-id") for value in args.session_id
    ]
    if len(requested_ids) != len(set(requested_ids)):
        raise SprintError("Synthesis session IDs must be unique")
    if requested_ids:
        entries = [find_session_entry(manifest, value) for value in requested_ids]
    else:
        entries = [
            item
            for item in manifest["sessions"]
            if item["counted"] and item["usable"] and item["includeInSynthesis"]
        ]
    if not entries:
        raise SprintError("No completed, counted session summaries are available")
    for entry in entries:
        if (
            entry["status"] != "complete"
            or not entry["counted"]
            or not entry["usable"]
        ):
            raise SprintError(
                f"Session {entry['sessionId']} is not complete, qualified, and usable"
            )
    question_versions = {entry["questionsVersion"] for entry in entries}
    if len(question_versions) != 1:
        raise SprintError(
            "A synthesis packet cannot mix questions versions; generate one packet per version"
        )
    questions_version = next(iter(question_versions))
    catalog = next(
        (
            item
            for item in manifest["versionCatalog"]["questions"]
            if item["version"] == questions_version
        ),
        None,
    )
    if catalog is None:
        raise SprintError(f"Questions version is missing from the catalog: {questions_version}")
    scorecard = descriptor_text(workspace, catalog["scorecard"], "Synthesis scorecard")
    summary_blocks: list[str] = []
    summary_hashes: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda item: item["sessionId"]):
        summary_path = workspace_relative_file(
            workspace, entry["summaryPath"], "Synthesis summary"
        )
        summary = load_session_summary(summary_path)
        record_path = workspace_relative_file(
            workspace, entry["recordPath"], "Synthesis session record"
        )
        record = load_session_record(record_path)
        errors = session_summary_errors(summary, record, require_complete=True)
        if summary.get("status") != "complete":
            errors.append("Summary status is not complete")
        if errors:
            raise SprintError(
                f"Session {entry['sessionId']} is not synthesis-ready:\n"
                + "\n".join(f"- {item}" for item in errors)
            )
        payload = synthesis_summary_payload(summary)
        payload["traceability"] = {
            "sessionRecord": entry["recordPath"],
            "summaryRecord": entry["summaryPath"],
            "citationPrefix": entry["sessionId"],
        }
        summary_blocks.append(
            f"## Session {entry['sessionId']}\n\n"
            f"```json\n{json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)}\n```"
        )
        summary_hashes.append(
            {
                "sessionId": entry["sessionId"],
                "path": entry["summaryPath"],
                "sha256": sha256_bytes(summary_path.read_bytes()),
            }
        )
    session_ids = [item["sessionId"] for item in sorted(entries, key=lambda item: item["sessionId"])]
    packet = f"""# Fresh-chat synthesis packet

Use this packet as the complete input to a separate, fresh synthesis chat. It contains the shared scorecard and anonymized structured summaries only. Raw transcripts, recordings, notes, participant identity maps, prior participant chats, and unrelated sprint history are intentionally excluded.

Questions version: `{questions_version}`
Sessions: {', '.join(f'`{value}`' for value in session_ids)}

## Synthesis operating contract

1. Compare evidence against the unchanged scorecard. Do not infer prevalence from this directional sample.
2. Distinguish patterns, contradictions, outliers, limitations, and unanswered questions.
3. Every synthesized claim must cite one or more trace IDs in the form `SESSION-ID/OBSERVATION-ID` or `SESSION-ID/QUESTION-ID`.
4. Do not create a claim when no included summary supports it. Mark interpretation as `Inference`, not `Observed`.
5. Use source/quote pointer IDs for audit escalation; do not open raw evidence unless a human explicitly authorizes a separate audit pass.
6. Report prototype versions per session and flag version-driven differences.

## Shared scorecard

Source: `{catalog['scorecard']['path']}`
SHA-256: `{catalog['scorecard']['sha256']}`

<declared-input name="Shared scorecard">
{scorecard.rstrip()}
</declared-input>

## Structured session summaries

{chr(10).join(summary_blocks)}

## Required return format

- Claims, each with `claimId`, label, text, and one or more session/evidence trace IDs.
- Question-by-question findings.
- Patterns, contradictions, and outliers.
- Evidence strength bounded by the available sessions and their quality.
- Limitations, uncertainties, and evidence gaps.
- Prototype-version effects and recommended next action.
"""
    budget = manifest["contextBudget"]
    packet_status = budget_status(
        len(packet), budget["synthesisMaximum"], budget["warningPercent"]
    )
    packet_path = workspace / CUSTOMER_TESTING_DIR / "synthesis" / "synthesis-packet.md"
    now = utc_now()
    manifest["synthesis"] = {
        "status": "packet-generated",
        "packetPath": packet_path.relative_to(workspace).as_posix(),
        "generatedAt": now,
        "questionsVersion": questions_version,
        "sessionIds": session_ids,
        "summaryHashes": summary_hashes,
        "packetSha256": sha256_text(packet),
        "characters": len(packet),
        "budgetStatus": packet_status,
        "rawEvidenceIncluded": False,
    }
    persist_customer_documents(
        workspace,
        None,
        manifest,
        extra_texts={packet_path: packet},
        timestamp=now,
    )
    print(
        f"Wrote fresh-chat synthesis packet: {packet_path} "
        f"({len(packet)}/{budget['synthesisMaximum']} characters)"
    )
    if packet_status == "approaching-limit":
        print("Warning: synthesis packet is approaching its context budget")
    print("Raw prior transcripts included: no")
    print("Fresh chat required: yes")


def command_customer(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    existing_errors = validate_state(state)
    if existing_errors:
        raise SprintError(
            "Cannot update customer testing from an invalid workflow state: "
            + "; ".join(existing_errors)
        )
    if args.status not in CUSTOMER_STATUSES:
        raise SprintError(f"Invalid customer-testing status: {args.status}")
    planned = args.planned
    completed = args.completed
    invited = args.invited
    mode = state.get("executionMode")
    if mode != "live" and (
        (completed or 0) > 0
        or (invited or 0) > 0
        or args.status in {"in-progress", "complete", "partial"}
    ):
        raise SprintError(
            f"Execution mode {mode} cannot record live customer sessions or customer evidence"
        )
    if manifest_path(workspace).exists():
        manifest = load_session_manifest(workspace)
        canonical_completed = sum(
            item.get("counted") is True for item in manifest["sessions"]
        )
        if completed is None:
            completed = canonical_completed
        elif completed != canonical_completed:
            raise SprintError(
                "--completed is derived from the canonical session manifest; "
                f"found {canonical_completed} counted session(s), not {completed}. "
                "Use session-complete or session-reopen."
            )
        minimum_invited = len(manifest["sessions"])
        if invited is None:
            invited = max(
                int(state.get("customerTesting", {}).get("sessionsInvited", 0)),
                minimum_invited,
            )
        elif invited < minimum_invited:
            raise SprintError(
                "Invited sessions cannot be lower than the number of initialized session records"
            )
    else:
        if completed is None:
            completed = 0
        if invited is None:
            invited = int(
                state.get("customerTesting", {}).get("sessionsInvited", 0)
            )
    assert invited is not None
    assert completed is not None
    if planned < 0 or invited < 0 or completed < 0:
        raise SprintError("Session counts cannot be negative")
    if completed > invited:
        raise SprintError("Completed sessions cannot exceed invited sessions")
    target = args.target.strip()
    if planned and not target:
        raise SprintError("A planned customer session target must name the suitable audience")
    if mode != "live" and (
        completed > 0 or invited > 0 or planned > 0 or args.status != "not-planned"
    ):
        raise SprintError(
            f"Execution mode {mode} cannot record live customer sessions; it "
            "requires not-planned customer status and zero sessions"
        )
    target_rationale = (args.rationale or "").strip()
    if state.get("methodProfile") == "sprint-book" and mode == "live":
        step_record = state["fidelity"]["steps"]["11-customer-sessions"]
        step_record["deviations"] = [
            item
            for item in step_record.get("deviations", [])
            if item.get("id") != "customer-target"
        ]
        if planned != 5:
            if not target_rationale:
                raise SprintError(
                    "Changing the Sprint-book live target from five requires --rationale"
                )
            add_fidelity_deviation(
                state,
                "11-customer-sessions",
                {
                    "id": "customer-target",
                    "type": "compression" if planned < 5 else "substitution",
                    "canonicalMethod": "Five suitable one-to-one customer interviews",
                    "selectedMethod": f"{planned} planned suitable one-to-one customer interviews",
                    "preservedPurpose": "Observe suitable real customers against the agreed questions; breadth differs from the canonical five-session target.",
                    "reason": target_rationale,
                    "impact": impact_record(
                        "The Sprint-book live five-customer target is not being followed.",
                        "The session target changes the opportunity to observe recurring and contradictory behaviour; it does not create a statistical confidence score.",
                        "Any outcome must be bounded to the usable observed sample and explain why the altered target is sufficient for the proposed decision.",
                    ),
                    "recordedAt": utc_now(),
                },
            )
        else:
            target_rationale = (
                target_rationale
                or "The Sprint-book live profile defaults to five suitable one-to-one sessions."
            )
    elif planned and not target_rationale:
        target_rationale = (
            "Adaptive customer-session target selected for this challenge; record a more specific rationale before testing."
        )
    state["customerTesting"] = {
        "status": args.status,
        "target": target,
        "targetRationale": target_rationale,
        "sessionsPlanned": planned,
        "sessionsInvited": invited,
        "sessionsAttempted": int(
            state.get("customerTesting", {}).get("sessionsAttempted", 0)
        ),
        "sessionsCompleted": completed,
        "sessionsQualified": int(
            state.get("customerTesting", {}).get("sessionsQualified", 0)
        ),
        "sessionsExcluded": int(
            state.get("customerTesting", {}).get("sessionsExcluded", 0)
        ),
        "sessionsUsable": int(
            state.get("customerTesting", {}).get("sessionsUsable", 0)
        ),
    }
    if manifest_path(workspace).exists():
        sync_customer_testing_from_manifest(state, manifest)
        state["customerTesting"]["status"] = args.status
    if args.status in {"recruiting", "scheduled", "in-progress", "blocked"}:
        state["status"] = "waiting-for-customers" if args.status == "blocked" else state["status"]
    transition_errors = customer_testing_errors(state)
    transition_errors.extend(customer_testing_record_errors(workspace, state))
    if transition_errors:
        raise SprintError("; ".join(transition_errors))
    state_errors = validate_state(state)
    if state_errors:
        raise SprintError(
            "Customer update would create an invalid workflow state: "
            + "; ".join(state_errors)
        )
    now = utc_now()
    test_plan_path = workspace / "artifact-data" / f"{TEST_PLAN_ID}.json"
    if test_plan_path.is_file():
        test_plan = load_artifact_data(test_plan_path)
        recruitment_plan = test_plan.get("recruitmentPlan")
        if isinstance(recruitment_plan, dict) and planned > 0:
            recruitment_plan["targetDefinition"].update(
                {
                    "audience": target,
                    "targetSessions": planned,
                    "rationale": target_rationale,
                }
            )
            recruitment_plan["tracking"]["lastActivityAt"] = now
            test_plan["updatedAt"] = now
            save_artifact_data(test_plan_path, test_plan)
    save_state(workspace, state, timestamp=now)
    render_workspace(workspace)
    print(f"Updated customer testing: {args.status}, {completed}/{planned} sessions")


def command_recruitment_status(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    data_path, data, plan = load_recruitment_plan_artifact(workspace)
    if args.status not in RECRUITMENT_STATUSES:
        raise SprintError(f"Invalid recruitment status: {args.status}")
    owner = args.owner.strip()
    next_action = args.next_action.strip()
    if not owner or not next_action:
        raise SprintError("Recruitment owner and next action cannot be blank")
    try:
        datetime.fromisoformat(args.deadline).date()
    except ValueError as error:
        raise SprintError("--deadline must use YYYY-MM-DD") from error
    tracking = plan["tracking"]
    tracking.update(
        {
            "owner": owner,
            "status": args.status,
            "nextAction": next_action,
            "deadline": args.deadline,
            "lastActivityAt": utc_now(),
        }
    )
    for milestone in args.complete_milestone:
        tracking["milestones"][RECRUITMENT_MILESTONES[milestone]] = "complete"
        if milestone == "screener-approved":
            plan["screener"]["status"] = "approved"
    for argument_name, field in (
        ("candidates_screened", "candidatesScreened"),
        ("sessions_booked", "sessionsBooked"),
        ("backups_booked", "backupsBooked"),
    ):
        value = getattr(args, argument_name)
        if value is not None:
            if value < 0:
                raise SprintError(f"--{argument_name.replace('_', '-')} cannot be negative")
            tracking[field] = value
    if args.status == "complete" and any(
        value != "complete" for value in tracking["milestones"].values()
    ):
        raise SprintError(
            "Recruitment cannot be complete while a milestone remains incomplete"
        )
    now = utc_now()
    data["updatedAt"] = now
    errors = recruitment_plan_errors(plan, require_ready=False, state=state)
    if errors:
        raise SprintError("; ".join(errors))
    save_artifact_data(data_path, data)
    save_state(workspace, state, timestamp=now)
    render_workspace(workspace)
    stalled, smallest_action = recruitment_stall(plan)
    print(
        f"Updated recruitment: {args.status}, owner {owner}, "
        f"{sum(value == 'complete' for value in tracking['milestones'].values())}/7 milestones"
    )
    if stalled:
        print(f"Recruitment is stalled or due. Next smallest action: {smallest_action}")


def command_next_action(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    existing_errors = validate_state(state)
    if existing_errors:
        raise SprintError(
            "Cannot update the next action from an invalid workflow state: "
            + "; ".join(existing_errors)
        )
    if state.get("status") == "complete":
        raise SprintError(
            "A Gate 5 terminal state cannot be reopened or rewritten with "
            "next-action; start a new workspace for further work"
        )
    if args.status == "complete":
        raise SprintError(
            "Workspace completion is a terminal transition owned by Gate 5; "
            "use complete-step 13-outcome and then gate --gate gate-5"
        )
    title = args.title.strip()
    body = args.body.strip()
    human_input = args.human_input.strip()
    if not title or not body or not human_input:
        raise SprintError("Next action fields cannot be blank")
    state["nextAction"] = {
        "title": title,
        "body": body,
        "humanInput": human_input,
    }
    if args.status:
        if args.status not in WORKSPACE_STATUSES:
            raise SprintError(f"Invalid workspace status: {args.status}")
        state["status"] = args.status
    transition_errors = validate_state(state)
    if transition_errors:
        raise SprintError(
            "Next-action update would create an invalid workflow state: "
            + "; ".join(transition_errors)
        )
    save_state(workspace, state)
    render_workspace(workspace)
    print("Updated the next action")


def print_guidance_list(title: str, values: list[str]) -> None:
    print(f"{title}:")
    for value in values:
        print(f"- {value}")


def command_guidance(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    guidance = guidance_for_state(state, args.step)
    if args.json:
        exported = copy.deepcopy(guidance)
        if args.action:
            exported["requestedAction"] = args.action
        print(json.dumps(exported, indent=2, ensure_ascii=False, sort_keys=True))
        return

    print(f"Current step: {guidance['step']} — {guidance['title']}")
    print(f"Why it matters: {guidance['whyItMatters']}")
    print(f"Canonical purpose: {guidance['purpose']}")
    print(
        f"Method: {guidance['selectedMethod']} "
        f"({guidance['suggestedTimeboxMinutes']} minutes suggested)"
    )
    print(f"Why this method: {guidance['selectedMethodRationale']}")
    print(f"Need from you: {guidance['humanAction']}")
    print(f"AI can: {'; '.join(guidance['aiRole'])}")
    print(f"Done when: {'; '.join(guidance['definitionOfDone'])}")
    if not args.action:
        print(
            "More: "
            + ", ".join(
                f"{action} ({item['label']})"
                for action, item in guidance["availableActions"].items()
            )
        )
        return

    action = args.action
    print(f"\n{guidance['availableActions'][action]['label']}")
    if action == "show-example":
        print_guidance_list("Examples", guidance["examples"])
    elif action == "explain-why":
        print(f"Why: {guidance['whyItMatters']}")
        print(f"Canonical purpose: {guidance['purpose']}")
        print_guidance_list(
            "If partial, compressed, or skipped", guidance["limitations"]
        )
    elif action == "show-canonical-method":
        for profile in ("sprint-book", "adaptive-design-sprint"):
            print(
                f"- {profile}: {guidance['methods'][profile]} "
                f"({guidance['timeboxMinutes'][profile]} minutes)"
            )
        print(f"Selected for this run: {guidance['selectedMethod']}")
        print(f"Selection rationale: {guidance['selectedMethodRationale']}")
        if guidance["recordedDeviations"]:
            print("Recorded fidelity impacts:")
            for deviation in guidance["recordedDeviations"]:
                impact = deviation.get("impact", {})
                print(
                    f"- {deviation.get('type')}: {impact.get('methodFidelity')} "
                    f"Evidence: {impact.get('evidence')}"
                )
    elif action == "show-checklist":
        print_guidance_list("Dependencies", guidance["dependencies"])
        print_guidance_list("What good looks like", guidance["whatGoodLooksLike"])
        print_guidance_list("Definition of done", guidance["definitionOfDone"])
    elif action == "compare-substitutes":
        for item in guidance["substitutes"]:
            print(f"- {item['name']}: {item['useWhen']}")
            print(f"  Preserves: {item['preserves']}")
            print(f"  Method impact: {item['methodFidelityImpact']}")
            print(f"  Evidence impact: {item['evidenceImpact']}")
    elif action == "i-am-blocked":
        print_guidance_list("Common blockers", guidance["failureModes"])
        first = guidance["substitutes"][0]
        print("Smallest approved workaround:")
        print(f"- {first['name']}: {first['useWhen']}")
        print(f"  Preserve: {first['preserves']}")
    elif action == "pause":
        print(
            "Record the current result and next action, then use `next-action "
            "--status paused`; do not mark the step or a human gate complete."
        )
    print("Deeper help:")
    for item in guidance["deeperHelp"]:
        print(f"- {item['label']}: {item['reference']}")


def memo_section_errors(text: str, required_outputs: list[str]) -> list[str]:
    matches = list(
        re.finditer(r"^##\s+(?:\d+\.\s*)?(.+?)\s*$", text, re.MULTILINE)
    )
    headings = [match.group(1).strip().rstrip(":") for match in matches]
    errors = []
    for required in required_outputs:
        matching_indexes = [
            index
            for index, item in enumerate(headings)
            if item.casefold() == required.casefold()
        ]
        count = len(matching_indexes)
        if count == 0:
            errors.append(f"result memo is missing required section {required!r}")
        elif count > 1:
            errors.append(f"result memo duplicates required section {required!r}")
        else:
            match_index = matching_indexes[0]
            body_start = matches[match_index].end()
            body_end = (
                matches[match_index + 1].start()
                if match_index + 1 < len(matches)
                else len(text)
            )
            if not text[body_start:body_end].strip():
                errors.append(f"result memo section {required!r} is empty")
    return errors


def assignment_by_id(
    manifest: dict[str, Any], assignment_id: str
) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in manifest.get("assignments", [])
            if isinstance(item, dict) and item.get("id") == assignment_id
        ),
        None,
    )


def assignment_manifest_errors(
    workspace: Path, manifest: dict[str, Any], state: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    assignments = manifest.get("assignments", [])
    if not isinstance(assignments, list):
        return ["assignments must be a list"]
    ids: dict[str, int] = {}
    packet_paths: dict[str, str] = {}
    result_paths: dict[str, str] = {}
    result_digests: dict[str, str] = {}
    step_roles: dict[tuple[str, str], str] = {}
    independent_runs: dict[tuple[str, str], str] = {}
    completed_steps = set(state.get("completedSteps", []))

    for index, assignment in enumerate(assignments):
        if not isinstance(assignment, dict):
            continue
        assignment_id = str(assignment.get("id", f"index-{index}"))
        step = str(assignment.get("step", ""))
        role = str(assignment.get("role", ""))
        ids[assignment_id] = ids.get(assignment_id, 0) + 1
        key = (step, role)
        if assignment.get("status") != "rejected":
            if key in step_roles:
                errors.append(
                    f"duplicate assignment for {step}/{role}: "
                    f"{step_roles[key]} and {assignment_id}"
                )
            else:
                step_roles[key] = assignment_id
        expected_independence = step in INDEPENDENT_ASSIGNMENT_STEPS
        independence = assignment.get("independence", {})
        if independence.get("required") is not expected_independence:
            errors.append(
                f"assignment {assignment_id} has the wrong independence requirement for {step}"
            )
        if expected_independence:
            if not independence.get("isolated") or independence.get("group") != step:
                errors.append(
                    f"assignment {assignment_id} must be isolated in independence group {step}"
                )
            run_id = str(assignment.get("assignee", {}).get("runId", ""))
            run_key = (step, run_id)
            if run_key in independent_runs:
                errors.append(
                    f"independent assignments {independent_runs[run_key]} and "
                    f"{assignment_id} reuse run {run_id!r}"
                )
            else:
                independent_runs[run_key] = assignment_id
        if assignment.get("requiredOutputs") != list(REQUIRED_RESULT_SECTIONS):
            errors.append(
                f"assignment {assignment_id} does not declare the canonical required outputs"
            )

        packet = assignment.get("packet", {})
        packet_path = str(packet.get("path", ""))
        if packet_path in packet_paths:
            errors.append(
                f"duplicate role packet path {packet_path!r} for "
                f"{packet_paths[packet_path]} and {assignment_id}"
            )
        else:
            packet_paths[packet_path] = assignment_id
        try:
            packet_file, packet_relative = resolved_workspace_file(
                workspace, packet_path, below="working"
            )
            if packet_relative != packet_path:
                errors.append(
                    f"assignment {assignment_id} packet path is not normalized: {packet_path}"
                )
            elif file_digest(packet_file) != packet.get("digest"):
                errors.append(
                    f"assignment {assignment_id} role packet is stale or was modified"
                )
        except SprintError as error:
            errors.append(f"assignment {assignment_id}: {error}")

        for snapshot in packet.get("inputs", []):
            if not isinstance(snapshot, dict):
                continue
            input_path = str(snapshot.get("path", ""))
            if expected_independence and (
                input_path == "working" or input_path.startswith("working/")
            ):
                errors.append(
                    f"independent assignment {assignment_id} includes cross-role working input {input_path}"
                )
            if step in completed_steps or assignment.get("status") == "rejected":
                continue
            try:
                input_file, normalized = resolved_workspace_file(workspace, input_path)
                if normalized != input_path:
                    errors.append(
                        f"assignment {assignment_id} input path is not normalized: {input_path}"
                    )
                elif file_digest(input_file) != snapshot.get("digest"):
                    errors.append(
                        f"assignment {assignment_id} is stale because input {input_path} changed"
                    )
            except SprintError as error:
                errors.append(f"assignment {assignment_id}: {error}")

        result = assignment.get("resultMemo")
        if isinstance(result, dict):
            result_path = str(result.get("path", ""))
            if result_path == packet_path:
                errors.append(
                    f"assignment {assignment_id} must keep its role packet and result memo separate"
                )
            if result_path in result_paths:
                errors.append(
                    f"duplicate result memo path {result_path!r} for "
                    f"{result_paths[result_path]} and {assignment_id}"
                )
            else:
                result_paths[result_path] = assignment_id
            result_digest = str(result.get("digest", ""))
            if result_digest in result_digests:
                errors.append(
                    f"duplicate result memo digest for {result_digests[result_digest]} "
                    f"and {assignment_id}"
                )
            else:
                result_digests[result_digest] = assignment_id
            if result.get("sourceAssignmentId") != assignment_id:
                errors.append(
                    f"result memo for {assignment_id} names a different source assignment"
                )
            included = result.get("includedAssignmentIds", [])
            if expected_independence and included:
                errors.append(
                    f"independent assignment {assignment_id} includes cross-role results: "
                    + ", ".join(str(item) for item in included)
                )
            try:
                result_file, normalized = resolved_workspace_file(
                    workspace, result_path, below="working"
                )
                if normalized != result_path:
                    errors.append(
                        f"assignment {assignment_id} result path is not normalized: {result_path}"
                    )
                else:
                    memo_text = result_file.read_text(encoding="utf-8")
                    if file_digest(result_file) != result_digest:
                        errors.append(
                            f"assignment {assignment_id} result memo is stale or was modified"
                        )
                    errors.extend(
                        f"assignment {assignment_id}: {item}"
                        for item in memo_section_errors(
                            memo_text, list(assignment.get("requiredOutputs", []))
                        )
                    )
                    if expected_independence:
                        for peer in assignments:
                            if not isinstance(peer, dict) or peer is assignment:
                                continue
                            if peer.get("step") != step:
                                continue
                            peer_tokens = [
                                str(peer.get("id", "")),
                                str(peer.get("packet", {}).get("path", "")),
                            ]
                            if isinstance(peer.get("resultMemo"), dict):
                                peer_tokens.append(str(peer["resultMemo"].get("path", "")))
                            if any(token and token in memo_text for token in peer_tokens):
                                errors.append(
                                    f"independent assignment {assignment_id} result memo "
                                    f"references peer assignment {peer.get('id')}"
                                )
                                break
            except (OSError, UnicodeError, SprintError) as error:
                errors.append(f"assignment {assignment_id}: {error}")
            if str(result.get("returnedAt", "")) < str(assignment.get("assignedAt", "")):
                errors.append(
                    f"assignment {assignment_id} result predates its assignment"
                )

    for assignment_id, count in ids.items():
        if count > 1:
            errors.append(f"duplicate assignment id {assignment_id!r}")
    known_ids = set(ids)
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        result = assignment.get("resultMemo")
        if not isinstance(result, dict):
            continue
        included_ids = set(result.get("includedAssignmentIds", []))
        packet_input_paths = {
            str(item.get("path"))
            for item in assignment.get("packet", {}).get("inputs", [])
            if isinstance(item, dict)
        }
        inferred_ids = {
            owner
            for path, owner in result_paths.items()
            if path in packet_input_paths and owner != assignment.get("id")
        }
        if not inferred_ids.issubset(included_ids):
            errors.append(
                f"assignment {assignment.get('id')} does not declare included result assignments: "
                + ", ".join(sorted(inferred_ids - included_ids))
            )
        for included_id in included_ids:
            if included_id not in known_ids:
                errors.append(
                    f"assignment {assignment.get('id')} includes unknown assignment {included_id}"
                )
            if included_id == assignment.get("id"):
                errors.append(
                    f"assignment {assignment.get('id')} cannot include itself as a peer result"
                )
    return errors


def required_assignment_errors(
    manifest: dict[str, Any], step_id: str
) -> list[str]:
    errors = []
    assignments = [
        item
        for item in manifest.get("assignments", [])
        if isinstance(item, dict)
        and item.get("step") == step_id
        and item.get("status") != "rejected"
    ]
    for role in REQUIRED_ROLES_BY_STEP.get(step_id, ()):
        matches = [item for item in assignments if item.get("role") == role]
        if not matches:
            errors.append(f"missing required {role} assignment for {step_id}")
            continue
        if len(matches) > 1:
            errors.append(f"duplicate required {role} assignments for {step_id}")
            continue
        status = matches[0].get("status")
        if status not in {"returned", "accepted"}:
            errors.append(
                f"required {role} assignment for {step_id} has status {status}; "
                "a validated returned result memo is required"
            )
    return errors


def command_role_packet(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    manifest = load_assignment_manifest(workspace)
    roles = load_role_contracts()
    if args.role not in roles:
        raise SprintError(f"Unknown role: {args.role}")
    task = args.task.strip()
    assignee = args.assignee.strip()
    run_id = args.run_id.strip()
    if not task or not assignee or not run_id:
        raise SprintError("Role task, assignee label, and run ID cannot be empty")
    step = str(state["currentStep"])
    assignment_id = (
        args.assignment_id.strip()
        if args.assignment_id
        else f"{step}-{args.role}-{slugify(run_id)}"
    )
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", assignment_id):
        raise SprintError(
            "Assignment ID must contain lowercase letters, numbers, and single hyphens"
        )
    existing = manifest.get("assignments", [])
    if assignment_by_id(manifest, assignment_id):
        raise SprintError(f"Duplicate assignment ID: {assignment_id}")
    if any(
        item.get("step") == step
        and item.get("role") == args.role
        and item.get("status") != "rejected"
        for item in existing
        if isinstance(item, dict)
    ):
        raise SprintError(f"Duplicate assignment for {step}/{args.role}")
    independent = step in INDEPENDENT_ASSIGNMENT_STEPS
    if independent and any(
        item.get("step") == step and isinstance(item.get("resultMemo"), dict)
        for item in existing
        if isinstance(item, dict)
    ):
        raise SprintError(
            f"All independent {step} role packets must be created before any result returns"
        )
    if independent and any(
        item.get("step") == step
        and item.get("assignee", {}).get("runId") == run_id
        for item in existing
        if isinstance(item, dict)
    ):
        raise SprintError(
            f"Independent assignments in {step} must use distinct run IDs"
        )

    output, output_relative = resolved_workspace_file(
        workspace, args.output, below="working"
    )
    if output.exists():
        raise SprintError(f"Refusing to overwrite an existing role packet: {output_relative}")
    if any(
        item.get("packet", {}).get("path") == output_relative
        for item in existing
        if isinstance(item, dict)
    ):
        raise SprintError(f"Duplicate role packet path: {output_relative}")
    input_snapshots = []
    input_labels = []
    for value in args.input:
        candidate, relative = resolved_workspace_file(workspace, value)
        if not candidate.is_file():
            raise SprintError(f"Role input is not a file: {value}")
        if independent and (relative == "working" or relative.startswith("working/")):
            raise SprintError(
                f"Independent role packets cannot include cross-role working input: {relative}"
            )
        input_snapshots.append({"path": relative, "digest": file_digest(candidate)})
        input_labels.append(relative)

    contract = roles[args.role]
    may = "\n".join(f"- {item}" for item in contract["may"])
    must_not = "\n".join(f"- {item}" for item in contract["mustNot"])
    permitted = (
        "\n".join(f"- {item}" for item in input_labels)
        or "- No files; use only the task context"
    )
    fidelity_step = state["fidelity"]["steps"][step]
    required_headings = "\n".join(
        f"## {item}" for item in REQUIRED_RESULT_SECTIONS
    )
    now = utc_now()
    packet = f"""# Bounded specialist assignment

Assignment ID: `{assignment_id}`
Packet version: {ROLE_PACKET_VERSION}
Assignee: {assignee}
Run ID: `{run_id}`
Role: {contract['displayName']} (`{args.role}`)
Sprint: {state['title']}
Method profile: {state['methodProfile']}
Execution mode: {state['executionMode']}
Current step: {step} — {step_name(step)}
Canonical purpose: {fidelity_step['canonicalPurpose']}
Selected method: {fidelity_step['selectedMethod']}
Independence: {'isolated; do not consume peer packets or results' if independent else 'bounded; declared inputs only'}

## Mission

{contract['mission']}

## Permitted inputs

{permitted}

Do not read other sprint files unless the Sprint Orchestrator issues a new assignment.

## Bounded task

{task}

## May

{may}

## Must not

{must_not}
- Edit `index.html`, `sprint-state.json`, `assignment-manifest.json`, canonical files in `artifact-data/`, or generated files in `artifacts/`
- Continue beyond the bounded task after returning the deliverable

## Required return

Deliverable: {contract['deliverable']}

Return one separate result memo with each heading exactly once:

{required_headings}
"""
    assignment = {
        "id": assignment_id,
        "step": step,
        "role": args.role,
        "objective": task,
        "assignee": {"label": assignee, "runId": run_id},
        "packet": {
            "path": output_relative,
            "digest": digest_bytes(packet.encode("utf-8")),
            "version": ROLE_PACKET_VERSION,
            "createdAt": now,
            "inputs": input_snapshots,
        },
        "requiredOutputs": list(REQUIRED_RESULT_SECTIONS),
        "independence": {
            "required": independent,
            "isolated": independent,
            "group": step if independent else "",
        },
        "status": "assigned",
        "assignedAt": now,
        "updatedAt": now,
    }
    manifest["assignments"].append(assignment)
    manifest["updatedAt"] = now
    require_valid_schema(
        manifest, "assignment-manifest", assignment_manifest_path(workspace)
    )
    write_texts_atomically(
        {
            output: packet,
            assignment_manifest_path(workspace): json_text(manifest),
        }
    )
    render_workspace(workspace)
    print(f"Wrote role packet and registered assignment {assignment_id}: {output}")


def command_role_result(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    manifest = load_assignment_manifest(workspace)
    assignment = assignment_by_id(manifest, args.assignment)
    if assignment is None:
        raise SprintError(f"Unknown assignment: {args.assignment}")
    if assignment.get("status") not in {"assigned", "in-progress"}:
        raise SprintError(
            f"Assignment {args.assignment} cannot return from status {assignment.get('status')}"
        )
    memo_path, memo_relative = resolved_workspace_file(
        workspace, args.memo, below="working"
    )
    if not memo_path.is_file():
        raise SprintError(f"Result memo does not exist: {memo_relative}")
    if memo_relative == assignment.get("packet", {}).get("path"):
        raise SprintError("The result memo must be separate from the immutable role packet")
    if any(
        item.get("resultMemo", {}).get("path") == memo_relative
        for item in manifest.get("assignments", [])
        if isinstance(item, dict) and isinstance(item.get("resultMemo"), dict)
    ):
        raise SprintError(f"Duplicate result memo path: {memo_relative}")
    memo_text = memo_path.read_text(encoding="utf-8")
    section_errors = memo_section_errors(
        memo_text, list(assignment.get("requiredOutputs", []))
    )
    if section_errors:
        raise SprintError("Invalid result memo: " + "; ".join(section_errors))
    packet_input_paths = {
        str(item.get("path"))
        for item in assignment.get("packet", {}).get("inputs", [])
        if isinstance(item, dict)
    }
    inferred_included = {
        str(item.get("id"))
        for item in manifest.get("assignments", [])
        if isinstance(item, dict)
        and item.get("id") != args.assignment
        and isinstance(item.get("resultMemo"), dict)
        and item["resultMemo"].get("path") in packet_input_paths
    }
    included = sorted(set(args.include_assignment) | inferred_included)
    for included_id in included:
        if included_id == args.assignment:
            raise SprintError("A result memo cannot include its own assignment as a peer")
        if assignment_by_id(manifest, included_id) is None:
            raise SprintError(f"Unknown included assignment: {included_id}")
    if assignment.get("independence", {}).get("required"):
        missing_packets = sorted(
            set(REQUIRED_ROLES_BY_STEP.get(str(assignment.get("step")), ()))
            - {
                str(item.get("role"))
                for item in manifest.get("assignments", [])
                if isinstance(item, dict)
                and item.get("step") == assignment.get("step")
                and item.get("status") != "rejected"
            }
        )
        if missing_packets:
            raise SprintError(
                "All independent role packets must exist before a result returns; missing "
                + ", ".join(missing_packets)
            )
        if included:
            raise SprintError(
                "Independent result memos cannot include cross-role assignments"
            )
    now = utc_now()
    assignment["resultMemo"] = {
        "path": memo_relative,
        "digest": file_digest(memo_path),
        "sourceAssignmentId": args.assignment,
        "includedAssignmentIds": included,
        "returnedAt": now,
    }
    assignment["status"] = "returned"
    assignment["updatedAt"] = now
    manifest["updatedAt"] = now
    errors = assignment_manifest_errors(workspace, manifest, state)
    if errors:
        raise SprintError(
            "Returned result violates assignment provenance:\n"
            + "\n".join(f"- {item}" for item in errors)
        )
    save_assignment_manifest(workspace, manifest, timestamp=now)
    render_workspace(workspace)
    print(f"Registered result memo for assignment {args.assignment}")


def command_assignment_status(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    if args.status == "rejected":
        state = load_state(workspace)
        manifest = load_assignment_manifest(workspace)
    else:
        state, _specs, _artifacts = load_workspace_documents(workspace)
        manifest = load_assignment_manifest(workspace)
    assignment = assignment_by_id(manifest, args.assignment)
    if assignment is None:
        raise SprintError(f"Unknown assignment: {args.assignment}")
    current = str(assignment.get("status"))
    target = args.status
    if target not in ASSIGNMENT_TRANSITIONS.get(current, set()):
        raise SprintError(
            f"Assignment status cannot move from {current} to {target}"
        )
    now = utc_now()
    if target == "in-progress":
        assignment["startedAt"] = now
    if target in {"accepted", "rejected"}:
        note = (args.note or "").strip()
        if not note:
            raise SprintError(f"Changing an assignment to {target} requires --note")
        assignment["reviewedAt"] = now
        assignment["reviewNote"] = note
    assignment["status"] = target
    assignment["updatedAt"] = now
    manifest_errors = assignment_manifest_errors(workspace, manifest, state)
    tolerated_stale_errors = (
        target == "rejected"
        and manifest_errors
        and all("is stale because input" in item for item in manifest_errors)
    )
    if manifest_errors and not tolerated_stale_errors:
        raise SprintError(
            "Assignment lifecycle update would leave invalid provenance:\n"
            + "\n".join(f"- {item}" for item in manifest_errors)
        )
    save_assignment_manifest(workspace, manifest, timestamp=now)
    if tolerated_stale_errors:
        print(
            "Warning: other stale assignments must also be rejected or replaced before rendering:",
            file=sys.stderr,
        )
        for error in manifest_errors:
            print(f"- {error}", file=sys.stderr)
        print(f"Updated assignment {args.assignment} to {target}")
        return
    render_workspace(workspace)
    print(f"Updated assignment {args.assignment} to {target}")


def fidelity_errors(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    fidelity = state.get("fidelity")
    if not isinstance(fidelity, dict):
        return ["fidelity must be an object"]
    if fidelity.get("schemaVersion") != FIDELITY_SCHEMA_VERSION:
        errors.append(
            f"Unsupported fidelity schema: {fidelity.get('schemaVersion')}"
        )
    contract = load_method_contract()
    method_profile = state.get("methodProfile")
    if method_profile in METHOD_PROFILES:
        profile_spec = contract["methodProfiles"][method_profile]
        if fidelity.get("teamModel") != profile_spec["teamModel"]:
            errors.append("fidelity.teamModel must match the selected method profile")
    principles = fidelity.get("nonNegotiablePrinciples")
    expected_principles = {
        item["id"]: item["statement"]
        for item in contract["nonNegotiablePrinciples"]
    }
    actual_principles = (
        {item.get("id") for item in principles if isinstance(item, dict)}
        if isinstance(principles, list)
        else set()
    )
    if actual_principles != set(expected_principles):
        errors.append(
            "fidelity.nonNegotiablePrinciples must contain every required learning principle"
        )
    elif isinstance(principles, list):
        for item in principles:
            if not isinstance(item, dict):
                continue
            principle_id = item.get("id")
            if (
                item.get("statement") != expected_principles[principle_id]
                or item.get("requirement") != "non-negotiable"
            ):
                errors.append(
                    f"Non-negotiable principle {principle_id} cannot be weakened or relabelled"
                )
    records = fidelity.get("steps")
    if not isinstance(records, dict) or set(records) != set(STEP_INDEX):
        errors.append("fidelity.steps must contain a record for every workflow step")
        return errors
    for step_id in STEP_INDEX:
        record = records.get(step_id)
        if not isinstance(record, dict):
            errors.append(f"Fidelity record {step_id} must be an object")
            continue
        for key in ("canonicalPurpose", "defaultMethod", "selectedMethod"):
            if not str(record.get(key, "")).strip():
                errors.append(f"Fidelity record {step_id} requires {key}")
        if method_profile in METHOD_PROFILES:
            method_key = (
                "bookDefaultMethod"
                if method_profile == "sprint-book"
                else "adaptiveDefaultMethod"
            )
            method_spec = contract["steps"][step_id]
            if record.get("canonicalPurpose") != method_spec["canonicalPurpose"]:
                errors.append(
                    f"Fidelity record {step_id} cannot change its canonical purpose"
                )
            if record.get("defaultMethod") != method_spec[method_key]:
                errors.append(
                    f"Fidelity record {step_id} default method does not match {method_profile}"
                )
        participants = record.get("participants")
        if not isinstance(participants, dict):
            errors.append(f"Fidelity record {step_id} requires participants")
        else:
            for kind in ("human", "ai"):
                values = participants.get(kind)
                if not isinstance(values, list):
                    errors.append(
                        f"Fidelity record {step_id} participants.{kind} must be a list"
                    )
        timebox = record.get("timebox")
        suggested = None
        actual = None
        if not isinstance(timebox, dict):
            errors.append(f"Fidelity record {step_id} requires a timebox")
        else:
            suggested = timebox.get("suggestedMinutes")
            actual = timebox.get("actualMinutes")
            if not isinstance(suggested, int) or suggested < 0:
                errors.append(
                    f"Fidelity record {step_id} suggestedMinutes must be a non-negative integer"
                )
            elif (
                method_profile in METHOD_PROFILES
                and suggested
                != contract["steps"][step_id]["suggestedTimeboxMinutes"][
                    method_profile
                ]
            ):
                errors.append(
                    f"Fidelity record {step_id} suggestedMinutes must match the selected profile"
                )
            if actual is not None and (
                not isinstance(actual, int) or isinstance(actual, bool) or actual < 0
            ):
                errors.append(
                    f"Fidelity record {step_id} actualMinutes must be null or a non-negative integer"
                )
        deviations = record.get("deviations")
        if not isinstance(deviations, list):
            errors.append(f"Fidelity record {step_id} deviations must be a list")
            deviations = []
        for index, deviation in enumerate(deviations, 1):
            prefix = f"Fidelity deviation {step_id}#{index}"
            if not isinstance(deviation, dict):
                errors.append(f"{prefix} must be an object")
                continue
            if deviation.get("type") not in DEVIATION_TYPES:
                errors.append(f"{prefix} has invalid type: {deviation.get('type')}")
            for key in (
                "canonicalMethod",
                "selectedMethod",
                "preservedPurpose",
                "reason",
            ):
                if not str(deviation.get(key, "")).strip():
                    errors.append(f"{prefix} requires {key}")
            impact = deviation.get("impact")
            if not isinstance(impact, dict):
                errors.append(f"{prefix} requires an impact object")
            else:
                for key in ("methodFidelity", "evidence", "decisionReadiness"):
                    if not str(impact.get(key, "")).strip():
                        errors.append(f"{prefix} impact requires {key}")
        if method_profile == "sprint-book":
            required_substitutions = contract["steps"][step_id].get(
                "bookSubstitutions", []
            )
            deviations_by_id = {
                item.get("id"): item
                for item in deviations
                if isinstance(item, dict) and item.get("id")
            }
            for index, substitution in enumerate(required_substitutions, 1):
                deviation_id = f"default-book-substitution-{index}"
                recorded = deviations_by_id.get(deviation_id)
                if not recorded:
                    errors.append(
                        f"Fidelity record {step_id} is missing required one-human-plus-AI substitution {deviation_id}"
                    )
                    continue
                expected = {
                    "type": "substitution",
                    "canonicalMethod": substitution["canonicalMethod"],
                    "selectedMethod": substitution["selectedMethod"],
                    "preservedPurpose": substitution["preservedPurpose"],
                    "reason": substitution["reason"],
                    "impact": substitution["impact"],
                }
                if any(recorded.get(key) != value for key, value in expected.items()):
                    errors.append(
                        f"Fidelity record {step_id} cannot weaken required substitution {deviation_id}"
                    )
        selected_differs = record.get("selectedMethod") != record.get("defaultMethod")
        if selected_differs and not deviations:
            errors.append(
                f"Fidelity record {step_id} changes the default method without a documented deviation"
            )
        if (
            isinstance(suggested, int)
            and isinstance(actual, int)
            and actual < suggested
            and not any(
                item.get("type") == "compression"
                for item in deviations
                if isinstance(item, dict)
            )
        ):
            errors.append(
                f"Fidelity record {step_id} has a compressed actual timebox without a compression deviation"
            )
        if step_id in state.get("skippedSteps", []) and not any(
            item.get("type") in {"skip", "omission"}
            for item in deviations
            if isinstance(item, dict)
        ):
            errors.append(
                f"Skipped step {step_id} requires a fidelity deviation with reason and impacts"
            )
    summary = fidelity.get("summary", {})
    if not isinstance(summary, dict) or summary.get("assessment") not in FIDELITY_ASSESSMENTS:
        errors.append("fidelity.summary has an invalid assessment")
    return errors


def route_history_errors(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    history = state.get("routeHistory", [])
    if not isinstance(history, list):
        return ["routeHistory must be a list"]
    expected_from = "undecided"
    for index, transition in enumerate(history):
        prefix = f"routeHistory[{index}]"
        if not isinstance(transition, dict):
            errors.append(f"{prefix} must be an object")
            continue
        from_route = transition.get("from")
        to_route = transition.get("to")
        if from_route != expected_from:
            errors.append(
                f"{prefix}.from must be {expected_from!r} to preserve a continuous route history"
            )
        if to_route not in ROUTE_TRANSITION_TABLE.get(str(from_route), set()):
            errors.append(
                f"{prefix} records impossible route transition {from_route} -> {to_route}"
            )
        if not str(transition.get("reason", "")).strip():
            errors.append(f"{prefix}.reason must explain the route change")
        expected_from = str(to_route)
    route = state.get("route")
    if route == "undecided" and history:
        errors.append("An undecided workspace cannot have route history")
    elif route != "undecided":
        if not history:
            errors.append(
                f"Route {route} requires routeHistory beginning at undecided"
            )
        elif expected_from != route:
            errors.append(
                f"routeHistory ends at {expected_from!r}, but the selected route is {route!r}"
            )
    if len(history) > 2:
        errors.append(
            "routeHistory may contain only the initial route and one research-first reroute"
        )
    if len(history) == 2:
        if history[0].get("to") != "research-first":
            errors.append("Only research-first may have a second route transition")
        if "03-evidence" not in state.get("completedSteps", []):
            errors.append(
                "A post-research route transition requires completed 03-evidence"
            )
    if route != "undecided" and not str(state.get("routeRationale", "")).strip():
        errors.append("A selected route requires a non-empty routeRationale")
    elif history and str(state.get("routeRationale", "")).strip() != str(
        history[-1].get("reason", "")
    ).strip():
        errors.append(
            "routeRationale must match the reason on the final routeHistory transition"
        )
    return errors


def skip_policy_error(state: dict[str, Any], step_id: str) -> str | None:
    if effective_route_step_policy(state).get(step_id) != STEP_REQUIRED:
        return f"Step {step_id} is not skippable on route {state.get('route')}"
    mode = state.get("executionMode")
    customer = state.get("customerTesting", {})
    if step_id == "11-customer-sessions":
        if mode != "live":
            return None
        if (
            customer.get("status") == "blocked"
            and customer.get("sessionsCompleted") == 0
        ):
            return None
        return (
            "Live customer sessions may be skipped only when customer testing is "
            "blocked with zero completed sessions; otherwise record suitable sessions"
        )
    if step_id == "12-synthesis":
        if "11-customer-sessions" in state.get("skippedSteps", []):
            if mode != "live" or (
                customer.get("status") == "blocked"
                and customer.get("sessionsCompleted") == 0
            ):
                return None
        if (
            mode == "live"
            and "11-customer-sessions" in state.get("completedSteps", [])
            and customer.get("status") in {"partial", "blocked"}
            and customer.get("sessionsCompleted", 0) > 0
            and customer.get("sessionsUsable", 0) == 0
        ):
            return None
    return (
        f"Step {step_id} is required for route {state.get('route')} in "
        f"{mode} mode and cannot be skipped"
    )


def skip_record_errors(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    skipped = state.get("skippedSteps", [])
    reasons = state.get("skipReasons", {})
    records = state.get("skipRecords", [])
    if not isinstance(records, list):
        return ["skipRecords must be a list"]
    records_by_step: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if not isinstance(record, dict):
            errors.append("Every skipRecords entry must be an object")
            continue
        step_id = str(record.get("step", ""))
        records_by_step.setdefault(step_id, []).append(record)
        if not str(record.get("skippedBy", "")).strip():
            errors.append(f"Skip record {step_id or '<unknown>'} requires skippedBy")
        if not str(record.get("reason", "")).strip():
            errors.append(f"Skip record {step_id or '<unknown>'} requires a reason")
        if record.get("executionMode") != state.get("executionMode"):
            errors.append(
                f"Skip record {step_id} execution mode does not match the workspace"
            )
        if record.get("route") != state.get("route"):
            errors.append(f"Skip record {step_id} route does not match the workspace")
    for step_id in skipped if isinstance(skipped, list) else []:
        matching = records_by_step.get(str(step_id), [])
        if len(matching) != 1:
            errors.append(
                f"Skipped step {step_id} requires exactly one auditable skip record"
            )
            continue
        if matching[0].get("reason") != reasons.get(step_id):
            errors.append(
                f"Skip record {step_id} reason must match skipReasons"
            )
    extras = sorted(set(records_by_step) - set(skipped if isinstance(skipped, list) else []))
    if extras:
        errors.append(
            "skipRecords contains entries for steps that are not skipped: "
            + ", ".join(extras)
        )
    return errors


def customer_testing_errors(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    customer = state.get("customerTesting", {})
    if not isinstance(customer, dict):
        return ["customerTesting must be an object"]
    status = customer.get("status")
    count_names = (
        "sessionsPlanned",
        "sessionsInvited",
        "sessionsAttempted",
        "sessionsCompleted",
        "sessionsQualified",
        "sessionsExcluded",
        "sessionsUsable",
    )
    counts: dict[str, int] = {}
    for name in count_names:
        value = customer.get(name)
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"Customer {name} must be an integer")
        else:
            counts[name] = value
    if errors:
        return errors
    if any(value < 0 for value in counts.values()):
        errors.append("Customer session counts cannot be negative")
        return errors
    planned = counts["sessionsPlanned"]
    invited = counts["sessionsInvited"]
    attempted = counts["sessionsAttempted"]
    completed = counts["sessionsCompleted"]
    qualified = counts["sessionsQualified"]
    excluded = counts["sessionsExcluded"]
    usable = counts["sessionsUsable"]
    if attempted > invited:
        errors.append("Attempted customer sessions cannot exceed invited sessions")
    if completed > attempted:
        errors.append("Completed customer sessions cannot exceed attempted sessions")
    if qualified + excluded > invited:
        errors.append("Qualified plus excluded participants cannot exceed invited sessions")
    if usable > completed or usable > qualified:
        errors.append("Usable sessions cannot exceed completed or qualified sessions")
    target = str(customer.get("target", ""))
    rationale = str(customer.get("targetRationale", ""))
    if planned > 0 and not target.strip():
        errors.append("Planned customer sessions require a non-empty target audience")
    if planned > 0 and not rationale.strip():
        errors.append("Planned customer sessions require a non-empty target rationale")

    if status == "not-planned":
        if any((invited, attempted, completed, qualified, excluded, usable)):
            errors.append(
                "Customer status not-planned requires zero invited, attempted, completed, qualified, excluded, and usable sessions"
            )
    elif status == "recruiting":
        if planned < 1 or completed != 0 or attempted != 0:
            errors.append(
                "Customer status recruiting requires a positive plan and no attempted or completed sessions"
            )
    elif status == "scheduled":
        if planned < 1 or invited < 1 or completed != 0:
            errors.append(
                "Customer status scheduled requires planned and invited sessions with zero completed sessions"
            )
    elif status == "in-progress":
        if planned < 1 or attempted < 1 or usable >= planned:
            errors.append(
                "Customer status in-progress requires an attempted session and fewer usable sessions than planned"
            )
    elif status == "complete":
        if planned < 1 or usable < planned:
            errors.append(
                "Customer status complete requires usable sessions to meet or exceed the positive planned target"
            )
    elif status == "partial":
        if planned < 1 or completed < 1 or usable >= planned:
            errors.append(
                "Customer status partial requires completed activity with fewer usable sessions than planned"
            )
    elif status == "blocked":
        if planned > 0 and usable >= planned:
            errors.append(
                "Customer status blocked requires fewer usable sessions than planned"
            )

    if state.get("executionMode") != "live":
        if status != "not-planned" or any(counts.values()):
            errors.append(
                "Non-live execution modes require customer status not-planned and "
                "zero customer-session counts"
            )
    return errors


def step_history_errors(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    completed = list(state.get("completedSteps", []))
    skipped = list(state.get("skippedSteps", []))
    not_applicable = list(state.get("notApplicableSteps", []))
    policy = effective_route_step_policy(state)
    completed_set = set(completed)
    skipped_set = set(skipped)
    current = state.get("currentStep")
    current_index = STEP_INDEX.get(str(current), -1)

    for label, values in (
        ("completedSteps", completed),
        ("skippedSteps", skipped),
    ):
        if values != sorted(
            values, key=lambda item: STEP_INDEX.get(item, len(STEPS))
        ):
            errors.append(f"{label} must preserve workflow order")
    expected_not_applicable = {
        step_id
        for step_id, disposition in policy.items()
        if disposition == STEP_NOT_APPLICABLE
    }
    if set(not_applicable) != expected_not_applicable:
        errors.append(
            "notApplicableSteps does not match the selected route history; "
            f"expected {sorted(expected_not_applicable)}"
        )
    skip_reasons = state.get("skipReasons", {})
    if set(skip_reasons) != skipped_set:
        errors.append(
            "skipReasons must contain exactly one non-empty reason for each skipped step"
        )
    elif any(
        not isinstance(skip_reasons.get(step_id), str)
        or not skip_reasons[step_id].strip()
        for step_id in skipped
    ):
        errors.append(
            "skipReasons must contain exactly one non-empty reason for each skipped step"
        )
    for step_id in skipped:
        policy_error = skip_policy_error(state, step_id)
        if policy_error:
            errors.append(policy_error)
    for step_id in completed_set | skipped_set:
        disposition = policy.get(step_id)
        if disposition != STEP_REQUIRED:
            errors.append(
                f"Step {step_id} is {disposition or 'undefined'} for route "
                f"{state.get('route')} and cannot be completed or skipped"
            )
        if STEP_INDEX.get(step_id, len(STEPS)) > current_index:
            errors.append(
                f"Future step {step_id} cannot appear before currentStep {current}"
            )

    if "11-customer-sessions" in completed_set:
        customer = state.get("customerTesting", {})
        if state.get("executionMode") != "live":
            errors.append(
                "Non-live execution modes cannot complete 11-customer-sessions; "
                "record the policy-eligible skip instead"
            )
        elif (
            customer.get("status") not in {"complete", "partial"}
            or customer.get("sessionsCompleted", 0) < 1
        ):
            errors.append(
                "Completed 11-customer-sessions requires complete or partial "
                "customer status with at least one recorded session"
            )

    for step in STEPS[: max(0, current_index)]:
        step_id = step["id"]
        if (
            policy.get(step_id) == STEP_REQUIRED
            and step_id not in completed_set | skipped_set
        ):
            errors.append(
                f"Route history is missing required step {step_id} before currentStep {current}"
            )
    if current in skipped_set or current in set(not_applicable):
        errors.append(
            f"currentStep {current} cannot already be skipped or not applicable"
        )
    if current in completed_set:
        pending_gate = state.get("pendingGate")
        waiting_for_reroute = (
            state.get("route") == "research-first"
            and current == "03-evidence"
            and state.get("status") == "waiting-for-human"
        )
        waiting_for_post_research_gate = (
            followed_research_first(state)
            and current == "03-evidence"
            and pending_gate == "gate-1"
            and state.get("status") == "waiting-for-human"
        )
        terminal = (
            state.get("status") == "complete" and current == "13-outcome"
        )
        if not (
            pending_gate == GATE_BY_STEP.get(str(current))
            or waiting_for_reroute
            or waiting_for_post_research_gate
            or terminal
        ):
            errors.append(
                f"Completed currentStep {current} must be awaiting its gate, "
                "awaiting the research reroute, or be terminal"
            )
    if policy.get(str(current)) == STEP_DEFERRED:
        errors.append(
            f"Step {current} is deferred until the required route transition is recorded"
        )
    return errors


def gate_history_errors(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    gates = {
        gate.get("id"): gate
        for gate in state.get("humanGates", [])
        if isinstance(gate, dict)
    }
    decisions_by_gate: dict[str, list[dict[str, Any]]] = {
        gate_id: [] for gate_id in GATE_NAMES
    }
    for decision in state.get("decisions", []):
        if (
            isinstance(decision, dict)
            and decision.get("gate") in decisions_by_gate
        ):
            decisions_by_gate[str(decision["gate"])].append(decision)
    active_decisions_by_gate = {
        gate_id: [
            decision
            for decision in decisions
            if decision.get("status") == "active"
        ]
        for gate_id, decisions in decisions_by_gate.items()
    }
    gate_1_complete = gates.get("gate-1", {}).get("status") == "complete"
    expected_not_applicable = (
        NO_SPRINT_NOT_APPLICABLE_GATES
        if state.get("route") == "no-sprint" and gate_1_complete
        else set()
    )
    completed = set(state.get("completedSteps", []))
    for step_id, gate_id in GATE_BY_STEP.items():
        gate = gates.get(gate_id, {})
        status = gate.get("status")
        expected_status = (
            "not-applicable" if gate_id in expected_not_applicable else None
        )
        if expected_status and status != expected_status:
            errors.append(
                f"{gate_id} must be not-applicable on the approved no-sprint route"
            )
        if not expected_status and status == "not-applicable":
            errors.append(
                f"{gate_id} cannot be not-applicable on route {state.get('route')}"
            )
        active_decisions = active_decisions_by_gate[gate_id]
        if status == "complete":
            if not str(gate.get("decision", "")).strip():
                errors.append(
                    f"{gate_id} complete requires a non-empty decision"
                )
            if step_id not in completed:
                errors.append(
                    f"{gate_id} cannot close before completed step {step_id}"
                )
            if len(active_decisions) != 1:
                errors.append(
                    f"{gate_id} complete requires exactly one active decision record"
                )
            elif gate.get("decisionId") != active_decisions[0].get("id"):
                errors.append(
                    f"{gate_id} decisionId does not match its active decision history"
                )
            elif gate.get("decision") != active_decisions[0].get("decision"):
                errors.append(
                    f"{gate_id} decision does not match the decision history"
                )
            elif not str(active_decisions[0].get("decision", "")).strip():
                errors.append(
                    f"{gate_id} decision history requires a non-empty decision"
                )
        elif active_decisions:
            errors.append(
                f"{gate_id} has an active decision record but is not complete"
            )
        if (
            step_id in completed
            and status == "pending"
            and state.get("pendingGate") != gate_id
        ):
            errors.append(
                f"Completed gated step {step_id} must make {gate_id} the pendingGate"
            )
    pending_gate = state.get("pendingGate")
    if pending_gate is not None:
        step_id = next(
            step for step, gate in GATE_BY_STEP.items() if gate == pending_gate
        )
        post_research_gate = (
            pending_gate == "gate-1"
            and followed_research_first(state)
            and state.get("currentStep") == "03-evidence"
            and "03-evidence" in completed
        )
        if (
            gates.get(pending_gate, {}).get("status") != "pending"
            or (
                not post_research_gate
                and (
                    state.get("currentStep") != step_id
                    or step_id not in completed
                )
            )
            or state.get("status") != "waiting-for-human"
        ):
            errors.append(
                f"pendingGate {pending_gate} requires completed current step "
                f"{step_id} and waiting-for-human status"
            )
    completed_gate_ids = [
        gate_id
        for gate_id in GATE_NAMES
        if gates.get(gate_id, {}).get("status") == "complete"
    ]
    for gate_id in completed_gate_ids:
        index = list(GATE_NAMES).index(gate_id)
        for prior_gate in list(GATE_NAMES)[:index]:
            if prior_gate in expected_not_applicable:
                continue
            if gates.get(prior_gate, {}).get("status") != "complete":
                errors.append(f"{gate_id} cannot close before {prior_gate}")
    if gate_1_complete and state.get("route") == "undecided":
        errors.append("Gate 1 cannot close while the route is undecided")
    return errors


def terminal_state_errors(state: dict[str, Any]) -> list[str]:
    if state.get("status") != "complete":
        errors = []
        if state.get("outcome") is not None:
            errors.append("Only a terminal complete workspace may record outcome")
        if state.get("terminalState") != "not-terminal":
            errors.append(
                "A non-terminal workspace must record terminalState as not-terminal"
            )
        return errors
    errors: list[str] = []
    expected = expected_terminal_state(state)
    if state.get("terminalState") != expected:
        errors.append(
            f"Terminal state must be {expected} for the recorded mode, route, and customer evidence"
        )
    if state.get("route") in {"undecided", "research-first"}:
        errors.append(
            "A terminal workspace requires a final route, not undecided or research-first"
        )
    if state.get("currentStep") != "13-outcome":
        errors.append("A terminal workspace must end at 13-outcome")
    if state.get("pendingGate") is not None:
        errors.append("A terminal workspace cannot have a pending gate")
    outcome = str(state.get("outcome", "")).lower()
    if outcome not in FINAL_OUTCOMES:
        errors.append("A terminal workspace requires a valid final outcome")
    gate_5 = next(
        (
            gate
            for gate in state.get("humanGates", [])
            if isinstance(gate, dict) and gate.get("id") == "gate-5"
        ),
        None,
    )
    if (
        gate_5 is not None
        and gate_5.get("status") == "complete"
        and str(gate_5.get("decision", "")).strip().lower() != outcome
    ):
        errors.append("Terminal outcome must match the recorded Gate 5 decision")
    policy = effective_route_step_policy(state)
    completed = set(state.get("completedSteps", []))
    skipped = set(state.get("skippedSteps", []))
    for step_id, disposition in policy.items():
        if (
            disposition == STEP_REQUIRED
            and step_id not in completed | skipped
        ):
            errors.append(f"Terminal route is missing required step {step_id}")
        if disposition == STEP_DEFERRED:
            errors.append(
                f"Terminal route still defers step {step_id}; record the final route first"
            )
    customer = state.get("customerTesting", {})
    if state.get("route") == "no-sprint":
        if outcome not in {"investigate", "stop"}:
            errors.append(
                "A no-sprint terminal state may close only as Investigate or Stop"
            )
    elif state.get("executionMode") != "live":
        if "11-customer-sessions" not in skipped:
            errors.append(
                "A non-live terminal state requires 11-customer-sessions to be "
                "explicitly skipped"
            )
        if "12-synthesis" not in skipped:
            errors.append(
                "A non-live terminal state requires customer-evidence synthesis to be explicitly skipped"
            )
        if outcome not in {"investigate", "stop"}:
            errors.append(
                "A non-live terminal state may close only as Investigate or Stop"
            )
    elif "11-customer-sessions" in skipped:
        if "12-synthesis" not in skipped:
            errors.append(
                "A live untested terminal state requires customer-evidence synthesis to be explicitly skipped"
            )
        if outcome not in {"investigate", "stop"}:
            errors.append(
                "A live run without customer sessions may close only as Investigate or Stop"
            )
        if (
            customer.get("status") != "blocked"
            or customer.get("sessionsCompleted") != 0
        ):
            errors.append(
                "A live untested terminal state requires blocked customer testing with zero sessions"
            )
    else:
        usable = int(customer.get("sessionsUsable", 0))
        if "11-customer-sessions" not in completed:
            errors.append(
                "A live terminal state with attempted testing requires completed customer sessions"
            )
        if usable == 0:
            if "12-synthesis" not in skipped:
                errors.append(
                    "A live terminal state with zero usable sessions requires synthesis to be explicitly skipped"
                )
            if outcome not in {"investigate", "stop"}:
                errors.append(
                    "A live run with zero usable sessions may close only as Investigate or Stop"
                )
        elif "12-synthesis" not in completed:
            errors.append(
                "A tested live terminal state with usable evidence requires completed synthesis"
            )
        if customer.get("status") not in {"complete", "partial"}:
            errors.append(
                "A tested live terminal state requires complete or partial customer status"
            )
    return errors


def decision_record_errors(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    decisions = state.get("decisions", [])
    gates = state.get("humanGates", [])
    if not isinstance(decisions, list) or not isinstance(gates, list):
        return errors
    by_id: dict[str, dict[str, Any]] = {}
    active_by_gate: dict[str, list[dict[str, Any]]] = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        decision_id = str(decision.get("id", ""))
        if decision_id in by_id:
            errors.append(f"Duplicate decision id: {decision_id}")
        else:
            by_id[decision_id] = decision
        gate_id = str(decision.get("gate", ""))
        if decision.get("status") == "active":
            active_by_gate.setdefault(gate_id, []).append(decision)
        subject = decision.get("subject", {})
        if isinstance(subject, dict):
            expected_digest = value_digest(
                str(subject.get("kind", "")), str(subject.get("value", ""))
            )
            if subject.get("digest") != expected_digest:
                errors.append(f"Decision {decision_id} has an invalid subject digest")
        if decision.get("status") == "superseded" and str(
            decision.get("supersededAt", "")
        ) < str(decision.get("decidedAt", "")):
            errors.append(f"Decision {decision_id} was superseded before it was made")
    for gate_id, active in active_by_gate.items():
        if len(active) > 1:
            errors.append(f"Gate {gate_id} has duplicate active decisions")

    for gate in gates:
        if not isinstance(gate, dict):
            continue
        gate_id = str(gate.get("id", ""))
        if gate.get("status") == "complete":
            decision_id = str(gate.get("decisionId", ""))
            decision = by_id.get(decision_id)
            if decision is None:
                errors.append(
                    f"Completed {gate_id} does not reference an explicit decision record"
                )
            elif decision.get("gate") != gate_id or decision.get("status") != "active":
                errors.append(
                    f"Completed {gate_id} must reference its active decision record"
                )
            elif gate.get("decision") != decision.get("decision"):
                errors.append(
                    f"Completed {gate_id} does not match decision {decision_id}"
                )
        elif gate.get("status") == "pending" and active_by_gate.get(gate_id):
            errors.append(f"Pending {gate_id} cannot retain an active decision")
    pending_gate = state.get("pendingGate")
    if pending_gate:
        pending_record = next(
            (
                gate
                for gate in gates
                if isinstance(gate, dict) and gate.get("id") == pending_gate
            ),
            None,
        )
        if pending_record is None or pending_record.get("status") != "pending":
            errors.append("pendingGate must reference a pending human gate")

    gate_1 = active_by_gate.get("gate-1", [])
    if gate_1:
        subject = gate_1[0].get("subject", {})
        if subject.get("kind") != "route" or subject.get("value") != state.get("route"):
            errors.append(
                "The current route materially differs from Gate 1; a new human decision is required"
            )
    gate_3 = active_by_gate.get("gate-3", [])
    if gate_3:
        subject = gate_3[0].get("subject", {})
        if (
            subject.get("kind") != "concept"
            or subject.get("value") != state.get("selectedConcept")
        ):
            errors.append(
                "The selected concept materially differs from Gate 3; a new human decision is required"
            )
    return errors


def validate_state(state: dict[str, Any]) -> list[str]:
    """Return cross-record workflow and transition-model checks.

    JSON shape, types, enums, formats, and nested conditions are enforced by the
    workspace-state schema before this function is called. This layer enforces
    semantic relationships that JSON Schema cannot express cleanly.
    """

    errors: list[str] = []
    required = {
        "schemaVersion",
        "title",
        "slug",
        "challenge",
        "methodProfile",
        "executionMode",
        "route",
        "methodProfileSelection",
        "executionModeSelection",
        "fidelity",
        "routeHistory",
        "status",
        "terminalState",
        "currentStep",
        "completedSteps",
        "skippedSteps",
        "skipRecords",
        "notApplicableSteps",
        "humanGates",
        "artifacts",
        "customerTesting",
        "nextAction",
        "updatedAt",
    }
    missing = sorted(required - state.keys())
    if missing:
        errors.append(f"State is missing keys: {', '.join(missing)}")
    if state.get("schemaVersion") != STATE_SCHEMA_VERSION:
        errors.append(f"Unsupported state schema: {state.get('schemaVersion')}")
    errors.extend(
        profile_mode_route_errors(
            state.get("methodProfile"),
            state.get("executionMode"),
            state.get("route"),
        )
    )
    for key in ("methodProfileSelection", "executionModeSelection"):
        selection = state.get(key)
        if not isinstance(selection, dict) or not str(
            selection.get("selectedBy", "")
        ).strip() or not str(selection.get("reason", "")).strip():
            errors.append(f"{key} must record selectedBy and reason")
    if state.get("status") not in WORKSPACE_STATUSES:
        errors.append(f"Invalid workspace status: {state.get('status')}")
    if state.get("terminalState") not in TERMINAL_STATES:
        errors.append(f"Invalid terminal state: {state.get('terminalState')}")
    if state.get("currentStep") not in STEP_INDEX:
        errors.append(f"Invalid current step: {state.get('currentStep')}")
    completed = state.get("completedSteps", [])
    skipped = state.get("skippedSteps", [])
    not_applicable = state.get("notApplicableSteps", [])
    if not isinstance(completed, list) or len(completed) != len(set(completed)):
        errors.append("completedSteps must be a unique list")
    if not isinstance(skipped, list) or len(skipped) != len(set(skipped)):
        errors.append("skippedSteps must be a unique list")
    if not isinstance(not_applicable, list) or len(not_applicable) != len(
        set(not_applicable)
    ):
        errors.append("notApplicableSteps must be a unique list")
    if all(isinstance(value, list) for value in (completed, skipped, not_applicable)):
        if set(completed) & set(skipped):
            errors.append("A step cannot be both completed and skipped")
        if set(completed) & set(not_applicable):
            errors.append("A step cannot be both completed and not applicable")
        if set(skipped) & set(not_applicable):
            errors.append("A step cannot be both skipped and not applicable")
        expected_not_applicable = set(
            route_not_applicable_steps(
                str(state.get("route")), state.get("routeHistory", [])
            )
        )
        if set(not_applicable) != expected_not_applicable:
            errors.append(
                "notApplicableSteps does not match the selected route"
            )
    errors.extend(customer_testing_errors(state))
    customer = state.get("customerTesting", {})
    if isinstance(customer, dict):
        planned = customer.get("sessionsPlanned")
        if (
            state.get("methodProfile") == "sprint-book"
            and state.get("executionMode") == "live"
            and isinstance(planned, int)
            and planned != 5
        ):
            customer_deviations = (
                state.get("fidelity", {})
                .get("steps", {})
                .get("11-customer-sessions", {})
                .get("deviations", [])
            )
            if not any(
                item.get("id") == "customer-target"
                for item in customer_deviations
                if isinstance(item, dict)
            ):
                errors.append(
                    "Sprint-book live profiles default to five suitable customers; another target requires a documented deviation"
                )
    errors.extend(route_history_errors(state))
    errors.extend(step_history_errors(state))
    errors.extend(skip_record_errors(state))
    errors.extend(gate_history_errors(state))
    errors.extend(terminal_state_errors(state))
    errors.extend(fidelity_errors(state))
    errors.extend(decision_record_errors(state))
    gates = state.get("humanGates", [])
    if not isinstance(gates, list) or {item.get("id") for item in gates if isinstance(item, dict)} != set(GATE_NAMES):
        errors.append("humanGates must contain gate-1 through gate-5")
    if state.get("status") == "complete":
        gate_5 = next((gate for gate in gates if gate.get("id") == "gate-5"), {})
        if gate_5.get("status") != "complete":
            errors.append("A complete sprint requires Gate 5")
        if state.get("executionMode") != "live" and str(
            state.get("outcome", "")
        ).lower() in {"proceed", "iterate", "pivot"}:
            errors.append(
                "A non-live run cannot close with a customer-evidence-dependent outcome"
            )
    return errors


def local_reference_target(
    source_path: Path, reference: str, site_root: Path
) -> tuple[Path | None, str | None, str | None]:
    parsed = urlsplit(reference)
    scheme = parsed.scheme.lower()
    if scheme in {"http", "https", "mailto", "tel", "data"}:
        return None, parsed.fragment or None, None
    if scheme or parsed.netloc:
        return None, None, f"unsupported or non-portable URL scheme: {reference}"
    decoded_path = unquote(parsed.path)
    if decoded_path.startswith(("/", "\\")):
        return None, None, f"root-absolute local link is not portable: {reference}"
    if "\\" in decoded_path:
        return None, None, f"local link must use URL-style separators: {reference}"
    target = (source_path.parent / (decoded_path or source_path.name)).resolve()
    try:
        target.relative_to(site_root.resolve())
    except ValueError:
        return None, None, f"local link escapes site root: {reference}"
    if target.is_dir():
        target = target / "index.html"
    return target, parsed.fragment or None, None


def reference_errors(path: Path, site_root: Path) -> list[str]:
    errors: list[str] = []
    if path.suffix.lower() == ".html":
        parser = LocalLinkParser()
        try:
            parser.feed(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as error:
            return [f"{path}: could not read HTML: {error}"]
        for tag, attribute, reference in parser.references:
            parsed = urlsplit(reference)
            if parsed.scheme.lower() in {"http", "https", "mailto", "tel"} and tag != "a":
                errors.append(
                    f"{path}: external {tag} {attribute} is not an offline local asset: {reference}"
                )
                continue
            target, fragment, problem = local_reference_target(
                path, reference, site_root
            )
            if problem:
                errors.append(f"{path}: {problem}")
                continue
            if target is None:
                continue
            if not target.exists():
                errors.append(f"{path}: broken local link: {reference}")
                continue
            if fragment and target.suffix.lower() == ".html":
                target_parser = LocalLinkParser()
                try:
                    target_parser.feed(target.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError) as error:
                    errors.append(f"{path}: could not inspect fragment target {target}: {error}")
                    continue
                if unquote(fragment) not in target_parser.ids:
                    errors.append(
                        f"{path}: missing fragment target #{fragment} in {target}"
                    )
    elif path.suffix.lower() == ".css":
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            return [f"{path}: could not read CSS: {error}"]
        references = re.findall(
            r"url\(\s*['\"]?([^)'\"\s]+)|@import\s+['\"]([^'\"]+)", text
        )
        for first, second in references:
            reference = first or second
            if urlsplit(reference).scheme.lower() in {"http", "https"}:
                errors.append(
                    f"{path}: external CSS asset is not an offline local asset: {reference}"
                )
                continue
            target, _fragment, problem = local_reference_target(
                path, reference, site_root
            )
            if problem:
                errors.append(f"{path}: {problem}")
            elif target is not None and not target.exists():
                errors.append(f"{path}: broken local asset: {reference}")
    elif path.suffix.lower() in {".js", ".mjs"}:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            return [f"{path}: could not read JavaScript: {error}"]
        patterns = (
            r"(?:^|[;\n])\s*import\s+(?:[^;\n]*?\s+from\s+)?['\"]([^'\"]+)['\"]",
            r"(?:^|[;\n])\s*export\s+[^;\n]*?\s+from\s+['\"]([^'\"]+)['\"]",
            r"\bimport\(\s*['\"]([^'\"]+)['\"]\s*\)",
            r"\b(?:fetch|new\s+(?:Worker|SharedWorker))\(\s*['\"]([^'\"]+)['\"]",
        )
        references = [
            match
            for pattern in patterns
            for match in re.findall(pattern, source, flags=re.MULTILINE)
        ]
        for reference in references:
            if urlsplit(reference).scheme.lower() in {"http", "https"}:
                errors.append(
                    f"{path}: external JavaScript dependency is not an offline local asset: {reference}"
                )
                continue
            target, _fragment, problem = local_reference_target(
                path, reference, site_root
            )
            if problem:
                errors.append(f"{path}: {problem}")
            elif target is not None and not target.exists():
                errors.append(f"{path}: broken local JavaScript dependency: {reference}")
    return errors


def local_link_errors(html_path: Path, workspace: Path) -> list[str]:
    """Backward-compatible single-page wrapper around the full reference check."""

    return reference_errors(html_path, workspace)


def site_crawl_errors(site_root: Path, site_manifest: dict[str, Any]) -> list[str]:
    errors = formatted_schema_errors(
        site_manifest, "site-manifest", site_root / SITE_MANIFEST_FILENAME
    )
    if errors:
        return errors
    pages = site_manifest["pages"]
    page_ids = [page["id"] for page in pages]
    page_paths = [page["path"] for page in pages]
    if len(page_ids) != len(set(page_ids)):
        errors.append("Site manifest contains duplicate page IDs")
    if len(page_paths) != len(set(page_paths)):
        errors.append("Site manifest contains duplicate page paths")
    asset_paths = [asset["path"] for asset in site_manifest["assets"]]
    if len(asset_paths) != len(set(asset_paths)):
        errors.append("Site manifest contains duplicate asset paths")
    page_path_set = set(page_paths)
    for asset in site_manifest["assets"]:
        if asset["path"] in page_path_set:
            errors.append(
                f"Site manifest path is both a page and an asset: {asset['path']}"
            )
        asset_path = site_root / str(asset["path"])
        if not asset_path.exists():
            errors.append(f"Missing site-manifest asset: {asset['path']}")
            continue
        try:
            payload = asset_path.read_bytes()
        except OSError as error:
            errors.append(f"Could not read site-manifest asset {asset['path']}: {error}")
            continue
        if sha256_bytes(payload) != asset["sha256"]:
            errors.append(f"Stale asset digest for site-manifest asset: {asset['path']}")
        if len(payload) != asset["bytes"]:
            errors.append(f"Stale byte count for site-manifest asset: {asset['path']}")
    known_ids = set(page_ids)
    manifest_html_paths: set[Path] = set()
    for page in pages:
        for key in ("home", "previous", "next", "decision", "prototype", "outcome"):
            target_id = page["relationships"].get(key)
            if target_id is not None and target_id not in known_ids:
                errors.append(
                    f"Site manifest page {page['id']} {key} references unknown page {target_id}"
                )
        unknown_related = sorted(
            set(page["relationships"]["relatedEvidence"]) - known_ids
        )
        if unknown_related:
            errors.append(
                f"Site manifest page {page['id']} has unknown related pages: {', '.join(unknown_related)}"
            )
        page_path = site_root / str(page["path"])
        manifest_html_paths.add(page_path.resolve())
        if not page_path.exists():
            errors.append(f"Missing site-manifest page: {page['path']}")
            continue
        try:
            payload = page_path.read_bytes()
        except OSError as error:
            errors.append(f"Could not read site-manifest page {page['path']}: {error}")
            continue
        if sha256_bytes(payload) != page["renderDigest"]:
            errors.append(f"Stale render digest for site-manifest page: {page['path']}")
        parser = LocalLinkParser()
        try:
            parser.feed(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            errors.append(f"Invalid HTML in site-manifest page {page['path']}: {error}")
            continue
        if parser.site_navigation_landmarks != 1:
            errors.append(
                f"Site-manifest page {page['path']} must contain exactly one Sprint site navigation landmark"
            )
        if parser.current_page_indicators < 1:
            errors.append(
                f"Site-manifest page {page['path']} is missing current-page indication"
            )

    all_html = sorted(site_root.rglob("*.html"))
    for html_path in all_html:
        text = html_path.read_text(encoding="utf-8")
        if re.search(r"\{\{[A-Z0-9_]+\}\}", text):
            errors.append(f"Unresolved template token in {html_path}")
        errors.extend(reference_errors(html_path, site_root))
    for css_path in sorted(site_root.rglob("*.css")):
        errors.extend(reference_errors(css_path, site_root))
    for javascript_pattern in ("*.js", "*.mjs"):
        for javascript_path in sorted(site_root.rglob(javascript_pattern)):
            errors.extend(reference_errors(javascript_path, site_root))

    home = next((page for page in pages if page["id"] == "home"), None)
    if home is None:
        errors.append("Site manifest is missing the home page")
        return errors
    start = (site_root / home["path"]).resolve()
    reachable: set[Path] = set()
    pending = [start]
    while pending:
        current = pending.pop()
        if current in reachable or not current.exists() or current.suffix.lower() != ".html":
            continue
        reachable.add(current)
        parser = LocalLinkParser()
        parser.feed(current.read_text(encoding="utf-8"))
        for tag, attribute, reference in parser.references:
            if tag != "a" or attribute != "href":
                continue
            target, _fragment, problem = local_reference_target(
                current, reference, site_root
            )
            if problem is None and target is not None and target.suffix.lower() == ".html":
                pending.append(target.resolve())
    unreachable = sorted(manifest_html_paths - reachable)
    for path in unreachable:
        errors.append(
            f"Site-manifest page is not reachable from index.html: {workspace_relative(path, site_root)}"
        )
    return errors


def workspace_relative(path: Path, workspace: Path) -> str:
    try:
        return path.relative_to(workspace).as_posix()
    except ValueError:
        return str(path)


def rendered_output_errors(workspace: Path) -> list[str]:
    """Compare disposable views with bytes derived from canonical JSON/templates."""

    plan = build_render_plan(workspace)
    errors: list[str] = []
    if plan.state_update is not None:
        errors.append(
            f"{STATE_FILENAME}: renderer-managed artifact catalog is stale"
        )
    for path, expected_text in sorted(
        plan.generated_files.items(), key=lambda item: item[0].as_posix()
    ):
        relative = workspace_relative(path, workspace)
        try:
            actual = path.read_bytes()
        except FileNotFoundError:
            errors.append(f"Missing rendered file: {relative}")
            continue
        except OSError as error:
            errors.append(f"Could not read rendered file {relative}: {error}")
            continue
        if actual != expected_text.encode("utf-8"):
            errors.append(f"Stale rendered file: {relative}")
        if (
            portable_permissions_supported()
            and file_mode(path) != PORTABLE_FILE_MODE
        ):
            errors.append(
                f"Non-portable permissions on {relative}: "
                f"{file_mode(path):04o}; expected {PORTABLE_FILE_MODE:04o}"
            )
    for path in plan.stale_files:
        errors.append(
            f"Unexpected rendered file with no canonical artifact: "
            f"{workspace_relative(path, workspace)}"
        )
    if portable_permissions_supported():
        for path in plan.canonical_files:
            if path.exists() and file_mode(path) != PORTABLE_FILE_MODE:
                errors.append(
                    f"Non-portable permissions on "
                    f"{workspace_relative(path, workspace)}: "
                    f"{file_mode(path):04o}; expected {PORTABLE_FILE_MODE:04o}"
                )
    return errors


def customer_testing_record_errors(
    workspace: Path, state: dict[str, Any]
) -> list[str]:
    """Validate session isolation, version bindings, counts, and packet traceability."""

    path = manifest_path(workspace)
    if not path.exists():
        completed = state.get("customerTesting", {}).get("sessionsCompleted", 0)
        if completed:
            return [
                "Customer sessions are counted but customer-testing/session-manifest.json is missing"
            ]
        return []
    try:
        manifest = read_json(path)
    except SprintError as error:
        return [str(error)]
    errors = formatted_schema_errors(manifest, "session-manifest", path)
    if errors:
        return errors
    if manifest["workspaceSlug"] != state.get("slug"):
        errors.append("Session manifest workspaceSlug does not match sprint state")
    requires_tested_version = (
        manifest.get("testArtifactWorkflowVersion")
        == TEST_ARTIFACT_WORKFLOW_VERSION
    )

    prototype_catalog = manifest["versionCatalog"]["prototypes"]
    questions_catalog = manifest["versionCatalog"]["questions"]
    prototype_versions = [item["version"] for item in prototype_catalog]
    questions_versions = [item["version"] for item in questions_catalog]
    if len(prototype_versions) != len(set(prototype_versions)):
        errors.append("Prototype version catalog contains duplicate version identifiers")
    if len(questions_versions) != len(set(questions_versions)):
        errors.append("Questions version catalog contains duplicate version identifiers")
    current = manifest["currentVersions"]
    if current["prototype"] is not None and current["prototype"] not in prototype_versions:
        errors.append("Current prototype version is absent from the version catalog")
    if current["questions"] is not None and current["questions"] not in questions_versions:
        errors.append("Current questions version is absent from the version catalog")
    for label, catalog_entries, descriptor_keys in (
        (
            "prototype",
            prototype_catalog,
            (
                "prototypeArtifact",
                "prototypeContext",
                *(("testedVersion",) if requires_tested_version else ()),
            ),
        ),
        ("questions", questions_catalog, ("interviewGuide", "scorecard")),
    ):
        for catalog_entry in catalog_entries:
            for key in descriptor_keys:
                try:
                    descriptor_text(
                        workspace,
                        catalog_entry[key],
                        f"Catalog {label} {catalog_entry['version']} {key}",
                    )
                except SprintError as error:
                    errors.append(str(error))

    entries = manifest["sessions"]
    session_ids = [item["sessionId"] for item in entries]
    if len(session_ids) != len(set(session_ids)):
        errors.append("Session manifest contains duplicate session IDs")
    identity_keys = [
        (
            item["participantId"],
            item["sessionDate"],
            item["prototypeVersion"],
            item["questionsVersion"],
        )
        for item in entries
    ]
    if len(identity_keys) != len(set(identity_keys)):
        errors.append(
            "Session manifest contains a duplicate participant/date/version combination"
        )
    registered_record_paths: set[str] = set()
    registered_summary_paths: set[str] = set()
    raw_references: set[str] = set()
    raw_reference_owners: dict[str, str] = {}
    session_packet_texts: dict[str, str] = {}
    for entry in entries:
        session_id = entry["sessionId"]
        if requires_tested_version and "testedVersion" not in entry:
            errors.append(
                f"Session {session_id} does not link an immutable tested version"
            )
        expected_directory = session_directory(workspace, session_id)
        expected_record = (expected_directory / "session.json").relative_to(workspace).as_posix()
        expected_summary = (expected_directory / "summary.json").relative_to(workspace).as_posix()
        if entry["recordPath"] != expected_record:
            errors.append(f"Session {session_id} recordPath does not use its isolated directory")
        if entry["summaryPath"] != expected_summary:
            errors.append(f"Session {session_id} summaryPath does not use its isolated directory")
        registered_record_paths.add(entry["recordPath"])
        registered_summary_paths.add(entry["summaryPath"])
        try:
            record_path = workspace_relative_file(
                workspace, entry["recordPath"], f"Session {session_id} record"
            )
            summary_path = workspace_relative_file(
                workspace, entry["summaryPath"], f"Session {session_id} summary"
            )
            record = load_session_record(record_path)
            summary = load_session_summary(summary_path)
        except SprintError as error:
            errors.append(str(error))
            continue
        for key in (
            "sessionId",
            "participantId",
            "sessionDate",
            "prototypeVersion",
            "questionsVersion",
            "status",
        ):
            if entry[key] != record[key]:
                errors.append(f"Session {session_id} manifest {key} does not match its record")
        participant = record["participant"]
        quality = record["evidenceQuality"]
        for entry_key, record_value in (
            ("participantSegment", participant["segment"]),
            ("participantFit", participant["fit"]),
            ("protocolFidelity", quality["protocolFidelity"]),
            ("criticalScenariosCovered", quality["criticalScenariosCovered"]),
            ("usable", quality["usable"]),
            ("exclusionReason", quality["exclusionReason"]),
        ):
            if entry[entry_key] != record_value:
                errors.append(
                    f"Session {session_id} manifest {entry_key} does not match its record"
                )
        attempted_should_be_true = quality["attemptedAt"] is not None
        if entry["attempted"] != attempted_should_be_true:
            errors.append(
                f"Session {session_id} attempted flag must match attemptedAt"
            )
        if participant["fit"] != "unassessed" and not participant[
            "fitRationale"
        ].strip():
            errors.append(
                f"Session {session_id} participant fit requires a rationale"
            )
        if record["artifacts"]["summaryPath"] != entry["summaryPath"]:
            errors.append(f"Session {session_id} record points to a different summary")
        if requires_tested_version:
            tested_descriptor = entry.get("testedVersion")
            if record["artifacts"].get("testedVersion") != tested_descriptor:
                errors.append(
                    f"Session {session_id} record does not link the manifest tested version"
                )
            if summary.get("testedVersion") != tested_descriptor:
                errors.append(
                    f"Session {session_id} summary does not link the manifest tested version"
                )
        errors.extend(
            f"Session {session_id}: {item}"
            for item in session_summary_errors(
                summary, record, require_complete=record["status"] == "complete"
            )
        )
        if entry["prototypeVersion"] not in prototype_versions:
            errors.append(f"Session {session_id} uses an unknown prototype version")
        else:
            catalog_entry = next(
                item for item in prototype_catalog if item["version"] == entry["prototypeVersion"]
            )
            keys = ["prototypeArtifact", "prototypeContext"]
            if requires_tested_version:
                keys.append("testedVersion")
            for key in keys:
                if record["artifacts"][key] != catalog_entry[key]:
                    errors.append(
                        f"Session {session_id} {key} does not match its prototype version"
                    )
            if requires_tested_version:
                try:
                    tested_path = workspace_relative_file(
                        workspace,
                        catalog_entry["testedVersion"]["path"],
                        f"Session {session_id} immutable tested-version record",
                    )
                    tested_record = load_tested_version(tested_path)
                    if tested_record["version"] != entry["prototypeVersion"]:
                        errors.append(
                            f"Session {session_id} tested-version record uses a different version ID"
                        )
                    for record_key, catalog_key in (
                        ("prototypeArtifact", "prototypeArtifact"),
                        ("prototypeContext", "prototypeContext"),
                    ):
                        frozen = tested_record[record_key]
                        catalog_descriptor = catalog_entry[catalog_key]
                        if (
                            frozen["path"] != catalog_descriptor["path"]
                            or frozen["sha256"] != catalog_descriptor["sha256"]
                        ):
                            errors.append(
                                f"Session {session_id} {record_key} is not the artifact frozen in its tested-version record"
                            )
                except SprintError as error:
                    errors.append(str(error))
        if entry["questionsVersion"] not in questions_versions:
            errors.append(f"Session {session_id} uses an unknown questions version")
        else:
            catalog_entry = next(
                item for item in questions_catalog if item["version"] == entry["questionsVersion"]
            )
            for key in ("interviewGuide", "scorecard"):
                if record["artifacts"][key] != catalog_entry[key]:
                    errors.append(
                        f"Session {session_id} {key} does not match its questions version"
                    )
        for key, descriptor in record["artifacts"].items():
            if key == "summaryPath":
                continue
            descriptors = descriptor if isinstance(descriptor, list) else [descriptor]
            for index, item in enumerate(descriptors, 1):
                try:
                    descriptor_text(
                        workspace, item, f"Session {session_id} {key} input {index}"
                    )
                except SprintError as error:
                    errors.append(str(error))
        counted_should_be_true = record["status"] == "complete"
        if entry["counted"] != counted_should_be_true:
            errors.append(
                f"Session {session_id} counted flag must match complete status"
            )
        if entry["includeInSynthesis"] and (
            not entry["counted"] or not entry["usable"]
        ):
            errors.append(
                f"Session {session_id} cannot enter synthesis unless it is completed and usable"
            )
        if quality["usable"]:
            if record["status"] != "complete":
                errors.append(f"Session {session_id} is usable before completion")
            if participant["fit"] != "qualified":
                errors.append(
                    f"Session {session_id} is usable without a qualified participant"
                )
            if quality["protocolFidelity"] in {
                "not-assessed",
                "material-deviation",
            }:
                errors.append(
                    f"Session {session_id} is usable without an acceptable protocol assessment"
                )
            if not quality["criticalScenariosCovered"]:
                errors.append(
                    f"Session {session_id} is usable without critical-scenario coverage"
                )
            if quality["exclusionReason"].strip():
                errors.append(
                    f"Session {session_id} is usable but retains an exclusion reason"
                )
        elif record["status"] == "complete" and not quality[
            "exclusionReason"
        ].strip():
            errors.append(
                f"Session {session_id} is completed but unusable without an exclusion reason"
            )
        if record["status"] == "complete":
            if summary["status"] != "complete":
                errors.append(f"Session {session_id} has a non-complete summary")
            if record["consent"]["status"] != "granted":
                errors.append(f"Session {session_id} is complete without granted consent")
            if not record["consent"]["scope"].strip():
                errors.append(f"Session {session_id} is complete without consent scope")
            if not record["consent"]["reference"].strip():
                errors.append(
                    f"Session {session_id} is complete without a consent-record reference"
                )
            if record["redaction"]["status"] not in {"complete", "not-required"}:
                errors.append(f"Session {session_id} is complete without redaction review")
            if record["rawEvidence"] != summary["sourceReferences"]:
                errors.append(
                    f"Session {session_id} raw-evidence pointers do not match its summary audit pointers"
                )
            if entry["summarySha256"] != sha256_bytes(summary_path.read_bytes()):
                errors.append(
                    f"Session {session_id} completed summary changed without reopening"
                )
        elif entry["summarySha256"] is not None:
            errors.append(
                f"Session {session_id} has a completion summary hash while not complete"
            )
        usage = record["usage"]
        if usage["available"] and not usage["measurements"]:
            errors.append(f"Session {session_id} marks usage available without measurements")
        if not usage["available"] and usage["measurements"]:
            errors.append(f"Session {session_id} has measurements marked unavailable")
        if not usage["available"] and not usage["unavailableReason"].strip():
            errors.append(f"Session {session_id} must explain unavailable usage")
        usage_names = [item["name"] for item in usage["measurements"]]
        if len(usage_names) != len(set(usage_names)):
            errors.append(f"Session {session_id} has duplicate usage measurements")
        usage_values = {
            item["name"]: item["value"] for item in usage["measurements"]
        }
        if all(
            name in usage_values
            for name in ("inputTokens", "outputTokens", "totalTokens")
        ) and (
            usage_values["inputTokens"] + usage_values["outputTokens"]
            != usage_values["totalTokens"]
        ):
            errors.append(f"Session {session_id} token usage totals do not reconcile")
        for raw_item in record["rawEvidence"]:
            reference = raw_item.get("reference")
            if not reference:
                continue
            previous_owner = raw_reference_owners.get(reference)
            if previous_owner is not None and previous_owner != session_id:
                errors.append(
                    f"Raw-evidence reference is shared by sessions {previous_owner} and {session_id}"
                )
            raw_reference_owners[reference] = session_id
            raw_references.add(reference)
        packet = record["packet"]
        if packet["path"] is not None:
            if packet["path"] != entry["packetPath"]:
                errors.append(f"Session {session_id} packet path differs from the manifest")
            expected_packet = (expected_directory / "handoff.md").relative_to(workspace).as_posix()
            if packet["path"] != expected_packet:
                errors.append(f"Session {session_id} packet is outside its isolated directory")
            try:
                packet_path = workspace_relative_file(
                    workspace, packet["path"], f"Session {session_id} packet"
                )
                packet_text = packet_path.read_text(encoding="utf-8")
                if len(packet_text) != packet["characters"]:
                    errors.append(f"Session {session_id} packet character count is stale")
                if sha256_text(packet_text) != packet["sha256"]:
                    errors.append(f"Session {session_id} packet hash is stale")
                maximum = manifest["contextBudget"]["perSessionMaximum"]
                if len(packet_text) > maximum:
                    errors.append(f"Session {session_id} packet exceeds its context budget")
                session_packet_texts[session_id] = packet_text
            except (SprintError, OSError, UnicodeDecodeError) as error:
                errors.append(str(error))

    for session_id, packet_text in session_packet_texts.items():
        for reference in raw_references:
            if reference in packet_text:
                errors.append(
                    f"Session {session_id} packet exposes a raw-evidence reference"
                )

    session_root = workspace / CUSTOMER_TESTING_DIR / "sessions"
    if session_root.exists():
        actual_records = {
            path.relative_to(workspace).as_posix()
            for path in session_root.glob("*/session.json")
        }
        actual_summaries = {
            path.relative_to(workspace).as_posix()
            for path in session_root.glob("*/summary.json")
        }
        for orphan in sorted(actual_records - registered_record_paths):
            errors.append(f"Unregistered customer-session record: {orphan}")
        for orphan in sorted(actual_summaries - registered_summary_paths):
            errors.append(f"Unregistered customer-session summary: {orphan}")

    counted = sum(item["counted"] for item in entries)
    customer = state.get("customerTesting", {})
    if customer.get("sessionsCompleted") != counted:
        errors.append(
            "sprint-state customer completed count does not match the session manifest"
        )
    canonical_state = copy.deepcopy(state)
    sync_customer_testing_from_manifest(canonical_state, manifest)
    canonical_customer = canonical_state.get("customerTesting", {})
    for count_name in (
        "sessionsInvited",
        "sessionsAttempted",
        "sessionsCompleted",
        "sessionsQualified",
        "sessionsExcluded",
        "sessionsUsable",
    ):
        if customer.get(count_name) != canonical_customer.get(count_name):
            errors.append(
                f"sprint-state customer {count_name} does not match the session manifest"
            )
    if customer.get("status") != canonical_customer.get("status"):
        errors.append(
            "sprint-state customer status does not match the session manifest lifecycle"
        )
    synthesis = manifest["synthesis"]
    if (
        "12-synthesis" in state.get("completedSteps", [])
        and synthesis["status"] != "packet-generated"
    ):
        errors.append("Completed synthesis requires a current synthesis packet")
    if synthesis["status"] == "packet-generated":
        if not synthesis["sessionIds"]:
            errors.append("Generated synthesis packet has no session IDs")
        selected_entries = {
            item["sessionId"]: item for item in entries if item["sessionId"] in synthesis["sessionIds"]
        }
        if set(selected_entries) != set(synthesis["sessionIds"]):
            errors.append("Synthesis packet references an unknown session")
        hash_session_ids = [item["sessionId"] for item in synthesis["summaryHashes"]]
        if len(hash_session_ids) != len(set(hash_session_ids)):
            errors.append("Synthesis packet contains duplicate summary hashes")
        if set(hash_session_ids) != set(synthesis["sessionIds"]):
            errors.append("Synthesis summary hashes do not match the selected sessions")
        for item in selected_entries.values():
            if (
                not item["counted"]
                or not item["usable"]
                or item["status"] != "complete"
            ):
                errors.append(
                    f"Synthesis packet references non-usable session {item['sessionId']}"
                )
            if item["questionsVersion"] != synthesis["questionsVersion"]:
                errors.append(
                    f"Synthesis packet mixes questions versions at {item['sessionId']}"
                )
        for summary_hash in synthesis["summaryHashes"]:
            selected_entry = selected_entries.get(summary_hash["sessionId"])
            if (
                selected_entry is not None
                and summary_hash["path"] != selected_entry["summaryPath"]
            ):
                errors.append(
                    f"Synthesis summary hash path does not match session {summary_hash['sessionId']}"
                )
            try:
                summary_path = workspace_relative_file(
                    workspace, summary_hash["path"], "Synthesis summary hash"
                )
                if sha256_bytes(summary_path.read_bytes()) != summary_hash["sha256"]:
                    errors.append(
                        f"Synthesis packet is stale for session {summary_hash['sessionId']}"
                    )
            except (SprintError, OSError) as error:
                errors.append(str(error))
        try:
            expected_synthesis_path = (
                workspace / CUSTOMER_TESTING_DIR / "synthesis" / "synthesis-packet.md"
            ).relative_to(workspace).as_posix()
            if synthesis["packetPath"] != expected_synthesis_path:
                errors.append("Synthesis packet is outside its canonical directory")
            packet_path = workspace_relative_file(
                workspace, synthesis["packetPath"], "Synthesis packet"
            )
            packet_text = packet_path.read_text(encoding="utf-8")
            if sha256_text(packet_text) != synthesis["packetSha256"]:
                errors.append("Synthesis packet hash is stale")
            if len(packet_text) != synthesis["characters"]:
                errors.append("Synthesis packet character count is stale")
            if len(packet_text) > manifest["contextBudget"]["synthesisMaximum"]:
                errors.append("Synthesis packet exceeds its context budget")
            for reference in raw_references:
                if reference in packet_text:
                    errors.append("Synthesis packet includes a raw-evidence reference")
        except (SprintError, OSError, UnicodeDecodeError) as error:
            errors.append(str(error))
    return errors


def synthesis_artifact_trace_errors(
    workspace: Path, data: dict[str, Any]
) -> list[str]:
    if data.get("id") != "12-synthesis" or data.get("status") != "complete":
        return []
    try:
        manifest = load_session_manifest(workspace)
    except SprintError as error:
        return [str(error)]
    synthesis = manifest["synthesis"]
    if synthesis["status"] != "packet-generated":
        return ["Completed synthesis artifact requires a current synthesis packet"]
    allowed_trace_ids: set[str] = set()
    for session_id in synthesis["sessionIds"]:
        entry = find_session_entry(manifest, session_id)
        try:
            summary_path = workspace_relative_file(
                workspace, entry["summaryPath"], "Synthesis trace summary"
            )
            summary = load_session_summary(summary_path)
        except SprintError as error:
            return [str(error)]
        allowed_trace_ids.update(
            f"{session_id}/{item['id']}" for item in summary["observations"]
        )
        allowed_trace_ids.update(
            f"{session_id}/{item['id']}" for item in summary["inferences"]
        )
        allowed_trace_ids.update(
            f"{session_id}/{item['id']}" for item in summary["quoteReferences"]
        )
        allowed_trace_ids.update(
            f"{session_id}/{item['questionId']}"
            for item in summary["questionEvidence"]
        )
    evidence = data.get("evidence", [])
    if not evidence:
        return [
            "Completed synthesis artifact requires a traceable evidence entry for every synthesized claim"
        ]
    errors: list[str] = []
    trace_pattern = re.compile(r"\bS[0-9][A-Z0-9-]{0,30}/[A-Za-z0-9][A-Za-z0-9._-]*\b")
    for index, item in enumerate(evidence, 1):
        source = str(item.get("source", ""))
        trace_ids = set(trace_pattern.findall(source))
        if not trace_ids:
            errors.append(
                f"Synthesis evidence entry {index} has no session/evidence trace ID"
            )
            continue
        unknown = sorted(trace_ids - allowed_trace_ids)
        if unknown:
            errors.append(
                f"Synthesis evidence entry {index} has unknown trace IDs: {', '.join(unknown)}"
            )
    return errors


def prototype_record_errors(
    workspace: Path, data: dict[str, Any]
) -> list[str]:
    if data.get("id") != PROTOTYPE_BRIEF_ID:
        return []
    brief = data.get("prototypeBrief")
    if not isinstance(brief, dict):
        return ["Structured prototype/MVP brief is missing"]
    errors: list[str] = []
    for packet in brief.get("buildPackets", []):
        try:
            path = workspace_relative_file(
                workspace, packet["path"], "Immutable AI build packet"
            )
            if sha256_bytes(path.read_bytes()) != packet["sha256"]:
                errors.append(
                    f"AI build packet changed after recording: {packet['path']}"
                )
        except SprintError as error:
            errors.append(str(error))
        for asset in packet.get("assets", []):
            descriptor_error = validate_file_descriptor(
                workspace, asset, f"Approved build asset {asset.get('path')}"
            )
            if descriptor_error:
                errors.append(descriptor_error)
    for trial in brief.get("trialRuns", []):
        for key in ("interviewScript", "testedArtifact"):
            descriptor_error = validate_file_descriptor(
                workspace,
                trial[key],
                f"Trial {trial['id']} {key}",
            )
            if descriptor_error:
                errors.append(descriptor_error)
    for summary in brief.get("versions", []):
        try:
            record_path = workspace_relative_file(
                workspace,
                summary["recordPath"],
                f"Tested version {summary['version']}",
            )
            payload = record_path.read_bytes()
            if sha256_bytes(payload) != summary["recordSha256"]:
                errors.append(
                    f"Tested version {summary['version']} immutable record changed after freeze"
                )
                continue
            record = load_tested_version(record_path)
        except SprintError as error:
            errors.append(str(error))
            continue
        if record["version"] != summary["version"]:
            errors.append(
                f"Tested version summary {summary['version']} points to a different version record"
            )
        if record["prototypeArtifact"]["path"] != summary["prototypePath"]:
            errors.append(
                f"Tested version {summary['version']} summary points to a different prototype"
            )
        if record["trialRun"]["id"] != summary["trialRunId"]:
            errors.append(
                f"Tested version {summary['version']} summary points to a different trial"
            )
        if record["deployment"]["url"] != summary["deploymentUrl"]:
            errors.append(
                f"Tested version {summary['version']} summary points to a different deployment URL"
            )
        if record["frozenAt"] != summary["frozenAt"]:
            errors.append(
                f"Tested version {summary['version']} summary has a different freeze timestamp"
            )
        snapshot_digest = sha256_bytes(
            json_text(record["approvedBrief"]["snapshot"]).encode("utf-8")
        )
        if snapshot_digest != record["approvedBrief"]["sha256"]:
            errors.append(
                f"Tested version {summary['version']} approved-brief digest is invalid"
            )
        for key, descriptor in (
            ("prototypeArtifact", record["prototypeArtifact"]),
            ("prototypeContext", record["prototypeContext"]),
            ("buildPacket", record["buildPacket"]),
            ("trial interview script", record["trialRun"]["interviewScript"]),
            ("trial tested artifact", record["trialRun"]["testedArtifact"]),
            *record["linkedArtifacts"].items(),
        ):
            descriptor_error = validate_file_descriptor(
                workspace,
                descriptor,
                f"Tested version {summary['version']} {key}",
            )
            if descriptor_error:
                errors.append(descriptor_error)
    return errors


def workspace_errors(workspace: Path) -> list[str]:
    errors: list[str] = []
    try:
        state = read_json(state_path(workspace))
    except SprintError as error:
        return [str(error)]
    state_schema_errors = formatted_schema_errors(
        state, "workspace-state", state_path(workspace)
    )
    errors.extend(state_schema_errors)
    state_is_valid = not state_schema_errors
    workspace_json_is_valid = state_is_valid
    if state_is_valid:
        errors.extend(validate_state(state))
    manifest: dict[str, Any] | None = None
    manifest_path = assignment_manifest_path(workspace)
    try:
        manifest = read_json(manifest_path)
    except SprintError as error:
        errors.append(str(error))
        workspace_json_is_valid = False
    if manifest is not None:
        manifest_schema_errors = formatted_schema_errors(
            manifest, "assignment-manifest", manifest_path
        )
        errors.extend(manifest_schema_errors)
        if manifest_schema_errors:
            workspace_json_is_valid = False
        elif state_is_valid:
            manifest_content_errors = assignment_manifest_errors(
                workspace, manifest, state
            )
            errors.extend(
                f"{manifest_path}: {item}" for item in manifest_content_errors
            )
            if manifest_content_errors:
                workspace_json_is_valid = False
            for step_id in state.get("completedSteps", []):
                step_assignment_errors = required_assignment_errors(
                    manifest, step_id
                )
                errors.extend(
                    f"Completed step {step_id}: {item}"
                    for item in step_assignment_errors
                )
                if step_assignment_errors:
                    workspace_json_is_valid = False
    if state_is_valid:
        errors.extend(customer_testing_record_errors(workspace, state))
    try:
        specs = load_artifact_specs()
    except SprintError as error:
        return [*errors, str(error)]
    try:
        load_step_guidance()
    except SprintError as error:
        return [*errors, str(error)]
    registrations = (
        {item["id"]: item for item in state["artifacts"]} if state_is_valid else {}
    )
    artifact_documents: dict[str, dict[str, Any]] = {}
    artifact_document_pairs: list[tuple[Path, dict[str, Any]]] = []
    for data_path in sorted((workspace / "artifact-data").glob("*.json")):
        try:
            data = read_json(data_path)
        except SprintError as error:
            errors.append(str(error))
            workspace_json_is_valid = False
            continue
        data_schema_errors = formatted_schema_errors(data, "artifact-data", data_path)
        errors.extend(data_schema_errors)
        if data_schema_errors:
            workspace_json_is_valid = False
            continue
        content_errors = artifact_data_errors(data, specs)
        errors.extend(f"{data_path}: {item}" for item in content_errors)
        if content_errors:
            workspace_json_is_valid = False
        evidence_errors = evidence_claim_errors(data, state)
        errors.extend(f"{data_path}: {item}" for item in evidence_errors)
        if evidence_errors:
            workspace_json_is_valid = False
        trace_errors = synthesis_artifact_trace_errors(workspace, data)
        errors.extend(f"{data_path}: {item}" for item in trace_errors)
        if trace_errors:
            workspace_json_is_valid = False
        prototype_errors = prototype_record_errors(workspace, data)
        errors.extend(f"{data_path}: {item}" for item in prototype_errors)
        if prototype_errors:
            workspace_json_is_valid = False
        artifact_id = data["id"]
        artifact_documents[artifact_id] = data
        artifact_document_pairs.append((data_path, data))
        if artifact_id in specs:
            output = workspace / "artifacts" / specs[artifact_id]["filename"]
            if not output.exists():
                errors.append(f"Missing rendered artifact: {output}")
            if artifact_id not in registrations:
                errors.append(f"Artifact is not registered in state: {artifact_id}")
    if state_is_valid:
        errors.extend(
            artifact_workflow_errors(state, specs, artifact_documents)
        )
        try:
            assessment = build_completion_assessment(
                workspace, state, artifact_document_pairs
            )
            for data_path, data in artifact_document_pairs:
                finding_errors = material_finding_errors(
                    workspace, data, assessment
                )
                errors.extend(f"{data_path}: {item}" for item in finding_errors)
                if finding_errors:
                    workspace_json_is_valid = False
        except SprintError as error:
            errors.append(str(error))
            workspace_json_is_valid = False
    if state_is_valid and "10-prototype" in state["completedSteps"]:
        brief_data = artifact_documents.get(PROTOTYPE_BRIEF_ID, {})
        brief = brief_data.get("prototypeBrief", {})
        current_version = brief.get("currentVersion") if isinstance(brief, dict) else None
        if not current_version:
            errors.append(
                "Completed prototype step is missing a frozen, trial-passed tested version"
            )
    if (
        state_is_valid
        and state.get("executionMode") == "live"
        and "03-evidence" in state.get("completedSteps", [])
    ):
        recruitment_data = artifact_documents.get(TEST_PLAN_ID, {})
        readiness_errors = recruitment_plan_errors(
            recruitment_data.get("recruitmentPlan"),
            require_ready=True,
            state=state,
        )
        errors.extend(
            f"Completed evidence step: {item}" for item in readiness_errors
        )
    site_manifest_path = workspace / SITE_MANIFEST_FILENAME
    if not site_manifest_path.exists():
        errors.append(f"Missing generated site manifest: {site_manifest_path}")
    else:
        try:
            site_manifest = read_json(site_manifest_path)
            errors.extend(site_crawl_errors(workspace, site_manifest))
        except SprintError as error:
            errors.append(str(error))
    if workspace_json_is_valid:
        try:
            errors.extend(rendered_output_errors(workspace))
        except SprintError as error:
            message = str(error)
            if not any(message in existing for existing in errors):
                errors.append(message)
    return errors


def add_evidence_count_dimensions(state: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(state)
    customer = migrated.setdefault("customerTesting", {})
    completed = int(customer.get("sessionsCompleted", 0))
    customer.setdefault("sessionsInvited", completed)
    customer.setdefault("sessionsAttempted", completed)
    customer.setdefault("sessionsQualified", 0)
    customer.setdefault("sessionsExcluded", 0)
    customer.setdefault("sessionsUsable", 0)
    if customer.get("status") == "complete" and completed:
        customer["status"] = "partial"
    migrated["schemaVersion"] = STATE_SCHEMA_VERSION
    return migrated


def migrate_workspace_state_v1_to_v4(data: dict[str, Any]) -> dict[str, Any]:
    """Add fidelity, terminal truth, skip audit, and evidence dimensions."""

    return add_evidence_count_dimensions(migrate_legacy_state(data))


def add_terminal_state_dimensions(data: dict[str, Any]) -> dict[str, Any]:
    """Add the schema-3 terminal classification and auditable skip records."""

    migrated = copy.deepcopy(data)
    fallback_timestamp = str(
        migrated.get("updatedAt") or migrated.get("createdAt") or utc_now()
    )
    records = []
    for step_id in migrated.get("skippedSteps", []):
        recorded_at = fallback_timestamp
        deviations = (
            migrated.get("fidelity", {})
            .get("steps", {})
            .get(step_id, {})
            .get("deviations", [])
        )
        for deviation in reversed(deviations):
            if isinstance(deviation, dict) and deviation.get("type") in {
                "skip",
                "omission",
            }:
                recorded_at = str(deviation.get("recordedAt") or recorded_at)
                break
        records.append(
            {
                "step": step_id,
                "skippedBy": "pre-3.0 actor unavailable",
                "reason": migrated.get("skipReasons", {}).get(
                    step_id, "Pre-3.0 skip reason unavailable."
                ),
                "executionMode": migrated.get("executionMode", "live"),
                "route": migrated.get("route", "undecided"),
                "skippedAt": recorded_at,
            }
        )
    migrated["skipRecords"] = records
    if any(
        isinstance(item, dict) and "id" not in item
        for item in migrated.get("decisions", [])
    ):
        migrate_legacy_decisions(migrated, fallback_timestamp)
    migrated["terminalState"] = expected_terminal_state(migrated)
    return migrated


def migrate_workspace_state_v2_to_v4(data: dict[str, Any]) -> dict[str, Any]:
    """Add terminal truth and independently counted evidence dimensions."""

    return add_evidence_count_dimensions(add_terminal_state_dimensions(data))


def migrate_workspace_state_v3_to_v4(data: dict[str, Any]) -> dict[str, Any]:
    """Preserve schema-3 terminal truth while adding evidence dimensions."""

    return add_evidence_count_dimensions(data)


def migrate_artifact_data_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    """Add explicit material-findings and outcome-boundary containers."""

    migrated = copy.deepcopy(data)
    migrated["schemaVersion"] = ARTIFACT_SCHEMA_VERSION
    for section in migrated.get("sections", []):
        if isinstance(section, dict) and section.get("title") == "Confidence":
            section["title"] = "Evidence strength"
    migrated.setdefault("materialFindings", [])
    for finding in migrated["materialFindings"]:
        if isinstance(finding, dict):
            finding.setdefault("outliers", [])
    if migrated.get("id") == "13-outcome":
        migrated.setdefault(
            "outcomeAssessment",
            {
                "processCompleted": "Legacy outcome; process completion requires review.",
                "methodAdaptations": "Legacy outcome; method adaptations require review.",
                "evidenceSupports": "Legacy outcome; supported claims require review.",
                "evidenceCannotSupport": "Statistical confidence, representativeness, and prevalence were not established.",
                "justifiedDecision": "Investigate the legacy evidence before relying on this outcome.",
                "decisionImpact": "investigate-or-retest",
                "smallestNextLearningAction": "Reassess the legacy session records and add traceable material findings.",
            },
        )
    return migrated


def migrate_session_manifest_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(data)
    migrated["schemaVersion"] = SESSION_MANIFEST_SCHEMA_VERSION
    for entry in migrated.get("sessions", []):
        completed = entry.get("counted") is True
        entry.setdefault("participantSegment", "Legacy unclassified segment")
        entry.setdefault("participantFit", "unassessed")
        entry.setdefault("protocolFidelity", "not-assessed")
        entry.setdefault("criticalScenariosCovered", [])
        entry.setdefault(
            "attempted",
            completed
            or entry.get("status") in {"in-progress", "reopened", "complete"},
        )
        entry.setdefault("usable", False)
        entry.setdefault(
            "exclusionReason",
            (
                "Legacy completion requires participant-fit, protocol, and scenario reassessment before synthesis."
                if completed
                else ""
            ),
        )
        if completed:
            entry["includeInSynthesis"] = False
    if migrated.get("synthesis", {}).get("status") == "packet-generated":
        migrated["synthesis"]["status"] = "stale"
    return migrated


def migrate_customer_session_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(data)
    migrated["schemaVersion"] = CUSTOMER_SESSION_SCHEMA_VERSION
    completed = migrated.get("status") == "complete"
    migrated.setdefault(
        "participant",
        {
            "segment": "Legacy unclassified segment",
            "fit": "unassessed",
            "fitRationale": "Participant fit was not explicitly assessed in schema 1.0.",
        },
    )
    migrated.setdefault(
        "evidenceQuality",
        {
            "attemptedAt": (
                migrated.get("completedAt")
                if completed
                else (
                    migrated.get("updatedAt")
                    if migrated.get("status") in {"in-progress", "reopened"}
                    else None
                )
            ),
            "protocolFidelity": "not-assessed",
            "criticalScenariosCovered": [],
            "usable": False,
            "exclusionReason": (
                "Legacy completion requires participant-fit, protocol, and scenario reassessment before synthesis."
                if completed
                else ""
            ),
        },
    )
    return migrated


MIGRATIONS = {
    "workspace-state": {
        (LEGACY_STATE_SCHEMA_VERSION, STATE_SCHEMA_VERSION): migrate_workspace_state_v1_to_v4,
        (PREVIOUS_STATE_SCHEMA_VERSION, STATE_SCHEMA_VERSION): migrate_workspace_state_v2_to_v4,
        (INTERMEDIATE_STATE_SCHEMA_VERSION, STATE_SCHEMA_VERSION): migrate_workspace_state_v3_to_v4,
    },
    "artifact-data": {
        (LEGACY_ARTIFACT_SCHEMA_VERSION, ARTIFACT_SCHEMA_VERSION): migrate_artifact_data_to_v3,
        (PREVIOUS_ARTIFACT_SCHEMA_VERSION, ARTIFACT_SCHEMA_VERSION): migrate_artifact_data_to_v3,
    },
    "session-manifest": {
        (LEGACY_SESSION_SCHEMA_VERSION, SESSION_MANIFEST_SCHEMA_VERSION): migrate_session_manifest_v1_to_v2,
    },
    "customer-session": {
        (LEGACY_SESSION_SCHEMA_VERSION, CUSTOMER_SESSION_SCHEMA_VERSION): migrate_customer_session_v1_to_v2,
    },
}


def migration_plan(workspace: Path) -> list[tuple[Path, str, dict[str, Any]]]:
    """Build and validate a complete in-memory migration plan."""

    documents = [(state_path(workspace), "workspace-state")]
    data_dir = workspace / "artifact-data"
    if data_dir.exists():
        documents.extend(
            (path, "artifact-data") for path in sorted(data_dir.glob("*.json"))
        )
    customer_manifest = manifest_path(workspace)
    if customer_manifest.exists():
        documents.append((customer_manifest, "session-manifest"))
    session_root = workspace / CUSTOMER_TESTING_DIR / "sessions"
    if session_root.exists():
        documents.extend(
            (path, "customer-session")
            for path in sorted(session_root.glob("*/session.json"))
        )
    plan: list[tuple[Path, str, dict[str, Any]]] = []
    errors: list[str] = []
    for path, family in documents:
        try:
            data = read_json(path)
        except SprintError as error:
            errors.append(str(error))
            continue
        version = data.get("schemaVersion")
        current = SCHEMA_FAMILIES[family]["current"]
        if version == current:
            current_errors = formatted_schema_errors(data, family, path)
            errors.extend(current_errors)
            if (
                not current_errors
                and family == "workspace-state"
                and any(
                    isinstance(item, dict) and "id" not in item
                    for item in data.get("decisions", [])
                )
            ):
                upgraded = copy.deepcopy(data)
                migrate_legacy_decisions(
                    upgraded,
                    str(upgraded.get("updatedAt") or upgraded.get("createdAt") or utc_now()),
                )
                upgraded_errors = formatted_schema_errors(
                    upgraded, family, path
                )
                if upgraded_errors:
                    errors.extend(
                        f"Decision attestation upgrade error: {item}"
                        for item in upgraded_errors
                    )
                else:
                    plan.append((path, family, upgraded))
            continue
        legacy_errors = formatted_schema_errors(
            data, family, path, accept_legacy=True
        )
        if legacy_errors:
            errors.extend(legacy_errors)
            continue
        migration = MIGRATIONS.get(family, {}).get((version, current))
        if migration is None:
            errors.append(
                f"{path}: $.schemaVersion: no migration path from {version!r} to {current!r}"
            )
            continue
        migrated = migration(data)
        migrated_errors = formatted_schema_errors(migrated, family, path)
        if migrated_errors:
            errors.extend(
                f"Migration output error: {item}" for item in migrated_errors
            )
            continue
        if family == "workspace-state":
            semantic_errors = validate_state(migrated)
            if semantic_errors:
                errors.extend(
                    f"Migration output error: {path}: {item}"
                    for item in semantic_errors
                )
                continue
        plan.append((path, family, migrated))
    assignment_path = assignment_manifest_path(workspace)
    if assignment_path.exists():
        try:
            manifest = read_json(assignment_path)
            errors.extend(
                formatted_schema_errors(
                    manifest, "assignment-manifest", assignment_path
                )
            )
        except SprintError as error:
            errors.append(str(error))
    else:
        try:
            source_state = read_json(state_path(workspace))
            manifest_timestamp = str(
                source_state.get("updatedAt")
                or source_state.get("createdAt")
                or utc_now()
            )
            manifest = empty_assignment_manifest(manifest_timestamp)
            manifest_errors = formatted_schema_errors(
                manifest, "assignment-manifest", assignment_path
            )
            if manifest_errors:
                errors.extend(manifest_errors)
            else:
                plan.append((assignment_path, "assignment-manifest", manifest))
        except SprintError as error:
            errors.append(str(error))
    if not customer_manifest.exists():
        try:
            source_state = read_json(state_path(workspace))
            customer_timestamp = str(
                source_state.get("updatedAt")
                or source_state.get("createdAt")
                or utc_now()
            )
            session_manifest = initial_session_manifest(
                str(source_state.get("slug", "migrated-sprint")),
                customer_timestamp,
            )
            session_manifest_errors = formatted_schema_errors(
                session_manifest, "session-manifest", customer_manifest
            )
            if session_manifest_errors:
                errors.extend(session_manifest_errors)
            else:
                plan.append(
                    (customer_manifest, "session-manifest", session_manifest)
                )
        except SprintError as error:
            errors.append(str(error))
    if errors:
        detail = "\n".join(f"- {item}" for item in errors)
        raise SprintError(f"Workspace cannot be migrated:\n{detail}")
    return plan


def default_backup_path(workspace: Path) -> Path:
    return workspace.parent / f"{workspace.name}.backup-before-schema-{STATE_SCHEMA_VERSION}"


def command_migrate(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    plan = migration_plan(workspace)
    if not plan:
        print(
            f"Workspace already uses state schema version {STATE_SCHEMA_VERSION}; no migration needed"
        )
        return
    print("Migration plan:")
    for path, family, migrated in plan:
        relative = path.relative_to(workspace)
        old_version = (
            read_json(path).get("schemaVersion") if path.exists() else "missing"
        )
        print(
            f"- {relative}: {SCHEMA_FAMILIES[family]['label']} "
            f"{old_version} -> {migrated['schemaVersion']}"
        )
    if args.dry_run:
        print("Dry run complete; no files or backups were written")
        return

    backup = workspace_path(args.backup) if args.backup else default_backup_path(workspace)
    if backup == workspace:
        raise SprintError("Backup path must differ from the workspace")
    try:
        backup.relative_to(workspace)
    except ValueError:
        pass
    else:
        raise SprintError("Backup path must be outside the workspace")
    if backup.exists():
        raise SprintError(f"Backup path already exists; refusing to overwrite it: {backup}")
    try:
        shutil.copytree(workspace, backup)
    except OSError as error:
        raise SprintError(f"Could not create migration backup {backup}: {error}") from error
    write_texts_atomically({path: json_text(migrated) for path, _family, migrated in plan})
    print(f"Untouched backup: {backup}")
    print(f"Migrated or created {len(plan)} canonical JSON file(s)")


EXPORT_TEXT_SUFFIXES = {
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".svg",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
EXPORT_NEVER_PATH_PARTS = {
    ".git",
    "account-evidence",
    "contacts",
    "identities",
    "participant-contacts",
    "participant-data",
    "participant-identities",
    "private-evidence",
    "raw-evidence",
    "recordings",
    "source-evidence",
    "transcripts",
}
SHAREABLE_FORBIDDEN_ROOTS = {
    "artifact-data",
    "customer-testing",
    "working",
}
EXPORT_EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])([A-Z0-9._%+-]+)@([A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])",
    re.IGNORECASE,
)
EXPORT_PHONE_PATTERN = re.compile(r"(?<!\w)\+\d[\d .()\-]{7,}\d(?!\w)")
EXPORT_IDENTIFIER_PATTERN = re.compile(
    r'''(?ix)
    ["']?
    (?:account|customer|org(?:anization)?|project|request|subscription|user|workspace)
    [_-]?(?:id|identifier)?["']?\s*[:=]\s*["']([^"'\r\n]+)["']
    ''',
)
EXPORT_SECRET_PATTERNS = (
    ("OpenAI-style secret key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("GitHub token", re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[A-Z0-9]{16}\b")),
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
)
EXPORT_LOCAL_PATH_PATTERN = re.compile(
    r"(?:file://|/(?:Users|home|private/var|var/folders)/[^\s<>'\"]+|[A-Za-z]:\\(?:Users|Documents)\\[^\s<>'\"]+)",
    re.IGNORECASE,
)


def load_export_approval(path: Path) -> dict[str, Any]:
    approval = read_json(path)
    require_valid_schema(approval, "export-approval", path)
    review = approval["redactionReview"]
    required_checks = ["completed", "secretsChecked", "contactDetailsChecked"]
    if approval["kind"] == "shareable-site":
        required_checks.extend(
            [
                "rawEvidenceChecked",
                "personalInformationChecked",
                "customerConfidentialChecked",
                "assetLicencesChecked",
                "consentAndRightsChecked",
            ]
        )
    missing_checks = [key for key in required_checks if review.get(key) is not True]
    if missing_checks:
        raise SprintError(
            "Export approval has incomplete required review checks: "
            + ", ".join(missing_checks)
        )
    return approval


def export_candidate_errors(root: Path, kind: str) -> list[str]:
    errors: list[str] = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root)
        lower_parts = tuple(part.lower() for part in relative.parts)
        if any(part in EXPORT_NEVER_PATH_PARTS for part in lower_parts):
            errors.append(f"{relative}: prohibited private/contact evidence path")
        if kind == "shareable-site":
            if lower_parts and lower_parts[0] in SHAREABLE_FORBIDDEN_ROOTS:
                errors.append(f"{relative}: private workspace records are not shareable-site files")
            if path.name in {STATE_FILENAME, ASSIGNMENT_MANIFEST_FILENAME, SESSION_MANIFEST_FILENAME}:
                errors.append(f"{relative}: private canonical record is not allowed in a shareable site")
        lower_name = path.name.lower()
        if (
            lower_name == ".env"
            or (lower_name.startswith(".env.") and lower_name != ".env.example")
            or path.suffix.lower() in {".key", ".pem"}
            or "contact-map" in lower_name
            or "identity-map" in lower_name
        ):
            errors.append(f"{relative}: credential or separate contact/identity file is prohibited")
        if path.suffix.lower() not in EXPORT_TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in EXPORT_EMAIL_PATTERN.finditer(line):
                if match.group(2).lower() not in {"example.com", "example.net", "example.org"}:
                    errors.append(
                        f"{relative}:{line_number}: non-example email address requires removal"
                    )
            if EXPORT_PHONE_PATTERN.search(line) or "tel:" in line.lower():
                errors.append(
                    f"{relative}:{line_number}: likely phone/contact detail requires removal"
                )
            for label, pattern in EXPORT_SECRET_PATTERNS:
                if pattern.search(line):
                    errors.append(f"{relative}:{line_number}: likely {label}")
            for match in EXPORT_IDENTIFIER_PATTERN.finditer(line):
                value = match.group(1).strip().lower()
                if not any(
                    marker in value
                    for marker in (
                        "example",
                        "not-collected",
                        "placeholder",
                        "redacted",
                        "removed",
                        "synthetic",
                        "test",
                        "unknown",
                    )
                ):
                    errors.append(
                        f"{relative}:{line_number}: likely private account/customer identifier"
                    )
            if EXPORT_LOCAL_PATH_PATTERN.search(line):
                errors.append(
                    f"{relative}:{line_number}: absolute local filesystem reference is not portable"
                )
    return errors


def copy_export_file(source: Path, destination: Path, source_root: Path) -> None:
    if source.is_symlink():
        raise SprintError(f"Export refuses symbolic links: {source}")
    resolved = source.resolve()
    try:
        resolved.relative_to(source_root.resolve())
    except ValueError as error:
        raise SprintError(f"Export source escapes the workspace: {source}") from error
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    try:
        destination.chmod(PORTABLE_FILE_MODE)
    except OSError as error:
        raise SprintError(f"Could not set portable export permissions on {destination}: {error}") from error


def copy_export_tree(
    workspace: Path,
    stage: Path,
    relative_root: str,
    *,
    exclude: set[str] | None = None,
) -> None:
    source_root = workspace / relative_root
    if not source_root.exists():
        return
    excluded = exclude or set()
    for source in sorted(candidate for candidate in source_root.rglob("*") if candidate.is_file()):
        relative = source.relative_to(workspace)
        if any(part in excluded for part in relative.parts):
            continue
        copy_export_file(source, stage / relative, workspace)


def copy_shareable_prototype(
    workspace: Path, stage: Path, site_manifest: dict[str, Any]
) -> None:
    page = next(
        (item for item in site_manifest["pages"] if item["type"] == "prototype-launch"),
        None,
    )
    if page is None:
        return
    prototype = page["prototype"]
    artifact_path = workspace_relative_file(
        workspace, prototype["artifactPath"], "Shareable prototype artifact"
    )
    version_root = workspace / "prototype" / prototype["version"]
    try:
        artifact_path.relative_to(version_root)
    except ValueError as error:
        raise SprintError(
            "The shareable prototype is outside its immutable version directory"
        ) from error
    record = load_tested_version(
        workspace_relative_file(
            workspace,
            f"prototype/{prototype['version']}/tested-version.json",
            "Shareable tested-version record",
        )
    )
    context_path = Path(record["prototypeContext"]["path"])
    for source in sorted(candidate for candidate in version_root.rglob("*") if candidate.is_file()):
        relative = source.relative_to(workspace)
        relative_to_version = source.relative_to(version_root)
        if (
            relative_to_version.parts
            and relative_to_version.parts[0] == "sources"
        ):
            continue
        if relative.as_posix() == context_path.as_posix():
            continue
        if source.name == "tested-version.json":
            continue
        copy_export_file(source, stage / relative, workspace)
    if not (stage / prototype["artifactPath"]).exists():
        raise SprintError("The packaged shareable prototype is missing its tested artifact")


def export_assets(stage: Path, site_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    page_paths = {page["path"] for page in site_manifest["pages"]}
    assets = []
    for path in sorted(candidate for candidate in stage.rglob("*") if candidate.is_file()):
        relative = path.relative_to(stage).as_posix()
        if relative == SITE_MANIFEST_FILENAME or relative in page_paths:
            continue
        payload = path.read_bytes()
        assets.append(
            {
                "path": relative,
                "sha256": sha256_bytes(payload),
                "bytes": len(payload),
            }
        )
    return assets


def write_deterministic_zip(source: Path, destination: Path, timestamp: str) -> None:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    year = max(1980, parsed.year)
    temp_destination = destination.with_name(f".{destination.name}.preparing")
    try:
        with zipfile.ZipFile(temp_destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(candidate for candidate in source.rglob("*") if candidate.is_file()):
                relative = path.relative_to(source).as_posix()
                info = zipfile.ZipInfo(
                    relative,
                    (year, parsed.month, parsed.day, parsed.hour, parsed.minute, parsed.second),
                )
                info.create_system = 3
                info.external_attr = PORTABLE_FILE_MODE << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
        os.replace(temp_destination, destination)
    except (OSError, zipfile.BadZipFile) as error:
        temp_destination.unlink(missing_ok=True)
        raise SprintError(f"Could not create ZIP archive {destination}: {error}") from error


def command_export(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    approval_path = Path(args.approval).expanduser().resolve()
    approval = load_export_approval(approval_path)
    workspace_validation = workspace_errors(workspace)
    if workspace_validation:
        raise SprintError(
            "The source workspace must validate before export:\n"
            + "\n".join(f"- {item}" for item in workspace_validation)
        )
    state, specs, artifact_documents = load_workspace_documents(workspace)
    created_artifacts = {str(data["id"]): data for _path, data in artifact_documents}
    customer_manifest = load_session_manifest(workspace)
    session_entries = {
        str(item["sessionId"]): item for item in customer_manifest["sessions"]
    }
    known_sessions = set(session_entries)
    unknown_artifacts = sorted(set(approval["artifactIds"]) - set(created_artifacts))
    unknown_sessions = sorted(set(approval["sessionIds"]) - known_sessions)
    if unknown_artifacts:
        raise SprintError(
            "Export approval references artifacts that do not exist: "
            + ", ".join(unknown_artifacts)
        )
    if unknown_sessions:
        raise SprintError(
            "Export approval references sessions that do not exist: "
            + ", ".join(unknown_sessions)
        )
    if approval["kind"] == "shareable-site":
        incomplete = sorted(
            artifact_id
            for artifact_id in approval["artifactIds"]
            if created_artifacts[artifact_id].get("status") != "complete"
        )
        if incomplete:
            raise SprintError(
                "Shareable-site artifacts require complete status: "
                + ", ".join(incomplete)
            )
        incomplete_sessions: list[str] = []
        for session_id in approval["sessionIds"]:
            entry = session_entries[session_id]
            summary = load_session_summary(
                workspace_relative_file(
                    workspace,
                    entry["summaryPath"],
                    f"Shareable session {session_id} summary",
                )
            )
            if (
                summary.get("status") != "complete"
                or summary.get("anonymized") is not True
                or summary.get("containsDirectIdentifiers") is not False
            ):
                incomplete_sessions.append(session_id)
        if incomplete_sessions:
            raise SprintError(
                "Shareable-site sessions require complete anonymized summaries "
                "without direct identifiers: "
                + ", ".join(sorted(incomplete_sessions))
            )
    approval_digest = sha256_bytes(approval_path.read_bytes())
    is_shareable = approval["kind"] == "shareable-site"
    export_metadata = {
        "kind": approval["kind"],
        "approvedBy": approval["approvedBy"],
        "approvedAt": approval["approvedAt"],
        "approvalDigest": approval_digest,
        "selection": {
            "artifactIds": (
                list(approval["artifactIds"])
                if is_shareable
                else sorted(created_artifacts)
            ),
            "sessionIds": (
                list(approval["sessionIds"])
                if is_shareable
                else sorted(known_sessions)
            ),
            "includePrototype": bool(approval["includePrototype"]),
            "includeCanonicalData": bool(approval["includeCanonicalData"]),
            "includeWorkingMaterial": bool(approval["includeWorkingMaterial"]),
            "includeCustomerTesting": bool(approval["includeCustomerTesting"]),
            "zipRequested": bool(args.zip),
        },
        "humanPublicationRequired": True,
        "published": False,
    }
    plan = build_render_plan(
        workspace,
        visibility="shareable" if is_shareable else "private",
        artifact_ids=set(approval["artifactIds"]) if is_shareable else None,
        session_ids=set(approval["sessionIds"]) if is_shareable else None,
        include_prototype=bool(approval["includePrototype"]),
        export_metadata=export_metadata,
    )
    output = Path(args.output).expanduser().resolve()
    try:
        output.relative_to(workspace.resolve())
    except ValueError:
        pass
    else:
        raise SprintError("Export output must be outside the private source workspace")
    if output.exists():
        raise SprintError(f"Export output already exists; refusing to overwrite it: {output}")
    zip_path = output.parent / f"{output.name}.zip"
    if args.zip and zip_path.exists():
        raise SprintError(f"ZIP output already exists; refusing to overwrite it: {zip_path}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-preparing-", dir=output.parent))
    published = False
    try:
        for source_path, text in plan.generated_files.items():
            relative = source_path.relative_to(workspace)
            if relative.as_posix() == SITE_MANIFEST_FILENAME:
                continue
            write_text(stage / relative, text)
        if is_shareable:
            if approval["includePrototype"]:
                copy_shareable_prototype(workspace, stage, plan.site_manifest)
        else:
            copy_export_file(workspace / ".gitignore", stage / ".gitignore", workspace)
            if approval["includeCanonicalData"]:
                for relative in (STATE_FILENAME, ASSIGNMENT_MANIFEST_FILENAME):
                    copy_export_file(workspace / relative, stage / relative, workspace)
                copy_export_tree(workspace, stage, "artifact-data")
            if approval["includeWorkingMaterial"]:
                copy_export_tree(workspace, stage, "working")
            if approval["includeCustomerTesting"]:
                copy_export_tree(workspace, stage, CUSTOMER_TESTING_DIR)
            if approval["includePrototype"]:
                copy_export_tree(workspace, stage, "prototype")

        plan.site_manifest["assets"] = export_assets(stage, plan.site_manifest)
        plan.site_manifest["site"]["versionDigest"] = sha256_bytes(
            json_text(
                {
                    "pages": [
                        {
                            "id": page["id"],
                            "contentDigest": page["contentDigest"],
                            "renderDigest": page["renderDigest"],
                        }
                        for page in plan.site_manifest["pages"]
                    ],
                    "assets": plan.site_manifest["assets"],
                    "export": plan.site_manifest["export"],
                }
            ).encode("utf-8")
        )
        require_valid_schema(
            plan.site_manifest, "site-manifest", stage / SITE_MANIFEST_FILENAME
        )
        write_json(stage / SITE_MANIFEST_FILENAME, plan.site_manifest)
        findings = export_candidate_errors(stage, approval["kind"])
        findings.extend(site_crawl_errors(stage, plan.site_manifest))
        if findings:
            raise SprintError(
                "Export preparation failed privacy, portability, or link checks:\n"
                + "\n".join(f"- {item}" for item in findings)
            )
        os.replace(stage, output)
        if args.zip:
            try:
                write_deterministic_zip(output, zip_path, approval["approvedAt"])
            except SprintError:
                zip_path.unlink(missing_ok=True)
                try:
                    shutil.rmtree(output)
                except OSError as cleanup_error:
                    raise SprintError(
                        "ZIP preparation failed and the new export directory "
                        f"could not be removed: {cleanup_error}"
                    ) from cleanup_error
                raise
        published = True
    finally:
        if not published and stage.exists():
            shutil.rmtree(stage)
    print(f"Prepared {approval['kind']}: {output}")
    if args.zip:
        print(f"Prepared ZIP archive: {zip_path}")
    print("No upload or publication was performed; a human must choose and approve a destination separately.")


def command_render(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    if args.check:
        errors = rendered_output_errors(workspace)
        if errors:
            print("Rendered output is stale:", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            raise SystemExit(1)
        plan = build_render_plan(workspace)
        print(
            f"Rendered output is current ({len(plan.registrations)} artifacts and dashboard)"
        )
        return
    plan = render_workspace(workspace)
    print(f"Rendered {len(plan.registrations)} artifacts and dashboard")


def command_validate(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    errors = workspace_errors(workspace)
    if errors:
        print("Sprint workspace is invalid:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        raise SystemExit(1)
    print("Sprint workspace is valid")


def command_status(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, artifact_documents = load_workspace_documents(workspace)
    manifest = load_assignment_manifest(workspace)
    assessment = build_completion_assessment(
        workspace, state, artifact_documents
    )
    current_guidance = guidance_for_state(state)
    if args.json:
        exported = copy.deepcopy(state)
        exported["completionAssessment"] = assessment
        exported["currentStepGuidance"] = current_guidance
        print(
            json.dumps(
                exported,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return
    print(f"Sprint: {state['title']}")
    print(f"Method profile: {state['methodProfile']}")
    print(f"Execution mode: {state['executionMode']}")
    mode_selection = state.get("executionModeSelection", {})
    print(
        "Mode selection: "
        f"{mode_selection.get('selectedBy', 'unknown')} — "
        f"{mode_selection.get('reason', 'unknown')}"
    )
    print(f"Route: {state['route']}")
    print(
        "Method fidelity: "
        f"{state.get('fidelity', {}).get('summary', {}).get('assessment', 'unknown')}"
    )
    print(f"Process status: {assessment['processStatus']['status']}")
    print(
        "Process steps: "
        + ", ".join(
            f"{display_label(name)} {value}"
            for name, value in assessment["processStatus"]["steps"].items()
        )
    )
    print(
        "Evidence strength: "
        f"{assessment['evidenceStrength']['band']} ({assessment['evidenceStrength']['quality']})"
    )
    print(
        "Decision readiness: "
        f"{assessment['decisionReadiness']['status']} — {assessment['decisionReadiness']['reason']}"
    )
    print(f"Terminal state: {state['terminalState']}")
    validation_label, validation_notice, _validation_class = validation_truth(state)
    print(f"Validation status: {validation_label}")
    print(f"Validation note: {validation_notice}")
    print(f"Current step: {state['currentStep']} — {step_name(str(state['currentStep']))}")
    fidelity_step = (
        state.get("fidelity", {})
        .get("steps", {})
        .get(str(state["currentStep"]), {})
    )
    timebox = fidelity_step.get("timebox", {})
    print(f"Canonical purpose: {fidelity_step.get('canonicalPurpose', 'unknown')}")
    print(f"Default method: {fidelity_step.get('defaultMethod', 'unknown')}")
    print(f"Selected method: {fidelity_step.get('selectedMethod', 'unknown')}")
    print(f"Selected-method rationale: {current_guidance['selectedMethodRationale']}")
    print(
        "Timebox: "
        f"{timebox.get('suggestedMinutes', 'unknown')} minutes suggested, "
        f"{timebox.get('actualMinutes') if timebox.get('actualMinutes') is not None else 'not recorded'} actual"
    )
    print(f"Why it matters: {current_guidance['whyItMatters']}")
    print(f"Need from human: {current_guidance['humanAction']}")
    print(f"AI role: {'; '.join(current_guidance['aiRole'])}")
    print(f"Definition of done: {'; '.join(current_guidance['definitionOfDone'])}")
    print(
        "Deeper guidance actions: "
        + ", ".join(current_guidance["availableActions"])
    )
    print(f"Pending gate: {state.get('pendingGate') or 'none'}")
    assignments = manifest.get("assignments", [])
    returned = sum(
        1
        for item in assignments
        if isinstance(item, dict) and item.get("status") in {"returned", "accepted"}
    )
    print(f"Specialist assignments: {returned}/{len(assignments)} returned or accepted")
    customer = state.get("customerTesting", {})
    counts = assessment["sessionCounts"]
    print(f"Customer testing: {customer.get('status')}")
    print(
        "Session counts: "
        + ", ".join(f"{name} {value}" for name, value in counts.items())
    )
    recruitment = next(
        (
            data.get("recruitmentPlan")
            for _path, data in artifact_documents
            if data.get("id") == TEST_PLAN_ID
        ),
        None,
    )
    if isinstance(recruitment, dict):
        tracking = recruitment["tracking"]
        stalled, smallest_action = recruitment_stall(recruitment)
        print(
            "Recruitment: "
            f"{tracking['status']}, owner {tracking['owner']}, "
            f"deadline {tracking['deadline']}"
        )
        print(f"Recruitment next action: {tracking['nextAction']}")
        if stalled:
            print(f"Recruitment stalled or due: {smallest_action}")
    if assessment["limitations"]:
        print("Automatic limitations:")
        for limitation in assessment["limitations"]:
            print(f"- {limitation}")
    if manifest_path(workspace).exists():
        manifest = load_session_manifest(workspace)
        current_versions = manifest["currentVersions"]
        print(
            "Customer test versions: "
            f"prototype {current_versions['prototype'] or 'not set'}, "
            f"questions {current_versions['questions'] or 'not set'}"
        )
        print(
            "Session manifest: "
            f"{len(manifest['sessions'])} records, "
            f"synthesis {manifest['synthesis']['status']}"
        )
    next_action = state.get("nextAction", {})
    if isinstance(next_action, dict):
        print(f"Next action: {next_action.get('title')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the deterministic workspace layer for Design Sprint for One."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a new sprint workspace")
    init_parser.add_argument("--title", required=True)
    init_parser.add_argument("--challenge", required=True)
    init_parser.add_argument("--output")
    init_parser.add_argument(
        "--method-profile",
        choices=sorted(METHOD_PROFILES),
        default="adaptive-design-sprint",
    )
    init_parser.add_argument(
        "--execution-mode", choices=sorted(EXECUTION_MODES), default="live"
    )
    init_parser.add_argument("--selected-by", required=True)
    init_parser.add_argument("--profile-reason")
    init_parser.add_argument("--mode-reason", required=True)
    init_parser.add_argument(
        "--session-context-maximum",
        type=int,
        default=DEFAULT_SESSION_CONTEXT_MAXIMUM,
        help="Maximum generated participant-packet size in characters",
    )
    init_parser.add_argument(
        "--synthesis-context-maximum",
        type=int,
        default=DEFAULT_SYNTHESIS_CONTEXT_MAXIMUM,
        help="Maximum generated synthesis-packet size in characters",
    )
    init_parser.add_argument(
        "--context-warning-percent",
        type=int,
        default=DEFAULT_CONTEXT_WARNING_PERCENT,
        help="Warn when a generated packet reaches this budget percentage",
    )
    init_parser.set_defaults(handler=command_init)

    artifact_parser = subparsers.add_parser("new-artifact", help="Create an artifact data draft")
    artifact_parser.add_argument("--workspace", required=True)
    artifact_parser.add_argument("--id", required=True)
    artifact_parser.set_defaults(handler=command_new_artifact)

    artifact_status_parser = subparsers.add_parser(
        "artifact-status", help="Update an artifact status and render"
    )
    artifact_status_parser.add_argument("--workspace", required=True)
    artifact_status_parser.add_argument("--id", required=True)
    artifact_status_parser.add_argument("--status", required=True, choices=sorted(ARTIFACT_STATUSES))
    artifact_status_parser.set_defaults(handler=command_set_artifact_status)

    route_parser = subparsers.add_parser("set-route", help="Record the recommended sprint route")
    route_parser.add_argument("--workspace", required=True)
    route_parser.add_argument("--route", required=True, choices=sorted(ROUTES - {"undecided"}))
    route_parser.add_argument("--rationale", required=True)
    route_parser.set_defaults(handler=command_set_route)

    concept_parser = subparsers.add_parser(
        "set-concept", help="Record or materially revise the selected concept"
    )
    concept_parser.add_argument("--workspace", required=True)
    concept_parser.add_argument("--concept", required=True)
    concept_parser.add_argument("--rationale", required=True)
    concept_parser.set_defaults(handler=command_set_concept)

    profile_parser = subparsers.add_parser(
        "set-method-profile", help="Select the canonical method profile"
    )
    profile_parser.add_argument("--workspace", required=True)
    profile_parser.add_argument(
        "--profile", required=True, choices=sorted(METHOD_PROFILES)
    )
    profile_parser.add_argument("--reason", required=True)
    profile_parser.add_argument("--selected-by", default="human Decider")
    profile_parser.set_defaults(handler=command_set_method_profile)

    mode_parser = subparsers.add_parser(
        "set-execution-mode", help="Select live, self-test, or planning/rehearsal mode"
    )
    mode_parser.add_argument("--workspace", required=True)
    mode_parser.add_argument(
        "--mode", required=True, choices=sorted(EXECUTION_MODES)
    )
    mode_parser.add_argument("--reason", required=True)
    mode_parser.add_argument("--selected-by", required=True)
    mode_parser.set_defaults(handler=command_set_execution_mode)

    fidelity_parser = subparsers.add_parser(
        "record-fidelity", help="Record a step method, participants, timebox, and deviation"
    )
    fidelity_parser.add_argument("--workspace", required=True)
    fidelity_parser.add_argument(
        "--step", required=True, choices=[step["id"] for step in STEPS]
    )
    fidelity_parser.add_argument("--selected-method")
    fidelity_parser.add_argument("--human-participant", action="append")
    fidelity_parser.add_argument("--ai-participant", action="append")
    fidelity_parser.add_argument("--actual-minutes", type=int)
    fidelity_parser.add_argument(
        "--deviation-type", choices=sorted(DEVIATION_TYPES)
    )
    fidelity_parser.add_argument("--canonical-method")
    fidelity_parser.add_argument("--preserved-purpose")
    fidelity_parser.add_argument("--reason")
    fidelity_parser.add_argument("--method-impact")
    fidelity_parser.add_argument("--evidence-impact")
    fidelity_parser.add_argument("--decision-impact")
    fidelity_parser.set_defaults(handler=command_record_fidelity)

    challenge_parser = subparsers.add_parser(
        "set-challenge", help="Refine the sprint challenge and brief"
    )
    challenge_parser.add_argument("--workspace", required=True)
    challenge_parser.add_argument("--challenge", required=True)
    challenge_parser.set_defaults(handler=command_set_challenge)

    question_parser = subparsers.add_parser(
        "question", help="Add or resolve an open sprint question"
    )
    question_parser.add_argument("--workspace", required=True)
    question_group = question_parser.add_mutually_exclusive_group(required=True)
    question_group.add_argument("--add")
    question_group.add_argument("--resolve")
    question_parser.set_defaults(handler=command_question)

    complete_parser = subparsers.add_parser("complete-step", help="Complete the current step")
    complete_parser.add_argument("--workspace", required=True)
    complete_parser.add_argument("--step", required=True, choices=[step["id"] for step in STEPS])
    complete_parser.set_defaults(handler=command_complete_step)

    skip_parser = subparsers.add_parser("skip-step", help="Skip an optional current step")
    skip_parser.add_argument("--workspace", required=True)
    skip_parser.add_argument("--step", required=True, choices=[step["id"] for step in STEPS])
    skip_parser.add_argument("--reason", required=True)
    skip_parser.add_argument("--skipped-by", required=True)
    skip_parser.set_defaults(handler=command_skip_step)

    gate_parser = subparsers.add_parser("gate", help="Record a human gate decision")
    gate_parser.add_argument("--workspace", required=True)
    gate_parser.add_argument("--gate", required=True, choices=sorted(GATE_NAMES))
    gate_parser.add_argument("--decision", required=True)
    gate_parser.add_argument("--decider", default="human Decider")
    gate_parser.add_argument(
        "--considered-input",
        action="append",
        default=[],
        help="Safe provenance reference such as artifact:<id> or assignment:<id>",
    )
    gate_parser.add_argument("--concept", help="Selected concept attested at Gate 3")
    gate_parser.add_argument("--rationale")
    gate_parser.add_argument("--reservations")
    gate_parser.set_defaults(handler=command_gate)

    recommendation_parser = subparsers.add_parser(
        "prototype-recommend",
        help="Recommend the smallest test artifact and provider-neutral tool route",
    )
    recommendation_parser.add_argument("--interaction-required", action="store_true")
    recommendation_parser.add_argument("--manual-service", action="store_true")
    recommendation_parser.add_argument("--code-fidelity-required", action="store_true")
    recommendation_parser.add_argument("--real-behavior-required", action="store_true")
    recommendation_parser.add_argument("--real-service-required", action="store_true")
    recommendation_parser.add_argument("--existing-product", action="store_true")
    recommendation_parser.add_argument("--no-external-tools", action="store_true")
    recommendation_parser.set_defaults(handler=command_prototype_recommend)

    prototype_approval_parser = subparsers.add_parser(
        "prototype-approve",
        help="Record a human prototype boundary approval without taking the external action",
    )
    prototype_approval_parser.add_argument("--workspace", required=True)
    prototype_approval_parser.add_argument(
        "--boundary",
        required=True,
        choices=sorted(PROTOTYPE_APPROVAL_BOUNDARIES),
    )
    prototype_approval_parser.add_argument(
        "--status", required=True, choices=["approved", "not-required", "declined"]
    )
    prototype_approval_parser.add_argument("--decider", default="human Decider")
    prototype_approval_parser.add_argument("--rationale", required=True)
    prototype_approval_parser.set_defaults(handler=command_prototype_approve)

    build_packet_parser = subparsers.add_parser(
        "prototype-build-packet",
        help="Generate an immutable AI build packet from only the approved brief and assets",
    )
    build_packet_parser.add_argument("--workspace", required=True)
    build_packet_parser.add_argument("--asset", action="append", default=[])
    build_packet_parser.add_argument("--output")
    build_packet_parser.set_defaults(handler=command_prototype_build_packet)

    trial_parser = subparsers.add_parser(
        "prototype-trial",
        help="Record a moderated trial using the actual customer interview script",
    )
    trial_parser.add_argument("--workspace", required=True)
    trial_parser.add_argument("--trial-id", required=True)
    trial_parser.add_argument("--status", required=True, choices=["passed", "failed"])
    trial_parser.add_argument("--moderator", required=True)
    trial_parser.add_argument("--prototype", required=True)
    trial_parser.add_argument("--interview-script", required=True)
    trial_parser.add_argument("--finding", action="append", default=[])
    trial_parser.add_argument("--issue", action="append", default=[])
    trial_parser.set_defaults(handler=command_prototype_trial)

    freeze_parser = subparsers.add_parser(
        "prototype-freeze",
        help="Freeze a trial-passed prototype/MVP and its deployment record",
    )
    freeze_parser.add_argument("--workspace", required=True)
    freeze_parser.add_argument("--version", required=True)
    freeze_parser.add_argument("--trial-run", required=True)
    freeze_parser.add_argument("--prototype", required=True)
    freeze_parser.add_argument("--prototype-context", required=True)
    freeze_parser.add_argument("--deployment-target", required=True)
    freeze_parser.add_argument(
        "--access-model",
        required=True,
        choices=["private-local", "private-preview", "invite-only", "public"],
    )
    freeze_parser.add_argument("--url")
    freeze_parser.add_argument("--expires-at")
    freeze_parser.add_argument("--cleanup-plan", required=True)
    freeze_parser.add_argument("--rollback-plan", required=True)
    freeze_parser.set_defaults(handler=command_prototype_freeze)

    session_init_parser = subparsers.add_parser(
        "session-init",
        help="Initialize one isolated, versioned customer-session record",
    )
    session_init_parser.add_argument("--workspace", required=True)
    session_init_parser.add_argument("--session-id", required=True)
    session_init_parser.add_argument("--participant-id", required=True)
    session_init_parser.add_argument(
        "--participant-segment",
        required=True,
        help="Stable, non-identifying target-customer segment label",
    )
    session_init_parser.add_argument(
        "--participant-fit",
        choices=sorted(PARTICIPANT_FITS),
        default="unassessed",
    )
    session_init_parser.add_argument(
        "--fit-rationale",
        default="",
        help="Why this participant is qualified or excluded",
    )
    session_init_parser.add_argument(
        "--session-date",
        default=datetime.now(timezone.utc).date().isoformat(),
    )
    session_init_parser.add_argument(
        "--run-mode",
        choices=["human-run", "agent-assisted"],
        default="human-run",
    )
    session_init_parser.add_argument("--prototype-version", required=True)
    session_init_parser.add_argument("--questions-version", required=True)
    session_init_parser.add_argument(
        "--prototype", required=True, help="Prototype file to open during the test"
    )
    session_init_parser.add_argument(
        "--prototype-context", required=True, help="Bounded textual prototype context"
    )
    session_init_parser.add_argument("--interview-guide", required=True)
    session_init_parser.add_argument("--scorecard", required=True)
    session_init_parser.add_argument("--prior-decision", action="append", default=[])
    session_init_parser.add_argument(
        "--activate-versions",
        action="store_true",
        help="Make the supplied prototype and questions versions current for new sessions",
    )
    session_init_parser.add_argument(
        "--consent-status",
        choices=["pending", "granted", "declined", "withdrawn"],
        default="pending",
    )
    session_init_parser.add_argument("--consent-scope")
    session_init_parser.add_argument("--consent-reference")
    session_init_parser.add_argument(
        "--redaction-status",
        choices=["not-reviewed", "in-progress", "complete", "not-required"],
        default="not-reviewed",
    )
    session_init_parser.set_defaults(handler=command_session_init)

    session_packet_parser = subparsers.add_parser(
        "session-packet",
        help="Generate the one bounded fresh-chat handoff packet for a session",
    )
    session_packet_parser.add_argument("--workspace", required=True)
    session_packet_parser.add_argument("--session-id", required=True)
    session_packet_parser.set_defaults(handler=command_session_packet)

    checkpoint_parser = subparsers.add_parser(
        "session-checkpoint",
        help="Persist a resumable customer-session checkpoint without conversation replay",
    )
    checkpoint_parser.add_argument("--workspace", required=True)
    checkpoint_parser.add_argument("--session-id", required=True)
    checkpoint_parser.add_argument(
        "--status",
        required=True,
        choices=["in-progress", "blocked", "withdrawn"],
    )
    checkpoint_parser.add_argument("--phase", required=True)
    checkpoint_parser.add_argument("--next-action", required=True)
    checkpoint_parser.add_argument("--completed-phase", action="append", default=[])
    checkpoint_parser.set_defaults(handler=command_session_checkpoint)

    session_complete_parser = subparsers.add_parser(
        "session-complete",
        help="Validate, complete, and count one isolated customer session",
    )
    session_complete_parser.add_argument("--workspace", required=True)
    session_complete_parser.add_argument("--session-id", required=True)
    session_complete_parser.add_argument(
        "--consent-status",
        choices=["granted", "declined", "withdrawn"],
    )
    session_complete_parser.add_argument("--consent-scope")
    session_complete_parser.add_argument("--consent-reference")
    session_complete_parser.add_argument(
        "--redaction-status", choices=["complete", "not-required"]
    )
    session_complete_parser.add_argument("--removed-category", action="append", default=[])
    session_complete_parser.add_argument("--limitation", action="append", default=[])
    session_complete_parser.add_argument(
        "--protocol-fidelity",
        choices=sorted(PROTOCOL_FIDELITIES - {"not-assessed"}),
    )
    session_complete_parser.add_argument(
        "--critical-scenario",
        action="append",
        default=[],
        help="Critical scenario actually covered; repeat for multiple scenarios",
    )
    usable_group = session_complete_parser.add_mutually_exclusive_group()
    usable_group.add_argument(
        "--usable",
        action="store_true",
        help="Include this completed, qualified session in evidence synthesis",
    )
    usable_group.add_argument(
        "--exclude-from-evidence",
        action="store_true",
        help="Complete the record without treating the session as usable evidence",
    )
    session_complete_parser.add_argument(
        "--exclusion-reason",
        default="",
        help="Required when the completed session is not usable",
    )
    session_complete_parser.add_argument("--usage-input-tokens", type=int)
    session_complete_parser.add_argument("--usage-output-tokens", type=int)
    session_complete_parser.add_argument("--usage-total-tokens", type=int)
    session_complete_parser.add_argument("--usage-requests", type=int)
    session_complete_parser.add_argument("--usage-duration-seconds", type=float)
    session_complete_parser.add_argument("--usage-source", default="runtime-reported")
    session_complete_parser.add_argument("--usage-unavailable-reason")
    session_complete_parser.set_defaults(handler=command_session_complete)

    reopen_parser = subparsers.add_parser(
        "session-reopen",
        help="Reopen a session from persisted state and remove its counted status",
    )
    reopen_parser.add_argument("--workspace", required=True)
    reopen_parser.add_argument("--session-id", required=True)
    reopen_parser.add_argument("--reason", required=True)
    reopen_parser.set_defaults(handler=command_session_reopen)

    synthesis_packet_parser = subparsers.add_parser(
        "synthesis-packet",
        help="Generate a bounded fresh-chat packet from structured summaries only",
    )
    synthesis_packet_parser.add_argument("--workspace", required=True)
    synthesis_packet_parser.add_argument("--session-id", action="append", default=[])
    synthesis_packet_parser.set_defaults(handler=command_synthesis_packet)

    customer_parser = subparsers.add_parser("customer", help="Update customer testing state")
    customer_parser.add_argument("--workspace", required=True)
    customer_parser.add_argument("--status", required=True, choices=sorted(CUSTOMER_STATUSES))
    customer_parser.add_argument("--target", default="")
    customer_parser.add_argument("--planned", type=int, default=0)
    customer_parser.add_argument(
        "--invited",
        type=int,
        help="People invited so far; attempts and later counts remain manifest-derived",
    )
    customer_parser.add_argument("--completed", type=int)
    customer_parser.add_argument("--rationale")
    customer_parser.set_defaults(handler=command_customer)

    recruitment_parser = subparsers.add_parser(
        "recruitment-status",
        help="Update the early recruitment owner, next action, deadline, counts, and milestones",
    )
    recruitment_parser.add_argument("--workspace", required=True)
    recruitment_parser.add_argument(
        "--status", required=True, choices=sorted(RECRUITMENT_STATUSES)
    )
    recruitment_parser.add_argument("--owner", required=True)
    recruitment_parser.add_argument("--next-action", required=True)
    recruitment_parser.add_argument("--deadline", required=True)
    recruitment_parser.add_argument(
        "--complete-milestone",
        action="append",
        default=[],
        choices=sorted(RECRUITMENT_MILESTONES),
    )
    recruitment_parser.add_argument("--candidates-screened", type=int)
    recruitment_parser.add_argument("--sessions-booked", type=int)
    recruitment_parser.add_argument("--backups-booked", type=int)
    recruitment_parser.set_defaults(handler=command_recruitment_status)

    next_parser = subparsers.add_parser("next-action", help="Update dashboard guidance")
    next_parser.add_argument("--workspace", required=True)
    next_parser.add_argument("--title", required=True)
    next_parser.add_argument("--body", required=True)
    next_parser.add_argument("--human-input", required=True)
    next_parser.add_argument("--status", choices=sorted(WORKSPACE_STATUSES))
    next_parser.set_defaults(handler=command_next_action)

    guidance_parser = subparsers.add_parser(
        "guidance", help="Show compact current-step guidance or one deeper-help action"
    )
    guidance_parser.add_argument("--workspace", required=True)
    guidance_parser.add_argument(
        "--step", choices=[step["id"] for step in STEPS]
    )
    guidance_parser.add_argument("--action", choices=sorted(GUIDANCE_ACTIONS))
    guidance_parser.add_argument("--json", action="store_true")
    guidance_parser.set_defaults(handler=command_guidance)

    role_parser = subparsers.add_parser("role-packet", help="Generate a bounded specialist assignment")
    role_parser.add_argument("--workspace", required=True)
    role_parser.add_argument("--role", required=True)
    role_parser.add_argument("--task", required=True)
    role_parser.add_argument("--assignee", required=True, help="Human-safe assignee label")
    role_parser.add_argument("--run-id", required=True, help="Unique execution/run identifier")
    role_parser.add_argument("--assignment-id", help="Stable assignment identifier")
    role_parser.add_argument("--input", action="append", default=[])
    role_parser.add_argument("--output", required=True, help="Packet path below working/")
    role_parser.set_defaults(handler=command_role_packet)

    result_parser = subparsers.add_parser(
        "role-result", help="Register and validate a specialist result memo"
    )
    result_parser.add_argument("--workspace", required=True)
    result_parser.add_argument("--assignment", required=True)
    result_parser.add_argument("--memo", required=True, help="Result path below working/")
    result_parser.add_argument(
        "--include-assignment",
        action="append",
        default=[],
        help="A peer assignment intentionally included in this non-independent result",
    )
    result_parser.set_defaults(handler=command_role_result)

    assignment_status_parser = subparsers.add_parser(
        "assignment-status", help="Advance or review an assignment lifecycle status"
    )
    assignment_status_parser.add_argument("--workspace", required=True)
    assignment_status_parser.add_argument("--assignment", required=True)
    assignment_status_parser.add_argument(
        "--status", required=True, choices=["in-progress", "accepted", "rejected"]
    )
    assignment_status_parser.add_argument("--note")
    assignment_status_parser.set_defaults(handler=command_assignment_status)

    export_parser = subparsers.add_parser(
        "export",
        help="Prepare an approved private archive or privacy-checked shareable static site",
    )
    export_parser.add_argument("--workspace", required=True)
    export_parser.add_argument(
        "--approval",
        required=True,
        help="Strict explicit export-approval JSON file",
    )
    export_parser.add_argument(
        "--output",
        required=True,
        help="New deployment-ready directory outside the private workspace",
    )
    export_parser.add_argument(
        "--zip",
        action="store_true",
        help="Also create a deterministic sibling ZIP archive",
    )
    export_parser.set_defaults(handler=command_export)

    render_parser = subparsers.add_parser("render", help="Render artifacts and dashboard")
    render_parser.add_argument("--workspace", required=True)
    render_parser.add_argument(
        "--check",
        action="store_true",
        help="Fail without writing when rendered views are stale or non-portable",
    )
    render_parser.set_defaults(handler=command_render)

    validate_parser = subparsers.add_parser("validate", help="Validate a sprint workspace")
    validate_parser.add_argument("--workspace", required=True)
    validate_parser.set_defaults(handler=command_validate)

    migrate_parser = subparsers.add_parser(
        "migrate", help="Migrate legacy persisted JSON to the current schema"
    )
    migrate_parser.add_argument("--workspace", required=True)
    migrate_parser.add_argument(
        "--dry-run", action="store_true", help="Validate and print the plan without writing"
    )
    migrate_parser.add_argument(
        "--backup", help="Backup destination outside the workspace (must not exist)"
    )
    migrate_parser.set_defaults(handler=command_migrate)

    status_parser = subparsers.add_parser("status", help="Show sprint status")
    status_parser.add_argument("--workspace", required=True)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(handler=command_status)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.handler(args)
    except SprintError as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()
