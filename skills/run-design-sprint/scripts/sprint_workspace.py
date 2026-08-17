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


def workspace_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def state_path(workspace: Path) -> Path:
    return workspace / STATE_FILENAME


def load_state(workspace: Path) -> dict[str, Any]:
    path = state_path(workspace)
    state = read_json(path)
    require_valid_schema(state, "workspace-state", path)
    return state


def load_artifact_data(path: Path) -> dict[str, Any]:
    data = read_json(path)
    require_valid_schema(data, "artifact-data", path)
    return data


def save_state(
    workspace: Path, state: dict[str, Any], timestamp: str | None = None
) -> None:
    state["updatedAt"] = timestamp or utc_now()
    path = state_path(workspace)
    require_valid_schema(state, "workspace-state", path)
    write_json(path, state)


def save_artifact_data(path: Path, data: dict[str, Any]) -> None:
    require_valid_schema(data, "artifact-data", path)
    write_json(path, data)


def next_step(current: str, skipped: set[str]) -> str | None:
    index = STEP_INDEX[current]
    for step in STEPS[index + 1 :]:
        if step["id"] not in skipped:
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


def remove_skip(state: dict[str, Any], step_id: str) -> None:
    skipped = state.setdefault("skippedSteps", [])
    if step_id in skipped:
        skipped.remove(step_id)
    state.setdefault("skipReasons", {}).pop(step_id, None)


def apply_route(state: dict[str, Any], route: str) -> None:
    state["route"] = route
    if route in {"full-design-sprint", "focused-design-sprint"}:
        add_skip(
            state,
            "04-foundation",
            "The approved route starts from an existing strategic foundation.",
        )
    elif route == "foundation-plus-design":
        remove_skip(state, "04-foundation")
    elif route == "no-sprint":
        for step in STEPS[2:-1]:
            add_skip(
                state,
                step["id"],
                "The Decider approved a no-sprint route after qualification.",
            )


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


def artifact_data_errors(
    data: dict[str, Any], specs: dict[str, dict[str, Any]]
) -> list[str]:
    """Return artifact completion rules that are intentionally above schema shape."""

    errors: list[str] = []
    artifact_id = data.get("id")
    if artifact_id not in specs:
        errors.append(f"$.id: unknown artifact id {artifact_id!r}")
        return errors
    sections = data.get("sections")
    assert isinstance(sections, list)
    section_indexes = {
        section["title"]: index
        for index, section in enumerate(sections)
        if isinstance(section, dict) and isinstance(section.get("title"), str)
    }
    for required in specs[artifact_id].get("requiredSections", []):
        if required not in section_indexes:
            errors.append(f"$.sections: missing required section {required!r}")
    if data.get("status") in {"ready-for-decision", "complete"}:
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
        if data.get("summary") == ["This artifact is in progress."]:
            errors.append("$.summary: completed artifact still has the draft summary")
    return errors


def section_has_content(section: dict[str, Any]) -> bool:
    placeholder = "not established yet."
    section_type = section.get("type", "paragraphs")
    if section_type in {"list", "ordered-list"}:
        values = section.get("items", [])
    elif section_type == "table":
        values = section.get("rows", [])
    elif section_type == "cards":
        values = section.get("cards", [])
    elif section_type == "key-value":
        values = section.get("items", [])
    else:
        values = section.get("paragraphs", section.get("body", []))
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list) or not values:
        return False
    meaningful = [value for value in values if str(value).strip().lower() != placeholder]
    return bool(meaningful)


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
            "UPDATED_ISO": escape(updated_at),
            "UPDATED_DISPLAY": escape(display_date(updated_at)),
            "SUMMARY_HTML": render_paragraphs(data.get("summary", [])),
            "PRIMARY_CONTENT_HTML": primary_content,
            "EVIDENCE_HTML": render_evidence(data.get("evidence", [])),
            "UNKNOWNS_HTML": render_list(data.get("unknowns", [])),
            "NEXT_ACTION_HTML": render_list(data.get("nextActions", []), ordered=True),
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
    current = state.get("currentStep")
    output = []
    for number, step in enumerate(STEPS, start=1):
        step_id = step["id"]
        if step_id in skipped:
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
    denominator = max(1, len(STEPS) - len(skipped))
    completed = len(set(state.get("completedSteps", [])) - skipped)
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
    rendered = replace_tokens(
        template,
        {
            "SPRINT_TITLE": escape(state.get("title", "Untitled sprint")),
            "SPRINT_CHALLENGE": escape(state.get("challenge", "No challenge recorded")),
            "SPRINT_STATUS": escape(str(state.get("status", "active")).replace("-", " ").title()),
            "SPRINT_ROUTE": escape(str(state.get("route", "undecided")).replace("-", " ").title()),
            "UPDATED_ISO": escape(updated_at),
            "UPDATED_DISPLAY": escape(display_date(updated_at)),
            "PROGRESS_PERCENT": progress,
            "CURRENT_STEP": escape(f"{current}: {step_name(current)}"),
            "NEXT_ACTION_TITLE": escape(next_action.get("title", "Continue the sprint")),
            "NEXT_ACTION_BODY": escape(next_action.get("body", "Review the current step.")),
            "HUMAN_INPUT_NEEDED": escape(next_action.get("humanInput", "None right now")),
            "SPRINT_STEPS": render_steps(state),
            "TEST_STATUS": escape(str(customer.get("status", "not-planned")).replace("-", " ").title()),
            "SESSIONS_PLANNED": escape(customer.get("sessionsPlanned", 0)),
            "SESSIONS_COMPLETED": escape(customer.get("sessionsCompleted", 0)),
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
    state_update = normalized_state if state.get("artifacts") != registrations else None
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
        "schemaVersion": SCHEMA_VERSION,
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
    now = utc_now()
    state = {
        "schemaVersion": SCHEMA_VERSION,
        "title": title,
        "slug": slugify(title),
        "challenge": challenge,
        "route": "undecided",
        "status": "waiting-for-human",
        "currentStep": "01-intake",
        "completedSteps": [],
        "skippedSteps": [],
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
            "target": "",
            "sessionsPlanned": 0,
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
    if args.status not in ARTIFACT_STATUSES:
        raise SprintError(f"Invalid artifact status: {args.status}")
    data_path = workspace / "artifact-data" / f"{args.id}.json"
    data = load_artifact_data(data_path)
    now = utc_now()
    data["status"] = args.status
    data["updatedAt"] = now
    errors = artifact_data_errors(data, specs)
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
    apply_route(state, args.route)
    state["routeRationale"] = args.rationale.strip()
    if (
        previous_route == "research-first"
        and "03-evidence" in state.get("completedSteps", [])
    ):
        following = next_step("03-evidence", set(state.get("skippedSteps", [])))
        if args.route == "no-sprint":
            following = "13-outcome"
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
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Set sprint route: {args.route}")


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


def command_complete_step(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    step_id = args.step
    if step_id not in STEP_INDEX:
        raise SprintError(f"Unknown step: {step_id}")
    if state.get("currentStep") != step_id:
        raise SprintError(
            f"Current step is {state.get('currentStep')}; cannot complete {step_id}"
        )
    if step_id in state.get("completedSteps", []):
        raise SprintError(f"Step is already complete: {step_id}")
    if step_id == "02-qualify" and state.get("route") == "undecided":
        raise SprintError("Set the sprint route before completing 02-qualify")
    if step_id == "10-prototype" and not (workspace / "prototype" / "index.html").exists():
        raise SprintError("prototype/index.html must exist before completing 10-prototype")
    if step_id == "11-customer-sessions":
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
            following = next_step(step_id, set(state.get("skippedSteps", [])))
            if following:
                state["currentStep"] = following
                state["status"] = "active"
                state["nextAction"] = {
                    "title": step_name(following),
                    "body": "Begin the next sprint step.",
                    "humanInput": "None unless the Orchestrator identifies a required decision.",
                }
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Completed step: {step_id}")


def command_skip_step(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    step_id = args.step
    if state.get("currentStep") != step_id:
        raise SprintError(f"Only the current step may be skipped: {state.get('currentStep')}")
    if step_id in GATE_BY_STEP:
        raise SprintError("A step with a human gate cannot be skipped")
    state.setdefault("skippedSteps", []).append(step_id)
    state.setdefault("skipReasons", {})[step_id] = args.reason.strip()
    following = next_step(step_id, set(state["skippedSteps"]))
    if following is None:
        raise SprintError("Cannot skip the final remaining step")
    state["currentStep"] = following
    state["status"] = "active"
    state["nextAction"] = {
        "title": step_name(following),
        "body": f"Step {step_id} was skipped: {args.reason.strip()}",
        "humanInput": "None unless the next step requires a decision.",
    }
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Skipped step: {step_id}")


def command_gate(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    gate_id = args.gate
    if gate_id not in GATE_NAMES:
        raise SprintError(f"Unknown gate: {gate_id}")
    if state.get("pendingGate") != gate_id:
        raise SprintError(f"Pending gate is {state.get('pendingGate')}; cannot record {gate_id}")
    if gate_id == "gate-1" and state.get("route") == "undecided":
        raise SprintError("Gate 1 requires an approved sprint route")
    normalized = args.decision.strip().lower()
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
        "decision": args.decision.strip(),
        "rationale": args.rationale.strip(),
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
            "title": f"Sprint complete: {args.decision.strip()}",
            "body": "Use the outcome artifact and owned next actions for the handoff.",
            "humanInput": "None.",
        }
    else:
        if gate_id == "gate-1":
            apply_route(state, str(state["route"]))
        following = next_step(current, set(state.get("skippedSteps", [])))
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
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Recorded {gate_id}: {args.decision.strip()}")


def command_customer(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    if args.status not in CUSTOMER_STATUSES:
        raise SprintError(f"Invalid customer-testing status: {args.status}")
    planned = args.planned
    completed = args.completed
    if planned < 0 or completed < 0:
        raise SprintError("Session counts cannot be negative")
    if planned and completed > planned:
        raise SprintError("Completed sessions cannot exceed planned sessions")
    if not planned and completed:
        planned = completed
    state["customerTesting"] = {
        "status": args.status,
        "target": args.target.strip(),
        "sessionsPlanned": planned,
        "sessionsCompleted": completed,
    }
    if args.status in {"recruiting", "scheduled", "in-progress", "blocked"}:
        state["status"] = "waiting-for-customers" if args.status == "blocked" else state["status"]
    save_state(workspace, state)
    render_workspace(workspace)
    print(f"Updated customer testing: {args.status}, {completed}/{planned} sessions")


def command_next_action(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state, _specs, _artifacts = load_workspace_documents(workspace)
    state["nextAction"] = {
        "title": args.title.strip(),
        "body": args.body.strip(),
        "humanInput": args.human_input.strip(),
    }
    if args.status:
        if args.status not in WORKSPACE_STATUSES:
            raise SprintError(f"Invalid workspace status: {args.status}")
        state["status"] = args.status
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
    packet = f"""# Bounded specialist assignment

Role: {contract['displayName']} (`{args.role}`)
Sprint: {state['title']}
Current step: {state['currentStep']} — {step_name(str(state['currentStep']))}

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


def validate_state(state: dict[str, Any]) -> list[str]:
    """Return the pre-existing cross-record workflow checks.

    JSON shape, types, enums, formats, and nested conditions are enforced by the
    workspace-state schema before this function is called. Route-history and
    transition policy intentionally remain outside this issue.
    """

    errors: list[str] = []
    completed = state["completedSteps"]
    skipped = state["skippedSteps"]
    if set(completed) & set(skipped):
        errors.append(
            "$.completedSteps and $.skippedSteps: a step cannot be both completed and skipped"
        )
    customer = state["customerTesting"]
    planned = customer["sessionsPlanned"]
    completed_sessions = customer["sessionsCompleted"]
    if planned and completed_sessions > planned:
        errors.append(
            "$.customerTesting.sessionsCompleted: completed customer sessions exceed planned sessions"
        )
    if "12-synthesis" in completed and completed_sessions < 1:
        errors.append(
            "$.completedSteps: synthesis cannot be complete without a real customer session"
        )
    gates = state["humanGates"]
    if state.get("status") == "complete":
        gate_5 = next((gate for gate in gates if gate.get("id") == "gate-5"), {})
        if gate_5.get("status") != "complete":
            errors.append("$.humanGates[4].status: a complete sprint requires Gate 5")
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
    artifact_statuses: dict[str, str] = {}
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
        artifact_id = data["id"]
        artifact_statuses[artifact_id] = data["status"]
        if artifact_id in specs:
            output = workspace / "artifacts" / specs[artifact_id]["filename"]
            if not output.exists():
                errors.append(f"Missing rendered artifact: {output}")
            if artifact_id not in registrations:
                errors.append(f"Artifact is not registered in state: {artifact_id}")
    for step_id in state["completedSteps"] if state_is_valid else []:
        for artifact_id in required_artifacts_for_step(step_id):
            status = artifact_statuses.get(artifact_id)
            allowed = {"ready-for-decision", "complete"} if step_id in GATE_BY_STEP else {"complete"}
            if status not in allowed:
                errors.append(f"Completed step {step_id} has incomplete artifact {artifact_id}")
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
    """Migrate a validated legacy state without inventing workflow history."""

    migrated = copy.deepcopy(data)
    migrated["schemaVersion"] = SCHEMA_VERSION
    return migrated


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
    print(f"Route: {state['route']}")
    print(f"Status: {state['status']}")
    print(f"Current step: {state['currentStep']} — {step_name(str(state['currentStep']))}")
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
