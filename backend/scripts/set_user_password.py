from __future__ import annotations

import argparse
from datetime import datetime
from getpass import getpass
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.auth import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import AuthSessionModel, UserModel  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Set or rotate an ICU DSS user password.")
    parser.add_argument("username", help="Existing username or user ID")
    args = parser.parse_args()

    first = getpass("New password: ")
    second = getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords do not match.")
    if len(first) < 12:
        raise SystemExit("Password must contain at least 12 characters.")

    with SessionLocal() as db:
        user = (
            db.query(UserModel)
            .filter((UserModel.username == args.username) | (UserModel.id == args.username))
            .one_or_none()
        )
        if not user:
            raise SystemExit(f"User {args.username!r} was not found.")
        user.username = user.username or user.id
        user.password_hash = hash_password(first)
        user.password_changed_at = datetime.utcnow()
        user.failed_login_count = 0
        user.locked_until = None
        user.is_active = True
        db.query(AuthSessionModel).filter(
            AuthSessionModel.user_id == user.id,
            AuthSessionModel.revoked_at.is_(None),
        ).update({AuthSessionModel.revoked_at: datetime.utcnow()}, synchronize_session=False)
        db.commit()
        print(f"Password updated for {user.username}; existing sessions were revoked.")


if __name__ == "__main__":
    main()
