"""One-shot: copy every row from the local SQLite DB to Turso.

Run from the repo root:

    LIBSQL_URL='libsql://...turso.io' \\
    LIBSQL_AUTH_TOKEN='eyJ…' \\
    python -m factory.scripts.migrate_to_turso

Reads from `output/ideation/ideation.db` (the local dev DB) and writes
into the Turso database identified by the env vars. Idempotent — uses
INSERT OR IGNORE so re-running won't duplicate rows.

Migrates these tables in dependency order:
  signals → runs → ideas → turns → turn_blocks → idea_chats → idea_chat_messages
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

LOCAL_DB = Path("output/ideation/ideation.db")

# Order matters because of foreign-key relationships (ideas → runs,
# turns → runs, turn_blocks → turns, etc.). Parents go first.
TABLES_IN_ORDER = [
    "signals",
    "runs",
    "ideas",
    "turns",
    "turn_blocks",
    "idea_chats",
    "idea_chat_messages",
]


def _check_env() -> None:
    missing = [
        k for k in ("LIBSQL_URL", "LIBSQL_AUTH_TOKEN")
        if not os.environ.get(k)
    ]
    if missing:
        print(f"Missing env vars: {missing}", file=sys.stderr)
        print(
            "\nUsage:\n"
            "  LIBSQL_URL='libsql://…' \\\n"
            "  LIBSQL_AUTH_TOKEN='eyJ…' \\\n"
            "  python -m factory.scripts.migrate_to_turso",
            file=sys.stderr,
        )
        sys.exit(1)


def _open_local() -> sqlite3.Connection:
    if not LOCAL_DB.exists():
        print(f"Local DB not found at {LOCAL_DB}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _open_remote():  # type: ignore[no-untyped-def]
    import libsql_experimental as libsql
    # Use a temp dir so we don't conflict with the local dev replica.
    tmp = Path(tempfile.gettempdir()) / "appfactory-migrate" / "replica.db"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    conn = libsql.connect(
        str(tmp),
        sync_url=os.environ["LIBSQL_URL"],
        auth_token=os.environ["LIBSQL_AUTH_TOKEN"],
    )
    conn.sync()  # pull current state from Turso

    # Apply schema in case Turso is empty.
    from factory.ideation.store import SCHEMA, _apply_migrations
    conn.executescript(SCHEMA)
    _apply_migrations(conn)
    return conn


def _columns_for_table(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"SELECT * FROM {table} LIMIT 1")
    return [desc[0] for desc in cur.description]


def _migrate_table(src: sqlite3.Connection, dst, table: str) -> tuple[int, int]:
    """Returns (total_rows_in_local, rows_inserted_into_remote)."""
    rows = src.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return 0, 0
    cols = _columns_for_table(src, table)
    placeholders = ",".join("?" * len(cols))
    col_list = ",".join(cols)
    sql = f"INSERT OR IGNORE INTO {table} ({col_list}) VALUES ({placeholders})"
    inserted = 0
    for row in rows:
        try:
            cur = dst.execute(sql, tuple(row))
            # libsql_experimental Cursor exposes .rowcount; if 0, the row
            # was skipped due to OR IGNORE (already on remote).
            if getattr(cur, "rowcount", 1) != 0:
                inserted += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ! row in {table} failed: {e}", file=sys.stderr)
    dst.commit()
    return len(rows), inserted


def main() -> None:
    _check_env()
    print(f"Source: {LOCAL_DB}")
    print(f"Target: {os.environ['LIBSQL_URL']}")
    print()

    src = _open_local()
    dst = _open_remote()

    grand_total = 0
    grand_inserted = 0
    for table in TABLES_IN_ORDER:
        try:
            total, inserted = _migrate_table(src, dst, table)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {table}: aborted with error — {e}", file=sys.stderr)
            continue
        grand_total += total
        grand_inserted += inserted
        print(f"  {table:>22}: {inserted:>5} new / {total} total")

    print()
    print("Pushing to Turso...")
    try:
        dst.sync()
    except Exception as e:  # noqa: BLE001
        print(f"  ! sync failed: {e}", file=sys.stderr)
        sys.exit(2)

    src.close()
    dst.close()

    print()
    print(f"Done — {grand_inserted} new row(s) inserted out of {grand_total} read.")
    print("Verify in Turso dashboard → Database → Browse.")


if __name__ == "__main__":
    main()
