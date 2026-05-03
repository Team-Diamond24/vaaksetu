"""
Vaaksetu — FastAPI backend entry point.

Run with:
    uvicorn app.main:app --reload
"""

import asyncio
from contextlib import asynccontextmanager
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import sqlite3

from app.config import settings
from app.models import CallMetadata
import base64

from app.services.call_service import call_service, CallState
from app.services.transcription_service import transcription_service
from app.services.reasoning_service import reasoning_service
from app.services.speech_service import speech_service
from app.services.acoustic_service import acoustic_service
from app.services.analytics_service import analytics_service
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
# TTS helper — stream audio chunks to the frontend
# ---------------------------------------------------------------------------
async def _stream_tts(websocket: WebSocket, text: str, lang: str) -> None:
    """Synthesize text and stream audio_chunk messages, followed by audio_done."""
    try:
        async for b64_chunk in speech_service.synthesize(text, lang):
            await websocket.send_json({
                "type": "audio_chunk",
                "data": b64_chunk,
            })
        await websocket.send_json({"type": "audio_done"})
    except Exception as tts_exc:
        print(f"[TTS] Speech synthesis error: {tts_exc}")
        await websocket.send_json({
            "type": "error",
            "message": "Speech synthesis failed",
        })


# ---------------------------------------------------------------------------
# State-change helper — emit state to frontend
# ---------------------------------------------------------------------------
async def _emit_state(websocket: WebSocket, session_id: str, state: CallState) -> None:
    """Send a state_change message so the frontend can update UI."""
    await websocket.send_json({
        "type": "state_change",
        "state": state.value,
        "session_id": session_id,
    })


# ---------------------------------------------------------------------------
# Confirmation TTS messages (multilingual)
# ---------------------------------------------------------------------------
CONFIRMED_MESSAGES = {
    "en": "Thank you for confirming. We are taking action on your report immediately.",
    "hi": "पुष्टि के लिए धन्यवाद। हम आपकी रिपोर्ट पर तुरंत कार्रवाई कर रहे हैं।",
    "kn": "ದೃಢೀಕರಿಸಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ನಿಮ್ಮ ವರದಿಯ ಮೇಲೆ ನಾವು ತಕ್ಷಣ ಕ್ರಮ ತೆಗೆದುಕೊಳ್ಳುತ್ತಿದ್ದೇವೆ.",
}

DENIED_MESSAGES = {
    "en": "I apologize for the misunderstanding. Could you please repeat the details so I can be sure?",
    "hi": "गलतफहमी के लिए क्षमा करें। कृपया विवरण दोबारा बताएं ताकि मैं सही समझ सकूं।",
    "kn": "ತಪ್ಪು ತಿಳುವಳಿಕೆಗೆ ಕ್ಷಮಿಸಿ. ನಾನು ಸರಿಯಾಗಿ ಅರ್ಥಮಾಡಿಕೊಳ್ಳಲು ದಯವಿಟ್ಟು ವಿವರಗಳನ್ನು ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ.",
}

FALLBACK_TECHNICAL_GLITCH_MESSAGE = (
    "I am experiencing a technical glitch, connecting you to an operator immediately."
)
API_GUARD_TIMEOUT_SECONDS = 4.0


def _resolve_sqlite_path() -> Path | None:
    """Resolve sqlite file path from app database_url, if configured."""
    if not settings.database_url.startswith("sqlite:///"):
        return None
    db_path = settings.database_url.removeprefix("sqlite:///")
    return Path(db_path).resolve()


def _write_transcript_row(
    session_id: str,
    transcript: str,
    call_state: str,
) -> None:
    """Persist transcript to local sqlite for later analytics/replay."""
    db_path = _resolve_sqlite_path()
    if db_path is None:
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                transcript TEXT NOT NULL,
                call_state TEXT NOT NULL,
                analytics_report TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(transcript_events)").fetchall()
        }
        if "analytics_report" not in columns:
            conn.execute(
                "ALTER TABLE transcript_events ADD COLUMN analytics_report TEXT"
            )
        conn.execute(
            """
            INSERT INTO transcript_events (session_id, transcript, call_state)
            VALUES (?, ?, ?)
            """,
            (session_id, transcript, call_state),
        )
        conn.commit()


def _read_session_transcript_timeline(session_id: str) -> str:
    """Build chronological transcript timeline for a session."""
    db_path = _resolve_sqlite_path()
    if db_path is None:
        return ""
    if not db_path.exists():
        return ""
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                transcript TEXT NOT NULL,
                call_state TEXT NOT NULL,
                analytics_report TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        rows = conn.execute(
            """
            SELECT call_state, transcript
            FROM transcript_events
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
    return "\n".join([f"[{state}] {text}" for state, text in rows])


def _write_final_report(session_id: str, report_json: str) -> None:
    """Persist final post-call report to session rows."""
    db_path = _resolve_sqlite_path()
    if db_path is None:
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                transcript TEXT NOT NULL,
                call_state TEXT NOT NULL,
                analytics_report TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(transcript_events)").fetchall()
        }
        if "analytics_report" not in columns:
            conn.execute(
                "ALTER TABLE transcript_events ADD COLUMN analytics_report TEXT"
            )
        conn.execute(
            """
            UPDATE transcript_events
            SET analytics_report = ?
            WHERE session_id = ?
            """,
            (report_json, session_id),
        )
        updated = conn.total_changes
        if updated == 0:
            conn.execute(
                """
                INSERT INTO transcript_events
                (session_id, transcript, call_state, analytics_report)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, "[NO TRANSCRIPT]", "END_CALL", report_json),
            )
        conn.commit()


async def _log_and_persist_transcript(
    session_id: str,
    transcript: str,
    call_state: CallState,
) -> None:
    """Background-safe transcript logging/persistence path."""
    print(
        f"[Transcript] session={session_id} state={call_state.value} text={transcript}"
    )
    await asyncio.to_thread(
        _write_transcript_row,
        session_id,
        transcript,
        call_state.value,
    )


async def _activate_resilience_takeover(
    websocket: WebSocket,
    session_id: str,
    reason: str,
) -> None:
    """Play fallback message once, then force AI mute for instant human takeover."""
    session = call_service.get_session(session_id)
    if session and session.fallback_triggered:
        return
    if session:
        session.fallback_triggered = True

    print(f"[Resilience] takeover session={session_id} reason={reason}")
    await _stream_tts(websocket, FALLBACK_TECHNICAL_GLITCH_MESSAGE, "en")
    muted = call_service.set_muted(session_id, True)
    updated = call_service.get_session(session_id)
    await websocket.send_json({
        "type": "metadata",
        "data": {
            "session_id": session_id,
            "is_user_speaking": False,
            "detected_sentiment": "neutral",
            "requires_confirmation": False,
            "is_muted": muted,
            "distress_level": updated.last_urgency if updated else 1,
            "environment": "quiet",
        },
    })


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
      { type: "state_change",      state, session_id }
    """
    await websocket.accept()
    session_id: str | None = None
    was_speaking = False  # track transitions for metadata events

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")

            # ==============================================================
            # START CALL
            # ==============================================================
            if msg_type == "start_call":
                session_id = msg.get("session_id", "unknown")
                manager.active_connections[session_id] = websocket
                transcription_service.start_session(session_id)
                acoustic_service.start_session(session_id)
                meta = call_service.create_session(session_id)
                await websocket.send_json(
                    {"type": "metadata", "data": meta.model_dump()}
                )
                # Emit initial state
                await _emit_state(websocket, session_id, CallState.LISTENING)

            # ==============================================================
            # AUDIO CHUNK
            # ==============================================================
            elif msg_type == "audio_chunk" and session_id:
                raw_b64 = msg.get("data", "")
                try:
                    result = await asyncio.wait_for(
                        transcription_service.feed_chunk(session_id, raw_b64),
                        timeout=API_GUARD_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    await _activate_resilience_takeover(
                        websocket,
                        session_id,
                        f"Groq timeout/error: {exc}",
                    )
                    continue

                # --- Acoustic analysis on every chunk ---
                try:
                    pcm_bytes = base64.b64decode(raw_b64)
                except Exception:
                    pcm_bytes = b""
                buf = transcription_service._sessions.get(session_id)
                is_speaking = buf.is_speaking if buf else False
                acoustic = acoustic_service.analyze_chunk(
                    session_id, pcm_bytes, is_speaking
                )

                # Emit speaking-state + acoustic changes
                if is_speaking != was_speaking:
                    was_speaking = is_speaking
                    session = call_service.get_session(session_id)
                    await websocket.send_json({
                        "type": "metadata",
                        "data": {
                            "session_id": session_id,
                            "is_user_speaking": is_speaking,
                            "detected_sentiment": "neutral",
                            "requires_confirmation": False,
                            "is_muted": session.is_muted if session else False,
                            "distress_level": acoustic.distress_level,
                            "environment": acoustic.environment,
                        },
                    })

                # Emit acoustic update periodically (every 4th chunk ≈ 1s)
                if acoustic_service._sessions.get(session_id) and \
                   acoustic_service._sessions[session_id].chunk_count % 4 == 0:
                    await websocket.send_json({
                        "type": "acoustic_update",
                        "data": {
                            "distress_level": acoustic.distress_level,
                            "environment": acoustic.environment,
                            "is_high_distress": acoustic.is_high_distress,
                            "loudness": acoustic.loudness_label,
                            "rms": acoustic.rms,
                            "zcr": acoustic.zcr,
                        },
                    })

                # If the service returned a transcript, send it
                if result and not result.skipped and not result.text:
                    await _activate_resilience_takeover(
                        websocket,
                        session_id,
                        "Groq returned empty transcript",
                    )
                    continue

                if result and not result.skipped and result.text:
                    await websocket.send_json({
                        "type": "transcript",
                        "text": result.text,
                        "is_final": result.is_final,
                    })

                    # ---- Get current session state ----
                    current_state = call_service.get_state(session_id)

                    # ==================================================
                    # STATE: VERIFYING — binary confirmation only
                    # ==================================================
                    if current_state == CallState.VERIFYING:
                        try:
                            confirmation, _ = await asyncio.gather(
                                asyncio.wait_for(
                                    reasoning_service.check_confirmation(result.text),
                                    timeout=API_GUARD_TIMEOUT_SECONDS,
                                ),
                                _log_and_persist_transcript(
                                    session_id,
                                    result.text,
                                    current_state,
                                ),
                            )
                        except Exception as exc:
                            await _activate_resilience_takeover(
                                websocket,
                                session_id,
                                f"Gemini confirmation timeout/error: {exc}",
                            )
                            continue
                        if confirmation is None:
                            await _activate_resilience_takeover(
                                websocket,
                                session_id,
                                "Gemini confirmation failed",
                            )
                            continue

                        if confirmation and confirmation.confirmed:
                            # ✅ User confirmed → CONFIRMED
                            call_service.transition_to_confirmed(session_id)
                            await _emit_state(websocket, session_id, CallState.CONFIRMED)

                            lang = confirmation.language_code or "en"
                            confirm_msg = CONFIRMED_MESSAGES.get(lang, CONFIRMED_MESSAGES["en"])
                            transcription_service.clear_buffer(session_id)
                            session = call_service.get_session(session_id)
                            if not (session and session.is_muted):
                                await _stream_tts(websocket, confirm_msg, lang)

                        elif confirmation and confirmation.is_denial:
                            # ❌ User denied → back to LISTENING
                            call_service.transition_to_listening(session_id)
                            await _emit_state(websocket, session_id, CallState.LISTENING)

                            lang = confirmation.language_code or "en"
                            deny_msg = DENIED_MESSAGES.get(lang, DENIED_MESSAGES["en"])
                            transcription_service.clear_buffer(session_id)
                            session = call_service.get_session(session_id)
                            if not (session and session.is_muted):
                                await _stream_tts(websocket, deny_msg, lang)

                        else:
                            # 🤷 Ambiguous — re-prompt for confirmation
                            session = call_service.get_session(session_id)
                            lang = session.last_language_code if session else "en"
                            transcription_service.clear_buffer(session_id)
                            if not (session and session.is_muted):
                                await _stream_tts(
                                    websocket,
                                    "Could you please say Yes or No to confirm?",
                                    lang,
                                )

                    # ==================================================
                    # STATE: LISTENING — full triage analysis
                    # ==================================================
                    elif current_state == CallState.LISTENING:
                        try:
                            reasoning, _ = await asyncio.gather(
                                asyncio.wait_for(
                                    reasoning_service.analyze(result.text),
                                    timeout=API_GUARD_TIMEOUT_SECONDS,
                                ),
                                _log_and_persist_transcript(
                                    session_id,
                                    result.text,
                                    current_state,
                                ),
                            )
                        except Exception as exc:
                            await _activate_resilience_takeover(
                                websocket,
                                session_id,
                                f"Gemini reasoning timeout/error: {exc}",
                            )
                            continue
                        if reasoning is None:
                            await _activate_resilience_takeover(
                                websocket,
                                session_id,
                                "Gemini reasoning failed",
                            )
                            continue
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
                                "is_muted": call_service.get_session(session_id).is_muted
                                if call_service.get_session(session_id)
                                else False,
                            },
                        })

                            # If needs_verification → transition to VERIFYING
                        if reasoning.needs_verification:
                            call_service.transition_to_verifying(
                                session_id,
                                restatement=reasoning.restatement,
                                language_code=reasoning.language_code,
                                intent=reasoning.intent,
                                urgency=reasoning.urgency_level,
                            )
                            await _emit_state(websocket, session_id, CallState.VERIFYING)

                            # TTS: speak the restatement
                        if reasoning.restatement:
                            transcription_service.clear_buffer(session_id)
                            session = call_service.get_session(session_id)
                            if not (session and session.is_muted):
                                await _stream_tts(
                                    websocket,
                                    reasoning.restatement,
                                    reasoning.language_code,
                                )

                    # ==================================================
                    # STATE: CONFIRMED — already confirmed, no new analysis
                    # ==================================================
                    elif current_state == CallState.CONFIRMED:
                        await _log_and_persist_transcript(
                            session_id,
                            result.text,
                            current_state,
                        )
                        # Could handle follow-up questions here in the future
                        pass

            # ==============================================================
            # TOGGLE TAKEOVER (AI mute)
            # ==============================================================
            elif msg_type == "TOGGLE_TAKEOVER" and session_id:
                muted = call_service.toggle_mute(session_id)
                session = call_service.get_session(session_id)
                await websocket.send_json({
                    "type": "metadata",
                    "data": {
                        "session_id": session_id,
                        "is_user_speaking": False,
                        "detected_sentiment": "neutral",
                        "requires_confirmation": False,
                        "is_muted": muted,
                        "distress_level": 1 if session is None else session.last_urgency,
                        "environment": "quiet",
                    },
                })

            # ==============================================================
            # END CALL
            # ==============================================================
            elif msg_type == "end_call":
                if session_id:
                    timeline = await asyncio.to_thread(
                        _read_session_transcript_timeline, session_id
                    )
                    report = None
                    try:
                        report = await asyncio.wait_for(
                            analytics_service.post_mortem(timeline),
                            timeout=API_GUARD_TIMEOUT_SECONDS,
                        )
                    except Exception as exc:
                        print(f"[Analytics] post-mortem timeout/error: {exc}")

                    if report:
                        report_payload = report.model_dump()
                    else:
                        report_payload = {
                            "understanding_score": 3,
                            "cultural_accuracy": 3,
                            "bottleneck_detected": "Analytics service unavailable during closeout",
                            "coaching_tip": "Escalate to the operator earlier when AI response latency exceeds safe limits.",
                        }
                    await websocket.send_json({
                        "type": "call_summary",
                        "data": report_payload,
                    })
                    await asyncio.to_thread(
                        _write_final_report,
                        session_id,
                        json.dumps(report_payload, ensure_ascii=False),
                    )

                    transcription_service.end_session(session_id)
                    acoustic_service.end_session(session_id)
                    call_service.end_session(session_id)
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
            acoustic_service.end_session(session_id)
            call_service.end_session(session_id)
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
