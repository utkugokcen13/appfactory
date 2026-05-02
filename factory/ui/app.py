"""App Factory — Streamlit Home dashboard."""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from factory.ui import auth, data, run_launcher, styles
from factory.ui.nav import render_sidebar

st.set_page_config(
    page_title="App Factory",
    page_icon="⚒️",
    layout="wide",
    initial_sidebar_state="expanded",
)
styles.inject()
auth.require_login()
render_sidebar(active="Home")


def _fmt_compact(n: int) -> str:
    """Compact int: 12345 → 12.3k, 1234567 → 1.23M."""
    n = int(n or 0)
    if n < 1000:
        return str(n)
    if n < 10_000:
        return f"{n/1000:.2f}k"
    if n < 1_000_000:
        return f"{n/1000:.1f}k"
    if n < 10_000_000:
        return f"{n/1_000_000:.2f}M"
    return f"{n/1_000_000:.1f}M"


# ───── Header ────────────────────────────────────────────────────────────

st.markdown(
    f"""
    <div class='hero'>
      <div class='hero-title'>App Factory</div>
      <div class='hero-sub'>Automated mobile app production pipeline · {date.today().isoformat()}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ───── In-flight monitor (only renders when a run is active) ───────────

in_flight = run_launcher.in_flight_run()
run_launcher.render_inflight_section()

# ───── Hero CTA: prominent "launch new run" button ─────────────────────

run_launcher.render_new_run_button(
    label="🚀  Launch new ideation run",
    key="home_launch_cta",
)

# ───── Metric cards ──────────────────────────────────────────────────────

counts = data.db_counts()
tok = data.tokens_today()
tok_total = tok["input"] + tok["output"]

m1, m2, m3, m4 = st.columns(4, gap="medium")
with m1:
    st.markdown(
        styles.stat_card_html(
            "Ideas", str(counts["ideas"]), accent="primary", href="Ideas",
        ),
        unsafe_allow_html=True,
    )
with m2:
    st.markdown(
        styles.stat_card_html(
            "Runs", str(counts["runs"]), accent="demand", href="Runs",
        ),
        unsafe_allow_html=True,
    )
with m3:
    st.markdown(
        styles.stat_card_html(
            "Signals in DB", f"{counts['signals']:,}",
            accent="monetization", href="Signals",
        ),
        unsafe_allow_html=True,
    )
with m4:
    st.markdown(
        styles.stat_card_html(
            "Tokens today",
            _fmt_compact(tok_total),
            sub=f"{_fmt_compact(tok['output'])} out" if tok_total else "—",
            accent="feasibility",
            href="Runs",
        ),
        unsafe_allow_html=True,
    )

st.write("")

# ───── Two columns: sparkline + latest run ───────────────────────────────

left, right = st.columns([7, 5], gap="large")

with left:
    metrics = data.daily_ideation_metrics()  # auto-extends to include the last run
    last_act = data.last_activity_date()
    range_caption = ""
    if metrics:
        range_caption = f"{metrics[0]['date']} → {metrics[-1]['date']}"
    st.markdown(
        styles.section_head_html("Activity", sub=range_caption, href="Runs"),
        unsafe_allow_html=True,
    )
    has_data = metrics and sum(m["ideas"] for m in metrics) > 0
    if has_data:
        df = pd.DataFrame(metrics)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["ideas"],
            mode="lines+markers", name="Ideas",
            line={"color": styles.COLORS["primary"], "width": 3, "shape": "spline"},
            marker={"size": 8, "color": styles.COLORS["primary"]},
            fill="tozeroy",
            fillcolor="rgba(129, 140, 248, 0.15)",
            hovertemplate="%{x}<br>%{y} ideas<extra></extra>",
        ))
        fig.update_layout(
            height=280,
            margin={"t": 10, "b": 10, "l": 10, "r": 10},
            xaxis={
                "showgrid": False, "zeroline": False,
                "tickfont": {"size": 11, "color": styles.COLORS["text_sub"]},
                "linecolor": styles.COLORS["border_soft"],
            },
            yaxis={
                "showgrid": True, "gridcolor": styles.COLORS["border_soft"],
                "zeroline": False,
                "tickfont": {"size": 11, "color": styles.COLORS["text_sub"]},
                "rangemode": "tozero",
            },
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            hoverlabel={"bgcolor": styles.COLORS["card"], "font": {"color": styles.COLORS["text"]}},
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.markdown(
            "<div class='empty-state'>"
            "<div class='empty-emoji'>📈</div>"
            "<div class='empty-title'>No activity yet</div>"
            "<div class='empty-body'>Click <strong>🚀 Launch new ideation run</strong> above to seed your first ideas.</div>"
            "</div>",
            unsafe_allow_html=True,
        )

with right:
    # When a run is in-flight, the live monitor above already covers it —
    # show the previous run here instead so the page stays informative.
    recent_runs = data.list_runs(limit=2)
    if in_flight and recent_runs and recent_runs[0]["id"] == in_flight["id"]:
        run = recent_runs[1] if len(recent_runs) > 1 else None
        section_label = "Previous run"
        section_sub = "last completed ideation pass"
    else:
        run = recent_runs[0] if recent_runs else None
        section_label = "Latest run"
        section_sub = "most recent ideation pass"

    st.markdown(
        styles.section_head_html(
            section_label,
            sub=section_sub,
            href=f"Run_Detail?run_id={run['id']}" if run else None,
        ),
        unsafe_allow_html=True,
    )
    if run:
        run_tokens = (run.get("input_tokens") or 0) + (run.get("output_tokens") or 0)
        started = styles.format_local_dt(run.get("started_at"), fmt="%Y-%m-%d %H:%M")
        ideas_n = run.get("ideas_generated") or 0
        sigs_n = run.get("signals_collected") or 0
        web_n = run.get("web_searches") or 0
        status = run.get("status") or "—"
        status_cls = "ok" if status == "ok" else ("err" if status == "error" else "neu")
        st.markdown(
            f"""
            <div class='run-card is-link'>
              <a class='card-overlay' href='Run_Detail?run_id={run['id']}' target='_self' aria-label='Open run #{run['id']}'></a>
              <div class='run-card-head'>
                <div class='run-id'>Run #{run['id']}</div>
                <div class='run-status {status_cls}'>{status}</div>
              </div>
              <div class='run-time'>{started}</div>
              <div class='run-grid'>
                <div class='run-stat'>
                  <div class='run-stat-label'>Ideas</div>
                  <div class='run-stat-val'>{ideas_n}</div>
                </div>
                <div class='run-stat'>
                  <div class='run-stat-label'>Tokens</div>
                  <div class='run-stat-val'>{_fmt_compact(run_tokens)}</div>
                </div>
                <div class='run-stat'>
                  <div class='run-stat-label'>Signals</div>
                  <div class='run-stat-val'>{sigs_n:,}</div>
                </div>
                <div class='run-stat'>
                  <div class='run-stat-label'>Searches</div>
                  <div class='run-stat-val'>{web_n}</div>
                </div>
              </div>
              <span class='run-cta-inline'>Open run →</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='empty-state small'>"
            "<div class='empty-title'>No runs yet</div>"
            "</div>",
            unsafe_allow_html=True,
        )

st.write("")
st.markdown(
    styles.section_head_html(
        "Top pending ideas",
        sub="highest-scoring not-yet-validated",
        href="Ideas",
    ),
    unsafe_allow_html=True,
)

pending = data.top_pending_ideas(limit=4)
if not pending:
    st.markdown(
        "<div class='empty-state small'>"
        "<div class='empty-title'>No pending ideas yet.</div>"
        "</div>",
        unsafe_allow_html=True,
    )
else:
    cols = st.columns(min(4, len(pending)), gap="medium")
    for col, idea in zip(cols, pending):
        with col:
            full = data.get_idea(idea["id"])
            if full:
                st.markdown(styles.idea_card_html(full), unsafe_allow_html=True)
