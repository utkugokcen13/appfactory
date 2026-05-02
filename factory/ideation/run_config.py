"""Configuration for a single ideation run.

Serialized as JSON and passed from the Streamlit launcher to the run_daily
subprocess via `--config <path>`. Every user-facing knob lives here so we
have one canonical schema.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Model registry — display name → AWS Bedrock model id
MODELS: dict[str, str] = {
    "Opus 4.7": "global.anthropic.claude-opus-4-7",
    "Sonnet 4.6": "global.anthropic.claude-sonnet-4-6",
}
DEFAULT_MODEL = "Opus 4.7"

FEASIBILITY_OPTIONS = ["solo-1wk", "solo-1mo", "solo-3mo", "team-only"]
MONETIZATION_OPTIONS = ["any", "subscription", "one-time", "freemium", "ads"]


@dataclass
class RunConfig:
    # ───── Tier 1: direction ────────────────────────────────────────────
    focus_prompt: str = ""
    niche_seeds: list[str] = field(default_factory=list)
    subreddits: list[str] = field(default_factory=list)
    avoid: str = ""

    # ───── Tier 2: output shape ─────────────────────────────────────────
    target_idea_count: int = 4
    min_score: int = 55
    feasibility_filter: list[str] = field(
        default_factory=lambda: list(FEASIBILITY_OPTIONS)
    )
    audience_hint: str = ""
    monetization_preference: str = "any"

    # ───── Tier 3: data sources ─────────────────────────────────────────
    skip_signal_collection: bool = False
    disable_google_trends: bool = False
    max_signal_age_days: int | None = None
    discovery_sources: list[str] = field(default_factory=list)

    # ───── Tier 4: technical ────────────────────────────────────────────
    max_turns: int = 22
    search_budget: int = 35
    model: str = MODELS[DEFAULT_MODEL]

    @classmethod
    def from_json(cls, path: str | Path) -> "RunConfig":
        with open(path) as f:
            data = json.load(f)
        # Forward-compat: ignore unknown keys silently
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_json(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    def target_count_phrase(self) -> str:
        n = max(1, int(self.target_idea_count or 4))
        if n == 1:
            return "1"
        return f"{max(1, n - 1)}-{n + 1}"
