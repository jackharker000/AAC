from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from datetime import datetime
from typing import List, Optional

from database import get_db
from models import Conversation, TranscriptSegment, JamesOutput, Memory, Person
from schemas import (
    ConversationCreate, ConversationUpdate, ConversationRead, ConversationDetail,
    SegmentCreate, SegmentUpdate, TranscriptSegmentRead,
    OutputCreate, OutputRating, JamesOutputRead,
    LabelSpeakerRequest, SpeakerConfirmRequest, MemoryRead
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ── Conversations ─────────────────────────────────────────────────────────────

@router.get("", response_model=List[ConversationRead])
async def list_conversations(
    person_id: Optional[int] = Query(None),
    location_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    q = select(Conversation).order_by(Conversation.start_time.desc())
    if location_id is not None:
        q = q.where(Conversation.location_id == location_id)
    q = q.limit(limit).offset(offset)
    result = await db.execute(q)
    convs = result.scalars().all()

    if person_id is not None:
        convs = [c for c in convs if person_id in (c.people_present or [])]

    if search:
        # Full-text search over summaries
        search_lower = search.lower()
        matched_ids = set()
        for conv in convs:
            if search_lower in (conv.summary or "").lower():
                matched_ids.add(conv.id)

        # Also search transcript text
        seg_result = await db.execute(
            select(TranscriptSegment.conversation_id)
            .where(TranscriptSegment.text.ilike(f"%{search}%"))
        )
        for row in seg_result.all():
            matched_ids.add(row[0])

        convs = [c for c in convs if c.id in matched_ids]

    return convs


@router.post("", response_model=ConversationRead, status_code=201)
async def start_conversation(data: ConversationCreate, db: AsyncSession = Depends(get_db)):
    conv = Conversation(**data.model_dump())
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    # Update last_seen_date for all people present
    for person_id in (data.people_present or []):
        person = await db.get(Person, person_id)
        if person:
            person.last_seen_date = datetime.utcnow()
    await db.commit()

    return conv


@router.get("/{conv_id}", response_model=ConversationDetail)
async def get_conversation(conv_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conv_id)
        .options(
            selectinload(Conversation.segments),
            selectinload(Conversation.outputs),
            selectinload(Conversation.memories),
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.patch("/{conv_id}", response_model=ConversationRead)
async def update_conversation(conv_id: int, data: ConversationUpdate, db: AsyncSession = Depends(get_db)):
    conv = await db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(conv, field, value)
    conv.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(conv)
    return conv


@router.post("/{conv_id}/end", response_model=ConversationRead)
async def end_conversation(conv_id: int, db: AsyncSession = Depends(get_db)):
    conv = await db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.end_time = datetime.utcnow()
    conv.updated_at = datetime.utcnow()
    await db.commit()

    # Trigger async memory extraction (non-blocking)
    import asyncio
    from services.memory_service import extract_memories_for_conversation
    asyncio.create_task(extract_memories_for_conversation(conv_id))

    await db.refresh(conv)
    return conv


@router.delete("/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: int,
    keep_memories: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    conv = await db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if keep_memories:
        result = await db.execute(select(Memory).where(Memory.conversation_id == conv_id))
        for mem in result.scalars().all():
            mem.conversation_id = None
    await db.delete(conv)
    await db.commit()


@router.get("/{conv_id}/export")
async def export_conversation(conv_id: int, format: str = Query("text"), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conv_id)
        .options(selectinload(Conversation.segments), selectinload(Conversation.outputs))
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    lines = []
    lines.append(f"AAC Conversation — {conv.start_time.strftime('%d %B %Y %H:%M')}")
    if conv.end_time:
        duration = int((conv.end_time - conv.start_time).total_seconds() // 60)
        lines.append(f"Duration: {duration} minutes")
    lines.append("")

    if conv.summary:
        lines.append("Summary:")
        lines.append(conv.summary)
        lines.append("")

    lines.append("Transcript:")
    for seg in conv.segments:
        ts = seg.timestamp.strftime("%H:%M:%S")
        lines.append(f"[{ts}] {seg.speaker_label}: {seg.text}")

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content="\n".join(lines),
        headers={"Content-Disposition": f'attachment; filename="conversation_{conv_id}.txt"'}
    )


# ── Transcript Segments ───────────────────────────────────────────────────────

@router.post("/{conv_id}/segments", response_model=TranscriptSegmentRead, status_code=201)
async def add_segment(conv_id: int, data: SegmentCreate, db: AsyncSession = Depends(get_db)):
    conv = await db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    seg = TranscriptSegment(conversation_id=conv_id, **data.model_dump())
    db.add(seg)
    await db.commit()
    await db.refresh(seg)
    return seg


@router.patch("/{conv_id}/segments/{seg_id}", response_model=TranscriptSegmentRead)
async def update_segment(
    conv_id: int,
    seg_id: int,
    data: SegmentUpdate,
    db: AsyncSession = Depends(get_db)
):
    seg = await db.get(TranscriptSegment, seg_id)
    if not seg or seg.conversation_id != conv_id:
        raise HTTPException(status_code=404, detail="Segment not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(seg, field, value)
    await db.commit()
    await db.refresh(seg)
    return seg


@router.post("/{conv_id}/label-speaker")
async def label_speaker(
    conv_id: int,
    data: LabelSpeakerRequest,
    db: AsyncSession = Depends(get_db)
):
    """Relabel all segments in this conversation that match the old label."""
    person_id = data.person_id

    if data.create_person and data.new_person_name:
        person = Person(name=data.new_person_name, last_seen_date=datetime.utcnow())
        db.add(person)
        await db.commit()
        await db.refresh(person)
        person_id = person.id

    # Retroactively update all segments with this label
    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.conversation_id == conv_id)
        .where(TranscriptSegment.speaker_label == data.speaker_label)
    )
    for seg in result.scalars().all():
        if person_id:
            seg.speaker_person_id = person_id
        if data.new_person_name:
            seg.speaker_label = data.new_person_name

    await db.commit()
    return {"ok": True, "person_id": person_id}


@router.post("/{conv_id}/confirm-speaker")
async def confirm_speaker(
    conv_id: int,
    data: SpeakerConfirmRequest,
    db: AsyncSession = Depends(get_db)
):
    """Confirm a speaker identity detected from conversation context."""
    person = await db.get(Person, data.person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.conversation_id == conv_id)
        .where(TranscriptSegment.speaker_label == data.current_label)
    )
    for seg in result.scalars().all():
        seg.speaker_label = person.name
        seg.speaker_person_id = person.id

    # Add person to conversation's people_present if not already there
    conv = await db.get(Conversation, conv_id)
    if conv and person.id not in (conv.people_present or []):
        conv.people_present = list(conv.people_present or []) + [person.id]
        person.last_seen_date = datetime.utcnow()

    await db.commit()
    return {"ok": True, "person_id": person.id, "person_name": person.name}


# ── James Outputs ─────────────────────────────────────────────────────────────

@router.post("/{conv_id}/outputs", response_model=JamesOutputRead, status_code=201)
async def save_output(conv_id: int, data: OutputCreate, db: AsyncSession = Depends(get_db)):
    conv = await db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    output = JamesOutput(conversation_id=conv_id, **data.model_dump())
    db.add(output)
    await db.commit()
    await db.refresh(output)
    return output


@router.patch("/{conv_id}/outputs/{output_id}/rating", response_model=JamesOutputRead)
async def rate_output(
    conv_id: int,
    output_id: int,
    data: OutputRating,
    db: AsyncSession = Depends(get_db)
):
    output = await db.get(JamesOutput, output_id)
    if not output or output.conversation_id != conv_id:
        raise HTTPException(status_code=404, detail="Output not found")
    if data.rating not in (1, -1):
        raise HTTPException(status_code=422, detail="Rating must be 1 or -1")
    output.rating = data.rating
    await db.commit()
    await db.refresh(output)
    return output


# ── Memory extraction ─────────────────────────────────────────────────────────

@router.post("/{conv_id}/extract-memories", response_model=List[MemoryRead])
async def trigger_memory_extraction(conv_id: int, db: AsyncSession = Depends(get_db)):
    conv = await db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    from services.memory_service import extract_memories_for_conversation
    memories = await extract_memories_for_conversation(conv_id)
    return memories
