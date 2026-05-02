"""Google Trends signal collector via pytrends (unofficial, free).

Provides:
  - `get_trend(keyword)` — interest-over-time summary + rising/top related queries
  - `collect_rising_for_niches(niches)` — batch call for a list of seed niches,
     returns the flat signal rows ready to upsert into the signals table.

Every rising or breakout query becomes a signal with `source='google_trends'`
so the agent can find them via `search_signals(source='google_trends')`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

# pytrends ships with urllib3 < 2.0 assumptions and crashes on Retry init with
# `method_whitelist` (deprecated in urllib3 ≥ 1.26 and removed in 2.0). Patch
# the constructor to accept the old kwarg before importing pytrends.
import urllib3.util.retry as _retry_module

_orig_retry_init = _retry_module.Retry.__init__

def _compat_retry_init(self, *args, **kwargs):
    if "method_whitelist" in kwargs and "allowed_methods" not in kwargs:
        kwargs["allowed_methods"] = kwargs.pop("method_whitelist")
    elif "method_whitelist" in kwargs:
        kwargs.pop("method_whitelist")
    return _orig_retry_init(self, *args, **kwargs)

_retry_module.Retry.__init__ = _compat_retry_init

from pytrends.request import TrendReq  # noqa: E402

THROTTLE_SECONDS = 6.0
DEFAULT_TIMEFRAME = "today 3-m"   # last 3 months
DEFAULT_GEO = ""                   # worldwide; "US" for US-only

# Google aggressively rate-limits the unofficial Trends endpoint for scraper
# user agents. We override with a regular browser UA to reduce 429s.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
)

_last_call = 0.0


def _throttle() -> None:
    global _last_call
    now = time.monotonic()
    delta = now - _last_call
    if delta < THROTTLE_SECONDS:
        time.sleep(THROTTLE_SECONDS - delta)
    _last_call = time.monotonic()


@dataclass
class TrendResult:
    keyword: str
    mean_interest: float        # 0-100 avg over timeframe
    latest_interest: float      # most recent datapoint
    slope_percent: float        # last-third vs first-third % change
    rising_queries: list[dict]  # [{query, value, type}]  type='rising'|'breakout'
    top_queries: list[dict]     # [{query, value}]  the established associations
    trend_url: str              # deep-link to Google Trends for this keyword


def _slope_percent(series: list[float]) -> float:
    """Return percentage change between first third and last third of a series."""
    if len(series) < 6:
        return 0.0
    third = max(1, len(series) // 3)
    first = sum(series[:third]) / third
    last = sum(series[-third:]) / third
    if first < 0.001:
        return 100.0 if last > 0 else 0.0
    return ((last - first) / first) * 100.0


def _pytrends() -> TrendReq:
    return TrendReq(
        hl="en-US",
        tz=360,
        timeout=(10, 25),
        retries=3,
        backoff_factor=2.0,
        requests_args={"headers": {"User-Agent": _BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}},
    )


def get_trend(
    keyword: str,
    *,
    timeframe: str = DEFAULT_TIMEFRAME,
    geo: str = DEFAULT_GEO,
) -> TrendResult | None:
    """Fetch interest-over-time and related queries for one keyword.

    Returns None on any failure (rate-limit, network, empty data) so callers
    can skip gracefully. Prints a short reason so runs stay auditable.
    """
    _throttle()
    try:
        pt = _pytrends()
        pt.build_payload([keyword], timeframe=timeframe, geo=geo)
        iot_df = pt.interest_over_time()
        related = pt.related_queries()
    except Exception as e:
        msg = str(e)
        if "429" in msg or "too many" in msg.lower():
            print(f"[trends] {keyword!r} rate-limited by Google — skipping")
        else:
            print(f"[trends] {keyword!r} failed: {msg[:140]}")
        return None

    if iot_df is None or iot_df.empty or keyword not in iot_df.columns:
        print(f"[trends] {keyword!r} returned empty interest data")
        return None

    series = [float(x) for x in iot_df[keyword].tolist()]
    mean = sum(series) / len(series)
    latest = series[-1] if series else 0.0
    slope = _slope_percent(series)

    rising: list[dict] = []
    top: list[dict] = []
    kw_related = (related or {}).get(keyword) or {}
    rising_df = kw_related.get("rising")
    top_df = kw_related.get("top")
    if rising_df is not None and not rising_df.empty:
        for _, row in rising_df.iterrows():
            val = row.get("value")
            # pytrends marks breakouts as value == 'Breakout' (string)
            is_breakout = isinstance(val, str) and val.strip().lower() == "breakout"
            try:
                numeric = float(val) if not is_breakout else None
            except (ValueError, TypeError):
                numeric = None
            rising.append({
                "query": row.get("query"),
                "value": numeric,
                "type": "breakout" if is_breakout else "rising",
            })
    if top_df is not None and not top_df.empty:
        for _, row in top_df.iterrows():
            try:
                val = float(row.get("value"))
            except (TypeError, ValueError):
                val = None
            top.append({"query": row.get("query"), "value": val})

    return TrendResult(
        keyword=keyword,
        mean_interest=round(mean, 1),
        latest_interest=round(latest, 1),
        slope_percent=round(slope, 1),
        rising_queries=rising[:15],
        top_queries=top[:10],
        trend_url=f"https://trends.google.com/trends/explore?q={quote_plus(keyword)}",
    )


def trend_to_signals(tr: TrendResult) -> list[dict]:
    """Convert a TrendResult into signal rows suitable for upsert_signal()."""
    rows: list[dict] = []
    # One "overall" signal for the seed keyword (so the search_signals view knows
    # the seed had trend data attached).
    rows.append({
        "source": "google_trends",
        "external_id": f"seed:{tr.keyword}",
        "title": f"Trend: {tr.keyword}",
        "content": (
            f"3-mo mean interest {tr.mean_interest}/100, latest {tr.latest_interest}, "
            f"slope {tr.slope_percent:+.1f}%. "
            f"{len(tr.rising_queries)} rising related queries, "
            f"{len(tr.top_queries)} established top queries."
        ),
        "url": tr.trend_url,
        "metadata": {
            "seed": tr.keyword,
            "mean_interest": tr.mean_interest,
            "latest_interest": tr.latest_interest,
            "slope_percent": tr.slope_percent,
            "rising_count": len(tr.rising_queries),
            "kind": "seed_summary",
        },
    })
    # One signal per rising / breakout query
    for r in tr.rising_queries:
        q = r.get("query")
        if not q:
            continue
        kind = r.get("type", "rising")
        value = r.get("value")
        rows.append({
            "source": "google_trends",
            "external_id": f"rising:{tr.keyword}:{q}",
            "title": f"↗ {q}",
            "content": (
                f"Rising Google Trends query associated with seed '{tr.keyword}'. "
                f"Type: {kind.upper()}"
                + (f" (+{int(value)}%)" if isinstance(value, (int, float)) else "")
                + "."
            ),
            "url": f"https://trends.google.com/trends/explore?q={quote_plus(q)}",
            "metadata": {
                "seed": tr.keyword,
                "query": q,
                "type": kind,
                "value": value,
                "kind": "rising_query",
            },
        })
    return rows


def collect_rising_for_niches(
    niches: list[str],
    *,
    timeframe: str = DEFAULT_TIMEFRAME,
    geo: str = DEFAULT_GEO,
) -> tuple[list[dict], list[TrendResult]]:
    """For each seed niche, fetch trend data. Returns (signal_rows, results)."""
    all_rows: list[dict] = []
    results: list[TrendResult] = []
    for niche in niches:
        tr = get_trend(niche, timeframe=timeframe, geo=geo)
        if not tr:
            continue
        results.append(tr)
        all_rows.extend(trend_to_signals(tr))
    return all_rows, results


if __name__ == "__main__":
    t = get_trend("habit tracker")
    if t:
        print(f"'{t.keyword}': mean={t.mean_interest} latest={t.latest_interest} slope={t.slope_percent:+.1f}%")
        print(f"  rising ({len(t.rising_queries)}):")
        for r in t.rising_queries[:5]:
            print(f"    ↗ {r['query']}  [{r['type']}]")
        print(f"  top ({len(t.top_queries)}):")
        for r in t.top_queries[:3]:
            print(f"    • {r['query']}")
