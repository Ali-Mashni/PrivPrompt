# proxy/app.py
import os, re, json, time, secrets
from typing import Dict, Any

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv("PP_PORT", "8787"))
UPSTREAM_CHATGPT = "https://chatgpt.com"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# ---- logging setup -----------------------------------------------------------
LOG_PATH = os.getenv("PP_LOG", os.path.join("proxy", "logs", "events.jsonl"))

def log_event(obj: dict) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

# -----------------------------------------------------------------------------

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE: Dict[str, Any] = {"salt": secrets.token_hex(8)}

@app.get("/healthz")
async def healthz():
    return PlainTextResponse("ok")

@app.get("/debug/echo")
async def debug_echo(request: Request):
    return JSONResponse({"method": request.method, "url": str(request.url)})

# ------------------------- /inspect (mode-aware) ------------------------------
@app.post("/inspect")
async def inspect(request: Request):
    payload = await request.json()
    url   = payload.get("url", "")
    ctx   = payload.get("context", "fetch")
    mode  = (payload.get("mode") or "warn").lower()  # "warn" | "strict" | "block"

    body  = payload.get("body")
    kind  = payload.get("bodyKind", "none")

    detections = []
    modified_body_str = None

    # --- helpers -------------------------------------------------------------
    def redact_text(s: str) -> str:
        changed = s
        if EMAIL_RE.search(changed):
            detections.append("email")
            changed = EMAIL_RE.sub("{{EMAIL}}", changed)
        return changed

    def redact_json_aware(s: str) -> str | None:
        """Return redacted string if any change, else None."""
        try:
            import json as _json
            def walk(x):
                if isinstance(x, str):    return redact_text(x)
                if isinstance(x, list):   return [walk(v) for v in x]
                if isinstance(x, dict):   return {k: walk(v) for k, v in x.items()}
                return x
            obj  = _json.loads(s)
            obj2 = walk(obj)
            if obj2 != obj:
                return _json.dumps(obj2, ensure_ascii=False, separators=(",", ":"))
            return None
        except Exception:
            red = redact_text(s)
            return red if red != s else None
    # ------------------------------------------------------------------------

    # Classify non-text uploads first
    if kind in ("binary", "multipart", "unknown"):
        if mode in ("strict", "block"):
            action = "block"; notify = {"message": "PrivPrompt: blocked non-text upload"}
        else:  # warn
            action = "allow"; notify = {"message": "PrivPrompt: non-text payload (not inspected)"}

        log_event({"ts": time.time(), "context": ctx, "url": url,
                   "body_kind": kind, "action": action, "detections": [], "note": "non_text"})
        return JSONResponse({"action": action, "notify": notify})

    # Text/JSON path — try to redact
    if isinstance(body, str):
        modified_body_str = redact_json_aware(body)

    has_violation = len(detections) > 0

    # Decide by mode
    if mode == "block":
        if has_violation:
            log_event({"ts": time.time(), "context": ctx, "url": url,
                       "body_kind": kind, "action": "block", "detections": detections, "note": "policy_block"})
            return JSONResponse({"action": "block",
                                 "notify": {"message": "PrivPrompt: blocked (privacy violation)"}})
        else:
            log_event({"ts": time.time(), "context": ctx, "url": url,
                       "body_kind": kind, "action": "allow", "detections": []})
            return JSONResponse({"action": "allow"})

    # strict and warn both allow text; strict only differs for non-text (handled above)
    if has_violation and modified_body_str is not None:
        log_event({"ts": time.time(), "context": ctx, "url": url,
                   "body_kind": kind, "action": "modify", "detections": detections})
        return JSONResponse({"action": "modify",
                             "body": modified_body_str,
                             "notify": {"message": "PrivPrompt: redacted sensitive text"}})

    # Nothing to redact
    log_event({"ts": time.time(), "context": ctx, "url": url,
               "body_kind": kind, "action": "allow", "detections": detections})
    return JSONResponse({"action": "allow"})



# -------------------------- relay to chatgpt.com ------------------------------
def _strip_hop(h: dict) -> dict:
    # keep cookies and Origin; drop hop-by-hop only
    drop = {
        "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
        "te", "trailers", "transfer-encoding", "upgrade", "content-length"
    }
    return {k: v for k, v in h.items() if k.lower() not in drop}

@app.api_route("/relay/chatgpt/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"])
async def relay_chatgpt(path: str, request: Request):
    method = request.method.upper()
    headers_in = dict(request.headers)
    ctype = headers_in.get("content-type", "").lower()
    origin = headers_in.get("origin", "*")
    raw = await request.body()

    # Properly forward query string
    query = request.url.query
    upstream_url = f"{UPSTREAM_CHATGPT}/{path}" + (f"?{query}" if query else "")

    # Handle CORS preflight (browser asks localhost)
    if method == "OPTIONS":
        return Response(status_code=204, headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
            "Access-Control-Allow-Headers": headers_in.get("access-control-request-headers", "*"),
            "Access-Control-Max-Age": "600",
        })

    # MVP redaction: emails in JSON bodies
    out = raw
    modified = False
    if "application/json" in ctype and raw:
        try:
            text = raw.decode("utf-8")
            redacted = EMAIL_RE.sub("{{EMAIL}}", text)
            if redacted != text:
                out = redacted.encode("utf-8")
                modified = True
        except Exception:
            pass

    # Forward upstream
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.request(
            method,
            upstream_url,
            headers=_strip_hop(headers_in),
            content=out if method not in ("GET", "HEAD") else None
        )

    # Pipe response back (+ CORS + signal if modified)
    resp_headers = {
        "Content-Type": r.headers.get("content-type", "application/octet-stream"),
        "Access-Control-Allow-Origin": origin,
    }
    if modified:
        resp_headers["X-PPF-Action"] = "modified"

    return Response(content=r.content, status_code=r.status_code, headers=resp_headers)

# ---------------------------- misc -------------------------------------------
@app.post("/session/start")
async def session_start():
    STATE["salt"] = secrets.token_hex(8)
    return {"ok": True, "salt": STATE["salt"]}

# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=PORT, reload=True)
