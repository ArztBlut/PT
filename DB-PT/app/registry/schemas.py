"""Request bodies. Responses are plain dicts built in services.py."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

Status = Literal["active", "leave", "inactive"]
FieldType = Literal[
    "text", "textarea", "number", "date", "email", "phone", "url", "select", "checkbox"
]

HEX_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


# ---- auth and users ---------------------------------------------------------


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=10, max_length=1024)


class UserCreateIn(BaseModel):
    username: str
    password: str = Field(min_length=10, max_length=1024)

    @field_validator("username")
    @classmethod
    def check_username(cls, value: str) -> str:
        value = value.strip().lower()
        if not USERNAME.match(value):
            raise ValueError(
                "Use 3 to 64 lowercase letters, numbers, dots, dashes or underscores."
            )
        return value


class UserPasswordIn(BaseModel):
    password: str = Field(min_length=10, max_length=1024)


# ---- groups -----------------------------------------------------------------


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str | None = Field(default=None, max_length=16)
    description: str | None = Field(default=None, max_length=2000)
    colour: str = "#b9bcc4"
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)

    _strip_name = field_validator("name", mode="before")(_strip)
    _blank = field_validator("code", "description", mode="before")(_blank_to_none)

    @field_validator("code")
    @classmethod
    def upper_code(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("colour", mode="before")
    @classmethod
    def check_colour(cls, value: Any) -> str:
        if not isinstance(value, str) or not HEX_COLOUR.match(value.strip()):
            raise ValueError("Choose a colour.")
        return value.strip().lower()


# ---- custom fields ----------------------------------------------------------


class FieldIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    field_type: FieldType = "text"
    options: list[str] | None = Field(default=None, validate_default=True)
    required: bool = False
    show_in_table: bool = False
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    group_id: int | None = None

    _strip_label = field_validator("label", mode="before")(_strip)

    @field_validator("options")
    @classmethod
    def clean_options(cls, value: list[str] | None, info: ValidationInfo) -> list[str] | None:
        if info.data.get("field_type") != "select":
            return None
        cleaned: list[str] = []
        seen: set[str] = set()
        for option in value or []:
            option = option.strip()[:100]
            if option and option.lower() not in seen:
                seen.add(option.lower())
                cleaned.append(option)
        if not cleaned:
            raise ValueError("Add at least one option, one per line.")
        if len(cleaned) > 200:
            raise ValueError("Use 200 options or fewer.")
        return cleaned

    @field_validator("required")
    @classmethod
    def checkbox_not_required(cls, value: bool, info: ValidationInfo) -> bool:
        return False if info.data.get("field_type") == "checkbox" else value


# ---- personnel --------------------------------------------------------------


class PersonIn(BaseModel):
    identifier: str | None = Field(default=None, max_length=64)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    preferred_name: str | None = Field(default=None, max_length=100)
    job_title: str | None = Field(default=None, max_length=150)
    role: str | None = Field(default=None, max_length=150)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    status: Status = "active"
    start_date: date | None = None
    notes: str | None = Field(default=None, max_length=20_000)
    group_id: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    _strip_names = field_validator("first_name", "last_name", mode="before")(_strip)
    _blank = field_validator(
        "identifier", "preferred_name", "job_title", "role", "email", "phone",
        "notes", "start_date", mode="before",
    )(_blank_to_none)

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str | None) -> str | None:
        if value and not EMAIL.match(value):
            raise ValueError("Enter a valid email address.")
        return value
