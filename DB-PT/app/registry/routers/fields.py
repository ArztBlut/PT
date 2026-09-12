"""Custom field definitions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, get_or_404
from ..errors import FormError
from ..models import CustomField, Group
from ..schemas import FieldIn
from ..services import field_to_dict, make_field_key, sorted_fields, strip_extra_keys

router = APIRouter(prefix="/api/fields", tags=["fields"], dependencies=[Depends(current_user)])


def _check_group(db: Session, group_id: int | None) -> None:
    if group_id is not None and db.get(Group, group_id) is None:
        raise FormError({"group_id": "That group no longer exists."})


@router.get("")
def list_fields(db: Session = Depends(get_db)) -> list[dict]:
    return [field_to_dict(f) for f in sorted_fields(db)]


@router.post("", status_code=201)
def create_field(payload: FieldIn, db: Session = Depends(get_db)) -> dict:
    _check_group(db, payload.group_id)
    existing_keys = set(db.scalars(select(CustomField.key)))
    field = CustomField(key=make_field_key(payload.label, existing_keys), **payload.model_dump())
    db.add(field)
    db.commit()
    db.refresh(field)
    return field_to_dict(field)


@router.put("/{field_id}")
def update_field(field_id: int, payload: FieldIn, db: Session = Depends(get_db)) -> dict:
    field = get_or_404(db, CustomField, field_id, "Field")
    _check_group(db, payload.group_id)
    # The key never changes, so stored values stay attached when a field is renamed.
    for key, value in payload.model_dump().items():
        setattr(field, key, value)
    db.commit()
    db.refresh(field)
    return field_to_dict(field)


@router.delete("/{field_id}", status_code=204)
def delete_field(field_id: int, db: Session = Depends(get_db)) -> Response:
    field = get_or_404(db, CustomField, field_id, "Field")
    strip_extra_keys(db, {field.key})
    db.delete(field)
    db.commit()
    return Response(status_code=204)
