"""Groups shown in the side menu."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, get_or_404
from ..errors import FormError
from ..models import CustomField, Group, Person, utcnow
from ..schemas import GroupIn
from ..services import group_to_dict, strip_extra_keys

router = APIRouter(prefix="/api/groups", tags=["groups"], dependencies=[Depends(current_user)])


def _member_counts(db: Session) -> dict[int | None, int]:
    rows = db.execute(select(Person.group_id, func.count(Person.id)).group_by(Person.group_id))
    return {group_id: count for group_id, count in rows}


def _check_name(db: Session, name: str, exclude_id: int | None = None) -> None:
    stmt = select(Group.id).where(func.lower(Group.name) == name.lower())
    if exclude_id is not None:
        stmt = stmt.where(Group.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise FormError({"name": "A group with this name already exists."}, status_code=409)


@router.get("")
def list_groups(db: Session = Depends(get_db)) -> dict:
    counts = _member_counts(db)
    groups = db.scalars(select(Group).order_by(Group.sort_order, Group.name))
    return {
        "groups": [group_to_dict(g, counts.get(g.id, 0)) for g in groups],
        "total": sum(counts.values()),
        "unassigned": counts.get(None, 0),
    }


@router.post("", status_code=201)
def create_group(payload: GroupIn, db: Session = Depends(get_db)) -> dict:
    _check_name(db, payload.name)
    group = Group(**payload.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    return group_to_dict(group, 0)


@router.put("/{group_id}")
def update_group(group_id: int, payload: GroupIn, db: Session = Depends(get_db)) -> dict:
    group = get_or_404(db, Group, group_id, "Group")
    _check_name(db, payload.name, exclude_id=group_id)
    for key, value in payload.model_dump().items():
        setattr(group, key, value)
    db.commit()
    db.refresh(group)
    return group_to_dict(group, _member_counts(db).get(group.id, 0))


@router.delete("/{group_id}", status_code=204)
def delete_group(
    group_id: int,
    reassign_to: int | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Delete a group. Members move to `reassign_to`, or become unassigned.

    Custom fields that belong only to this group are deleted with their values.
    """
    group = get_or_404(db, Group, group_id, "Group")
    if reassign_to is not None:
        if reassign_to == group_id:
            raise HTTPException(422, "Choose a different group to move members to.")
        if db.get(Group, reassign_to) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "The group to move members to no longer exists.")

    field_keys = set(db.scalars(select(CustomField.key).where(CustomField.group_id == group_id)))
    db.execute(
        update(Person)
        .where(Person.group_id == group_id)
        .values(group_id=reassign_to, updated_at=utcnow())
    )
    strip_extra_keys(db, field_keys)
    db.execute(delete(CustomField).where(CustomField.group_id == group_id))
    db.delete(group)
    db.commit()
    return Response(status_code=204)
