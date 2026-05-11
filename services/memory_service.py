from __future__ import annotations
import json
import re
from datetime import datetime
from typing import Optional
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import get_settings
from database import AsyncSessionLocal
from models import Conversation, TranscriptSegment, Memory, Person

settings = get_settings()

MEMORY_EXTRACTION_SYSTEM = """You are an assistant that extracts useful long-term memory facts from a conversation transcript.

Extract facts that would be useful for James (a non-verbal man with cerebral palsy who uses an AAC system) to remember for future conversations.

Focus on:
- Personal facts about the people in the conversation (family, pets, health, hobbies, jobs)
- Follow-up items (things to ask next time, unresolved topics)
- Preferences or interests of the people
- Important events mentioned
- Relationship context

Return ONLY a valid JSON object:
{
  "summary": "2-3 sentence plain English summary of what happened",
  "memories": [
    {
      "person_name": "name or null",
      "memory_text": "The fact to remember",
      "memory_type": "personal_fact|preference|follow_up|location_routine|conversation_topic|open_issue",
      "importance": 1-5,
      "source_text": "exact quote from transcript that supports this"
    }
  ]
}

Rules:
- Only extract clearly stated facts, not assumptions
- importance 5 = critical to remember, 1 = minor detail
- follow_up type = something James should ask or mention next time
- Maximum 10 memories per conversation
- If nothing memorable happened, return empty memories array
"""


async def extract_memories_for_conversation(conversation_id: int) -> list[Memory]:
    """
    Extract memories from a completed conversation.
    Called after conversation ends. Returns the list of newly created Memory objects.
    """
    async with AsyncSessionLocal() as db:
        conv = await db.get(Conversation, conversation_id)
        if not conv:
            return []

        seg_result = await db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.conversation_id == conversation_id)
            .order_by(TranscriptSegment.timestamp.asc())
        )
        segments = seg_result.scalars().all()

        if not segments:
            return []

        # Build people name → id map
        people_map = {}
        for pid in (conv.people_present or []):
            person = await db.get(Person, pid)
            if person:
                people_map[person.name.lower()] = person.id

        transcript_lines = []
        for seg in segments:
            ts = seg.timestamp.strftime("%H:%M")
            transcript_lines.append(f"[{ts}] {seg.speaker_label}: {seg.text}")
        transcript_text = "\n".join(transcript_lines)

        if not settings.openai_api_key:
            return []

        client = AsyncOpenAI(api_key=settings.openai_api_key)

        response = await client.chat.completions.create(
            model=settings.openai_chat_model,
            max_tokens=1000,
            messages=[
                {"role": "system", "content": MEMORY_EXTRACTION_SYSTEM},
                {"role": "user", "content": f"Conversation transcript:\n{transcript_text}"},
            ],
        )

        raw = response.choices[0].message.content or ""
        extracted = _parse_extraction(raw)
        summary = extracted.get("summary", "")
        raw_memories = extracted.get("memories", [])

        if summary:
            conv.summary = summary
            await db.commit()

        created = []
        for item in raw_memories[:10]:
            person_id = None
            person_name = (item.get("person_name") or "").lower()
            if person_name:
                for name_key, pid in people_map.items():
                    if person_name in name_key or name_key in person_name:
                        person_id = pid
                        break

            memory = Memory(
                person_id=person_id,
                conversation_id=conversation_id,
                memory_text=item.get("memory_text", ""),
                memory_type=item.get("memory_type", "personal_fact"),
                importance=int(item.get("importance", 3)),
                confidence=0.85,
                source_text=item.get("source_text", ""),
                confirmed=False,
            )
            db.add(memory)
            created.append(memory)

        await db.commit()
        for mem in created:
            await db.refresh(mem)

        return created


def _parse_extraction(raw: str) -> dict:
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        return {"summary": "", "memories": []}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {"summary": "", "memories": []}


async def get_relevant_memories(
    person_ids: list[int],
    location_id: Optional[int],
    db: AsyncSession,
    limit: int = 10,
) -> list[Memory]:
    q = select(Memory).where(
        (Memory.person_id.in_(person_ids)) | (Memory.location_id == location_id)
        if location_id else Memory.person_id.in_(person_ids)
    )
    q = q.order_by(Memory.importance.desc(), Memory.last_used_at.desc().nullslast())
    q = q.limit(limit)
    result = await db.execute(q)
    return result.scalars().all()
