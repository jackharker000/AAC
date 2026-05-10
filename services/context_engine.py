from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import get_settings
from models import (
    Conversation, TranscriptSegment, Memory, Person, Location, PreConversationPlan
)

settings = get_settings()


@dataclass
class ContextPacket:
    conversation_id: int
    location_name: str = ""
    date_time: str = ""
    people: list[dict] = field(default_factory=list)          # [{name, relationship, notes}]
    recent_transcript: list[dict] = field(default_factory=list)  # [{speaker, text}]
    relevant_memories: list[str] = field(default_factory=list)
    plan_things_to_say: list[str] = field(default_factory=list)
    plan_questions: list[str] = field(default_factory=list)
    plan_topics: list[str] = field(default_factory=list)
    plan_tone: str = "friendly"
    # Prompt style biases from ratings
    preferred_categories: list[str] = field(default_factory=list)
    disliked_categories: list[str] = field(default_factory=list)


async def build_context_packet(
    conversation_id: int,
    db: AsyncSession,
    plan_id: Optional[int] = None,
) -> ContextPacket:
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        return ContextPacket(conversation_id=conversation_id)

    packet = ContextPacket(
        conversation_id=conversation_id,
        date_time=datetime.utcnow().strftime("%A, %d %B %Y, %H:%M"),
    )

    # Location
    if conv.location_id:
        loc = await db.get(Location, conv.location_id)
        if loc:
            packet.location_name = loc.name

    # People present
    person_ids = list(conv.people_present or [])
    for pid in person_ids:
        person = await db.get(Person, pid)
        if person:
            packet.people.append({
                "id": person.id,
                "name": person.name,
                "relationship": person.relation,
                "notes": person.notes,
            })

    # Recent transcript (last N turns)
    seg_result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.conversation_id == conversation_id)
        .order_by(TranscriptSegment.timestamp.desc())
        .limit(settings.transcript_context_turns)
    )
    segs = list(reversed(seg_result.scalars().all()))
    packet.recent_transcript = [
        {"speaker": s.speaker_label, "text": s.text}
        for s in segs
    ]

    # Relevant memories for people present
    if person_ids:
        mem_result = await db.execute(
            select(Memory)
            .where(Memory.person_id.in_(person_ids))
            .where(Memory.confirmed == True)
            .order_by(Memory.importance.desc(), Memory.last_used_at.desc().nullslast())
            .limit(settings.memory_context_limit)
        )
        memories = mem_result.scalars().all()
        # Also get unconfirmed high-importance ones
        if len(memories) < 4:
            unconf_result = await db.execute(
                select(Memory)
                .where(Memory.person_id.in_(person_ids))
                .where(Memory.confirmed == False)
                .where(Memory.importance >= 4)
                .limit(4)
            )
            memories = list(memories) + list(unconf_result.scalars().all())

        for mem in memories:
            person_name = ""
            if mem.person_id:
                p = await db.get(Person, mem.person_id)
                if p:
                    person_name = p.name
            label = f"[{person_name}] " if person_name else ""
            packet.relevant_memories.append(f"{label}{mem.memory_text}")
            # Mark as used
            mem.last_used_at = datetime.utcnow()

        await db.commit()

    # Location memories
    if conv.location_id:
        loc_mem_result = await db.execute(
            select(Memory)
            .where(Memory.location_id == conv.location_id)
            .where(Memory.memory_type == "location_routine")
            .order_by(Memory.importance.desc())
            .limit(3)
        )
        for mem in loc_mem_result.scalars().all():
            packet.relevant_memories.append(f"[Location routine] {mem.memory_text}")

    # Pre-conversation plan
    plan = None
    if plan_id:
        plan = await db.get(PreConversationPlan, plan_id)
    else:
        # Find any active plan for today that matches these people
        from datetime import date
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start.replace(hour=23, minute=59, second=59)
        plan_result = await db.execute(
            select(PreConversationPlan)
            .where(PreConversationPlan.conversation_id == None)
            .order_by(PreConversationPlan.created_at.desc())
            .limit(1)
        )
        plan = plan_result.scalar_one_or_none()

    if plan:
        packet.plan_things_to_say = list(plan.things_to_say or [])
        packet.plan_questions = list(plan.questions_to_ask or [])
        packet.plan_topics = list(plan.topics_expected or [])
        packet.plan_tone = plan.tone or "friendly"

    # Prompt style biases from recent ratings
    from models import JamesOutput
    from sqlalchemy import func
    rated_result = await db.execute(
        select(JamesOutput.category, func.avg(JamesOutput.rating))
        .where(JamesOutput.rating.isnot(None))
        .group_by(JamesOutput.category)
    )
    for category, avg_rating in rated_result.all():
        if avg_rating and avg_rating > 0.5:
            packet.preferred_categories.append(category)
        elif avg_rating and avg_rating < -0.5:
            packet.disliked_categories.append(category)

    return packet


async def build_plan_context_packet(plan: PreConversationPlan, db: AsyncSession) -> ContextPacket:
    """Build a context packet from a plan alone (for preview before conversation starts)."""
    packet = ContextPacket(
        conversation_id=0,
        date_time=datetime.utcnow().strftime("%A, %d %B %Y"),
        location_name=plan.location_expected or "",
        plan_things_to_say=list(plan.things_to_say or []),
        plan_questions=list(plan.questions_to_ask or []),
        plan_topics=list(plan.topics_expected or []),
        plan_tone=plan.tone or "friendly",
    )

    for pid in (plan.people_expected or []):
        person = await db.get(Person, pid)
        if person:
            packet.people.append({
                "id": person.id,
                "name": person.name,
                "relationship": person.relation,
                "notes": person.notes,
            })
            # Get their memories
            mem_result = await db.execute(
                select(Memory)
                .where(Memory.person_id == pid)
                .where(Memory.confirmed == True)
                .order_by(Memory.importance.desc())
                .limit(5)
            )
            for mem in mem_result.scalars().all():
                packet.relevant_memories.append(f"[{person.name}] {mem.memory_text}")

    return packet
