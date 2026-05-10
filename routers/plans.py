from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, date
from typing import List, Optional

from database import get_db
from models import PreConversationPlan, Person
from schemas import PlanCreate, PlanUpdate, PlanRead, PromptSuggestion

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("", response_model=List[PlanRead])
async def list_plans(
    upcoming_only: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    q = select(PreConversationPlan).order_by(PreConversationPlan.planned_date.desc())
    if upcoming_only:
        q = q.where(PreConversationPlan.planned_date >= datetime.utcnow())
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=PlanRead, status_code=201)
async def create_plan(data: PlanCreate, db: AsyncSession = Depends(get_db)):
    plan = PreConversationPlan(**data.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.get("/today", response_model=List[PlanRead])
async def get_todays_plans(db: AsyncSession = Depends(get_db)):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59)
    result = await db.execute(
        select(PreConversationPlan)
        .where(PreConversationPlan.planned_date >= today_start)
        .where(PreConversationPlan.planned_date <= today_end)
        .where(PreConversationPlan.conversation_id == None)
    )
    return result.scalars().all()


@router.get("/{plan_id}", response_model=PlanRead)
async def get_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    plan = await db.get(PreConversationPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.patch("/{plan_id}", response_model=PlanRead)
async def update_plan(plan_id: int, data: PlanUpdate, db: AsyncSession = Depends(get_db)):
    plan = await db.get(PreConversationPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(plan, field, value)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.delete("/{plan_id}", status_code=204)
async def delete_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    plan = await db.get(PreConversationPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    await db.delete(plan)
    await db.commit()


@router.post("/{plan_id}/preview-prompts", response_model=List[PromptSuggestion])
async def preview_plan_prompts(plan_id: int, db: AsyncSession = Depends(get_db)):
    """Generate a preview of prompts that would be suggested using this plan."""
    plan = await db.get(PreConversationPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    from services.context_engine import build_plan_context_packet
    from services.prompt_engine import generate_prompts

    context = await build_plan_context_packet(plan, db)
    prompts = await generate_prompts(context)
    return prompts
