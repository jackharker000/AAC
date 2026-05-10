from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from typing import List, Optional

from database import get_db
from models import Person, Memory, Conversation, TranscriptSegment
from schemas import PersonCreate, PersonUpdate, PersonRead, MemoryRead, ConversationRead

router = APIRouter(prefix="/people", tags=["people"])


@router.get("", response_model=List[PersonRead])
async def list_people(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Person).order_by(Person.name))
    return result.scalars().all()


@router.post("", response_model=PersonRead, status_code=201)
async def create_person(data: PersonCreate, db: AsyncSession = Depends(get_db)):
    person = Person(**data.model_dump())
    db.add(person)
    await db.commit()
    await db.refresh(person)
    return person


@router.get("/{person_id}", response_model=PersonRead)
async def get_person(person_id: int, db: AsyncSession = Depends(get_db)):
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@router.patch("/{person_id}", response_model=PersonRead)
async def update_person(person_id: int, data: PersonUpdate, db: AsyncSession = Depends(get_db)):
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(person, field, value)
    person.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(person)
    return person


@router.delete("/{person_id}", status_code=204)
async def delete_person(
    person_id: int,
    cascade_memories: bool = True,
    db: AsyncSession = Depends(get_db)
):
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    if not cascade_memories:
        # Anonymise linked memories instead of deleting them
        result = await db.execute(select(Memory).where(Memory.person_id == person_id))
        for mem in result.scalars().all():
            mem.person_id = None
    await db.delete(person)
    await db.commit()


@router.get("/{person_id}/memories", response_model=List[MemoryRead])
async def get_person_memories(person_id: int, db: AsyncSession = Depends(get_db)):
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    result = await db.execute(
        select(Memory)
        .where(Memory.person_id == person_id)
        .order_by(Memory.importance.desc(), Memory.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{person_id}/conversations", response_model=List[ConversationRead])
async def get_person_conversations(person_id: int, db: AsyncSession = Depends(get_db)):
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    result = await db.execute(
        select(Conversation).order_by(Conversation.start_time.desc())
    )
    convs = result.scalars().all()
    # Filter to those where person_id is in people_present JSON array
    return [c for c in convs if person_id in (c.people_present or [])]
