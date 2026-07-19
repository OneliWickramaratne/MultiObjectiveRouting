from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import (
    CSRF_COOKIE,
    REFRESH_COOKIE,
    authenticate_access_token,
    create_event_stream_ticket,
    create_session,
    hash_password,
    issue_access_token,
    rotate_session_tokens,
    user_summary,
    validate_refresh_session,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models import AuthSessionModel, UserModel
from app.schemas import AuthTokenResponse, EventStreamTicketResponse, LoginRequest, UserSummary


router = APIRouter()
_dummy_password_hash = hash_password("timing-equalization-password-only")


def _set_auth_cookies(response: Response, refresh_token: str, csrf_token: str) -> None:
    max_age = settings.auth_refresh_token_days * 24 * 60 * 60
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/api/auth",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth", secure=settings.auth_cookie_secure, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.auth_cookie_secure, samesite="strict")


def _token_response(user: UserModel, session: AuthSessionModel) -> AuthTokenResponse:
    return AuthTokenResponse(
        access_token=issue_access_token(user, session),
        expires_in=settings.auth_access_token_minutes * 60,
        user=UserSummary(**user_summary(user)),
    )


@router.post("/login", response_model=AuthTokenResponse)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    username = payload.username.strip().lower()
    user = db.query(UserModel).filter(func.lower(UserModel.username) == username).one_or_none()
    now = datetime.utcnow()
    if not user:
        verify_password(payload.password, _dummy_password_hash)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if user.locked_until and user.locked_until > now:
        verify_password(payload.password, _dummy_password_hash)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.is_active or not user.password_hash or not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.auth_max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.auth_lockout_minutes)
            user.failed_login_count = 0
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session, refresh_token, csrf_token = create_session(db, user, request.headers.get("user-agent"))
    db.commit()
    _set_auth_cookies(response, refresh_token, csrf_token)
    return _token_response(user, session)


@router.post("/refresh", response_model=AuthTokenResponse)
def refresh(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> AuthTokenResponse:
    user, session = validate_refresh_session(db, refresh_token, csrf_cookie, csrf_header)
    next_refresh_token, next_csrf_token = rotate_session_tokens(session)
    db.commit()
    _set_auth_cookies(response, next_refresh_token, next_csrf_token)
    return _token_response(user, session)


@router.post("/logout", status_code=204)
def logout(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Response:
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    _, session = authenticate_access_token(db, authorization)
    session.revoked_at = datetime.utcnow()
    db.commit()
    logout_response = Response(status_code=204)
    _clear_auth_cookies(logout_response)
    return logout_response


@router.get("/me", response_model=UserSummary)
def me(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> UserSummary:
    user, _ = authenticate_access_token(db, authorization)
    return UserSummary(**user_summary(user))


@router.post("/event-stream-ticket", response_model=EventStreamTicketResponse)
def event_stream_ticket(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> EventStreamTicketResponse:
    user, _ = authenticate_access_token(db, authorization)
    ticket = create_event_stream_ticket(db, user)
    db.commit()
    return EventStreamTicketResponse(ticket=ticket, expires_in=45)
