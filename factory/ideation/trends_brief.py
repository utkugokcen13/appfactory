"""Assemble a 'what's rising' brief from Reddit + Google Trends.

Runs BEFORE the agent loop. Produces:
  - Signal rows (upserted into the signals table so the agent can query them)
  - A compact markdown brief embedded into the agent's user message so Claude
    starts the run with a concrete view of "what's hot right now" and cites
    sources.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from factory.ideation.signals import reddit, trends

# Seed niches we track trends for daily. Tight list — Google rate-limits ~5-10/hr.
DEFAULT_TREND_SEEDS = [
    "habit tracker",
    "ai journal",
    "focus timer",
    "sleep tracker",
    "budget app",
    "language learning",
    "pomodoro",
    "meditation",
]

DISABLE_TRENDS = os.getenv("DISABLE_GOOGLE_TRENDS", "").strip() in ("1", "true", "yes")


@dataclass
class TrendsBrief:
    reddit_rows: list[dict]
    trends_rows: list[dict]
    trends_results: list[trends.TrendResult]
    markdown: str


def _fmt_reddit_top(reddit_rows: list[dict], per_sub: int = 3, total_cap: int = 30) -> list[dict]:
    """Pick the strongest posts per subreddit for the brief."""
    by_sub: dict[str, list[dict]] = {}
    for r in reddit_rows:
        sub = (r.get("metadata") or {}).get("subreddit") or "unknown"
        by_sub.setdefault(sub, []).append(r)
    picked: list[dict] = []
    for sub, rows in by_sub.items():
        rows.sort(key=lambda x: (x.get("metadata") or {}).get("score") or 0, reverse=True)
        picked.extend(rows[:per_sub])
    picked.sort(key=lambda x: (x.get("metadata") or {}).get("score") or 0, reverse=True)
    return picked[:total_cap]


def _render_markdown(reddit_picks: list[dict], trend_results: list[trends.TrendResult]) -> str:
    lines: list[str] = []
    lines.append("## Today's rising signals")
    lines.append("")

    if trend_results:
        lines.append("### Google Trends — rising & breakout queries")
        for tr in trend_results:
            rising = [r for r in tr.rising_queries if r.get("query")]
            if not rising:
                continue
            lines.append(
                f"- **{tr.keyword}** — 3-mo mean {tr.mean_interest}/100, "
                f"slope {tr.slope_percent:+.1f}% ([trend]({tr.trend_url}))"
            )
            for r in rising[:6]:
                marker = "🔥" if r.get("type") == "breakout" else "↗"
                val = r.get("value")
                val_str = f" (+{int(val)}%)" if isinstance(val, (int, float)) else ""
                lines.append(f"  - {marker} `{r['query']}`{val_str}")
        lines.append("")
    else:
        lines.append("_Google Trends unavailable this run (rate-limited or disabled)._")
        lines.append("")

    if reddit_picks:
        lines.append("### Reddit — top posts across target subreddits (last 24h)")
        for r in reddit_picks:
            md = r.get("metadata") or {}
            sub = md.get("subreddit") or "—"
            score = md.get("score") or 0
            comments = md.get("num_comments") or 0
            url = r.get("url") or ""
            lines.append(
                f"- **r/{sub}** · ↑{score} · 💬{comments} — [{r['title'][:140]}]({url})"
            )
        lines.append("")
    else:
        lines.append("_No Reddit signals collected._")
        lines.append("")

    lines.append(
        "_When you save an idea, cite at least one Google Trends query or Reddit "
        "permalink from above in `evidence_urls` so the trail is auditable._"
    )
    return "\n".join(lines)


def collect_brief(
    *,
    reddit_subreddits: list[str] | None = None,
    reddit_limit_per_sub: int = 15,
    reddit_time_filter: str = "day",
    trend_seeds: list[str] | None = None,
    trend_timeframe: str = "today 3-m",
) -> TrendsBrief:
    """Collect all 'rising' signals and assemble the markdown brief."""
    reddit_rows = reddit.collect_daily_top(
        subreddits=reddit_subreddits,
        limit_per_sub=reddit_limit_per_sub,
        time_filter=reddit_time_filter,
    )
    print(f"[brief] collected {len(reddit_rows)} reddit posts")

    trend_rows: list[dict] = []
    trend_results: list[trends.TrendResult] = []
    if DISABLE_TRENDS:
        print("[brief] DISABLE_GOOGLE_TRENDS set — skipping trends")
    else:
        seeds = trend_seeds or DEFAULT_TREND_SEEDS
        trend_rows, trend_results = trends.collect_rising_for_niches(
            seeds, timeframe=trend_timeframe
        )
        print(
            f"[brief] collected {len(trend_rows)} trend signals "
            f"across {len(trend_results)}/{len(seeds)} seeds"
        )

    reddit_picks = _fmt_reddit_top(reddit_rows, per_sub=3, total_cap=30)
    md = _render_markdown(reddit_picks, trend_results)
    return TrendsBrief(
        reddit_rows=reddit_rows,
        trends_rows=trend_rows,
        trends_results=trend_results,
        markdown=md,
    )
