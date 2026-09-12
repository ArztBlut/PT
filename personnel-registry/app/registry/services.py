"""Shared logic: custom field values, serialisation, search and CSV safety."""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CustomField, Group, Person, User

URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")
INT_RE = re.compile(r"^[+-]?\d+$")
PHONE_LIKE = re.compile(r"^[+-][\d\s().-]*$")


# ---- serialisation ----------------------------------------------------------


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0).isoformat() + "Z"


def user_to_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "last_login_at": iso_utc(user.last_login_at),
        "created_at": iso_utc(user.created_at),
    }


def group_to_dict(group: Group, member_count: int = 0) -> dict[str, Any]:
    return {
        "id": group.id,
        "name": group.name,
        "code": group.code,
        "description": group.description,
        "colour": group.colour,
        "sort_order": group.sort_order,
        "member_count": member_count,
        "created_at": iso_utc(group.created_at),
        "updated_at": iso_utc(group.updated_at),
    }


def field_to_dict(field: CustomField) -> dict[str, Any]:
    return {
        "id": field.id,
        "key": field.key,
        "label": field.label,
        "field_type": field.field_type,
        "options": field.options,
        "required": field.required,
        "show_in_table": field.show_in_table,
        "sort_order": field.sort_order,
        "group_id": field.group_id,
        "created_at": iso_utc(field.created_at),
        "updated_at": iso_utc(field.updated_at),
    }


def person_to_dict(person: Person) -> dict[str, Any]:
    return {
        "id": person.id,
        "identifier": person.identifier,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "preferred_name": person.preferred_name,
        "job_title": person.job_title,
        "role": person.role,
        "email": person.email,
        "phone": person.phone,
        "status": person.status,
        "start_date": person.start_date.isoformat() if person.start_date else None,
        "notes": person.notes,
        "group_id": person.group_id,
        "extra": person.extra or {},
        "created_at": iso_utc(person.created_at),
        "updated_at": iso_utc(person.updated_at),
    }


def sorted_fields(db: Session) -> list[CustomField]:
    fields = list(db.scalars(select(CustomField)))
    fields.sort(key=lambda f: (f.group_id is not None, f.group_id or 0, f.sort_order, f.label.lower()))
    return fields


# ---- custom field keys and values -------------------------------------------


def make_field_key(label: str, existing: set[str]) -> str:
    ascii_label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", ascii_label.lower()).strip("_")[:48] or "field"
    if base[0].isdigit():
        base = f"f_{base}"
    key, n = base, 2
    while key in existing:
        key = f"{base}_{n}"
        n += 1
    return key


def coerce_value(field: CustomField, raw: Any) -> Any:
    """Normalise a submitted value for a custom field. Returns None for 'not set'."""
    kind = field.field_type

    if kind == "checkbox":
        if isinstance(raw, bool):
            return raw
        if raw is None or raw == "":
            return False
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str) and raw.strip().lower() in {"true", "1", "yes", "on"}:
            return True
        if isinstance(raw, str) and raw.strip().lower() in {"false", "0", "no", "off"}:
            return False
        raise ValueError("Choose yes or no.")

    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        raise ValueError("This value isn't supported for this field.")

    if kind == "number":
        if isinstance(raw, bool):
            raise ValueError("Enter a number.")
        if isinstance(raw, (int, float)):
            number: int | float = raw
        else:
            text = str(raw).strip()
            if not text:
                return None
            try:
                number = int(text) if INT_RE.match(text) else float(text)
            except ValueError as exc:
                raise ValueError("Enter a number.") from exc
        if isinstance(number, float) and not math.isfinite(number):
            raise ValueError("Enter a number.")
        return number

    text = str(raw).strip()
    if not text:
        return None

    if kind == "date":
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError as exc:
            raise ValueError("Use the format YYYY-MM-DD.") from exc
    if kind == "email" and not EMAIL_RE.match(text):
        raise ValueError("Enter a valid email address.")
    if kind == "url" and not URL_RE.match(text):
        raise ValueError("Links must start with http:// or https://")
    if kind == "select":
        if text not in (field.options or []):
            raise ValueError("Choose one of the listed options.")
        return text

    limit = 10_000 if kind == "textarea" else 500
    if len(text) > limit:
        raise ValueError(f"Use {limit:,} characters or fewer.")
    return text


def resolve_extra(
    db: Session,
    group_id: int | None,
    submitted: dict[str, Any],
    existing: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Merge submitted custom values into existing ones.

    Only fields that apply to the person's group are read from the submission.
    Values for fields belonging to other groups are kept, so moving someone
    between groups and back doesn't lose data. Keys with no field definition
    are dropped.
    """
    fields = list(db.scalars(select(CustomField)))
    known = {f.key for f in fields}
    existing = existing or {}
    result = {k: v for k, v in existing.items() if k in known}
    errors: dict[str, str] = {}

    for field in fields:
        if field.group_id is not None and field.group_id != group_id:
            continue
        error_key = f"extra.{field.key}"
        if field.key in submitted:
            raw = submitted[field.key]
            if field.field_type == "select" and raw == existing.get(field.key):
                value = raw  # keep a value whose dropdown option was later removed
            else:
                try:
                    value = coerce_value(field, raw)
                except ValueError as exc:
                    errors[error_key] = str(exc)
                    continue
            if value is None:
                result.pop(field.key, None)
            else:
                result[field.key] = value
        if field.required and field.field_type != "checkbox" and result.get(field.key) in (None, ""):
            errors.setdefault(error_key, "This field is required.")

    return result, errors


def strip_extra_keys(db: Session, keys: set[str]) -> None:
    """Remove stored values for deleted fields from every person."""
    if not keys:
        return
    for person in db.scalars(select(Person)):
        if person.extra and keys & person.extra.keys():
            person.extra = {k: v for k, v in person.extra.items() if k not in keys}


# ---- search and export ------------------------------------------------------


def search_text(person: Person, group_names: dict[int, str]) -> str:
    parts: list[Any] = [
        person.identifier, person.first_name, person.last_name, person.preferred_name,
        person.job_title, person.role, person.email, person.phone,
        group_names.get(person.group_id) if person.group_id else None,
    ]
    parts.extend(v for v in (person.extra or {}).values() if not isinstance(v, bool))
    return " ".join(str(p) for p in parts if p not in (None, "")).lower()


def csv_cell(value: Any) -> str:
    """Stringify for CSV and neutralise spreadsheet formula injection."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value)
    if text[:1] in ("=", "@", "\t", "\r") or (text[:1] in ("+", "-") and not PHONE_LIKE.match(text)):
        return "'" + text
    return text
