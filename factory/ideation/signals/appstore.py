"""App Store signal collector: iTunes Search API + top charts RSS.

Free, no credentials needed. Feeds:
  - Top Free / Top Paid / Top Grossing per category (RSS JSON)
  - iTunes Search API for keyword-based queries
"""

from __future__ import annotations

from typing import Any

import requests

RSS_BASE = "https://itunes.apple.com/us/rss"
SEARCH_URL = "https://itunes.apple.com/search"

# iTunes genre ids for iOS apps most relevant to indie opportunity hunting
DEFAULT_GENRES = {
    "All": None,
    "Productivity": 6007,
    "Utilities": 6002,
    "Lifestyle": 6012,
    "HealthFitness": 6013,
    "Education": 6017,
    "Photo": 6008,
    "Finance": 6015,
}

TIMEOUT = 15


def _rss_url(feed: str, limit: int, genre: int | None) -> str:
    g = f"/genre={genre}" if genre else ""
    return f"{RSS_BASE}/{feed}/limit={limit}{g}/json"


def fetch_top_charts(
    feed: str = "topfreeapplications",
    limit: int = 50,
    genres: dict[str, int | None] | None = None,
) -> list[dict[str, Any]]:
    """Fetch top charts per genre and return signal rows ready for upsert_signal()."""
    genres = genres or DEFAULT_GENRES
    out: list[dict[str, Any]] = []
    for genre_name, genre_id in genres.items():
        url = _rss_url(feed, limit, genre_id)
        try:
            r = requests.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[appstore] {genre_name} fetch failed: {e}")
            continue
        entries = data.get("feed", {}).get("entry", []) or []
        for rank, entry in enumerate(entries, start=1):
            app_id = entry.get("id", {}).get("attributes", {}).get("im:id")
            if not app_id:
                continue
            name = entry.get("im:name", {}).get("label")
            artist = entry.get("im:artist", {}).get("label")
            summary = entry.get("summary", {}).get("label")
            category = entry.get("category", {}).get("attributes", {}).get("label")
            url_ = entry.get("id", {}).get("label")
            out.append({
                "source": "appstore_chart",
                "external_id": f"{feed}:{genre_name}:{app_id}",
                "title": name,
                "content": summary,
                "url": url_,
                "metadata": {
                    "rank": rank,
                    "genre": genre_name,
                    "category": category,
                    "artist": artist,
                    "feed": feed,
                },
            })
    return out


def search_apps(term: str, country: str = "us", limit: int = 25) -> list[dict[str, Any]]:
    """Search iTunes for apps by keyword. Returns signal rows."""
    params = {
        "term": term,
        "country": country,
        "entity": "software",
        "limit": limit,
    }
    try:
        r = requests.get(SEARCH_URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[appstore] search '{term}' failed: {e}")
        return []
    out: list[dict[str, Any]] = []
    for app in data.get("results", []):
        app_id = app.get("trackId")
        if not app_id:
            continue
        out.append({
            "source": "appstore_search",
            "external_id": f"{term}:{app_id}",
            "title": app.get("trackName"),
            "content": app.get("description"),
            "url": app.get("trackViewUrl"),
            "metadata": {
                "query": term,
                "seller": app.get("sellerName"),
                "price": app.get("price"),
                "currency": app.get("currency"),
                "rating": app.get("averageUserRating"),
                "rating_count": app.get("userRatingCount"),
                "genres": app.get("genres"),
                "release_date": app.get("releaseDate"),
                "version": app.get("version"),
            },
        })
    return out


def collect(
    search_terms: list[str] | None = None,
    charts: tuple[str, ...] = ("topfreeapplications", "topgrossingapplications"),
) -> list[dict[str, Any]]:
    """Collect a default daily batch of App Store signals."""
    signals: list[dict[str, Any]] = []
    for feed in charts:
        signals.extend(fetch_top_charts(feed=feed, limit=50))
    if search_terms:
        for term in search_terms:
            signals.extend(search_apps(term, limit=25))
    return signals


if __name__ == "__main__":
    rows = collect(search_terms=["habit tracker", "ai journal"])
    print(f"collected {len(rows)} signals")
    for r in rows[:3]:
        print(r["source"], "-", r["title"])
