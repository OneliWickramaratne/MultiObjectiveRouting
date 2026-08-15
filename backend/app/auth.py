from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import Depends, Header, HTTPException
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import AuthSessionModel, EventStreamTicketModel, UserModel
from app.time_utils import utcnow


REFRESH_COOKIE = "icu_refresh"
CSRF_COOKIE = "icu_csrf"
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return password_hash.verify(password, encoded_hash)
    except Exception:
        return False


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def user_summary(user: UserModel) -> dict[str, str | None]:
    return {
        "id": user.id,
        "name": user.name,
        "role": user.role,
        "hospital_id": user.hospital_id,
        "ambulance_id": user.ambulance_id,
    }


def issue_access_token(user: UserModel, session: AuthSessionModel) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.auth_access_token_minutes)
    return jwt.encode(
        {
            "sub": user.id,
            "sid": session.id,
            "jti": str(uuid4()),
            "type": "access",
            "iat": now,
            "nbf": now,
            "exp": expires_at,
            "iss": settings.auth_jwt_issuer,
            "aud": settings.auth_jwt_audience,
        },
        settings.auth_jwt_secret,
        algorithm="HS256",
    )


def create_session(db: Session, user: UserModel, user_agent: str | None = None) -> tuple[AuthSessionModel, str, str]:
    session_id = str(uuid4())
    refresh_secret = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    refresh_token = f"{session_id}.{refresh_secret}"
    now = utcnow()
    session = AuthSessionModel(
        id=session_id,
        user_id=user.id,
        refresh_token_hash=_token_hash(refresh_token),
        csrf_token_hash=_token_hash(csrf_token),
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=settings.auth_refresh_token_days),
        user_agent=(user_agent or "")[:500] or None,
    )
    db.add(session)
    db.flush()
    return session, refresh_token, csrf_token


def rotate_session_tokens(session: AuthSessionModel) -> tuple[str, str]:
    refresh_token = f"{session.id}.{secrets.token_urlsafe(48)}"
    csrf_token = secrets.token_urlsafe(32)
    session.refresh_token_hash = _token_hash(refresh_token)
    session.csrf_token_hash = _token_hash(csrf_token)
    session.last_used_at = utcnow()
    return refresh_token, csrf_token


def parse_refresh_session_id(refresh_token: str) -> str | None:
    session_id, separator, _ = refresh_token.partition(".")
    return session_id if separator and session_id else None


def validate_refresh_session(
    db: Session,
    refresh_token: str | None,
    csrf_cookie: str | None,
    csrf_header: str | None,
) -> tuple[UserModel, AuthSessionModel]:
    if not refresh_token or not csrf_cookie or not csrf_header:
        raise _authentication_error()
    if not hmac.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    session_id = parse_refresh_session_id(refresh_token)
    session = db.get(AuthSessionModel, session_id) if session_id else None
    now = utcnow()
    if not session or session.revoked_at or session.expires_at <= now:
        raise _authentication_error()
    if not hmac.compare_digest(session.refresh_token_hash, _token_hash(refresh_token)):
        session.revoked_at = now
        db.commit()
        raise _authentication_error()
    if not hmac.compare_digest(session.csrf_token_hash, _token_hash(csrf_header)):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    user = db.get(UserModel, session.user_id)
    if not user or not user.is_active:
        raise _authentication_error()
    return user, session


def authenticate_access_token(db: Session, authorization: str | None) -> tuple[UserModel, AuthSessionModel]:
    if not authorization or not authorization.startswith("Bearer "):
        raise _authentication_error()
    token = authorization[7:].strip()
    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=["HS256"],
            issuer=settings.auth_jwt_issuer,
            audience=settings.auth_jwt_audience,
            options={"require": ["sub", "sid", "jti", "type", "iat", "nbf", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise _authentication_error() from exc
    if payload.get("type") != "access":
        raise _authentication_error()
    session = db.get(AuthSessionModel, str(payload["sid"]))
    now = utcnow()
    if not session or session.user_id != payload["sub"] or session.revoked_at or session.expires_at <= now:
        raise _authentication_error()
    user = db.get(UserModel, str(payload["sub"]))
    if not user or not user.is_active:
        raise _authentication_error()
    return user, session


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> UserModel:
    user, _ = authenticate_access_token(db, authorization)
    return user


def create_event_stream_ticket(db: Session, user: UserModel) -> str:
    ticket_id = str(uuid4())
    ticket = f"{ticket_id}.{secrets.token_urlsafe(32)}"
    now = utcnow()
    db.add(
        EventStreamTicketModel(
            id=ticket_id,
            user_id=user.id,
            token_hash=_token_hash(ticket),
            created_at=now,
            expires_at=now + timedelta(seconds=45),
        )
    )
    db.flush()
    return ticket


def consume_event_stream_ticket(db: Session, ticket: str) -> UserModel:
    ticket_id, separator, _ = ticket.partition(".")
    row = db.get(EventStreamTicketModel, ticket_id) if separator else None
    now = utcnow()
    if (
        not row
        or row.used_at is not None
        or row.expires_at <= now
        or not hmac.compare_digest(row.token_hash, _token_hash(ticket))
    ):
        raise _authentication_error()
    user = db.get(UserModel, row.user_id)
    if not user or not user.is_active:
        raise _authentication_error()
    row.used_at = now
    db.commit()
    return user


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_super_admin(user: UserModel) -> None:
    if user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")


def require_hospital_scope(user: UserModel, hospital_id: str) -> None:
    if user.role == "super_admin":
        return
    if user.role != "hospital_admin" or user.hospital_id != hospital_id:
        raise HTTPException(status_code=403, detail="Hospital admin scope required")
