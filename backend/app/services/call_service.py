"""
Call session service for the VaakSetu helpline state machine.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from app.models import CallMetadata


COMPLAINTS_FILE = Path(__file__).resolve().parent.parent / "data" / "complaints.json"
GREETING_TEXT = "Namaskara, 1092 Helpline. What is your emergency?"


class CallState(str, Enum):
    GREETING = "GREETING"
    LISTENING = "LISTENING"
    WAITING_FOR_LOCATION = "WAITING_FOR_LOCATION"
    VERIFYING = "VERIFYING"
    ASSURANCE = "ASSURANCE"
    ESCALATED = "ESCALATED"


@dataclass
class SessionState:
    session_id: str
    state: CallState = CallState.GREETING
    pre_escalation_state: CallState | None = None
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    last_language_code: str = "en"
    last_restatement: str = ""
    last_response_text: str = ""
    last_assurance: str = ""
    last_location: str | None = None
    last_intent: str | None = None
    last_urgency: int = 1
    last_distress_level: int = 1
    last_environment: str = "quiet"
    last_loudness: str = "normal"
    is_muted: bool = False
    fallback_triggered: bool = False
    complaint_logged: bool = False


class CallService:
    """Handles call lifecycle, conversation memory, and complaint logging."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._complaints_lock = threading.Lock()
        self._cached_greeting_audio: str | None = None
        self.ensure_complaints_file()

    def ensure_complaints_file(self) -> None:
        COMPLAINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not COMPLAINTS_FILE.exists():
            COMPLAINTS_FILE.write_text("[]", encoding="utf-8")
            return
        try:
            existing = json.loads(COMPLAINTS_FILE.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                raise ValueError("complaints.json must contain a JSON array")
        except Exception:
            COMPLAINTS_FILE.write_text("[]", encoding="utf-8")

    def read_complaints(self) -> list[dict]:
        self.ensure_complaints_file()
        try:
            data = json.loads(COMPLAINTS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def set_cached_greeting_audio(self, audio_b64: str | None) -> None:
        self._cached_greeting_audio = audio_b64

    def get_cached_greeting_audio(self) -> str | None:
        return self._cached_greeting_audio

    def create_session(self, session_id: str | None = None) -> CallMetadata:
        sid = session_id or str(uuid.uuid4())
        self._sessions[sid] = SessionState(session_id=sid)
        return CallMetadata(
            session_id=sid,
            is_user_speaking=False,
            detected_sentiment="neutral",
            requires_confirmation=False,
            is_muted=False,
            distress_level=1,
            environment="quiet",
        )

    def end_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def get_state(self, session_id: str) -> CallState:
        session = self._sessions.get(session_id)
        return session.state if session else CallState.LISTENING

    def get_session(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def append_user_turn(self, session_id: str, transcript: str) -> None:
        session = self._sessions.get(session_id)
        if not session or not transcript.strip():
            return
        session.conversation_history.append({"role": "user", "content": transcript.strip()})

    def append_assistant_turn(self, session_id: str, text: str) -> None:
        session = self._sessions.get(session_id)
        if not session or not text.strip():
            return
        session.conversation_history.append({"role": "assistant", "content": text.strip()})
        session.last_response_text = text.strip()

    def get_conversation_history(self, session_id: str) -> list[dict[str, str]]:
        session = self._sessions.get(session_id)
        if not session:
            return []
        return list(session.conversation_history)

    def transition_to_greeting(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.state = CallState.GREETING
            print(f"[CallState] {session_id} -> GREETING")

    def transition_to_listening(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.state = CallState.LISTENING
            session.pre_escalation_state = None
            session.last_restatement = ""
            session.last_response_text = ""
            session.last_assurance = ""
            session.last_location = None
            session.last_intent = session.last_intent
            session.last_urgency = max(1, session.last_urgency)
            session.complaint_logged = False
            print(f"[CallState] {session_id} -> LISTENING")

    def transition_to_waiting_for_location(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.state = CallState.WAITING_FOR_LOCATION
            session.pre_escalation_state = None
            session.complaint_logged = False
            print(f"[CallState] {session_id} -> WAITING_FOR_LOCATION")

    def update_reasoning_context(
        self,
        session_id: str,
        *,
        language_code: str,
        intent: str | None,
        location: str | None,
        urgency: int,
        response_text: str,
    ) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return
        session.last_language_code = language_code or session.last_language_code
        if intent:
            session.last_intent = intent
        if location:
            session.last_location = location
        session.last_urgency = max(1, min(5, urgency))
        session.last_response_text = response_text

    def update_listening_context(
        self,
        session_id: str,
        *,
        language_code: str,
        intent: str | None,
        location: str | None,
        urgency: int,
        response_text: str,
    ) -> None:
        self.update_reasoning_context(
            session_id,
            language_code=language_code,
            intent=intent,
            location=location,
            urgency=urgency,
            response_text=response_text,
        )

    def transition_to_verifying(
        self,
        session_id: str,
        *,
        restatement: str,
        language_code: str,
        intent: str | None,
        urgency: int,
        location: str | None,
    ) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.state = CallState.VERIFYING
            session.last_restatement = restatement
            session.last_response_text = restatement
            session.last_language_code = language_code or session.last_language_code
            if location:
                session.last_location = location
            if intent:
                session.last_intent = intent
            session.last_urgency = max(1, min(5, urgency))
            session.last_assurance = ""
            session.complaint_logged = False
            print(f"[CallState] {session_id} -> VERIFYING")

    def transition_to_assurance(self, session_id: str, assurance_text: str) -> bool:
        session = self._sessions.get(session_id)
        if not session or session.state != CallState.VERIFYING:
            return False
        session.state = CallState.ASSURANCE
        session.last_assurance = assurance_text
        session.last_response_text = assurance_text
        print(f"[CallState] {session_id} -> ASSURANCE")
        return True

    def transition_to_escalated(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            if session.state != CallState.ESCALATED:
                session.pre_escalation_state = session.state
            session.state = CallState.ESCALATED
            print(f"[CallState] {session_id} -> ESCALATED")

    def restore_from_escalation(self, session_id: str) -> CallState:
        session = self._sessions.get(session_id)
        if not session:
            return CallState.LISTENING
        session.state = session.pre_escalation_state or CallState.LISTENING
        session.pre_escalation_state = None
        print(f"[CallState] {session_id} -> {session.state.value}")
        return session.state

    def update_acoustic(
        self,
        session_id: str,
        *,
        distress_level: int,
        environment: str,
        loudness: str,
    ) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.last_distress_level = max(1, min(5, distress_level))
            session.last_environment = environment
            session.last_loudness = loudness

    def toggle_mute(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.is_muted = not session.is_muted
        print(f"[CallState] {session_id} mute={session.is_muted}")
        return session.is_muted

    def set_muted(self, session_id: str, muted: bool) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.is_muted = muted
        print(f"[CallState] {session_id} mute={session.is_muted}")
        return session.is_muted

    def log_complaint(self, session_id: str) -> dict | None:
        session = self._sessions.get(session_id)
        if not session or session.complaint_logged or session.state != CallState.ASSURANCE:
            return None

        complaint_text = session.last_restatement or session.last_response_text
        complaint = {
            "session_id": session.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "location": session.last_location,
            "complaint_text": complaint_text,
            "intent": session.last_intent,
            "urgency": session.last_urgency,
            "distress_level": session.last_distress_level,
            "language": session.last_language_code,
            "acoustic_data": {
                "environment": session.last_environment,
                "loudness": session.last_loudness,
            },
            "status": "Pending Dispatch",
        }

        self.ensure_complaints_file()
        with self._complaints_lock:
            complaints = self.read_complaints()
            complaints.append(complaint)
            with COMPLAINTS_FILE.open("w", encoding="utf-8") as handle:
                json.dump(complaints, handle, ensure_ascii=False, indent=2)

        session.complaint_logged = True
        print(f"[Complaint] Logged complaint for session={session_id}")
        return complaint


call_service = CallService()
