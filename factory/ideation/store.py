"""SQLite store for ideation signals, ideas, and run logs.

In dev (no env vars set) we use plain `sqlite3` against a local file.

In production (Streamlit Cloud) the disk is ephemeral, so we instead use
`libsql_experimental` embedded replicas: a local SQLite file that syncs
bidirectionally with a remote Turso database. Set both `LIBSQL_URL` and
`LIBSQL_AUTH_TOKEN` env vars to activate this mode.

The libsql Connection / Cursor API is sqlite3-compatible — same SQL, same
`?` placeholders, same `row_factory`, same `executescript` — so callers
elsewhere in the codebase don't need to change.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

# Path to the local SQLite file. In Turso mode this is still used — it's the
# embedded-replica file that syncs with the remote DB. Can be overridden via
# APPFACTORY_DATA_DIR (e.g. set to a tmpfs path on cloud hosts).
_DATA_DIR = Path(os.environ.get("APPFACTORY_DATA_DIR", "output/ideation"))
DB_PATH = _DATA_DIR / "ideation.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT,
    content TEXT,
    url TEXT,
    metadata TEXT,
    collected_at TEXT NOT NULL,
    UNIQUE(source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source);
CREATE INDEX IF NOT EXISTS idx_signals_collected_at ON signals(collected_at);

CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    title TEXT NOT NULL,
    concept TEXT NOT NULL,
    target_users TEXT,
    monetization TEXT,
    ios_feasibility TEXT,
    score INTEGER,
    score_breakdown TEXT,
    rationale TEXT,
    evidence_urls TEXT,
    evidence_signal_ids TEXT,
    pros TEXT,
    cons TEXT,
    risks TEXT,
    differentiators TEXT,
    key_competitors TEXT,
    parent_idea_id INTEGER,
    pivot_note TEXT,
    stage TEXT DEFAULT 'ideated',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ideas_run_id ON ideas(run_id);
CREATE INDEX IF NOT EXISTS idx_ideas_score ON ideas(score);
CREATE INDEX IF NOT EXISTS idx_ideas_stage ON ideas(stage);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL DEFAULT 'ideation',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    signals_collected INTEGER DEFAULT 0,
    ideas_generated INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    web_searches INTEGER DEFAULT 0,
    model TEXT,
    status TEXT DEFAULT 'running',
    error TEXT
);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    turn_number INTEGER NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    stop_reason TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_turns_run_id ON turns(run_id);

CREATE TABLE IF NOT EXISTS turn_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    block_type TEXT NOT NULL,
    text TEXT,
    tool_name TEXT,
    tool_input TEXT,
    tool_use_id TEXT,
    tool_result TEXT,
    tool_error INTEGER DEFAULT 0,
    FOREIGN KEY (turn_id) REFERENCES turns(id)
);

CREATE INDEX IF NOT EXISTS idx_turn_blocks_turn_id ON turn_blocks(turn_id);
CREATE INDEX IF NOT EXISTS idx_turn_blocks_type ON turn_blocks(block_type);
CREATE INDEX IF NOT EXISTS idx_turn_blocks_tool ON turn_blocks(tool_name);

CREATE TABLE IF NOT EXISTS idea_chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id INTEGER NOT NULL,
    title TEXT,
    started_at TEXT NOT NULL,
    last_message_at TEXT,
    FOREIGN KEY (idea_id) REFERENCES ideas(id)
);

CREATE INDEX IF NOT EXISTS idx_idea_chats_idea_id ON idea_chats(idea_id);

CREATE TABLE IF NOT EXISTS idea_chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    text TEXT,
    tool_name TEXT,
    tool_input TEXT,
    tool_use_id TEXT,
    tool_result TEXT,
    tool_error INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES idea_chats(id)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_id ON idea_chat_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_seq ON idea_chat_messages(chat_id, seq);
"""

MAX_BLOCK_TEXT = 8192  # truncate stored text/tool_result to ~8KB


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _apply_migrations(conn) -> None:  # type: ignore[no-untyped-def]
    """Idempotent ALTER TABLEs for columns added after the initial schema.
    Uses .fetchall() so it works with both sqlite3.Cursor (iterable) and
    libsql_experimental.Cursor (not iterable — needs explicit fetch)."""
    rows = conn.execute("PRAGMA table_info(ideas)").fetchall()
    cols = {r[1] for r in rows}
    if "parent_idea_id" not in cols:
        conn.execute("ALTER TABLE ideas ADD COLUMN parent_idea_id INTEGER")
    if "pivot_note" not in cols:
        conn.execute("ALTER TABLE ideas ADD COLUMN pivot_note TEXT")


def _is_turso_mode() -> bool:
    return bool(os.environ.get("LIBSQL_URL") and os.environ.get("LIBSQL_AUTH_TOKEN"))


class _DictRow(dict):
    """Row class that supports BOTH dict-style (row['name']) AND sqlite3.Row-
    style (row[0], iter(row) → values) access. Used as row_factory on both
    backends so callers don't need to know which DB they're talking to."""

    __slots__ = ("_values",)

    def __init__(self, cursor, values):  # type: ignore[no-untyped-def]
        super().__init__(
            (col[0], val) for col, val in zip(cursor.description, values)
        )
        self._values = tuple(values)

    def __getitem__(self, key):  # type: ignore[no-untyped-def]
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._values)


def _set_dict_row_factory(conn) -> None:  # type: ignore[no-untyped-def]
    """Best-effort install of the unified row_factory. Silent fallback on
    backends that reject the assignment."""
    try:
        conn.row_factory = _DictRow
    except (AttributeError, TypeError):
        pass


def _open_raw_sqlite(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=15.0)
    _set_dict_row_factory(conn)
    # WAL = concurrent UI reads while a run subprocess writes.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _open_raw_turso(db_path: Path):  # type: ignore[no-untyped-def]
    """Embedded replica: a local SQLite file that bidirectionally syncs to
    the remote Turso DB. The Connection object is sqlite3-API-compatible."""
    import libsql_experimental as libsql
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = libsql.connect(
        str(db_path),
        sync_url=os.environ["LIBSQL_URL"],
        auth_token=os.environ["LIBSQL_AUTH_TOKEN"],
    )
    _set_dict_row_factory(conn)
    # Pull latest from remote on open. Non-fatal if it fails (e.g. cold
    # start with empty remote): we'll still work locally and push on commit.
    try:
        conn.sync()
    except Exception as e:  # noqa: BLE001
        print(f"[store] libsql initial sync failed (non-fatal): {e}",
              file=sys.stderr)
    return conn


def open_connection(db_path: Path = DB_PATH):  # type: ignore[no-untyped-def]
    """Open a fresh DB connection (raw — caller is responsible for close()
    and commit()). Routes to libsql in Turso mode, sqlite3 otherwise.
    Schema + migrations are applied here so callers can assume tables exist."""
    if _is_turso_mode():
        conn = _open_raw_turso(db_path)
    else:
        conn = _open_raw_sqlite(db_path)
    conn.executescript(SCHEMA)
    _apply_migrations(conn)
    return conn


@contextmanager
def connect(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = open_connection(db_path)
    try:
        yield conn
        conn.commit()
        # Push local changes to Turso. Fire-and-forget logging on failure so
        # the user-facing operation succeeds even if the network is flaky.
        if _is_turso_mode():
            try:
                conn.sync()
            except Exception as e:  # noqa: BLE001
                print(f"[store] libsql sync failed (non-fatal): {e}",
                      file=sys.stderr)
    finally:
        conn.close()


def upsert_signal(
    conn: sqlite3.Connection,
    *,
    source: str,
    external_id: str,
    title: str | None,
    content: str | None,
    url: str | None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Insert a signal; update metadata if it already exists. Returns signal id."""
    row = conn.execute(
        "SELECT id FROM signals WHERE source = ? AND external_id = ?",
        (source, external_id),
    ).fetchone()
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    if row:
        conn.execute(
            "UPDATE signals SET title=?, content=?, url=?, metadata=? WHERE id=?",
            (title, content, url, meta_json, row["id"]),
        )
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO signals (source, external_id, title, content, url, metadata, collected_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (source, external_id, title, content, url, meta_json, _now()),
    )
    return int(cur.lastrowid)


def upsert_signals(conn: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for r in rows:
        upsert_signal(conn, **r)
        count += 1
    return count


def start_run(
    conn: sqlite3.Connection,
    *,
    agent: str = "ideation",
    model: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO runs (agent, started_at, model) VALUES (?, ?, ?)",
        (agent, _now(), model),
    )
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    signals_collected: int,
    ideas_generated: int,
    input_tokens: int,
    output_tokens: int,
    web_searches: int,
    status: str = "ok",
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE runs SET finished_at=?, signals_collected=?, ideas_generated=?,"
        " input_tokens=?, output_tokens=?, web_searches=?, status=?, error=? WHERE id=?",
        (
            _now(),
            signals_collected,
            ideas_generated,
            input_tokens,
            output_tokens,
            web_searches,
            status,
            error,
            run_id,
        ),
    )


def save_idea(
    conn: sqlite3.Connection,
    *,
    run_id: int | None,
    title: str,
    concept: str,
    target_users: str | None,
    monetization: str | None,
    ios_feasibility: str | None,
    score: int | None,
    score_breakdown: dict[str, Any] | None,
    rationale: str | None,
    evidence_urls: list[str] | None = None,
    evidence_signal_ids: list[int] | None = None,
    pros: list[str] | None = None,
    cons: list[str] | None = None,
    risks: list[str] | None = None,
    differentiators: list[str] | None = None,
    key_competitors: list[dict[str, Any]] | None = None,
    parent_idea_id: int | None = None,
    pivot_note: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO ideas (run_id, title, concept, target_users, monetization,"
        " ios_feasibility, score, score_breakdown, rationale, evidence_urls,"
        " evidence_signal_ids, pros, cons, risks, differentiators, key_competitors,"
        " parent_idea_id, pivot_note, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            title,
            concept,
            target_users,
            monetization,
            ios_feasibility,
            score,
            json.dumps(score_breakdown or {}, ensure_ascii=False),
            rationale,
            json.dumps(evidence_urls or [], ensure_ascii=False),
            json.dumps(evidence_signal_ids or [], ensure_ascii=False),
            json.dumps(pros or [], ensure_ascii=False),
            json.dumps(cons or [], ensure_ascii=False),
            json.dumps(risks or [], ensure_ascii=False),
            json.dumps(differentiators or [], ensure_ascii=False),
            json.dumps(key_competitors or [], ensure_ascii=False),
            parent_idea_id,
            pivot_note,
            _now(),
        ),
    )
    return int(cur.lastrowid)


_UPDATABLE_IDEA_FIELDS = {
    "target_users", "monetization", "ios_feasibility", "stage",
    "concept", "title", "rationale",
}
_JSON_IDEA_FIELDS = {
    "score_breakdown", "evidence_urls", "evidence_signal_ids",
    "pros", "cons", "risks", "differentiators", "key_competitors",
}


def update_idea_field(
    conn: sqlite3.Connection,
    idea_id: int,
    field: str,
    value: Any,
) -> None:
    """Update a single field on an idea. Accepts scalar or structured values."""
    if field == "score":
        conn.execute("UPDATE ideas SET score = ? WHERE id = ?", (int(value) if value is not None else None, idea_id))
        return
    if field in _JSON_IDEA_FIELDS:
        conn.execute(
            f"UPDATE ideas SET {field} = ? WHERE id = ?",
            (json.dumps(value or ([] if field != 'score_breakdown' else {}), ensure_ascii=False), idea_id),
        )
        return
    if field in _UPDATABLE_IDEA_FIELDS:
        conn.execute(
            f"UPDATE ideas SET {field} = ? WHERE id = ?",
            (str(value) if value is not None else None, idea_id),
        )
        return
    raise ValueError(f"Field '{field}' is not updatable.")


# ───── Chat / Idea Lab ──────────────────────────────────────────────────

def start_chat(conn: sqlite3.Connection, *, idea_id: int, title: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO idea_chats (idea_id, title, started_at, last_message_at) VALUES (?, ?, ?, ?)",
        (idea_id, title, _now(), _now()),
    )
    return int(cur.lastrowid)


def touch_chat(conn: sqlite3.Connection, chat_id: int) -> None:
    conn.execute("UPDATE idea_chats SET last_message_at = ? WHERE id = ?", (_now(), chat_id))


def next_chat_seq(conn: sqlite3.Connection, chat_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), -1) + 1 FROM idea_chat_messages WHERE chat_id = ?",
        (chat_id,),
    ).fetchone()
    return int(row[0])


def save_chat_message(
    conn: sqlite3.Connection,
    *,
    chat_id: int,
    role: str,
    text: str | None = None,
    tool_name: str | None = None,
    tool_input: dict[str, Any] | None = None,
    tool_use_id: str | None = None,
    tool_result: str | None = None,
    tool_error: bool = False,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> int:
    seq = next_chat_seq(conn, chat_id)
    cur = conn.execute(
        "INSERT INTO idea_chat_messages (chat_id, seq, role, text, tool_name, tool_input,"
        " tool_use_id, tool_result, tool_error, input_tokens, output_tokens, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            chat_id, seq, role,
            (text or "")[:MAX_BLOCK_TEXT] if text else None,
            tool_name,
            json.dumps(tool_input, ensure_ascii=False)[:MAX_BLOCK_TEXT] if tool_input is not None else None,
            tool_use_id,
            (tool_result or "")[:MAX_BLOCK_TEXT] if tool_result else None,
            1 if tool_error else 0,
            input_tokens, output_tokens,
            _now(),
        ),
    )
    touch_chat(conn, chat_id)
    return int(cur.lastrowid)


def load_chat_messages(conn: sqlite3.Connection, chat_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM idea_chat_messages WHERE chat_id = ? ORDER BY seq ASC",
        (chat_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("tool_input"):
            try:
                d["tool_input_parsed"] = json.loads(d["tool_input"])
            except json.JSONDecodeError:
                d["tool_input_parsed"] = None
        out.append(d)
    return out


def list_chats_for_idea(conn: sqlite3.Connection, idea_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM idea_chat_messages m WHERE m.chat_id = c.id) AS msg_count"
        " FROM idea_chats c WHERE idea_id = ? ORDER BY last_message_at DESC, id DESC",
        (idea_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_chat(conn: sqlite3.Connection, chat_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM idea_chats WHERE id = ?", (chat_id,)).fetchone()
    return dict(row) if row else None


def get_idea_with_variants(conn: sqlite3.Connection, idea_id: int) -> tuple[dict | None, list[dict]]:
    row = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
    idea = dict(row) if row else None
    variants = [
        dict(r) for r in conn.execute(
            "SELECT * FROM ideas WHERE parent_idea_id = ? ORDER BY id ASC", (idea_id,)
        ).fetchall()
    ]
    return idea, variants


def get_parent_idea(conn: sqlite3.Connection, idea_id: int) -> dict | None:
    """Fetch the parent of a variant. Returns None if the idea has no parent."""
    row = conn.execute(
        "SELECT * FROM ideas WHERE id = (SELECT parent_idea_id FROM ideas WHERE id = ?)",
        (idea_id,),
    ).fetchone()
    return dict(row) if row else None


def parent_titles_map(conn: sqlite3.Connection) -> dict[int, str]:
    """Batched lookup: {parent_id: parent_title} for every idea that IS a parent
    (i.e. has at least one variant). Used by the Ideas grid to avoid N+1."""
    rows = conn.execute(
        "SELECT id, title FROM ideas"
        " WHERE id IN (SELECT DISTINCT parent_idea_id FROM ideas WHERE parent_idea_id IS NOT NULL)"
    ).fetchall()
    return {int(r["id"]): r["title"] for r in rows}


def save_turn(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    turn_number: int,
    input_tokens: int,
    output_tokens: int,
    stop_reason: str | None,
    assistant_blocks: list[Any],
    tool_results: list[dict[str, Any]] | None = None,
) -> int:
    """Persist one agent turn: the assistant's content blocks + the tool results we sent back.

    assistant_blocks are Anthropic content blocks (objects with .type, .text, .name, .input, .id).
    tool_results are the dicts we posted back to the next turn (type='tool_result', tool_use_id, content).
    """
    cur = conn.execute(
        "INSERT INTO turns (run_id, turn_number, input_tokens, output_tokens, stop_reason, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, turn_number, input_tokens, output_tokens, stop_reason, _now()),
    )
    turn_id = int(cur.lastrowid)

    seq = 0
    for b in assistant_blocks:
        btype = getattr(b, "type", None)
        if btype == "text":
            text = (getattr(b, "text", "") or "")[:MAX_BLOCK_TEXT]
            conn.execute(
                "INSERT INTO turn_blocks (turn_id, seq, block_type, text) VALUES (?, ?, 'text', ?)",
                (turn_id, seq, text),
            )
        elif btype == "tool_use":
            tool_input_json = json.dumps(getattr(b, "input", {}) or {}, ensure_ascii=False)[:MAX_BLOCK_TEXT]
            conn.execute(
                "INSERT INTO turn_blocks (turn_id, seq, block_type, tool_name, tool_input, tool_use_id)"
                " VALUES (?, ?, 'tool_use', ?, ?, ?)",
                (turn_id, seq, getattr(b, "name", None), tool_input_json, getattr(b, "id", None)),
            )
        seq += 1

    for tr in tool_results or []:
        content = tr.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        is_error = 1 if '"error"' in content[:200] or tr.get("is_error") else 0
        conn.execute(
            "INSERT INTO turn_blocks (turn_id, seq, block_type, tool_use_id, tool_result, tool_error)"
            " VALUES (?, ?, 'tool_result', ?, ?, ?)",
            (turn_id, seq, tr.get("tool_use_id"), content[:MAX_BLOCK_TEXT], is_error),
        )
        seq += 1

    return turn_id


def turns_for_run(conn: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM turns WHERE run_id = ? ORDER BY turn_number ASC",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def blocks_for_turn(conn: sqlite3.Connection, turn_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM turn_blocks WHERE turn_id = ? ORDER BY seq ASC",
        (turn_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def tool_call_queries(conn: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    """Every search_signals / web_search query used in a run — raw keyword trace."""
    rows = conn.execute(
        """
        SELECT tb.tool_name, tb.tool_input, t.turn_number
        FROM turn_blocks tb
        JOIN turns t ON tb.turn_id = t.id
        WHERE t.run_id = ? AND tb.block_type = 'tool_use'
          AND tb.tool_name IN ('search_signals', 'web_search')
        ORDER BY t.turn_number ASC, tb.seq ASC
        """,
        (run_id,),
    ).fetchall()
    out = []
    for r in rows:
        try:
            inp = json.loads(r["tool_input"] or "{}")
        except json.JSONDecodeError:
            inp = {}
        out.append({
            "tool": r["tool_name"],
            "turn": r["turn_number"],
            "query": inp.get("query"),
            "source": inp.get("source"),
        })
    return out


def search_signals(
    conn: sqlite3.Connection,
    *,
    query: str | None = None,
    source: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search recent signals by keyword (LIKE on title+content) and/or source."""
    clauses = []
    params: list[Any] = []
    if query:
        clauses.append("(title LIKE ? OR content LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like])
    if source:
        clauses.append("source = ?")
        params.append(source)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT id, source, external_id, title, content, url, metadata, collected_at"
        f" FROM signals {where} ORDER BY collected_at DESC LIMIT ?",
        tuple(params),
    ).fetchall()
    return [dict(r) for r in rows]


def ideas_for_run(conn: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM ideas WHERE run_id = ? ORDER BY score IS NULL, score DESC, id ASC",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]
