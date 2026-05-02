"""DuckDuckGo HTML search — no API key, scrapes html.duckduckgo.com.

Brittle by design (DDG can rate-limit or show anomaly pages). We enforce a
per-run budget so a misbehaving agent can't spam requests, and we surface
failures clearly so the agent can back off.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

DDG_HTML = "https://html.duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
)
TIMEOUT = 20


def _unwrap_ddg_url(href: str) -> str:
    """DDG sometimes wraps outbound links; extract the real URL from `uddg=`."""
    if not href:
        return href
    parsed = urlparse(href if href.startswith("http") else f"https:{href}")
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
        qs = parse_qs(parsed.query)
        if "uddg" in qs and qs["uddg"]:
            return unquote(qs["uddg"][0])
    return href


@dataclass
class WebSearchClient:
    budget: int = 30
    used: int = 0
    throttle_seconds: float = 1.5  # be gentle so DDG doesn't block us
    _last_call: float = 0.0
    results_log: list[dict[str, Any]] = field(default_factory=list)

    def _check_budget(self) -> None:
        if self.used >= self.budget:
            raise RuntimeError(
                f"Web search budget exhausted ({self.budget}). "
                "Stop searching and work with what you have."
            )

    def _throttle(self) -> None:
        delta = time.monotonic() - self._last_call
        if delta < self.throttle_seconds:
            time.sleep(self.throttle_seconds - delta)
        self._last_call = time.monotonic()

    def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        self._check_budget()
        self._throttle()
        self.used += 1
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
        try:
            r = requests.post(
                DDG_HTML,
                data={"q": query, "b": "", "kl": "us-en"},
                headers=headers,
                timeout=TIMEOUT,
            )
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"DDG request failed: {e}") from e

        soup = BeautifulSoup(r.text, "html.parser")
        nodes = soup.select("div.result, div.web-result")
        results: list[dict[str, Any]] = []
        for node in nodes:
            a = node.select_one("a.result__a") or node.select_one("h2 a")
            if not a or not a.has_attr("href"):
                continue
            snippet_el = node.select_one(".result__snippet") or node.select_one("a.result__snippet")
            url = _unwrap_ddg_url(a["href"])
            title = a.get_text(" ", strip=True)
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            if not url or url.startswith("javascript:"):
                continue
            results.append({
                "title": title,
                "url": url,
                "snippet": snippet[:1200],
                "published_date": None,
                "author": None,
            })
            if len(results) >= num_results:
                break

        if not results and ("anomaly" in r.text.lower() or "captcha" in r.text.lower()):
            raise RuntimeError("DDG returned an anomaly/captcha page — back off.")

        self.results_log.append({"query": query, "results": results})
        return results


def make_client(budget: int = 30) -> WebSearchClient:
    return WebSearchClient(budget=budget)


if __name__ == "__main__":
    c = make_client(budget=2)
    res = c.search("best indie iOS app ideas 2026", num_results=5)
    print(f"got {len(res)} results")
    for r in res:
        print("-", r["title"])
        print("  ", r["url"])
