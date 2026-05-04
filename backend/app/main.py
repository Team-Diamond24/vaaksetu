"""
Vaaksetu FastAPI backend entry point.

Run with:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import sqlite3
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from app.config import settings
from app.models import CallMetadata
from app.services.acoustic_service import acoustic_service
from app.services.analytics_service import analytics_service
from app.services.call_service import CallState, GREETING_TEXT, call_service
from app.services.reasoning_service import reasoning_service
from app.services.speech_service import speech_service
from app.services.transcription_service import transcription_service
from app.websockets.connection import manager

logger = logging.getLogger(__name__)


VERIFY_PROMPTS = {
    "en": "Please say Yes or No to confirm.",
    "hi": "\u0926\u092f\u093e \u0915\u0930\u0915\u0947 \u0939\u093e\u0901 \u092f\u093e \u0928\u0939\u0940\u0902 \u0915\u0939\u0915\u0930 \u092a\u0941\u0937\u094d\u091f\u093f \u0915\u0930\u0947\u0902.",
    "kn": "\u0ca6\u0caf\u0cb5\u0cbf\u0c9f\u0ccd\u0c9f\u0cc1 \u0cb9\u0ccc\u0ca6\u0cc1 \u0c85\u0ca5\u0cb5\u0cbe \u0c87\u0cb2\u0ccd\u0cb2 \u0c8e\u0c82\u0ca6\u0cc1 \u0cb9\u0cc7\u0cb3\u0abf \u0ca6\u0cc3\u0ca2\u0ac0\u0c95\u0cb0\u0cbf\u0cb8\u0abf.",
}
DENIED_MESSAGES = {
    "en": "I did not get that correctly. Please repeat the emergency details.",
    "hi": "\u092e\u0941\u091d\u0947 \u092f\u0939 \u0938\u0939\u0940 \u0938\u0947 \u0938\u092e\u091d \u0928\u0939\u0940\u0902 \u0906\u092f\u093e. \u0915\u0943\u092a\u092f\u093e \u0906\u092a\u093e\u0924 \u0938\u094d\u0925\u093f\u0924\u093f \u0915\u0947 \u0935\u093f\u0935\u0930\u0923 \u092b\u093f\u0930 \u0938\u0947 \u092c\u0924\u093e\u090f\u0902.",
    "kn": "\u0ca8\u0ca8\u0c97\u0cc6 \u0c87\u0ca6\u0cc1 \u0cb8\u0cb0\u0abf\u0caf\u0cbe\u0c97\u0abf \u0c85\u0cb0\u0ccd\u0ca5\u0cb5\u0cbe\u0c97\u0cb2\u0abf\u0cb2\u0ccd\u0cb2. \u0ca6\u0caf\u0cb5\u0cbf\u0c9f\u0ccd\u0c9f\u0cc1 \u0ca4\u0cc1\u0cb0\u0ccd\u0ca4\u0cc1 \u0cb8\u0cae\u0cb8\u0ccd\u0caf\u0cc6\u0caf \u0cb5\u0cbf\u0cb5\u0cb0\u0ca8\u0ccd\u0ca8\u0cc1 \u0cae\u0ca4\u0ccd\u0ca4\u0cca\u0cae\u0ccd\u0cae\u0cc6 \u0cb9\u0cc7\u0cb3\u0abf.",
}
FALLBACK_TECHNICAL_GLITCH_MESSAGE = (
    "I am experiencing a technical glitch, connecting you to an operator immediately."
)
STT_TIMEOUT_SECONDS = 4.0
LLM_TIMEOUT_SECONDS = 12.0
ANALYTICS_TIMEOUT_SECONDS = 12.0
FILLER_WORDS = {
    "okay",
    "ok",
    "hmm",
    "huh",
    "ji",
    "sari",
    "haan",
    "ha",
    "hmmm",
    "umm",
    "uh",
    "huhh",
    "achha",
    "acha",
    "hello",
    "yes",
    "no",
}
MEANINGFUL_HINT_WORDS = {
    "road",
    "street",
    "area",
    "near",
    "house",
    "home",
    "school",
    "hospital",
    "injury",
    "accident",
    "fire",
    "theft",
    "assault",
    "bleeding",
    "help",
    "water",
    "electricity",
    "danger",
    "location",
    "address",
    "problem",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[START] Vaaksetu backend starting ({settings.app_env})")
    call_service.ensure_complaints_file()
    greeting_audio = await speech_service.synthesize_full(GREETING_TEXT, "en")
    call_service.set_cached_greeting_audio(greeting_audio)
    yield
    print("[STOP] Vaaksetu backend shutting down")


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


@app.get("/")
async def root():
    return {"status": "ok", "service": "vaaksetu"}


@app.get("/health")
async def health():
    return {"status": "healthy", "env": settings.app_env}


@app.post("/api/session", response_model=CallMetadata)
async def create_session():
    return call_service.create_session()


@app.get("/api/complaints")
async def get_complaints():
    return call_service.read_complaints()


async def _stream_tts(websocket: WebSocket, text: str, lang: str) -> None:
    try:
        async for b64_chunk in speech_service.synthesize(text, lang):
            if not await _safe_send_json(websocket, {"type": "audio_chunk", "data": b64_chunk}):
                return
        await _safe_send_json(websocket, {"type": "audio_done"})
    except Exception as exc:
        logger.exception("[TTS] Speech synthesis error")
        await _safe_send_json(websocket, {"type": "error", "message": "Speech synthesis failed"})


async def _speak_and_record(
    websocket: WebSocket,
    session_id: str,
    text: str,
    lang: str,
    *,
    prebuilt_audio: str | None = None,
) -> None:
    if not text or not text.strip():
        return
    call_service.append_assistant_turn(session_id, text)
    if prebuilt_audio:
        if await _safe_send_json(websocket, {"type": "audio_chunk", "data": prebuilt_audio}):
            await _safe_send_json(websocket, {"type": "audio_done"})
        return
    await _stream_tts(websocket, text, lang)


async def _emit_state(websocket: WebSocket, session_id: str, state: CallState) -> None:
    await _safe_send_json(
        websocket,
        {"type": "state_change", "state": state.value, "session_id": session_id}
    )


async def _safe_send_json(websocket: WebSocket, payload: dict) -> bool:
    if websocket.client_state == WebSocketState.DISCONNECTED:
        return False
    if websocket.application_state == WebSocketState.DISCONNECTED:
        return False
    try:
        await websocket.send_json(payload)
        return True
    except RuntimeError as exc:
        logger.warning("[WebSocket] send skipped: %s", exc)
        return False
    except WebSocketDisconnect:
        return False


def _resolve_sqlite_path() -> Path | None:
    if not settings.database_url.startswith("sqlite:///"):
        return None
    db_path = settings.database_url.removeprefix("sqlite:///")
    return Path(db_path).resolve()


def _write_transcript_row(session_id: str, transcript: str, call_state: str) -> None:
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
            row[1] for row in conn.execute("PRAGMA table_info(transcript_events)").fetchall()
        }
        if "analytics_report" not in columns:
            conn.execute("ALTER TABLE transcript_events ADD COLUMN analytics_report TEXT")
        conn.execute(
            """
            INSERT INTO transcript_events (session_id, transcript, call_state)
            VALUES (?, ?, ?)
            """,
            (session_id, transcript, call_state),
        )
        conn.commit()


def _read_session_transcript_timeline(session_id: str) -> str:
    db_path = _resolve_sqlite_path()
    if db_path is None or not db_path.exists():
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
    return "\n".join(f"[{state}] {text}" for state, text in rows)


def _write_final_report(session_id: str, report_json: str) -> None:
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
            row[1] for row in conn.execute("PRAGMA table_info(transcript_events)").fetchall()
        }
        if "analytics_report" not in columns:
            conn.execute("ALTER TABLE transcript_events ADD COLUMN analytics_report TEXT")
        conn.execute(
            """
            UPDATE transcript_events
            SET analytics_report = ?
            WHERE session_id = ?
            """,
            (report_json, session_id),
        )
        if conn.total_changes == 0:
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
    print(f"[Transcript] session={session_id} state={call_state.value} text={transcript}")
    await asyncio.to_thread(_write_transcript_row, session_id, transcript, call_state.value)


def _sentiment_from_distress(distress_level: int) -> str:
    if distress_level >= 4:
        return "distressed"
    if distress_level == 3:
        return "fearful"
    return "neutral"


def _localized_verify_prompt(language_code: str) -> str:
    return VERIFY_PROMPTS.get(language_code, VERIFY_PROMPTS["en"])


def _localized_denied_message(language_code: str) -> str:
    return DENIED_MESSAGES.get(language_code, DENIED_MESSAGES["en"])


def _build_metadata_payload(
    session_id: str,
    *,
    is_user_speaking: bool,
    requires_confirmation: bool,
    detected_sentiment: str | None = None,
) -> dict:
    session = call_service.get_session(session_id)
    distress_level = 1 if session is None else session.last_distress_level
    environment = "quiet" if session is None else session.last_environment
    return {
        "session_id": session_id,
        "is_user_speaking": is_user_speaking,
        "detected_sentiment": detected_sentiment or _sentiment_from_distress(distress_level),
        "requires_confirmation": requires_confirmation,
        "is_muted": False if session is None else session.is_muted,
        "distress_level": distress_level,
        "environment": environment,
    }


async def _activate_resilience_takeover(
    websocket: WebSocket,
    session_id: str,
    reason: str,
) -> None:
    session = call_service.get_session(session_id)
    if session and session.fallback_triggered:
        return
    if session:
        session.fallback_triggered = True

    print(f"[Resilience] takeover session={session_id} reason={reason}")
    await _speak_and_record(
        websocket,
        session_id,
        FALLBACK_TECHNICAL_GLITCH_MESSAGE,
        "en",
    )
    call_service.set_muted(session_id, True)
    call_service.transition_to_escalated(session_id)
    await _emit_state(websocket, session_id, CallState.ESCALATED)
    await _safe_send_json(
        websocket,
        {"type": "metadata", "data": _build_metadata_payload(
            session_id,
            is_user_speaking=False,
            requires_confirmation=False,
        )},
    )


def _tokenize_transcript(transcript: str) -> list[str]:
    return re.findall(r"[\w']+", transcript.lower())


def _has_meaningful_content(transcript: str) -> bool:
    tokens = _tokenize_transcript(transcript)
    non_filler = [token for token in tokens if token not in FILLER_WORDS]
    if not non_filler:
        return False
    if any(token.isdigit() for token in non_filler):
        return True
    if any(token in MEANINGFUL_HINT_WORDS for token in non_filler):
        return True
    if len(non_filler) == 1 and len(non_filler[0]) >= 5:
        return True
    if len(non_filler) == 2 and any(len(token) >= 3 for token in non_filler):
        return True
    informative = [token for token in non_filler if len(token) >= 3]
    return len(informative) >= 1


@app.websocket("/ws/call")
async def ws_call(websocket: WebSocket):
    await websocket.accept()
    session_id: str | None = None
    was_speaking = False

    try:
        while True:
            try:
                msg = await websocket.receive_json()
            except Exception as recv_err:
                logger.exception("[WebSocket] receive error")
                break

            msg_type = msg.get("type")

            if msg_type == "start_call":
                session_id = msg.get("session_id", "unknown")
                manager.active_connections[session_id] = websocket
                transcription_service.start_session(session_id)
                acoustic_service.start_session(session_id)
                meta = call_service.create_session(session_id)
                await _safe_send_json(websocket, {"type": "metadata", "data": meta.model_dump()})
                call_service.transition_to_greeting(session_id)
                await _emit_state(websocket, session_id, CallState.GREETING)
                cached_greeting = call_service.get_cached_greeting_audio()
                await _speak_and_record(
                    websocket,
                    session_id,
                    GREETING_TEXT,
                    "en",
                    prebuilt_audio=cached_greeting,
                )
                call_service.transition_to_listening(session_id)
                await _emit_state(websocket, session_id, CallState.LISTENING)

            elif msg_type == "audio_chunk" and session_id:
                raw_b64 = msg.get("data", "")
                try:
                    result = await asyncio.wait_for(
                        transcription_service.feed_chunk(session_id, raw_b64),
                        timeout=STT_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    await _activate_resilience_takeover(
                        websocket,
                        session_id,
                        f"Groq timeout/error: {exc}",
                    )
                    continue

                try:
                    pcm_bytes = base64.b64decode(raw_b64)
                except Exception:
                    pcm_bytes = b""

                buf = transcription_service._sessions.get(session_id)
                is_speaking = buf.is_speaking if buf else False
                acoustic = acoustic_service.analyze_chunk(session_id, pcm_bytes, is_speaking)
                call_service.update_acoustic(
                    session_id,
                    distress_level=acoustic.distress_level,
                    environment=acoustic.environment,
                    loudness=acoustic.loudness_label,
                )

                if is_speaking != was_speaking:
                    was_speaking = is_speaking
                    await _safe_send_json(
                        websocket,
                        {
                            "type": "metadata",
                            "data": _build_metadata_payload(
                                session_id,
                                is_user_speaking=is_speaking,
                                requires_confirmation=call_service.get_state(session_id) == CallState.VERIFYING,
                            ),
                        }
                    )

                session_acoustic = acoustic_service._sessions.get(session_id)
                if session_acoustic and session_acoustic.chunk_count % 4 == 0:
                    await _safe_send_json(
                        websocket,
                        {
                            "type": "acoustic_update",
                            "data": {
                                "distress_level": acoustic.distress_level,
                                "environment": acoustic.environment,
                                "is_high_distress": acoustic.is_high_distress,
                                "loudness": acoustic.loudness_label,
                                "rms": acoustic.rms,
                                "zcr": acoustic.zcr,
                            },
                        }
                    )

                if result and not result.skipped and not result.text:
                    print(f"[Transcript] Empty result from Groq for session={session_id}, ignoring")
                    continue

                if result and not result.skipped and result.text:
                    call_service.append_user_turn(session_id, result.text)
                    await _safe_send_json(
                        websocket,
                        {"type": "transcript", "text": result.text, "is_final": result.is_final}
                    )

                    current_state = call_service.get_state(session_id)
                    acoustic_context = {
                        "distress_level": acoustic.distress_level,
                        "environment": acoustic.environment,
                        "loudness": acoustic.loudness_label,
                    }

                    if current_state == CallState.VERIFYING:
                        try:
                            confirmation, _ = await asyncio.gather(
                                reasoning_service.check_confirmation(result.text),
                                _log_and_persist_transcript(session_id, result.text, current_state),
                            )
                        except Exception as exc:
                            logger.exception("[ReasoningService] Confirmation error")
                            await _activate_resilience_takeover(
                                websocket,
                                session_id,
                                f"Confirmation error: {exc}",
                            )
                            continue

                        if confirmation is None:
                            session = call_service.get_session(session_id)
                            verify_lang = session.last_language_code if session else "en"
                            await _speak_and_record(
                                websocket,
                                session_id,
                                _localized_verify_prompt(verify_lang),
                                verify_lang,
                            )
                            continue

                        if confirmation.confirmed:
                            session = call_service.get_session(session_id)
                            if session is None:
                                continue

                            try:
                                assurance_text = await asyncio.wait_for(
                                    reasoning_service.generate_assurance(
                                        session.last_location,
                                        confirmation.language_code or session.last_language_code,
                                        session.last_intent,
                                    ),
                                    timeout=LLM_TIMEOUT_SECONDS,
                                )
                            except Exception as exc:
                                logger.exception("[ReasoningService] Assurance timeout/error")
                                assurance_text = (
                                    f"Help is on the way to {session.last_location}. Stay on the line."
                                    if session.last_location
                                    else "Help is on the way. Stay on the line."
                                )

                            transitioned = call_service.transition_to_assurance(session_id, assurance_text)
                            if not transitioned:
                                call_service.transition_to_listening(session_id)
                                await _emit_state(websocket, session_id, CallState.LISTENING)
                                continue

                            call_service.log_complaint(session_id)
                            await _emit_state(websocket, session_id, CallState.ASSURANCE)
                            await _safe_send_json(
                                websocket,
                                {
                                    "type": "metadata",
                                    "data": _build_metadata_payload(
                                        session_id,
                                        is_user_speaking=False,
                                        requires_confirmation=False,
                                    ),
                                },
                            )
                            transcription_service.clear_buffer(session_id)
                            session = call_service.get_session(session_id)
                            if not (session and session.is_muted):
                                await _speak_and_record(
                                    websocket,
                                    session_id,
                                    assurance_text,
                                    session.last_language_code,
                                )

                        elif confirmation.is_denial:
                            call_service.transition_to_listening(session_id)
                            await _emit_state(websocket, session_id, CallState.LISTENING)
                            await _safe_send_json(
                                websocket,
                                {
                                    "type": "metadata",
                                    "data": _build_metadata_payload(
                                        session_id,
                                        is_user_speaking=False,
                                        requires_confirmation=False,
                                    ),
                                }
                            )
                            transcription_service.clear_buffer(session_id)
                            session = call_service.get_session(session_id)
                            if not (session and session.is_muted):
                                denied_lang = confirmation.language_code or (session.last_language_code if session else "en")
                                await _speak_and_record(
                                    websocket,
                                    session_id,
                                    _localized_denied_message(denied_lang),
                                    denied_lang,
                                )
                        else:
                            transcription_service.clear_buffer(session_id)
                            session = call_service.get_session(session_id)
                            if not (session and session.is_muted):
                                verify_lang = confirmation.language_code or (session.last_language_code if session else "en")
                                await _speak_and_record(
                                    websocket,
                                    session_id,
                                    _localized_verify_prompt(verify_lang),
                                    verify_lang,
                                )

                    elif current_state == CallState.LISTENING:
                        if not _has_meaningful_content(result.text):
                            await _log_and_persist_transcript(
                                session_id,
                                result.text,
                                CallState.LISTENING,
                            )
                            continue

                        try:
                            reasoning, _ = await asyncio.gather(
                                asyncio.wait_for(
                                    reasoning_service.analyze(
                                        call_service.get_conversation_history(session_id),
                                        acoustic_context=acoustic_context,
                                    ),
                                    timeout=LLM_TIMEOUT_SECONDS,
                                ),
                                _log_and_persist_transcript(session_id, result.text, current_state),
                            )
                        except Exception as exc:
                            logger.exception("[ReasoningService] Groq reasoning timeout/error")
                            reasoning = reasoning_service.fallback_analyze(
                                call_service.get_conversation_history(session_id),
                                acoustic_context=acoustic_context,
                            )

                        if reasoning is None:
                            logger.warning("[ReasoningService] Groq reasoning failed, using local fallback")
                            reasoning = reasoning_service.fallback_analyze(
                                call_service.get_conversation_history(session_id),
                                acoustic_context=acoustic_context,
                            )

                        await _safe_send_json(
                            websocket,
                            {"type": "reasoning_update", "data": reasoning.model_dump()}
                        )
                        await _safe_send_json(
                            websocket,
                            {
                                "type": "metadata",
                                "data": _build_metadata_payload(
                                    session_id,
                                    is_user_speaking=False,
                                    requires_confirmation=reasoning.is_complete_complaint,
                                    detected_sentiment=reasoning.sentiment,
                                ),
                            }
                        )

                        if reasoning.is_complete and reasoning.response_text and reasoning.intent:
                            call_service.transition_to_verifying(
                                session_id,
                                restatement=reasoning.response_text,
                                language_code=reasoning.language_code,
                                intent=reasoning.intent,
                                urgency=reasoning.urgency_level,
                                location=reasoning.location,
                            )
                            await _emit_state(websocket, session_id, CallState.VERIFYING)
                            transcription_service.clear_buffer(session_id)
                            session = call_service.get_session(session_id)
                            if not (session and session.is_muted):
                                await _speak_and_record(
                                    websocket,
                                    session_id,
                                    reasoning.response_text,
                                    reasoning.language_code,
                                )
                        else:
                            call_service.update_listening_context(
                                session_id,
                                language_code=reasoning.language_code,
                                intent=reasoning.intent,
                                location=reasoning.location,
                                urgency=reasoning.urgency_level,
                                response_text=reasoning.response_text,
                            )
                            transcription_service.clear_buffer(session_id)
                            session = call_service.get_session(session_id)
                            
                            if reasoning.intent and not reasoning.location:
                                call_service.transition_to_waiting_for_location(session_id)
                                await _emit_state(websocket, session_id, CallState.WAITING_FOR_LOCATION)

                            if (
                                reasoning.response_text
                                and not (session and session.is_muted)
                            ):
                                await _speak_and_record(
                                    websocket,
                                    session_id,
                                    reasoning.response_text,
                                    reasoning.language_code,
                                )

                    elif current_state == CallState.WAITING_FOR_LOCATION:
                        if not _has_meaningful_content(result.text):
                            await _log_and_persist_transcript(
                                session_id,
                                result.text,
                                CallState.WAITING_FOR_LOCATION,
                            )
                            continue

                        await _log_and_persist_transcript(session_id, result.text, CallState.WAITING_FOR_LOCATION)
                        
                        location = result.text.strip()
                        session = call_service.get_session(session_id)
                        intent = session.last_intent if session else None
                        urgency = session.last_urgency if session else 1
                        lang = session.last_language_code if session else "en"

                        confirmation_text = reasoning_service.build_confirmation_text(lang, intent, location)
                        
                        call_service.transition_to_verifying(
                            session_id,
                            restatement=confirmation_text,
                            language_code=lang,
                            intent=intent,
                            urgency=urgency,
                            location=location,
                        )
                        await _emit_state(websocket, session_id, CallState.VERIFYING)
                        transcription_service.clear_buffer(session_id)
                        
                        if not (session and session.is_muted):
                            await _speak_and_record(
                                websocket,
                                session_id,
                                confirmation_text,
                                lang,
                            )

                    elif current_state in {CallState.ASSURANCE, CallState.ESCALATED, CallState.GREETING}:
                        await _log_and_persist_transcript(session_id, result.text, current_state)

            elif msg_type == "TOGGLE_TAKEOVER" and session_id:
                muted = call_service.toggle_mute(session_id)
                if muted:
                    call_service.transition_to_escalated(session_id)
                    await _emit_state(websocket, session_id, CallState.ESCALATED)
                else:
                    restored = call_service.restore_from_escalation(session_id)
                    await _emit_state(websocket, session_id, restored)

                await _safe_send_json(
                    websocket,
                    {
                        "type": "metadata",
                        "data": _build_metadata_payload(
                            session_id,
                            is_user_speaking=False,
                            requires_confirmation=call_service.get_state(session_id) == CallState.VERIFYING,
                        ),
                    }
                )

            elif msg_type == "end_call":
                if session_id:
                    timeline = await asyncio.to_thread(_read_session_transcript_timeline, session_id)
                    report = None
                    try:
                        report = await asyncio.wait_for(
                            analytics_service.post_mortem(timeline),
                            timeout=ANALYTICS_TIMEOUT_SECONDS,
                        )
                    except Exception as exc:
                        logger.exception("[Analytics] post-mortem timeout/error")

                    report_payload = (
                        report.model_dump()
                        if report
                        else {
                            "understanding_score": 3,
                            "cultural_accuracy": 3,
                            "bottleneck_detected": "Analytics service unavailable during closeout",
                            "coaching_tip": "Escalate to the operator earlier when AI response latency exceeds safe limits.",
                        }
                    )

                    await _safe_send_json(websocket, {"type": "call_summary", "data": report_payload})
                    await asyncio.to_thread(
                        _write_final_report,
                        session_id,
                        json.dumps(report_payload, ensure_ascii=False),
                    )

                    transcription_service.end_session(session_id)
                    acoustic_service.end_session(session_id)
                    reasoning_service.reset_session(session_id)
                    call_service.end_session(session_id)
                    manager.disconnect(session_id)

                await _safe_send_json(
                    websocket,
                    {"type": "transcript", "text": "Call ended.", "is_final": True}
                )
                break

    except WebSocketDisconnect:
        logger.info("[WebSocket] Client disconnected: session=%s", session_id)
        if session_id:
            transcription_service.end_session(session_id)
            acoustic_service.end_session(session_id)
            reasoning_service.reset_session(session_id)
            call_service.end_session(session_id)
            manager.disconnect(session_id)
    except Exception as exc:
        logger.exception("[WebSocket] Unexpected error")
        if session_id:
            transcription_service.end_session(session_id)
            acoustic_service.end_session(session_id)
            reasoning_service.reset_session(session_id)
            call_service.end_session(session_id)
            manager.disconnect(session_id)
        try:
            await websocket.close()
        except Exception:
            pass


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_json()
            metadata = CallMetadata(**data)
            await manager.send_metadata(session_id, metadata)
    except WebSocketDisconnect:
        manager.disconnect(session_id)
