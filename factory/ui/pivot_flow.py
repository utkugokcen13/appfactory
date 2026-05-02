"""Explicit 'Pivot this idea' flow: button → form → preview → save/discard.

The UX complements the chat-driven `create_variant_idea` tool: anyone who
prefers a structured form over a chat prompt gets a drafting surface with a
preview before the DB write.

State lives in `st.session_state`:
  - `pivot_form_open_<idea_id>` : bool — form visible?
  - `pivot_draft_<idea_id>`     : dict | None — staged draft waiting for approval
"""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from factory.ideation import store


def _form_key(idea_id: int) -> str:
    return f"pivot_form_open_{idea_id}"


def _draft_key(idea_id: int) -> str:
    return f"pivot_draft_{idea_id}"


def _feasibility_options() -> list[str]:
    return ["solo-1wk", "solo-1mo", "solo-3mo", "team-only"]


def render_pivot_button(parent: dict[str, Any]) -> None:
    """Toggle button that opens/closes the Pivot form for this idea."""
    key = f"pivot_btn_{parent['id']}"
    is_open = st.session_state.get(_form_key(parent["id"]), False)
    label = "✕ Cancel pivot" if is_open else "🎯 Pivot this idea…"
    if st.button(label, key=key):
        st.session_state[_form_key(parent["id"])] = not is_open
        # Clear any stale draft when toggling form open
        if not is_open:
            st.session_state.pop(_draft_key(parent["id"]), None)
        st.rerun()


def render_pivot_form(parent: dict[str, Any]) -> None:
    """Inline form for drafting a variant. Stages into session_state only."""
    if not st.session_state.get(_form_key(parent["id"]), False):
        return

    with st.container(border=True):
        st.markdown("### 🎯 Draft a variant")
        st.caption(
            "Edit the fields that change in your pivot. Unchanged fields will be "
            "copied from the parent. Required: **Pivot note** — a single line "
            "describing the delta."
        )

        with st.form(key=f"pivot_form_{parent['id']}"):
            new_title = st.text_input(
                "Title",
                value=f"{parent.get('title') or ''} — variant",
                max_chars=120,
            )
            pivot_note = st.text_area(
                "Pivot note (required)",
                placeholder="e.g. 'drop B2B, target prosumers at $9.99/mo'",
                max_chars=200,
                height=70,
            )
            new_concept = st.text_area(
                "Concept",
                value=parent.get("concept") or "",
                height=160,
                help="Adjust the concept paragraph to reflect the pivot.",
            )
            c1, c2 = st.columns(2)
            with c1:
                new_target = st.text_area(
                    "Target users",
                    value=parent.get("target_users") or "",
                    height=80,
                )
            with c2:
                new_monetization = st.text_area(
                    "Monetization",
                    value=parent.get("monetization") or "",
                    height=80,
                )
            feas_opts = _feasibility_options()
            current_feas = parent.get("ios_feasibility") or feas_opts[1]
            new_feas = st.selectbox(
                "Feasibility",
                feas_opts,
                index=feas_opts.index(current_feas) if current_feas in feas_opts else 1,
            )

            submit_col, cancel_col = st.columns([1, 1])
            submitted = submit_col.form_submit_button("Stage draft →", type="primary")
            cancelled = cancel_col.form_submit_button("Cancel")

        if cancelled:
            st.session_state[_form_key(parent["id"])] = False
            st.session_state.pop(_draft_key(parent["id"]), None)
            st.rerun()

        if submitted:
            if not pivot_note.strip():
                st.error("Pivot note is required — this is what makes the variant auditable later.")
                return
            if not new_title.strip() or not new_concept.strip():
                st.error("Title and concept can't be empty.")
                return
            st.session_state[_draft_key(parent["id"])] = {
                "title": new_title.strip(),
                "pivot_note": pivot_note.strip(),
                "concept": new_concept.strip(),
                "target_users": new_target.strip() or None,
                "monetization": new_monetization.strip() or None,
                "ios_feasibility": new_feas,
            }
            st.rerun()


def _diff_style(parent_val: str | None, draft_val: str | None) -> str:
    return (
        "padding: 10px 12px; border-radius: 8px; background: var(--card); "
        "border: 1px solid var(--border);"
        + (" border-left: 3px solid #A855F7;" if (parent_val or "") != (draft_val or "") else "")
    )


def render_pivot_preview(parent: dict[str, Any]) -> None:
    """If a draft exists, show side-by-side parent vs draft with Save/Discard."""
    draft = st.session_state.get(_draft_key(parent["id"]))
    if not draft:
        return

    with st.container(border=True):
        st.markdown("### 📝 Proposed variant — review")
        st.caption("Fields that differ from the parent are outlined in purple.")

        def _col_pair(label: str, parent_val: Any, draft_val: Any) -> None:
            st.markdown(f"**{label}**")
            cp, cd = st.columns(2)
            with cp:
                st.caption("Parent")
                st.markdown(
                    f"<div style='{_diff_style(parent_val, draft_val).replace('#A855F7', 'var(--border)')}'>"
                    f"{html.escape(str(parent_val or '—'))}</div>",
                    unsafe_allow_html=True,
                )
            with cd:
                st.caption("Draft")
                st.markdown(
                    f"<div style='{_diff_style(parent_val, draft_val)}'>"
                    f"{html.escape(str(draft_val or '—'))}</div>",
                    unsafe_allow_html=True,
                )

        _col_pair("Title", parent.get("title"), draft.get("title"))
        _col_pair("Concept", (parent.get("concept") or "")[:600], (draft.get("concept") or "")[:600])
        _col_pair("Target users", parent.get("target_users"), draft.get("target_users"))
        _col_pair("Monetization", parent.get("monetization"), draft.get("monetization"))
        _col_pair("Feasibility", parent.get("ios_feasibility"), draft.get("ios_feasibility"))

        st.markdown("**Pivot note**")
        st.markdown(
            f"<div class='variant-pivot-note'>{html.escape(draft.get('pivot_note') or '')}</div>",
            unsafe_allow_html=True,
        )

        st.write("")
        save_col, discard_col, _ = st.columns([1, 1, 3])
        if save_col.button("✓ Save variant", type="primary", key=f"pivot_save_{parent['id']}"):
            _save_variant(parent, draft)
        if discard_col.button("✗ Discard", key=f"pivot_discard_{parent['id']}"):
            st.session_state.pop(_draft_key(parent["id"]), None)
            st.session_state[_form_key(parent["id"])] = False
            st.rerun()


def _save_variant(parent: dict[str, Any], draft: dict[str, Any]) -> None:
    """Persist the draft as a new idea with parent_idea_id + pivot_note set."""
    # Carry parent's structured fields the form didn't touch (pros/cons/score etc).
    # The user can evolve them later in Idea Lab.
    def _as_list(v: Any) -> list:
        if isinstance(v, list):
            return v
        return []

    def _as_dict(v: Any) -> dict:
        if isinstance(v, dict):
            return v
        return {}

    with store.connect() as conn:
        new_id = store.save_idea(
            conn,
            run_id=None,
            title=draft["title"],
            concept=draft["concept"],
            target_users=draft.get("target_users"),
            monetization=draft.get("monetization") or parent.get("monetization"),
            ios_feasibility=draft.get("ios_feasibility") or parent.get("ios_feasibility"),
            score=parent.get("score"),
            score_breakdown=_as_dict(parent.get("score_breakdown")),
            rationale=parent.get("rationale"),
            evidence_urls=_as_list(parent.get("evidence_urls")),
            evidence_signal_ids=_as_list(parent.get("evidence_signal_ids")),
            pros=_as_list(parent.get("pros")),
            cons=_as_list(parent.get("cons")),
            risks=_as_list(parent.get("risks")),
            differentiators=_as_list(parent.get("differentiators")),
            key_competitors=_as_list(parent.get("key_competitors")),
            parent_idea_id=parent["id"],
            pivot_note=draft["pivot_note"],
        )

    # Clear state + navigate to new variant
    st.session_state.pop(_draft_key(parent["id"]), None)
    st.session_state[_form_key(parent["id"])] = False
    st.query_params["id"] = str(new_id)
    st.success(f"Variant #{new_id} saved — opening…")
    st.rerun()
