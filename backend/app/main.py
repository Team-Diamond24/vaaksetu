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
      { type: "metadata",       data: CallMetadata }
      { type: "audio_playback", data: "<base64>" }
      { type: "interrupt" }
      { type: "transcript",     text, is_final }
    """
    await websocket.accept()
    session_id: str | None = None
    chunk_count = 0

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")

            if msg_type == "start_call":
                session_id = msg.get("session_id", "unknown")
                manager.active_connections[session_id] = websocket
                meta = call_service.create_session()
                meta = meta.model_copy(update={"session_id": session_id})
                await websocket.send_json({"type": "metadata", "data": meta.model_dump()})

            elif msg_type == "audio_chunk":
                chunk_count += 1
                # Placeholder: forward to STT service in production.
                # Every 20 chunks (~5 s) send a simulated transcript update.
                if chunk_count % 20 == 0 and session_id:
                    await websocket.send_json({
                        "type": "transcript",
                        "text": f"[audio received — {chunk_count} chunks]",
                        "is_final": False,
                    })

            elif msg_type == "end_call":
                if session_id:
                    manager.disconnect(session_id)
                await websocket.send_json({
                    "type": "transcript",
                    "text": "Call ended.",
                    "is_final": True,
                })
                break

    except WebSocketDisconnect:
        if session_id:
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


