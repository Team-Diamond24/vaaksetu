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
from google import genai
from google.genai import types

from app.config import settings

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


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the **VaakSetu Intelligence Layer**, the AI reasoning engine behind \
the 1092 emergency helpline.  Your job is to analyze each caller transcript \
and produce a structured JSON analysis for the human operator.

## Your responsibilities
1. **Intent classification** — classify as exactly one of:
   Medical, Fire, Crime, Inquiry.
2. **Urgency assessment** — score 1-5:
   1 = general inquiry / no danger
   2 = non-urgent issue, can wait
   3 = moderate urgency, needs attention soon
   4 = high urgency, immediate response recommended
   5 = life-threatening / active emergency
3. **Sentiment detection** — capture the caller's emotional state
   (positive, negative, neutral, fearful, angry, distressed).
4. **Restatement** — write exactly ONE sentence IN THE CALLER'S LANGUAGE \
   that paraphrases their issue for confirmation.  If the caller spoke in \
   Kannada, restate in Kannada.  If Hindi, restate in Hindi.  If English, \
   restate in English.  For code-switched input, use the dominant language.
5. **Verification flag** — set `needs_verification` to `true` when:
   • The transcript is ambiguous or unclear
   • The caller described a life-threatening situation (urgency ≥ 4)
   • Key details (location, nature of emergency) are missing
   • The intent could be interpreted in multiple ways
6. **Language detection** — output the ISO 639-1 code of the primary \
   language (en, hi, kn, etc.).

## Rules
- NEVER fabricate information not present in the transcript.
- If the transcript is too short or unintelligible, set intent to "Inquiry", \
  urgency_level to 1, and needs_verification to true.
- Always respond with the specified JSON schema — no extra keys, no markdown.
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
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = "gemini-1.5-flash"

    async def analyze(self, transcript: str) -> ReasoningOutput | None:
        """
        Send the transcript to Gemini 1.5 Flash and return structured
        reasoning, or ``None`` if the call fails.
        """
        if not transcript or not transcript.strip():
            return None

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=f"Caller transcript:\n\n{transcript}",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_json_schema=ReasoningOutput,
                    temperature=0.2,
                ),
            )
            return ReasoningOutput.model_validate_json(response.text)

        except Exception as exc:
            print(f"[ReasoningService] Gemini error: {exc}")
            return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
reasoning_service = ReasoningService()
