import json
from typing import List

from .detectors import (
    EMAIL_RE,
    PHONE_RE,
    IPV4_RE,
    IPV6_RE,
    JWT_RE,
    API_KEY_RE,
    NATIONAL_ID_RE,
    COMPANY_RE,
)

# ========== HELPER FUNCTIONS ==========

def mask_keep_last_n(value: str, n: int) -> str:
    """
    Mask all characters except the last n with '*'.
    """
    length = len(value)
    if length <= n:
        return "*" * length
    return "*" * (length - n) + value[-n:]


def mask_ipv4(ip: str) -> str:
    """
    Anonymize IPv4 by masking the host portion.
    '192.168.1.25' -> '192.168.xxx.xxx'
    """
    parts = ip.split(".")
    if len(parts) != 4:
        # Fallback to generic placeholder if something is wrong
        return "{{IPV4}}"
    return ".".join(parts[:2] + ["xxx", "xxx"])


def mask_ipv6(_: str) -> str:
    return "{{IPV6}}"


def mask_jwt(_: str) -> str:
    """
    Fully redact.
    """
    return "{{JWT}}"


def mask_email(_: str) -> str:
    """
    Emails are fully redacted.
    """
    return "{{EMAIL}}"


def mask_api_key(key: str) -> str:
    """
    Generic API keys: keep only last 4 characters.
    """
    return mask_keep_last_n(key, 4)


def mask_phone(phone: str) -> str:
    """
    Phone numbers: mask everything except last 4 digits.
    Works for both local (05xxxxxxxx) and international (+XXXXXXXXXXXX).
    """
    return mask_keep_last_n(phone, 4)


def mask_national_id(nid: str) -> str:
    """
    National IDs: same rule – keep only the last 4.
    '1234567890' -> '******7890'
    """
    return mask_keep_last_n(nid, 4)

def redact_text(text: str, detections_out: list[str]) -> str:
    """Redact email, record detection tags into detections_out."""
    changed = text
    if EMAIL_RE.search(changed):
        detections_out.append("email")
        changed = EMAIL_RE.sub("{{EMAIL}}", changed)
    return changed

def json_transform(body_str: str, transform) -> tuple[str|None, list[str]]:
    """
    Walk strings in a JSON body and apply `transform` (e.g., redact_text).
    Returns (new_body_or_none, detections).
    If `body_str` is not JSON, treat it as plain text.
    """
    detections: list[str] = []
    try:
        obj = json.loads(body_str)
    except Exception:
        # Not JSON, treat it as text
        new = transform(body_str, detections)
        return (new if new != body_str else None), detections

    def walk(x):
        if isinstance(x, str):
            return transform(x, detections)
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        return x

    obj2 = walk(obj)
    if obj2 == obj:
        return None, detections
    return json.dumps(obj2, ensure_ascii=False, separators=(",", ":")), detections
