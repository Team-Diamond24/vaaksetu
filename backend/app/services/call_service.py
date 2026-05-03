"""
Call session service — state machine for managing call lifecycle.

States:
  LISTENING   — AI is actively listening and will do full triage analysis.
  VERIFYING   — AI has restated the issue; waiting for user confirmation.
  CONFIRMED   — User confirmed the restatement; dispatching help.
  ESCALATED   — Call has been escalated to a human operator.
"""

from __future__ import annotations

import uuid
from enum import Enum
from dataclasses import dataclass, field

from app.models import CallMetadata


# ---------------------------------------------------------------------------
# Call state enum
# ---------------------------------------------------------------------------

class CallState(str, Enum):
    """Finite states a call session can be in."""
    LISTENING  = "LISTENING"
    VERIFYING  = "VERIFYING"
    CONFIRMED  = "CONFIRMED"
    ESCALATED  = "ESCALATED"


# ---------------------------------------------------------------------------
# Per-session state
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    """Tracks the current state and context for a single call session."""
    session_id: str
    state: CallState = CallState.LISTENING
    last_language_code: str = "en"
    last_restatement: str = ""
    last_intent: str = ""
    last_urgency: int = 1


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class CallService:
    """Handles call session lifecycle, state transitions, and metadata."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    # -- session lifecycle ---------------------------------------------------

    def create_session(self, session_id: str | None = None) -> CallMetadata:
        """Create a new call session with default metadata."""
        sid = session_id or str(uuid.uuid4())
        self._sessions[sid] = SessionState(session_id=sid)
        return CallMetadata(
            session_id=sid,
            is_user_speaking=False,
            detected_sentiment="neutral",
            requires_confirmation=False,
        )

    def end_session(self, session_id: str) -> None:
        """Remove a session's state and free memory."""
        self._sessions.pop(session_id, None)

    # -- state queries -------------------------------------------------------

    def get_state(self, session_id: str) -> CallState:
        """Return the current state for a session (defaults to LISTENING)."""
        s = self._sessions.get(session_id)
        return s.state if s else CallState.LISTENING

    def get_session(self, session_id: str) -> SessionState | None:
        """Return the full session state object, or None."""
        return self._sessions.get(session_id)

    # -- state transitions ---------------------------------------------------

    def transition_to_verifying(
        self,
        session_id: str,
        restatement: str,
        language_code: str,
        intent: str = "",
        urgency: int = 1,
    ) -> None:
        """Move to VERIFYING — the AI has restated the issue."""
        s = self._sessions.get(session_id)
        if s:
            s.state = CallState.VERIFYING
            s.last_restatement = restatement
            s.last_language_code = language_code
            s.last_intent = intent
            s.last_urgency = urgency
            print(f"[CallState] {session_id} → VERIFYING")

    def transition_to_confirmed(self, session_id: str) -> None:
        """Move to CONFIRMED — user said Yes / Sari / Haan."""
        s = self._sessions.get(session_id)
        if s:
            s.state = CallState.CONFIRMED
            print(f"[CallState] {session_id} → CONFIRMED")

    def transition_to_listening(self, session_id: str) -> None:
        """Move back to LISTENING — user said No / Alla / Nahi or fresh start."""
        s = self._sessions.get(session_id)
        if s:
            s.state = CallState.LISTENING
            s.last_restatement = ""
            print(f"[CallState] {session_id} → LISTENING")

    def transition_to_escalated(self, session_id: str) -> None:
        """Move to ESCALATED — call has been escalated to a human."""
        s = self._sessions.get(session_id)
        if s:
            s.state = CallState.ESCALATED
            print(f"[CallState] {session_id} → ESCALATED")

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def update_sentiment(
        metadata: CallMetadata, sentiment: str
    ) -> CallMetadata:
        """Return a new metadata instance with updated sentiment."""
        return metadata.model_copy(update={"detected_sentiment": sentiment})

    @staticmethod
    def toggle_speaking(
        metadata: CallMetadata, is_speaking: bool
    ) -> CallMetadata:
        """Return a new metadata instance with updated speaking state."""
        return metadata.model_copy(update={"is_user_speaking": is_speaking})


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
call_service = CallService()
