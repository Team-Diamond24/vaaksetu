"""
Low-latency reasoning service powered by Groq chat models.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from groq import Groq
from pydantic import BaseModel, Field

from app.config import settings
from app.services.cultural_service import CulturalContext, cultural_context_service


TRIAGE_MODEL = "llama-3.1-8b-instant"
TRIAGE_SYSTEM_PROMPT = (
    "1092 triage. Extract intent(Medical|Fire|Crime|Inquiry), location, "
    "restatement(one confirmation sentence in caller language), "
    "needs_verification. Output strict JSON only with keys "
    "restatement,location,intent,needs_verification."
)
ASSURANCE_SYSTEM_PROMPT = (
    "1092 assurance. Return one short reassuring sentence in the caller language. "
    "Mention the location once if present. Plain text only."
)

YES_WORDS = {
    "en": {"yes", "yeah", "yep", "correct", "right", "ok", "okay"},
    "hi": {"haan", "ha", "haanji", "ji", "sahi", "theek"},
    "kn": {"howdu", "haudu", "sari", "correct", "aythu", "aitu"},
}

NO_WORDS = {
    "en": {"no", "nope", "wrong", "incorrect"},
    "hi": {"nahi", "nahin", "galat", "mat", "nahiin"},
    "kn": {"illa", "beda", "tappu", "alla"},
}

SEVERE_KEYWORDS = {
    "medical": {
        "medical",
        "ambulance",
        "bleeding",
        "unconscious",
        "breathe",
        "breathing",
        "attack",
        "stroke",
        "collapse",
        "heart",
        "chest",
        "accident",
        "injury",
    },
    "fire": {
        "fire",
        "smoke",
        "burn",
        "burning",
        "explosion",
        "gas",
        "leak",
        "flood",
        "rescue",
    },
    "crime": {
        "crime",
        "police",
        "attack",
        "assault",
        "kidnap",
        "murder",
        "theft",
        "robbery",
        "fight",
        "weapon",
        "thief",
    },
}

ANGRY_KEYWORDS = {"angry", "furious", "fight", "threat", "threatening"}
FEARFUL_KEYWORDS = {"help", "please", "scared", "afraid", "panic", "panicing"}
HINDI_HINTS = {"haan", "nahi", "madad", "aag", "chor", "sahi"}
KANNADA_HINTS = {"howdu", "haudu", "sari", "illa", "beda", "benki", "usiru"}


class TriageLLMOutput(BaseModel):
    restatement: str = ""
    location: str | None = None
    intent: str = "Inquiry"
    needs_verification: bool = True


class ReasoningOutput(BaseModel):
    restatement: str = Field(default="")
    location: str | None = Field(default=None)
    intent: str = Field(default="Inquiry")
    urgency_level: int = Field(default=1, ge=1, le=5)
    sentiment: str = Field(default="neutral")
    needs_verification: bool = Field(default=True)
    language_code: str = Field(default="en")


class ConfirmationOutput(BaseModel):
    confirmed: bool = False
    is_denial: bool = False
    language_code: str = "en"


def _normalize_intent(intent: str) -> str:
    mapping = {
        "medical": "Medical",
        "fire": "Fire",
        "crime": "Crime",
        "inquiry": "Inquiry",
        "police": "Crime",
    }
    return mapping.get((intent or "Inquiry").strip().lower(), "Inquiry")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def _contains_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in text)


def _contains_kannada(text: str) -> bool:
    return any("\u0c80" <= ch <= "\u0cff" for ch in text)


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _extract_location(transcript: str) -> str | None:
    patterns = [
        r"\b(?:at|in|near|from|on)\s+([A-Za-z0-9][A-Za-z0-9,\- ]{2,60})",
        r"\b(?:address is|location is)\s+([A-Za-z0-9][A-Za-z0-9,\- ]{2,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, transcript, flags=re.IGNORECASE)
        if match:
            location = re.split(
                r"\b(?:and|with|because|there is|there's)\b",
                match.group(1),
                maxsplit=1,
            )[0]
            location = location.strip(" ,.-")
            if location:
                return location
    return None


def _build_fallback_restatement(
    *,
    intent: str,
    location: str | None,
    language_code: str,
) -> str:
    if language_code == "hi":
        emergency = {
            "Medical": "मेडिकल",
            "Fire": "आग",
            "Crime": "पुलिस",
            "Inquiry": "आपातकाल",
        }.get(intent, "आपातकाल")
        if location:
            return f"मैं समझ रहा हूँ कि आपको {location} में {emergency} मदद चाहिए, क्या यह सही है?"
        return f"मैं समझ रहा हूँ कि आपको {emergency} मदद चाहिए, क्या यह सही है?"

    if language_code == "kn":
        emergency = {
            "Medical": "ವೈದ್ಯಕೀಯ",
            "Fire": "ಅಗ್ನಿ",
            "Crime": "ಪೊಲೀಸ್",
            "Inquiry": "ತುರ್ತು",
        }.get(intent, "ತುರ್ತು")
        if location:
            return f"ನಿಮಗೆ {location} ನಲ್ಲಿ {emergency} ಸಹಾಯ ಬೇಕಿದೆ, ಇದು ಸರಿಯೇ?"
        return f"ನಿಮಗೆ {emergency} ಸಹಾಯ ಬೇಕಿದೆ, ಇದು ಸರಿಯೇ?"

    if location:
        return f"I understand you need {intent.lower()} help at {location}, is that correct?"
    return f"I understand you need {intent.lower()} help, is that correct?"


def _fallback_assurance(location: str | None) -> str:
    if location:
        return f"Help is on the way to {location}. Stay on the line."
    return "Help is on the way. Stay on the line."


class ReasoningService:
    """Groq-backed triage with local fallbacks."""

    def __init__(self) -> None:
        self._client = Groq(api_key=settings.groq_api_key)
        self._turn_history: dict[str, list[str]] = {}

    def reset_session(self, session_id: str) -> None:
        self._turn_history.pop(session_id, None)

    def detect_language(self, text: str) -> str:
        if not text:
            return "en"
        if _contains_kannada(text):
            return "kn"
        if _contains_devanagari(text):
            return "hi"

        tokens = set(_tokenize(text))
        if tokens & KANNADA_HINTS:
            return "kn"
        if tokens & HINDI_HINTS:
            return "hi"
        return "en"

    def _build_recent_context(self, session_id: str | None, transcript: str) -> str:
        if not session_id:
            return transcript.strip()

        history = self._turn_history.setdefault(session_id, [])
        history.append(transcript.strip())
        if len(history) > 2:
            history = history[-2:]
            self._turn_history[session_id] = history
        return " | ".join(history)

    def _compact_cultural_context(self, transcript: str) -> tuple[CulturalContext, str]:
        cultural_ctx = cultural_context_service.get_context(transcript)
        if not cultural_ctx.matched_terms:
            return cultural_ctx, ""

        parts: list[str] = []
        for entry in cultural_ctx.matched_terms[:3]:
            part = f"{entry.term}={entry.canonical}"
            if entry.urgency_hint:
                part += f"/u{entry.urgency_hint}"
            parts.append(part)
        return cultural_ctx, "; ".join(parts)

    def _estimate_urgency(
        self,
        transcript: str,
        intent: str,
        acoustic_context: dict[str, Any] | None,
        cultural_ctx: CulturalContext,
    ) -> int:
        urgency = {
            "Inquiry": 1,
            "Medical": 3,
            "Fire": 4,
            "Crime": 3,
        }.get(intent, 1)

        text = transcript.lower()
        keyword_bucket = SEVERE_KEYWORDS.get(intent.lower(), set())
        if any(word in text for word in keyword_bucket):
            urgency = max(urgency, 4)

        cultural_hint = max(
            (entry.urgency_hint or 0 for entry in cultural_ctx.matched_terms),
            default=0,
        )
        if cultural_hint:
            urgency = max(urgency, cultural_hint)

        distress = int((acoustic_context or {}).get("distress_level", 1))
        if distress >= 4:
            urgency = max(urgency, distress)
        elif distress == 3 and urgency < 3:
            urgency = 3

        return max(1, min(5, urgency))

    def _derive_sentiment(self, transcript: str, distress_level: int) -> str:
        text = transcript.lower()
        if distress_level >= 4:
            return "distressed"
        if any(word in text for word in ANGRY_KEYWORDS):
            return "angry"
        if any(word in text for word in FEARFUL_KEYWORDS):
            return "fearful"
        return "neutral"

    def _infer_intent(self, transcript: str) -> str:
        text = transcript.lower()
        for intent, keywords in SEVERE_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return _normalize_intent(intent)
        return "Inquiry"

    def fallback_analyze(
        self,
        transcript: str,
        acoustic_context: dict[str, Any] | None = None,
    ) -> ReasoningOutput:
        acoustic = acoustic_context or {}
        language_code = self.detect_language(transcript)
        intent = self._infer_intent(transcript)
        location = _extract_location(transcript)
        cultural_ctx, _ = self._compact_cultural_context(transcript)
        urgency = self._estimate_urgency(transcript, intent, acoustic, cultural_ctx)
        distress_level = int(acoustic.get("distress_level", 1))

        return ReasoningOutput(
            restatement=_build_fallback_restatement(
                intent=intent,
                location=location,
                language_code=language_code,
            ),
            location=location,
            intent=intent,
            urgency_level=urgency,
            sentiment=self._derive_sentiment(transcript, distress_level),
            needs_verification=True,
            language_code=language_code,
        )

    def _chat_json_sync(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        response = self._client.chat.completions.create(
            model=TRIAGE_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return _strip_code_fences(response.choices[0].message.content or "")

    def _chat_text_sync(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        response = self._client.chat.completions.create(
            model=TRIAGE_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        return _strip_code_fences(response.choices[0].message.content or "")

    async def analyze(
        self,
        transcript: str,
        session_id: str | None = None,
        acoustic_context: dict[str, Any] | None = None,
    ) -> ReasoningOutput | None:
        if not transcript or not transcript.strip():
            return None

        recent_turns = self._build_recent_context(session_id, transcript)
        cultural_ctx, compact_cultural = self._compact_cultural_context(transcript)
        language_code = self.detect_language(transcript)
        acoustic = acoustic_context or {}

        prompt_parts = [
            f"T:{recent_turns}",
            f"L:{language_code}",
            f"A:d={acoustic.get('distress_level', 1)},e={acoustic.get('environment', 'quiet')},l={acoustic.get('loudness', 'normal')}",
        ]
        if compact_cultural:
            prompt_parts.append(f"C:{compact_cultural}")

        try:
            content = await asyncio.to_thread(
                self._chat_json_sync,
                TRIAGE_SYSTEM_PROMPT,
                "\n".join(prompt_parts),
                140,
            )
            llm_output = TriageLLMOutput.model_validate_json(content)
            intent = _normalize_intent(llm_output.intent)
            urgency = self._estimate_urgency(transcript, intent, acoustic, cultural_ctx)
            distress_level = int(acoustic.get("distress_level", 1))

            return ReasoningOutput(
                restatement=llm_output.restatement.strip(),
                location=llm_output.location.strip() if llm_output.location else None,
                intent=intent,
                urgency_level=urgency,
                sentiment=self._derive_sentiment(transcript, distress_level),
                needs_verification=True,
                language_code=language_code,
            )
        except Exception as exc:
            print(f"[ReasoningService] Groq triage error: {exc}")
            return None

    async def check_confirmation(self, transcript: str) -> ConfirmationOutput | None:
        if not transcript or not transcript.strip():
            return None

        language_code = self.detect_language(transcript)
        tokens = set(_tokenize(transcript))
        yes_tokens = set().union(*YES_WORDS.values())
        no_tokens = set().union(*NO_WORDS.values())

        confirmed = bool(tokens & yes_tokens)
        is_denial = bool(tokens & no_tokens)
        if confirmed and is_denial:
            confirmed = False
            is_denial = False

        return ConfirmationOutput(
            confirmed=confirmed,
            is_denial=is_denial,
            language_code=language_code,
        )

    async def generate_assurance(
        self,
        location: str | None,
        language_code: str,
        intent: str,
    ) -> str:
        prompt = f"lang={language_code}\nintent={intent}\nlocation={location or 'unknown'}"
        try:
            assurance = await asyncio.to_thread(
                self._chat_text_sync,
                ASSURANCE_SYSTEM_PROMPT,
                prompt,
                40,
            )
            return assurance.strip() or _fallback_assurance(location)
        except Exception as exc:
            print(f"[ReasoningService] Groq assurance error: {exc}")
            return _fallback_assurance(location)


reasoning_service = ReasoningService()
