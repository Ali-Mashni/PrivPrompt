import json
from .detectors import EMAIL_RE

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
