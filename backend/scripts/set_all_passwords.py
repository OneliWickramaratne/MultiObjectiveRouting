"""
Set EVERY user's password to the same value in one run — local dev/thesis
convenience only, never for production (that's what set_user_password.py's
interactive per-user flow is for).

Run inside the Docker container:

    docker compose exec -it backend python scripts/set_all_passwords.py devpass123456

Requires 12+ characters, same rule as set_user_password.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.auth import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import AuthSessionModel, UserModel  # noqa: E402
from app.time_utils import utcnow  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/set_all_passwords.py <new-password>")
    password = sys.argv[1]
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters.")

    with SessionLocal() as db:
        users = db.query(UserModel).all()
        if not users:
            print("No users found.")
            return
        hashed = hash_password(password)
        for user in users:
            user.username = user.username or user.id
            user.password_hash = hashed
            user.password_changed_at = utcnow()
            user.failed_login_count = 0
            user.locked_until = None
            user.is_active = True
        db.query(AuthSessionModel).filter(AuthSessionModel.revoked_at.is_(None)).update(
            {AuthSessionModel.revoked_at: utcnow()}, synchronize_session=False
        )
        db.commit()
        print(f"Password updated for {len(users)} users; all existing sessions were revoked.\n")
        for user in sorted(users, key=lambda u: u.role):
            print(f"  {user.username:30s} role={user.role}")


if __name__ == "__main__":
    main()
