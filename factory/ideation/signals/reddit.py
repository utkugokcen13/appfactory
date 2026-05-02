"""Reddit signal collector — public JSON API, no auth required.

Two modes:
  - `collect_daily_top(subreddits)` — fetches today's top posts per subreddit
    (runs at the start of a daily ideation run)
  - `search(query, subreddit)` — on-demand search used by the agent tool
"""

from __future__ import annotations

import time
from typing import Any

import requests

REDDIT_BASE = "https://www.reddit.com"
USER_AGENT = "AppFactoryScout/0.1 (by /u/appfactory)"
TIMEOUT = 15
THROTTLE_SECONDS = 0.8  # be gentle; Reddit rate-limits public JSON ~60/min

# Subreddits we scan daily for pain points, demand signals, app ideas
DEFAULT_SUBREDDITS = [
    # Explicit idea/demand
    "SomebodyMakeThis",
    "AppIdeas",
    "shutupandtakemymoney",
    # Indie dev / maker conversation
    "iOSProgramming",
    "SideProject",
    "indiehackers",
    "Entrepreneur",
    "startups",
    # Pain-driven niches (feature requests + complaints about existing apps)
    "ADHD",
    "productivity",
    "getdisciplined",
    "personalfinance",
    "fitness",
    "loseit",
    "books",
    "LanguageLearning",
]

_last_call = 0.0


def _throttle() -> None:
    global _last_call
    now = time.monotonic()
    delta = now - _last_call
    if delta < THROTTLE_SECONDS:
        time.sleep(THROTTLE_SECONDS - delta)
    _last_call = time.monotonic()


def _get_json(url: str, params: dict | None = None) -> dict | None:
    _throttle()
    try:
        r = requests.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        if r.status_code == 429:
            print(f"[reddit] rate-limited on {url}")
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[reddit] fetch failed {url}: {e}")
        return None


def _rows_from_listing(data: dict, *, source_tag: str, subreddit_fallback: str | None = None) -> list[dict]:
    rows: list[dict] = []
    for child in (data.get("data", {}) or {}).get("children", []) or []:
        p = child.get("data", {}) or {}
        if not p.get("id") or p.get("over_18"):
            continue
        title = (p.get("title") or "").strip()
        body = (p.get("selftext") or "").strip()
        sub = p.get("subreddit") or subreddit_fallback or "—"
        permalink = "https://www.reddit.com" + p.get("permalink", "")
        rows.append({
            "source": source_tag,
            "external_id": f"{sub}:{p.get('id')}",
            "title": title[:300],
            "content": body[:1200] if body else None,
            "url": permalink,
            "metadata": {
                "subreddit": sub,
                "score": p.get("score"),
                "upvote_ratio": p.get("upvote_ratio"),
                "num_comments": p.get("num_comments"),
                "author": p.get("author"),
                "created_utc": p.get("created_utc"),
                "flair": p.get("link_flair_text"),
                "domain": p.get("domain"),
            },
        })
    return rows


def fetch_subreddit_top(
    subreddit: str,
    *,
    time_filter: str = "day",
    limit: int = 20,
) -> list[dict]:
    """Top posts from a subreddit over `time_filter` (day / week / month)."""
    url = f"{REDDIT_BASE}/r/{subreddit}/top.json"
    data = _get_json(url, params={"t": time_filter, "limit": limit})
    if not data:
        return []
    return _rows_from_listing(data, source_tag="reddit", subreddit_fallback=subreddit)


def search(
    query: str,
    *,
    subreddit: str | None = None,
    sort: str = "top",
    time_filter: str = "month",
    limit: int = 20,
) -> list[dict]:
    """Search Reddit — optionally scoped to a subreddit.

    sort: 'top' | 'new' | 'relevance'
    time_filter (only when sort='top'): 'hour' | 'day' | 'week' | 'month' | 'year' | 'all'
    """
    if subreddit:
        url = f"{REDDIT_BASE}/r/{subreddit}/search.json"
        params: dict[str, Any] = {
            "q": query, "restrict_sr": 1, "sort": sort, "t": time_filter, "limit": limit,
        }
        sub_fb = subreddit
    else:
        url = f"{REDDIT_BASE}/search.json"
        params = {"q": query, "sort": sort, "t": time_filter, "limit": limit}
        sub_fb = None
    data = _get_json(url, params=params)
    if not data:
        return []
    return _rows_from_listing(data, source_tag="reddit", subreddit_fallback=sub_fb)


def collect_daily_top(
    subreddits: list[str] | None = None,
    *,
    limit_per_sub: int = 15,
    time_filter: str = "day",
) -> list[dict]:
    """Aggregate today's top posts across all target subreddits."""
    subreddits = subreddits or DEFAULT_SUBREDDITS
    out: list[dict] = []
    for sub in subreddits:
        rows = fetch_subreddit_top(sub, time_filter=time_filter, limit=limit_per_sub)
        out.extend(rows)
    return out


if __name__ == "__main__":
    rows = collect_daily_top(subreddits=["SomebodyMakeThis", "iOSProgramming"], limit_per_sub=5)
    print(f"collected {len(rows)} reddit posts")
    for r in rows[:4]:
        md = r["metadata"]
        print(f"  [r/{md['subreddit']}] {r['title'][:80]} (↑{md.get('score')})")
