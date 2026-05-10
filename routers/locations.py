from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import List

from database import get_db
from models import Location
from schemas import LocationCreate, LocationUpdate, LocationRead

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=List[LocationRead])
async def list_locations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Location).order_by(Location.name))
    return result.scalars().all()


@router.post("", response_model=LocationRead, status_code=201)
async def create_location(data: LocationCreate, db: AsyncSession = Depends(get_db)):
    location = Location(**data.model_dump())
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return location


@router.get("/{location_id}", response_model=LocationRead)
async def get_location(location_id: int, db: AsyncSession = Depends(get_db)):
    location = await db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.patch("/{location_id}", response_model=LocationRead)
async def update_location(location_id: int, data: LocationUpdate, db: AsyncSession = Depends(get_db)):
    location = await db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(location, field, value)
    location.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(location)
    return location


@router.delete("/{location_id}", status_code=204)
async def delete_location(location_id: int, db: AsyncSession = Depends(get_db)):
    location = await db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    await db.delete(location)
    await db.commit()
