"""Lab Chat Agent — iterative refinement conversation on a single idea.

Each call to `run_chat_turn()` runs ONE user-message → assistant-response cycle
(which may include multiple tool_use rounds internally). All content blocks
persist to idea_chat_messages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from factory.client import DEFAULT_MODEL, get_client
from factory.ideation import store
from factory.ideation.signals.websearch import make_client as make_web_client
from factory.lab.tools import TOOL_SCHEMAS, LabContext, dispatch

SYSTEM_PROMPT_TEMPLATE = """You are App Factory's Idea Lab — a partner for the user as they iterate on a saved idea. You are paired with the research and mutation tools listed below; use them eagerly but frugally.

Current idea (read-only unless the user approves a change):
{idea_context}

Rules of engagement:
- Understand the user's intent first. If they want to pivot, validate, deepen,
  or critique — match that mode. Never make changes unilaterally.
- To research: use `search_signals` (free) first; then `search_reddit`,
  `get_trend`, `web_search`, or `fetch_url` as needed. Cite URLs in your reply
  so the user can follow up.
- To mutate the idea: call `update_idea_field` only after the user explicitly
  asks for a change or confirms a proposal. Keep the change minimal.
- When the user wants to pivot (different audience, pricing, feature focus) AND
  wants to keep both versions, call `create_variant_idea`. Set `pivot_note` to
  one clear line describing the delta. Note: there is also a UI-driven Pivot
  form (with its own preview + approval). If the user already staged a variant
  via the form, DO NOT call `create_variant_idea` — the UI handles saving. Only
  call the tool when the user requests a variant purely in chat.
- Keep replies tight: 2-5 sentences by default. Add bullet lists only when
  enumerating options. Show tool output selectively — don't dump JSON.
- When you don't have enough info to answer, say so and propose a research
  step (or just run it).

Do NOT emit `<parameter>` XML tags inside tool input strings — use the native
JSON format.
"""


def build_idea_context(idea: dict[str, Any]) -> str:
    """Render a compact, structured idea context for the system prompt."""
    parts = [
        f"- Title: {idea.get('title')}",
        f"- Score: {idea.get('score')}/100  (stage: {idea.get('stage')})",
        f"- Feasibility: {idea.get('ios_feasibility')}",
        f"- Target users: {idea.get('target_users') or '—'}",
        f"- Monetization: {idea.get('monetization') or '—'}",
        f"- Concept: {(idea.get('concept') or '')[:500]}",
    ]

    def _decode(v):
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    for k in ("pros", "cons", "risks", "differentiators"):
        items = _decode(idea.get(k))
        if items:
            parts.append(f"- {k.capitalize()}: " + "; ".join(items))

    comps = _decode(idea.get("key_competitors"))
    if comps:
        names = [c.get("name") for c in comps if isinstance(c, dict) and c.get("name")]
        if names:
            parts.append(f"- Competitors: " + ", ".join(names[:5]))

    return "\n".join(parts)


def _messages_from_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert stored chat rows back into Anthropic API message shape.

    Our storage is one row per content block. We must collapse into the API's
    interleaved user/assistant structure, grouping consecutive tool_result rows
    into a single user message (Anthropic requires this for the tool loop).
    """
    api_msgs: list[dict[str, Any]] = []
    cur_role: str | None = None
    cur_blocks: list[dict[str, Any]] = []

    def _flush():
        if cur_role and cur_blocks:
            api_msgs.append({"role": cur_role, "content": list(cur_blocks)})

    for m in messages:
        role = m["role"]
        if role == "user":
            _flush()
            cur_role = "user"
            cur_blocks = [{"type": "text", "text": m.get("text") or ""}]
            _flush()
            cur_role, cur_blocks = None, []
        elif role == "assistant_text":
            if cur_role != "assistant":
                _flush()
                cur_role = "assistant"
                cur_blocks = []
            cur_blocks.append({"type": "text", "text": m.get("text") or ""})
        elif role == "assistant_tool_use":
            if cur_role != "assistant":
                _flush()
                cur_role = "assistant"
                cur_blocks = []
            cur_blocks.append({
                "type": "tool_use",
                "id": m.get("tool_use_id"),
                "name": m.get("tool_name"),
                "input": json.loads(m.get("tool_input") or "{}"),
            })
        elif role == "tool_result":
            if cur_role != "user":
                _flush()
                cur_role = "user"
                cur_blocks = []
            cur_blocks.append({
                "type": "tool_result",
                "tool_use_id": m.get("tool_use_id"),
                "content": m.get("tool_result") or "",
            })

    _flush()
    return api_msgs


@dataclass
class ChatTurnResult:
    final_text: str
    tool_uses: int
    input_tokens: int
    output_tokens: int
    variants_created: list[int] = field(default_factory=list)
    fields_updated: list[str] = field(default_factory=list)


def run_chat_turn(
    *,
    chat_id: int,
    idea: dict[str, Any],
    user_text: str,
    web_budget: int = 15,
    max_tool_rounds: int = 8,
    max_tokens_per_turn: int = 4096,
    model: str = DEFAULT_MODEL,
) -> ChatTurnResult:
    client = get_client()
    web = make_web_client(budget=web_budget)

    with store.connect() as conn:
        # Persist the user's message first
        store.save_chat_message(conn, chat_id=chat_id, role="user", text=user_text)

        # Rebuild API message list from full history (including the user msg we just saved)
        history = store.load_chat_messages(conn, chat_id)
        api_messages = _messages_from_history(history)

        ctx = LabContext(conn=conn, web=web, idea_id=idea["id"], chat_id=chat_id)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(idea_context=build_idea_context(idea))

        total_in = 0
        total_out = 0
        tool_use_count = 0
        final_text = ""

        for _ in range(max_tool_rounds):
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens_per_turn,
                system=system_prompt,
                tools=TOOL_SCHEMAS,
                messages=api_messages,
            )
            total_in += resp.usage.input_tokens
            total_out += resp.usage.output_tokens

            # Persist assistant content blocks (text + tool_use)
            for block in resp.content:
                btype = getattr(block, "type", None)
                if btype == "text":
                    text = getattr(block, "text", "") or ""
                    if text.strip():
                        store.save_chat_message(
                            conn, chat_id=chat_id, role="assistant_text",
                            text=text,
                            input_tokens=resp.usage.input_tokens,
                            output_tokens=resp.usage.output_tokens,
                        )
                        final_text = text
                elif btype == "tool_use":
                    store.save_chat_message(
                        conn, chat_id=chat_id, role="assistant_tool_use",
                        tool_name=getattr(block, "name", None),
                        tool_input=getattr(block, "input", {}) or {},
                        tool_use_id=getattr(block, "id", None),
                    )

            api_messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason != "tool_use":
                break

            # Execute tool calls and persist results
            tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
            tool_results = []
            for tu in tool_uses:
                tool_use_count += 1
                try:
                    result_str = dispatch(ctx, tu.name, tu.input or {})
                    is_err = False
                except Exception as e:
                    result_str = json.dumps({"error": f"{type(e).__name__}: {e}"})
                    is_err = True
                store.save_chat_message(
                    conn, chat_id=chat_id, role="tool_result",
                    tool_use_id=tu.id,
                    tool_result=result_str,
                    tool_error=is_err,
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_str,
                })

            api_messages.append({"role": "user", "content": tool_results})

        conn.commit()

    return ChatTurnResult(
        final_text=final_text,
        tool_uses=tool_use_count,
        input_tokens=total_in,
        output_tokens=total_out,
        variants_created=list(ctx.variants_created),
        fields_updated=list(ctx.fields_updated),
    )
