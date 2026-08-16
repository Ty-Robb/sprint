#!/usr/bin/env python3
"""Create, render, advance, and validate a Design Sprint for One workspace."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SKILL_DIR = Path(__file__).resolve().parent.parent
REFERENCES_DIR = SKILL_DIR / "references"
HTML_KIT_DIR = SKILL_DIR / "assets" / "html-kit"

STATE_FILENAME = "sprint-state.json"
SCHEMA_VERSION = "1.0"

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
EVIDENCE_STATUSES = {
    "Observed",
    "Assumption",
    "Inference",
    "Decision",
    "Unknown",
    "Synthetic rehearsal",
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


class SprintError(Exception):
    """A user-correctable sprint workspace error."""


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
    return slug[:64] or "sprint"


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SprintError(f"Missing required file: {path}") from error
    except json.JSONDecodeError as error:
        raise SprintError(f"Invalid JSON in {path}: {error}") from error
    if not isinstance(data, dict):
        raise SprintError(f"Expected a JSON object in {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def load_artifact_specs() -> dict[str, dict[str, Any]]:
    data = read_json(REFERENCES_DIR / "artifact-specs.json")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        raise SprintError("artifact-specs.json must contain an artifacts object")
    return artifacts


def load_role_contracts() -> dict[str, dict[str, Any]]:
    data = read_json(REFERENCES_DIR / "role-contracts.json")
    roles = data.get("roles")
    if not isinstance(roles, dict):
        raise SprintError("role-contracts.json must contain a roles object")
    return roles


def workspace_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def state_path(workspace: Path) -> Path:
    return workspace / STATE_FILENAME


def load_state(workspace: Path) -> dict[str, Any]:
    return read_json(state_path(workspace))


def save_state(workspace: Path, state: dict[str, Any]) -> None:
    state["updatedAt"] = utc_now()
    write_json(state_path(workspace), state)


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
    errors: list[str] = []
    artifact_id = data.get("id")
    if artifact_id not in specs:
        errors.append(f"Unknown artifact id: {artifact_id}")
        return errors
    if data.get("status") not in ARTIFACT_STATUSES:
        errors.append(f"Invalid artifact status: {data.get('status')}")
    sections = data.get("sections")
    if not isinstance(sections, list):
        errors.append("sections must be a list")
        sections = []
    titles = {section.get("title") for section in sections if isinstance(section, dict)}
    for required in specs[artifact_id].get("requiredSections", []):
        if required not in titles:
            errors.append(f"Missing required section: {required}")
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
                errors.append(f"Required section is still empty: {required}")
        if data.get("summary") == ["This artifact is in progress."]:
            errors.append("Completed artifact still has the draft summary")
    evidence = data.get("evidence", [])
    if not isinstance(evidence, list):
        errors.append("evidence must be a list")
    else:
        for index, item in enumerate(evidence, start=1):
            if not isinstance(item, dict):
                errors.append(f"Evidence entry {index} must be an object")
                continue
            if item.get("status") not in EVIDENCE_STATUSES:
                errors.append(
                    f"Evidence entry {index} has invalid status: {item.get('status')}"
                )
    for key in ("summary", "unknowns", "nextActions"):
        if not isinstance(data.get(key, []), list):
            errors.append(f"{key} must be a list")
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
) -> dict[str, Any]:
    errors = artifact_data_errors(data, specs)
    if errors:
        raise SprintError(f"Artifact {data.get('id')} is invalid: {'; '.join(errors)}")
    artifact_id = str(data["id"])
    spec = specs[artifact_id]
    updated_at = str(data.get("updatedAt") or utc_now())
    data["updatedAt"] = updated_at
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
    write_text(output_path, rendered)
    return {
        "id": artifact_id,
        "title": spec["title"],
        "path": str(output_path.relative_to(workspace)),
        "status": status,
        "step": spec["step"],
        "updatedAt": updated_at,
    }


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


def render_dashboard(workspace: Path, state: dict[str, Any]) -> None:
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
    updated_at = str(state.get("updatedAt", utc_now()))
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
            "ARTIFACT_COUNT": len(state.get("artifacts", [])),
            "ARTIFACT_LINKS": render_artifact_links(state.get("artifacts", [])),
            "DECISION_SUMMARY": render_decisions(state.get("decisions", [])),
            "OPEN_QUESTIONS": questions_html,
        },
    )
    rendered = rendered.replace('value="0" max="100"', f'value="{progress}" max="100"', 1)
    write_text(workspace / "index.html", rendered)


def render_workspace(workspace: Path) -> dict[str, Any]:
    state = load_state(workspace)
    specs = load_artifact_specs()
    (workspace / "assets").mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HTML_KIT_DIR / "sprint.css", workspace / "assets" / "sprint.css")
    registrations = []
    data_dir = workspace / "artifact-data"
    for data_path in sorted(data_dir.glob("*.json")) if data_dir.exists() else []:
        data = read_json(data_path)
        registrations.append(render_artifact(workspace, data, state, specs))
        write_json(data_path, data)
    registrations.sort(key=lambda item: item["id"])
    state["artifacts"] = registrations
    state["updatedAt"] = utc_now()
    render_dashboard(workspace, state)
    save_state(workspace, state)
    return state


def empty_section(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "eyebrow": "To establish",
        "type": "paragraphs",
        "paragraphs": ["Not established yet."],
    }


def new_artifact_data(artifact_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
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


def initial_brief_data(challenge: str) -> dict[str, Any]:
    spec = load_artifact_specs()["01-sprint-brief"]
    data = new_artifact_data("01-sprint-brief", spec)
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
            "date": utc_now()[:10],
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
    output = workspace_path(args.output or f"design-sprint-{slugify(title)}")
    if output.exists():
        if not output.is_dir():
            raise SprintError(f"Output path is not a directory: {output}")
        if any(output.iterdir()):
            raise SprintError(f"Output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for directory in ("artifact-data", "artifacts", "assets", "prototype", "working"):
        (output / directory).mkdir(exist_ok=True)
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
    write_json(state_path(output), state)
    write_json(output / "artifact-data" / "01-sprint-brief.json", initial_brief_data(challenge))
    render_workspace(output)
    print(f"Created sprint workspace: {output}")
    print(f"Dashboard: {output / 'index.html'}")


def command_new_artifact(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    specs = load_artifact_specs()
    if args.id not in specs:
        raise SprintError(f"Unknown artifact id: {args.id}")
    data_path = workspace / "artifact-data" / f"{args.id}.json"
    if data_path.exists():
        raise SprintError(f"Artifact data already exists: {data_path}")
    write_json(data_path, new_artifact_data(args.id, specs[args.id]))
    render_workspace(workspace)
    print(f"Created artifact draft: {data_path}")


def command_set_artifact_status(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    if args.status not in ARTIFACT_STATUSES:
        raise SprintError(f"Invalid artifact status: {args.status}")
    data_path = workspace / "artifact-data" / f"{args.id}.json"
    data = read_json(data_path)
    data["status"] = args.status
    data["updatedAt"] = utc_now()
    write_json(data_path, data)
    render_workspace(workspace)
    print(f"Updated {args.id} to {args.status}")


def command_set_route(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    if args.route not in ROUTES - {"undecided"}:
        raise SprintError(f"Invalid sprint route: {args.route}")
    state = load_state(workspace)
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
    state = load_state(workspace)
    state["challenge"] = challenge
    brief_path = workspace / "artifact-data" / "01-sprint-brief.json"
    brief = read_json(brief_path)
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
    brief["updatedAt"] = utc_now()
    write_json(brief_path, brief)
    save_state(workspace, state)
    render_workspace(workspace)
    print("Updated the sprint challenge")


def command_question(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state = load_state(workspace)
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
    return str(read_json(path).get("status"))


def command_complete_step(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state = load_state(workspace)
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
    state = load_state(workspace)
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
    state = load_state(workspace)
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
    state = load_state(workspace)
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
    state = load_state(workspace)
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
    state = load_state(workspace)
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
- Edit `index.html`, `sprint-state.json`, or canonical files in `artifacts/`
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
    errors: list[str] = []
    required = {
        "schemaVersion",
        "title",
        "slug",
        "challenge",
        "route",
        "status",
        "currentStep",
        "completedSteps",
        "skippedSteps",
        "humanGates",
        "artifacts",
        "customerTesting",
        "nextAction",
    }
    missing = sorted(required - state.keys())
    if missing:
        errors.append(f"State is missing keys: {', '.join(missing)}")
    if state.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"Unsupported state schema: {state.get('schemaVersion')}")
    if state.get("route") not in ROUTES:
        errors.append(f"Invalid route: {state.get('route')}")
    if state.get("status") not in WORKSPACE_STATUSES:
        errors.append(f"Invalid workspace status: {state.get('status')}")
    if state.get("currentStep") not in STEP_INDEX:
        errors.append(f"Invalid current step: {state.get('currentStep')}")
    completed = state.get("completedSteps", [])
    skipped = state.get("skippedSteps", [])
    if not isinstance(completed, list) or len(completed) != len(set(completed)):
        errors.append("completedSteps must be a unique list")
    if not isinstance(skipped, list) or len(skipped) != len(set(skipped)):
        errors.append("skippedSteps must be a unique list")
    if isinstance(completed, list) and isinstance(skipped, list) and set(completed) & set(skipped):
        errors.append("A step cannot be both completed and skipped")
    customer = state.get("customerTesting", {})
    if not isinstance(customer, dict):
        errors.append("customerTesting must be an object")
    else:
        if customer.get("status") not in CUSTOMER_STATUSES:
            errors.append(f"Invalid customer-testing status: {customer.get('status')}")
        planned = customer.get("sessionsPlanned")
        completed_sessions = customer.get("sessionsCompleted")
        if not isinstance(planned, int) or not isinstance(completed_sessions, int):
            errors.append("Customer session counts must be integers")
        elif planned and completed_sessions > planned:
            errors.append("Completed customer sessions exceed planned sessions")
        if "12-synthesis" in completed and completed_sessions < 1:
            errors.append("Synthesis cannot be complete without a real customer session")
    gates = state.get("humanGates", [])
    if not isinstance(gates, list) or {item.get("id") for item in gates if isinstance(item, dict)} != set(GATE_NAMES):
        errors.append("humanGates must contain gate-1 through gate-5")
    if state.get("status") == "complete":
        gate_5 = next((gate for gate in gates if gate.get("id") == "gate-5"), {})
        if gate_5.get("status") != "complete":
            errors.append("A complete sprint requires Gate 5")
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


def workspace_errors(workspace: Path) -> list[str]:
    errors: list[str] = []
    try:
        state = load_state(workspace)
    except SprintError as error:
        return [str(error)]
    errors.extend(validate_state(state))
    specs = load_artifact_specs()
    registrations = {item.get("id"): item for item in state.get("artifacts", []) if isinstance(item, dict)}
    for data_path in sorted((workspace / "artifact-data").glob("*.json")):
        try:
            data = read_json(data_path)
        except SprintError as error:
            errors.append(str(error))
            continue
        errors.extend(f"{data_path.name}: {item}" for item in artifact_data_errors(data, specs))
        artifact_id = data.get("id")
        if artifact_id in specs:
            output = workspace / "artifacts" / specs[artifact_id]["filename"]
            if not output.exists():
                errors.append(f"Missing rendered artifact: {output}")
            if artifact_id not in registrations:
                errors.append(f"Artifact is not registered in state: {artifact_id}")
    for step_id in state.get("completedSteps", []):
        for artifact_id in required_artifacts_for_step(step_id):
            status = artifact_status(workspace, artifact_id)
            allowed = {"ready-for-decision", "complete"} if step_id in GATE_BY_STEP else {"complete"}
            if status not in allowed:
                errors.append(f"Completed step {step_id} has incomplete artifact {artifact_id}")
    if "10-prototype" in state.get("completedSteps", []) and not (workspace / "prototype" / "index.html").exists():
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
    return errors


def command_render(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    state = render_workspace(workspace)
    print(f"Rendered {len(state.get('artifacts', []))} artifacts and dashboard")


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
        print(json.dumps(state, indent=2, ensure_ascii=False))
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
    render_parser.set_defaults(handler=command_render)

    validate_parser = subparsers.add_parser("validate", help="Validate a sprint workspace")
    validate_parser.add_argument("--workspace", required=True)
    validate_parser.set_defaults(handler=command_validate)

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
