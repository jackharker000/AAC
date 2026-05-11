from __future__ import annotations
import asyncio
import json
import io
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, init_db
from config import get_settings
from schemas import TTSRequest, PromptSuggestion
from routers import conversations, people, memories, locations, plans

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="AAC Communication Copilot", version="1.0.0", lifespan=lifespan)

app.include_router(conversations.router)
app.include_router(people.router)
app.include_router(memories.router)
app.include_router(locations.router)
app.include_router(plans.router)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("templates/index.html")


# ── WebSocket — live conversation ─────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: dict[int, list[WebSocket]] = {}

    async def connect(self, conv_id: int, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(conv_id, []).append(ws)

    def disconnect(self, conv_id: int, ws: WebSocket):
        if conv_id in self.active:
            self.active[conv_id].discard(ws) if hasattr(self.active[conv_id], 'discard') else None
            try:
                self.active[conv_id].remove(ws)
            except ValueError:
                pass

    async def broadcast(self, conv_id: int, message: dict):
        for ws in list(self.active.get(conv_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()

# Debounce state per conversation: track segment count at last prompt refresh
_last_prompt_refresh: dict[int, int] = {}
# MIME type reported by each WebSocket client (keyed by websocket id)
_ws_mime: dict[int, str] = {}


@app.websocket("/ws/{conv_id}")
async def websocket_endpoint(conv_id: int, websocket: WebSocket):
    await manager.connect(conv_id, websocket)
    ws_id = id(websocket)
    try:
        while True:
            msg = await websocket.receive()

            if msg["type"] == "websocket.receive":
                if "bytes" in msg and msg["bytes"]:
                    mime = _ws_mime.get(ws_id, "")
                    await _handle_audio_chunk(conv_id, msg["bytes"], websocket, mime)
                elif "text" in msg and msg["text"]:
                    try:
                        data = json.loads(msg["text"])
                        await _handle_control_message(conv_id, data, websocket, ws_id)
                    except json.JSONDecodeError:
                        pass

    except WebSocketDisconnect:
        manager.disconnect(conv_id, websocket)
        _ws_mime.pop(ws_id, None)


async def _handle_audio_chunk(conv_id: int, audio_bytes: bytes, websocket: WebSocket, mime_type: str = ""):
    """Transcribe audio chunk and push transcript + prompts back to client."""
    from services.transcription import transcribe_audio
    from database import AsyncSessionLocal
    from models import TranscriptSegment
    from sqlalchemy import select, func

    try:
        text = await transcribe_audio(audio_bytes, mime_type)
        if not text or not text.strip():
            return

        async with AsyncSessionLocal() as db:
            seg = TranscriptSegment(
                conversation_id=conv_id,
                text=text.strip(),
                speaker_label="Unknown Speaker",
                source="whisper",
                confidence=0.9,
            )
            db.add(seg)
            await db.commit()
            await db.refresh(seg)

            seg_count_result = await db.execute(
                select(func.count(TranscriptSegment.id))
                .where(TranscriptSegment.conversation_id == conv_id)
            )
            seg_count = seg_count_result.scalar() or 0

        await websocket.send_json({
            "type": "transcript",
            "id": seg.id,
            "text": seg.text,
            "speaker": seg.speaker_label,
            "timestamp": seg.timestamp.isoformat(),
        })

        # Debounce: refresh prompts after every 2 new segments
        last = _last_prompt_refresh.get(conv_id, 0)
        if seg_count - last >= 2:
            _last_prompt_refresh[conv_id] = seg_count
            await asyncio.sleep(1.5)
            await _push_prompts(conv_id, websocket)

    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})


async def _handle_control_message(conv_id: int, data: dict, websocket: WebSocket, ws_id: int = 0):
    action = data.get("action")

    if action == "set_mime_type":
        _ws_mime[ws_id] = data.get("mime_type", "")

    elif action == "refresh_prompts":
        await _push_prompts(conv_id, websocket)

    elif action == "name_detected":
        # Client detected a name in the transcript — send confirmation request
        await websocket.send_json({
            "type": "confirm_speaker",
            "detected_name": data.get("name", ""),
            "current_label": data.get("current_label", "Unknown Speaker"),
        })


async def _push_prompts(conv_id: int, websocket: WebSocket):
    from services.context_engine import build_context_packet
    from services.prompt_engine import generate_prompts
    from database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            context = await build_context_packet(conv_id, db)
        suggestions = await generate_prompts(context)
        await websocket.send_json({
            "type": "prompts",
            "suggestions": [s.model_dump() for s in suggestions],
        })
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Prompt error: {e}"})


# ── TTS endpoint ──────────────────────────────────────────────────────────────

@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    from services.tts_service import synthesize_speech
    try:
        audio_bytes = await synthesize_speech(request.text, request.voice_id)
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"},
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"TTS unavailable: {e}")


# ── Prompt generation endpoint (non-WebSocket fallback) ───────────────────────

@app.get("/conversations/{conv_id}/prompts", response_model=list[PromptSuggestion])
async def get_prompts(conv_id: int, plan_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    from services.context_engine import build_context_packet
    from services.prompt_engine import generate_prompts

    context = await build_context_packet(conv_id, db, plan_id=plan_id)
    return await generate_prompts(context)


# ── TTS availability check ───────────────────────────────────────────────────

@app.get("/tts/available")
async def tts_available():
    from services.tts_service import elevenlabs_available
    return {"available": elevenlabs_available()}


# ── ElevenLabs voice list ─────────────────────────────────────────────────────

@app.get("/tts/voices")
async def list_voices():
    try:
        from services.tts_service import list_voices as _list_voices
        return await _list_voices()
    except Exception as e:
        return {"voices": [], "error": str(e)}


@app.post("/tts/preview")
async def preview_voice(request: TTSRequest):
    """Preview a specific voice with sample text."""
    from services.tts_service import synthesize_speech
    text = request.text or "Hi, I'm James. Nice to meet you."
    try:
        audio_bytes = await synthesize_speech(text, request.voice_id)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
