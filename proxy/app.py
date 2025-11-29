import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from .utils import PORT, UPSTREAM_CHATGPT, log_event, now
from .policy import decide

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/healthz")
async def healthz():
    return PlainTextResponse("ok")

@app.post("/inspect")
async def inspect(request: Request):
    start_ts = now()
    payload = await request.json()

    url   = payload.get("url", "")
    ctx   = payload.get("context", "fetch")
    mode  = (payload.get("mode") or "warn").lower()
    body  = payload.get("body")
    kind  = payload.get("bodyKind", "none")

    # NEW: hand MIME/filename to policy so it can classify non-text correctly
    content_type = payload.get("contentType")
    filename     = payload.get("filename")

    # ask policy only (keep app clean)
    decision = decide(
        mode, kind, url, body,
        content_type=content_type,
        filename=filename
    )

    # compute a status for dashboards
    status = 200 if decision.get("action") != "block" else 403
    detected = decision.get("detected", []) 

    # optional: nicer route field for logs
    route = ""
    if url:
        try:
            from urllib.parse import urlparse
            route = urlparse(url).path.split("?")[0]
        except Exception:
            route = url.split("?")[0] if "?" in url else url

    # --- reduce noise: skip logging heartbeats/prepare ---
    noisy = (
        url.endswith("/conversation/prepare")
        or url.endswith("/conversation/implicit_message_feedback")
    )
    if not noisy:
        log_event({
            "ts": start_ts,
            "route": route,
            "duration_ms": round((now() - start_ts) * 1000, 2),
            "status": status,
            "detected": detected,
            
            "context": ctx,
            "url": url,
            "body_kind": kind,
            "content_type": content_type,
            "filename": filename,

            "action": decision.get("action", "allow"),
            "mode": mode,
            "send_id": payload.get("sendId"),
            "tab_id": payload.get("tabId"),
        })

    return JSONResponse(decision, status_code=status)



# ---- Optional relay (not used by ChatGPT main-world patch; keep for later) ----

_HOP_DROP = {
    "connection","keep-alive","proxy-authenticate","proxy-authorization",
    "te","trailers","transfer-encoding","upgrade","content-length"
}

def _strip_hop(h: dict) -> dict:
    return {k:v for k,v in h.items() if k.lower() not in _HOP_DROP}

@app.api_route("/relay/chatgpt/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"])
async def relay_chatgpt(path: str, request: Request):
    method = request.method.upper()
    headers_in = dict(request.headers)
    origin = headers_in.get("origin","*")
    raw = await request.body()
    query = request.url.query
    upstream_url = f"{UPSTREAM_CHATGPT}/{path}" + (f"?{query}" if query else "")

    if method == "OPTIONS":
        return Response(status_code=204, headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
            "Access-Control-Allow-Headers": headers_in.get("access-control-request-headers","*"),
            "Access-Control-Max-Age": "600",
        })

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.request(method, upstream_url, headers=_strip_hop(headers_in),
                                 content=(raw if method not in ("GET","HEAD") else None))

    return Response(content=r.content, status_code=r.status_code, headers={
        "Content-Type": r.headers.get("content-type","application/octet-stream"),
        "Access-Control-Allow-Origin": origin
    })
