"""All agent runs — list view."""

from __future__ import annotations

# sys.path: ensure repo root is importable on Streamlit Cloud (see app.py).
import sys as _sys
from pathlib import Path as _Path
_root = str(_Path(__file__).resolve().parents[3])
if _root not in _sys.path:
    _sys.path.insert(0, _root)

import pandas as pd
import streamlit as st

from factory.ui import auth, data, run_launcher, styles
from factory.ui.nav import render_sidebar

st.set_page_config(page_title="Runs · App Factory", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
styles.inject()
auth.require_login()
render_sidebar(active="Runs")

runs = data.list_runs(limit=200)

# Page header: title on the left, prominent "+ New run" button on the right.
# The launcher itself lives in a dialog now — no duplicated form on this page.
head_left, head_right = st.columns([4, 2], gap="medium")
with head_left:
    st.markdown(
        "<div class='page-head-text'>"
        "<div class='page-head-title'>Runs</div>"
        "<div class='page-head-sub'>All agent executions, most recent first. "
        "Click a row to open its detail.</div>"
        "</div>",
        unsafe_allow_html=True,
    )
with head_right:
    run_launcher.render_new_run_button(
        label="🚀  New ideation run",
        key="runs_launch_cta",
        hero=False,
    )

# In-flight banner / live monitor / booting skeleton (renders nothing if idle)
run_launcher.render_inflight_section()

if not runs:
    st.info("No runs yet — click **🚀 New ideation run** above to start your first one.")
    st.stop()

rows = []
for r in runs:
    rows.append({
        "run_id": r["id"],
        "started": styles.format_local_dt(r.get("started_at")),
        "agent": r.get("agent") or "—",
        "model": (r.get("model") or "—").replace("global.anthropic.claude-", ""),
        "status": r.get("status") or "—",
        "ideas": r.get("ideas_generated") or 0,
        "tokens": (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0),
        "searches": r.get("web_searches") or 0,
        "dur_s": round(r["duration_seconds"], 1) if r.get("duration_seconds") else None,
    })
df = pd.DataFrame(rows)

event = st.dataframe(
    df,
    hide_index=True,
    use_container_width=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "run_id": st.column_config.NumberColumn("ID", width="small"),
        "started": st.column_config.TextColumn("Started"),
        "agent": st.column_config.TextColumn("Agent"),
        "model": st.column_config.TextColumn("Model"),
        "status": st.column_config.TextColumn("Status"),
        "ideas": st.column_config.NumberColumn("Ideas", width="small"),
        "tokens": st.column_config.NumberColumn("Tokens", format="%d"),
        "searches": st.column_config.NumberColumn("Searches", width="small"),
        "dur_s": st.column_config.NumberColumn("Dur (s)", format="%.1f", width="small"),
    },
)

selection = event.selection if event else None
if selection and selection.rows:
    row_idx = selection.rows[0]
    run_id = int(df.iloc[row_idx]["run_id"])
    st.page_link("pages/2_Run_Detail.py", label=f"Open Run #{run_id} →", icon="🔍")
    st.caption(f"Deep link: `?run_id={run_id}`")
