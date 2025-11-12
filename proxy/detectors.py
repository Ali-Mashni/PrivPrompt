import re

# Extend these as you add more signals (phone, IP, card, JWT, API keys, etc.)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

def detect_all(text: str) -> list[str]:
    tags = []
    if EMAIL_RE.search(text):
        tags.append("email")
    return tags
