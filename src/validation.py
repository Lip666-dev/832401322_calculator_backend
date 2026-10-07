"""Payload validation for the API layer.

Validation is deliberately separated from parsing: this module only answers
"is the shape of the request acceptable?", while :mod:`src.calculator` answers
"is the expression mathematically valid?".
"""

from __future__ import annotations

from typing import Any, Mapping

from .config import Settings
from .errors import ValidationError

MIN_PAGE = 1
MIN_BASE = 2
MAX_BASE = 36


def require_json_object(payload: Any) -> Mapping[str, Any]:
    """Ensure the request body is a JSON object."""
    if payload is None:
        raise ValidationError("A JSON request body is required")
    if not isinstance(payload, Mapping):
        raise ValidationError("The request body must be a JSON object")
    return payload


def require_expression(payload: Mapping[str, Any], settings: Settings) -> str:
    """Extract and sanity check the ``expression`` field."""
    if "expression" not in payload:
        raise ValidationError("The 'expression' field is required", field="expression")
    raw = payload["expression"]
    if not isinstance(raw, str):
        raise ValidationError("The 'expression' field must be a string", field="expression")
    text = raw.strip()
    if not text:
        raise ValidationError("The 'expression' field must not be empty", field="expression")
    if len(text) > settings.max_expression_length:
        raise ValidationError(
            f"The expression may contain at most {settings.max_expression_length} characters",
            field="expression",
            length=len(text),
        )
    for character in text:
        if ord(character) < 32:
            raise ValidationError(
                "The expression must not contain control characters", field="expression"
            )
    return text


def require_int(
    payload: Mapping[str, Any],
    field: str,
    minimum: int,
    maximum: int,
    default: int | None = None,
) -> int:
    """Read an integer field from a payload and range check it."""
    if field not in payload or payload[field] is None or payload[field] == "":
        if default is None:
            raise ValidationError(f"The '{field}' field is required", field=field)
        return default
    value = payload[field]
    if isinstance(value, bool):
        raise ValidationError(f"The '{field}' field must be an integer", field=field)
    if isinstance(value, str):
        try:
            value = int(value.strip())
        except ValueError as exc:
            raise ValidationError(f"The '{field}' field must be an integer", field=field) from exc
    if not isinstance(value, int):
        raise ValidationError(f"The '{field}' field must be an integer", field=field)
    if not minimum <= value <= maximum:
        raise ValidationError(
            f"The '{field}' field must be between {minimum} and {maximum}",
            field=field,
            minimum=minimum,
            maximum=maximum,
        )
    return value


def require_bool(payload: Mapping[str, Any], field: str, default: bool | None = None) -> bool:
    """Read a boolean field, accepting the usual string spellings."""
    if field not in payload or payload[field] is None:
        if default is None:
            raise ValidationError(f"The '{field}' field is required", field=field)
        return default
    value = payload[field]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ValidationError(f"The '{field}' field must be a boolean", field=field)


def parse_record_id(raw: str) -> int:
    """Convert a path segment into a positive history id."""
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError("The history id must be an integer", parameter="id") from exc
    if value <= 0:
        raise ValidationError("The history id must be a positive integer", parameter="id")
    return value


def require_value_text(payload: Mapping[str, Any]) -> str:
    """Read the value that should be converted between bases."""
    for field in ("value", "expression"):
        if field in payload and payload[field] is not None:
            raw = payload[field]
            if not isinstance(raw, str):
                raise ValidationError(f"The '{field}' field must be a string", field=field)
            if not raw.strip():
                raise ValidationError(f"The '{field}' field must not be empty", field=field)
            return raw.strip()
    raise ValidationError("The 'value' field is required", field="value")
