"""
Speech service — Empathetic TTS powered by Edge-TTS (Microsoft Neural Voices).

Maps language_code from the ReasoningService to high-quality neural voices:
  - kn  → kn-IN-SapnaNeural   (Kannada, female, calm)
  - hi  → hi-IN-SwaraNeural   (Hindi, female, calm)
  - en  → en-IN-NeerjaNeural  (Indian English, female, calm)

Audio is streamed as Base64-encoded MP3 chunks — never written to disk.
"""

from __future__ import annotations

import base64
import io

import edge_tts

from app.config import settings  # noqa: F401 — available for future config

# ---------------------------------------------------------------------------
# Voice mapping
# ---------------------------------------------------------------------------

# Neural voice IDs keyed by ISO 639-1 language code.
# All chosen for calm, empathetic tone suitable for an emergency helpline.
VOICE_MAP: dict[str, str] = {
    "kn": "kn-IN-SapnaNeural",
    "hi": "hi-IN-SwaraNeural",
    "en": "en-IN-NeerjaNeural",
    "ta": "ta-IN-PallaviNeural",
    "te": "te-IN-ShrutiNeural",
    "mr": "mr-IN-AarohiNeural",
}

DEFAULT_VOICE = "en-IN-NeerjaNeural"

# Chunk size (bytes) for streaming over WebSocket.
# ~4 KB lowers first-byte latency while keeping overhead manageable.
STREAM_CHUNK_SIZE = 4096


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SpeechService:
    """
    Converts text to speech using Microsoft Edge-TTS neural voices.

    Usage::

        async for b64_chunk in speech_service.synthesize(text, "kn"):
            await ws.send_json({"type": "audio_chunk", "data": b64_chunk})
    """

    def _resolve_voice(self, language_code: str) -> str:
        """Pick the best neural voice for the given language code."""
        code = (language_code or "en").lower().strip()
        return VOICE_MAP.get(code, DEFAULT_VOICE)

    async def synthesize(
        self, text: str, language_code: str = "en"
    ):
        """
        Async generator — yields Base64-encoded MP3 byte chunks.

        The caller can stream each chunk to the frontend immediately,
        enabling low-latency playback while the rest of the audio is
        still being generated.
        """
        if not text or not text.strip():
            return

        voice = self._resolve_voice(language_code)
        print(f"[SpeechService] Synthesizing with voice={voice} lang={language_code}")

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate="-5%",       # slightly slower for clarity
            volume="+0%",
        )

        # Stream audio bytes with small buffering for low latency.
        pending = bytearray()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                pending.extend(chunk["data"])
                while len(pending) >= STREAM_CHUNK_SIZE:
                    data = bytes(pending[:STREAM_CHUNK_SIZE])
                    del pending[:STREAM_CHUNK_SIZE]
                    yield base64.b64encode(data).decode("ascii")

        # Flush any remaining bytes
        if pending:
            yield base64.b64encode(bytes(pending)).decode("ascii")

    async def synthesize_full(
        self, text: str, language_code: str = "en"
    ) -> str | None:
        """
        Generate the *entire* audio as a single Base64 string.

        Useful for short confirmations where streaming is unnecessary.
        Returns ``None`` if synthesis fails.
        """
        if not text or not text.strip():
            return None

        voice = self._resolve_voice(language_code)

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate="-5%",
                volume="+0%",
            )

            audio_buffer = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_buffer.write(chunk["data"])

            if audio_buffer.tell() == 0:
                return None

            audio_buffer.seek(0)
            return base64.b64encode(audio_buffer.read()).decode("ascii")

        except Exception as exc:
            print(f"[SpeechService] Edge-TTS error: {exc}")
            return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
speech_service = SpeechService()
