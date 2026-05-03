"""
Vaaksetu — FastAPI backend entry point.

Run with:
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models import CallMetadata
from app.services.call_service import call_service
from app.services.transcription_service import transcription_service
from app.services.reasoning_service import reasoning_service
from app.services.speech_service import speech_service
from app.websockets.connection import manager


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    print(f"[START] Vaaksetu backend starting ({settings.app_env})")
    yield
    print("[STOP] Vaaksetu backend shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Vaaksetu API",
    version="0.1.0",
    description="Real-time voice AI call assistant backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    return {"status": "ok", "service": "vaaksetu"}


@app.get("/health")
async def health():
    return {"status": "healthy", "env": settings.app_env}


@app.post("/api/session", response_model=CallMetadata)
async def create_session():
    """Create a new call session and return its metadata."""
    return call_service.create_session()


# ---------------------------------------------------------------------------
# WebSocket endpoint for VoiceClient audio streaming
# NOTE: Must be registered BEFORE /ws/{session_id} to avoid path conflict.
# ---------------------------------------------------------------------------
@app.websocket("/ws/call")
async def ws_call(websocket: WebSocket):
    """
    Audio-streaming WebSocket used by the VoiceClient component.

    Client messages:
      { type: "start_call", session_id }
      { type: "audio_chunk", data: "<base64 Int16 PCM>", session_id }
      { type: "end_call",   session_id }

    Server messages:
      { type: "metadata",          data: CallMetadata }
      { type: "audio_playback",    data: "<base64>" }
      { type: "audio_chunk",       data: "<base64 MP3 chunk>" }
      { type: "audio_done" }
      { type: "interrupt" }
      { type: "transcript",        text, is_final }
      { type: "reasoning_update",  data: ReasoningOutput }
    """
    await websocket.accept()
    session_id: str | None = None
    was_speaking = False  # track transitions for metadata events

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")

            if msg_type == "start_call":
                session_id = msg.get("session_id", "unknown")
                manager.active_connections[session_id] = websocket
                transcription_service.start_session(session_id)
                meta = call_service.create_session()
                meta = meta.model_copy(update={"session_id": session_id})
                await websocket.send_json(
                    {"type": "metadata", "data": meta.model_dump()}
                )

            elif msg_type == "audio_chunk" and session_id:
                result = await transcription_service.feed_chunk(
                    session_id, msg.get("data", "")
                )

                # Emit speaking-state changes so the frontend can update UI
                buf = transcription_service._sessions.get(session_id)
                is_speaking = buf.is_speaking if buf else False
                if is_speaking != was_speaking:
                    was_speaking = is_speaking
                    await websocket.send_json({
                        "type": "metadata",
                        "data": {
                            "session_id": session_id,
                            "is_user_speaking": is_speaking,
                            "detected_sentiment": "neutral",
                            "requires_confirmation": False,
                        },
                    })

                # If the service returned a transcript, send it
                if result and not result.skipped and result.text:
                    await websocket.send_json({
                        "type": "transcript",
                        "text": result.text,
                        "is_final": result.is_final,
                    })

                    # --- Reasoning pipeline ---
                    reasoning = await reasoning_service.analyze(result.text)
                    if reasoning:
                        await websocket.send_json({
                            "type": "reasoning_update",
                            "data": reasoning.model_dump(),
                        })

                        # Propagate sentiment back as metadata
                        await websocket.send_json({
                            "type": "metadata",
                            "data": {
                                "session_id": session_id,
                                "is_user_speaking": False,
                                "detected_sentiment": reasoning.sentiment,
                                "requires_confirmation": reasoning.needs_verification,
                            },
                        })

                        # --- TTS pipeline: stream audio back ---
                        if reasoning.restatement:
                            try:
                                async for b64_chunk in speech_service.synthesize(
                                    reasoning.restatement,
                                    reasoning.language_code,
                                ):
                                    await websocket.send_json({
                                        "type": "audio_chunk",
                                        "data": b64_chunk,
                                    })
                                # Notify frontend that all chunks have been sent
                                await websocket.send_json({"type": "audio_done"})
                            except Exception as tts_exc:
                                print(f"[TTS] Speech synthesis error: {tts_exc}")
                                await websocket.send_json({
                                    "type": "error",
                                    "message": "Speech synthesis failed",
                                })

            elif msg_type == "end_call":
                if session_id:
                    transcription_service.end_session(session_id)
                    manager.disconnect(session_id)
                await websocket.send_json({
                    "type": "transcript",
                    "text": "Call ended.",
                    "is_final": True,
                })
                break

    except WebSocketDisconnect:
        if session_id:
            transcription_service.end_session(session_id)
            manager.disconnect(session_id)


# ---------------------------------------------------------------------------
# WebSocket endpoint (generic)
# ---------------------------------------------------------------------------
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time call communication.
    Clients connect with their session_id and exchange CallMetadata.
    """
    await manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_json()
            metadata = CallMetadata(**data)
            # Echo back (in a real app, process & route through services)
            await manager.send_metadata(session_id, metadata)
    except WebSocketDisconnect:
        manager.disconnect(session_id)


