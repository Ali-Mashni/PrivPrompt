import os, json, time, secrets
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from dotenv import load_dotenv
load_dotenv()

PORT = int(os.getenv("PP_PORT", "8787"))
LOG_PATH = os.getenv("PP_LOG", "proxy/logs/events.jsonl")
UPSTREAM = "https://api.openai.com"  # placeholder; we are only wiring shape now

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE = {"salt": secrets.token_hex(8)}  # rotates per private session

MAX_BYTES = 64 * 1024  # MVP cap

def log_event(obj: dict):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

@app.post("/session/start")
async def start_session():
    STATE["salt"] = secrets.token_hex(8)
    return {"ok": True, "salt": STATE["salt"]}

@app.post("/relay/openai/v1/chat/completions")
async def relay_chat(request: Request):
    ctype = request.headers.get("content-type", "")
    if "application/json" not in ctype.lower():
        raise HTTPException(status_code=415, detail="E_NONJSON")

    body = await request.body()
    if len(body) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="E_LARGE")

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="E_BADJSON")

    t0 = time.time()

    # MVP: no transforms yet. You will plug detectors/transformers here.
    sanitized = payload

    # Forward upstream as-is for now
    headers = {
        "Content-Type": "application/json",
    }
    # If you later set an Authorization header, do it here, not in the extension.

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{UPSTREAM}/v1/chat/completions",
            headers=headers,
            json=sanitized,
        )
        resp_json = r.json()

    dt = int((time.time() - t0) * 1000)
    log_event({
        "ts": time.time(),
        "route": "openai.chat.completions",
        "duration_ms": dt,
        "status": r.status_code,
        "detected": [],
        "transforms": {},
        "session_id": STATE["salt"],
    })
    return resp_json

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=PORT, reload=True)
