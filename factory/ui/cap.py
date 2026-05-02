"""Per-user daily Bedrock cost cap.

Soft limits to keep AWS bills predictable when 4-5 friends share a deploy.
Defaults are intentionally generous (we trust users) but firm enough to
prevent a single bad actor from racking up $$$.

Caps are evaluated against the `runs` table — no separate ledger needed.
We tag each run with the user who launched it via the `agent` column
(repurposed: was hardcoded "ideation"; now "ideation:<username>").
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from factory.ideation import store

# ── Default caps (override via env vars) ────────────────────────────────
DAILY_RUN_CAP = int(os.environ.get("CAP_DAILY_RUNS", "20"))
DAILY_TOKEN_CAP = int(os.environ.get("CAP_DAILY_TOKENS", "1000000"))
MAX_CONCURRENT_PER_USER = int(os.environ.get("CAP_CONCURRENT_PER_USER", "1"))

AGENT_PREFIX = "ideation"  # was the only value; now we suffix ":<username>"


def agent_tag(username: str | None) -> str:
    """Tag for the `agent` column when launching a run. The launcher writes
    this; the cap reader splits on ':' to extract the username."""
    if not username:
        return AGENT_PREFIX
    safe = "".join(c for c in username if c.isalnum() or c in "_-")
    return f"{AGENT_PREFIX}:{safe}" if safe else AGENT_PREFIX


def _username_from_agent(agent: str | None) -> str | None:
    if not agent or ":" not in agent:
        return None
    return agent.split(":", 1)[1] or None


class CapStatus(NamedTuple):
    allowed: bool
    reason: str  # empty when allowed
    runs_today: int
    tokens_today: int
    concurrent_now: int


def check(username: str) -> CapStatus:
    """Inspect today's run / token usage for `username` and decide whether
    a new run is allowed. Returns the counts so the UI can surface them."""
    today_start = (
        datetime.now(timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .isoformat()
    )
    tag = agent_tag(username)

    with store.connect() as c:
        runs_today = c.execute(
            "SELECT COUNT(*) FROM runs WHERE agent = ? AND started_at >= ?",
            (tag, today_start),
        ).fetchone()[0]
        tokens_today = c.execute(
            "SELECT COALESCE(SUM(input_tokens + output_tokens), 0) "
            "FROM runs WHERE agent = ? AND started_at >= ?",
            (tag, today_start),
        ).fetchone()[0]
        concurrent_now = c.execute(
            "SELECT COUNT(*) FROM runs WHERE agent = ? AND status = 'running'",
            (tag,),
        ).fetchone()[0]

    runs_today = int(runs_today or 0)
    tokens_today = int(tokens_today or 0)
    concurrent_now = int(concurrent_now or 0)

    if concurrent_now >= MAX_CONCURRENT_PER_USER:
        return CapStatus(
            False,
            f"You already have a run in flight. Wait for it to finish.",
            runs_today, tokens_today, concurrent_now,
        )
    if runs_today >= DAILY_RUN_CAP:
        return CapStatus(
            False,
            f"Daily run cap reached ({runs_today}/{DAILY_RUN_CAP}). "
            "Resets at 00:00 UTC.",
            runs_today, tokens_today, concurrent_now,
        )
    if tokens_today >= DAILY_TOKEN_CAP:
        return CapStatus(
            False,
            f"Daily token cap reached "
            f"({tokens_today:,}/{DAILY_TOKEN_CAP:,}). "
            "Resets at 00:00 UTC.",
            runs_today, tokens_today, concurrent_now,
        )
    return CapStatus(True, "", runs_today, tokens_today, concurrent_now)


def status_blurb(s: CapStatus) -> str:
    """One-line human-readable summary for the UI."""
    return (
        f"Today: {s.runs_today}/{DAILY_RUN_CAP} runs · "
        f"{s.tokens_today:,}/{DAILY_TOKEN_CAP:,} tokens"
    )
