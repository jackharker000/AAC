from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import List, Optional

from database import get_db
from models import Memory
from schemas import MemoryCreate, MemoryUpdate, MemoryRead

router = APIRouter(prefix="/memories", tags=["memories"])

VALID_TYPES = {
    "personal_fact", "preference", "follow_up", "location_routine",
    "james_goal", "relationship", "open_issue", "conversation_topic"
}


@router.get("", response_model=List[MemoryRead])
async def list_memories(
    person_id: Optional[int] = Query(None),
    location_id: Optional[int] = Query(None),
    conversation_id: Optional[int] = Query(None),
    memory_type: Optional[str] = Query(None),
    confirmed: Optional[bool] = Query(None),
    min_importance: int = Query(1),
    limit: int = Query(100),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    q = select(Memory)
    if person_id is not None:
        q = q.where(Memory.person_id == person_id)
    if location_id is not None:
        q = q.where(Memory.location_id == location_id)
    if conversation_id is not None:
        q = q.where(Memory.conversation_id == conversation_id)
    if memory_type is not None:
        q = q.where(Memory.memory_type == memory_type)
    if confirmed is not None:
        q = q.where(Memory.confirmed == confirmed)
    q = q.where(Memory.importance >= min_importance)
    q = q.order_by(Memory.importance.desc(), Memory.created_at.desc())
    q = q.limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/unreviewed", response_model=List[MemoryRead])
async def get_unreviewed_memories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Memory)
        .where(Memory.confirmed == False)
        .order_by(Memory.importance.desc(), Memory.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=MemoryRead, status_code=201)
async def create_memory(data: MemoryCreate, db: AsyncSession = Depends(get_db)):
    memory = Memory(**data.model_dump())
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    return memory


@router.get("/{memory_id}", response_model=MemoryRead)
async def get_memory(memory_id: int, db: AsyncSession = Depends(get_db)):
    memory = await db.get(Memory, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.patch("/{memory_id}", response_model=MemoryRead)
async def update_memory(memory_id: int, data: MemoryUpdate, db: AsyncSession = Depends(get_db)):
    memory = await db.get(Memory, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(memory, field, value)
    await db.commit()
    await db.refresh(memory)
    return memory


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: int, db: AsyncSession = Depends(get_db)):
    memory = await db.get(Memory, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    await db.delete(memory)
    await db.commit()


@router.post("/{memory_id}/confirm", response_model=MemoryRead)
async def confirm_memory(memory_id: int, db: AsyncSession = Depends(get_db)):
    memory = await db.get(Memory, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory.confirmed = True
    await db.commit()
    await db.refresh(memory)
    return memory
