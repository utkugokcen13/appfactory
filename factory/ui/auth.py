"""Login gate for the Streamlit app.

Every page calls `auth.require_login()` at the top of its script. If the
session cookie is valid, this returns the username and the page renders
normally. Otherwise, the login form is shown and `st.stop()` is called so
nothing else loads.

Credentials are stored in `factory/ui/auth_users.yaml` as bcrypt hashes.
The cookie signing key comes from `AUTH_COOKIE_KEY` (Streamlit secret).
Use `python -m factory.ui.auth_setup add-user <name>` to add users.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit_authenticator as stauth
import yaml

USERS_PATH = Path(__file__).parent / "auth_users.yaml"
COOKIE_NAME = "appfactory_auth"
COOKIE_EXPIRY_DAYS = 30


def _load_config() -> dict[str, Any]:
    """Load the YAML credentials file. Falls back to a stub config that
    refuses logins so a broken/missing file fails closed (not open)."""
    if not USERS_PATH.exists():
        return {
            "credentials": {"usernames": {}},
            "cookie": {
                "name": COOKIE_NAME,
                "key": _cookie_key(),
                "expiry_days": COOKIE_EXPIRY_DAYS,
            },
        }
    with open(USERS_PATH, "r") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("credentials", {"usernames": {}})
    cfg["cookie"] = {
        "name": COOKIE_NAME,
        "key": _cookie_key(),
        "expiry_days": COOKIE_EXPIRY_DAYS,
    }
    return cfg


def _cookie_key() -> str:
    """Read the cookie signing key. In dev a stable fallback is used; in
    prod (Streamlit Cloud) AUTH_COOKIE_KEY must be set in secrets."""
    key = os.environ.get("AUTH_COOKIE_KEY")
    if key:
        return key
    # Try Streamlit secrets (in case env wasn't propagated yet)
    try:
        return str(st.secrets["AUTH_COOKIE_KEY"])
    except (KeyError, FileNotFoundError, AttributeError):
        # Local dev fallback — fine because dev sessions are throwaway.
        return "local-dev-cookie-key-do-not-use-in-prod"


def _get_authenticator() -> stauth.Authenticate:
    if "_authenticator" in st.session_state:
        return st.session_state["_authenticator"]
    cfg = _load_config()
    auth = stauth.Authenticate(
        credentials=cfg["credentials"],
        cookie_name=cfg["cookie"]["name"],
        cookie_key=cfg["cookie"]["key"],
        cookie_expiry_days=cfg["cookie"]["expiry_days"],
    )
    st.session_state["_authenticator"] = auth
    return auth


def current_user() -> str | None:
    """Username of the logged-in user, or None if no session."""
    return st.session_state.get("username")


def _render_sidebar_user(auth: stauth.Authenticate) -> None:
    """Sidebar pill showing the logged-in user + a Logout button. Lives in
    auth.py (not nav.py) so every page's sidebar is consistent."""
    with st.sidebar:
        user = st.session_state.get("name") or st.session_state.get("username", "")
        st.markdown(
            f"<div class='auth-user-pill'>"
            f"<span class='auth-user-dot'></span>"
            f"<span class='auth-user-name'>{user}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        auth.logout(button_name="Logout", location="sidebar", key="logout_btn")


def require_login() -> str:
    """Block the page until the user is logged in. Returns the username on
    success. Call this once at the top of every page (after set_page_config
    + styles.inject() but before any data fetch).

    Critical: we call `auth.login()` ONLY when the user isn't already
    authenticated. streamlit-authenticator 0.4.x renders the form
    unconditionally when login() is invoked — calling it for already-logged-
    in users leaves a stale form on screen until the next user interaction.
    """
    auth = _get_authenticator()

    # Fast path: cookie or previous login already set the status to True.
    # Skip rendering the form widget entirely.
    if st.session_state.get("authentication_status") is True:
        _render_sidebar_user(auth)
        return st.session_state.get("username", "")

    # Render the login form inside a placeholder. The placeholder lets us
    # WIPE the form before rerun() so the user doesn't see it lingering on
    # screen during the redirect transition.
    form_slot = st.empty()
    with form_slot.container():
        auth.login(location="main", key="login_widget")

    # If login() just succeeded (form submit or cookie), replace the form
    # with a "Loading…" spinner and rerun. The spinner stays on screen
    # during the transition so the UX feels instant.
    if st.session_state.get("authentication_status") is True:
        form_slot.empty()
        form_slot.markdown(
            "<div class='auth-redirect'>"
            "<div class='auth-redirect-spinner'></div>"
            "<div class='auth-redirect-text'>Welcome — loading dashboard…</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.rerun()

    status = st.session_state.get("authentication_status")
    if status is False:
        st.error("Username veya şifre hatalı.")
    elif status is None:
        st.caption("Devam etmek için giriş yap.")

    st.stop()
    return ""  # unreachable; satisfies type checker
