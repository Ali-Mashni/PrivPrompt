import os, time, json
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
load_dotenv()
LOG_PATH = os.getenv("PP_LOG", "proxy/logs/events.jsonl")

st.set_page_config(page_title="PrivPrompt Dashboard", layout="wide")
st.title("PrivPrompt Dashboard")

placeholder = st.empty()

def load_events():
    if not os.path.exists(LOG_PATH):
        return pd.DataFrame(columns=["ts","route","duration_ms","status","detected"])
    rows = []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                rows.append({
                    "ts": pd.to_datetime(obj.get("ts", time.time()), unit="s"),
                    "route": obj.get("route",""),
                    "duration_ms": obj.get("duration_ms",0),
                    "status": obj.get("status",0),
                    "detected": ",".join(obj.get("detected",[]))
                })
            except:
                continue
    return pd.DataFrame(rows)

df = load_events()
col1, col2, col3 = st.columns(3)
col1.metric("Total Calls", len(df))
col2.metric("Avg Latency (ms)", round(df["duration_ms"].mean(), 1) if len(df) else 0)
ok_rate = (df["status"] == 200).mean()*100 if len(df) else 0
col3.metric("OK Rate", f"{ok_rate:.1f}%")

st.subheader("Detections by Type")
if len(df):
    st.bar_chart(df["detected"].value_counts())
else:
    st.write("No data yet. Make a request through the proxy.")

st.subheader("Latency over Time")
if len(df):
    df_time = df.sort_values("ts")[["ts","duration_ms"]].set_index("ts")
    st.line_chart(df_time)
else:
    st.write("No data yet.")
