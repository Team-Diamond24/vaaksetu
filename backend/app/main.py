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
    print(f"🚀  Vaaksetu backend starting ({settings.app_env})")
    yield
    print("👋  Vaaksetu backend shutting down")


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
# WebSocket endpoint
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
