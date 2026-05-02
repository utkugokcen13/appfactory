"""Single run detail: meta card + Summary / Timeline / Raw tabs."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from factory.ui import auth, data, styles
from factory.ui.components.turn_timeline import render_run_timeline
from factory.ui.nav import render_sidebar

st.set_page_config(page_title="Run · App Factory", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
styles.inject()
auth.require_login()
render_sidebar()

# ───── Resolve run_id ────────────────────────────────────────────────────

qp = st.query_params
run_id_raw = qp.get("run_id")
if run_id_raw is None:
    latest = data.latest_run()
    if not latest:
        st.info("No runs yet.")
        st.stop()
    run_id = latest["id"]
    st.caption(f"No `run_id` in URL — showing latest (#{run_id}).")
else:
    try:
        run_id = int(run_id_raw)
    except (TypeError, ValueError):
        st.error(f"Invalid run_id: {run_id_raw!r}")
        st.stop()

run = data.get_run(run_id)
if not run:
    st.error(f"Run #{run_id} not found.")
    st.stop()

# ───── Header ────────────────────────────────────────────────────────────

st.markdown(f"# Run #{run_id}")
model = (run.get("model") or "—").replace("global.anthropic.claude-", "")
st.caption(f"{run.get('agent', 'ideation')} · `{model}`")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Status", run.get("status") or "—")
m2.metric("Ideas", run.get("ideas_generated") or 0)
m3.metric("Tokens in", f"{(run.get('input_tokens') or 0):,}")
m4.metric("Tokens out", f"{(run.get('output_tokens') or 0):,}")
m5.metric("Web searches", run.get("web_searches") or 0)

started = styles.format_local_dt(run.get("started_at"))
finished = styles.format_local_dt(run.get("finished_at"), fallback="(in flight)")
dur = run.get("duration_seconds")
dur_str = f"{dur:.1f}s" if dur is not None else "—"
st.caption(f"{started} → {finished} · {dur_str}")
if run.get("error"):
    st.error(f"Error: {run['error']}")

st.write("")

# ───── Tabs ──────────────────────────────────────────────────────────────

tab_summary, tab_timeline, tab_raw = st.tabs(["Summary", "Timeline", "Raw"])

with tab_summary:
    st.markdown("### Ideas saved this run")
    ideas = data.ideas_for_run(run_id)
    if not ideas:
        st.caption("No ideas saved in this run.")
    else:
        for i in range(0, len(ideas), 3):
            cols = st.columns(3, gap="medium")
            for j, idea in enumerate(ideas[i : i + 3]):
                with cols[j]:
                    st.markdown(styles.idea_card_html(idea), unsafe_allow_html=True)
            for j in range(len(ideas[i : i + 3]), 3):
                with cols[j]:
                    st.write("")

    st.markdown("### Queries used")
    queries = data.get_queries_for_run(run_id)
    if not queries:
        st.caption("No queries recorded.")
    else:
        df = pd.DataFrame(queries)[["turn", "tool", "query", "source"]]
        st.dataframe(df, hide_index=True, use_container_width=True)

with tab_timeline:
    st.markdown("### Turn-by-turn trace")
    st.caption("Each turn expands to show Claude's text, tool calls, and results.")
    render_run_timeline(run_id)

with tab_raw:
    st.markdown("### Raw run data")
    st.json({"run": run})
    turns = data.get_turns(run_id)
    with st.expander(f"Turns ({len(turns)})", expanded=False):
        for t in turns:
            blocks = data.get_blocks(t["id"])
            st.markdown(f"#### Turn {t['turn_number']}")
            st.json({
                "turn": t,
                "blocks": [
                    {
                        k: v for k, v in b.items()
                        if k in ("seq", "block_type", "tool_name", "tool_input",
                                 "tool_use_id", "tool_result", "tool_error", "text")
                    }
                    for b in blocks
                ],
            })
