"""All ideas — filterable grid view with clickable cards."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import streamlit as st

from factory.ui import auth, data, styles
from factory.ui.nav import render_sidebar

st.set_page_config(
    page_title="Ideas · App Factory",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded",
)
styles.inject()
auth.require_login()
render_sidebar(active="Ideas")

st.markdown(
    "<div class='page-head-text'>"
    "<div class='page-head-title'>Ideas</div>"
    "<div class='page-head-sub'>Click any card to open the full research trail and scoring.</div>"
    "</div>",
    unsafe_allow_html=True,
)

FEASIBILITY_OPTIONS = ["solo-1wk", "solo-1mo", "solo-3mo", "team-only"]
STAGE_OPTIONS = ["ideated", "validated", "specced", "designed", "coded", "built", "shipped"]

# Quick filters: each maps to a partial filter override applied on top of the
# detailed bar below. Multi-select; values combine (intersection).
QUICK_FILTERS = {
    "🔥  Top scoring (80+)":      {"min_score": 80},
    "🛠  Solo-friendly (≤1 mo)": {"feasibility": ["solo-1wk", "solo-1mo"]},
    "🌱  Pending validation":    {"stages": ["ideated"]},
    "🆕  Last 7 days":           {"recent_days": 7},
}

# ───── Quick filter chips (one row, one click each) ──────────────────────
st.markdown(
    "<div class='filter-quick-label'>Quick filters</div>",
    unsafe_allow_html=True,
)
quick_selected = st.pills(
    "Quick filters",
    options=list(QUICK_FILTERS.keys()),
    selection_mode="multi",
    default=[],
    label_visibility="collapsed",
    key="ideas_quick_filters",
)

# ───── Detailed filter bar (fine-grained overrides) ──────────────────────
with st.container(border=True):
    c1, c2, c3, c4 = st.columns([2, 2, 2, 3])
    with c1:
        score_range = st.slider("Score", 0, 100, (0, 100))
    with c2:
        feasibility = st.multiselect(
            "Build effort",
            FEASIBILITY_OPTIONS,
            default=FEASIBILITY_OPTIONS,
            format_func=styles.humanize_feasibility,
            help="Filter by how much work the idea needs.",
        )
    with c3:
        stages = st.multiselect("Stage", STAGE_OPTIONS, default=STAGE_OPTIONS)
    with c4:
        text = st.text_input("Search title / concept", "", placeholder="e.g. ADHD, sleep, freelance")

# ───── Combine quick filters with detailed filters ───────────────────────
effective_min_score = score_range[0]
effective_max_score = score_range[1]
effective_feasibility = list(feasibility)
effective_stages = list(stages)
effective_created_after: str | None = None

for chip in quick_selected or []:
    overrides = QUICK_FILTERS[chip]
    if "min_score" in overrides:
        effective_min_score = max(effective_min_score, overrides["min_score"])
    if "feasibility" in overrides:
        effective_feasibility = [
            f for f in effective_feasibility if f in overrides["feasibility"]
        ]
    if "stages" in overrides:
        effective_stages = [s for s in effective_stages if s in overrides["stages"]]
    if "recent_days" in overrides:
        cutoff = datetime.now(timezone.utc) - timedelta(days=overrides["recent_days"])
        effective_created_after = cutoff.isoformat()

ideas = data.list_ideas_with_filters(
    min_score=effective_min_score,
    max_score=effective_max_score,
    feasibility=effective_feasibility or None,
    stages=effective_stages or None,
    created_after=effective_created_after,
    text=text or None,
    limit=500,
)

# Filter summary (concise, scannable line above the grid)
quick_label = " · ".join(quick_selected) if quick_selected else "—"
st.markdown(
    f"<div class='filter-summary'>"
    f"<strong>{len(ideas)}</strong> idea{'s' if len(ideas) != 1 else ''} match"
    f"  ·  quick: {quick_label}"
    f"</div>",
    unsafe_allow_html=True,
)

if not ideas:
    st.info("No ideas match these filters. Loosen them or run ideation to generate more.")
    st.stop()

# ───── Auto-fill grid (no st.columns, no pad-empty hack) ─────────────────
parent_map = data.parent_titles_map()
cards_html = ["<div class='ideas-grid'>"]
for idea in ideas:
    pid = idea.get("parent_idea_id")
    cards_html.append(
        styles.idea_card_html(
            idea,
            is_variant=bool(pid),
            parent_title=parent_map.get(pid) if pid else None,
        )
    )
cards_html.append("</div>")
st.markdown("".join(cards_html), unsafe_allow_html=True)
