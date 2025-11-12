from typing import TypedDict
from .transformers import json_transform, redact_text

class Decision(TypedDict, total=False):
    action: str           # "allow" | "modify" | "block"
    body: str
    notify: dict          # {"message": str}

def decide(mode: str, kind: str, url: str, body: str|None) -> Decision:
    """
    Centralized policy:
      - non-text: block in 'strict' and 'block'; allow-with-toast in 'warn'
      - text/json: redact email in 'warn' & 'strict'; block only when a violation exists in 'block'
    """
    # Non-text uploads
    if kind in ("binary", "multipart", "unknown"):
        if mode in ("strict", "block"):
            return {"action":"block","notify":{"message":"PrivPrompt: blocked non-text upload"}}
        return {"action":"allow","notify":{"message":"PrivPrompt: non-text payload (not inspected)"}}

    if not isinstance(body, str):
        return {"action": "allow"}

    # JSON-aware transform across leaves
    new_body, detections = json_transform(body, redact_text)
    has_violation = bool(detections)

    if mode == "block" and has_violation:
        return {"action":"block","notify":{"message":"PrivPrompt: blocked (privacy violation)"}}

    if new_body is not None:
        return {"action":"modify","body":new_body,"notify":{"message":"PrivPrompt: redacted sensitive text"}}

    return {"action":"allow"}
