"""Login gate for the Streamlit app.

Every page calls `auth.require_login()` at the top of its script. If the
session cookie is valid, this returns the username and the page renders
normally. Otherwise, the login form is shown and `st.stop()` is called so
nothing else loads.

Credentials are stored in `factory/ui/auth_users.yaml` as bcrypt hashes.

Cookie persistence: streamlit-authenticator 0.4.x ships an iframe-based
CookieManager (via `extra-streamlit-components`) whose set/delete calls
silently no-op against newer Streamlit versions — so the auth cookie never
makes it to the browser. We sidestep that by issuing our OWN signed JWT
cookie using `streamlit-cookies-controller` for the write side and
`st.context.cookies` for the read side. stauth is still used for the form
UI + bcrypt password check, but its built-in cookie path is ignored.

The cookie signing key comes from `AUTH_COOKIE_KEY` (Streamlit secret).
Use `python -m factory.ui.auth_setup add-user <name>` to add users.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from streamlit_cookies_controller import CookieController

USERS_PATH = Path(__file__).parent / "auth_users.yaml"
COOKIE_NAME = "appfactory_auth"
COOKIE_EXPIRY_DAYS = 30
JWT_ALG = "HS256"


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
    try:
        return str(st.secrets["AUTH_COOKIE_KEY"])
    except (KeyError, FileNotFoundError, AttributeError):
        return "local-dev-cookie-key-do-not-use-in-prod"


def _get_authenticator() -> stauth.Authenticate:
    if "_authenticator" in st.session_state:
        return st.session_state["_authenticator"]
    cfg = _load_config()
    auth = stauth.Authenticate(
        credentials=cfg["credentials"],
        cookie_name=cfg["cookie"]["name"],
        cookie_key=cfg["cookie"]["key"],
        cookie_expiry_days=0,  # disable stauth's broken cookie write entirely
    )
    st.session_state["_authenticator"] = auth
    return auth


def _get_cookie_controller() -> CookieController:
    """One controller per session, cached so we don't render multiple
    component iframes on the same page (each one would race the others)."""
    if "_cookie_controller" not in st.session_state:
        st.session_state["_cookie_controller"] = CookieController(key="appfactory_cookies")
    return st.session_state["_cookie_controller"]


def _encode_token(username: str) -> str:
    payload = {
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(days=COOKIE_EXPIRY_DAYS),
    }
    return jwt.encode(payload, _cookie_key(), algorithm=JWT_ALG)


def _decode_token(token: str) -> str | None:
    """Verify the JWT and return the username, or None if invalid/expired."""
    try:
        data = jwt.decode(token, _cookie_key(), algorithms=[JWT_ALG])
    except (jwt.InvalidTokenError, jwt.DecodeError):
        return None
    username = data.get("username")
    return username if isinstance(username, str) and username else None


def _try_cookie_login() -> str | None:
    """Read the auth cookie from the incoming request and, if valid, mark
    this session as authenticated. Returns the username on success.

    `st.context.cookies` is populated synchronously from the HTTP request
    headers, so this works on the very first script run after a reload —
    no need to wait for a component round-trip."""
    raw = (st.context.cookies or {}).get(COOKIE_NAME) if st.context else None
    if not raw:
        return None
    username = _decode_token(raw)
    if not username:
        return None
    st.session_state["authentication_status"] = True
    st.session_state["username"] = username
    st.session_state["name"] = username
    st.session_state["logout"] = None  # stauth's cookie_model reads this key
    return username


def _persist_cookie(username: str) -> None:
    """Write the signed auth cookie to the browser via streamlit-cookies-
    controller. The library renders a component iframe that flushes the
    cookie on the next browser tick — by the time the user reloads the
    page the cookie is in `document.cookie` and arrives in
    `st.context.cookies`."""
    controller = _get_cookie_controller()
    token = _encode_token(username)
    controller.set(
        COOKIE_NAME,
        token,
        max_age=COOKIE_EXPIRY_DAYS * 24 * 60 * 60,
        same_site="lax",
    )


def _clear_cookie() -> None:
    controller = _get_cookie_controller()
    try:
        controller.remove(COOKIE_NAME)
    except Exception:  # noqa: BLE001
        pass


def current_user() -> str | None:
    """Username of the logged-in user, or None if no session."""
    return st.session_state.get("username")


def _logout_now() -> None:
    """Wipe local session state + browser cookie, then rerun to the login."""
    _clear_cookie()
    for k in ("authentication_status", "username", "name", "_authenticator"):
        st.session_state.pop(k, None)
    st.session_state["logout"] = True
    st.rerun()


def _render_sidebar_user() -> None:
    """Sidebar pill showing the logged-in user + a Logout button."""
    with st.sidebar:
        user = st.session_state.get("name") or st.session_state.get("username", "")
        st.markdown(
            f"<div class='auth-user-pill'>"
            f"<span class='auth-user-dot'></span>"
            f"<span class='auth-user-name'>{user}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button("Logout", key="logout_btn", use_container_width=True):
            _logout_now()


def require_login() -> str:
    """Block the page until the user is logged in. Returns the username on
    success. Call this once at the top of every page (after set_page_config
    + styles.inject() but before any data fetch)."""
    # Already authenticated this session — fast path.
    if st.session_state.get("authentication_status") is True:
        _render_sidebar_user()
        return st.session_state.get("username", "")

    # Try cookie auto-login (synchronous read from request headers).
    user = _try_cookie_login()
    if user:
        _render_sidebar_user()
        return user

    auth = _get_authenticator()

    # Render the login form. We use a placeholder so we can wipe it once
    # the user logs in successfully — the page below then renders inline,
    # no rerun needed.
    form_slot = st.empty()
    with form_slot.container():
        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            auth.login(location="main", key="login_widget")

    if st.session_state.get("authentication_status") is True:
        username = st.session_state.get("username") or ""
        if username:
            _persist_cookie(username)
        form_slot.empty()
        _render_sidebar_user()
        return username

    status = st.session_state.get("authentication_status")
    if status is False:
        st.error("Username veya şifre hatalı.")

    st.stop()
    return ""  # unreachable; satisfies type checker
