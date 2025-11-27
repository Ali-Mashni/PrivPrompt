import json
from typing import List, Tuple, Callable

from detectors import detect_all, Detection

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


def mask_company(_: str) -> str:
    """Company names: replace with generic placeholder."""
    return "{{COMPANY}}"


def _add_tag_once(tags: List[str], tag: str) -> None:
    """Append tag only if not already present."""
    if tag not in tags:
        tags.append(tag)


def _mask_value(det: Detection) -> str:
    """
    Given a single Detection, return its masked replacement string.
    """
    t = det["type"]
    v = det["value"]

    if t == "email":
        return mask_email(v)
    if t == "phone":
        return mask_phone(v)
    if t == "ipv4":
        return mask_ipv4(v)
    if t == "ipv6":
        return mask_ipv6(v)
    if t == "jwt":
        return mask_jwt(v)
    if t == "api_key":
        return mask_api_key(v)
    if t == "national_id":
        return mask_national_id(v)
    if t == "company":
        return mask_company(v)

    # Fallback: if some unknown type sneaks in, just return original
    return v


# ========= LOW-LEVEL STRING TRANSFORM (USES detect_all) =========

def redact_text(text: str, tags_out: List[str]) -> str:
    """
    Redact all supported PII types in a plain text string, using detect_all.

    - Uses detect_all(text) to get a list[Detection].
    - Builds a new redacted string based on those detections.
    - Populates tags_out with a list[str] of unique detection types.
    """

    detections = detect_all(text)  # List[Detection]

    if not detections:
        return text

    # Add detection types to tags_out
    for det in detections:
        _add_tag_once(tags_out, det["type"])

    # Sort detections by start index so we can rebuild the string
    detections_sorted = sorted(detections, key=lambda d: d["start"])

    parts: List[str] = []
    cursor = 0

    for det in detections_sorted:
        start = det["start"]
        end = det["end"]

        # If overlapping or out of order, skip this detection
        if start < cursor:
            continue

        # Add text before detection
        parts.append(text[cursor:start])
        # Add masked value
        parts.append(_mask_value(det))

        cursor = end

    # Add any remaining text after the last detection
    parts.append(text[cursor:])

    return "".join(parts)


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
