"""Idea Lab — conversational refinement of a saved idea.

URL: /Idea_Lab?id=N[&chat=K]
  id   — idea id (required)
  chat — optional chat_id; defaults to most recent, or auto-starts one
"""

from __future__ import annotations

# sys.path: ensure repo root is importable on Streamlit Cloud (see app.py).
import sys as _sys
from pathlib import Path as _Path
_root = str(_Path(__file__).resolve().parents[3])
if _root not in _sys.path:
    _sys.path.insert(0, _root)

import html
import json

import streamlit as st

from factory.lab.chat_agent import run_chat_turn
from factory.ui import auth, data, pivot_flow, styles
from factory.ui.components.radar_chart import render_radar
from factory.ui.nav import render_sidebar

st.set_page_config(
    page_title="Idea Lab · App Factory",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)
styles.inject()
auth.require_login()
render_sidebar()

# ───── Resolve idea + chat ──────────────────────────────────────────────

qp = st.query_params
idea_id_raw = qp.get("id")
if idea_id_raw is None:
    st.info("No idea selected. Open an idea from the Ideas list first.")
    st.stop()
try:
    idea_id = int(idea_id_raw)
except (TypeError, ValueError):
    st.error(f"Invalid id: {idea_id_raw!r}")
    st.stop()

# Always re-read after a turn so field updates are visible immediately
idea = data.get_idea(idea_id)
if not idea:
    st.error(f"Idea #{idea_id} not found.")
    st.stop()


def _start_new_chat() -> int:
    from factory.ideation import store
    with store.connect() as c:
        return store.start_chat(c, idea_id=idea_id, title=None)


existing_chats = data.list_chats_for_idea(idea_id)
chat_id_raw = qp.get("chat")
if chat_id_raw is not None:
    try:
        chat_id = int(chat_id_raw)
    except (TypeError, ValueError):
        chat_id = None
else:
    chat_id = None

if chat_id is None:
    if existing_chats:
        chat_id = existing_chats[0]["id"]
    else:
        chat_id = _start_new_chat()

chat = data.get_chat(chat_id)
if not chat:
    chat_id = _start_new_chat()
    chat = data.get_chat(chat_id)

# ───── Layout ────────────────────────────────────────────────────────────

left, right = st.columns([1, 2], gap="large")

# ───── LEFT: Idea summary + quick actions ──────────────────────────────
with left:
    st.markdown(f"### {idea['title']}")
    score = idea.get("score")
    score_c = styles.score_color(score)
    st.markdown(
        f"<div style='font-size:28px; font-weight:700; color:{score_c};'>"
        f"{score if score is not None else '—'}"
        f"<span style='color:var(--text-sub); font-size:14px;'> /100</span></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"#{idea['id']} · {idea.get('ios_feasibility') or '—'} · stage: `{idea.get('stage')}`"
    )
    st.markdown(styles.stage_stepper_html(idea.get("stage")), unsafe_allow_html=True)

    with st.expander("Radar breakdown", expanded=False):
        fig = render_radar(idea.get("score_breakdown") or {})
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Concept", expanded=True):
        st.write(idea.get("concept") or "—")

    variants = data.get_variants(idea_id)
    if variants:
        st.markdown("### Variants")
        for v in variants:
            st.markdown(
                f"- ↪ [**{v['title']}**](Idea_Detail?id={v['id']}) · "
                f"score {v.get('score')}"
            )
            if v.get("pivot_note"):
                st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;*{v['pivot_note']}*", unsafe_allow_html=True)

    st.markdown("### Chat sessions")
    if existing_chats:
        for c in existing_chats[:6]:
            is_active = c["id"] == chat_id
            marker = "● " if is_active else ""
            label = (c.get("title") or f"Session #{c['id']}")[:50]
            msg_n = c.get("msg_count") or 0
            st.markdown(
                f"{marker}[{label}](Idea_Lab?id={idea_id}&chat={c['id']}) "
                f"<span style='color:var(--text-sub); font-size:11px;'>({msg_n} msg)</span>",
                unsafe_allow_html=True,
            )
    if st.button("➕ New chat", use_container_width=True):
        new_id = _start_new_chat()
        st.query_params["chat"] = str(new_id)
        st.rerun()

    st.markdown("### Pivot")
    pivot_flow.render_pivot_button(idea)

    st.markdown("### Quick actions")
    presets = [
        ("🔍 Run quick validation", "Run a quick validation pass on this idea: score the monetization assumption, sanity-check the top 3 competitors, and give me a GO / NEEDS-WORK / NO-GO."),
        ("⚔️ Competitor teardown", "Teardown the 3-5 closest competitors: rating, review count if known, positioning, gaps. Cite App Store URLs."),
        ("💰 Pricing sanity", "Validate the pricing hypothesis. What do comparable apps charge? What's the ceiling for my target users?"),
        ("📈 TAM estimate", "Rough TAM estimate — how many users could realistically pay, based on category signals I have?"),
        ("🎯 Sharpen differentiation", "Tighten the differentiators section — what's the one thing this MUST own vs incumbents?"),
    ]
    for label, prompt in presets:
        if st.button(label, use_container_width=True, key=f"preset_{label}"):
            st.session_state.lab_pending_input = prompt
            st.rerun()

# ───── Pivot form + preview (render at full width if active) ───────────
pivot_flow.render_pivot_form(idea)
pivot_flow.render_pivot_preview(idea)

# ───── RIGHT: Chat thread ───────────────────────────────────────────────
with right:
    st.markdown("### Chat")
    st.caption(
        f"Session #{chat_id} · started {styles.format_local_dt(chat.get('started_at'))}"
    )

    messages = data.load_chat_messages(chat_id)
    if not messages:
        st.info("Start a conversation — ask anything about this idea, or use a Quick action on the left.")
    else:
        for m in messages:
            role = m["role"]
            if role == "user":
                text = html.escape(m.get("text") or "")
                st.markdown(
                    f"<div class='lab-msg user'><div class='bubble'>{text}</div></div>",
                    unsafe_allow_html=True,
                )
            elif role == "assistant_text":
                # Render as markdown inside our styled container
                bubble_inner = st.container()
                st.markdown(
                    "<div class='lab-msg assistant'><div class='bubble'>",
                    unsafe_allow_html=True,
                )
                st.markdown(m.get("text") or "")
                st.markdown("</div></div>", unsafe_allow_html=True)
            elif role == "assistant_tool_use":
                tool_name = m.get("tool_name") or "?"
                try:
                    tin = json.loads(m.get("tool_input") or "{}")
                except json.JSONDecodeError:
                    tin = {}
                # Short summary line for the call
                preview_keys = ("query", "source", "url", "keyword", "field", "title", "subreddit")
                preview = " · ".join(
                    f"{k}={tin[k]!r}" for k in preview_keys if k in tin and tin[k] is not None
                )
                preview = preview[:200]
                st.markdown(
                    f"<div class='lab-tool-call'>"
                    f"<span class='tool-name'>🔧 {tool_name}</span>"
                    + (f" — {html.escape(preview)}" if preview else "")
                    + "</div>",
                    unsafe_allow_html=True,
                )
                with st.expander("tool call + result", expanded=False):
                    st.markdown("**Input**")
                    st.json(tin)
            elif role == "tool_result":
                # Attach under most recent tool_use expander is tricky in Streamlit.
                # Render a subtle marker instead and an expander with full content.
                tr_text = m.get("tool_result") or ""
                is_err = bool(m.get("tool_error"))
                icon = "❌" if is_err else "✓"
                summary = ""
                try:
                    parsed = json.loads(tr_text)
                    if isinstance(parsed, dict):
                        if "count" in parsed:
                            summary = f"{parsed['count']} results"
                        elif "variant_id" in parsed:
                            summary = f"variant #{parsed['variant_id']} created"
                        elif "idea_id" in parsed and parsed.get("field"):
                            summary = f"updated {parsed.get('field')}"
                        elif "available" in parsed:
                            summary = "trend data" if parsed.get("available") else "trend unavailable"
                        elif "error" in parsed:
                            summary = f"error: {str(parsed['error'])[:80]}"
                except json.JSONDecodeError:
                    summary = tr_text[:80]
                with st.expander(f"{icon} {summary or 'tool result'}", expanded=False):
                    try:
                        st.json(json.loads(tr_text))
                    except json.JSONDecodeError:
                        st.code(tr_text, language="text")

    st.write("")

    # Input — handle preset injection
    default_input = st.session_state.pop("lab_pending_input", "") if "lab_pending_input" in st.session_state else ""

    with st.container():
        if default_input:
            st.info(f"Prefilled: _{default_input[:120]}…_")
        user_input = st.chat_input("Ask something, pivot the idea, or sharpen a field...")

    # If a preset was clicked, use it; otherwise use the chat_input value.
    submit_text = default_input or user_input

    if submit_text:
        with st.spinner("Claude is thinking..."):
            try:
                result = run_chat_turn(
                    chat_id=chat_id,
                    idea=idea,
                    user_text=submit_text,
                )
                ctx_hints = []
                if result.variants_created:
                    ctx_hints.append(f"{len(result.variants_created)} variant(s) created")
                if result.fields_updated:
                    ctx_hints.append("updated: " + ", ".join(result.fields_updated))
                hint = " · ".join(ctx_hints)
                if hint:
                    st.success(hint)
            except Exception as e:
                st.error(f"Chat turn failed: {type(e).__name__}: {e}")
        st.rerun()
