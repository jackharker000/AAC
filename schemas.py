from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict


# ── Person ──────────────────────────────────────────────────────────────────

class PersonCreate(BaseModel):
    name: str
    relation: str = ""
    notes: str = ""
    usual_locations: List[int] = []
    first_met_date: Optional[datetime] = None
    confidence_level: float = 1.0


class PersonUpdate(BaseModel):
    name: Optional[str] = None
    relation: Optional[str] = None
    notes: Optional[str] = None
    usual_locations: Optional[List[int]] = None
    last_seen_date: Optional[datetime] = None
    confidence_level: Optional[float] = None


class PersonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    relation: str
    notes: str
    usual_locations: List[int]
    first_met_date: Optional[datetime]
    last_seen_date: Optional[datetime]
    confidence_level: float
    created_at: datetime
    updated_at: datetime


# ── Location ─────────────────────────────────────────────────────────────────

class LocationCreate(BaseModel):
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: str = ""
    notes: str = ""


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    latitude: Optional[float]
    longitude: Optional[float]
    address: str
    notes: str
    created_at: datetime
    updated_at: datetime


# ── Conversation ──────────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    location_id: Optional[int] = None
    people_present: List[int] = []


class ConversationUpdate(BaseModel):
    end_time: Optional[datetime] = None
    location_id: Optional[int] = None
    people_present: Optional[List[int]] = None
    summary: Optional[str] = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    start_time: datetime
    end_time: Optional[datetime]
    location_id: Optional[int]
    people_present: List[int]
    summary: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationRead):
    segments: List[TranscriptSegmentRead] = []
    outputs: List[JamesOutputRead] = []
    memories: List[MemoryRead] = []


# ── TranscriptSegment ─────────────────────────────────────────────────────────

class SegmentCreate(BaseModel):
    speaker_label: str = "Unknown Speaker"
    speaker_person_id: Optional[int] = None
    text: str
    confidence: float = 1.0
    source: str = "manual"


class SegmentUpdate(BaseModel):
    speaker_label: Optional[str] = None
    speaker_person_id: Optional[int] = None
    text: Optional[str] = None


class TranscriptSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    conversation_id: int
    timestamp: datetime
    speaker_label: str
    speaker_person_id: Optional[int]
    text: str
    confidence: float
    source: str


# ── JamesOutput ───────────────────────────────────────────────────────────────

class OutputCreate(BaseModel):
    typed_input: str = ""
    suggested_prompt: str = ""
    final_spoken_text: str
    was_edited: bool = False
    was_spoken: bool = True
    category: str = "reply"
    person_id: Optional[int] = None


class OutputRating(BaseModel):
    rating: int  # 1 or -1


class JamesOutputRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    conversation_id: int
    timestamp: datetime
    typed_input: str
    suggested_prompt: str
    final_spoken_text: str
    was_edited: bool
    was_spoken: bool
    category: str
    rating: Optional[int]


# ── Memory ────────────────────────────────────────────────────────────────────

class MemoryCreate(BaseModel):
    person_id: Optional[int] = None
    location_id: Optional[int] = None
    conversation_id: Optional[int] = None
    memory_text: str
    memory_type: str = "personal_fact"
    importance: int = 3
    confidence: float = 0.9
    source_text: str = ""
    confirmed: bool = False


class MemoryUpdate(BaseModel):
    memory_text: Optional[str] = None
    memory_type: Optional[str] = None
    importance: Optional[int] = None
    confidence: Optional[float] = None
    confirmed: Optional[bool] = None


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    person_id: Optional[int]
    location_id: Optional[int]
    conversation_id: Optional[int]
    memory_text: str
    memory_type: str
    importance: int
    confidence: float
    source_text: str
    confirmed: bool
    created_at: datetime
    last_used_at: Optional[datetime]


# ── PreConversationPlan ───────────────────────────────────────────────────────

class PlanCreate(BaseModel):
    title: str
    planned_date: Optional[datetime] = None
    people_expected: List[int] = []
    location_expected: str = ""
    topics_expected: List[str] = []
    things_to_say: List[str] = []
    questions_to_ask: List[str] = []
    tone: str = "friendly"
    notes: str = ""


class PlanUpdate(BaseModel):
    title: Optional[str] = None
    planned_date: Optional[datetime] = None
    people_expected: Optional[List[int]] = None
    location_expected: Optional[str] = None
    topics_expected: Optional[List[str]] = None
    things_to_say: Optional[List[str]] = None
    questions_to_ask: Optional[List[str]] = None
    tone: Optional[str] = None
    notes: Optional[str] = None
    conversation_id: Optional[int] = None


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    planned_date: Optional[datetime]
    people_expected: List[int]
    location_expected: str
    topics_expected: List[str]
    things_to_say: List[str]
    questions_to_ask: List[str]
    tone: str
    notes: str
    conversation_id: Optional[int]
    created_at: datetime


# ── Misc ──────────────────────────────────────────────────────────────────────

class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None


class PromptSuggestion(BaseModel):
    text: str
    category: str


class LabelSpeakerRequest(BaseModel):
    speaker_label: str
    person_id: Optional[int] = None
    create_person: bool = False
    new_person_name: Optional[str] = None


class SpeakerConfirmRequest(BaseModel):
    current_label: str
    person_id: int


# Resolve forward references
ConversationDetail.model_rebuild()
