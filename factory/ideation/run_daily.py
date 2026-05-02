"""Daily ideation run: collect signals, invoke agent, write markdown digest."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from factory.client import DEFAULT_MODEL
from factory.ideation import lessons, store
from factory.ideation.agent import run_agent
from factory.ideation.run_config import RunConfig
from factory.ideation.signals import appstore
from factory.ideation.signals.websearch import make_client
from factory.ideation.tools import ToolContext
from factory.ideation.trends_brief import collect_brief

OUTPUT_DIR = Path("output/ideation")
DEFAULT_SEARCH_TERMS = [
    "habit tracker",
    "ai journal",
    "budget planner",
    "meditation",
    "pomodoro",
    "sleep tracker",
    "language learning",
    "reading tracker",
]


def collect_appstore_signals(conn, search_terms: list[str]) -> int:
    rows = appstore.collect(search_terms=search_terms)
    for r in rows:
        store.upsert_signal(conn, **r)
    return len(rows)


def persist_brief_signals(conn, brief) -> int:
    """Persist reddit + google_trends rows from a TrendsBrief."""
    n = 0
    for r in brief.reddit_rows:
        store.upsert_signal(conn, **r)
        n += 1
    for r in brief.trends_rows:
        store.upsert_signal(conn, **r)
        n += 1
    return n


def build_brief(
    appstore_count: int,
    reddit_count: int,
    trends_count: int,
    today: str,
    trends_md: str,
    lessons_md: str = "",
    focus_prompt: str = "",
    target_count_phrase: str = "3-5",
) -> str:
    focus_block = ""
    if focus_prompt.strip():
        focus_block = (
            "## 🎯 USER FOCUS — read this FIRST\n\n"
            "The user has supplied an explicit direction for this run. Treat it "
            "as the highest-priority constraint, above the trends brief and "
            "lessons section. Every saved idea must clearly serve this focus.\n\n"
            f"> {focus_prompt.strip()}\n\n"
        )
    lessons_block = (lessons_md.strip() + "\n\n") if lessons_md.strip() else ""
    return (
        f"Today is {today}. I just collected fresh signals across sources:\n"
        f"- {appstore_count} App Store (charts + keyword search)\n"
        f"- {reddit_count} Reddit posts (top of last 24h across target subreddits)\n"
        f"- {trends_count} Google Trends rows (rising + breakout queries)\n\n"
        f"{focus_block}"
        f"{lessons_block}"
        "Below is a precomputed brief of the highest-signal items. Start from "
        "here — cross-reference with `search_signals` and drill into threads "
        f"with `search_reddit` / `get_trend`. Save {target_count_phrase} ideas, each citing at "
        "least one Google Trends or Reddit URL as evidence.\n\n"
        f"{trends_md}"
    )


def _format_breakdown(breakdown: dict) -> list[str]:
    dims = ["novelty", "demand", "monetization", "feasibility"]
    notes = breakdown.get("notes") or {}
    lines = ["| Dimension | Score | Note |", "|---|---|---|"]
    for d in dims:
        score = breakdown.get(d, "—")
        note = (notes.get(d) or "").replace("|", "\\|")
        lines.append(f"| {d.capitalize()} | {score}/25 | {note} |")
    return lines


def write_digest(run_id: int, ideas: list[dict], queries: list[dict], target: Path) -> None:
    today = date.today().isoformat()
    lines = [
        f"# Ideation Digest — {today}",
        "",
        f"Run id: {run_id}  ·  Ideas: {len(ideas)}  ·  Queries: {len(queries)}",
        "",
    ]
    if queries:
        lines += ["## Keywords used this run", ""]
        lines.append("| Turn | Tool | Query | Source |")
        lines.append("|---|---|---|---|")
        for q in queries:
            qtext = (q.get("query") or "").replace("|", "\\|")
            lines.append(
                f"| {q['turn']} | {q['tool']} | {qtext or '—'} | {q.get('source') or '—'} |"
            )
        lines.append("")

    if not ideas:
        lines.append("_No ideas met the quality bar this run._")
    for i, idea in enumerate(ideas, start=1):
        urls = json.loads(idea.get("evidence_urls") or "[]")
        breakdown = json.loads(idea.get("score_breakdown") or "{}")
        lines += [
            f"## {i}. {idea['title']}  ·  score {idea.get('score')}/100",
            "",
            f"**Concept.** {idea['concept']}",
            "",
            f"- **Target users:** {idea.get('target_users') or '—'}",
            f"- **Monetization:** {idea.get('monetization') or '—'}",
            f"- **Feasibility:** {idea.get('ios_feasibility') or '—'}",
            "",
        ]
        if breakdown:
            lines += _format_breakdown(breakdown)
            lines.append("")
        lines += [
            f"**Why.** {idea.get('rationale') or ''}",
            "",
        ]
        if urls:
            lines.append("**Evidence:**")
            lines += [f"- {u}" for u in urls]
            lines.append("")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")


def _resolve_config(args: argparse.Namespace) -> RunConfig:
    """Build a RunConfig from --config JSON path (preferred) or from CLI flags
    (legacy / direct invocation)."""
    if args.config:
        cfg = RunConfig.from_json(args.config)
    else:
        cfg = RunConfig()
        if args.max_turns is not None:
            cfg.max_turns = int(args.max_turns)
        if args.search_budget is not None:
            cfg.search_budget = int(args.search_budget)
        if args.terms:
            cfg.niche_seeds = list(args.terms)
    return cfg


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the ideation agent once.")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to RunConfig JSON file (Streamlit launcher uses this).")
    parser.add_argument("--search-budget", type=int, default=None,
                        help="Max web searches this run (default 35).")
    parser.add_argument("--max-turns", type=int, default=None,
                        help="Max agent tool-use turns (default 22).")
    parser.add_argument("--terms", nargs="*", default=None,
                        help="iTunes Search API terms to seed signals with.")
    args = parser.parse_args()

    load_dotenv()
    cfg = _resolve_config(args)

    # Pre-flight env knobs derived from config
    if cfg.disable_google_trends:
        os.environ["DISABLE_GOOGLE_TRENDS"] = "1"

    seeds = cfg.niche_seeds if cfg.niche_seeds else DEFAULT_SEARCH_TERMS
    subreddits = cfg.subreddits if cfg.subreddits else None  # None → reddit module default

    # Tag the run with the launching user (for per-user cap accounting).
    # Falls back to the bare "ideation" tag for CLI / cron-style runs that
    # don't go through the auth-gated UI.
    _user = os.environ.get("APPFACTORY_USER")
    if _user:
        _safe = "".join(c for c in _user if c.isalnum() or c in "_-")
        agent_tag = f"ideation:{_safe}" if _safe else "ideation"
    else:
        agent_tag = "ideation"

    with store.connect() as conn:
        run_id = store.start_run(conn, agent=agent_tag, model=cfg.model or DEFAULT_MODEL)
        try:
            if cfg.skip_signal_collection:
                print("[ideation] skip_signal_collection=True — using existing DB signals only")
                appstore_count = 0
                trends_brief_obj = None
                reddit_count = 0
                trends_count = 0
                trends_md = "_(signal collection skipped — relying on existing signals in DB)_"
                pre_count = 0
            else:
                appstore_count = collect_appstore_signals(conn, seeds)
                print(f"[ideation] collected {appstore_count} appstore signals")

                trends_brief_obj = collect_brief(
                    reddit_subreddits=subreddits,
                    trend_seeds=seeds,
                )
                pre_count = persist_brief_signals(conn, trends_brief_obj)
                reddit_count = len(trends_brief_obj.reddit_rows)
                trends_count = len(trends_brief_obj.trends_rows)
                trends_md = trends_brief_obj.markdown
                print(
                    f"[ideation] persisted {pre_count} reddit+trends signals "
                    f"({reddit_count} reddit, {trends_count} trends)"
                )

            signals_count = appstore_count + pre_count

            web = make_client(budget=cfg.search_budget)
            ctx = ToolContext(conn=conn, web=web, run_id=run_id)

            lessons_md = lessons.build_lessons_brief(conn)
            if lessons_md:
                print(f"[ideation] lessons brief: {len(lessons_md)} chars")

            brief = build_brief(
                appstore_count=appstore_count,
                reddit_count=reddit_count,
                trends_count=trends_count,
                today=date.today().isoformat(),
                trends_md=trends_md,
                lessons_md=lessons_md,
                focus_prompt=cfg.focus_prompt,
                target_count_phrase=cfg.target_count_phrase(),
            )
            result = run_agent(
                ctx,
                brief,
                model=cfg.model or DEFAULT_MODEL,
                max_turns=cfg.max_turns,
                config=cfg,
            )

            ideas = store.ideas_for_run(conn, run_id)
            queries = store.tool_call_queries(conn, run_id)
            digest_path = OUTPUT_DIR / f"{date.today().isoformat()}.md"
            write_digest(run_id, ideas, queries, digest_path)

            store.finish_run(
                conn,
                run_id,
                signals_collected=signals_count,
                ideas_generated=result.ideas_saved,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                web_searches=result.web_searches,
                status="ok",
            )
            print(
                f"[ideation] done: {result.ideas_saved} ideas | "
                f"{result.input_tokens} in / {result.output_tokens} out tokens | "
                f"{result.web_searches} web searches | stop={result.stop_reason}"
            )
            print(f"[ideation] digest: {digest_path}")
            return 0
        except Exception as e:
            traceback.print_exc()
            store.finish_run(
                conn,
                run_id,
                signals_collected=0,
                ideas_generated=0,
                input_tokens=0,
                output_tokens=0,
                web_searches=0,
                status="error",
                error=str(e),
            )
            return 1


if __name__ == "__main__":
    sys.exit(main())
