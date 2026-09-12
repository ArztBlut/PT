"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import session_fingerprint


def session_user(request: Request, db: Session) -> User | None:
    uid = request.session.get("uid")
    if not isinstance(uid, int):
        return None
    user = db.get(User, uid)
    if user is None or request.session.get("fp") != session_fingerprint(user.password_hash):
        return None
    return user


def start_session(request: Request, user: User) -> None:
    request.session.clear()
    request.session["uid"] = user.id
    request.session["fp"] = session_fingerprint(user.password_hash)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = session_user(request, db)
    if user is None:
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    return user


def get_or_404(db: Session, model: type, object_id: int, label: str):
    obj = db.get(model, object_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found.")
    return obj
