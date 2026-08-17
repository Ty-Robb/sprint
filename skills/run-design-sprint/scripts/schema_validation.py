"""Small dependency-free validator for the JSON Schema vocabulary used by the skill.

The published schemas target JSON Schema Draft 2020-12.  The workspace engine
intentionally remains dependency-free, so this module implements the assertion
keywords used by those schemas and reports JSONPath-style instance locations.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


JsonPathPart = str | int


def strict_json_loads(text: str) -> Any:
    """Parse standards-compliant JSON, rejecting Python's NaN/Infinity extension."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON numeric token {value!r}")

    return json.loads(text, parse_constant=reject_constant)


@dataclass(frozen=True)
class ValidationIssue:
    """One JSON Schema assertion failure."""

    path: tuple[JsonPathPart, ...]
    message: str

    @property
    def json_path(self) -> str:
        output = "$"
        for part in self.path:
            if isinstance(part, int):
                output += f"[{part}]"
            elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part):
                output += f".{part}"
            else:
                escaped = part.replace("\\", "\\\\").replace("'", "\\'")
                output += f"['{escaped}']"
        return output

    def __str__(self) -> str:
        return f"{self.json_path}: {self.message}"


class SchemaValidator:
    """Validate JSON-compatible values against local Draft 2020-12 schemas."""

    def __init__(self) -> None:
        self._schema_cache: dict[Path, Any] = {}

    def validate(self, instance: Any, schema_path: Path) -> list[ValidationIssue]:
        resolved = schema_path.resolve()
        schema = self._load_schema(resolved)
        return self._validate(instance, schema, (), resolved, schema)

    def _load_schema(self, path: Path) -> Any:
        if path not in self._schema_cache:
            self._schema_cache[path] = strict_json_loads(
                path.read_text(encoding="utf-8")
            )
        return self._schema_cache[path]

    def _resolve_ref(
        self, ref: str, schema_path: Path, root_schema: Any
    ) -> tuple[Any, Path, Any]:
        file_part, separator, fragment = ref.partition("#")
        if file_part:
            target_path = (schema_path.parent / unquote(file_part)).resolve()
            target_root = self._load_schema(target_path)
        else:
            target_path = schema_path
            target_root = root_schema
        target = target_root
        if separator and fragment:
            if not fragment.startswith("/"):
                raise ValueError(f"Unsupported JSON Schema reference: {ref}")
            for raw_part in fragment[1:].split("/"):
                part = unquote(raw_part).replace("~1", "/").replace("~0", "~")
                target = target[int(part)] if isinstance(target, list) else target[part]
        return target, target_path, target_root

    @staticmethod
    def _is_type(instance: Any, expected: str) -> bool:
        checks = {
            "null": lambda value: value is None,
            "boolean": lambda value: isinstance(value, bool),
            "object": lambda value: isinstance(value, dict),
            "array": lambda value: isinstance(value, list),
            "string": lambda value: isinstance(value, str),
            "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
            "number": lambda value: isinstance(value, (int, float))
            and not isinstance(value, bool),
        }
        return expected in checks and checks[expected](instance)

    @staticmethod
    def _json_value(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _format_is_valid(value: str, format_name: str) -> bool:
        try:
            if format_name == "date":
                return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)) and (
                    date.fromisoformat(value).isoformat() == value
                )
            if format_name == "date-time":
                if re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
                    value,
                ) is None:
                    return False
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.tzinfo is not None
            if format_name == "uri":
                parsed = urlparse(value)
                return bool(parsed.scheme and (parsed.netloc or parsed.scheme == "urn"))
        except ValueError:
            return False
        return True

    def _validate(
        self,
        instance: Any,
        schema: Any,
        path: tuple[JsonPathPart, ...],
        schema_path: Path,
        root_schema: Any,
    ) -> list[ValidationIssue]:
        if schema is True:
            return []
        if schema is False:
            return [ValidationIssue(path, "value is not allowed")]
        if not isinstance(schema, dict):
            raise ValueError(f"Invalid JSON Schema in {schema_path}: expected an object")

        issues: list[ValidationIssue] = []

        if "$ref" in schema:
            target, target_path, target_root = self._resolve_ref(
                str(schema["$ref"]), schema_path, root_schema
            )
            issues.extend(
                self._validate(instance, target, path, target_path, target_root)
            )

        expected_type = schema.get("type")
        if expected_type is not None:
            allowed_types = (
                expected_type if isinstance(expected_type, list) else [expected_type]
            )
            if not any(self._is_type(instance, item) for item in allowed_types):
                label = " or ".join(str(item) for item in allowed_types)
                return issues + [
                    ValidationIssue(path, f"expected {label}, found {type(instance).__name__}")
                ]

        if "const" in schema and instance != schema["const"]:
            issues.append(
                ValidationIssue(
                    path,
                    f"found {self._json_value(instance)}; must equal "
                    f"{self._json_value(schema['const'])}",
                )
            )
        if "enum" in schema and instance not in schema["enum"]:
            allowed = ", ".join(self._json_value(item) for item in schema["enum"])
            issues.append(
                ValidationIssue(
                    path,
                    f"found {self._json_value(instance)}; must be one of: {allowed}",
                )
            )

        for subschema in schema.get("allOf", []):
            issues.extend(
                self._validate(instance, subschema, path, schema_path, root_schema)
            )

        if "anyOf" in schema:
            branch_results = [
                self._validate(instance, branch, path, schema_path, root_schema)
                for branch in schema["anyOf"]
            ]
            if not any(not result for result in branch_results):
                best = min(branch_results, key=self._branch_error_score)
                issues.extend(best or [ValidationIssue(path, "does not match any allowed schema")])

        if "oneOf" in schema:
            branch_results = [
                self._validate(instance, branch, path, schema_path, root_schema)
                for branch in schema["oneOf"]
            ]
            valid_count = sum(not result for result in branch_results)
            if valid_count == 0:
                best = min(branch_results, key=self._branch_error_score)
                issues.extend(best or [ValidationIssue(path, "does not match an allowed schema")])
            elif valid_count > 1:
                issues.append(ValidationIssue(path, "matches more than one allowed schema"))

        if "not" in schema:
            if not self._validate(instance, schema["not"], path, schema_path, root_schema):
                issues.append(ValidationIssue(path, "matches a prohibited schema"))

        if "if" in schema:
            condition_matches = not self._validate(
                instance, schema["if"], path, schema_path, root_schema
            )
            selected = schema.get("then") if condition_matches else schema.get("else")
            if selected is not None:
                issues.extend(
                    self._validate(instance, selected, path, schema_path, root_schema)
                )

        if isinstance(instance, dict):
            required = schema.get("required", [])
            for key in required:
                if key not in instance:
                    issues.append(
                        ValidationIssue(path + (str(key),), "required field is missing")
                    )
            properties = schema.get("properties", {})
            for key, value in instance.items():
                if key in properties:
                    issues.extend(
                        self._validate(
                            value,
                            properties[key],
                            path + (str(key),),
                            schema_path,
                            root_schema,
                        )
                    )
                elif schema.get("additionalProperties") is False:
                    issues.append(
                        ValidationIssue(path + (str(key),), "unexpected field")
                    )
                elif isinstance(schema.get("additionalProperties"), dict):
                    issues.extend(
                        self._validate(
                            value,
                            schema["additionalProperties"],
                            path + (str(key),),
                            schema_path,
                            root_schema,
                        )
                    )
            if len(instance) < schema.get("minProperties", 0):
                issues.append(
                    ValidationIssue(
                        path,
                        f"must contain at least {schema['minProperties']} properties",
                    )
                )

        if isinstance(instance, list):
            item_schema = schema.get("items")
            if item_schema is not None:
                for index, value in enumerate(instance):
                    issues.extend(
                        self._validate(
                            value,
                            item_schema,
                            path + (index,),
                            schema_path,
                            root_schema,
                        )
                    )
            if len(instance) < schema.get("minItems", 0):
                issues.append(
                    ValidationIssue(path, f"must contain at least {schema['minItems']} items")
                )
            if "maxItems" in schema and len(instance) > schema["maxItems"]:
                issues.append(
                    ValidationIssue(path, f"must contain at most {schema['maxItems']} items")
                )
            if schema.get("uniqueItems"):
                encoded = [self._json_value(item) for item in instance]
                if len(encoded) != len(set(encoded)):
                    issues.append(ValidationIssue(path, "items must be unique"))
            if "contains" in schema:
                matches = sum(
                    not self._validate(item, schema["contains"], path + (index,), schema_path, root_schema)
                    for index, item in enumerate(instance)
                )
                minimum = schema.get("minContains", 1)
                maximum = schema.get("maxContains")
                if matches < minimum:
                    issues.append(
                        ValidationIssue(
                            path,
                            f"must contain at least {minimum} item(s) matching the required shape",
                        )
                    )
                if maximum is not None and matches > maximum:
                    issues.append(
                        ValidationIssue(
                            path,
                            f"must contain at most {maximum} item(s) matching the required shape",
                        )
                    )

        if isinstance(instance, str):
            if len(instance) < schema.get("minLength", 0):
                issues.append(
                    ValidationIssue(
                        path, f"must contain at least {schema['minLength']} characters"
                    )
                )
            if "maxLength" in schema and len(instance) > schema["maxLength"]:
                issues.append(
                    ValidationIssue(
                        path, f"must contain at most {schema['maxLength']} characters"
                    )
                )
            if "pattern" in schema and re.search(schema["pattern"], instance) is None:
                issues.append(
                    ValidationIssue(path, f"must match pattern {schema['pattern']!r}")
                )
            format_name = schema.get("format")
            if format_name and not self._format_is_valid(instance, str(format_name)):
                issues.append(
                    ValidationIssue(path, f"must be a valid {format_name}")
                )

        if isinstance(instance, (int, float)) and not isinstance(instance, bool):
            if "minimum" in schema and instance < schema["minimum"]:
                issues.append(
                    ValidationIssue(path, f"must be at least {schema['minimum']}")
                )
            if "maximum" in schema and instance > schema["maximum"]:
                issues.append(
                    ValidationIssue(path, f"must be at most {schema['maximum']}")
                )

        return issues

    @staticmethod
    def _branch_error_score(issues: list[ValidationIssue]) -> tuple[int, int, int]:
        """Prefer the branch with few errors, then the deepest useful path."""

        deepest = max((len(issue.path) for issue in issues), default=0)
        type_mismatches = sum(issue.message.startswith("expected ") for issue in issues)
        return len(issues), type_mismatches, -deepest
