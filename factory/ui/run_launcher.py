"""On-demand ideation runner: a Streamlit button that spawns `run_daily` as
a detached subprocess and surfaces live progress.

State coordination is via the SQLite `runs` table:
  - subprocess inserts a row with status='running' at start (`store.start_run`)
  - subprocess updates status='ok'|'error' at end (`store.finish_run`)
  - we mark stuck-runs (no turn updates for >10 min, started >30 min ago)
    as 'crashed' before showing the launcher, so the button isn't blocked
    forever by a dead subprocess.
"""

from __future__ import annotations

import html
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from factory.ideation import store
from factory.ideation.discovery_sources import (
    CATEGORIES as DISCOVERY_CATEGORIES,
    DISCOVERY_SOURCES,
    PRESET_DESCRIPTIONS as DISCOVERY_PRESET_DESCRIPTIONS,
    PRESET_NAMES as DISCOVERY_PRESET_NAMES,
    SOURCES_BY_ID,
    default_selection as default_discovery_selection,
    sources_for_preset,
    sources_in_category,
    subreddits_from_selection,
)
from factory.ideation.presets import PRESETS, PRESET_NAMES
from factory.ideation.run_config import (
    FEASIBILITY_OPTIONS,
    MODELS,
    MONETIZATION_OPTIONS,
    RunConfig,
)
from factory.ui import styles as _styles

LOG_DIR = Path("output/ideation/logs")
CONFIG_DIR = Path("output/ideation/configs")
STALE_AFTER_MIN = 30
NO_PROGRESS_MIN = 10


from contextlib import contextmanager as _contextmanager
from factory.ui import data as _data


@_contextmanager
def _conn():  # type: ignore[no-untyped-def]
    """Routed through the data module's cached connection — same singleton
    is reused across reruns and across data.py / run_launcher.py."""
    conn = _data._shared_conn()
    try:
        yield conn
    except Exception:
        try:
            _data._shared_conn.clear()
        except Exception:  # noqa: BLE001
            pass
        raise


def mark_stale_runs() -> int:
    """Mark long-stuck runs as 'crashed' so the launcher doesn't get blocked."""
    started_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STALE_AFTER_MIN)).isoformat()
    activity_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=NO_PROGRESS_MIN)).isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT r.id, COALESCE(MAX(t.created_at), r.started_at) AS last_act "
            "FROM runs r LEFT JOIN turns t ON t.run_id = r.id "
            "WHERE r.status = 'running' AND r.started_at < ? "
            "GROUP BY r.id "
            "HAVING last_act < ?",
            (started_cutoff, activity_cutoff),
        ).fetchall()
        run_ids = [r["id"] for r in rows]
        for rid in run_ids:
            c.execute(
                "UPDATE runs SET status='crashed', finished_at=?, "
                "error='no progress for >10min — process likely killed' "
                "WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), rid),
            )
        c.commit()
    return len(run_ids)


def in_flight_run() -> dict[str, Any] | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM runs WHERE status='running' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def in_flight_progress(run_id: int) -> dict[str, Any]:
    with _conn() as c:
        turns = c.execute(
            "SELECT COUNT(*), COALESCE(MAX(created_at), '') "
            "FROM turns WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        ideas = c.execute(
            "SELECT COUNT(*) FROM ideas WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
    return {
        "turns": int(turns[0] or 0),
        "ideas": int(ideas or 0),
        "last_turn_at": turns[1] or "",
    }


def _python_executable() -> str:
    return sys.executable or "python3"


def spawn_run(cfg: RunConfig, *, username: str | None = None) -> Path:
    """Write config JSON + spawn detached subprocess. Returns the log file path.
    `username` is forwarded to the child via APPFACTORY_USER so the runs row
    is tagged correctly for per-user cap accounting."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = LOG_DIR / f"launcher_{ts}.log"
    cfg_path = CONFIG_DIR / f"run_{ts}.json"
    cfg.to_json(cfg_path)

    cmd = [
        _python_executable(), "-u", "-m", "factory.ideation.run_daily",
        "--config", str(cfg_path),
    ]
    env = os.environ.copy()
    if username:
        env["APPFACTORY_USER"] = username
    log_f = open(log_path, "ab")
    subprocess.Popen(
        cmd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=str(Path.cwd()),
        start_new_session=True,
    )
    return log_path


def _format_elapsed(started_at: str | None) -> str:
    if not started_at:
        return ""
    try:
        s = datetime.fromisoformat(started_at)
    except ValueError:
        return ""
    delta = datetime.now(timezone.utc) - s
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m {secs % 60:02d}s"


def _ago(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    try:
        s = datetime.fromisoformat(iso_str)
    except ValueError:
        return "—"
    secs = int((datetime.now(timezone.utc) - s).total_seconds())
    if secs < 0:
        return "now"
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    return f"{secs // 3600}h ago"


def _fmt_compact(n: int) -> str:
    n = int(n or 0)
    if n < 1000:
        return str(n)
    if n < 10_000:
        return f"{n/1000:.2f}k"
    if n < 1_000_000:
        return f"{n/1000:.1f}k"
    return f"{n/1_000_000:.2f}M"


_TOOL_ICONS = {
    "search_signals": "🔎",
    "search_reddit":  "🟠",
    "get_trend":      "📈",
    "web_search":     "🌐",
    "fetch_url":      "📄",
    "save_idea":      "💾",
}


def _format_tool_input(tool_name: str, tin: dict[str, Any]) -> str:
    if tool_name == "search_reddit":
        sub = tin.get("subreddit")
        q = (tin.get("query") or "").strip()
        if sub:
            return f"r/{sub}" + (f' · "{q[:50]}"' if q else "")
        return f'"{q[:60]}"' if q else "—"
    if tool_name == "get_trend":
        return f'"{(tin.get("keyword") or "")[:60]}"'
    if tool_name == "search_signals":
        q = (tin.get("query") or "—").strip()
        s = tin.get("source")
        return f'"{q[:50]}"' + (f" · {s}" if s else "")
    if tool_name == "web_search":
        return f'"{(tin.get("query") or "")[:60]}"'
    if tool_name == "fetch_url":
        url = tin.get("url") or ""
        url = url.replace("https://", "").replace("http://", "")
        return url[:60]
    if tool_name == "save_idea":
        title = tin.get("title") or "(untitled)"
        score = tin.get("score", "?")
        return f'"{title[:50]}" — {score}/100'
    return json.dumps(tin)[:60]


def live_activity(run_id: int) -> dict[str, Any]:
    """Snapshot of what the agent is doing right now: current tool, recent
    activity feed, last-text reasoning, ideas saved this run, token totals."""
    with _conn() as c:
        last_tool = c.execute(
            "SELECT tb.tool_name, tb.tool_input, t.turn_number, t.created_at "
            "FROM turn_blocks tb JOIN turns t ON tb.turn_id = t.id "
            "WHERE t.run_id = ? AND tb.block_type = 'tool_use' "
            "ORDER BY t.turn_number DESC, tb.seq DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        last_text = c.execute(
            "SELECT tb.text, t.created_at FROM turn_blocks tb "
            "JOIN turns t ON tb.turn_id = t.id "
            "WHERE t.run_id = ? AND tb.block_type = 'text' "
            "  AND tb.text IS NOT NULL AND tb.text != '' "
            "ORDER BY t.turn_number DESC, tb.seq DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        recent_rows = c.execute(
            "SELECT tb.tool_name, tb.tool_input, t.turn_number, t.created_at "
            "FROM turn_blocks tb JOIN turns t ON tb.turn_id = t.id "
            "WHERE t.run_id = ? AND tb.block_type = 'tool_use' "
            "ORDER BY t.turn_number DESC, tb.seq DESC LIMIT 8",
            (run_id,),
        ).fetchall()
        idea_rows = c.execute(
            "SELECT id, title, score, created_at FROM ideas "
            "WHERE run_id = ? ORDER BY id DESC",
            (run_id,),
        ).fetchall()
        tok = c.execute(
            "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COUNT(*) "
            "FROM turns WHERE run_id = ?",
            (run_id,),
        ).fetchone()

    def _pj(raw):
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}

    current = None
    if last_tool:
        tin = _pj(last_tool["tool_input"])
        current = {
            "tool_name": last_tool["tool_name"],
            "input_summary": _format_tool_input(last_tool["tool_name"], tin),
            "turn": last_tool["turn_number"],
            "at": last_tool["created_at"],
        }

    recent = []
    for r in recent_rows:
        tin = _pj(r["tool_input"])
        recent.append({
            "tool_name": r["tool_name"],
            "input_summary": _format_tool_input(r["tool_name"], tin),
            "turn": r["turn_number"],
            "at": r["created_at"],
        })

    saved = [
        {
            "id": r["id"],
            "title": r["title"],
            "score": r["score"],
            "at": r["created_at"],
        }
        for r in idea_rows
    ]

    return {
        "current": current,
        "last_text": (last_text["text"] or "").strip()[:280] if last_text else "",
        "recent": recent,
        "saved": saved,
        "input_tokens": int(tok[0] or 0),
        "output_tokens": int(tok[1] or 0),
        "turn_count": int(tok[2] or 0),
    }


def _render_running_banner(in_flight: dict[str, Any]) -> None:
    prog = in_flight_progress(in_flight["id"])
    elapsed = _format_elapsed(in_flight.get("started_at"))
    st.markdown(
        f"""
        <div class='runner running'>
          <div class='runner-left'>
            <span class='runner-pulse'></span>
            <div class='runner-text'>
              <div class='runner-title'>Run #{in_flight['id']} in progress</div>
              <div class='runner-meta'>
                {prog['turns']} turn{'s' if prog['turns'] != 1 else ''}
                · {prog['ideas']} idea{'s' if prog['ideas'] != 1 else ''} saved
                · {elapsed} elapsed
              </div>
            </div>
          </div>
          <a class='runner-cta secondary' href='Run_Detail?run_id={in_flight['id']}' target='_self'>Open run →</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _format_clock(iso_str: str | None) -> str:
    """HH:MM:SS in local time, or '—'."""
    if not iso_str:
        return "—"
    try:
        s = datetime.fromisoformat(iso_str)
    except ValueError:
        return "—"
    return s.astimezone().strftime("%H:%M:%S")


_TOOL_ACCENT = {
    "search_signals": "demand",
    "search_reddit":  "novelty",
    "get_trend":      "demand",
    "web_search":     "primary",
    "fetch_url":      "monetization",
    "save_idea":      "score_hi",
}


@st.fragment(run_every="1.5s")
def _live_monitor_fragment(run_id: int) -> None:
    """Self-refreshing live monitor (re-runs every 1.5s, only this fragment)."""
    act = live_activity(run_id)
    cur = act["current"]

    cur_html = ""
    if cur:
        icon = _TOOL_ICONS.get(cur["tool_name"], "🔧")
        cur_html = (
            f"<div class='live-card'>"
            f"  <div class='live-card-head'>"
            f"    <span class='live-pulse-dot'></span>"
            f"    <span class='live-card-label'>Currently inspecting</span>"
            f"    <span class='live-card-turn'>turn {cur['turn']}</span>"
            f"  </div>"
            f"  <div class='live-current-row'>"
            f"    <span class='live-current-icon'>{icon}</span>"
            f"    <span class='live-current-tool'>{cur['tool_name']}</span>"
            f"    <span class='live-current-detail'>{html.escape(cur['input_summary'])}</span>"
            f"  </div>"
            f"</div>"
        )
    else:
        cur_html = (
            "<div class='live-card warming'>"
            "  <div class='live-card-head'>"
            "    <span class='live-pulse-dot'></span>"
            "    <span class='live-card-label'>Warming up — agent is booting</span>"
            "  </div>"
            "  <div class='live-warming-shimmer'></div>"
            "</div>"
        )
    st.markdown(cur_html, unsafe_allow_html=True)

    left, right = st.columns([3, 2], gap="medium")

    with left:
        st.markdown(
            "<div class='section-head'>"
            "<div class='section-title'>Live activity log</div>"
            f"<div class='section-sub'>"
            f"{act['turn_count']} turn{'s' if act['turn_count'] != 1 else ''} · "
            f"{_fmt_compact(act['input_tokens'] + act['output_tokens'])} tokens"
            f"</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        if not act["recent"]:
            st.markdown(
                "<div class='log-feed'>"
                "<div class='log-skeleton'>"
                "<div class='log-skeleton-row'></div>"
                "<div class='log-skeleton-row'></div>"
                "<div class='log-skeleton-row'></div>"
                "</div>"
                "<div class='log-empty-hint'>Waiting for first tool call…</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            rows = ["<div class='log-feed'>"]
            for idx, r in enumerate(act["recent"]):
                clock = _format_clock(r["at"])
                ago = _ago(r["at"])
                icon = _TOOL_ICONS.get(r["tool_name"], "🔧")
                accent = _TOOL_ACCENT.get(r["tool_name"], "primary")
                latest_cls = " is-latest" if idx == 0 else ""
                rows.append(
                    f"<div class='log-row{latest_cls}' data-accent='{accent}'>"
                    f"  <span class='log-bar'></span>"
                    f"  <span class='log-time'>{clock}</span>"
                    f"  <span class='log-ago'>{ago}</span>"
                    f"  <span class='log-icon'>{icon}</span>"
                    f"  <span class='log-tool'>{r['tool_name']}</span>"
                    f"  <span class='log-detail'>{html.escape(r['input_summary'])}</span>"
                    f"</div>"
                )
            rows.append("</div>")
            st.markdown("".join(rows), unsafe_allow_html=True)

        if act["last_text"]:
            st.markdown(
                f"<div class='live-thought'>"
                f"<span class='live-thought-label'>Latest reasoning</span>"
                f"<div class='live-thought-text'>{html.escape(act['last_text'])}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    with right:
        st.markdown(
            "<div class='section-head'>"
            "<div class='section-title'>Saved this run</div>"
            f"<div class='section-sub'>{len(act['saved'])} idea{'s' if len(act['saved']) != 1 else ''}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        if not act["saved"]:
            st.markdown(
                "<div class='empty-state small'>"
                "<div class='empty-title'>No ideas saved yet</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            rows = ["<div class='live-saved'>"]
            for idea in act["saved"]:
                color = _styles.score_color(idea["score"])
                title_safe = html.escape(idea["title"] or "(untitled)")
                score_text = idea["score"] if idea["score"] is not None else "—"
                rows.append(
                    f"<a class='live-saved-row' href='Idea_Detail?id={idea['id']}' target='_self'>"
                    f"  <span class='live-saved-title'>{title_safe}</span>"
                    f"  <span class='live-saved-score' style='background:{color};'>{score_text}</span>"
                    f"</a>"
                )
            rows.append("</div>")
            st.markdown("".join(rows), unsafe_allow_html=True)


@st.fragment(run_every="1s")
def _booting_skeleton_fragment() -> None:
    """Shown immediately after Run-now click, before subprocess inserts the
    runs row. Auto-promotes to the real monitor once the row appears."""
    in_flight = in_flight_run()
    if in_flight:
        # Subprocess is alive; clear the pending flag and let the page rerun
        # into the real monitor.
        st.session_state.pop("pending_run_started", None)
        st.rerun()
        return

    started_at = st.session_state.get("pending_run_started")
    if started_at is None:
        return  # Nothing to render

    secs = max(0, int(time.time() - started_at))
    # Give up after ~60s — likely the subprocess crashed silently
    if secs > 60:
        st.session_state.pop("pending_run_started", None)
        st.error(
            "The run didn't start within 60s. Check your AWS / Bedrock "
            "credentials and the latest log file in `output/ideation/logs/`."
        )
        return

    st.markdown(
        f"""
        <div class='booting'>
          <div class='booting-head'>
            <span class='booting-spinner'></span>
            <div class='booting-text'>
              <div class='booting-title'>Starting agent…</div>
              <div class='booting-meta'>Spawning subprocess · {secs}s elapsed</div>
            </div>
          </div>
          <div class='booting-steps'>
            <div class='booting-step done'>✓ Config saved</div>
            <div class='booting-step done'>✓ Subprocess launched</div>
            <div class='booting-step active'>↻ Loading model & tools</div>
            <div class='booting-step'>○ Issuing first tool call</div>
          </div>
          <div class='log-feed'>
            <div class='log-skeleton'>
              <div class='log-skeleton-row'></div>
              <div class='log-skeleton-row'></div>
              <div class='log-skeleton-row'></div>
              <div class='log-skeleton-row'></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_inflight_section() -> None:
    """Banner + live monitor for an in-flight run (or pending-skeleton if a
    run was just spawned but the subprocess hasn't inserted its row yet).
    Renders nothing if no run is active.

    This is the public entrypoint Home / Runs use — they no longer embed the
    full launcher form.
    """
    mark_stale_runs()
    in_flight = in_flight_run()

    if in_flight:
        st.session_state.pop("pending_run_started", None)
        _render_running_banner(in_flight)
        _live_monitor_fragment(in_flight["id"])
        return

    if "pending_run_started" in st.session_state:
        _booting_skeleton_fragment()


def render_new_run_button(
    *,
    label: str = "🚀  Launch new ideation run",
    key: str = "open_launch_dialog",
    use_container_width: bool = True,
    hero: bool = True,
) -> None:
    """Prominent CTA that opens the launch dialog. Skips itself when a run
    is already in flight (the in-flight section takes over)."""
    if in_flight_run() or "pending_run_started" in st.session_state:
        return

    cls = "hero-cta-wrap" if hero else "compact-cta-wrap"
    st.markdown(f"<div class='{cls}'>", unsafe_allow_html=True)
    if st.button(
        label,
        key=key,
        type="primary",
        use_container_width=use_container_width,
    ):
        _render_launch_dialog()
    st.markdown("</div>", unsafe_allow_html=True)


@st.dialog("New ideation run", width="large")
def _render_launch_dialog() -> None:
    """The launcher form, wrapped in a modal dialog. Closes itself on
    successful spawn (sets pending_run_started + st.rerun)."""
    _render_launcher_form()


# ─── Legacy: keep render_launcher() as a thin shim so other callers still
# work during the migration. New pages should call render_inflight_section()
# + render_new_run_button() instead.
def render_launcher(*, live_monitor: bool = True) -> None:
    render_inflight_section()
    if not in_flight_run() and "pending_run_started" not in st.session_state:
        render_new_run_button()


def _apply_preset_to_state(preset_name: str) -> None:
    """Push preset values into st.session_state BEFORE widgets render."""
    if preset_name not in PRESETS:
        return
    p = PRESETS[preset_name]
    st.session_state.cfg_focus = p.focus_prompt
    st.session_state.cfg_seeds = ", ".join(p.niche_seeds)
    st.session_state.cfg_avoid = p.avoid
    st.session_state.cfg_target_count = int(p.target_idea_count)
    st.session_state.cfg_min_score = int(p.min_score)
    st.session_state.cfg_feasibility = list(p.feasibility_filter or FEASIBILITY_OPTIONS)
    st.session_state.cfg_audience = p.audience_hint
    st.session_state.cfg_monetization = p.monetization_preference
    st.session_state.cfg_skip_signals = bool(p.skip_signal_collection)
    st.session_state.cfg_disable_trends = bool(p.disable_google_trends)
    # Sync reddit-category discovery sources to the preset's subreddit list
    # (other discovery categories are left alone — discovery scope is an
    #  orthogonal axis from the run-config preset).
    if p.subreddits:
        target = {sub.lower() for sub in p.subreddits}
        for s in DISCOVERY_SOURCES:
            if s.category != "reddit":
                continue
            st.session_state[f"cfg_src_{s.id}"] = (s.payload or "").lower() in target
    # Keep technical fields untouched on preset apply (Opus, max_turns, budget)


def _apply_discovery_preset() -> None:
    """on_change for the discovery preset radio. Flips every cfg_src_<id>
    flag to match the preset bundle. 'Custom' is a no-op."""
    name = st.session_state.get("cfg_discovery_preset", "Quick")
    if name == "Custom":
        return
    target = set(sources_for_preset(name))
    for s in DISCOVERY_SOURCES:
        st.session_state[f"cfg_src_{s.id}"] = s.id in target


def _toggle_category(category_id: str) -> None:
    """Flip every source in a category. If all are on, turn all off; else
    turn all on. Wired to the per-category 'Select all / none' button."""
    sources = sources_in_category(category_id)
    all_on = all(st.session_state.get(f"cfg_src_{s.id}", False) for s in sources)
    target = not all_on
    for s in sources:
        st.session_state[f"cfg_src_{s.id}"] = target


def _selected_discovery_ids() -> list[str]:
    return [s.id for s in DISCOVERY_SOURCES
            if st.session_state.get(f"cfg_src_{s.id}", False)]


def _ensure_state_defaults() -> None:
    """Initialize cfg_* keys once so widgets render with sensible values."""
    defaults = {
        "cfg_focus": "",
        "cfg_seeds": "",
        "cfg_avoid": "",
        "cfg_target_count": 4,
        "cfg_min_score": 55,
        "cfg_feasibility": list(FEASIBILITY_OPTIONS),
        "cfg_audience": "",
        "cfg_monetization": "any",
        "cfg_skip_signals": False,
        "cfg_disable_trends": False,
        "cfg_model_label": "Opus 4.7",
        "cfg_max_turns": 22,
        "cfg_search_budget": 35,
        "cfg_preset": "(custom)",
        "cfg_discovery_preset": "Quick",
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)
    # Per-source defaults (Quick preset = only natively-integrated sources)
    default_ids = set(default_discovery_selection())
    for s in DISCOVERY_SOURCES:
        st.session_state.setdefault(f"cfg_src_{s.id}", s.id in default_ids)


def _collect_config_from_state() -> RunConfig:
    seeds_raw = st.session_state.get("cfg_seeds", "") or ""
    seeds = [s.strip() for s in seeds_raw.split(",") if s.strip()]
    discovery_ids = _selected_discovery_ids()
    subreddits = subreddits_from_selection(discovery_ids)
    return RunConfig(
        focus_prompt=st.session_state.get("cfg_focus", ""),
        niche_seeds=seeds,
        subreddits=subreddits,
        avoid=st.session_state.get("cfg_avoid", ""),
        target_idea_count=int(st.session_state.get("cfg_target_count", 4)),
        min_score=int(st.session_state.get("cfg_min_score", 55)),
        feasibility_filter=list(st.session_state.get("cfg_feasibility", FEASIBILITY_OPTIONS)),
        audience_hint=st.session_state.get("cfg_audience", ""),
        monetization_preference=st.session_state.get("cfg_monetization", "any"),
        skip_signal_collection=bool(st.session_state.get("cfg_skip_signals", False)),
        disable_google_trends=bool(st.session_state.get("cfg_disable_trends", False)),
        discovery_sources=discovery_ids,
        max_turns=int(st.session_state.get("cfg_max_turns", 22)),
        search_budget=int(st.session_state.get("cfg_search_budget", 35)),
        model=MODELS.get(st.session_state.get("cfg_model_label", "Opus 4.7"), MODELS["Opus 4.7"]),
    )


_BADGE_DISPLAY = {
    "api":    "✅",
    "web":    "🌐",
    "search": "🔍",
}
_BADGE_TOOLTIP = {
    "api":    "Native API integration",
    "web":    "Public page · WebFetch",
    "search": "Search-only fallback",
}

# Short, plain-English summary of each preset (1 line, shown under selectbox).
# Keeps the dialog's "simple mode" informative without needing to open Advanced.
PRESET_DESCRIPTIONS = {
    "(custom)":
        "Start from your own knobs · pick a preset to load a starting configuration",
    "Daily-use consumer (default)":
        "Daily-habit iPhone apps · widgets + freemium subscription · ~4 ideas",
    "Productivity & focus":
        "Todo / calendar / time-blocking / focus · Lock Screen + Watch · ~4 ideas",
    "Wellness & HealthKit":
        "HealthKit / Apple Watch wellness (no medical) · freemium · ~4 ideas",
    "Photo & video":
        "Editors, filter packs, organizers, batch tools · freemium · ~3 ideas",
    "Education & learning":
        "Language, flashcards, exam prep, kids learning · freemium · ~4 ideas",
    "Finance & money":
        "Budget / expenses / investing, privacy-first · subscription · ~3 ideas",
    "Travel & local":
        "Itineraries, packing, offline maps, phrasebook · one-time · ~3 ideas",
    "Food & cooking":
        "Recipes, meal planning, grocery, kitchen timers · freemium · ~3 ideas",
    "Apple Pencil & iPad-native":
        "Creative iPad tools leveraging Pencil + large screen · one-time · ~3 ideas",
    "Camera · AR · on-device AI":
        "Camera-first iPhone tools using ARKit / Vision / Core ML · freemium · ~3 ideas",
    "Widgets · Watch · Live Activities":
        "Apps whose value is the widget / complication / Live Activity · freemium · ~4 ideas",
    "Indie dev tools (iOS-native)":
        "Native iOS dev / power-user tools · premium one-time · ~3 ideas",
}


def _on_preset_change() -> None:
    """Auto-apply preset values when the user picks one — saves a click vs.
    the old 'Pick + Apply' pattern."""
    name = st.session_state.get("cfg_preset", "(custom)")
    if name and name != "(custom)":
        _apply_preset_to_state(name)


def _render_discovery_sources_block() -> None:
    """Top-level expander that lets the user choose which sources the
    agent will scan this run. Lives above 'Direction & constraints'
    because it controls the raw signal feed (highest leverage knob)."""
    selected = _selected_discovery_ids()

    with st.expander(
        f"🛰  Discovery sources — what to scan  ·  "
        f"{len(selected)}/{len(DISCOVERY_SOURCES)} selected",
        expanded=False,
    ):
        # Preset row
        st.radio(
            "Preset",
            DISCOVERY_PRESET_NAMES,
            key="cfg_discovery_preset",
            on_change=_apply_discovery_preset,
            horizontal=True,
            help=(
                "Quick = native APIs only · Medium = + curated web-fetch · "
                "Deep = everything · Custom = leave selection alone."
            ),
        )
        preset = st.session_state.get("cfg_discovery_preset", "Quick")
        st.caption(DISCOVERY_PRESET_DESCRIPTIONS.get(preset, ""))

        st.markdown(
            "<div class='discovery-legend'>"
            "<span>✅ native API</span>"
            "<span>🌐 web-fetch</span>"
            "<span>🔍 search-only</span>"
            "</div>",
            unsafe_allow_html=True,
        )

        # Per-category sub-expanders
        for category_id, category_label in DISCOVERY_CATEGORIES:
            sources = sources_in_category(category_id)
            if not sources:
                continue
            cat_selected = sum(
                1 for s in sources
                if st.session_state.get(f"cfg_src_{s.id}", False)
            )
            with st.expander(
                f"{category_label}  ·  {cat_selected}/{len(sources)}",
                expanded=False,
            ):
                btn_label = (
                    "Deselect all" if cat_selected == len(sources)
                    else ("Select all" if cat_selected == 0 else "Toggle all")
                )
                st.button(
                    btn_label,
                    key=f"cfg_src_toggle_{category_id}",
                    on_click=_toggle_category,
                    args=(category_id,),
                )
                cols = st.columns(2)
                for i, src in enumerate(sources):
                    with cols[i % 2]:
                        badge = _BADGE_DISPLAY.get(src.badge, "")
                        label = f"{badge}  {src.label}" if badge else src.label
                        st.checkbox(
                            label,
                            key=f"cfg_src_{src.id}",
                            help=_BADGE_TOOLTIP.get(src.badge, ""),
                        )


def _render_launcher_form() -> None:
    """Body of the launch dialog. Renders preset/focus + advanced options +
    the prominent Run button. On click, spawns the subprocess and closes
    the dialog (st.rerun) — page detects pending_run_started and shows the
    booting skeleton, which auto-upgrades to the live monitor."""
    _ensure_state_defaults()

    st.markdown(
        "<div class='dialog-intro'>"
        "Pick a preset (or stay custom), optionally describe your angle, then launch. "
        "The agent scans signals, scores ideas, and saves the best — about 5–10 min."
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Step 1: Preset (auto-applies on change) ─────────────────────────
    st.markdown("<div class='form-step-label'>1 · Choose a starting point</div>",
                unsafe_allow_html=True)
    preset_options = ["(custom)"] + PRESET_NAMES
    selected_preset = st.selectbox(
        "Preset",
        preset_options,
        key="cfg_preset",
        on_change=_on_preset_change,
        label_visibility="collapsed",
        help="Loads a starting configuration. You can still tweak anything in Advanced.",
    )
    st.markdown(
        f"<div class='preset-desc'>{PRESET_DESCRIPTIONS.get(selected_preset, '')}</div>",
        unsafe_allow_html=True,
    )

    # ── Step 2: Focus textarea (optional but high leverage) ─────────────
    st.markdown(
        "<div class='form-step-label'>2 · Set a focus  "
        "<span class='form-step-hint'>optional · sharpens direction</span></div>",
        unsafe_allow_html=True,
    )
    st.text_area(
        "Focus",
        key="cfg_focus",
        placeholder=(
            "e.g. 'B2B prosumers willing to pay $20+/mo, no consumer apps' "
            "or 'apps for parents of toddlers during the 5–7pm chaos hour'."
        ),
        height=88,
        label_visibility="collapsed",
    )

    # ── Step 3: Advanced toggle (everything else lives behind this) ─────
    st.toggle(
        "Show advanced settings",
        value=False,
        key="show_advanced",
        help="Discovery sources, output shape, data sources, model & budget.",
    )

    if st.session_state.get("show_advanced"):
        st.markdown(
            "<div class='advanced-block-intro'>"
            "Defaults work for most runs — these knobs override them."
            "</div>",
            unsafe_allow_html=True,
        )

        # Discovery sources (highest-leverage: decides raw signal feed)
        _render_discovery_sources_block()

        with st.expander(
            "🎯  Direction & constraints  ·  "
            "niche seed terms + topics to avoid",
            expanded=False,
        ):
            st.text_input(
                "Niche seeds (comma-separated)",
                key="cfg_seeds",
                placeholder="habit tracker, ai journal, focus timer",
                help=(
                    "Seed terms for App Store keyword search and Google "
                    "Trends rising-query collection. Leave blank for defaults."
                ),
            )
            st.text_area(
                "Avoid topics / niches / monetization patterns",
                key="cfg_avoid",
                placeholder="fitness, meditation, anything FDA-regulated",
                height=60,
                help="Becomes a hard constraint the agent must respect.",
            )

        with st.expander(
            "📦  Output shape  ·  "
            "how many ideas, score threshold, audience, monetization",
            expanded=False,
        ):
            c1, c2 = st.columns(2)
            with c1:
                st.slider(
                    "Target idea count", 1, 10,
                    key="cfg_target_count",
                    help="Agent aims for N ± 1 saved ideas.",
                )
            with c2:
                st.slider(
                    "Min score threshold (0–100)", 40, 80,
                    key="cfg_min_score",
                    help="Ideas below this score aren't saved (unless evidence is exceptional).",
                )
            st.multiselect(
                "Allowed build effort",
                options=FEASIBILITY_OPTIONS,
                key="cfg_feasibility",
                format_func=_styles.humanize_feasibility,
                help=(
                    "Restricts how much build effort the agent allows. "
                    "Solo·1wk = a weekend hack · Team only = needs a small team."
                ),
            )
            st.text_input(
                "Audience hint (optional)",
                key="cfg_audience",
                placeholder="parents of toddlers, ADHD adults, indie iOS devs…",
                help="Will appear as a 'target_users always includes…' constraint.",
            )
            st.radio(
                "Monetization preference",
                options=MONETIZATION_OPTIONS,
                key="cfg_monetization",
                horizontal=True,
                help="Biases the agent toward this monetization where it makes sense.",
            )

        with st.expander(
            "💾  Data sources  ·  fresh signals vs. cached DB",
            expanded=False,
        ):
            st.checkbox(
                "Skip signal collection (use existing DB only)",
                key="cfg_skip_signals",
                help="Faster — skips fresh App Store / Reddit / Trends scraping. Useful for repeat runs.",
            )
            st.checkbox(
                "Disable Google Trends (use when rate-limited)",
                key="cfg_disable_trends",
                help="Sets DISABLE_GOOGLE_TRENDS=1 for the subprocess.",
            )

        with st.expander(
            "⚙️  Technical  ·  model, max turns, web-search budget",
            expanded=False,
        ):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.radio(
                    "Model",
                    options=list(MODELS.keys()),
                    key="cfg_model_label",
                    help="Opus = deeper reasoning, ~5x cost. Sonnet = fast & cheap.",
                )
            with c2:
                st.select_slider(
                    "Max turns", options=[10, 16, 22, 28, 36],
                    key="cfg_max_turns",
                    help="Hard cap on agent tool-use turns. 22 ≈ ~5–7 min on Opus.",
                )
            with c3:
                st.select_slider(
                    "Web-search budget", options=[0, 5, 15, 25, 35, 50],
                    key="cfg_search_budget",
                    help="Max DuckDuckGo searches this run can spend.",
                )

    # ── Cap status (per-user daily quota) ───────────────────────────────
    from factory.ui import auth, cap
    username = auth.current_user() or ""
    cap_status = cap.check(username) if username else None
    if cap_status:
        cls = "cap-pill" + ("" if cap_status.allowed else " is-blocked")
        msg = cap.status_blurb(cap_status)
        if not cap_status.allowed:
            msg = f"⛔  {cap_status.reason}  ·  {msg}"
        st.markdown(
            f"<div class='{cls}'>{msg}</div>",
            unsafe_allow_html=True,
        )

    # ── Run button ──────────────────────────────────────────────────────
    st.markdown("<div class='dialog-run-cta'>", unsafe_allow_html=True)
    btn_disabled = bool(cap_status and not cap_status.allowed)
    if st.button(
        "🚀  Launch run",
        type="primary",
        key="runner_btn",
        use_container_width=True,
        disabled=btn_disabled,
    ):
        cfg = _collect_config_from_state()
        log_path = spawn_run(cfg, username=username or None)
        # Mark "pending" — the page-level booting skeleton renders immediately,
        # and auto-upgrades to the live monitor once the subprocess inserts
        # its runs row (no fixed sleep — the fragment polls every 1s).
        st.session_state["pending_run_started"] = time.time()
        st.session_state["pending_run_log"] = log_path.name
        # Drop cached read results so the new run shows up on home/runs
        # without waiting for the @st.cache_data TTL to expire.
        from factory.ui import data as _data
        _data.invalidate_caches()
        st.toast(f"Run launched · log: {log_path.name}", icon="🚀")
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
