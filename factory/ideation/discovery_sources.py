"""Registry of every discovery source the ideation agent may scan.

Single source of truth that both the Streamlit launcher (UI) and the
runtime read. Each entry carries:
  - `id`        stable key used in `RunConfig.discovery_sources`
  - `label`     UI display name
  - `category`  group id (used to render category sections in the UI)
  - `badge`     'api' (native integration), 'web' (WebFetch on a public
                page), or 'search' (only reachable via DuckDuckGo search)
  - `presets`   which preset bundles include this source
                ('quick' / 'medium' / 'deep')
  - `payload`   optional adapter-specific value (e.g. subreddit name,
                App Store chart key) — runtime collectors use this.

When you add a source here, two things happen automatically:
  1. it appears as a checkbox in the "Discovery sources" launcher block
  2. its id flows into `RunConfig.discovery_sources` and reaches the agent
The actual fetching adapter still has to be wired separately for sources
whose badge is not 'api' yet — until then they're surfaced to the agent
as "consider this source via web search" hints.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoverySource:
    id: str
    label: str
    category: str
    badge: str             # 'api' | 'web' | 'search'
    presets: tuple[str, ...]
    note: str = ""
    payload: str = ""


# ───── Categories ────────────────────────────────────────────────────────
# Order here = render order in the UI.
CATEGORIES: list[tuple[str, str]] = [
    ("maker",      "🛠 Maker community"),
    ("reddit",     "💬 Reddit"),
    ("appstore",   "📱 App stores"),
    ("trends",     "🔍 Search trends"),
    ("social",     "🐦 Social pulse"),
    ("forums",     "📚 Forums & Q&A"),
    ("newsletter", "📰 Newsletters"),
    ("dev",        "💻 Dev ecosystem"),
    ("funding",    "💰 Funding signals"),
    ("reviews",    "⭐ Reviews & complaints"),
]

CATEGORY_LABELS: dict[str, str] = dict(CATEGORIES)

# ───── Presets ───────────────────────────────────────────────────────────
PRESET_NAMES: list[str] = ["Quick", "Medium", "Deep", "Custom"]
PRESET_DESCRIPTIONS: dict[str, str] = {
    "Quick":  "Only sources with native integrations — fast, cheap, predictable.",
    "Medium": "Quick + curated web-fetch sources (HN, Product Hunt, IndieHackers, RSS newsletters…).",
    "Deep":   "Everything, including search-only fallbacks (X, TikTok, LinkedIn, Crunchbase…).",
    "Custom": "Pick exactly what to scan.",
}

# ───── The list ──────────────────────────────────────────────────────────
DISCOVERY_SOURCES: list[DiscoverySource] = [
    # ── Maker / startup community ────────────────────────────────────────
    DiscoverySource("hn",             "Hacker News (top + Show HN + Ask HN)",      "maker", "web", ("medium", "deep"), note="Algolia HN API"),
    DiscoverySource("product_hunt",   "Product Hunt (today/week + maker comments)","maker", "web", ("medium", "deep")),
    DiscoverySource("indie_hackers",  "IndieHackers (top posts + $MRR threads)",   "maker", "web", ("medium", "deep")),
    DiscoverySource("betalist",       "BetaList (pre-launch SaaS dir)",            "maker", "web", ("deep",)),
    DiscoverySource("microns",        "Microns / Tiny Acquisitions (sales)",       "maker", "web", ("deep",)),
    DiscoverySource("acquire_com",    "Acquire.com (SaaS marketplace)",            "maker", "web", ("deep",)),
    DiscoverySource("failory",        "Failory (failed-startup post-mortems)",     "maker", "web", ("deep",)),
    DiscoverySource("starter_story",  "StarterStory ($0→$X case studies)",         "maker", "web", ("deep",)),

    # ── Reddit (subreddit per row, payload = real subreddit name) ────────
    DiscoverySource("reddit_somebodymakethis",     "r/SomebodyMakeThis",     "reddit", "api", ("quick", "medium", "deep"), payload="SomebodyMakeThis"),
    DiscoverySource("reddit_appideas",             "r/AppIdeas",             "reddit", "api", ("quick", "medium", "deep"), payload="AppIdeas"),
    DiscoverySource("reddit_shutupandtakemymoney", "r/shutupandtakemymoney", "reddit", "api", ("quick", "medium", "deep"), payload="shutupandtakemymoney"),
    DiscoverySource("reddit_iosprogramming",       "r/iOSProgramming",       "reddit", "api", ("quick", "medium", "deep"), payload="iOSProgramming"),
    DiscoverySource("reddit_sideproject",          "r/SideProject",          "reddit", "api", ("quick", "medium", "deep"), payload="SideProject"),
    DiscoverySource("reddit_indiehackers",         "r/indiehackers",         "reddit", "api", ("quick", "medium", "deep"), payload="indiehackers"),
    DiscoverySource("reddit_entrepreneur",         "r/Entrepreneur",         "reddit", "api", ("quick", "medium", "deep"), payload="Entrepreneur"),
    DiscoverySource("reddit_startups",             "r/startups",             "reddit", "api", ("quick", "medium", "deep"), payload="startups"),
    DiscoverySource("reddit_adhd",                 "r/ADHD",                 "reddit", "api", ("quick", "medium", "deep"), payload="ADHD"),
    DiscoverySource("reddit_productivity",         "r/productivity",         "reddit", "api", ("quick", "medium", "deep"), payload="productivity"),
    DiscoverySource("reddit_getdisciplined",       "r/getdisciplined",       "reddit", "api", ("quick", "medium", "deep"), payload="getdisciplined"),
    DiscoverySource("reddit_personalfinance",      "r/personalfinance",      "reddit", "api", ("quick", "medium", "deep"), payload="personalfinance"),
    DiscoverySource("reddit_fitness",              "r/fitness",              "reddit", "api", ("quick", "medium", "deep"), payload="fitness"),
    DiscoverySource("reddit_loseit",               "r/loseit",               "reddit", "api", ("quick", "medium", "deep"), payload="loseit"),
    DiscoverySource("reddit_books",                "r/books",                "reddit", "api", ("quick", "medium", "deep"), payload="books"),
    DiscoverySource("reddit_languagelearning",     "r/LanguageLearning",     "reddit", "api", ("quick", "medium", "deep"), payload="LanguageLearning"),
    DiscoverySource("reddit_askreddit",            "r/AskReddit (cultural pulse)",          "reddit", "api", ("deep",),                       payload="AskReddit"),
    DiscoverySource("reddit_nostupidquestions",    "r/NoStupidQuestions",                   "reddit", "api", ("deep",),                       payload="NoStupidQuestions"),
    DiscoverySource("reddit_lifeprotips",          "r/LifeProTips",                         "reddit", "api", ("medium", "deep"),               payload="LifeProTips"),
    DiscoverySource("reddit_frugal",               "r/Frugal",                              "reddit", "api", ("deep",),                       payload="Frugal"),
    DiscoverySource("reddit_parenting",            "r/parenting",                           "reddit", "api", ("medium", "deep"),               payload="parenting"),
    DiscoverySource("reddit_mommit",               "r/Mommit",                              "reddit", "api", ("deep",),                       payload="Mommit"),
    DiscoverySource("reddit_cooking",              "r/cooking",                             "reddit", "api", ("deep",),                       payload="cooking"),
    DiscoverySource("reddit_mealprepsunday",       "r/MealPrepSunday",                      "reddit", "api", ("deep",),                       payload="MealPrepSunday"),
    DiscoverySource("reddit_learnprogramming",     "r/learnprogramming",                    "reddit", "api", ("deep",),                       payload="learnprogramming"),
    DiscoverySource("reddit_cscareerquestions",    "r/cscareerquestions",                   "reddit", "api", ("deep",),                       payload="cscareerquestions"),
    DiscoverySource("reddit_saas",                 "r/SaaS",                                "reddit", "api", ("medium", "deep"),               payload="SaaS"),

    # ── App stores ──────────────────────────────────────────────────────
    DiscoverySource("appstore_charts",  "App Store top charts (free/paid/grossing)", "appstore", "api", ("quick", "medium", "deep")),
    DiscoverySource("appstore_search",  "App Store keyword search (iTunes API)",     "appstore", "api", ("quick", "medium", "deep")),
    DiscoverySource("appstore_reviews", "App Store 1★ reviews on category leaders",  "appstore", "api", ("medium", "deep")),
    DiscoverySource("playstore_charts", "Google Play top charts",                    "appstore", "web", ("medium", "deep")),
    DiscoverySource("appfigures",       "AppFigures rising apps",                    "appstore", "web", ("deep",)),
    DiscoverySource("alternativeto",    "AlternativeTo (users seeking alternatives)","appstore", "web", ("medium", "deep")),

    # ── Search trends ───────────────────────────────────────────────────
    DiscoverySource("google_trends",     "Google Trends rising/breakout queries",    "trends", "api", ("quick", "medium", "deep")),
    DiscoverySource("exploding_topics",  "Exploding Topics (early-stage growth)",    "trends", "web", ("medium", "deep")),
    DiscoverySource("answer_the_public", "AnswerThePublic (question-keyword seeds)", "trends", "web", ("deep",)),
    DiscoverySource("glimpse",           "Glimpse (Trends explosive-growth detector)","trends","web", ("deep",)),

    # ── Social pulse ────────────────────────────────────────────────────
    DiscoverySource("x_lists",            "X / Twitter (trending lists, tech timeline)", "social", "search", ("medium", "deep")),
    DiscoverySource("tiktok_trending",    "TikTok trending hashtags + sounds",           "social", "search", ("deep",)),
    DiscoverySource("youtube_trending",   "YouTube trending (tech / productivity)",      "social", "search", ("deep",)),
    DiscoverySource("linkedin_trending",  "LinkedIn trending posts (B2B pulse)",         "social", "search", ("deep",)),
    DiscoverySource("pinterest_trending", "Pinterest trending (DIY / hobby / lifestyle)","social", "search", ("deep",)),

    # ── Forums & Q&A ────────────────────────────────────────────────────
    DiscoverySource("stackexchange",  "Stack Exchange network (170+ topic sites)",       "forums", "api",    ("medium", "deep")),
    DiscoverySource("stackoverflow",  "Stack Overflow (developer pain points)",          "forums", "api",    ("medium", "deep")),
    DiscoverySource("quora",          "Quora popular questions in topic spaces",         "forums", "search", ("deep",)),
    DiscoverySource("discourse",      "Discourse forums (Obsidian, Notion, HomeAssistant…)","forums","web",  ("deep",)),

    # ── Newsletter / curated ────────────────────────────────────────────
    DiscoverySource("lennys",      "Lenny's Newsletter (product / growth)", "newsletter", "web", ("medium", "deep")),
    DiscoverySource("not_boring",  "Not Boring (Packy McCormick)",          "newsletter", "web", ("deep",)),
    DiscoverySource("trends_vc",   "Trends.vc (explicit niche reports)",    "newsletter", "web", ("medium", "deep")),
    DiscoverySource("the_hustle",  "The Hustle (daily consumer trend)",     "newsletter", "web", ("deep",)),
    DiscoverySource("tldr",        "TLDR / Hacker Newsletter",              "newsletter", "web", ("medium", "deep")),
    DiscoverySource("stratechery", "Stratechery (strategy analysis)",       "newsletter", "web", ("deep",)),

    # ── Dev ecosystem ───────────────────────────────────────────────────
    DiscoverySource("github_trending", "GitHub Trending (dev tool ideas)",  "dev", "web", ("medium", "deep")),
    DiscoverySource("dribbble",        "Dribbble (designer pain points)",   "dev", "web", ("deep",)),
    DiscoverySource("dev_to",          "Dev.to (developer blog topics)",    "dev", "api", ("medium", "deep")),
    DiscoverySource("hashnode",        "Hashnode (dev community)",          "dev", "api", ("deep",)),
    DiscoverySource("replit_trending", "Replit Trending",                   "dev", "web", ("deep",)),

    # ── Funding ─────────────────────────────────────────────────────────
    DiscoverySource("crunchbase", "Crunchbase seed / Series-A rounds", "funding", "search", ("deep",)),
    DiscoverySource("angellist",  "AngelList trending startups",        "funding", "search", ("deep",)),
    DiscoverySource("yc_blog",    "YC blog (theme essays)",             "funding", "web",    ("medium", "deep")),
    DiscoverySource("a16z_blog",  "a16z / Sequoia thesis posts",        "funding", "web",    ("deep",)),

    # ── Reviews / complaints ────────────────────────────────────────────
    DiscoverySource("g2_capterra", "G2 / Capterra trending searches", "reviews", "search", ("deep",)),
    DiscoverySource("trustpilot",  "Trustpilot worst-rated",          "reviews", "search", ("deep",)),
]

# Quick-lookup map by id (build once at import time).
SOURCES_BY_ID: dict[str, DiscoverySource] = {s.id: s for s in DISCOVERY_SOURCES}


def sources_for_preset(name: str) -> list[str]:
    """Return source IDs included by the given preset (lowercased name)."""
    key = (name or "").strip().lower()
    if key not in {"quick", "medium", "deep"}:
        return []
    return [s.id for s in DISCOVERY_SOURCES if key in s.presets]


def sources_in_category(category: str) -> list[DiscoverySource]:
    return [s for s in DISCOVERY_SOURCES if s.category == category]


def subreddits_from_selection(selected_ids: list[str]) -> list[str]:
    """Resolve selected reddit-category sources to their subreddit names
    (the payload field). Drives the existing reddit collector's input."""
    chosen = set(selected_ids or [])
    return [s.payload for s in DISCOVERY_SOURCES
            if s.id in chosen and s.category == "reddit" and s.payload]


def default_selection() -> list[str]:
    """Default = Quick preset (only the natively-integrated sources)."""
    return sources_for_preset("quick")
