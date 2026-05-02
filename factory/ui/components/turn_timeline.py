"""Reusable expandable turn viewer.

Used in Run Detail (full trace) and Idea Detail (filtered subset).
Each turn: header with token + stop_reason, then blocks inline.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from factory.ui import data


def _format_block(block: dict[str, Any]) -> None:
    btype = block.get("block_type")
    if btype == "text":
        text = block.get("text") or ""
        if text.strip():
            st.markdown(f"💬 {text}")
    elif btype == "tool_use":
        name = block.get("tool_name", "?")
        parsed = block.get("tool_input_parsed") or {}
        st.markdown(f"🔧 **`{name}`**")
        if parsed:
            # Compact one-line preview for common fields
            preview_keys = ("query", "source", "url", "title", "limit", "num_results")
            preview = {k: v for k, v in parsed.items() if k in preview_keys and v is not None}
            if preview:
                for k, v in preview.items():
                    st.markdown(f"&nbsp;&nbsp;&nbsp;`{k}`: `{v!r}`", unsafe_allow_html=True)
            with st.expander("Full input JSON", expanded=False):
                st.json(parsed)
    elif btype == "tool_result":
        result_raw = block.get("tool_result") or ""
        is_err = bool(block.get("tool_error"))
        icon = "❌" if is_err else "✓"
        # Try to give a short summary
        summary = ""
        try:
            parsed = json.loads(result_raw)
            if isinstance(parsed, dict):
                if "count" in parsed:
                    summary = f"{parsed.get('count')} results"
                elif "idea_id" in parsed:
                    summary = f"idea saved (#{parsed.get('idea_id')}, score {parsed.get('final_score', '?')})"
                elif "error" in parsed:
                    summary = f"error: {str(parsed['error'])[:80]}"
                elif "url" in parsed:
                    summary = f"fetched {parsed.get('url')}"
        except json.JSONDecodeError:
            summary = result_raw[:120]
        st.markdown(f"{icon} {summary or 'result'}")
        with st.expander("Full result", expanded=False):
            try:
                st.json(json.loads(result_raw))
            except json.JSONDecodeError:
                st.code(result_raw, language="text")


def render_run_timeline(run_id: int) -> None:
    turns = data.get_turns(run_id)
    if not turns:
        st.info("No turns persisted for this run.")
        return
    for t in turns:
        header = (
            f"Turn {t['turn_number']} · "
            f"{t.get('input_tokens', 0):,} in / {t.get('output_tokens', 0):,} out · "
            f"`{t.get('stop_reason', '?')}`"
        )
        with st.expander(header, expanded=t["turn_number"] <= 2):
            blocks = data.get_blocks(t["id"])
            for b in blocks:
                _format_block(b)
                st.write("")  # gap


def render_turn_subset(turns: list[dict], compact: bool = True) -> None:
    """Used by Idea Detail's research trail: render a slice of turns."""
    if not turns:
        st.info("No turns found for this idea.")
        return
    for t in turns:
        label = f"Turn {t['turn_number']} · {t.get('input_tokens', 0):,} in / {t.get('output_tokens', 0):,} out"
        with st.expander(label, expanded=not compact):
            blocks = data.get_blocks(t["id"])
            for b in blocks:
                _format_block(b)
                st.write("")
