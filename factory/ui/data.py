"""Read-only SQLite helpers for the Streamlit UI.

The UI never mutates; it only reads from the same DB the agents write to.
Each helper opens and closes its own connection for simplicity — SQLite is
cheap to re-open and Streamlit reruns scripts on interaction.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any

from factory.ideation import store


@contextmanager
def _conn():  # type: ignore[no-untyped-def]
    """Open a connection routed through the central store (handles SQLite vs
    Turso libSQL embedded-replica transparently). Wrapped as a contextmanager
    so `with _conn() as c:` works on both backends — libsql's Connection
    doesn't natively support the `with` protocol."""
    conn = store.open_connection()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _rows(cur) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


def _duration_seconds(started_at: str | None, finished_at: str | None) -> float | None:
    if not started_at or not finished_at:
        return None
    try:
        s = datetime.fromisoformat(started_at)
        f = datetime.fromisoformat(finished_at)
        return (f - s).total_seconds()
    except (ValueError, TypeError):
        return None


# ───── Runs ──────────────────────────────────────────────────────────────

def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = _rows(c.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ))
    for r in rows:
        r["duration_seconds"] = _duration_seconds(r.get("started_at"), r.get("finished_at"))
    return rows


def get_run(run_id: int) -> dict[str, Any] | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    r = dict(row)
    r["duration_seconds"] = _duration_seconds(r.get("started_at"), r.get("finished_at"))
    return r


def latest_run() -> dict[str, Any] | None:
    runs = list_runs(limit=1)
    return runs[0] if runs else None


# ───── Turns and blocks ──────────────────────────────────────────────────

def get_turns(run_id: int) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = _rows(c.execute(
            "SELECT * FROM turns WHERE run_id = ? ORDER BY turn_number ASC",
            (run_id,),
        ))
    return rows


def get_blocks(turn_id: int) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = _rows(c.execute(
            "SELECT * FROM turn_blocks WHERE turn_id = ? ORDER BY seq ASC",
            (turn_id,),
        ))
    for b in rows:
        if b.get("tool_input"):
            try:
                b["tool_input_parsed"] = json.loads(b["tool_input"])
            except json.JSONDecodeError:
                b["tool_input_parsed"] = None
    return rows


def get_queries_for_run(run_id: int) -> list[dict[str, Any]]:
    with _conn() as c:
        return store.tool_call_queries(c, run_id)


# ───── Ideas ─────────────────────────────────────────────────────────────

def top_pending_ideas(limit: int = 5) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = _rows(c.execute(
            "SELECT id, title, score, ios_feasibility, stage, created_at"
            " FROM ideas WHERE stage = 'ideated'"
            " ORDER BY score IS NULL, score DESC, id DESC LIMIT ?",
            (limit,),
        ))
    return rows


def get_idea(idea_id: int) -> dict[str, Any] | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
    if not row:
        return None
    return _hydrate_idea(dict(row))


def list_ideas_with_filters(
    *,
    min_score: int = 0,
    max_score: int = 100,
    feasibility: list[str] | None = None,
    stages: list[str] | None = None,
    created_after: str | None = None,
    text: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    clauses = ["(score >= ? OR score IS NULL)", "(score <= ? OR score IS NULL)"]
    params: list[Any] = [min_score, max_score]
    if feasibility:
        placeholders = ",".join("?" for _ in feasibility)
        clauses.append(f"ios_feasibility IN ({placeholders})")
        params.extend(feasibility)
    if stages:
        placeholders = ",".join("?" for _ in stages)
        clauses.append(f"stage IN ({placeholders})")
        params.extend(stages)
    if created_after:
        clauses.append("created_at >= ?")
        params.append(created_after)
    if text:
        like = f"%{text}%"
        clauses.append("(title LIKE ? OR concept LIKE ?)")
        params.extend([like, like])
    where = " AND ".join(clauses)
    params.append(limit)
    with _conn() as c:
        rows = _rows(c.execute(
            f"SELECT * FROM ideas WHERE {where} ORDER BY score IS NULL, score DESC, id DESC LIMIT ?",
            tuple(params),  # libsql requires tuple; sqlite3 accepts both
        ))
    return [_hydrate_idea(r) for r in rows]


def _hydrate_idea(idea: dict[str, Any]) -> dict[str, Any]:
    """Parse JSON columns into Python values for easier UI rendering."""
    for col in ("evidence_urls", "evidence_signal_ids", "score_breakdown",
                "pros", "cons", "risks", "differentiators", "key_competitors"):
        raw = idea.get(col)
        if raw:
            try:
                idea[col] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                idea[col] = None
        else:
            idea[col] = None
    return idea


def signal_source_counts() -> list[dict[str, Any]]:
    """How many signals we have per source. Drives the filter pills."""
    with _conn() as c:
        rows = _rows(c.execute(
            "SELECT source, COUNT(*) as count FROM signals GROUP BY source ORDER BY 2 DESC"
        ))
    return rows


def list_signals_with_filters(
    *,
    sources: list[str] | None = None,
    text: str | None = None,
    after: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if sources:
        placeholders = ",".join("?" for _ in sources)
        clauses.append(f"source IN ({placeholders})")
        params.extend(sources)
    if text:
        like = f"%{text}%"
        clauses.append("(title LIKE ? OR content LIKE ?)")
        params.extend([like, like])
    if after:
        clauses.append("collected_at >= ?")
        params.append(after)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.extend([limit, offset])
    with _conn() as c:
        rows = _rows(c.execute(
            f"SELECT * FROM signals {where}"
            f" ORDER BY collected_at DESC LIMIT ? OFFSET ?",
            tuple(params),
        ))
    for s in rows:
        if s.get("metadata"):
            try:
                s["metadata"] = json.loads(s["metadata"])
            except json.JSONDecodeError:
                pass
    return rows


def count_signals_with_filters(
    *,
    sources: list[str] | None = None,
    text: str | None = None,
    after: str | None = None,
) -> int:
    clauses = []
    params: list[Any] = []
    if sources:
        placeholders = ",".join("?" for _ in sources)
        clauses.append(f"source IN ({placeholders})")
        params.extend(sources)
    if text:
        like = f"%{text}%"
        clauses.append("(title LIKE ? OR content LIKE ?)")
        params.extend([like, like])
    if after:
        clauses.append("collected_at >= ?")
        params.append(after)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as c:
        row = c.execute(f"SELECT COUNT(*) FROM signals {where}", tuple(params)).fetchone()
    return int(row[0])


def get_parent_idea(idea_id: int) -> dict[str, Any] | None:
    with _conn() as c:
        parent = store.get_parent_idea(c, idea_id)
    return _hydrate_idea(parent) if parent else None


def parent_titles_map() -> dict[int, str]:
    with _conn() as c:
        return store.parent_titles_map(c)


def get_signals_by_ids(signal_ids: list[int]) -> list[dict[str, Any]]:
    if not signal_ids:
        return []
    placeholders = ",".join("?" for _ in signal_ids)
    with _conn() as c:
        rows = _rows(c.execute(
            f"SELECT * FROM signals WHERE id IN ({placeholders})",
            signal_ids,
        ))
    # Preserve caller order
    by_id = {r["id"]: r for r in rows}
    ordered = [by_id[i] for i in signal_ids if i in by_id]
    for s in ordered:
        if s.get("metadata"):
            try:
                s["metadata"] = json.loads(s["metadata"])
            except json.JSONDecodeError:
                pass
    return ordered


def ideas_for_run(run_id: int) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = _rows(c.execute(
            "SELECT * FROM ideas WHERE run_id = ? ORDER BY score IS NULL, score DESC, id ASC",
            (run_id,),
        ))
    return [_hydrate_idea(r) for r in rows]


def research_turns_for_idea(idea: dict[str, Any], lookback: int = 4) -> list[dict[str, Any]]:
    """Best-effort: return the N turns immediately preceding the save_idea call
    for this idea. Heuristic but matches how Claude actually works — explore,
    validate, then save.
    """
    run_id = idea.get("run_id")
    if not run_id:
        return []
    with _conn() as c:
        # Find the turn that called save_idea for this idea's title
        title = idea.get("title") or ""
        like = f'%"title": "{title}"%'
        save_row = c.execute(
            """
            SELECT t.turn_number FROM turn_blocks tb
            JOIN turns t ON tb.turn_id = t.id
            WHERE t.run_id = ? AND tb.block_type='tool_use' AND tb.tool_name='save_idea'
              AND tb.tool_input LIKE ?
            ORDER BY t.turn_number ASC LIMIT 1
            """,
            (run_id, like),
        ).fetchone()
        if not save_row:
            # Fall back to all turns
            start = 1
            end = 9999
        else:
            end = int(save_row["turn_number"])
            start = max(1, end - lookback)
        turns = _rows(c.execute(
            "SELECT * FROM turns WHERE run_id = ? AND turn_number BETWEEN ? AND ?"
            " ORDER BY turn_number ASC",
            (run_id, start, end),
        ))
    return turns


# ───── Dashboard metrics ─────────────────────────────────────────────────

def db_counts() -> dict[str, int]:
    with _conn() as c:
        signals = c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        ideas = c.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]
        runs = c.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    return {"signals": signals, "ideas": ideas, "runs": runs}


def daily_ideation_metrics(days: int = 14) -> list[dict[str, Any]]:
    """One row per day for the last `days` days: idea_count, token_in, token_out, run_count.

    If the most recent activity is older than `days`, the window auto-extends so
    the sparkline always shows real data when any exists (capped at 60 days).
    """
    today = date.today()
    last = last_activity_date()
    if last:
        gap = (today - last).days
        if gap >= days:
            days = min(60, gap + 7)
    out: list[dict[str, Any]] = []
    with _conn() as c:
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            date_str = d.isoformat()
            like = f"{date_str}%"
            ideas_count = c.execute(
                "SELECT COUNT(*) FROM ideas WHERE created_at LIKE ?", (like,)
            ).fetchone()[0]
            runs_agg = c.execute(
                "SELECT COUNT(*), COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0)"
                " FROM runs WHERE started_at LIKE ?",
                (like,),
            ).fetchone()
            out.append({
                "date": date_str,
                "ideas": ideas_count,
                "runs": runs_agg[0],
                "input_tokens": runs_agg[1],
                "output_tokens": runs_agg[2],
            })
    return out


def last_activity_date() -> date | None:
    """Most recent run start date — drives the auto-extending sparkline window."""
    with _conn() as c:
        row = c.execute(
            "SELECT MAX(started_at) FROM runs"
        ).fetchone()
    if not row or not row[0]:
        return None
    try:
        return datetime.fromisoformat(row[0]).date()
    except (ValueError, TypeError):
        return None


# ───── Idea Lab / Chat ───────────────────────────────────────────────────

def list_chats_for_idea(idea_id: int) -> list[dict[str, Any]]:
    with _conn() as c:
        return store.list_chats_for_idea(c, idea_id)


def get_chat(chat_id: int) -> dict[str, Any] | None:
    with _conn() as c:
        return store.get_chat(c, chat_id)


def load_chat_messages(chat_id: int) -> list[dict[str, Any]]:
    with _conn() as c:
        return store.load_chat_messages(c, chat_id)


def get_variants(idea_id: int) -> list[dict[str, Any]]:
    with _conn() as c:
        _, variants = store.get_idea_with_variants(c, idea_id)
    return [_hydrate_idea(v) for v in variants]


# ───── Dashboard metrics ─────────────────────────────────────────────────

def tokens_today() -> dict[str, int]:
    today_str = date.today().isoformat()
    like = f"{today_str}%"
    with _conn() as c:
        row = c.execute(
            "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0)"
            " FROM runs WHERE started_at LIKE ?",
            (like,),
        ).fetchone()
    return {"input": int(row[0] or 0), "output": int(row[1] or 0)}
