"""Custom sidebar navigation.

Default Streamlit multipage nav is disabled via .streamlit/config.toml.
This module renders a clean sidebar that omits detail pages
(Run Detail, Idea Detail) — those are reachable only via cards/links.
"""

from __future__ import annotations

import streamlit as st


def render_sidebar(active: str | None = None) -> None:
    with st.sidebar:
        st.markdown(
            "<div class='brand'>"
            "<span class='brand-mark'>⚒</span>"
            "<span class='brand-name'>App Factory</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div class='nav-group'>", unsafe_allow_html=True)
        st.page_link("app.py", label="Home", icon="🏠")
        st.page_link("pages/1_Runs.py", label="Runs", icon="📊")
        st.page_link("pages/3_Ideas.py", label="Ideas", icon="💡")
        st.page_link("pages/5_Signals.py", label="Signals", icon="📡")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='sidebar-footer'>", unsafe_allow_html=True)
        st.caption("v0.1 · Opus 4.7 on Bedrock")
        st.markdown("</div>", unsafe_allow_html=True)
