from __future__ import annotations

from collections.abc import Mapping, Sequence


SENSITIVE_KEY_PARTS = {
    "address",
    "allerg",
    "blood",
    "contact",
    "date_of_birth",
    "diagnosis",
    "dob",
    "emergency",
    "handover",
    "identifier",
    "medication",
    "name",
    "next_of_kin",
    "notes",
    "patient",
    "phone",
    "vitals",
}


def redact_sensitive(value):
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in SENSITIVE_KEY_PARTS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive(item)
        return redacted
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_sensitive(item) for item in value]
    return value
