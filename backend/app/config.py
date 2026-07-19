from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


def _nonnegative_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 0:
        raise RuntimeError(f"{name} must be zero or greater")
    return value


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    allow_default_dev_user: bool
    default_dev_user_id: str
    cors_allow_origin_regex: str
    db_pool_size: int
    db_max_overflow: int
    db_pool_timeout_seconds: int
    db_pool_recycle_seconds: int
    db_statement_timeout_ms: int
    db_idle_transaction_timeout_ms: int
    auth_jwt_secret: str
    auth_jwt_issuer: str
    auth_jwt_audience: str
    auth_access_token_minutes: int
    auth_refresh_token_days: int
    auth_cookie_secure: bool
    auth_max_failed_logins: int
    auth_lockout_minutes: int

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"


DEFAULT_SQLITE_PATH = Path(__file__).resolve().parents[1] / "hospital_dss_dev.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"


settings = Settings(
    app_env=os.getenv("APP_ENV", "development"),
    database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
    allow_default_dev_user=_truthy(os.getenv("ALLOW_DEFAULT_DEV_USER")),
    default_dev_user_id=os.getenv("DEFAULT_DEV_USER_ID", "super-admin"),
    cors_allow_origin_regex=os.getenv(
        "CORS_ALLOW_ORIGIN_REGEX",
        r"http://(127\.0\.0\.1|localhost):51[0-9][0-9]",
    ),
    db_pool_size=_positive_int("DB_POOL_SIZE", 10),
    db_max_overflow=_nonnegative_int("DB_MAX_OVERFLOW", 10),
    db_pool_timeout_seconds=_positive_int("DB_POOL_TIMEOUT_SECONDS", 10),
    db_pool_recycle_seconds=_positive_int("DB_POOL_RECYCLE_SECONDS", 1800),
    db_statement_timeout_ms=_positive_int("DB_STATEMENT_TIMEOUT_MS", 30000),
    db_idle_transaction_timeout_ms=_positive_int("DB_IDLE_TRANSACTION_TIMEOUT_MS", 30000),
    auth_jwt_secret=os.getenv("AUTH_JWT_SECRET", "development-only-auth-secret-change-before-production"),
    auth_jwt_issuer=os.getenv("AUTH_JWT_ISSUER", "icu-transfer-dss"),
    auth_jwt_audience=os.getenv("AUTH_JWT_AUDIENCE", "icu-transfer-web"),
    auth_access_token_minutes=_positive_int("AUTH_ACCESS_TOKEN_MINUTES", 10),
    auth_refresh_token_days=_positive_int("AUTH_REFRESH_TOKEN_DAYS", 7),
    auth_cookie_secure=_truthy(os.getenv("AUTH_COOKIE_SECURE", "0")),
    auth_max_failed_logins=_positive_int("AUTH_MAX_FAILED_LOGINS", 5),
    auth_lockout_minutes=_positive_int("AUTH_LOCKOUT_MINUTES", 15),
)


def validate_runtime_settings() -> None:
    if settings.is_production and settings.allow_default_dev_user:
        raise RuntimeError("ALLOW_DEFAULT_DEV_USER must be disabled in production.")
    if settings.is_production and settings.database_url.startswith("sqlite"):
        raise RuntimeError("Production must not use the local SQLite development database.")
    if settings.is_production and len(settings.auth_jwt_secret.encode("utf-8")) < 32:
        raise RuntimeError("AUTH_JWT_SECRET must contain at least 32 bytes in production.")
    if settings.is_production and settings.auth_jwt_secret.startswith(("development-only", "replace-with")):
        raise RuntimeError("AUTH_JWT_SECRET must be replaced in production.")
    if settings.is_production and not settings.auth_cookie_secure:
        raise RuntimeError("AUTH_COOKIE_SECURE must be enabled in production.")
