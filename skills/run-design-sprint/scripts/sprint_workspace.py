#!/usr/bin/env python3
"""Create, render, advance, and validate a Design Sprint for One workspace."""

from __future__ import annotations

import argparse
import copy
import html
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from schema_validation import SchemaValidator, ValidationIssue, strict_json_loads


SKILL_DIR = Path(__file__).resolve().parent.parent
REFERENCES_DIR = SKILL_DIR / "references"
HTML_KIT_DIR = SKILL_DIR / "assets" / "html-kit"
SCHEMAS_DIR = REFERENCES_DIR / "schemas"

STATE_FILENAME = "sprint-state.json"
SCHEMA_VERSION = "2.0"
LEGACY_SCHEMA_VERSION = "1.0"
REFERENCE_SCHEMA_VERSION = "1.0"
STATE_SCHEMA_VERSION = SCHEMA_VERSION
LEGACY_STATE_SCHEMA_VERSION = LEGACY_SCHEMA_VERSION
ARTIFACT_SCHEMA_VERSION = SCHEMA_VERSION
FIDELITY_SCHEMA_VERSION = "1.0"
PORTABLE_FILE_MODE = 0o644

SCHEMA_FAMILIES = {
    "workspace-state": {
        "label": "workspace state",
        "current": SCHEMA_VERSION,
        "schemas": {
            LEGACY_SCHEMA_VERSION: SCHEMAS_DIR / "workspace-state-v1.schema.json",
            SCHEMA_VERSION: SCHEMAS_DIR / "workspace-state-v2.schema.json",
        },
        "migratable": {LEGACY_SCHEMA_VERSION},
    },
    "artifact-data": {
        "label": "artifact data",
        "current": SCHEMA_VERSION,
        "schemas": {
            LEGACY_SCHEMA_VERSION: SCHEMAS_DIR / "artifact-data-v1.schema.json",
            SCHEMA_VERSION: SCHEMAS_DIR / "artifact-data-v2.schema.json",
        },
        "migratable": {LEGACY_SCHEMA_VERSION},
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

WORKSPACE_GITIGNORE = """# This generated workspace is private by default.
# Keep sensitive source material outside the workspace; these rules are a fallback.
**/account-evidence/
**/participant-data/
**/private-evidence/
**/raw-evidence/
**/recordings/
**/transcripts/
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


class LocalLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag in {"a", "link", "script", "img"}:
            value = attr_map.get("href") or attr_map.get("src")
            if value:
                self.links.append(value)


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


def workspace_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def state_path(workspace: Path) -> Path:
    return workspace / STATE_FILENAME


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
    migrated["compatibility"] = {
        "migratedFromSchemaVersion": LEGACY_STATE_SCHEMA_VERSION,
        "migrationNote": "Legacy state was classified as adaptive/live; review and revise the selectors if that historical assumption is inaccurate.",
        "migratedAt": migration_timestamp,
    }
    refresh_fidelity_summary(migrated)
    return migrated


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
    if route == "no-sprint":
        assessment = "not-applicable"
    elif mode != "live":
        assessment = "self-test-rehearsal"
    elif skipped:
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


def add_skip(state: dict[str, Any], step_id: str, reason: str) -> None:
    completed = set(state.get("completedSteps", []))
    if step_id in completed:
        return
    skipped = state.setdefault("skippedSteps", [])
    if step_id not in skipped:
        skipped.append(step_id)
    state.setdefault("skipReasons", {})[step_id] = reason
    add_skip_deviation(state, step_id, reason)


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
        "draft": "status--unknown",
        "in-review": "status--active",
        "ready-for-decision": "status--decision",
        "blocked": "status--risk",
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
    return (
        '<section class="section" aria-labelledby="method-fidelity-title">'
        '<p class="eyebrow">Method record</p>'
        '<h2 id="method-fidelity-title">Method-fidelity summary</h2>'
        '<div class="three-column">'
        '<div class="metric"><span class="metric__label">Method profile</span>'
        f'<span class="metric__value">{escape(display_label(state.get("methodProfile")))}</span></div>'
        '<div class="metric"><span class="metric__label">Execution mode</span>'
        f'<span class="metric__value">{escape(display_label(state.get("executionMode")))}</span></div>'
        '<div class="metric"><span class="metric__label">Method fidelity</span>'
        f'<span class="metric__value">{escape(assessment)}</span></div>'
        '</div><h3>Adaptations</h3><ul>'
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
            if (
                artifact_id == "11-customer-evidence"
                and item.get("status") == "Observed"
                and re.search(r"\b(?:customers?|participants?|sessions?|interviews?)\b", claim, re.I)
                and not live_evidence_available
                and not negates_customer_claim(claim)
            ):
                errors.append(
                    f"Evidence entry {index} labels a customer claim Observed without a recorded live customer session"
                )
    return errors


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


def render_artifact(
    workspace: Path,
    data: dict[str, Any],
    state: dict[str, Any],
    specs: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    require_valid_schema(
        data,
        "artifact-data",
        workspace / "artifact-data" / f"{data.get('id', 'unknown')}.json",
    )
    errors = artifact_data_errors(data, specs)
    errors.extend(evidence_claim_errors(data, state))
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
    template = (HTML_KIT_DIR / "artifact-template.html").read_text(encoding="utf-8")
    status = str(data.get("status", "draft"))
    rendered = replace_tokens(
        template,
        {
            "ARTIFACT_PURPOSE": escape(spec["purpose"]),
            "ARTIFACT_TITLE": escape(spec["title"]),
            "SPRINT_TITLE": escape(state["title"]),
            "SPRINT_PHASE": escape(spec["phase"]),
            "STATUS_CLASS": class_for_status(status),
            "ARTIFACT_STATUS": escape(status.replace("-", " ").title()),
            "METHOD_PROFILE": escape(display_label(state.get("methodProfile"))),
            "EXECUTION_MODE": escape(display_label(state.get("executionMode"))),
            "SPRINT_ROUTE": escape(display_label(state.get("route"))),
            "UPDATED_ISO": escape(updated_at),
            "UPDATED_DISPLAY": escape(display_date(updated_at)),
            "SUMMARY_HTML": render_paragraphs(data.get("summary", [])),
            "PRIMARY_CONTENT_HTML": primary_content,
            "EVIDENCE_HTML": render_evidence(data.get("evidence", [])),
            "UNKNOWNS_HTML": render_list(data.get("unknowns", [])),
            "NEXT_ACTION_HTML": render_list(data.get("nextActions", []), ordered=True),
            "METHOD_FIDELITY_HTML": (
                render_method_fidelity_section(state)
                if artifact_id == "13-outcome"
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
            detail = "Skipped with a recorded reason"
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
            f'<div><strong>{escape(step["name"])}</strong><p>{detail}</p></div>'
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


def render_decisions(decisions: Any) -> str:
    if not isinstance(decisions, list) or not decisions:
        return '<li class="decision"><div><strong>No decisions yet</strong><p>Human gate decisions will appear here.</p></div></li>'
    output = []
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        output.append(
            '<li class="decision">'
            '<span class="step__marker" aria-hidden="true">✓</span>'
            f'<div><strong>{escape(decision.get("decision", "Decision"))}</strong>'
            f'<p>{escape(GATE_NAMES.get(str(decision.get("gate")), str(decision.get("gate", "Gate"))))}: '
            f'{escape(decision.get("rationale", "No rationale recorded"))}</p></div>'
            '<span class="status status--decision">Decision</span>'
            "</li>"
        )
    return "\n".join(output)


def render_dashboard(
    state: dict[str, Any], artifacts: list[dict[str, Any]]
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
            "SPRINT_CHALLENGE": escape(state.get("challenge", "No challenge recorded")),
            "SPRINT_STATUS": escape(str(state.get("status", "active")).replace("-", " ").title()),
            "SPRINT_ROUTE": escape(str(state.get("route", "undecided")).replace("-", " ").title()),
            "METHOD_PROFILE": escape(display_label(state.get("methodProfile"))),
            "EXECUTION_MODE": escape(display_label(state.get("executionMode"))),
            "METHOD_FIDELITY": escape(
                display_label(fidelity_summary.get("assessment"))
            ),
            "UPDATED_ISO": escape(updated_at),
            "UPDATED_DISPLAY": escape(display_date(updated_at)),
            "PROGRESS_PERCENT": progress,
            "CURRENT_STEP": escape(f"{current}: {step_name(current)}"),
            "COMPLETED_STEPS": completed,
            "SKIPPED_STEPS": len(skipped),
            "NOT_APPLICABLE_STEPS": len(not_applicable),
            "NEXT_ACTION_TITLE": escape(next_action.get("title", "Continue the sprint")),
            "NEXT_ACTION_BODY": escape(next_action.get("body", "Review the current step.")),
            "HUMAN_INPUT_NEEDED": escape(next_action.get("humanInput", "None right now")),
            "SPRINT_STEPS": render_steps(state),
            "TEST_STATUS": escape(str(customer.get("status", "not-planned")).replace("-", " ").title()),
            "SESSIONS_PLANNED": escape(customer.get("sessionsPlanned", 0)),
            "SESSIONS_COMPLETED": escape(customer.get("sessionsCompleted", 0)),
            "EVIDENCE_BOUNDARY": escape(evidence_boundary),
            "FIDELITY_ADAPTATIONS": render_fidelity_adaptations(state),
            "FIDELITY_LIMITATIONS": render_fidelity_limitations(state),
            "CURRENT_FIDELITY_GUIDANCE": render_current_fidelity_guidance(state),
            "ARTIFACT_COUNT": len(artifacts),
            "ARTIFACT_LINKS": render_artifact_links(artifacts),
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


def build_render_plan(workspace: Path) -> RenderPlan:
    source_state = read_json(state_path(workspace))
    state, specs, artifact_documents = load_workspace_documents(workspace)
    registrations: list[dict[str, Any]] = []
    generated_files: dict[Path, str] = {
        workspace / "assets" / "sprint.css": (
            HTML_KIT_DIR / "sprint.css"
        ).read_text(encoding="utf-8")
    }
    data_paths = [path for path, _data in artifact_documents]
    seen_ids: set[str] = set()
    for data_path, data in artifact_documents:
        registration, rendered = render_artifact(workspace, data, state, specs)
        artifact_id = str(registration["id"])
        if artifact_id in seen_ids:
            raise SprintError(f"Duplicate artifact id: {artifact_id}")
        seen_ids.add(artifact_id)
        output_path = workspace / str(registration["path"])
        if output_path in generated_files:
            raise SprintError(f"Duplicate rendered output path: {output_path}")
        generated_files[output_path] = rendered
        registrations.append(registration)
    registrations.sort(key=lambda item: item["id"])
    generated_files[workspace / "index.html"] = render_dashboard(state, registrations)

    normalized_state = dict(state)
    normalized_state["artifacts"] = registrations
    require_valid_schema(normalized_state, "workspace-state", state_path(workspace))
    state_update = normalized_state if source_state != normalized_state else None
    expected_artifact_files = {
        path for path in generated_files if path.parent == workspace / "artifacts"
    }
    rendered_artifact_files = (
        set((workspace / "artifacts").glob("*.html"))
        if (workspace / "artifacts").exists()
        else set()
    )
    return RenderPlan(
        registrations=registrations,
        generated_files=generated_files,
        state_update=state_update,
        stale_files=sorted(rendered_artifact_files - expected_artifact_files),
        canonical_files=[state_path(workspace), *data_paths],
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


def new_artifact_data(
    artifact_id: str, spec: dict[str, Any], timestamp: str | None = None
) -> dict[str, Any]:
    now = timestamp or utc_now()
    return {
        "schemaVersion": ARTIFACT_SCHEMA_VERSION,
        "id": artifact_id,
        "status": "draft",
        "updatedAt": now,
        "summary": ["This artifact is in progress."],
        "sections": [empty_section(title) for title in spec["requiredSections"]],
        "evidence": [],
        "unknowns": [],
        "nextActions": ["Replace draft entries with evidence-backed content."],
    }


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


def command_init(args: argparse.Namespace) -> None:
    title = args.title.strip()
    challenge = args.challenge.strip()
    if not title or not challenge:
        raise SprintError("Both --title and --challenge are required")
    load_artifact_specs()
    now = utc_now()
    method_profile = args.method_profile
    execution_mode = args.execution_mode
    selected_by = args.selected_by.strip()
    if not selected_by:
        raise SprintError("--selected-by cannot be empty")
    combination_errors = profile_mode_route_errors(
        method_profile, execution_mode, "undecided"
    )
    if combination_errors:
        raise SprintError("; ".join(combination_errors))
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
    for directory in ("artifact-data", "artifacts", "assets", "prototype", "working"):
        (output / directory).mkdir(exist_ok=True)
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
            args.mode_reason
            or "Selected when the workspace was initialised.",
        ),
        "fidelity": fidelity,
        "routeHistory": [],
        "status": "waiting-for-human",
        "currentStep": "01-intake",
        "completedSteps": [],
        "skippedSteps": [],
        "notApplicableSteps": [],
        "skipReasons": {},
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
            "sessionsCompleted": 0,
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
    save_artifact_data(
        output / "artifact-data" / "01-sprint-brief.json",
        initial_brief_data(challenge, now),
    )
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
    save_artifact_data(data_path, new_artifact_data(args.id, specs[args.id], now))
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
    previous_route = state.get("route")
    rationale = args.rationale.strip()
    if not rationale:
        raise SprintError("A route transition requires a non-empty rationale")
    transition_errors = route_change_errors(state, args.route)
    if transition_errors:
        raise SprintError("; ".join(transition_errors))
    state.setdefault("routeHistory", []).append(
        route_transition_record(str(previous_route), args.route, rationale)
    )
    apply_route(state, args.route)
    state["routeRationale"] = rationale
    if (
        previous_route == "research-first"
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
    else:
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
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Set sprint route: {args.route}")


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
    if state.get("completedSteps"):
        raise SprintError(
            "Execution mode cannot change after a step is complete; create or restart a workspace so evidence history stays truthful"
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


def recorded_session_errors(
    state: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    customer = state.get("customerTesting", {})
    completed = customer.get("sessionsCompleted", 0)
    if not isinstance(completed, int) or isinstance(completed, bool):
        return errors
    evidence = artifacts.get("11-customer-evidence")
    session_rows: list[Any] = []
    if evidence is not None:
        register = next(
            (
                section
                for section in evidence.get("sections", [])
                if isinstance(section, dict)
                and section.get("title") == "Session register"
            ),
            None,
        )
        if register is None:
            errors.append(
                "Customer evidence is missing the Session register section"
            )
        elif register.get("type") != "table":
            if completed > 0 or evidence.get("status") in {
                "ready-for-decision",
                "complete",
            }:
                errors.append(
                    "Customer evidence Session register must be a table with one row per completed session"
                )
        else:
            session_rows = register.get("rows", [])
            if not isinstance(session_rows, list):
                session_rows = []
    if completed > 0 and evidence is None:
        errors.append(
            "Recorded customer sessions require artifact 11-customer-evidence with a Session register"
        )
        return errors
    if evidence is None:
        return errors
    valid_ids: list[str] = []
    for index, row in enumerate(session_rows):
        if not isinstance(row, list) or not row or not meaningful_text(row[0]):
            errors.append(
                f"Customer evidence Session register row {index + 1} requires a non-empty session ID in its first cell"
            )
            continue
        if not nested_has_content(row[1:]):
            errors.append(
                f"Customer evidence Session register row {index + 1} requires non-empty recorded session evidence"
            )
        valid_ids.append(row[0].strip())
    if len(valid_ids) != len(set(valid_ids)):
        errors.append("Customer evidence Session register IDs must be unique")
    if len(session_rows) != completed:
        errors.append(
            "customerTesting.sessionsCompleted must equal the number of Session "
            f"register rows; state has {completed}, artifact has {len(session_rows)}"
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
    errors.extend(recorded_session_errors(state, artifacts))
    return errors


def command_complete_step(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, artifacts = load_workspace_documents(workspace)
    existing_errors = validate_state(state)
    if existing_errors:
        raise SprintError(
            "Cannot complete a step from an invalid workflow state: "
            + "; ".join(existing_errors)
        )
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
    if step_id == "10-prototype" and not (workspace / "prototype" / "index.html").exists():
        raise SprintError("prototype/index.html must exist before completing 10-prototype")
    if step_id == "11-customer-sessions":
        if state.get("executionMode") != "live":
            raise SprintError(
                "Non-live execution modes cannot complete real-customer sessions; skip the step with an explicit reason and fidelity impact"
            )
        customer = state.get("customerTesting", {})
        if int(customer.get("sessionsCompleted", 0)) < 1:
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
        session_errors = recorded_session_errors(
            state, artifact_documents_by_id(artifacts)
        )
        if session_errors:
            raise SprintError("; ".join(session_errors))
    for artifact_id in required_artifacts_for_step(step_id):
        status = artifact_status(workspace, artifact_id)
        allowed = {"ready-for-decision", "complete"} if step_id in GATE_BY_STEP else {"complete"}
        if status not in allowed:
            raise SprintError(
                f"Artifact {artifact_id} must have status {' or '.join(sorted(allowed))}; found {status or 'missing'}"
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
    if not reason:
        raise SprintError("A skipped step requires a reason")
    policy_error = skip_policy_error(state, step_id)
    if policy_error:
        raise SprintError(policy_error)
    add_skip(state, step_id, reason)
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


def command_gate(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, artifacts = load_workspace_documents(workspace)
    existing_errors = validate_state(state)
    if existing_errors:
        raise SprintError(
            "Cannot close a gate from an invalid workflow state: "
            + "; ".join(existing_errors)
        )
    gate_id = args.gate
    if gate_id not in GATE_NAMES:
        raise SprintError(f"Unknown gate: {gate_id}")
    if state.get("pendingGate") != gate_id:
        raise SprintError(f"Pending gate is {state.get('pendingGate')}; cannot record {gate_id}")
    if gate_id == "gate-1" and state.get("route") == "undecided":
        raise SprintError("Gate 1 requires an approved sprint route")
    decision_text = args.decision.strip()
    rationale = args.rationale.strip()
    if not decision_text or not rationale:
        raise SprintError("A gate decision requires a non-empty decision and rationale")
    artifact_map = artifact_documents_by_id(artifacts)
    readiness_errors = gate_artifact_errors(gate_id, artifact_map)
    if readiness_errors:
        raise SprintError("; ".join(readiness_errors))
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
    decision = {
        "gate": gate_id,
        "decision": decision_text,
        "rationale": rationale,
        "reservations": args.reservations.strip() if args.reservations else "",
        "decidedAt": utc_now(),
    }
    state.setdefault("decisions", []).append(decision)
    for gate in state.get("humanGates", []):
        if gate.get("id") == gate_id:
            gate.update(
                {
                    "status": "complete",
                    "decision": decision["decision"],
                    "rationale": decision["rationale"],
                    "decidedAt": decision["decidedAt"],
                }
            )
    state["pendingGate"] = None
    current = str(state["currentStep"])
    if gate_id == "gate-5":
        state["status"] = "complete"
        state["outcome"] = args.decision.strip()
        state["nextAction"] = {
            "title": f"Sprint complete: {decision_text}",
            "body": "Use the outcome artifact and owned next actions for the handoff.",
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
        session_errors = recorded_session_errors(state, artifact_map)
        if session_errors:
            raise SprintError("; ".join(session_errors))
    transition_errors = validate_state(state)
    if transition_errors:
        raise SprintError(
            f"Closing {gate_id} would create an invalid transition: "
            + "; ".join(transition_errors)
        )
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Recorded {gate_id}: {args.decision.strip()}")


def command_customer(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, artifacts = load_workspace_documents(workspace)
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
    if planned < 0 or completed < 0:
        raise SprintError("Session counts cannot be negative")
    if completed > planned:
        raise SprintError("Completed sessions cannot exceed planned sessions")
    target = args.target.strip()
    if planned and not target:
        raise SprintError("A planned customer session target must name the suitable audience")
    mode = state.get("executionMode")
    if mode != "live" and (
        completed > 0 or planned > 0 or args.status != "not-planned"
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
        "sessionsCompleted": completed,
    }
    if args.status in {"recruiting", "scheduled", "in-progress", "blocked"}:
        state["status"] = "waiting-for-customers" if args.status == "blocked" else state["status"]
    transition_errors = customer_testing_errors(state)
    transition_errors.extend(
        recorded_session_errors(state, artifact_documents_by_id(artifacts))
    )
    if transition_errors:
        raise SprintError("; ".join(transition_errors))
    state_errors = validate_state(state)
    if state_errors:
        raise SprintError(
            "Customer update would create an invalid workflow state: "
            + "; ".join(state_errors)
        )
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Updated customer testing: {args.status}, {completed}/{planned} sessions")


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


def command_role_packet(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    roles = load_role_contracts()
    if args.role not in roles:
        raise SprintError(f"Unknown role: {args.role}")
    contract = roles[args.role]
    inputs = []
    for value in args.input:
        candidate = (workspace / value).resolve()
        try:
            candidate.relative_to(workspace)
        except ValueError as error:
            raise SprintError(f"Input escapes the sprint workspace: {value}") from error
        if not candidate.exists():
            raise SprintError(f"Role input does not exist: {value}")
        inputs.append(value)
    may = "\n".join(f"- {item}" for item in contract["may"])
    must_not = "\n".join(f"- {item}" for item in contract["mustNot"])
    permitted = "\n".join(f"- {item}" for item in inputs) or "- No files; use only the task context"
    fidelity_step = state["fidelity"]["steps"][str(state["currentStep"])]
    packet = f"""# Bounded specialist assignment

Role: {contract['displayName']} (`{args.role}`)
Sprint: {state['title']}
Method profile: {state['methodProfile']}
Execution mode: {state['executionMode']}
Current step: {state['currentStep']} — {step_name(str(state['currentStep']))}
Canonical purpose: {fidelity_step['canonicalPurpose']}
Selected method: {fidelity_step['selectedMethod']}

## Mission

{contract['mission']}

## Permitted inputs

{permitted}

Do not read other sprint files unless the Sprint Orchestrator issues a new assignment.

## Bounded task

{args.task.strip()}

## May

{may}

## Must not

{must_not}
- Edit `index.html`, `sprint-state.json`, canonical files in `artifact-data/`, or generated files in `artifacts/`
- Continue beyond the bounded task after returning the deliverable

## Required return

Deliverable: {contract['deliverable']}

Return exactly these sections:

1. Findings
2. Evidence and provenance
3. Assumptions and inferences
4. Recommendation
5. Risks or disagreements
6. Open questions
7. Stop condition reached: yes or no
"""
    if args.output:
        output = (workspace / args.output).resolve()
        try:
            output.relative_to(workspace / "working")
        except ValueError as error:
            raise SprintError("Role packets may only be written below working/") from error
        write_text(output, packet)
        print(f"Wrote role packet: {output}")
    else:
        print(packet)


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
    if step_id == "12-synthesis" and "11-customer-sessions" in state.get(
        "skippedSteps", []
    ):
        if mode != "live" or (
            customer.get("status") == "blocked"
            and customer.get("sessionsCompleted") == 0
        ):
            return None
    return (
        f"Step {step_id} is required for route {state.get('route')} in "
        f"{mode} mode and cannot be skipped"
    )


def customer_testing_errors(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    customer = state.get("customerTesting", {})
    if not isinstance(customer, dict):
        return ["customerTesting must be an object"]
    status = customer.get("status")
    planned = customer.get("sessionsPlanned")
    completed = customer.get("sessionsCompleted")
    if not isinstance(planned, int) or isinstance(planned, bool):
        errors.append("Customer sessionsPlanned must be an integer")
        return errors
    if not isinstance(completed, int) or isinstance(completed, bool):
        errors.append("Customer sessionsCompleted must be an integer")
        return errors
    if planned < 0 or completed < 0:
        errors.append("Customer session counts cannot be negative")
        return errors
    if completed > planned:
        errors.append("Completed customer sessions cannot exceed planned sessions")
    target = str(customer.get("target", ""))
    rationale = str(customer.get("targetRationale", ""))
    if planned > 0 and not target.strip():
        errors.append("Planned customer sessions require a non-empty target audience")
    if planned > 0 and not rationale.strip():
        errors.append("Planned customer sessions require a non-empty target rationale")

    if status == "not-planned":
        if completed != 0:
            errors.append(
                "Customer status not-planned requires zero completed sessions"
            )
    elif status == "recruiting":
        if planned < 1 or completed != 0:
            errors.append(
                "Customer status recruiting requires planned sessions and zero "
                "completed sessions; use in-progress or partial after a session"
            )
    elif status == "scheduled":
        if planned < 1 or completed != 0:
            errors.append(
                "Customer status scheduled requires planned sessions and zero completed sessions"
            )
    elif status == "in-progress":
        if planned < 2 or not 0 < completed < planned:
            errors.append(
                "Customer status in-progress requires 0 < completed sessions < planned sessions"
            )
    elif status == "complete":
        if planned < 1 or completed != planned:
            errors.append(
                "Customer status complete requires completed sessions to equal a positive planned count"
            )
    elif status == "partial":
        if planned < 2 or not 0 < completed < planned:
            errors.append(
                "Customer status partial requires 0 < completed sessions < planned sessions"
            )
    elif status == "blocked":
        if planned > 0 and completed >= planned:
            errors.append(
                "Customer status blocked requires fewer completed sessions than planned"
            )

    if state.get("executionMode") != "live":
        if status != "not-planned" or planned != 0 or completed != 0:
            errors.append(
                "Non-live execution modes require customer status not-planned and "
                "zero planned/completed sessions"
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
        terminal = (
            state.get("status") == "complete" and current == "13-outcome"
        )
        if not (
            pending_gate == GATE_BY_STEP.get(str(current))
            or waiting_for_reroute
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
        decisions = decisions_by_gate[gate_id]
        if status == "complete":
            if not str(gate.get("decision", "")).strip() or not str(
                gate.get("rationale", "")
            ).strip():
                errors.append(
                    f"{gate_id} complete requires a non-empty decision and rationale"
                )
            if step_id not in completed:
                errors.append(
                    f"{gate_id} cannot close before completed step {step_id}"
                )
            if len(decisions) != 1:
                errors.append(
                    f"{gate_id} complete requires exactly one matching decision record"
                )
            elif gate.get("decision") != decisions[0].get("decision"):
                errors.append(
                    f"{gate_id} decision does not match the decision history"
                )
            elif not str(decisions[0].get("decision", "")).strip() or not str(
                decisions[0].get("rationale", "")
            ).strip():
                errors.append(
                    f"{gate_id} decision history requires a non-empty decision and rationale"
                )
        elif decisions:
            errors.append(
                f"{gate_id} has a decision record but is not complete"
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
        if (
            gates.get(pending_gate, {}).get("status") != "pending"
            or state.get("currentStep") != step_id
            or step_id not in completed
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
        if state.get("outcome") is not None:
            return ["Only a terminal complete workspace may record outcome"]
        return []
    errors: list[str] = []
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
        if outcome not in {"investigate", "stop"}:
            errors.append(
                "A non-live terminal state may close only as Investigate or Stop"
            )
    elif "11-customer-sessions" in skipped:
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
        if (
            "11-customer-sessions" not in completed
            or "12-synthesis" not in completed
        ):
            errors.append(
                "A tested live terminal state requires completed customer sessions and synthesis"
            )
        if customer.get("status") not in {"complete", "partial"}:
            errors.append(
                "A tested live terminal state requires complete or partial customer status"
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
        "currentStep",
        "completedSteps",
        "skippedSteps",
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
    errors.extend(gate_history_errors(state))
    errors.extend(terminal_state_errors(state))
    errors.extend(fidelity_errors(state))
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


def local_link_errors(html_path: Path, workspace: Path) -> list[str]:
    parser = LocalLinkParser()
    parser.feed(html_path.read_text(encoding="utf-8"))
    errors = []
    for link in parser.links:
        if link.startswith(("http://", "https://", "mailto:", "#", "data:")):
            continue
        target_text = link.split("#", 1)[0]
        if not target_text:
            continue
        target = (html_path.parent / target_text).resolve()
        try:
            target.relative_to(workspace)
        except ValueError:
            errors.append(f"{html_path}: local link escapes workspace: {link}")
            continue
        if not target.exists():
            errors.append(f"{html_path}: broken local link: {link}")
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
    try:
        specs = load_artifact_specs()
    except SprintError as error:
        return [*errors, str(error)]
    registrations = (
        {item["id"]: item for item in state["artifacts"]} if state_is_valid else {}
    )
    artifact_documents: dict[str, dict[str, Any]] = {}
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
        artifact_id = data["id"]
        artifact_documents[artifact_id] = data
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
    if state_is_valid and "10-prototype" in state["completedSteps"] and not (workspace / "prototype" / "index.html").exists():
        errors.append("Completed prototype step is missing prototype/index.html")
    html_files = [workspace / "index.html", *sorted((workspace / "artifacts").glob("*.html"))]
    if (workspace / "prototype" / "index.html").exists():
        html_files.append(workspace / "prototype" / "index.html")
    for html_path in html_files:
        if not html_path.exists():
            errors.append(f"Missing HTML file: {html_path}")
            continue
        text = html_path.read_text(encoding="utf-8")
        if re.search(r"\{\{[A-Z0-9_]+\}\}", text):
            errors.append(f"Unresolved template token in {html_path}")
        errors.extend(local_link_errors(html_path, workspace))
    if workspace_json_is_valid:
        try:
            errors.extend(rendered_output_errors(workspace))
        except SprintError as error:
            message = str(error)
            if not any(message in existing for existing in errors):
                errors.append(message)
    return errors


def migrate_workspace_state_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Add explicit adaptive/live fidelity records to validated legacy state."""

    return migrate_legacy_state(data)


def migrate_artifact_data_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate validated legacy artifact content without changing its meaning."""

    migrated = copy.deepcopy(data)
    migrated["schemaVersion"] = SCHEMA_VERSION
    return migrated


MIGRATIONS = {
    "workspace-state": {
        (LEGACY_SCHEMA_VERSION, SCHEMA_VERSION): migrate_workspace_state_v1_to_v2
    },
    "artifact-data": {
        (LEGACY_SCHEMA_VERSION, SCHEMA_VERSION): migrate_artifact_data_v1_to_v2
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
            errors.extend(formatted_schema_errors(data, family, path))
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
    if errors:
        detail = "\n".join(f"- {item}" for item in errors)
        raise SprintError(f"Workspace cannot be migrated:\n{detail}")
    return plan


def default_backup_path(workspace: Path) -> Path:
    return workspace.parent / f"{workspace.name}.backup-before-schema-{SCHEMA_VERSION}"


def command_migrate(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    plan = migration_plan(workspace)
    if not plan:
        print(f"Workspace already uses schema version {SCHEMA_VERSION}; no migration needed")
        return
    print("Migration plan:")
    for path, family, migrated in plan:
        relative = path.relative_to(workspace)
        old_version = read_json(path).get("schemaVersion")
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
    print(f"Migrated {len(plan)} JSON file(s) to schema version {SCHEMA_VERSION}")


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
    state = load_state(workspace)
    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True))
        return
    print(f"Sprint: {state['title']}")
    print(f"Method profile: {state['methodProfile']}")
    print(f"Execution mode: {state['executionMode']}")
    print(f"Route: {state['route']}")
    print(
        "Method fidelity: "
        f"{state.get('fidelity', {}).get('summary', {}).get('assessment', 'unknown')}"
    )
    print(f"Status: {state['status']}")
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
    print(
        "Timebox: "
        f"{timebox.get('suggestedMinutes', 'unknown')} minutes suggested, "
        f"{timebox.get('actualMinutes') if timebox.get('actualMinutes') is not None else 'not recorded'} actual"
    )
    print(f"Pending gate: {state.get('pendingGate') or 'none'}")
    customer = state.get("customerTesting", {})
    print(
        "Customer testing: "
        f"{customer.get('status')}, {customer.get('sessionsCompleted', 0)}/"
        f"{customer.get('sessionsPlanned', 0)} sessions"
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
    init_parser.add_argument("--selected-by", default="workspace default")
    init_parser.add_argument("--profile-reason")
    init_parser.add_argument("--mode-reason")
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
    mode_parser.add_argument("--selected-by", default="human Decider")
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
    skip_parser.set_defaults(handler=command_skip_step)

    gate_parser = subparsers.add_parser("gate", help="Record a human gate decision")
    gate_parser.add_argument("--workspace", required=True)
    gate_parser.add_argument("--gate", required=True, choices=sorted(GATE_NAMES))
    gate_parser.add_argument("--decision", required=True)
    gate_parser.add_argument("--rationale", required=True)
    gate_parser.add_argument("--reservations")
    gate_parser.set_defaults(handler=command_gate)

    customer_parser = subparsers.add_parser("customer", help="Update customer testing state")
    customer_parser.add_argument("--workspace", required=True)
    customer_parser.add_argument("--status", required=True, choices=sorted(CUSTOMER_STATUSES))
    customer_parser.add_argument("--target", default="")
    customer_parser.add_argument("--planned", type=int, default=0)
    customer_parser.add_argument("--completed", type=int, default=0)
    customer_parser.add_argument("--rationale")
    customer_parser.set_defaults(handler=command_customer)

    next_parser = subparsers.add_parser("next-action", help="Update dashboard guidance")
    next_parser.add_argument("--workspace", required=True)
    next_parser.add_argument("--title", required=True)
    next_parser.add_argument("--body", required=True)
    next_parser.add_argument("--human-input", required=True)
    next_parser.add_argument("--status", choices=sorted(WORKSPACE_STATUSES))
    next_parser.set_defaults(handler=command_next_action)

    role_parser = subparsers.add_parser("role-packet", help="Generate a bounded specialist assignment")
    role_parser.add_argument("--workspace", required=True)
    role_parser.add_argument("--role", required=True)
    role_parser.add_argument("--task", required=True)
    role_parser.add_argument("--input", action="append", default=[])
    role_parser.add_argument("--output", help="Path below working/; omit to print")
    role_parser.set_defaults(handler=command_role_packet)

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
