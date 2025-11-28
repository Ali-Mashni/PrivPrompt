import os, time, json
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
load_dotenv()
LOG_PATH = os.getenv("PP_LOG", "proxy/logs/events.jsonl")

st.set_page_config(page_title="PrivPrompt Dashboard", layout="wide")
st.title("PrivPrompt Dashboard")

# Auto-refresh every 2 seconds
placeholder = st.empty()

def load_events():
    if not os.path.exists(LOG_PATH):
        return pd.DataFrame(columns=["ts","route","duration_ms","status","detected"])
    rows = []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                # Handle both old and new log formats
                detected = obj.get("detected", [])
                if isinstance(detected, str):
                    detected = [d.strip() for d in detected.split(",") if d.strip()]
                elif not isinstance(detected, list):
                    detected = []
                
                rows.append({
                    "ts": pd.to_datetime(obj.get("ts", time.time()), unit="s"),
                    "route": obj.get("route", obj.get("url", "").split("?")[0] if obj.get("url") else ""),
                    "duration_ms": obj.get("duration_ms", 0),
                    "status": obj.get("status", 200 if obj.get("action") != "block" else 403),
                    "detected": ",".join(detected) if detected else ""
                })
            except Exception as e:
                # Skip malformed lines
                continue
    return pd.DataFrame(rows)

# Auto-refresh
if st.button("🔄 Refresh"):
    st.rerun()

df = load_events()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Calls", len(df))
col2.metric("Avg Latency (ms)", round(df["duration_ms"].mean(), 1) if len(df) > 0 else 0)
ok_rate = (df["status"] == 200).mean()*100 if len(df) > 0 else 0
col3.metric("OK Rate", f"{ok_rate:.1f}%")
blocked = (df["status"] == 403).sum() if len(df) > 0 else 0
col4.metric("Blocked", blocked)

st.subheader("Detections by Type")
if len(df) > 0:
    # Flatten detected column (comma-separated) into individual detections
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

st.subheader("Latency over Time")
if len(df) > 0:
    df_time = df.sort_values("ts")[["ts","duration_ms"]].set_index("ts")
    st.line_chart(df_time)
else:
    st.write("No data yet.")

st.subheader("Recent Requests")
if len(df) > 0:
    st.dataframe(
        df.sort_values("ts", ascending=False).head(20)[["ts", "route", "duration_ms", "status", "detected"]],
        use_container_width=True
    )
else:
    st.write("No requests logged yet.")
