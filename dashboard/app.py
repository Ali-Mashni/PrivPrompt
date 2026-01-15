import os, time, json
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
LOG_PATH = os.getenv("PP_LOG", "proxy/logs/events.jsonl")

st.set_page_config(page_title="PrivPrompt Dashboard", layout="wide")
st.title("PrivPrompt Dashboard")

def _normalize_detected(obj) -> list[str]:
    detected = obj.get("detected", [])
    if isinstance(detected, str):
        return [d.strip() for d in detected.split(",") if d.strip()]
    if isinstance(detected, list):
        return [str(d).strip() for d in detected if str(d).strip()]
    return []

def _infer_status(obj) -> int:
    # Prefer explicit status if present
    if isinstance(obj.get("status", None), int):
        return obj["status"]
    # Otherwise infer from action
    action = (obj.get("action") or "").lower()
    return 403 if action == "block" else 200

def _route_from_obj(obj) -> str:
    if obj.get("route"):
        return obj["route"]
    url = obj.get("url") or ""
    return url.split("?")[0] if url else ""

def load_events_grouped():
    """
    Reads jsonl log and returns ONE row per (send_id, tab_id).
    If send_id is missing, falls back to unique key per line.
    """
    if not os.path.exists(LOG_PATH):
        return pd.DataFrame(columns=[
            "send_id", "tab_id",
            "first_ts", "last_ts",
            "route", "duration_ms",
            "final_status", "final_action",
            "actions", "detected"
        ])

    raw_rows = []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            try:
                obj = json.loads(line)

                ts_val = obj.get("ts", time.time())
                # Your logs use seconds (float). Keep consistent.
                ts = pd.to_datetime(ts_val, unit="s")

                raw_rows.append({
                    "send_id": obj.get("send_id") or f"_no_send_id_{i}",
                    "tab_id": obj.get("tab_id", None),
                    "ts": ts,
                    "route": _route_from_obj(obj),
                    "duration_ms": float(obj.get("duration_ms", 0) or 0),
                    "status": _infer_status(obj),
                    "action": (obj.get("action") or "").lower(),
                    "detected_list": _normalize_detected(obj),
                })
            except Exception:
                continue

    if not raw_rows:
        return pd.DataFrame(columns=[
            "send_id", "tab_id",
            "first_ts", "last_ts",
            "route", "duration_ms",
            "final_status", "final_action",
            "actions", "detected"
        ])

    df = pd.DataFrame(raw_rows)

    # Group key: (send_id, tab_id) to avoid cross-tab collisions
    group_cols = ["send_id", "tab_id"]

    def most_common(series: pd.Series) -> str:
        series = series.dropna()
        if len(series) == 0:
            return ""
        return series.value_counts().index[0]

    def worst_status(statuses: pd.Series) -> int:
        # If any blocked/4xx/5xx exists, prefer the max status code (usually 403/500 etc).
        # Otherwise 200.
        try:
            return int(statuses.max())
        except Exception:
            return 200

    def union_detected(det_lists: pd.Series) -> str:
        s = set()
        for lst in det_lists:
            if isinstance(lst, list):
                s.update(lst)
        return ",".join(sorted(s))

    def actions_join(actions: pd.Series) -> str:
        ordered = [a for a in actions.tolist() if a]
        # de-dup while keeping order
        seen = set()
        out = []
        for a in ordered:
            if a not in seen:
                seen.add(a)
                out.append(a)
        return ",".join(out)

    grouped = (
        df.sort_values("ts")
          .groupby(group_cols, dropna=False, as_index=False)
          .agg(
              first_ts=("ts", "min"),
              last_ts=("ts", "max"),
              route=("route", most_common),
              duration_ms=("duration_ms", "sum"),
              final_status=("status", worst_status),
              final_action=("action", lambda s: (s.dropna().tolist()[-1] if len(s.dropna()) else "")),
              actions=("action", actions_join),
              detected=("detected_list", union_detected),
          )
    )

    return grouped

# Manual refresh
if st.button("🔄 Refresh"):
    st.rerun()

df = load_events_grouped()

# Metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Sends", len(df))
col2.metric("Avg Total Latency (ms)", round(df["duration_ms"].mean(), 1) if len(df) > 0 else 0)
ok_rate = (df["final_status"] == 200).mean() * 100 if len(df) > 0 else 0
col3.metric("OK Rate", f"{ok_rate:.1f}%")
blocked = (df["final_status"] >= 400).sum() if len(df) > 0 else 0
col4.metric("Blocked", blocked)

# Detections
st.subheader("Detections by Type")
if len(df) > 0:
    all_detections = []
    for det_str in df["detected"]:
        if det_str:
            all_detections.extend([d.strip() for d in det_str.split(",") if d.strip()])

    if all_detections:
        det_df = pd.DataFrame({"type": all_detections})
        st.bar_chart(det_df["type"].value_counts())
    else:
        st.write("No detections yet.")
else:
    st.write("No data yet. Make a request through the proxy.")

# Latency over time (use last_ts as the time point for the grouped send)
st.subheader("Latency over Time")
if len(df) > 0:
    df_time = df.sort_values("last_ts")[["last_ts", "duration_ms"]].set_index("last_ts")
    st.line_chart(df_time)
else:
    st.write("No data yet.")

# Recent grouped sends
st.subheader("Recent Sends (Grouped by send_id)")
if len(df) > 0:
    st.dataframe(
        df.sort_values("last_ts", ascending=False).head(30)[
            ["last_ts", "send_id", "tab_id", "route", "duration_ms", "final_status", "final_action", "actions", "detected"]
        ],
        use_container_width=True
    )
else:
    st.write("No requests logged yet.")
