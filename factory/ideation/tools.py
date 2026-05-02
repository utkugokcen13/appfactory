"""Claude tool-use schemas + dispatchers for the ideation agent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import requests
import trafilatura

from factory.ideation import store
from factory.ideation.signals import reddit as reddit_signal
from factory.ideation.signals import trends as trends_signal
from factory.ideation.signals.websearch import WebSearchClient

FETCH_TIMEOUT = 15
FETCH_MAX_CHARS = 6000

# Matches `<parameter name="foo">value</parameter>` OR the open tag with no close
# (Claude sometimes omits the closing tag when it runs off). Captures name + value.
_PARAM_TAG_RE = re.compile(
    r'<parameter\s+name="([^"]+)"\s*>(.*?)(?=</parameter>|<parameter\s+name="|\Z)',
    re.DOTALL,
)
_CLOSE_TAG_RE = re.compile(r"</[a-zA-Z_][\w-]*>")


def _heal_xml_leakage(raw_input: dict[str, Any]) -> dict[str, Any]:
    """Heal tool inputs where Claude leaked XML `<parameter>` tags into a JSON
    string field (observed on Opus 4.7 / Bedrock for very long inputs).

    For each string value: if it contains a closing tag or `<parameter name=`,
    split at the first such tag, keep the prefix as the cleaned value, and
    extract any `<parameter name="X">Y</parameter>` pairs from the tail.
    Pairs whose target field is empty / missing in raw_input get filled.
    """
    healed = dict(raw_input)
    for key, val in list(healed.items()):
        if not isinstance(val, str):
            continue
        close_idx = -1
        close_m = _CLOSE_TAG_RE.search(val)
        param_idx = val.find('<parameter name="')
        if close_m:
            close_idx = close_m.start()
        candidates = [i for i in (close_idx, param_idx) if i >= 0]
        if not candidates:
            continue
        split_at = min(candidates)
        clean = val[:split_at].rstrip()
        tail = val[split_at:]
        for m in _PARAM_TAG_RE.finditer(tail):
            pname = m.group(1)
            pval = m.group(2).strip()
            # Strip a trailing close tag if regex didn't consume it
            pval = re.sub(r"</parameter>\s*$", "", pval).strip()
            if pname not in healed or not healed.get(pname):
                healed[pname] = pval
        healed[key] = clean
    return healed


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_signals",
        "description": (
            "Search the local signal database collected from App Store charts, "
            "keyword searches, and other sources. Use this to find apps, reviews, "
            "or posts matching a theme. Returns up to `limit` recent rows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword to match against signal title/content (LIKE). Optional.",
                },
                "source": {
                    "type": "string",
                    "description": (
                        "Optional source filter. Known values: "
                        "'appstore_chart', 'appstore_search', 'web_search'."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return (default 15, max 40).",
                },
            },
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web via DuckDuckGo and return titles, URLs, and short snippets. "
            "Use this to investigate a trend, find discussions about a user pain point, "
            "or validate that an app idea is novel. Costs 1 unit from the search budget. "
            "Snippets are short — call `fetch_url` on the most promising links for detail."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "num_results": {
                    "type": "integer",
                    "description": "Number of results (default 5, max 10).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": (
            "Fetch the readable main text of a URL. Use this when a search snippet is "
            "too short and you need the full article (e.g. a Reddit thread or blog post). "
            "Returns up to ~6000 characters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "search_reddit",
        "description": (
            "Search Reddit for posts — optionally scoped to a single subreddit. "
            "Use this to find user pain points, feature requests, app complaints, "
            "or demand discussions. Results are persisted as signals so they "
            "show up in `search_signals(source='reddit')` later."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "subreddit": {
                    "type": "string",
                    "description": "Optional subreddit name (without 'r/'). E.g. 'ADHD'.",
                },
                "sort": {
                    "type": "string",
                    "enum": ["top", "new", "relevance"],
                    "description": "Sort order (default 'top').",
                },
                "time_filter": {
                    "type": "string",
                    "enum": ["day", "week", "month", "year", "all"],
                    "description": "Time window for 'top' (default 'month').",
                },
                "limit": {"type": "integer", "description": "Max posts (default 15, max 25)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_trend",
        "description": (
            "Get Google Trends data for a keyword: 3-month interest-over-time "
            "summary (mean, latest, slope %), plus top and rising related queries. "
            "Rising/breakout queries are the highest-value signal for new app ideas. "
            "Every result is persisted as a signal with source='google_trends' and "
            "a deep link to the Trends page is included for citation. May return "
            "null if Google rate-limits the request."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Seed keyword or phrase."},
                "timeframe": {
                    "type": "string",
                    "description": "Google Trends timeframe string, e.g. 'today 3-m', 'today 12-m', 'today 5-y'. Default 'today 3-m'.",
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "save_idea",
        "description": (
            "Save a candidate app idea with supporting evidence and an explainable "
            "score breakdown. Each run should produce 3-5 high-quality ideas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short app title (2-5 words)."},
                "concept": {
                    "type": "string",
                    "description": "One-paragraph pitch: what it does and for whom.",
                },
                "target_users": {
                    "type": "string",
                    "description": "Primary audience (e.g. 'ADHD adults managing routines').",
                },
                "monetization": {
                    "type": "string",
                    "description": "Revenue hypothesis (freemium, one-time, subscription tier, etc.) with rationale.",
                },
                "ios_feasibility": {
                    "type": "string",
                    "enum": ["solo-1wk", "solo-1mo", "solo-3mo", "team-only"],
                    "description": "How buildable this is for a solo/small team in SwiftUI.",
                },
                "score_breakdown": {
                    "type": "object",
                    "description": (
                        "Explainable scoring — four dimensions, each 0-25. "
                        "Sum should equal `score`."
                    ),
                    "properties": {
                        "novelty": {
                            "type": "integer", "minimum": 0, "maximum": 25,
                            "description": "How fresh/differentiated this wedge is (0 = saturated, 25 = green field)."
                        },
                        "demand": {
                            "type": "integer", "minimum": 0, "maximum": 25,
                            "description": "Strength of demand evidence (chart positions, rating counts, search volume, forum pain)."
                        },
                        "monetization": {
                            "type": "integer", "minimum": 0, "maximum": 25,
                            "description": "Willingness-to-pay + LTV potential given audience and comps."
                        },
                        "feasibility": {
                            "type": "integer", "minimum": 0, "maximum": 25,
                            "description": "How realistic a solo iOS dev can ship a quality MVP (25 = <=1 month)."
                        },
                        "notes": {
                            "type": "object",
                            "description": "Optional 1-sentence note per dimension explaining the score.",
                            "properties": {
                                "novelty": {"type": "string"},
                                "demand": {"type": "string"},
                                "monetization": {"type": "string"},
                                "feasibility": {"type": "string"},
                            },
                        },
                    },
                    "required": ["novelty", "demand", "monetization", "feasibility"],
                },
                "score": {
                    "type": "integer",
                    "description": "Sum of the four breakdown dimensions (0-100). Must equal the sum.",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this idea was chosen — the signals and reasoning narrative.",
                },
                "evidence_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "URLs backing the idea (from web_search or signal rows).",
                },
                "evidence_signal_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Signal row ids that back the idea.",
                },
                "pros": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-4 concrete strengths this idea has.",
                },
                "cons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-4 honest weaknesses, limitations, or reasons this could underperform.",
                },
                "risks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "1-3 things that could kill this idea (regulatory, platform, incumbent reaction).",
                },
                "differentiators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-4 reasons this idea wins vs the strongest incumbents.",
                },
                "key_competitors": {
                    "type": "array",
                    "description": "3-5 nearest competitors with context. Use `note` for anything that doesn't fit the structured fields.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "App or product name."},
                            "url": {"type": "string", "description": "App Store or product URL if known."},
                            "rating": {"type": "number", "description": "Average rating 0-5 if known."},
                            "reviews": {"type": "integer", "description": "Total rating count if known."},
                            "pricing": {"type": "string", "description": "e.g. 'freemium $4.99/mo', '$29.99/yr'."},
                            "note": {"type": "string", "description": "One-line context (their wedge, strengths, weaknesses)."},
                        },
                        "required": ["name"],
                    },
                },
            },
            "required": [
                "title", "concept", "monetization", "ios_feasibility",
                "score_breakdown", "score", "rationale",
                "pros", "cons", "differentiators",
            ],
        },
    },
]


@dataclass
class ToolContext:
    conn: Any  # sqlite3.Connection
    web: WebSearchClient
    run_id: int
    ideas_saved: int = 0
    web_searches_used: int = 0
    saved_idea_ids: list[int] = field(default_factory=list)


def _fetch_url_text(url: str) -> str:
    try:
        r = requests.get(url, timeout=FETCH_TIMEOUT, headers={"User-Agent": "AppFactoryBot/0.1"})
        r.raise_for_status()
    except Exception as e:
        return f"[fetch error: {e}]"
    extracted = trafilatura.extract(r.text, include_comments=False, include_tables=False) or ""
    return extracted[:FETCH_MAX_CHARS] if extracted else r.text[:FETCH_MAX_CHARS]


def dispatch(ctx: ToolContext, name: str, raw_input: dict[str, Any]) -> str:
    """Execute a tool and return a string result suitable for a tool_result block."""
    raw_input = _heal_xml_leakage(raw_input)
    if name == "search_signals":
        rows = store.search_signals(
            ctx.conn,
            query=raw_input.get("query"),
            source=raw_input.get("source"),
            limit=min(int(raw_input.get("limit") or 15), 40),
        )
        # Trim content for prompt efficiency
        trimmed = []
        for r in rows:
            content = (r.get("content") or "")[:400]
            trimmed.append({
                "id": r["id"],
                "source": r["source"],
                "title": r["title"],
                "content": content,
                "url": r["url"],
                "metadata": json.loads(r["metadata"] or "{}"),
            })
        return json.dumps({"count": len(trimmed), "results": trimmed}, ensure_ascii=False)

    if name == "web_search":
        query = raw_input["query"]
        num = min(int(raw_input.get("num_results") or 5), 10)
        results = ctx.web.search(query, num_results=num)
        ctx.web_searches_used = ctx.web.used
        # Also persist these as signals for future runs
        for r in results:
            if r.get("url"):
                store.upsert_signal(
                    ctx.conn,
                    source="web_search",
                    external_id=r["url"],
                    title=r.get("title"),
                    content=r.get("snippet"),
                    url=r.get("url"),
                    metadata={"query": query, "published_date": r.get("published_date")},
                )
        return json.dumps({"count": len(results), "results": results}, ensure_ascii=False)

    if name == "fetch_url":
        url = raw_input["url"]
        text = _fetch_url_text(url)
        return json.dumps({"url": url, "text": text}, ensure_ascii=False)

    if name == "search_reddit":
        query = raw_input["query"]
        subreddit = raw_input.get("subreddit") or None
        sort = raw_input.get("sort") or "top"
        time_filter = raw_input.get("time_filter") or "month"
        limit = min(int(raw_input.get("limit") or 15), 25)
        rows = reddit_signal.search(
            query,
            subreddit=subreddit,
            sort=sort,
            time_filter=time_filter,
            limit=limit,
        )
        # Persist to signals table for later search_signals() access
        for r in rows:
            store.upsert_signal(ctx.conn, **r)
        # Trim to the fields the agent needs
        trimmed = []
        for r in rows:
            md = r.get("metadata") or {}
            trimmed.append({
                "title": r.get("title"),
                "url": r.get("url"),
                "subreddit": md.get("subreddit"),
                "score": md.get("score"),
                "comments": md.get("num_comments"),
                "author": md.get("author"),
                "excerpt": (r.get("content") or "")[:320],
            })
        return json.dumps({"count": len(trimmed), "results": trimmed}, ensure_ascii=False)

    if name == "get_trend":
        keyword = raw_input["keyword"]
        timeframe = raw_input.get("timeframe") or "today 3-m"
        tr = trends_signal.get_trend(keyword, timeframe=timeframe)
        if tr is None:
            return json.dumps({
                "keyword": keyword,
                "available": False,
                "reason": "Google Trends unavailable (rate-limit or empty data)",
            }, ensure_ascii=False)
        # Persist
        for row in trends_signal.trend_to_signals(tr):
            store.upsert_signal(ctx.conn, **row)
        return json.dumps({
            "keyword": tr.keyword,
            "available": True,
            "mean_interest": tr.mean_interest,
            "latest_interest": tr.latest_interest,
            "slope_percent": tr.slope_percent,
            "trend_url": tr.trend_url,
            "rising_queries": tr.rising_queries[:12],
            "top_queries": tr.top_queries[:8],
        }, ensure_ascii=False)

    if name == "save_idea":
        breakdown = raw_input.get("score_breakdown") or {}
        computed = sum(
            int(breakdown.get(k, 0) or 0)
            for k in ("novelty", "demand", "monetization", "feasibility")
        )
        declared = int(raw_input.get("score") or 0)
        # If declared score doesn't match the breakdown sum, trust the breakdown
        # (prevents Claude from inflating the headline number).
        score = computed if abs(declared - computed) > 2 else declared
        idea_id = store.save_idea(
            ctx.conn,
            run_id=ctx.run_id,
            title=raw_input["title"],
            concept=raw_input["concept"],
            target_users=raw_input.get("target_users"),
            monetization=raw_input["monetization"],
            ios_feasibility=raw_input["ios_feasibility"],
            score=score,
            score_breakdown=breakdown,
            rationale=raw_input["rationale"],
            evidence_urls=raw_input.get("evidence_urls") or [],
            evidence_signal_ids=raw_input.get("evidence_signal_ids") or [],
            pros=raw_input.get("pros") or [],
            cons=raw_input.get("cons") or [],
            risks=raw_input.get("risks") or [],
            differentiators=raw_input.get("differentiators") or [],
            key_competitors=raw_input.get("key_competitors") or [],
        )
        ctx.ideas_saved += 1
        ctx.saved_idea_ids.append(idea_id)
        return json.dumps({
            "idea_id": idea_id,
            "saved": True,
            "final_score": score,
            "breakdown_sum": computed,
        }, ensure_ascii=False)

    return json.dumps({"error": f"unknown tool '{name}'"}, ensure_ascii=False)
