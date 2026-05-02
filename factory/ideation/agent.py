"""Bedrock-hosted Claude agent that mines signals for app ideas via tool use."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from factory.client import DEFAULT_MODEL, get_client
from factory.ideation import store
from factory.ideation.run_config import RunConfig
from factory.ideation.tools import TOOL_SCHEMAS, ToolContext, dispatch


def build_system_prompt(cfg: RunConfig | None = None) -> str:
    """Compose the system prompt with optional user-supplied constraints
    interleaved into the appropriate places."""
    cfg = cfg or RunConfig()
    target_phrase = cfg.target_count_phrase()
    min_score = int(cfg.min_score)

    constraints: list[str] = []
    if cfg.audience_hint.strip():
        constraints.append(
            f"- Target audience must always include or relate to: **{cfg.audience_hint.strip()}**"
        )
    if cfg.monetization_preference and cfg.monetization_preference != "any":
        constraints.append(
            f"- Monetization preference: **{cfg.monetization_preference}** "
            f"(use this revenue model when feasibility allows; justify in the rationale)"
        )
    if cfg.avoid.strip():
        constraints.append(
            f"- AVOID these topics, niches, or categories entirely: **{cfg.avoid.strip()}**"
        )
    if cfg.feasibility_filter and len(cfg.feasibility_filter) < 4:
        constraints.append(
            f"- `ios_feasibility` MUST be one of: "
            + ", ".join(f"`{f}`" for f in cfg.feasibility_filter)
        )

    constraints_block = ""
    if constraints:
        constraints_block = (
            "\n**USER-SUPPLIED CONSTRAINTS (these override defaults — non-negotiable):**\n"
            + "\n".join(constraints)
            + "\n"
        )

    return f"""You are App Factory's Ideation Scout.

Goal: produce {target_phrase} saved app ideas per run for a solo iOS developer to ship
within 1-3 months. Saving ideas via `save_idea` is the only deliverable —
exploration without saving is a failed run.
{constraints_block}
Signal sources available to you:
- `appstore_chart` — iOS top free + top grossing charts across 8 categories
- `appstore_search` — iTunes keyword search results
- `reddit` — pre-collected top posts today across target subreddits
- `google_trends` — rising / breakout related queries for seed niches
- `web_search` — live DuckDuckGo scrape (costs budget)
On-demand tools for deeper investigation:
- `search_reddit` — search Reddit for a specific pain point or discussion
- `get_trend` — fetch Google Trends data for any keyword (3-mo slope + rising)
- `fetch_url` — pull the full text of an article / Reddit thread

Pace (follow this strictly):
- Turns 1-2: open the pre-computed trends brief embedded in the user message
  and explore `search_signals` across 'reddit' and 'google_trends' sources
  (where the hot stuff already is), then 'appstore_chart' to anchor demand.
- Turns 3-4: form 3-4 concrete hypotheses. For each, validate with either
  `get_trend` (if volume/growth matters) or `search_reddit` (if pain matters)
  or `web_search` (for open-web evidence).
- Turn 5: SAVE your first `save_idea`. Do not wait for perfect evidence.
- Turns 6-12: alternate validate → save. Aim for {target_phrase} total saved ideas.

Citation requirement (non-negotiable):
- Every `save_idea` MUST include `evidence_urls` that contain at least ONE
  Google Trends permalink (https://trends.google.com/...) OR a Reddit thread
  permalink, plus at least one App Store URL when relevant. This is how the
  dashboard shows where each idea came from.
- `evidence_signal_ids` MUST include ids from `search_signals` / `search_reddit`
  / `get_trend` / `web_search` tool results (every tool persists its rows and
  returns ids, so reference them).

Rules:
- If you have explored for 6+ tool calls without saving anything, stop
  exploring and save your best 2 ideas immediately.
- Don't repeat search queries. Don't re-query the same signal source with
  the same arguments twice.
- Quality > quantity, but ending with 0 saved ideas is worse than saving 2
  mediocre ones.

Scoring (explainable):
- Score every idea on four dimensions, each 0-25, summing to `score` (0-100):
  · novelty      — how green-field the wedge is
  · demand       — evidence of users wanting this (chart ranks, rating counts, forum pain)
  · monetization — willingness-to-pay and LTV, given audience and comps
  · feasibility  — solo iOS dev MVP within 1-3 months (25 = ≤1 month)
- Include one-sentence `notes` per dimension so the score is auditable.
- Don't save ideas with total < {min_score} unless evidence is exceptional.

Structured qualitative fields (required for every saved idea):
- `pros`:            2-4 concrete strengths.
- `cons`:            2-4 honest weaknesses.
- `differentiators`: 2-4 reasons this wins vs the strongest incumbent.
- `risks`:           1-3 things that could kill it (optional but strongly preferred).
- `key_competitors`: 3-5 nearest competitors. For each: `name` required;
  `url`, `rating`, `reviews`, `pricing`, `note` optional. Pull from the signal
  data when possible (App Store chart rank, rating count) — use `note` for
  anything that doesn't fit the structured fields.

Budget: each `web_search` costs a quota unit. Prefer `search_signals`,
`search_reddit`, and `get_trend` (all cheap/free) first. Never spend more
than ~6 web searches before saving your first idea.

Tool call format (critical):
- Call tools using the native JSON tool-use format. Each field goes in its own
  JSON key. DO NOT emit `<parameter name="...">...</parameter>` XML tags inside
  any string field — those are a legacy format and will corrupt the data.
- Keep `concept` to a focused single paragraph (~120 words) so the tool call
  stays compact.
"""


# Backwards-compatible: existing imports of `SYSTEM_PROMPT` still work.
SYSTEM_PROMPT = build_system_prompt()


@dataclass
class AgentResult:
    ideas_saved: int
    input_tokens: int
    output_tokens: int
    web_searches: int
    stop_reason: str
    turns_taken: int = 0
    saved_idea_ids: list[int] = field(default_factory=list)


def _print_turn_header(turn_idx: int, texts: list[Any]) -> None:
    for t in texts:
        snippet = (t.text or "").strip().splitlines()[0:2]
        if snippet:
            print(f"[turn {turn_idx}] {' '.join(snippet)[:160]}")
            return


def run_agent(
    ctx: ToolContext,
    user_brief: str,
    *,
    model: str = DEFAULT_MODEL,
    max_turns: int = 22,
    max_tokens_per_turn: int = 8192,
    config: RunConfig | None = None,
) -> AgentResult:
    """Run the Claude tool-use loop. Persists every turn + block to SQLite.

    `config` (optional) lets the caller customize the system prompt
    (target idea count, min score, audience hint, monetization preference,
    avoid list, feasibility filter). When omitted, defaults match the
    legacy hardcoded prompt.
    """
    client = get_client()
    system_prompt = build_system_prompt(config)
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_brief}]

    total_in = 0
    total_out = 0
    last_stop = "unknown"
    turns_taken = 0

    for turn in range(max_turns):
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens_per_turn,
            system=system_prompt,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        total_in += resp.usage.input_tokens
        total_out += resp.usage.output_tokens
        last_stop = resp.stop_reason or "unknown"
        turns_taken = turn + 1

        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        texts = [b for b in resp.content if getattr(b, "type", None) == "text"]
        _print_turn_header(turns_taken, texts)

        if resp.stop_reason != "tool_use" or not tool_uses:
            # Terminal turn — persist assistant output with no tool results, then stop.
            store.save_turn(
                ctx.conn,
                run_id=ctx.run_id,
                turn_number=turns_taken,
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                stop_reason=last_stop,
                assistant_blocks=list(resp.content),
                tool_results=None,
            )
            break

        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            name = tu.name
            raw_input = tu.input or {}
            print(f"  → tool: {name} {str(raw_input)[:120]}")
            try:
                result_str = dispatch(ctx, name, raw_input)
                is_error = False
            except Exception as e:
                result_str = f'{{"error": "{type(e).__name__}: {e}"}}'
                is_error = True
                print(f"    tool error: {e}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result_str,
                "is_error": is_error,
            })

        store.save_turn(
            ctx.conn,
            run_id=ctx.run_id,
            turn_number=turns_taken,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            stop_reason=last_stop,
            assistant_blocks=list(resp.content),
            tool_results=tool_results,
        )
        # Commit so the dashboard can show live progress of in-flight runs.
        ctx.conn.commit()

        # Strip is_error key from what we actually send back to Claude; it's only
        # for our DB. Anthropic tool_result blocks don't use that in Bedrock.
        messages.append({
            "role": "user",
            "content": [
                {k: v for k, v in tr.items() if k != "is_error"}
                for tr in tool_results
            ],
        })

    return AgentResult(
        ideas_saved=ctx.ideas_saved,
        input_tokens=total_in,
        output_tokens=total_out,
        web_searches=ctx.web.used,
        stop_reason=last_stop,
        turns_taken=turns_taken,
        saved_idea_ids=list(ctx.saved_idea_ids),
    )
