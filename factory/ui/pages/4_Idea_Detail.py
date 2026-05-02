"""Single idea deep-dive: Overview / Scoring / Research trail / Rationale."""

from __future__ import annotations

import html

import streamlit as st

from factory.ui import auth, data, pivot_flow, styles
from factory.ui.components.radar_chart import render_radar
from factory.ui.components.turn_timeline import render_turn_subset
from factory.ui.nav import render_sidebar

st.set_page_config(page_title="Idea · App Factory", page_icon="💡", layout="wide", initial_sidebar_state="expanded")
styles.inject()
auth.require_login()
render_sidebar()

# ───── Resolve idea ──────────────────────────────────────────────────────

qp = st.query_params
idea_id_raw = qp.get("id")
if idea_id_raw is None:
    top = data.top_pending_ideas(limit=1)
    if not top:
        st.info("No ideas yet. Run ideation first.")
        st.stop()
    idea_id = top[0]["id"]
    st.caption(f"No `id` in URL — showing top pending (#{idea_id}).")
else:
    try:
        idea_id = int(idea_id_raw)
    except (TypeError, ValueError):
        st.error(f"Invalid id: {idea_id_raw!r}")
        st.stop()

idea = data.get_idea(idea_id)
if not idea:
    st.error(f"Idea #{idea_id} not found.")
    st.stop()

# ───── Parent breadcrumb (if this idea is a variant) ────────────────────

parent_idea = None
if idea.get("parent_idea_id"):
    parent_idea = data.get_parent_idea(idea["id"])
    if parent_idea:
        parent_title_safe = html.escape(parent_idea["title"])
        st.markdown(
            f"<a href='Idea_Detail?id={parent_idea['id']}' target='_self' class='breadcrumb-parent'>"
            f"<span class='arrow'>←</span> Parent: <strong>{parent_title_safe}</strong>"
            f"</a>",
            unsafe_allow_html=True,
        )

# ───── Header ────────────────────────────────────────────────────────────

head_left, head_right = st.columns([4, 1])
with head_left:
    variant_mark = " <span class='variant-badge'>↪ variant</span>" if parent_idea else ""
    st.markdown(f"# {idea['title']}" + (f"  {variant_mark}" if parent_idea else ""), unsafe_allow_html=True)
    run_part = f"from run #{idea.get('run_id')} · " if idea.get("run_id") else ""
    st.caption(
        f"#{idea['id']} · {run_part}"
        f"{styles.humanize_feasibility(idea.get('ios_feasibility'))} · "
        f"{styles.format_local_date(idea.get('created_at'))}"
    )
    if parent_idea and idea.get("pivot_note"):
        st.markdown(
            f"<div class='variant-pivot-note' style='margin-top:8px;'>"
            f"<strong>Pivot:</strong> {html.escape(idea['pivot_note'])}"
            f"</div>",
            unsafe_allow_html=True,
        )
with head_right:
    score = idea.get("score")
    score_c = styles.score_color(score)
    st.markdown(
        f"<div class='score-headline'>"
        f"<span class='score-num' style='color:{score_c};'>{score if score is not None else '—'}</span>"
        f"<span class='score-total'>/100</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.markdown(styles.stage_stepper_html(idea.get("stage")), unsafe_allow_html=True)

act1, act2, _spacer = st.columns([1, 1, 4])
with act1:
    st.markdown(
        f"<a href='Idea_Lab?id={idea['id']}' target='_self' "
        f"style='display:inline-block; padding:10px 18px; background:var(--primary); "
        f"color:white; border-radius:8px; text-decoration:none; font-weight:600; "
        f"font-size:13px;'>🧪 Open in Idea Lab</a>",
        unsafe_allow_html=True,
    )
with act2:
    pivot_flow.render_pivot_button(idea)

# Inline form + preview (no-op if neither is active)
pivot_flow.render_pivot_form(idea)
pivot_flow.render_pivot_preview(idea)

# ───── Tabs ──────────────────────────────────────────────────────────────

tab_overview, tab_scoring, tab_research, tab_rationale = st.tabs(
    ["Overview", "Scoring", "Research trail", "Rationale"]
)


def _list_card(items: list[str] | None, kind: str) -> None:
    if not items:
        st.caption("—")
        return
    for item in items:
        safe = html.escape(item)
        st.markdown(f"<div class='list-card {kind}'>{safe}</div>", unsafe_allow_html=True)


# Overview ────────────────────────────────────────────────────────────────
with tab_overview:
    st.markdown(f"**Concept.** {idea.get('concept') or '—'}")
    st.write("")

    meta1, meta2, meta3 = st.columns(3)
    with meta1:
        st.markdown("**Target users**")
        st.write(idea.get("target_users") or "—")
    with meta2:
        st.markdown("**Monetization**")
        st.write(idea.get("monetization") or "—")
    with meta3:
        st.markdown("**Feasibility**")
        st.write(idea.get("ios_feasibility") or "—")

    st.divider()

    col_pro, col_con = st.columns(2)
    with col_pro:
        st.markdown("#### ✅ Pros")
        _list_card(idea.get("pros"), "pro")
    with col_con:
        st.markdown("#### ⚠️ Cons")
        _list_card(idea.get("cons"), "con")

    col_diff, col_risk = st.columns(2)
    with col_diff:
        st.markdown("#### 🎯 Differentiators")
        _list_card(idea.get("differentiators"), "diff")
    with col_risk:
        st.markdown("#### 🔥 Risks")
        _list_card(idea.get("risks"), "risk")

    # Variants-of-this-idea section (shown only if there are variants)
    variants = data.get_variants(idea["id"])
    if variants:
        st.divider()
        st.markdown(f"#### ↪ Variants of this idea ({len(variants)})")
        st.caption("Pivots and alternative framings that branched from this idea.")
        for i in range(0, len(variants), 2):
            vcols = st.columns(2, gap="medium")
            for j, v in enumerate(variants[i : i + 2]):
                with vcols[j]:
                    st.markdown(
                        styles.idea_card_html(
                            v, is_variant=True, parent_title=idea["title"]
                        ),
                        unsafe_allow_html=True,
                    )

# Scoring ─────────────────────────────────────────────────────────────────
with tab_scoring:
    breakdown = idea.get("score_breakdown") or {}
    if not breakdown:
        st.info("No score breakdown stored for this idea.")
    else:
        cchart, cnotes = st.columns([3, 2])
        with cchart:
            fig = render_radar(breakdown)
            st.plotly_chart(fig, use_container_width=True)
        with cnotes:
            notes = breakdown.get("notes") or {}
            total_computed = sum(
                int(breakdown.get(k, 0) or 0)
                for k in ("novelty", "demand", "monetization", "feasibility")
            )
            declared = idea.get("score") or 0
            st.markdown(f"**Declared score:** `{declared}/100`")
            st.markdown(f"**Dimensions sum:** `{total_computed}/100`")
            if abs(declared - total_computed) <= 2:
                st.success("Score verified — declared matches breakdown sum.")
            else:
                st.warning("Declared score differs from breakdown — healer used the sum.")
            st.divider()
            for dim in ("novelty", "demand", "monetization", "feasibility"):
                st.markdown(f"**{dim.capitalize()}**: `{breakdown.get(dim, '—')}/25`")
                note = notes.get(dim) if isinstance(notes, dict) else None
                if note:
                    st.caption(note)
                st.write("")

# Research trail ──────────────────────────────────────────────────────────
with tab_research:
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown("#### 🧠 Reasoning turns preceding this idea")
        st.caption(
            "Best-effort heuristic: the turns Claude ran immediately before calling "
            "`save_idea` for this title."
        )
        turns = data.research_turns_for_idea(idea, lookback=4)
        render_turn_subset(turns, compact=True)

    with col_right:
        st.markdown("#### 🔗 Linked signals")
        signal_ids = idea.get("evidence_signal_ids") or []
        signals = data.get_signals_by_ids(signal_ids) if signal_ids else []
        if signals:
            for s in signals:
                with st.container(border=True):
                    st.markdown(f"**{s.get('title') or '(no title)'}**")
                    st.caption(f"source: `{s.get('source')}` · id: `{s.get('id')}`")
                    if s.get("url"):
                        st.markdown(f"[Open source ↗]({s['url']})")
                    meta = s.get("metadata") if isinstance(s.get("metadata"), dict) else {}
                    compact = {k: meta[k] for k in ("rank", "genre", "rating", "rating_count", "price") if k in meta}
                    if compact:
                        st.caption(" · ".join(f"{k}: {v}" for k, v in compact.items()))
        else:
            st.caption("No signals were linked as evidence.")

        st.markdown("#### 🌐 Evidence URLs")
        urls = idea.get("evidence_urls") or []
        if urls:
            for u in urls:
                st.markdown(f"- [{u}]({u})")
        else:
            st.caption("No URLs recorded.")

        st.markdown("#### ⚔️ Competitors")
        comps = idea.get("key_competitors") or []
        if not comps:
            st.caption("No competitors recorded.")
        else:
            for c in comps:
                name = html.escape(c.get("name") or "(unnamed)")
                name_html = (
                    f"<a href='{html.escape(c['url'])}' target='_blank'>{name}</a>"
                    if c.get("url") else name
                )
                bits = []
                if c.get("rating") is not None:
                    bits.append(f"★ {c['rating']}")
                if c.get("reviews") is not None:
                    try:
                        bits.append(f"{int(c['reviews']):,} reviews")
                    except (TypeError, ValueError):
                        bits.append(f"{c['reviews']} reviews")
                if c.get("pricing"):
                    bits.append(html.escape(c["pricing"]))
                meta_line = (
                    f"<div class='comp-meta'>{' · '.join(bits)}</div>" if bits else ""
                )
                note_line = (
                    f"<div class='comp-note'>{html.escape(c['note'])}</div>"
                    if c.get("note") else ""
                )
                st.markdown(
                    f"<div class='comp-card'>"
                    f"<div class='comp-name'>{name_html}</div>"
                    f"{meta_line}{note_line}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

# Rationale ───────────────────────────────────────────────────────────────
with tab_rationale:
    rationale = idea.get("rationale") or "—"
    st.markdown(rationale)
    st.divider()
    st.markdown("#### Score breakdown notes")
    notes = (idea.get("score_breakdown") or {}).get("notes") or {}
    if notes:
        for dim in ("novelty", "demand", "monetization", "feasibility"):
            if notes.get(dim):
                st.markdown(f"**{dim.capitalize()}** — {notes[dim]}")
    else:
        st.caption("No per-dimension notes stored.")
