"""
Behavior

- Non-text (images, pdf, audio/video, office, archives, multipart) OR JSON that *declares/embeds* non-text:
    • mode in {"strict","block"} -> BLOCK with toast "PrivPrompt: blocked non-text upload"
    • mode == "warn"             -> ALLOW with toast "PrivPrompt: allowed non-text upload"

- Plain text / JSON (no binary declared/embedded):
    • Use json_transform + redact_text (your existing transformers)
    • In mode == "block", block only if violations were detected
    • In warn/strict, allow/modify (redacted) like your current behavior

"""

from __future__ import annotations
import json
import re
import binascii
from typing import TypedDict, Optional, Any

# ---------- Constants ---------------------------------------------------------

#For warn mode
NON_TEXT_TOAST = "PrivPrompt: allowed non-text upload"

# Common binary extensions
_BINARY_EXTS = (
    ".png",".jpg",".jpeg",".gif",".webp",".tif",".tiff",".bmp",".heic",".heif",
    ".pdf",
    ".zip",".rar",".7z",".tar",".gz",".bz2",".xz",
    ".mp4",".mov",".avi",".mkv",".webm",".wmv",".m4v",
    ".wav",".mp3",".m4a",".aac",".flac",".ogg",".opus",
    ".doc",".docx",".ppt",".pptx",".xls",".xlsx",".rtf",".odt",".ods",".odp",
)

# Data URL detector
_DATA_URL_RE = re.compile(r'^data:([^;,\s]+);base64,([A-Za-z0-9+/=\s]+)$', re.IGNORECASE)

# Suspect JSON keys that often carry binary payloads
_SUSPECT_KEYS = {
    "file", "files", "file_id", "file_ids", "fileId", "fileIds",
    "upload_id", "uploadId", "asset_pointer", "assetPointer",
    "file_token", "fileToken",
    "data", "content", "bytes", "blob",
    "image", "image_url", "imageUrl",
    "media", "attachment", "attachments", "payload", "buffer", "body",
    "url", "src", "filename", "file_name",
    "mime", "mime_type", "mimetype", "content_type", "mimeType",
    "type",  # e.g., "input_image", "input_audio", etc.
}

# Quick base64 signatures to short-circuit decoding
_BASE64_SNIFFERS = (
    ("image/jpeg", re.compile(r"/9j/")),               # JPEG
    ("image/png",  re.compile(r"iVBORw0KGgo")),        # PNG
    ("image/gif",  re.compile(r"R0lGODdh|R0lGODlh")),  # GIF
    ("image/webp", re.compile(r"UklGR")),              # RIFF/WEBP (weak)
    ("application/pdf", re.compile(r"JVBERi0x")),      # %PDF-
)

# ---------- Types -------------------------------------------------------------

class Decision(TypedDict, total=False):
    action: str            # "allow" | "modify" | "block"
    body: str              # for modified text/json
    notify: dict           # {"message": str}

# ---------- Utilities ---------------------------------------------------------

def _is_probably_base64(s: str) -> bool:
    # Coarse filter: charset + length + padding sanity
    if len(s) < 128:
        return False
    if not re.fullmatch(r"[A-Za-z0-9+/=\s]+", s):
        return False
    if s.count("=") > 2:
        return False
    return True

def _b64_to_bytes(s: str) -> Optional[bytes]:
    try:
        return binascii.a2b_base64(s)
    except Exception:
        return None

def _has_binary_magic(b: bytes) -> bool:
    # PNG
    if b.startswith(b"\x89PNG\r\n\x1a\n"): return True
    # JPEG
    if b.startswith(b"\xff\xd8\xff"): return True
    # GIF
    if b.startswith(b"GIF87a") or b.startswith(b"GIF89a"): return True
    # WEBP (RIFF....WEBP)
    if len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP": return True
    # PDF
    if b.startswith(b"%PDF-"): return True
    # ZIP/Office
    if b.startswith(b"PK\x03\x04"): return True
    return False

def _mime_is_binary(s: str) -> bool:
    s = s.lower()
    return (
        s.startswith(("image/", "audio/", "video/"))
        or s in ("application/pdf",)
    )

def _looks_non_text(content_type: Optional[str], filename: Optional[str], body: Optional[str|bytes]) -> bool:
    # If it's bytes, it's non-text
    if isinstance(body, (bytes, bytearray)):
        return True

    ct = (content_type or "").lower()
    if ct.startswith(("image/","audio/","video/")):
        return True
    if ct in {"application/pdf"}:
        return True
    if "multipart/form-data" in ct:
        return True

    fn = (filename or "").lower()
    if fn.endswith(_BINARY_EXTS):
        return True

    return False

# ---------- JSON Binary Detection --------------------------------------------

def _json_declares_or_embeds_binary(obj: Any) -> bool:
    """
    Returns True if JSON either:
      - embeds binary via data URLs/base64 that decode to known binary signatures, OR
      - declares/points to binary attachments via common schema patterns used by chat payloads.
    """
    # Strings
    if isinstance(obj, str):
        # data URL
        m = _DATA_URL_RE.match(obj.strip())
        if m:
            b = _b64_to_bytes(m.group(2))
            return bool(b and _has_binary_magic(b))
        # large base64 anywhere
        if _is_probably_base64(obj):
            for _, pat in _BASE64_SNIFFERS:
                if pat.search(obj):
                    return True
            b = _b64_to_bytes(obj)
            return bool(b and _has_binary_magic(b))
        return False

    # Lists
    if isinstance(obj, list):
        return any(_json_declares_or_embeds_binary(v) for v in obj)

    # Dicts
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()

            # Recurse first (nested structures often hide payloads)
            if _json_declares_or_embeds_binary(v):
                return True

            # Skip keys we don't care about quickly
            if kl not in _SUSPECT_KEYS:
                continue

            # Attachment-ish containers
            if kl in {
                "attachments","files","file_ids","fileids","file_id","upload_id",
                "asset_pointer","assetpointer","file_token","filetoken",
                "image","image_url","imageurl","media","payload","blob"
            }:
                return True

            # MIME hints
            if kl in {"mime","mime_type","mimetype","content_type","mimetype","mimetype"} and isinstance(v, str):
                if _mime_is_binary(v):
                    return True

            # Part "type" fields used by multi-modal chat payloads
            if kl == "type" and isinstance(v, str) and v.lower() in {
                "input_image","image","input_audio","audio","input_video","video","file"
            }:
                return True

            # Filename / URL heuristics
            if kl in {"filename","file_name"} and isinstance(v, str) and v.lower().endswith(_BINARY_EXTS):
                return True
            if kl in {"url","src"} and isinstance(v, str):
                vl = v.lower()
                if vl.startswith(("blob:", "file:")) or vl.endswith(_BINARY_EXTS):
                    return True

            # Nested object resembling an attachment record
            if isinstance(v, dict):
                mt = v.get("mime") or v.get("mime_type") or v.get("mimetype") or v.get("content_type") or v.get("mimeType")
                if isinstance(mt, str) and _mime_is_binary(mt):
                    return True
                fn = v.get("filename") or v.get("file_name")
                if isinstance(fn, str) and fn.lower().endswith(_BINARY_EXTS):
                    return True
                u = v.get("url") or v.get("src")
                if isinstance(u, str):
                    ul = u.lower()
                    if ul.startswith(("blob:", "file:")) or ul.endswith(_BINARY_EXTS):
                        return True

        return False

    # Anything else
    return False

# ---------- Main Policy -------------------------------------------------------

def decide(
    mode: str,
    kind: str,
    url: str,
    body: Optional[str | bytes],
    *,
    content_type: Optional[str] = None,
    filename: Optional[str] = None
) -> Decision:
    """
    Centralized policy:

      Non-text (or JSON that declares/embeds non-text):
        - 'strict' & 'block'  -> {"action":"block","notify":{"message": NON_TEXT_TOAST}}
        - 'warn'              -> {"action":"allow","notify":{"message": NON_TEXT_TOAST}}

      Plain text/JSON (no binary):
        - Use json_transform + redact_text.
        - In 'block', block only if violations were detected.
    """
    mode = (mode or "").lower()
    kind = (kind or "").lower()

    # 1) Obvious non-text by MIME/ext/bytes
    if _looks_non_text(content_type, filename, body):
        if mode in ("strict", "block"):
            return {"action": "block", "notify": {"message": NON_TEXT_TOAST}}
        return {"action": "allow", "notify": {"message": NON_TEXT_TOAST}}

    # 2) From here, treat non-str as suspect fallback
    if not isinstance(body, str):
        if mode in ("strict", "block"):
            return {"action": "block", "notify": {"message": NON_TEXT_TOAST}}
        return {"action": "allow", "notify": {"message": NON_TEXT_TOAST}}

    # 3) JSON that *declares/embeds* binary even without base64 bytes in this request
    is_json = False
    parsed = None
    try:
        parsed = json.loads(body)
        is_json = True
    except Exception:
        is_json = False

    if is_json and _json_declares_or_embeds_binary(parsed):
        if mode in ("strict", "block"):
            return {"action": "block", "notify": {"message": NON_TEXT_TOAST}}
        return {"action": "allow", "notify": {"message": NON_TEXT_TOAST}}

    # 4) Plain text / safe JSON path: reuse your transformers
    try:
        from .transformers import json_transform, redact_text  # your implementations
    except Exception:
        # Safe fallbacks if your module isn't importable (no-ops)
        def redact_text(x: str) -> str: return x
        def json_transform(x: str, _redactor) -> tuple[str, list]:
            return x, []

    if is_json:
        new_body, detections = json_transform(body, redact_text)
        has_violation = bool(detections)
        if mode == "block" and has_violation:
            return {"action": "block", "notify": {"message": "PrivPrompt: blocked (privacy violation)"}}
        if new_body is not None and new_body != body:
            return {"action": "modify", "body": new_body, "notify": {"message": "PrivPrompt: redacted sensitive text"}}
        return {"action": "allow"}

    # Plain text (not JSON)
    new_text = redact_text(body)
    if mode == "block" and new_text != body:
        return {"action": "block", "notify": {"message": "PrivPrompt: blocked (privacy violation)"}}
    if new_text != body:
        return {"action": "modify", "body": new_text, "notify": {"message": "PrivPrompt: redacted sensitive text"}}
    return {"action": "allow"}
