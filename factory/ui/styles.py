"""Global CSS + helpers for App Factory UI — dark theme."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st


# ───── Time formatting (UTC in DB → user's local tz on screen) ───────────
def format_local_dt(
    iso_str: str | None,
    fmt: str = "%Y-%m-%d %H:%M:%S",
    *,
    fallback: str = "—",
) -> str:
    """Render a DB ISO timestamp in the user's local timezone.

    The DB stores everything in UTC (some rows tz-aware, some naive — naive
    rows are assumed UTC). We convert to the host's local tz for display.
    For deploys where the server runs in a different tz than the viewer, set
    the TZ env var on the host (e.g. TZ=Europe/Istanbul).
    """
    if not iso_str:
        return fallback
    try:
        s = datetime.fromisoformat(iso_str)
    except (TypeError, ValueError):
        return iso_str[:19].replace("T", " ")
    if s.tzinfo is None:
        s = s.replace(tzinfo=timezone.utc)
    return s.astimezone().strftime(fmt)


def format_local_date(iso_str: str | None, fallback: str = "—") -> str:
    """Date-only variant (YYYY-MM-DD) in the user's local tz."""
    return format_local_dt(iso_str, fmt="%Y-%m-%d", fallback=fallback)


# ───── Color system (dark) ───────────────────────────────────────────────
COLORS = {
    "bg":          "#0B0F17",
    "sidebar_bg":  "#11161F",
    "card":        "#1A2130",
    "card_hover":  "#1F2636",
    "border":      "#2D3748",
    "border_soft": "#1F2636",
    "divider":     "#1F2636",
    "text":        "#F3F4F6",
    "text_mid":    "#CBD5E0",
    "text_sub":    "#718096",
    "primary":     "#818CF8",
    "primary_hi":  "#A5B4FC",
    "novelty":      "#A78BFA",
    "demand":       "#60A5FA",
    "monetization": "#34D399",
    "feasibility":  "#FBBF24",
    "score_hi":  "#34D399",
    "score_mid": "#60A5FA",
    "score_lo":  "#FBBF24",
    "score_bad": "#94A3B8",
    "danger":    "#F87171",
}

DIM_COLORS = {
    "novelty":      COLORS["novelty"],
    "demand":       COLORS["demand"],
    "monetization": COLORS["monetization"],
    "feasibility":  COLORS["feasibility"],
}


def score_color(score: int | None) -> str:
    if score is None:
        return COLORS["score_bad"]
    if score >= 80:
        return COLORS["score_hi"]
    if score >= 70:
        return COLORS["score_mid"]
    if score >= 60:
        return COLORS["score_lo"]
    return COLORS["score_bad"]


# ───── Global CSS ────────────────────────────────────────────────────────
CSS = f"""
<style>
:root {{
  --bg: {COLORS['bg']};
  --sidebar-bg: {COLORS['sidebar_bg']};
  --card: {COLORS['card']};
  --card-hover: {COLORS['card_hover']};
  --border: {COLORS['border']};
  --border-soft: {COLORS['border_soft']};
  --divider: {COLORS['divider']};
  --text: {COLORS['text']};
  --text-mid: {COLORS['text_mid']};
  --text-sub: {COLORS['text_sub']};
  --primary: {COLORS['primary']};
}}

html, body, [class*="css"] {{
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Roboto, sans-serif !important;
  -webkit-font-smoothing: antialiased;
  color: var(--text);
}}

/* Hide Streamlit's own header chrome */
header [data-testid="stDecoration"],
header [data-testid="stToolbar"] {{
  display: none !important;
}}

/* ───── Sidebar: always visible, clearly differentiated from body ──── */
section[data-testid="stSidebar"],
div[data-testid="stSidebar"] {{
  background: var(--sidebar-bg) !important;
  border-right: 1px solid var(--border) !important;
  min-width: 232px !important;
  width: 232px !important;
  visibility: visible !important;
  transform: none !important;
}}
section[data-testid="stSidebar"] > div,
div[data-testid="stSidebar"] > div {{
  background: var(--sidebar-bg) !important;
  padding-top: 16px;
}}

/* Hide every collapse/expand affordance — sidebar stays pinned */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
button[kind="header"] {{
  display: none !important;
}}

/* Brand header inside sidebar */
[data-testid="stSidebar"] .brand {{
  display: flex; align-items: center; gap: 10px;
  padding: 6px 8px 20px 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
}}
[data-testid="stSidebar"] .brand-mark {{
  font-size: 24px;
  background: linear-gradient(135deg, #818CF8, #C084FC);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  filter: drop-shadow(0 2px 8px rgba(168,85,247,0.25));
}}
[data-testid="stSidebar"] .brand-name {{
  font-weight: 700; font-size: 17px; letter-spacing: -0.015em;
  color: var(--text);
}}

/* Nav links */
[data-testid="stSidebar"] .nav-group {{
  display: flex; flex-direction: column; gap: 2px;
}}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {{
  border-radius: 8px;
  padding: 8px 10px !important;
  color: var(--text-mid) !important;
  transition: background 0.15s ease, color 0.15s ease;
  text-decoration: none;
}}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {{
  background: var(--card-hover) !important;
  color: var(--text) !important;
}}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] p {{
  color: inherit !important;
  font-weight: 500;
}}
[data-testid="stSidebar"] .sidebar-footer {{
  margin-top: 32px; padding-top: 14px;
  border-top: 1px solid var(--border);
}}
[data-testid="stSidebar"] .sidebar-footer p,
[data-testid="stSidebar"] .sidebar-footer div {{
  color: var(--text-sub) !important;
  font-size: 12px;
}}

/* ───── Main content area ────────────────────────────────────────────── */
.main .block-container {{
  padding-top: 28px; padding-bottom: 56px;
  padding-left: 36px !important; padding-right: 36px !important;
  max-width: 1480px;
}}

/* Typography */
h1, h2, h3, h4 {{ color: var(--text) !important; }}
h1 {{ font-weight: 700 !important; letter-spacing: -0.025em !important; }}
h2 {{ font-weight: 600 !important; letter-spacing: -0.02em !important; }}
h3 {{ font-weight: 600 !important; letter-spacing: -0.015em !important; }}

p, li, label, span {{ color: var(--text); }}
[data-testid="stCaptionContainer"] p,
[data-testid="stCaptionContainer"] {{ color: var(--text-sub) !important; }}

/* Tabular numerals everywhere numbers matter */
.stat-card-val, .run-stat-val, .score-headline,
[data-testid="stMetricValue"] {{
  font-feature-settings: 'tnum' 1, 'lnum' 1;
}}

/* Hero header */
.hero {{
  margin: 0 0 28px 0;
  padding: 4px 0 18px 0;
  border-bottom: 1px solid var(--border-soft);
}}
.hero-title {{
  font-size: 34px; font-weight: 700;
  letter-spacing: -0.03em; line-height: 1.1;
  background: linear-gradient(110deg, #F3F4F6 0%, #C7D2FE 70%, #A5B4FC 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  display: inline-block;
}}
.hero-sub {{
  color: var(--text-sub); font-size: 13px;
  margin-top: 4px; letter-spacing: 0.01em;
}}

/* Section headers (replaces ad-hoc h3 + caption combos) */
.section-head {{
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 12px; margin: 0 0 14px 0;
  position: relative;
}}
.section-title {{
  font-size: 16px; font-weight: 600; letter-spacing: -0.015em;
  color: var(--text);
}}
.section-sub {{
  font-size: 12px; color: var(--text-sub); font-weight: 500;
}}
.section-link {{
  font-size: 12px; color: var(--primary); text-decoration: none;
  font-weight: 500;
}}
.section-link:hover {{ color: var(--primary_hi, #A5B4FC); }}

.section-head.linked {{
  position: relative;
  padding: 6px 10px; margin: -6px -10px 8px -10px;
  border-radius: 8px;
  transition: background 0.15s ease;
  cursor: pointer;
}}
.section-head.linked:hover {{ background: var(--card); }}
.section-head.linked:hover .section-title {{ color: var(--primary_hi, #A5B4FC); }}
.section-chevron {{
  margin-left: auto;
  color: var(--text-sub); font-size: 14px;
  transition: transform 0.15s ease, color 0.15s ease;
}}
.section-head.linked:hover .section-chevron {{
  color: var(--primary); transform: translateX(3px);
}}

/* Run card hover (overlay-link makes the whole card clickable) */
.run-card.is-link {{ cursor: pointer; transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease; }}
.run-card.is-link:hover {{
  border-color: var(--primary);
  transform: translateY(-1px);
  box-shadow: 0 12px 32px rgba(129,140,248,0.14);
}}
.run-cta-inline {{
  display: inline-flex; align-items: center; gap: 4px;
  align-self: flex-start;
  font-size: 13px; font-weight: 600;
  color: var(--primary);
  margin-top: 4px;
}}
.run-card.is-link:hover .run-cta-inline {{
  color: var(--primary_hi, #A5B4FC);
}}

/* Custom stat cards (replaces st.metric on Home) */
.stat-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px 18px;
  position: relative; overflow: hidden;
  transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
  min-height: 96px;
  display: block;
}}
.stat-card:hover {{ border-color: var(--primary); transform: translateY(-1px); }}
.stat-card.is-link {{ cursor: pointer; }}
.stat-card.is-link:hover {{
  border-color: var(--accent, var(--primary));
  box-shadow: 0 8px 24px rgba(129,140,248,0.12);
}}
.stat-card.is-link:hover .stat-card-chevron {{
  opacity: 1; transform: translateX(0);
  color: var(--accent, var(--primary));
}}
.stat-card-chevron {{
  position: absolute; right: 14px; bottom: 12px;
  font-size: 14px; color: var(--text-sub);
  opacity: 0; transform: translateX(-4px);
  transition: opacity 0.18s ease, transform 0.18s ease, color 0.18s ease;
  z-index: 1;
}}

/* Whole-card overlay link — sits above content, captures clicks. Used by
   stat-card / section-head / run-card so we don't wrap block children in <a>
   (which Streamlit's markdown renderer breaks). */
.card-overlay {{
  position: absolute; inset: 0;
  z-index: 2;
  text-decoration: none !important;
  border-radius: inherit;
  cursor: pointer;
}}
.stat-card::before {{
  content: ''; position: absolute; left: 0; top: 0; bottom: 0;
  width: 3px; background: var(--accent, var(--primary));
  opacity: 0.85;
}}
.stat-card-label {{
  font-size: 11px; font-weight: 600; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--text-sub);
}}
.stat-card-val {{
  font-size: 30px; font-weight: 700; letter-spacing: -0.025em;
  color: var(--text); line-height: 1.1; margin-top: 6px;
  white-space: nowrap;
}}
.stat-card-sub {{
  font-size: 11px; color: var(--text-sub); margin-top: 4px;
  font-weight: 500;
}}

/* Latest run card */
.run-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px 20px;
  display: flex; flex-direction: column; gap: 12px;
  position: relative;
}}
.run-card-head {{
  display: flex; align-items: center; justify-content: space-between;
}}
.run-id {{
  font-size: 15px; font-weight: 700; color: var(--text);
  letter-spacing: -0.01em;
}}
.run-status {{
  font-size: 10px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 3px 9px; border-radius: 999px;
}}
.run-status.ok  {{ background: rgba(52,211,153,0.16); color: #6EE7B7; }}
.run-status.err {{ background: rgba(248,113,113,0.16); color: #FCA5A5; }}
.run-status.neu {{ background: rgba(148,163,184,0.16); color: #CBD5E0; }}
.run-time {{
  font-size: 12px; color: var(--text-sub); font-feature-settings: 'tnum' 1;
}}
.run-grid {{
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 10px; margin-top: 4px;
}}
.run-stat {{
  background: var(--card-hover);
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  padding: 10px 12px;
}}
.run-stat-label {{
  font-size: 10px; font-weight: 600; letter-spacing: 0.05em;
  text-transform: uppercase; color: var(--text-sub);
}}
.run-stat-val {{
  font-size: 20px; font-weight: 700; color: var(--text);
  letter-spacing: -0.02em; line-height: 1.1; margin-top: 4px;
  white-space: nowrap;
}}
.run-cta {{
  display: inline-flex; align-items: center; gap: 4px;
  margin-top: 4px; padding: 9px 14px;
  background: var(--primary); color: #0B0F17 !important;
  border-radius: 9px; text-decoration: none;
  font-size: 13px; font-weight: 600;
  width: fit-content;
  transition: background 0.15s ease;
}}
.run-cta:hover {{ background: var(--primary_hi, #A5B4FC); }}

/* Run launcher banner */
.runner {{
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px;
  padding: 14px 18px;
  border-radius: 14px;
  border: 1px solid var(--border);
  margin-bottom: 14px;
  transition: border-color 0.15s ease;
}}
.runner.idle {{
  background: linear-gradient(120deg,
    rgba(129,140,248,0.10) 0%,
    rgba(168,85,247,0.06) 100%);
  border-color: rgba(129,140,248,0.35);
}}
.runner.running {{
  background: linear-gradient(120deg,
    rgba(251,191,36,0.10) 0%,
    rgba(248,113,113,0.05) 100%);
  border-color: rgba(251,191,36,0.40);
}}
.runner-left {{
  display: flex; align-items: center; gap: 14px;
}}
.runner-icon {{ font-size: 22px; }}
.runner-text {{ display: flex; flex-direction: column; gap: 2px; }}
.runner-title {{
  font-size: 14px; font-weight: 700; letter-spacing: -0.01em;
  color: var(--text);
}}
.runner-meta {{
  font-size: 12px; color: var(--text-sub); font-weight: 500;
}}
.runner-cta {{
  display: inline-flex; align-items: center; gap: 4px;
  padding: 9px 16px;
  background: var(--primary); color: #0B0F17 !important;
  border-radius: 9px; text-decoration: none;
  font-size: 13px; font-weight: 700;
  transition: transform 0.15s ease, background 0.15s ease;
}}
.runner-cta:hover {{ background: var(--primary_hi, #A5B4FC); transform: translateX(2px); }}
.runner-cta.secondary {{
  background: rgba(251,191,36,0.16); color: #FCD34D !important;
  border: 1px solid rgba(251,191,36,0.4);
}}
.runner-cta.secondary:hover {{ background: rgba(251,191,36,0.24); }}

.runner-pulse {{
  display: inline-block;
  width: 10px; height: 10px;
  border-radius: 50%;
  background: #FBBF24;
  box-shadow: 0 0 0 0 rgba(251,191,36,0.7);
  animation: pulse-amber 1.5s infinite;
}}
@keyframes pulse-amber {{
  0% {{ box-shadow: 0 0 0 0 rgba(251,191,36,0.7); }}
  70% {{ box-shadow: 0 0 0 12px rgba(251,191,36,0); }}
  100% {{ box-shadow: 0 0 0 0 rgba(251,191,36,0); }}
}}

/* Live monitor (in-flight run summary) */
.live-card {{
  background: linear-gradient(120deg,
    rgba(251,191,36,0.08) 0%,
    rgba(168,85,247,0.06) 100%);
  border: 1px solid rgba(251,191,36,0.32);
  border-radius: 14px;
  padding: 14px 18px;
  margin-bottom: 14px;
}}
.live-card-head {{
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 6px;
}}
.live-card-label {{
  font-size: 11px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; color: #FCD34D;
}}
.live-card-turn {{
  margin-left: auto;
  font-size: 11px; color: var(--text-sub);
  background: var(--card-hover);
  padding: 2px 8px; border-radius: 999px;
  border: 1px solid var(--border);
}}
.live-pulse-dot {{
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #FBBF24;
  animation: pulse-amber 1.5s infinite;
}}
.live-current-row {{
  display: flex; align-items: center; gap: 12px;
  flex-wrap: wrap;
}}
.live-current-icon {{ font-size: 22px; line-height: 1; }}
.live-current-tool {{
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 15px; font-weight: 700;
  color: var(--text);
  background: var(--card);
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
}}
.live-current-detail {{
  font-size: 14px; color: var(--text-mid);
  font-family: 'SF Mono', Menlo, monospace;
  word-break: break-word;
}}

.live-feed {{
  display: flex; flex-direction: column; gap: 4px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px 12px;
}}
.live-feed-row {{
  display: grid;
  grid-template-columns: 64px 18px auto 1fr;
  gap: 8px; align-items: center;
  padding: 6px 4px;
  border-radius: 6px;
  font-size: 12.5px;
  transition: background 0.15s ease;
}}
.live-feed-row:hover {{ background: var(--card-hover); }}
.live-feed-row + .live-feed-row {{ border-top: 1px dashed var(--border-soft); }}
.live-feed-time {{
  color: var(--text-sub); font-size: 11px;
  font-feature-settings: 'tnum' 1;
}}
.live-feed-icon {{ font-size: 14px; line-height: 1; }}
.live-feed-tool {{
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 12px; font-weight: 600;
  color: var(--primary_hi, #A5B4FC);
}}
.live-feed-detail {{
  color: var(--text-mid);
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 12px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}

.live-thought {{
  margin-top: 12px;
  padding: 10px 14px;
  background: var(--card);
  border: 1px solid var(--border);
  border-left: 3px solid var(--primary);
  border-radius: 8px;
}}
.live-thought-label {{
  font-size: 10px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--primary);
}}
.live-thought-text {{
  margin-top: 4px;
  font-size: 13px; line-height: 1.55;
  color: var(--text-mid);
}}

.live-saved {{
  display: flex; flex-direction: column; gap: 6px;
}}
.live-saved-row {{
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 14px;
  text-decoration: none !important;
  transition: border-color 0.15s ease, transform 0.15s ease;
}}
.live-saved-row:hover {{
  border-color: var(--primary);
  transform: translateX(2px);
}}
.live-saved-title {{
  font-size: 13px; font-weight: 600; color: var(--text);
  line-height: 1.3;
}}
.live-saved-score {{
  font-size: 12px; font-weight: 700;
  color: #0B0F17;
  padding: 3px 9px; border-radius: 999px;
  min-width: 36px; text-align: center;
  font-feature-settings: 'tnum' 1;
}}

/* ───── Modern log feed (in-flight monitor) ─────────────────────────── */
.log-feed {{
  display: flex; flex-direction: column;
  background: #0F1421;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 8px;
  font-family: 'JetBrains Mono', 'SF Mono', Menlo, monospace;
  overflow: hidden;
}}
.log-row {{
  position: relative;
  display: grid;
  grid-template-columns: 3px 78px 56px 18px auto 1fr;
  gap: 10px; align-items: center;
  padding: 8px 10px 8px 6px;
  border-radius: 8px;
  font-size: 12.5px;
  transition: background 0.15s ease;
  animation: log-row-in 0.35s ease-out;
}}
.log-row:hover {{ background: rgba(129,140,248,0.06); }}
.log-row.is-latest {{
  background: rgba(129,140,248,0.06);
  box-shadow: inset 0 0 0 1px rgba(129,140,248,0.18);
}}
.log-bar {{
  align-self: stretch;
  width: 3px; border-radius: 2px;
  background: var(--primary);
}}
.log-row[data-accent="demand"]       .log-bar {{ background: {COLORS['demand']}; }}
.log-row[data-accent="novelty"]      .log-bar {{ background: {COLORS['novelty']}; }}
.log-row[data-accent="monetization"] .log-bar {{ background: {COLORS['monetization']}; }}
.log-row[data-accent="score_hi"]     .log-bar {{ background: {COLORS['score_hi']}; }}
.log-time {{
  color: var(--text-mid); font-size: 11.5px; font-weight: 600;
  font-feature-settings: 'tnum' 1; letter-spacing: 0.02em;
}}
.log-ago {{
  color: var(--text-sub); font-size: 10.5px;
  font-feature-settings: 'tnum' 1;
  text-align: right;
}}
.log-icon {{ font-size: 14px; line-height: 1; }}
.log-tool {{
  font-size: 12px; font-weight: 700;
  color: var(--text);
  letter-spacing: 0.005em;
}}
.log-row[data-accent="demand"]       .log-tool {{ color: {COLORS['demand']}; }}
.log-row[data-accent="novelty"]      .log-tool {{ color: {COLORS['novelty']}; }}
.log-row[data-accent="monetization"] .log-tool {{ color: {COLORS['monetization']}; }}
.log-row[data-accent="score_hi"]     .log-tool {{ color: {COLORS['score_hi']}; }}
.log-detail {{
  color: var(--text-mid);
  font-size: 12px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
@keyframes log-row-in {{
  from {{ opacity: 0; transform: translateY(-4px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}

.log-skeleton {{
  display: flex; flex-direction: column; gap: 6px;
  padding: 4px 6px;
}}
.log-skeleton-row {{
  height: 28px; border-radius: 8px;
  background: linear-gradient(90deg,
    rgba(129,140,248,0.04) 0%,
    rgba(129,140,248,0.12) 50%,
    rgba(129,140,248,0.04) 100%);
  background-size: 200% 100%;
  animation: shimmer 1.4s ease-in-out infinite;
}}
.log-skeleton-row:nth-child(2) {{ animation-delay: 0.2s; opacity: 0.85; }}
.log-skeleton-row:nth-child(3) {{ animation-delay: 0.4s; opacity: 0.7; }}
.log-skeleton-row:nth-child(4) {{ animation-delay: 0.6s; opacity: 0.55; }}
@keyframes shimmer {{
  0%   {{ background-position: -200% 0; }}
  100% {{ background-position:  200% 0; }}
}}
.log-empty-hint {{
  text-align: center;
  font-family: -apple-system, 'Inter', sans-serif;
  font-size: 12px; color: var(--text-sub);
  padding: 8px 0 4px;
}}

/* ───── Booting skeleton (immediate post-launch feedback) ────────────── */
.booting {{
  background: linear-gradient(120deg,
    rgba(129,140,248,0.10) 0%,
    rgba(168,85,247,0.06) 100%);
  border: 1px solid rgba(129,140,248,0.30);
  border-radius: 14px;
  padding: 18px;
  margin-bottom: 14px;
}}
.booting-head {{
  display: flex; align-items: center; gap: 14px;
  margin-bottom: 14px;
}}
.booting-spinner {{
  width: 22px; height: 22px;
  border-radius: 50%;
  border: 2.5px solid rgba(129,140,248,0.25);
  border-top-color: var(--primary);
  animation: spin 0.8s linear infinite;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
.booting-title {{
  font-size: 14px; font-weight: 700; color: var(--text);
  letter-spacing: -0.01em;
}}
.booting-meta {{
  font-size: 12px; color: var(--text-sub); margin-top: 2px;
  font-feature-settings: 'tnum' 1;
}}
.booting-steps {{
  display: flex; flex-direction: column; gap: 6px;
  margin: 10px 0 14px;
  padding: 10px 14px;
  background: rgba(11,15,23,0.45);
  border-radius: 10px;
  border: 1px solid var(--border-soft);
}}
.booting-step {{
  font-size: 12.5px; color: var(--text-sub);
  font-family: 'SF Mono', Menlo, monospace;
}}
.booting-step.done   {{ color: {COLORS['score_hi']}; }}
.booting-step.active {{ color: var(--primary); animation: pulse-fade 1.4s ease-in-out infinite; }}
@keyframes pulse-fade {{
  0%, 100% {{ opacity: 0.9; }}
  50%      {{ opacity: 0.55; }}
}}

.live-card.warming {{
  background: linear-gradient(120deg,
    rgba(129,140,248,0.10) 0%,
    rgba(168,85,247,0.06) 100%);
  border-color: rgba(129,140,248,0.30);
}}
.live-warming-shimmer {{
  height: 8px; border-radius: 4px;
  background: linear-gradient(90deg,
    rgba(129,140,248,0.08) 0%,
    rgba(129,140,248,0.22) 50%,
    rgba(129,140,248,0.08) 100%);
  background-size: 200% 100%;
  animation: shimmer 1.4s ease-in-out infinite;
  margin-top: 4px;
}}

/* ───── Hero CTA (prominent "Launch new run" button) ────────────────── */
.hero-cta-wrap {{ margin: 8px 0 18px; }}
.hero-cta-wrap [data-testid="stButton"] > button {{
  height: 64px !important;
  font-size: 17px !important;
  font-weight: 800 !important;
  letter-spacing: -0.005em;
  background: linear-gradient(135deg, #818CF8 0%, #A78BFA 50%, #C084FC 100%) !important;
  color: #0B0F17 !important;
  border: 1px solid rgba(129,140,248,0.55) !important;
  box-shadow:
    0 8px 24px -8px rgba(129,140,248,0.55),
    inset 0 1px 0 rgba(255,255,255,0.18) !important;
  transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease !important;
}}
.hero-cta-wrap [data-testid="stButton"] > button:hover {{
  transform: translateY(-1px);
  box-shadow:
    0 12px 32px -8px rgba(129,140,248,0.7),
    inset 0 1px 0 rgba(255,255,255,0.22) !important;
  filter: brightness(1.08);
}}
.hero-cta-wrap [data-testid="stButton"] > button:active {{
  transform: translateY(0);
  filter: brightness(0.96);
}}

.compact-cta-wrap [data-testid="stButton"] > button {{
  font-weight: 700 !important;
  background: var(--primary) !important;
  color: #0B0F17 !important;
}}

/* ───── Launch dialog (inside @st.dialog) ───────────────────────────── */
.dialog-intro {{
  font-size: 13.5px; line-height: 1.55;
  color: var(--text-mid);
  padding: 4px 0 14px;
  border-bottom: 1px solid var(--border-soft);
  margin-bottom: 14px;
}}
.form-step-label {{
  font-size: 11px; font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--primary_hi, #A5B4FC);
  margin: 14px 0 6px;
}}
.form-step-hint {{
  font-size: 10.5px; font-weight: 500;
  letter-spacing: 0.04em; text-transform: none;
  color: var(--text-sub);
  margin-left: 6px;
}}
.preset-desc {{
  font-size: 12px; color: var(--text-sub);
  padding: 6px 12px;
  background: rgba(129,140,248,0.06);
  border: 1px solid rgba(129,140,248,0.18);
  border-radius: 8px;
  margin: 4px 0 4px;
  line-height: 1.45;
}}
.advanced-block-intro {{
  font-size: 12px; color: var(--text-sub);
  padding: 8px 12px;
  background: var(--card);
  border: 1px dashed var(--border);
  border-radius: 10px;
  margin: 10px 0 12px;
  line-height: 1.5;
}}
/* Make expander headers inside the dialog visually scannable */
[data-testid="stDialog"] [data-testid="stExpander"] details > summary {{
  font-size: 13px !important;
  font-weight: 600 !important;
  color: var(--text) !important;
  padding: 10px 14px !important;
  background: var(--card) !important;
  border-radius: 10px !important;
  border: 1px solid var(--border) !important;
}}
[data-testid="stDialog"] [data-testid="stExpander"] details[open] > summary {{
  border-bottom-left-radius: 0 !important;
  border-bottom-right-radius: 0 !important;
  border-color: rgba(129,140,248,0.35) !important;
}}
.dialog-run-cta {{
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border-soft);
}}
.dialog-run-cta [data-testid="stButton"] > button {{
  height: 52px !important;
  font-size: 15px !important;
  font-weight: 800 !important;
  background: linear-gradient(135deg, #818CF8 0%, #A78BFA 100%) !important;
  color: #0B0F17 !important;
  border: 1px solid rgba(129,140,248,0.5) !important;
  box-shadow: 0 6px 18px -6px rgba(129,140,248,0.55) !important;
}}
.dialog-run-cta [data-testid="stButton"] > button:hover {{
  filter: brightness(1.08);
}}

/* ───── Auto-fill ideas grid (replaces st.columns + pad-empty hack) ──── */
.ideas-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
  gap: 14px;
  margin-top: 14px;
}}
/* The card itself is already styled via .idea-card; this just lays them out. */

/* ───── Filter bar polish (Ideas page) ──────────────────────────────── */
.filter-summary {{
  display: flex; align-items: center; gap: 8px;
  font-size: 12.5px;
  color: var(--text-sub);
  margin: 8px 0 4px;
}}
.filter-summary strong {{
  color: var(--text-mid); font-weight: 600;
}}
.filter-quick-label {{
  font-size: 11px; font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--text-sub);
  margin: 4px 0 6px;
}}

/* ───── Auth redirect transition (post-login spinner) ───────────────── */
.auth-redirect {{
  display: flex; flex-direction: column; align-items: center;
  gap: 14px;
  margin: 80px auto;
  max-width: 380px;
  padding: 36px 28px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  text-align: center;
}}
.auth-redirect-spinner {{
  width: 32px; height: 32px;
  border-radius: 50%;
  border: 3px solid rgba(129,140,248,0.20);
  border-top-color: var(--primary);
  animation: spin 0.7s linear infinite;
}}
.auth-redirect-text {{
  font-size: 14px; font-weight: 600;
  color: var(--text-mid);
  letter-spacing: -0.005em;
}}

/* ───── Auth: user pill + login form polish ─────────────────────────── */
.auth-user-pill {{
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px;
  margin: 14px 8px 8px 8px;
  background: rgba(129,140,248,0.08);
  border: 1px solid rgba(129,140,248,0.2);
  border-radius: 10px;
  font-size: 12.5px; color: var(--text);
}}
.auth-user-dot {{
  width: 8px; height: 8px; border-radius: 50%;
  background: {COLORS['score_hi']};
  box-shadow: 0 0 0 0 rgba(52,211,153,0.6);
  animation: pulse-amber 2s infinite;
}}
.auth-user-name {{
  font-weight: 600;
}}
/* Center the login form in main area */
[data-testid="stMainBlockContainer"] form[data-testid="stForm"] {{
  max-width: 380px;
  margin: 80px auto;
  padding: 28px 28px 22px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
}}

/* ───── Cap pill (per-user daily quota) ─────────────────────────────── */
.cap-pill {{
  display: inline-block;
  padding: 7px 12px;
  margin: 8px 0 4px;
  font-size: 12px; font-weight: 500;
  color: var(--text-mid);
  background: rgba(96,165,250,0.08);
  border: 1px solid rgba(96,165,250,0.20);
  border-radius: 999px;
}}
.cap-pill.is-blocked {{
  color: {COLORS['danger']};
  background: rgba(248,113,113,0.10);
  border-color: rgba(248,113,113,0.32);
  font-weight: 600;
}}

/* ───── Page header with right-aligned new-run button ───────────────── */
.page-head {{
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: 24px;
  padding: 4px 0 18px;
  border-bottom: 1px solid var(--border-soft);
  margin-bottom: 18px;
}}
.page-head-text {{ display: flex; flex-direction: column; gap: 4px; }}
.page-head-title {{
  font-size: 28px; font-weight: 800; letter-spacing: -0.02em;
  color: var(--text);
}}
.page-head-sub {{
  font-size: 13px; color: var(--text-sub);
}}

/* Empty states */
.empty-state {{
  background: var(--card);
  border: 1px dashed var(--border);
  border-radius: 14px;
  padding: 32px 24px;
  text-align: center;
  color: var(--text-sub);
}}
.empty-state.small {{ padding: 18px; }}
.empty-emoji {{ font-size: 32px; margin-bottom: 8px; }}
.empty-title {{
  font-size: 14px; font-weight: 600; color: var(--text-mid);
  margin-bottom: 4px;
}}
.empty-body {{
  font-size: 12px; color: var(--text-sub); line-height: 1.55;
}}

/* Legacy st.metric (kept for other pages) */
[data-testid="stMetric"] {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  transition: border-color 0.15s ease;
}}
[data-testid="stMetric"]:hover {{
  border-color: var(--primary);
}}
[data-testid="stMetricLabel"] p {{
  color: var(--text-sub) !important;
  font-size: 11px !important;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}
[data-testid="stMetricValue"] {{
  font-weight: 700 !important;
  font-size: 26px !important;
  letter-spacing: -0.025em;
  color: var(--text) !important;
  line-height: 1.1 !important;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
[data-testid="stMetricDelta"] {{
  color: var(--text-sub) !important;
  font-size: 11px !important;
}}

/* Containers with border (st.container(border=True)) */
[data-testid="stVerticalBlockBorderWrapper"] {{
  border-radius: 12px !important;
  border-color: var(--border) !important;
  background: var(--card) !important;
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
}}
[data-testid="stVerticalBlockBorderWrapper"]:hover {{
  border-color: var(--primary) !important;
}}

/* Dataframes */
[data-testid="stDataFrame"] {{
  border-radius: 10px; overflow: hidden;
  border: 1px solid var(--border) !important;
  background: var(--card);
}}

/* Tabs */
[data-testid="stTabs"] button[role="tab"] {{
  font-weight: 500;
  color: var(--text-mid);
  transition: color 0.15s ease;
}}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
  color: var(--primary) !important;
}}

/* Expanders */
[data-testid="stExpander"] {{
  border-radius: 10px !important;
  border: 1px solid var(--border) !important;
  background: var(--card) !important;
}}
[data-testid="stExpander"] summary {{
  font-weight: 500;
  color: var(--text) !important;
}}

/* Plotly chart background */
.js-plotly-plot .plotly {{
  background: transparent !important;
}}

/* Code inline & blocks */
code {{
  background: var(--card-hover) !important;
  color: var(--primary_hi, #A5B4FC) !important;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 90%;
}}
pre code {{
  background: var(--card) !important;
  border: 1px solid var(--border);
}}

/* Sliders, inputs */
[data-baseweb="slider"] div[role="slider"] {{
  background: var(--primary) !important;
}}
[data-baseweb="input"] input,
[data-baseweb="select"] div {{
  background: var(--card) !important;
  color: var(--text) !important;
}}

/* Multiselect: when unfocused, BaseWeb gives the value container a fixed
   single-row height with `overflow: hidden`, so any pills that wrap to a
   second row get their top half clipped until the user clicks the field.
   Force the container to grow with its content and stop pills from
   truncating (truncation also triggers a mispositioned hover tooltip that
   looks like the first pill is "cut"). */
[data-baseweb="select"] > div,
[data-baseweb="select"] > div > div {{
  height: auto !important;
  max-height: none !important;
  align-content: flex-start !important;
}}
[data-baseweb="select"] [data-baseweb="tag"] {{
  max-width: none !important;
  margin: 4px 0 4px 8px !important;
}}
[data-baseweb="select"] [data-baseweb="tag"] > div,
[data-baseweb="select"] [data-baseweb="tag"] span {{
  max-width: none !important;
  overflow: visible !important;
  text-overflow: clip !important;
}}
/* Strip any leftover input border/underline that overlaps the first pill
   when the field is unfocused. */
[data-baseweb="select"] input {{
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  text-decoration: none !important;
  background: transparent !important;
  caret-color: var(--primary);
}}

/* Alert / info / success / warning boxes */
[data-testid="stAlertContainer"] {{
  background: var(--card) !important;
  border: 1px solid var(--border) !important;
  border-radius: 10px;
}}

/* ───── Custom components ────────────────────────────────────────────── */

.idea-card {{
  display: block; text-decoration: none; color: inherit;
  margin-bottom: 14px;
}}
.idea-card:hover {{ text-decoration: none; }}
.idea-card-inner {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px 20px;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease, background 0.18s ease;
  position: relative;
}}
.idea-card:hover .idea-card-inner {{
  border-color: var(--primary);
  background: var(--card-hover);
  box-shadow: 0 12px 32px rgba(129, 140, 248, 0.18);
  transform: translateY(-2px);
}}
.idea-head {{
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 12px; margin-bottom: 6px;
}}
.idea-title {{
  font-weight: 600; font-size: 15px; line-height: 1.3;
  color: var(--text); letter-spacing: -0.015em;
}}
.score-badge {{
  font-weight: 600; font-size: 13px;
  color: #0B0F17;
  padding: 4px 10px; border-radius: 999px;
  min-width: 40px; text-align: center;
  flex-shrink: 0;
}}
.idea-meta {{
  font-size: 11px; color: var(--text-sub);
  margin-bottom: 14px;
  display: flex; gap: 6px; flex-wrap: wrap; align-items: center;
}}
.idea-meta .pill {{
  padding: 2px 8px; border-radius: 999px;
  background: var(--card-hover);
  color: var(--text-mid);
  font-weight: 500;
  border: 1px solid var(--border);
}}
.bars {{ margin: 12px 0; }}
.bar-row {{
  display: grid; grid-template-columns: 48px 1fr 28px;
  gap: 8px; align-items: center; margin: 5px 0;
  font-size: 10.5px; color: var(--text-sub);
  letter-spacing: 0.01em;
  cursor: help;
}}
.bar-label {{ font-weight: 600; }}
.bar-track {{
  height: 5px; background: var(--card-hover);
  border-radius: 3px; overflow: hidden;
  border: 1px solid var(--border-soft);
}}
.bar-fill {{ height: 100%; border-radius: 3px; transition: width 0.3s ease; }}
.bar-val {{ text-align: right; font-weight: 600; color: var(--text-mid); }}
.idea-concept {{
  font-size: 12.5px; color: var(--text-mid); line-height: 1.55;
  margin-top: 10px;
}}

/* Stage stepper */
.stepper {{
  display: flex; gap: 4px; margin: 16px 0 24px 0;
}}
.stepper-step {{
  flex: 1; padding: 8px 10px; border-radius: 6px;
  text-align: center; font-size: 12px; font-weight: 600;
  letter-spacing: 0.02em; text-transform: capitalize;
  transition: all 0.15s ease;
}}
.stepper-step.done {{ background: #065F46; color: #6EE7B7; }}
.stepper-step.current {{
  background: var(--primary); color: #0B0F17;
  box-shadow: 0 0 0 1px rgba(129,140,248,0.4), 0 4px 16px rgba(129,140,248,0.25);
}}
.stepper-step.todo {{ background: var(--card); color: var(--text-sub); border: 1px solid var(--border); }}

/* Score headline on idea detail */
.score-headline {{ text-align: right; }}
.score-headline .score-num {{
  font-size: 44px; font-weight: 700; letter-spacing: -0.03em;
  line-height: 1;
}}
.score-headline .score-total {{
  color: var(--text-sub); font-size: 14px; margin-left: 4px;
}}

/* Pros/Cons/etc list cards */
.list-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 8px;
  font-size: 13px; line-height: 1.55; color: var(--text-mid);
}}
.list-card.pro {{ border-left: 3px solid {COLORS['score_hi']}; }}
.list-card.con {{ border-left: 3px solid {COLORS['danger']}; }}
.list-card.diff {{ border-left: 3px solid {COLORS['primary']}; }}
.list-card.risk {{ border-left: 3px solid {COLORS['score_lo']}; }}

/* Variant markers */
.variant-badge {{
  background: rgba(168, 85, 247, 0.15);
  color: #DDD6FE;
  border: 1px solid rgba(168, 85, 247, 0.35);
  font-size: 10px; font-weight: 700; letter-spacing: 0.04em;
  padding: 2px 8px; border-radius: 999px;
  text-transform: uppercase;
}}
.idea-card-inner.is-variant {{
  border-left: 3px solid #A855F7;
}}
.variant-from {{
  font-size: 11px; color: var(--text-sub);
  margin-top: 6px; font-style: italic;
}}
.variant-pivot-note {{
  font-size: 11.5px; color: var(--text-mid);
  margin-top: 4px; line-height: 1.4;
  padding: 4px 8px;
  background: rgba(168, 85, 247, 0.08);
  border-radius: 4px;
  border-left: 2px solid rgba(168, 85, 247, 0.4);
}}
.breadcrumb-parent {{
  display: inline-block;
  padding: 6px 12px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-mid);
  text-decoration: none;
  font-size: 13px;
  margin-bottom: 12px;
  transition: border-color 0.15s ease, color 0.15s ease;
}}
.breadcrumb-parent:hover {{
  border-color: #A855F7;
  color: var(--text);
}}
.breadcrumb-parent .arrow {{ color: #A855F7; margin-right: 4px; }}

.comp-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 10px;
}}
.comp-card .comp-name {{
  font-weight: 600; font-size: 14px; color: var(--text);
  margin-bottom: 4px;
}}
.comp-card .comp-name a {{ color: var(--primary); text-decoration: none; }}
.comp-card .comp-name a:hover {{ text-decoration: underline; }}
.comp-card .comp-meta {{
  font-size: 12px; color: var(--text-sub);
  margin-bottom: 6px;
  display: flex; gap: 10px; flex-wrap: wrap;
}}
.comp-card .comp-note {{
  font-size: 12px; color: var(--text-mid); line-height: 1.55;
}}

/* Idea Lab — chat bubbles */
.lab-wrap {{ padding-bottom: 80px; }}
.lab-msg {{
  margin: 10px 0;
}}
.lab-msg .bubble {{
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 14px; line-height: 1.55;
  color: var(--text);
}}
.lab-msg.user .bubble {{
  background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%);
  color: white;
  border-bottom-right-radius: 4px;
  margin-left: auto;
  max-width: 80%;
}}
.lab-msg.assistant .bubble {{
  background: var(--card);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
  max-width: 90%;
}}
.lab-msg .bubble-meta {{
  font-size: 10px; color: var(--text-sub);
  margin-top: 4px;
}}
.lab-tool-call {{
  background: var(--card-hover);
  border: 1px solid var(--border);
  border-left: 3px solid var(--primary);
  border-radius: 8px;
  padding: 8px 12px;
  margin: 4px 0;
  font-size: 12px; color: var(--text-mid);
  font-family: 'SF Mono', 'Monaco', Menlo, monospace;
}}
.lab-tool-call .tool-name {{
  color: var(--primary); font-weight: 600;
}}

/* Discovery sources legend (Run launcher) */
.discovery-legend {{
  display: flex; gap: 16px; flex-wrap: wrap;
  margin: 6px 0 12px 0;
  font-size: 11.5px; color: var(--text-sub);
  letter-spacing: 0.01em;
}}
.discovery-legend span {{
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 9px; border-radius: 999px;
  background: var(--card-hover);
  border: 1px solid var(--border-soft);
}}

/* Signal card (Signals page) */
.sig-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 10px;
  transition: border-color 0.15s ease;
}}
.sig-card:hover {{ border-color: var(--primary); }}
.sig-head {{
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; margin-bottom: 6px;
}}
.sig-head-left {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.sig-src {{
  font-size: 10px; font-weight: 700; letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 2px 8px; border-radius: 999px;
}}
.sig-src.appstore_chart {{ background: rgba(129,140,248,0.18); color: #C7D2FE; }}
.sig-src.appstore_search {{ background: rgba(96,165,250,0.18); color: #BFDBFE; }}
.sig-src.reddit {{ background: rgba(251,146,60,0.18); color: #FED7AA; }}
.sig-src.google_trends {{ background: rgba(52,211,153,0.18); color: #A7F3D0; }}
.sig-src.web_search {{ background: rgba(167,139,250,0.18); color: #DDD6FE; }}
.sig-meta {{
  font-size: 11px; color: var(--text-sub); font-weight: 500;
}}
.sig-title {{
  font-size: 14px; color: var(--text); font-weight: 500;
  line-height: 1.4; margin: 2px 0 4px 0;
}}
.sig-title a {{ color: var(--text); text-decoration: none; }}
.sig-title a:hover {{ color: var(--primary); }}
.sig-content {{
  font-size: 12.5px; color: var(--text-mid); line-height: 1.5;
  margin-top: 4px;
}}
.sig-date {{
  font-size: 10px; color: var(--text-sub);
}}

/* Scrollbar (webkit) */
::-webkit-scrollbar {{
  width: 10px; height: 10px;
}}
::-webkit-scrollbar-track {{ background: var(--bg); }}
::-webkit-scrollbar-thumb {{
  background: var(--border); border-radius: 5px;
}}
::-webkit-scrollbar-thumb:hover {{ background: var(--text-sub); }}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


# ───── HTML snippet helpers ─────────────────────────────────────────────

def stage_stepper_html(current_stage: str | None) -> str:
    stages = ["ideated", "validated", "specced", "designed", "coded", "built", "shipped"]
    current = current_stage or "ideated"
    try:
        idx = stages.index(current)
    except ValueError:
        idx = 0
    parts = ["<div class='stepper'>"]
    for i, s in enumerate(stages):
        if i < idx:
            cls = "done"
        elif i == idx:
            cls = "current"
        else:
            cls = "todo"
        parts.append(f"<div class='stepper-step {cls}'>{s}</div>")
    parts.append("</div>")
    return "".join(parts)


def score_badge_html(score: int | None) -> str:
    color = score_color(score)
    text = str(score) if score is not None else "—"
    return f"<span class='score-badge' style='background:{color};'>{text}</span>"


_ACCENT_MAP = {
    "primary":      COLORS["primary"],
    "novelty":      COLORS["novelty"],
    "demand":       COLORS["demand"],
    "monetization": COLORS["monetization"],
    "feasibility":  COLORS["feasibility"],
}


def stat_card_html(
    label: str,
    value: str,
    *,
    sub: str | None = None,
    accent: str = "primary",
    href: str | None = None,
) -> str:
    """Compact stat card for the Home dashboard. Replaces st.metric so we get
    consistent sizing, accent stripe, and tabular numerals.

    If `href` is given, the entire card becomes a clickable link via an
    absolute-positioned overlay <a> (we never wrap block-level children in
    <a>, since Streamlit's markdown renderer breaks that into siblings).
    """
    import html as _html
    accent_color = _ACCENT_MAP.get(accent, COLORS["primary"])
    sub_html = (
        f"<div class='stat-card-sub'>{_html.escape(sub)}</div>" if sub else ""
    )
    classes = "stat-card" + (" is-link" if href else "")
    overlay = (
        f"<a class='card-overlay' href='{_html.escape(href)}' "
        f"target='_self' aria-label='{_html.escape(label)}'></a>"
        if href else ""
    )
    chevron = "<span class='stat-card-chevron'>→</span>" if href else ""
    return (
        f"<div class='{classes}' style='--accent: {accent_color};'>"
        f"{overlay}"
        f"<div class='stat-card-label'>{_html.escape(label)}</div>"
        f"<div class='stat-card-val'>{_html.escape(value)}</div>"
        f"{sub_html}"
        f"{chevron}"
        f"</div>"
    )


def section_head_html(title: str, sub: str | None = None, href: str | None = None) -> str:
    """Section header. If `href` is given, the entire row becomes clickable."""
    import html as _html
    sub_html = (
        f"<div class='section-sub'>{_html.escape(sub)}</div>" if sub else ""
    )
    classes = "section-head" + (" linked" if href else "")
    overlay = (
        f"<a class='card-overlay' href='{_html.escape(href)}' "
        f"target='_self' aria-label='{_html.escape(title)}'></a>"
        if href else ""
    )
    chevron = "<span class='section-chevron'>→</span>" if href else ""
    return (
        f"<div class='{classes}'>"
        f"{overlay}"
        f"<div class='section-title'>{_html.escape(title)}</div>"
        f"{sub_html}"
        f"{chevron}"
        f"</div>"
    )


_DIM_LABELS = {
    "novelty":      ("Novel", "Novelty — how original / non-obvious the idea is"),
    "demand":       ("Demand", "Demand — evidence people actually want this"),
    "monetization": ("Money",  "Monetization — how clearly it can make revenue"),
    "feasibility":  ("Build",  "Feasibility — how easy it is to build"),
}


def humanize_feasibility(value: str | None) -> str:
    """`solo-1wk` → 'Solo · 1 wk' etc — used in cards, pills, and filters."""
    if not value:
        return "—"
    mapping = {
        "solo-1wk":  "Solo · 1 wk",
        "solo-1mo":  "Solo · 1 mo",
        "solo-3mo":  "Solo · 3 mo",
        "team-only": "Team only",
    }
    return mapping.get(value, value)


def mini_bars_html(breakdown: dict) -> str:
    parts = ["<div class='bars'>"]
    dims = ("novelty", "demand", "monetization", "feasibility")
    for d in dims:
        v = int((breakdown or {}).get(d, 0) or 0)
        pct = min(100, v * 4)
        label, tooltip = _DIM_LABELS[d]
        parts.append(
            f"<div class='bar-row' title='{tooltip}'>"
            f"<div class='bar-label'>{label}</div>"
            f"<div class='bar-track'><div class='bar-fill' "
            f"style='width:{pct}%; background:{DIM_COLORS[d]};'></div></div>"
            f"<div class='bar-val'>{v}</div>"
            f"</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def idea_card_html(
    idea: dict,
    *,
    is_variant: bool = False,
    parent_title: str | None = None,
) -> str:
    import html
    title = html.escape(idea.get("title") or "(untitled)")
    concept_raw = idea.get("concept") or ""
    concept = html.escape(concept_raw[:160] + ("…" if len(concept_raw) > 160 else ""))
    score = idea.get("score")
    score_c = score_color(score)
    score_text = str(score) if score is not None else "—"
    feasibility = html.escape(humanize_feasibility(idea.get("ios_feasibility")))
    stage = html.escape(idea.get("stage") or "ideated")
    date = format_local_date(idea.get("created_at"), fallback="—")
    bars = mini_bars_html(idea.get("score_breakdown") or {})
    pivot_note_raw = idea.get("pivot_note") or ""
    pivot_note = html.escape(pivot_note_raw[:140]) if pivot_note_raw else ""

    variant_badge = "<span class='variant-badge'>↪ variant</span>" if is_variant else ""
    variant_inner_class = " is-variant" if is_variant else ""
    from_line = (
        f"<div class='variant-from'>↳ from: {html.escape(parent_title)}</div>"
        if is_variant and parent_title else ""
    )
    pivot_note_html = (
        f"<div class='variant-pivot-note'>{pivot_note}</div>"
        if is_variant and pivot_note else ""
    )

    return (
        f"<a href='Idea_Detail?id={idea['id']}' target='_self' class='idea-card'>"
        f"  <div class='idea-card-inner{variant_inner_class}'>"
        f"    <div class='idea-head'>"
        f"      <div class='idea-title'>{title}</div>"
        f"      <div class='score-badge' style='background:{score_c};'>{score_text}</div>"
        f"    </div>"
        f"    <div class='idea-meta'>"
        f"      <span class='pill'>#{idea['id']}</span>"
        f"      <span class='pill'>{feasibility}</span>"
        f"      <span class='pill'>{stage}</span>"
        f"      {variant_badge}"
        f"      <span>· {date}</span>"
        f"    </div>"
        f"    {bars}"
        f"    <div class='idea-concept'>{concept}</div>"
        f"    {pivot_note_html}"
        f"    {from_line}"
        f"  </div>"
        f"</a>"
    )
