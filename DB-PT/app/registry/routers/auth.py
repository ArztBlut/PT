"""Sign in, sign out and password changes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, start_session
from ..errors import FormError
from ..models import User, utcnow
from ..schemas import LoginIn, PasswordChangeIn
from ..security import DUMMY_HASH, LoginThrottle, hash_password, needs_rehash, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
throttle = LoginThrottle()


@router.post("/login")
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict:
    username = payload.username.strip().lower()
    client = request.client.host if request.client else "unknown"
    key = f"{client}|{username}"
    if throttle.blocked(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed sign-in attempts. Wait 15 minutes and try again.",
        )

    user = db.scalar(select(User).where(User.username == username))
    valid = verify_password(user.password_hash if user else DUMMY_HASH, payload.password)
    if user is None or not valid:
        throttle.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password.")

    throttle.clear(key)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    user.last_login_at = utcnow()
    db.commit()
    start_session(request, user)
    return {"id": user.id, "username": user.username}


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"id": user.id, "username": user.username}


@router.post("/password", status_code=204)
def change_password(
    payload: PasswordChangeIn,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    if not verify_password(user.password_hash, payload.current_password):
        raise FormError({"current_password": "That isn't your current password."})
    if payload.new_password == payload.current_password:
        raise FormError({"new_password": "Choose a password you haven't just used."})
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    start_session(request, user)  # keep this session, sign out the others
    return Response(status_code=204)
