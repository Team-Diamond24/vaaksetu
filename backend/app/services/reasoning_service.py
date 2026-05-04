"""
Reasoning service with full conversation-memory slot filling.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from groq import Groq
from pydantic import BaseModel, Field

from app.config import settings


TRIAGE_MODEL = "llama-3.3-70b-versatile"
SYSTEM_PROMPT = """You are VaakSetu, a 1092 emergency helpline dispatcher in Karnataka. You must output strict JSON.
Read the entire conversation history to extract facts.

RULES:
1. To dispatch help, you MUST have both an actionable 'intent' (e.g., Fire, Medical) AND a specific 'location' (e.g., Sector 12, MG Road). "My house" or "here" are NOT valid locations.
2. If intent or location is missing, set "is_complete": false and ask the user for the missing info in "response_text".
3. If both are present, set "is_complete": true and provide a confirmation summary in "response_text".
4. STRICT LANGUAGE MATCHING: If the user's latest input is Hindi (even if typed in English letters), your "response_text" MUST be in Devanagari script. If Kannada, use Kannada script. If English, use English.

JSON SCHEMA TO RETURN:
{
  "detected_language": "en" | "hi" | "kn",
  "intent": "string or null",
  "location": "string or null",
  "is_complete": boolean,
  "response_text": "String in the native script matching detected_language"
}"""

YES_WORDS = {
    "en": {"yes", "yeah", "yep", "correct", "right", "ok", "okay"},
    "hi": {
        "haan",
        "ha",
        "haa",
        "han",
        "haanji",
        "haji",
        "ji",
        "sahi",
        "theek",
        "हाँ",
        "हां",
    },
    "kn": {"howdu", "houdu", "haudu", "sari", "aythu", "aitu", "ಹೌದು"},
}
NO_WORDS = {
    "en": {"no", "nope", "wrong", "incorrect"},
    "hi": {"nahi", "nahin", "nhi", "galat", "नहीं", "नहि"},
    "kn": {"illa", "beda", "tappu", "alla", "ಇಲ್ಲ"},
}
HINDI_HINTS = {
    "haan",
    "nahi",
    "nahin",
    "madad",
    "aag",
    "bachao",
    "mera",
    "meri",
    "ghar",
    "main",
    "hai",
    "ho",
    "gaya",
    "accident",
}
KANNADA_HINTS = {
    "haudu",
    "howdu",
    "illa",
    "beda",
    "benki",
    "mane",
    "nanna",
    "yalli",
    "ide",
    "aythu",
    "raste",
}
INTENT_KEYWORDS: dict[str, set[str]] = {
    "Fire": {"fire", "benki", "aag", "आग", "ಬೆಂಕಿ", "smoke", "burn", "burning", "gas leak"},
    "Medical": {
        "medical",
        "ambulance",
        "accident",
        "एक्सीडेंट",
        "दुर्घटना",
        "ಆಂಬುಲೆನ್ಸ್",
        "ಅಪಘಾತ",
        "bleeding",
        "खून",
        "रक्त",
        "ಗಾಯ",
        "injury",
        "heart",
        "stroke",
        "unconscious",
        "breathing",
        "hospital",
    },
    "Crime": {
        "crime",
        "police",
        "पुलिस",
        "चोरी",
        "हमला",
        "पोलीस",
        "ಕಳ್ಳತನ",
        "ಪೊಲೀಸ್",
        "robbery",
        "theft",
        "assault",
        "attack",
        "fight",
        "chor",
        "thief",
        "kidnap",
    },
    "Flood/Tsunami": {"tsunami", "flood", "water rising", "wave", "inundation", "सुनामी", "बाढ़", "ಸುನಾಮಿ", "ನೆರೆ"},
}
GENERIC_LOCATIONS = {
    "my house",
    "house",
    "home",
    "my home",
    "here",
    "there",
    "outside",
    "inside",
    "office",
    "my office",
    "room",
    "my room",
    "highway",
    "road",
    "street",
    "area",
    "place",
    "ghar",
    "mera ghar",
    "house only",
    "mane",
    "nanna mane",
}
ANGRY_KEYWORDS = {"angry", "furious", "fight", "threat", "threatening"}
FEARFUL_KEYWORDS = {"help", "please", "scared", "afraid", "panic", "bachao", "sahay"}


class TriageLLMOutput(BaseModel):
    detected_language: str = "en"
    intent: str | None = None
    location: str | None = None
    is_complete: bool = False
    response_text: str = ""


class ReasoningOutput(BaseModel):
    detected_language: str = "en"
    intent: str | None = None
    location: str | None = None
    is_complete: bool = False
    response_text: str = ""
    urgency_level: int = Field(default=1, ge=1, le=5)
    sentiment: str = "neutral"
    language_code: str = "en"
    needs_verification: bool = False
    is_complete_complaint: bool = False
    restatement: str | None = None
    missing_info_question: str | None = None


class ConfirmationOutput(BaseModel):
    confirmed: bool = False
    is_denial: bool = False
    language_code: str = "en"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def _contains_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in text)


def _contains_kannada(text: str) -> bool:
    return any("\u0c80" <= ch <= "\u0cff" for ch in text)


def _normalize_language(code: str | None, fallback: str = "en") -> str:
    normalized = (code or fallback or "en").strip().lower()
    return normalized if normalized in {"en", "hi", "kn"} else fallback


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _clean_location(location: str | None) -> str | None:
    if not location:
        return None
    cleaned = location.strip(" .,-")
    return cleaned or None


def _is_actionable_location(location: str | None) -> bool:
    cleaned = _clean_location(location)
    if not cleaned:
        return False
    normalized = " ".join(_tokenize(cleaned))
    if not normalized or normalized in GENERIC_LOCATIONS:
        return False
    if any(char.isdigit() for char in normalized):
        return True
    if re.search(
        r"\b(sector|road|rd|street|st|nagar|layout|phase|block|cross|main|"
        r"bus stand|station|circle|junction|market|colony|city|town|village)\b",
        normalized,
    ):
        return True
    tokens = normalized.split()
    if len(tokens) >= 2:
        return True
    return len(normalized) >= 6


def _location_from_text(text: str) -> str | None:
    patterns = [
        r"\b(?:at|in|near|on|from)\s+([A-Za-z0-9][A-Za-z0-9,\- ]{2,80})",
        r"\b(?:location is|address is)\s+([A-Za-z0-9][A-Za-z0-9,\- ]{2,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = re.split(
                r"\b(?:because|and|there is|there's|please|help)\b",
                match.group(1),
                maxsplit=1,
            )[0]
            candidate = _clean_location(candidate)
            if _is_actionable_location(candidate):
                return candidate
    return None


def _intent_from_text(text: str) -> str | None:
    lowered = text.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return intent
    return None


def _has_native_script(text: str, language_code: str) -> bool:
    if language_code == "hi":
        return _contains_devanagari(text)
    if language_code == "kn":
        return _contains_kannada(text)
    return True


def _translate_intent(intent: str | None, language_code: str) -> str:
    if not intent:
        if language_code == "hi":
            return "आपातस्थिति"
        if language_code == "kn":
            return "ತುರ್ತು ಪರಿಸ್ಥಿತಿ"
        return "emergency"
    if language_code == "hi":
        return {
            "Fire": "आग",
            "Medical": "मेडिकल आपातस्थिति",
            "Crime": "अपराध",
            "Flood/Tsunami": "बाढ़ या सुनामी",
        }.get(intent, "आपातस्थिति")
    if language_code == "kn":
        return {
            "Fire": "ಬೆಂಕಿ",
            "Medical": "ವೈದ್ಯಕೀಯ ತುರ್ತು ಪರಿಸ್ಥಿತಿ",
            "Crime": "ಅಪರಾಧ",
            "Flood/Tsunami": "ನೆರೆ ಅಥವಾ ಸುನಾಮಿ",
        }.get(intent, "ತುರ್ತು ಪರಿಸ್ಥಿತಿ")
    return intent


def _build_missing_info_question(
    language_code: str,
    *,
    missing_intent: bool,
    missing_location: bool,
) -> str:
    if language_code == "hi":
        if missing_intent and missing_location:
            return "कृपया बताइए क्या आपातस्थिति है और सही इलाका या पता क्या है?"
        if missing_location:
            return "कृपया सही इलाका, पता या नज़दीकी स्थल बताइए।"
        return "कृपया बताइए क्या आपातस्थिति है?"
    if language_code == "kn":
        if missing_intent and missing_location:
            return "ದಯವಿಟ್ಟು ಯಾವ ತುರ್ತು ಸಮಸ್ಯೆ ಇದೆ ಮತ್ತು ಸರಿಯಾದ ಸ್ಥಳ ಅಥವಾ ವಿಳಾಸ ಏನು ಎಂದು ತಿಳಿಸಿ."
        if missing_location:
            return "ದಯವಿಟ್ಟು ಸರಿಯಾದ ಪ್ರದೇಶ, ವಿಳಾಸ ಅಥವಾ ಹತ್ತಿರದ ಗುರುತು ತಿಳಿಸಿ."
        return "ದಯವಿಟ್ಟು ಯಾವ ತುರ್ತು ಸಮಸ್ಯೆ ಇದೆ ಎಂದು ತಿಳಿಸಿ."
    if missing_intent and missing_location:
        return "Please tell me what emergency is happening and the exact location."
    if missing_location:
        return "Please tell me the exact area, address, or nearby landmark."
    return "Please tell me what emergency is happening."


def _build_confirmation_text(language_code: str, intent: str | None, location: str) -> str:
    localized_intent = _translate_intent(intent, language_code)
    if language_code == "hi":
        return (
            f"मुझे समझ आ रहा है कि {location} में {localized_intent} की स्थिति है। "
            "क्या यह सही है?"
        )
    if language_code == "kn":
        return (
            f"{location} ನಲ್ಲಿ {localized_intent} ಇದೆ ಎಂದು ನನಗೆ ಅರ್ಥವಾಗುತ್ತಿದೆ. "
            "ಇದು ಸರಿಯೇ?"
        )
    return f"I understand there is a {localized_intent} emergency at {location}. Is that correct?"


def _build_assurance_text(language_code: str, location: str | None) -> str:
    if language_code == "hi":
        if location:
            return f"मदद {location} के लिए भेजी जा रही है। कृपया लाइन पर बने रहिए।"
        return "मदद भेजी जा रही है। कृपया लाइन पर बने रहिए।"
    if language_code == "kn":
        if location:
            return f"{location} ಗೆ ಸಹಾಯ ಕಳುಹಿಸಲಾಗುತ್ತಿದೆ. ದಯವಿಟ್ಟು ಲೈನ್‌ನಲ್ಲಿ ಇರಿ."
        return "ಸಹಾಯ ಕಳುಹಿಸಲಾಗುತ್ತಿದೆ. ದಯವಿಟ್ಟು ಲೈನ್‌ನಲ್ಲಿ ಇರಿ."
    if location:
        return f"Help is being sent to {location}. Please stay on the line."
    return "Help is being sent. Please stay on the line."


class ReasoningService:
    def __init__(self) -> None:
        self._client = Groq(api_key=settings.groq_api_key)

    def reset_session(self, session_id: str) -> None:
        return None

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

    def _extract_slots_from_history(
        self,
        conversation_history: list[dict[str, str]],
    ) -> tuple[str | None, str | None, str]:
        user_turns = [item["content"] for item in conversation_history if item.get("role") == "user"]
        combined = " ".join(user_turns)
        latest_user_text = user_turns[-1] if user_turns else ""

        intent = _intent_from_text(combined)
        location = None
        for user_text in reversed(user_turns):
            location = _location_from_text(user_text)
            if location:
                break

        if not location and intent:
            latest_candidate = _clean_location(latest_user_text)
            if (
                latest_candidate
                and _is_actionable_location(latest_candidate)
                and not _intent_from_text(latest_candidate)
            ):
                location = latest_candidate

        return intent, location, latest_user_text

    def _derive_sentiment(self, transcript: str, distress_level: int) -> str:
        lowered = transcript.lower()
        if distress_level >= 4:
            return "distressed"
        if any(word in lowered for word in ANGRY_KEYWORDS):
            return "angry"
        if any(word in lowered for word in FEARFUL_KEYWORDS):
            return "fearful"
        return "neutral"

    def _estimate_urgency(
        self,
        transcript: str,
        intent: str | None,
        acoustic_context: dict[str, Any] | None,
    ) -> int:
        urgency = {
            None: 1,
            "Fire": 4,
            "Medical": 4,
            "Crime": 3,
            "Flood/Tsunami": 5,
        }.get(intent, 3 if intent else 1)
        distress = int((acoustic_context or {}).get("distress_level", 1))
        if distress >= 4:
            urgency = max(urgency, distress)
        return max(1, min(5, urgency))

    def _chat_json_sync(self, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=TRIAGE_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=220,
            response_format={"type": "json_object"},
        )
        return _strip_code_fences(response.choices[0].message.content or "")

    def _normalize_llm_output(
        self,
        llm_output: TriageLLMOutput,
        *,
        fallback_language: str,
        fallback_intent: str | None,
        fallback_location: str | None,
    ) -> tuple[str, str | None, str | None, bool, str]:
        detected_language = _normalize_language(
            llm_output.detected_language,
            fallback=fallback_language,
        )
        intent = llm_output.intent or fallback_intent
        location = _clean_location(llm_output.location) or fallback_location
        if not _is_actionable_location(location):
            location = None

        is_complete = bool(intent and location and llm_output.is_complete)
        response_text = (llm_output.response_text or "").strip()
        if not response_text or (
            detected_language in {"hi", "kn"} and not _has_native_script(response_text, detected_language)
        ):
            if is_complete and location:
                response_text = _build_confirmation_text(detected_language, intent, location)
            else:
                response_text = _build_missing_info_question(
                    detected_language,
                    missing_intent=intent is None,
                    missing_location=location is None,
                )

        if not is_complete:
            is_complete = bool(intent and location)
            if is_complete and location:
                response_text = _build_confirmation_text(detected_language, intent, location)

        return detected_language, intent, location, is_complete, response_text

    def fallback_analyze(
        self,
        conversation_history: list[dict[str, str]],
        acoustic_context: dict[str, Any] | None = None,
    ) -> ReasoningOutput | None:
        intent, location, latest_user_text = self._extract_slots_from_history(conversation_history)
        if not latest_user_text:
            return None
        detected_language = self.detect_language(latest_user_text)
        is_complete = bool(intent and location)
        response_text = (
            _build_confirmation_text(detected_language, intent, location)
            if is_complete and location
            else _build_missing_info_question(
                detected_language,
                missing_intent=intent is None,
                missing_location=location is None,
            )
        )
        urgency = self._estimate_urgency(latest_user_text, intent, acoustic_context)
        sentiment = self._derive_sentiment(
            latest_user_text,
            int((acoustic_context or {}).get("distress_level", 1)),
        )
        return ReasoningOutput(
            detected_language=detected_language,
            intent=intent,
            location=location,
            is_complete=is_complete,
            response_text=response_text,
            urgency_level=urgency,
            sentiment=sentiment,
            language_code=detected_language,
            needs_verification=is_complete,
            is_complete_complaint=is_complete,
            restatement=response_text if is_complete else None,
            missing_info_question=response_text if not is_complete else None,
        )

    async def analyze(
        self,
        conversation_history: list[dict[str, str]],
        acoustic_context: dict[str, Any] | None = None,
    ) -> ReasoningOutput | None:
        intent_hint, location_hint, latest_user_text = self._extract_slots_from_history(conversation_history)
        if not latest_user_text:
            return None
        fallback_language = self.detect_language(latest_user_text)
        user_prompt = (
            "Conversation history:\n"
            f"{json.dumps(conversation_history, ensure_ascii=False)}\n"
            f"Latest user input: {latest_user_text}"
        )
        try:
            content = await asyncio.to_thread(self._chat_json_sync, user_prompt)
            llm_output = TriageLLMOutput.model_validate_json(content)
            detected_language, intent, location, is_complete, response_text = self._normalize_llm_output(
                llm_output,
                fallback_language=fallback_language,
                fallback_intent=intent_hint,
                fallback_location=location_hint,
            )
        except Exception as exc:
            print(f"[ReasoningService] Groq triage error: {exc}")
            return self.fallback_analyze(conversation_history, acoustic_context)

        urgency = self._estimate_urgency(latest_user_text, intent, acoustic_context)
        sentiment = self._derive_sentiment(
            latest_user_text,
            int((acoustic_context or {}).get("distress_level", 1)),
        )
        return ReasoningOutput(
            detected_language=detected_language,
            intent=intent,
            location=location,
            is_complete=is_complete,
            response_text=response_text,
            urgency_level=urgency,
            sentiment=sentiment,
            language_code=detected_language,
            needs_verification=is_complete,
            is_complete_complaint=is_complete,
            restatement=response_text if is_complete else None,
            missing_info_question=response_text if not is_complete else None,
        )

    async def check_confirmation(self, transcript: str) -> ConfirmationOutput | None:
        if not transcript or not transcript.strip():
            return None
        language_code = self.detect_language(transcript)
        tokens = set(_tokenize(transcript))
        yes_tokens = YES_WORDS.get(language_code, set()).union(*YES_WORDS.values())
        no_tokens = NO_WORDS.get(language_code, set()).union(*NO_WORDS.values())

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
        intent: str | None,
    ) -> str:
        del intent
        language_code = _normalize_language(language_code)
        return _build_assurance_text(language_code, location)

    def build_confirmation_text(self, language_code: str, intent: str | None, location: str) -> str:
        return _build_confirmation_text(language_code, intent, location)


reasoning_service = ReasoningService()
