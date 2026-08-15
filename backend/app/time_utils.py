from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime.

    Every ``DateTime`` column in :mod:`app.models` is declared without
    ``timezone=True``, so the database round-trips naive values. Stripping the
    tzinfo here keeps stored timestamps directly comparable with each other and
    with the values this function returns; mixing in aware datetimes would make
    those comparisons raise ``TypeError``.

    This replaces ``datetime.utcnow()``, which is deprecated and scheduled for
    removal, while keeping exactly the same naive-UTC semantics.
    """
    return datetime.now(UTC).replace(tzinfo=None)
