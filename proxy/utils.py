import os, json, time, secrets
from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv("PP_PORT", "8787"))
UPSTREAM_CHATGPT = "https://chatgpt.com"
LOG_PATH = os.getenv("PP_LOG", os.path.join("proxy", "logs", "events.jsonl"))

_STATE = {"salt": secrets.token_hex(8)}

def get_salt() -> str:
    return _STATE["salt"]

def rotate_salt() -> str:
    _STATE["salt"] = secrets.token_hex(8)
    return _STATE["salt"]

def log_event(obj: dict) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def now() -> float:
    return time.time()
