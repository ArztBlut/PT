"""Personnel records."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, get_or_404
from ..errors import FormError
from ..models import CustomField, Group, Person
from ..schemas import PersonIn
from ..services import csv_cell, person_to_dict, resolve_extra, search_text, sorted_fields

router = APIRouter(prefix="/api/personnel", tags=["personnel"], dependencies=[Depends(current_user)])

StatusFilter = Literal["all", "active", "leave", "inactive"]


def _query_people(db: Session, group: str, status_filter: str, q: str | None) -> list[Person]:
    stmt = select(Person)
    if group == "unassigned":
        stmt = stmt.where(Person.group_id.is_(None))
    elif group != "all":
        if not group.isdecimal():
            raise HTTPException(
                422,
                "group must be 'all', 'unassigned' or a group id.",
            )
        stmt = stmt.where(Person.group_id == int(group))
    if status_filter != "all":
        stmt = stmt.where(Person.status == status_filter)
    people = list(db.scalars(stmt.order_by(Person.last_name, Person.first_name, Person.id)))

    terms = (q or "").lower().split()
    if terms:
        names = {gid: name for gid, name in db.execute(select(Group.id, Group.name))}
        haystacks = ((p, search_text(p, names)) for p in people)
        people = [p for p, text in haystacks if all(t in text for t in terms)]
    return people


def _validate(db: Session, payload: PersonIn, person: Person | None) -> dict:
    errors: dict[str, str] = {}
    if payload.group_id is not None and db.get(Group, payload.group_id) is None:
        errors["group_id"] = "That group no longer exists."
    if payload.identifier:
        stmt = select(Person.id).where(func.lower(Person.identifier) == payload.identifier.lower())
        if person is not None:
            stmt = stmt.where(Person.id != person.id)
        if db.scalar(stmt) is not None:
            errors["identifier"] = "Another person already has this ID."
    extra, extra_errors = resolve_extra(
        db, payload.group_id, payload.extra, person.extra if person else {}
    )
    errors.update(extra_errors)
    if errors:
        raise FormError(errors)
    return extra


@router.get("")
def list_personnel(
    group: str = "all",
    status: StatusFilter = "all",
    q: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    return [person_to_dict(p) for p in _query_people(db, group, status, q)]


@router.get("/export.csv")
def export_personnel(
    group: str = "all",
    status: StatusFilter = "all",
    q: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    people = _query_people(db, group, status, q)
    group_names = {gid: name for gid, name in db.execute(select(Group.id, Group.name))}
    fields: list[CustomField] = sorted_fields(db)
    if group.isdecimal():
        fields = [f for f in fields if f.group_id in (None, int(group))]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "ID", "First name", "Last name", "Preferred name", "Job title", "Role", "Email",
        "Phone", "Status", "Start date", "Group", "Notes", *[f.label for f in fields],
        "Created (UTC)", "Updated (UTC)",
    ])
    for p in people:
        extra = p.extra or {}
        writer.writerow([csv_cell(v) for v in [
            p.identifier, p.first_name, p.last_name, p.preferred_name, p.job_title, p.role,
            p.email, p.phone, p.status, p.start_date.isoformat() if p.start_date else None,
            group_names.get(p.group_id) if p.group_id else None, p.notes,
            *[extra.get(f.key) for f in fields],
            p.created_at.isoformat(sep=" "), p.updated_at.isoformat(sep=" "),
        ]])

    filename = f"personnel-{datetime.now():%Y%m%d-%H%M}.csv"
    return Response(
        content="\ufeff" + buffer.getvalue(),  # BOM so Excel reads UTF-8 correctly
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{person_id}")
def get_person(person_id: int, db: Session = Depends(get_db)) -> dict:
    return person_to_dict(get_or_404(db, Person, person_id, "Person"))


@router.post("", status_code=201)
def create_person(payload: PersonIn, db: Session = Depends(get_db)) -> dict:
    extra = _validate(db, payload, None)
    person = Person(**payload.model_dump(exclude={"extra"}), extra=extra)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person_to_dict(person)


@router.put("/{person_id}")
def update_person(person_id: int, payload: PersonIn, db: Session = Depends(get_db)) -> dict:
    person = get_or_404(db, Person, person_id, "Person")
    extra = _validate(db, payload, person)
    for key, value in payload.model_dump(exclude={"extra"}).items():
        setattr(person, key, value)
    person.extra = extra
    db.commit()
    db.refresh(person)
    return person_to_dict(person)


@router.delete("/{person_id}", status_code=204)
def delete_person(person_id: int, db: Session = Depends(get_db)) -> Response:
    person = get_or_404(db, Person, person_id, "Person")
    db.delete(person)
    db.commit()
    return Response(status_code=204)
