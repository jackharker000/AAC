import json
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from database import Base


class Person(Base):
    __tablename__ = "people"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    relation = Column(String(255), default="")
    notes = Column(Text, default="")
    usual_locations = Column(JSON, default=list)   # list of location IDs
    first_met_date = Column(DateTime, nullable=True)
    last_seen_date = Column(DateTime, nullable=True)
    confidence_level = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    memories = relationship("Memory", back_populates="person", cascade="all, delete-orphan")
    outputs = relationship("JamesOutput", back_populates="person")


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    address = Column(String(512), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversations = relationship("Conversation", back_populates="location")
    memories = relationship("Memory", back_populates="location")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    people_present = Column(JSON, default=list)   # list of person IDs
    summary = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    location = relationship("Location", back_populates="conversations")
    segments = relationship("TranscriptSegment", back_populates="conversation", cascade="all, delete-orphan", order_by="TranscriptSegment.timestamp")
    outputs = relationship("JamesOutput", back_populates="conversation", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="conversation")
    plans = relationship("PreConversationPlan", back_populates="conversation")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    speaker_label = Column(String(255), default="Unknown Speaker")
    speaker_person_id = Column(Integer, ForeignKey("people.id"), nullable=True)
    text = Column(Text, nullable=False)
    confidence = Column(Float, default=1.0)
    source = Column(String(50), default="whisper")  # whisper | manual

    conversation = relationship("Conversation", back_populates="segments")
    speaker = relationship("Person", foreign_keys=[speaker_person_id])


class JamesOutput(Base):
    __tablename__ = "james_outputs"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("people.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    typed_input = Column(Text, default="")
    suggested_prompt = Column(Text, default="")
    final_spoken_text = Column(Text, nullable=False)
    was_edited = Column(Boolean, default=False)
    was_spoken = Column(Boolean, default=True)
    category = Column(String(100), default="reply")
    rating = Column(Integer, nullable=True)   # 1 = thumbs up, -1 = thumbs down

    conversation = relationship("Conversation", back_populates="outputs")
    person = relationship("Person", back_populates="outputs")


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("people.id"), nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    memory_text = Column(Text, nullable=False)
    memory_type = Column(String(100), default="personal_fact")
    # types: personal_fact | preference | follow_up | location_routine | james_goal | relationship | open_issue | conversation_topic
    importance = Column(Integer, default=3)   # 1–5
    confidence = Column(Float, default=0.9)   # 0–1
    source_text = Column(Text, default="")
    confirmed = Column(Boolean, default=False)  # user has reviewed
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    person = relationship("Person", back_populates="memories")
    location = relationship("Location", back_populates="memories")
    conversation = relationship("Conversation", back_populates="memories")


class PreConversationPlan(Base):
    __tablename__ = "pre_conversation_plans"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    planned_date = Column(DateTime, nullable=True)
    people_expected = Column(JSON, default=list)   # list of person IDs
    location_expected = Column(String(255), default="")
    topics_expected = Column(JSON, default=list)
    things_to_say = Column(JSON, default=list)
    questions_to_ask = Column(JSON, default=list)
    tone = Column(String(100), default="friendly")  # friendly | formal | relaxed | curious
    notes = Column(Text, default="")
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="plans")
