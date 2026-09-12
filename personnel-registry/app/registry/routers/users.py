"""Accounts that can sign in to the registry."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, get_or_404, start_session
from ..errors import FormError
from ..models import User
from ..schemas import UserCreateIn, UserPasswordIn
from ..security import hash_password
from ..services import user_to_dict

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(current_user)])


@router.get("")
def list_users(db: Session = Depends(get_db)) -> list[dict]:
    return [user_to_dict(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("", status_code=201)
def create_user(payload: UserCreateIn, db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(User.id).where(User.username == payload.username)) is not None:
        raise FormError({"username": "That username is already taken."}, status_code=409)
    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


@router.put("/{user_id}/password", status_code=204)
def reset_password(
    user_id: int,
    payload: UserPasswordIn,
    request: Request,
    me: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    user = get_or_404(db, User, user_id, "User")
    user.password_hash = hash_password(payload.password)
    db.commit()
    if user.id == me.id:
        start_session(request, user)
    return Response(status_code=204)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int, me: User = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    if user_id == me.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't delete the account you're signed in with.")
    user = get_or_404(db, User, user_id, "User")
    db.delete(user)
    db.commit()
    return Response(status_code=204)
