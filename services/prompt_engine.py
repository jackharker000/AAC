import json
import re
from openai import AsyncOpenAI
from config import get_settings
from services.context_engine import ContextPacket
from schemas import PromptSuggestion

settings = get_settings()
_client: AsyncOpenAI | None = None

JAMES_SYSTEM_PROMPT = """You are an AAC (Augmentative and Alternative Communication) copilot helping James — a 44-year-old non-verbal man with cerebral palsy — participate in real-time conversation.

James's communication style:
- Short, direct sentences (ideally under 10 words)
- Socially engaged and curious
- Enjoys humour and wit when it fits naturally
- Interested in trains, politics, current affairs, popular culture
- Authentic — sounds like a real person, not a robot or a chatbot

Your task: Generate exactly 5 things James could say RIGHT NOW based on the conversation context.

ALWAYS return ONLY a valid JSON array, nothing else:
[{"text": "...", "category": "..."}]

Categories to use:
- reply: direct response to what was just said
- question: ask something
- memory-followup: follow up on something you know about this person
- topic: relate to a shared interest or topic
- social: friendly/humorous/social remark, or a request for more time

Rules:
- Each response must be 10 words or fewer
- Vary the categories — include at least 3 different ones
- Sound like James, not like an AI assistant
- If someone just asked James a question, make "reply" the first option
- If there are memory follow-ups available, always include at least one
- Avoid repeating the same idea twice
- Do not start every response with "I" — vary the openings
"""


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def _build_user_message(context: ContextPacket) -> str:
    parts = []

    parts.append(f"Date and time: {context.date_time}")
    if context.location_name:
        parts.append(f"Location: {context.location_name}")

    if context.people:
        names = ", ".join(p["name"] for p in context.people)
        parts.append(f"People present: {names}")
        for p in context.people:
            desc = p.get("relation", "")
            notes = p.get("notes", "")
            line = f"  - {p['name']}"
            if desc:
                line += f" ({desc})"
            if notes:
                line += f": {notes}"
            parts.append(line)

    if context.relevant_memories:
        parts.append("\nMemories about people present:")
        for m in context.relevant_memories:
            parts.append(f"  - {m}")

    if context.plan_things_to_say or context.plan_questions or context.plan_topics:
        parts.append(f"\nPre-conversation plan (tone: {context.plan_tone}):")
        if context.plan_topics:
            parts.append(f"  Topics: {', '.join(context.plan_topics)}")
        if context.plan_things_to_say:
            parts.append("  Things James wants to say:")
            for item in context.plan_things_to_say:
                parts.append(f"    - {item}")
        if context.plan_questions:
            parts.append("  Questions James wants to ask:")
            for item in context.plan_questions:
                parts.append(f"    - {item}")

    if context.recent_transcript:
        parts.append("\nRecent conversation:")
        for turn in context.recent_transcript:
            parts.append(f"  {turn['speaker']}: {turn['text']}")
    else:
        parts.append("\nConversation just started.")

    if context.preferred_categories:
        parts.append(f"\nJames tends to prefer: {', '.join(context.preferred_categories)}")
    if context.disliked_categories:
        parts.append(f"James tends to skip: {', '.join(context.disliked_categories)}")

    parts.append("\nGenerate exactly 5 things James could say now.")
    return "\n".join(parts)


def _parse_suggestions(raw: str) -> list[PromptSuggestion]:
    match = re.search(r'\[.*?\]', raw, re.DOTALL)
    if not match:
        return _fallback_suggestions()
    try:
        items = json.loads(match.group())
        suggestions = []
        for item in items[:settings.max_prompt_suggestions]:
            text = str(item.get("text", "")).strip()
            category = str(item.get("category", "reply")).strip()
            if text:
                suggestions.append(PromptSuggestion(text=text, category=category))
        return suggestions if suggestions else _fallback_suggestions()
    except (json.JSONDecodeError, KeyError):
        return _fallback_suggestions()


def _fallback_suggestions() -> list[PromptSuggestion]:
    return [
        PromptSuggestion(text="Can you give me a moment please?", category="social"),
        PromptSuggestion(text="That is interesting.", category="reply"),
        PromptSuggestion(text="Tell me more.", category="question"),
        PromptSuggestion(text="I agree.", category="reply"),
        PromptSuggestion(text="Could you say that again?", category="social"),
    ]


async def generate_prompts(context: ContextPacket) -> list[PromptSuggestion]:
    if not settings.openai_api_key:
        return _fallback_suggestions()

    client = _get_client()
    user_message = _build_user_message(context)

    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        max_tokens=400,
        messages=[
            {"role": "system", "content": JAMES_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    raw = response.choices[0].message.content or ""
    return _parse_suggestions(raw)
