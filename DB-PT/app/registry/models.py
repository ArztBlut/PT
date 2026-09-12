"""Database tables. Schema changes must ship with an Alembic migration in migrations/versions."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# JSONB on PostgreSQL, JSON (stored as LONGTEXT) on MariaDB.
JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    """Naive UTC timestamp, stored the same way on both engines."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class User(TimestampMixin, Base):
    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)


class AppSetting(Base):
    """Values the application generates and must keep, such as the session key."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class Group(TimestampMixin, Base):
    __tablename__ = "personnel_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(Text)
    colour: Mapped[str] = mapped_column(String(7), nullable=False, default="#b9bcc4")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CustomField(TimestampMixin, Base):
    """A field definition. Values live in Person.extra under the field's key."""

    __tablename__ = "custom_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    options: Mapped[list[str] | None] = mapped_column(JSONType)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    show_in_table: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # NULL means the field applies to every group.
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("personnel_groups.id", ondelete="CASCADE"), index=True
    )


class Person(TimestampMixin, Base):
    __tablename__ = "personnel"
    __table_args__ = (Index("ix_personnel_name", "last_name", "first_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    identifier: Mapped[str | None] = mapped_column(String(64), unique=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    preferred_name: Mapped[str | None] = mapped_column(String(100))
    job_title: Mapped[str | None] = mapped_column(String(150))
    role: Mapped[str | None] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    start_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("personnel_groups.id", ondelete="SET NULL"), index=True
    )
    extra: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
