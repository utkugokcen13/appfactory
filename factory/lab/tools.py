"""Tool-use schemas + dispatcher for the Idea Lab chat agent.

Reuses existing research tools (search_signals, web_search, fetch_url,
search_reddit, get_trend) and adds lab-specific mutation tools:

  - update_idea_field(field, value)  — edit an existing idea's structured field
  - create_variant_idea(...)          — save a new idea row with parent_idea_id
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import requests
import trafilatura

from factory.ideation import store
from factory.ideation.signals import reddit as reddit_signal
from factory.ideation.signals import trends as trends_signal
from factory.ideation.signals.websearch import WebSearchClient
from factory.ideation.tools import _heal_xml_leakage  # reuse XML healer

FETCH_TIMEOUT = 15
FETCH_MAX_CHARS = 6000

UPDATABLE_FIELDS = [
    "target_users",
    "monetization",
    "ios_feasibility",
    "score",
    "score_breakdown",
    "pros",
    "cons",
    "risks",
    "differentiators",
    "key_competitors",
    "rationale",
    "stage",
]


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_signals",
        "description": (
            "Search the local signal database (App Store charts, iTunes search, "
            "Reddit, Google Trends, web_search) for supporting evidence. Great as "
            "a first step before spending a live search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "source": {"type": "string", "description": "Optional: 'appstore_chart', 'reddit', 'google_trends', etc."},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "web_search",
        "description": "Live DuckDuckGo search. Use when local signals aren't enough.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": "Fetch readable text of a URL (~6000 char max).",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "search_reddit",
        "description": "Search Reddit (optionally a single subreddit) for pain points, requests, complaints.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "subreddit": {"type": "string"},
                "sort": {"type": "string", "enum": ["top", "new", "relevance"]},
                "time_filter": {"type": "string", "enum": ["day", "week", "month", "year", "all"]},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_trend",
        "description": (
            "Google Trends — interest over time + rising queries for a keyword. "
            "Best way to validate whether a pivot direction is actually growing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "timeframe": {"type": "string"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "update_idea_field",
        "description": (
            "Update a structured field on the CURRENT idea after the user agrees "
            "to a change. Use only when the user explicitly wants to edit. For "
            "list/object fields, pass the full replacement value (not a delta)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": UPDATABLE_FIELDS,
                    "description": "Which idea field to update.",
                },
                "value": {
                    "description": (
                        "New value. Strings for text fields (target_users, monetization, "
                        "ios_feasibility, rationale, stage). Integer for score. "
                        "Array of strings for pros/cons/risks/differentiators. "
                        "Array of competitor objects for key_competitors. "
                        "Object with novelty/demand/monetization/feasibility/notes for score_breakdown."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": "One-line justification — what changed and why.",
                },
            },
            "required": ["field", "value", "reason"],
        },
    },
    {
        "name": "create_variant_idea",
        "description": (
            "Save a NEW idea as a variant of the current one (parent_idea_id set). "
            "Use when the user wants to pivot (different audience, pricing, feature "
            "focus) and keep both concepts in play. Mirror the save_idea schema."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "concept": {"type": "string"},
                "target_users": {"type": "string"},
                "monetization": {"type": "string"},
                "ios_feasibility": {
                    "type": "string",
                    "enum": ["solo-1wk", "solo-1mo", "solo-3mo", "team-only"],
                },
                "score": {"type": "integer"},
                "score_breakdown": {
                    "type": "object",
                    "properties": {
                        "novelty": {"type": "integer"},
                        "demand": {"type": "integer"},
                        "monetization": {"type": "integer"},
                        "feasibility": {"type": "integer"},
                        "notes": {"type": "object"},
                    },
                    "required": ["novelty", "demand", "monetization", "feasibility"],
                },
                "rationale": {"type": "string"},
                "pros": {"type": "array", "items": {"type": "string"}},
                "cons": {"type": "array", "items": {"type": "string"}},
                "risks": {"type": "array", "items": {"type": "string"}},
                "differentiators": {"type": "array", "items": {"type": "string"}},
                "key_competitors": {"type": "array"},
                "evidence_urls": {"type": "array", "items": {"type": "string"}},
                "pivot_note": {
                    "type": "string",
                    "description": "One-line: how this variant differs from parent.",
                },
            },
            "required": [
                "title", "concept", "monetization", "ios_feasibility",
                "score_breakdown", "score", "rationale", "pivot_note",
            ],
        },
    },
]


@dataclass
class LabContext:
    conn: Any
    web: WebSearchClient
    idea_id: int
    chat_id: int
    web_searches_used: int = 0
    fields_updated: list[str] = field(default_factory=list)
    variants_created: list[int] = field(default_factory=list)


def _fetch_url_text(url: str) -> str:
    try:
        r = requests.get(url, timeout=FETCH_TIMEOUT, headers={"User-Agent": "AppFactoryBot/0.1"})
        r.raise_for_status()
    except Exception as e:
        return f"[fetch error: {e}]"
    extracted = trafilatura.extract(r.text, include_comments=False, include_tables=False) or ""
    return extracted[:FETCH_MAX_CHARS] if extracted else r.text[:FETCH_MAX_CHARS]


def dispatch(ctx: LabContext, name: str, raw_input: dict[str, Any]) -> str:
    raw_input = _heal_xml_leakage(raw_input)

    if name == "search_signals":
        rows = store.search_signals(
            ctx.conn,
            query=raw_input.get("query"),
            source=raw_input.get("source"),
            limit=min(int(raw_input.get("limit") or 15), 40),
        )
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
        rows = reddit_signal.search(
            raw_input["query"],
            subreddit=raw_input.get("subreddit") or None,
            sort=raw_input.get("sort") or "top",
            time_filter=raw_input.get("time_filter") or "month",
            limit=min(int(raw_input.get("limit") or 15), 25),
        )
        for r in rows:
            store.upsert_signal(ctx.conn, **r)
        trimmed = []
        for r in rows:
            md = r.get("metadata") or {}
            trimmed.append({
                "title": r.get("title"),
                "url": r.get("url"),
                "subreddit": md.get("subreddit"),
                "score": md.get("score"),
                "comments": md.get("num_comments"),
                "excerpt": (r.get("content") or "")[:320],
            })
        return json.dumps({"count": len(trimmed), "results": trimmed}, ensure_ascii=False)

    if name == "get_trend":
        tr = trends_signal.get_trend(
            raw_input["keyword"],
            timeframe=raw_input.get("timeframe") or "today 3-m",
        )
        if tr is None:
            return json.dumps({
                "keyword": raw_input["keyword"],
                "available": False,
                "reason": "Google Trends unavailable",
            }, ensure_ascii=False)
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

    if name == "update_idea_field":
        field_name = raw_input["field"]
        value = raw_input["value"]
        reason = raw_input.get("reason", "")
        try:
            store.update_idea_field(ctx.conn, ctx.idea_id, field_name, value)
            ctx.fields_updated.append(field_name)
            return json.dumps({
                "ok": True,
                "idea_id": ctx.idea_id,
                "field": field_name,
                "reason": reason,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    if name == "create_variant_idea":
        breakdown = raw_input.get("score_breakdown") or {}
        computed = sum(
            int(breakdown.get(k, 0) or 0)
            for k in ("novelty", "demand", "monetization", "feasibility")
        )
        declared = int(raw_input.get("score") or 0)
        final_score = computed if abs(declared - computed) > 2 else declared
        pivot_note = raw_input.get("pivot_note")
        variant_id = store.save_idea(
            ctx.conn,
            run_id=None,
            title=raw_input["title"],
            concept=raw_input["concept"],
            target_users=raw_input.get("target_users"),
            monetization=raw_input["monetization"],
            ios_feasibility=raw_input["ios_feasibility"],
            score=final_score,
            score_breakdown=breakdown,
            rationale=raw_input["rationale"],
            evidence_urls=raw_input.get("evidence_urls") or [],
            evidence_signal_ids=[],
            pros=raw_input.get("pros") or [],
            cons=raw_input.get("cons") or [],
            risks=raw_input.get("risks") or [],
            differentiators=raw_input.get("differentiators") or [],
            key_competitors=raw_input.get("key_competitors") or [],
            parent_idea_id=ctx.idea_id,
            pivot_note=pivot_note,
        )
        ctx.variants_created.append(variant_id)
        return json.dumps({
            "ok": True,
            "variant_id": variant_id,
            "parent_idea_id": ctx.idea_id,
            "pivot_note": pivot_note,
            "final_score": final_score,
        }, ensure_ascii=False)

    return json.dumps({"error": f"unknown tool '{name}'"}, ensure_ascii=False)
