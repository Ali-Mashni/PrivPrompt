import re
from typing import TypedDict, List


class Detection(TypedDict):
    type: str
    start: int
    end: int
    value: str


# ========== REGEX PATTERNS ==========

# 1. Email
EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)

# Strict phone:
# - Local: must start with 05 and be exactly 10 digits (e.g. 0512341234)
# - International: must be + followed by exactly 12 digits (e.g. +966580360801)
PHONE_RE = re.compile(
    r"""
    (?<!\d)                 # don't be inside a longer digit sequence
    (
        05\d{8}             # local SA mobile: 05 + 8 digits = 10 digits total
        |
        \+\d{12}            # international: + followed by exactly 12 digits
    )
    (?!\d)                  # don't be inside a longer digit sequence
    """,
    re.VERBOSE,
)


# 3. IPv4
IPV4_RE = re.compile(
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
)

# 4. IPv6 (compressed/full – still a bit permissive but okay for now)
IPV6_RE = re.compile(
    r"\b(?:[A-Fa-f0-9]{1,4}:){7}[A-Fa-f0-9]{1,4}\b|\b(?:[A-Fa-f0-9]{1,4}:){1,7}:\b"
)

# 5. JWT token (header.payload.signature)
# Require:
#   - each part >= 10 chars
JWT_RE = re.compile(
    r"""
    \b
    (?=[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})   # length check
    (?=[A-Za-z0-9_.-]*[A-Za-z][A-Za-z0-9_.-]*)                       # at least one letter
    [A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+
    \b
    """,
    re.VERBOSE,
)

# 6. Generic API keys (unchanged for now)
API_KEY_RE = re.compile(
    r"\b[A-Za-z0-9]{20,64}\b"
)

# 7. National ID (example: Saudi ID: 10 digits, starts with 1 or 2)
NATIONAL_ID_RE = re.compile(
    r"\b[12]\d{9}\b"
)

# 8. Company names
COMPANY_RE = re.compile(
    r"\b([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)* )"
    r"(Company|Co\.|Corporation|Corp\.|Inc|Incorporated|LLC|Ltd)\b"
)


PATTERNS: dict[str, re.Pattern[str]] = {
    "email": EMAIL_RE,
    "phone": PHONE_RE,
    "ipv4": IPV4_RE,
    "ipv6": IPV6_RE,
    "jwt": JWT_RE,
    "api_key": API_KEY_RE,
    "national_id": NATIONAL_ID_RE,
    "company": COMPANY_RE,
}

## Main function from detectors.py
def detect_all(text: str) -> List[Detection]:
    """
    Return a list of detections:
      [
        {"type": "email", "start": 10, "end": 20, "value": "x@y.com"},
        {"type": "ipv4", "start": 50, "end": 60, "value": "192.168.1.1"},
        ...
      ]
    """

    detections: List[Detection] = []
    for dtype, pattern in PATTERNS.items():
        for m in pattern.finditer(text):
            detections.append(
                Detection(
                    type=dtype,
                    start=m.start(),
                    end=m.end(),
                    value=m.group(0),
                )
            )
    return detections


def detect_tags(text: str) -> List[str]:
    return list({d["type"] for d in detect_all(text)})
