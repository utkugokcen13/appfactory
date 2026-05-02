"""Signals browser — raw collected data, filterable by source."""

from __future__ import annotations

# sys.path: ensure repo root is importable on Streamlit Cloud (see app.py).
import sys as _sys
from pathlib import Path as _Path
_root = str(_Path(__file__).resolve().parents[3])
if _root not in _sys.path:
    _sys.path.insert(0, _root)

import html
from datetime import date, timedelta

import streamlit as st

from factory.ui import auth, data, run_launcher, styles
from factory.ui.nav import render_sidebar

st.set_page_config(
    page_title="Signals · App Factory",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)
styles.inject()
auth.require_login()
render_sidebar(active="Signals")

head_left, head_right = st.columns([4, 2], gap="medium")
with head_left:
    st.markdown(
        "<div class='page-head-text'>"
        "<div class='page-head-title'>Signals</div>"
        "<div class='page-head-sub'>"
        "Every raw data point the factory has collected — App Store charts, "
        "Reddit posts, Google Trends rising queries, web search results. "
        "Persisted across runs (dedup'd by source + external id)."
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
with head_right:
    run_launcher.render_new_run_button(
        label="🚀  New ideation run",
        key="signals_launch_cta",
        hero=False,
    )

run_launcher.render_inflight_section()

# ───── Source counts + filter ──────────────────────────────────────────

counts = data.signal_source_counts()
if not counts:
    st.markdown(
        "<div class='empty-state'>"
        "<div class='empty-emoji'>📡</div>"
        "<div class='empty-title'>No signals collected yet</div>"
        "<div class='empty-body'>"
        "Click <strong>🚀 New ideation run</strong> above. "
        "The agent will scrape App Store, Reddit, and Trends — and they'll show up here."
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

total = sum(c["count"] for c in counts)
src_names = [c["source"] for c in counts]
src_counts_map = {c["source"]: c["count"] for c in counts}


def _src_label(src: str) -> str:
    return f"{src} ({src_counts_map.get(src, 0):,})"


# Metric row
mcols = st.columns(len(counts) + 1)
mcols[0].metric("Total signals", f"{total:,}")
for i, c in enumerate(counts):
    mcols[i + 1].metric(c["source"], f"{c['count']:,}")

st.write("")

# ───── Filters ──────────────────────────────────────────────────────────

with st.container(border=True):
    f1, f2, f3 = st.columns([3, 2, 2])
    with f1:
        selected_sources = st.multiselect(
            "Sources",
            src_names,
            default=src_names,
            format_func=_src_label,
        )
    with f2:
        window = st.selectbox(
            "Collected since",
            ["All time", "Last 24h", "Last 7 days", "Last 30 days"],
            index=0,
        )
    with f3:
        text_q = st.text_input("Search title/content", "")

after_iso: str | None = None
if window == "Last 24h":
    after_iso = (date.today() - timedelta(days=1)).isoformat()
elif window == "Last 7 days":
    after_iso = (date.today() - timedelta(days=7)).isoformat()
elif window == "Last 30 days":
    after_iso = (date.today() - timedelta(days=30)).isoformat()

# ───── Pagination state ────────────────────────────────────────────────
PAGE_SIZE = 50

if "sig_page" not in st.session_state:
    st.session_state.sig_page = 1

# Reset page when filters change
filter_key = (tuple(sorted(selected_sources)), after_iso, text_q)
if st.session_state.get("sig_filter_key") != filter_key:
    st.session_state.sig_filter_key = filter_key
    st.session_state.sig_page = 1

total_matches = data.count_signals_with_filters(
    sources=selected_sources or None,
    text=text_q or None,
    after=after_iso,
)

st.caption(
    f"{total_matches:,} matching signal{'s' if total_matches != 1 else ''} · "
    f"Page {st.session_state.sig_page} of "
    f"{max(1, (total_matches + PAGE_SIZE - 1) // PAGE_SIZE)}"
)

if total_matches == 0:
    st.info("No signals match these filters.")
    st.stop()

offset = (st.session_state.sig_page - 1) * PAGE_SIZE
rows = data.list_signals_with_filters(
    sources=selected_sources or None,
    text=text_q or None,
    after=after_iso,
    limit=PAGE_SIZE,
    offset=offset,
)


# ───── Signal card rendering ────────────────────────────────────────────

def _fmt_meta(source: str, meta: dict) -> str:
    """Source-specific compact metadata line."""
    if not meta:
        return ""
    if source == "reddit":
        sub = meta.get("subreddit") or "?"
        score = meta.get("score") or 0
        comments = meta.get("num_comments") or 0
        author = meta.get("author") or "?"
        return f"r/{sub} · ↑{score} · 💬{comments} · u/{author}"
    if source == "google_trends":
        kind = meta.get("kind")
        if kind == "seed_summary":
            return (
                f"seed · 3mo mean {meta.get('mean_interest')}/100 · "
                f"slope {meta.get('slope_percent', 0):+.1f}%"
            )
        if kind == "rising_query":
            typ = meta.get("type", "rising")
            val = meta.get("value")
            val_s = f" +{int(val)}%" if isinstance(val, (int, float)) else ""
            return f"seed='{meta.get('seed')}' · {typ.upper()}{val_s}"
        return ""
    if source == "appstore_chart":
        bits = []
        if meta.get("rank") is not None:
            bits.append(f"rank #{meta['rank']}")
        if meta.get("genre"):
            bits.append(meta["genre"])
        if meta.get("feed"):
            bits.append(meta["feed"].replace("applications", ""))
        return " · ".join(bits)
    if source == "appstore_search":
        bits = []
        if meta.get("query"):
            bits.append(f"query: {meta['query']}")
        if meta.get("rating") is not None:
            bits.append(f"★ {meta['rating']}")
        if meta.get("rating_count") is not None:
            try:
                bits.append(f"{int(meta['rating_count']):,} reviews")
            except (TypeError, ValueError):
                pass
        return " · ".join(bits)
    if source == "web_search":
        q = meta.get("query")
        pub = meta.get("published_date")
        bits = []
        if q:
            bits.append(f"query: {q}")
        if pub:
            bits.append(pub[:10])
        return " · ".join(bits)
    return ""


def _render_signal(s: dict) -> None:
    src = s.get("source") or "?"
    meta = s.get("metadata") if isinstance(s.get("metadata"), dict) else {}
    title = html.escape(s.get("title") or "(untitled)")
    content = html.escape((s.get("content") or "")[:320])
    url = s.get("url") or ""
    collected = styles.format_local_dt(s.get("collected_at"))
    meta_line = _fmt_meta(src, meta or {})

    title_html = (
        f"<a href='{html.escape(url)}' target='_blank' rel='noopener'>{title}</a>"
        if url else title
    )

    st.markdown(
        f"<div class='sig-card'>"
        f"  <div class='sig-head'>"
        f"    <div class='sig-head-left'>"
        f"      <span class='sig-src {src}'>{src}</span>"
        f"      <span class='sig-meta'>{html.escape(meta_line)}</span>"
        f"    </div>"
        f"    <span class='sig-date'>{collected}</span>"
        f"  </div>"
        f"  <div class='sig-title'>{title_html}</div>"
        + (f"  <div class='sig-content'>{content}</div>" if content else "")
        + f"</div>",
        unsafe_allow_html=True,
    )


for s in rows:
    _render_signal(s)

# ───── Pagination controls ─────────────────────────────────────────────

nav_cols = st.columns([1, 2, 1])
with nav_cols[0]:
    if st.session_state.sig_page > 1:
        if st.button("← Previous", use_container_width=True):
            st.session_state.sig_page -= 1
            st.rerun()
with nav_cols[2]:
    if offset + PAGE_SIZE < total_matches:
        if st.button("Next →", use_container_width=True):
            st.session_state.sig_page += 1
            st.rerun()
