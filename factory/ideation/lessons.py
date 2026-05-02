"""Build a 'lessons from past runs' brief that prepends every new ideation run.

Goal: every time the agent runs, it sees what previous runs already explored —
which queries were tried, which ideas scored well, which signal sources paid
off — so it can pick fresh angles instead of re-treading old ground.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from factory.ideation.signals.reddit import DEFAULT_SUBREDDITS as ALL_SUBREDDITS
from factory.ideation.trends_brief import DEFAULT_TREND_SEEDS as ALL_SEEDS

LOOKBACK_RUNS = 5
MAX_TITLES = 24
MAX_QUERIES_PER_TOOL = 24
MIN_GOOD_SCORE = 70


def build_lessons_brief(conn: sqlite3.Connection) -> str:
    """Return a markdown brief of what past runs did. Empty string if no history."""
    runs = conn.execute(
        "SELECT id FROM runs WHERE status='ok' ORDER BY id DESC LIMIT ?",
        (LOOKBACK_RUNS,),
    ).fetchall()
    if not runs:
        return ""

    run_ids = [r["id"] for r in runs]
    placeholders = ",".join("?" for _ in run_ids)

    top_ideas = conn.execute(
        f"SELECT run_id, title, score, target_users, ios_feasibility "
        f"FROM ideas WHERE run_id IN ({placeholders}) "
        f"ORDER BY score IS NULL, score DESC LIMIT 6",
        run_ids,
    ).fetchall()

    all_titles = [
        r["title"] for r in conn.execute(
            f"SELECT title FROM ideas WHERE run_id IN ({placeholders}) "
            f"ORDER BY id DESC LIMIT ?",
            run_ids + [MAX_TITLES],
        ).fetchall()
    ]

    queries_by_tool: dict[str, list[str]] = {}
    for r in conn.execute(
        f"SELECT tb.tool_name, tb.tool_input FROM turn_blocks tb "
        f"JOIN turns t ON tb.turn_id = t.id "
        f"WHERE t.run_id IN ({placeholders}) AND tb.block_type='tool_use' "
        f"  AND tb.tool_name IN ('search_signals','web_search','search_reddit','get_trend')",
        run_ids,
    ).fetchall():
        try:
            inp = json.loads(r["tool_input"] or "{}")
        except json.JSONDecodeError:
            continue
        # Normalize to one descriptive token per call
        if r["tool_name"] == "search_reddit":
            sub = inp.get("subreddit")
            q = inp.get("query") or ""
            label = f"r/{sub}: {q}" if sub else q
        elif r["tool_name"] == "get_trend":
            label = inp.get("keyword") or ""
        else:
            label = inp.get("query") or ""
        label = (label or "").strip()
        if not label:
            continue
        bucket = queries_by_tool.setdefault(r["tool_name"], [])
        if label not in bucket:
            bucket.append(label)

    source_to_scores: dict[str, list[int]] = {}
    for r in conn.execute(
        f"SELECT score, evidence_signal_ids FROM ideas WHERE run_id IN ({placeholders}) "
        f"  AND score IS NOT NULL",
        run_ids,
    ).fetchall():
        sids_raw = r["evidence_signal_ids"] or "[]"
        try:
            sids = json.loads(sids_raw)
        except json.JSONDecodeError:
            continue
        if not sids:
            continue
        sig_ph = ",".join("?" for _ in sids)
        sig_rows = conn.execute(
            f"SELECT DISTINCT source FROM signals WHERE id IN ({sig_ph})",
            sids,
        ).fetchall()
        for s in sig_rows:
            source_to_scores.setdefault(s["source"], []).append(int(r["score"]))

    parts: list[str] = []
    parts.append("## Lessons from previous runs")
    parts.append("")
    parts.append(
        f"You've run ideation **{len(run_ids)} time(s)** before. Use these notes to "
        "pick fresh angles, avoid duplication, and lean into what worked. "
        "Read this section before you touch the trends brief."
    )
    parts.append("")

    if top_ideas:
        parts.append("### What scored well in past runs (reverse-engineer the pattern)")
        for idea in top_ideas:
            score = idea["score"] if idea["score"] is not None else "—"
            tu = (idea["target_users"] or "").strip()
            tu_part = f" · target: _{tu[:60]}_" if tu else ""
            feas = idea["ios_feasibility"] or "—"
            parts.append(
                f"- Run #{idea['run_id']} · **{idea['title']}** — {score}/100 ({feas}){tu_part}"
            )
        parts.append("")

    if all_titles:
        parts.append(
            f"### Already-saved titles — DON'T propose near-duplicates ({len(all_titles)} total)"
        )
        parts.append(", ".join(f"_{t}_" for t in all_titles))
        parts.append("")

    if queries_by_tool:
        parts.append("### Queries / pivots already tried (pick different angles)")
        for tool in ("search_signals", "search_reddit", "get_trend", "web_search"):
            qs = queries_by_tool.get(tool, [])
            if not qs:
                continue
            sample = qs[:MAX_QUERIES_PER_TOOL]
            parts.append(
                f"- **{tool}** · " + " · ".join(f"`{q[:60]}`" for q in sample)
            )
        parts.append("")

    if source_to_scores:
        parts.append("### Source quality from history (avg score · idea count)")
        ranked = sorted(
            source_to_scores.items(),
            key=lambda x: -sum(x[1]) / len(x[1]),
        )
        for src, scores in ranked:
            avg = sum(scores) / len(scores)
            parts.append(f"- `{src}` — avg **{avg:.0f}/100** across {len(scores)} idea(s)")
        parts.append("")

    used_keywords = {q.lower() for qs in queries_by_tool.values() for q in qs}

    untouched_seeds = [s for s in ALL_SEEDS if s.lower() not in used_keywords]
    if untouched_seeds:
        parts.append("### Trend seeds NOT yet hit — `get_trend` candidates")
        parts.append(", ".join(f"`{s}`" for s in untouched_seeds))
        parts.append("")

    sub_used = {
        q.split(":", 1)[0].lower().lstrip("r/").strip()
        for q in queries_by_tool.get("search_reddit", [])
        if ":" in q
    }
    untouched_subs = [s for s in ALL_SUBREDDITS if s.lower() not in sub_used]
    if untouched_subs:
        parts.append("### Subreddits less explored — `search_reddit(subreddit=...)` candidates")
        parts.append(", ".join(f"`r/{s}`" for s in untouched_subs[:12]))
        parts.append("")

    parts.append(
        "**Strategy for this run:** if a source category scored well historically, "
        "lean there again — but on a **different** niche or pain point. If a query "
        "was tried before, don't re-issue it; rephrase or pick a sibling concept. "
        "Aim to push the saved-idea catalog into territory it hasn't covered yet."
    )
    return "\n".join(parts)
