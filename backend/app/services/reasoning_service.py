"""
Reasoning service — VaakSetu Intelligence Layer powered by Gemini 1.5 Flash.

Takes a raw transcript and returns structured analysis:
  - restatement   : 1-sentence confirmation in the caller's language
  - intent        : Medical | Fire | Crime | Inquiry
  - urgency_level : 1 (low) – 5 (critical)
  - sentiment     : positive | negative | neutral | fearful | angry | distressed
  - needs_verification : true if ambiguous or high-stakes
  - language_code : ISO 639-1 code of the detected language
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from openai import AsyncOpenAI

from app.config import settings
from app.services.cultural_service import cultural_context_service

# ---------------------------------------------------------------------------
# Output contract (Pydantic → Gemini JSON schema enforcement)
# ---------------------------------------------------------------------------

class ReasoningOutput(BaseModel):
    """Strict JSON contract returned by the intelligence layer."""

    restatement: str = Field(
        description=(
            "A single-sentence summary in the CALLER'S language that "
            "restates the issue for confirmation, e.g. 'I understand you "
            "need help with a water shortage in Indiranagar, is that correct?'"
        )
    )
    intent: str = Field(
        description="One of: Medical, Fire, Crime, Inquiry"
    )
    urgency_level: int = Field(
        ge=1, le=5,
        description="1 = low / informational, 5 = life-threatening emergency"
    )
    sentiment: str = Field(
        description=(
            "Caller's emotional state: positive, negative, neutral, "
            "fearful, angry, or distressed"
        )
    )
    needs_verification: bool = Field(
        description=(
            "true if the transcript is ambiguous, contradictory, or "
            "describes a high-stakes situation that requires explicit "
            "operator confirmation before dispatching"
        )
    )
    language_code: str = Field(
        description="ISO 639-1 language code of the primary language detected (e.g. en, hi, kn)"
    )


class ConfirmationOutput(BaseModel):
    """Result of a binary confirmation check during VERIFYING state."""

    confirmed: bool = Field(
        description=(
            "true if the caller said a confirmation word (Yes, Sari, Haan, "
            "Howdu, OK, Correct, Right, etc.). false if they said a denial "
            "(No, Alla, Nahi, Beda, Wrong, etc.) or said something ambiguous."
        )
    )
    is_denial: bool = Field(
        description=(
            "true if the caller explicitly denied or corrected "
            "(No, Alla, Nahi, Beda, Wrong, That's not right, etc.)"
        )
    )
    language_code: str = Field(
        description="ISO 639-1 language code of the response (en, hi, kn)"
    )


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
[Role] VaakSetu Intelligence Layer for emergency triage.

[Do]
- Classify intent as exactly one: Medical, Fire, Crime, Inquiry.
- Score urgency 1-5 (5 = life-threatening / active emergency).
- Detect sentiment: positive, negative, neutral, fearful, angry, distressed.
- Restate in exactly one sentence in the caller's dominant language.
- Detect primary language as ISO code (en, hi, kn, etc.).
- Set needs_verification=true for ambiguity, missing key details, high stakes, or multi-interpretation risk.

[Dialect Handling]
- If a Linguistic Context section exists, use those detected regional definitions.
- Treat urgency hints as minimum urgency signals.
- Mirror caller dialect naturally; avoid over-formalized wording.

[Guardrails]
- Use only facts present in transcript/context.
- For unintelligible/too-short speech, default to Inquiry with urgency 1 and needs_verification=true.
"""

CONFIRMATION_PROMPT = """\
You are a binary confirmation detector for the 1092 emergency helpline.

The AI just asked the caller to confirm a restated issue. \
The caller's response is below. Your ONLY job is to determine:
1. Did they say YES / confirm? (Sari, Haan, Howdu, Yes, OK, Correct, Right, Ha, etc.)
2. Did they say NO / deny? (Alla, Nahi, Beda, No, Wrong, That's not right, Galat, etc.)
3. What language did they respond in?

Rules:
- If the response is clearly affirmative → confirmed=true, is_denial=false
- If the response is clearly negative → confirmed=false, is_denial=true
- If ambiguous or unrelated → confirmed=false, is_denial=false
- Be generous with affirmative detection — colloquial forms count.
"""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ReasoningService:
    """
    Stateless service — call ``analyze(transcript)`` with any transcript
    and receive a ``ReasoningOutput``.
    """

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
        )
        self._model = "google/gemini-2.5-flash"
        self._turn_history: dict[str, list[str]] = {}

    def _build_recent_context(self, session_id: str | None, transcript: str) -> str:
        """
        Keep only the last 3 user turns to reduce prompt tokens.
        """
        if not session_id:
            return transcript

        history = self._turn_history.setdefault(session_id, [])
        history.append(transcript.strip())
        if len(history) > 3:
            self._turn_history[session_id] = history[-3:]
            history = self._turn_history[session_id]

        lines = [f"Turn {i + 1}: {t}" for i, t in enumerate(history[-3:])]
        return "\n".join(lines)

    def reset_session(self, session_id: str) -> None:
        """Clear transcript history for a finished call session."""
        self._turn_history.pop(session_id, None)

    async def analyze(
        self,
        transcript: str,
        session_id: str | None = None,
    ) -> ReasoningOutput | None:
        """
        Send the transcript to Gemini and return structured
        reasoning, or ``None`` if the call fails.

        Before calling the LLM, the transcript is scanned by the
        CulturalContextService for regional dialect markers.  If any
        are found, the linguistic context is injected into the prompt
        so the model can adjust its restatement and urgency assessment.
        """
        if not transcript or not transcript.strip():
            return None

        # --- Cultural context injection ---
        recent_turns = self._build_recent_context(session_id, transcript)
        cultural_ctx = cultural_context_service.get_context(transcript)
        user_content = f"Recent caller turns (last 3 max):\n\n{recent_turns}"
        if cultural_ctx.context_string:
            user_content += f"\n\n{cultural_ctx.context_string}"

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                extra_body={
                    "response_mime_type": "application/json",
                    "response_schema": ReasoningOutput.model_json_schema(),
                },
                temperature=0.2,
                max_tokens=500,
            )
            content = response.choices[0].message.content or ""
            return ReasoningOutput.model_validate_json(content)

        except Exception as exc:
            print(f"[ReasoningService] OpenRouter/OpenAI error: {exc}")
            return None

    async def check_confirmation(self, transcript: str) -> ConfirmationOutput | None:
        """
        Lightweight Gemini call — used ONLY during VERIFYING state.
        Detects a binary Yes/No (including Kannada/Hindi equivalents).
        """
        if not transcript or not transcript.strip():
            return None

        try:
            response = await self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": CONFIRMATION_PROMPT},
                    {"role": "user", "content": f"Caller's response:\n\n{transcript}"}
                ],
                response_format=ConfirmationOutput,
                temperature=0.1,
                max_tokens=200,
            )
            return response.choices[0].message.parsed

        except Exception as exc:
            print(f"[ReasoningService] Confirmation check error: {exc}")
            return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
reasoning_service = ReasoningService()

