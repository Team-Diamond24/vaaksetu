"""
Resilient multilingual TTS service backed by Edge-TTS.
"""

from __future__ import annotations

import base64
import io
import re

import edge_tts


DEFAULT_VOICE = "en-IN-NeerjaNeural"
STREAM_CHUNK_SIZE = 4096


class SpeechService:
    def _resolve_voice(self, lang_code: str) -> str:
        voice_map = {
            "en": "en-IN-NeerjaNeural",
            "hi": "hi-IN-SwaraNeural",
            "kn": "kn-IN-SapnaNeural",
        }
        return voice_map.get((lang_code or "en").lower().strip(), DEFAULT_VOICE)

    def _needs_english_fallback(self, text: str, lang_code: str) -> bool:
        normalized_lang = (lang_code or "en").lower().strip()
        if normalized_lang not in {"hi", "kn"}:
            return False
        return re.fullmatch(r"[A-Za-z0-9\s.,!?'\-:;()]+", text.strip()) is not None

    async def _stream_with_voice(self, text: str, voice: str):
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate="+10%",
            pitch="+0Hz",
            volume="+0%",
        )

        pending = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                pending.extend(chunk["data"])
                while len(pending) >= STREAM_CHUNK_SIZE:
                    data = bytes(pending[:STREAM_CHUNK_SIZE])
                    del pending[:STREAM_CHUNK_SIZE]
                    yield base64.b64encode(data).decode("ascii")

        if pending:
            yield base64.b64encode(bytes(pending)).decode("ascii")

    async def _synthesize_full_with_voice(self, text: str, voice: str) -> str | None:
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate="+10%",
            pitch="+0Hz",
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

    async def synthesize(self, text: str, language_code: str = "en"):
        if not text or not text.strip():
            return

        voice = self._resolve_voice(language_code)
        if self._needs_english_fallback(text, language_code):
            print(
                f"[SpeechService] Romanized text detected for lang={language_code}, "
                f"falling back to {DEFAULT_VOICE}: {text}"
            )
            voice = DEFAULT_VOICE

        print(f"[SpeechService] Synthesizing with voice={voice} lang={language_code} text={text}")
        try:
            async for chunk in self._stream_with_voice(text, voice):
                yield chunk
        except Exception as exc:
            print(f"[SpeechService] Edge-TTS primary voice error: {exc}")
            if voice == DEFAULT_VOICE:
                raise
            print(f"[SpeechService] Falling back to {DEFAULT_VOICE} for text={text}")
            async for chunk in self._stream_with_voice(text, DEFAULT_VOICE):
                yield chunk

    async def synthesize_full(self, text: str, language_code: str = "en") -> str | None:
        if not text or not text.strip():
            return None

        voice = self._resolve_voice(language_code)
        if self._needs_english_fallback(text, language_code):
            print(
                f"[SpeechService] Romanized text detected for lang={language_code}, "
                f"falling back to {DEFAULT_VOICE}: {text}"
            )
            voice = DEFAULT_VOICE

        print(f"[SpeechService] Synthesizing full with voice={voice} lang={language_code} text={text}")
        try:
            return await self._synthesize_full_with_voice(text, voice)
        except Exception as exc:
            print(f"[SpeechService] Edge-TTS primary voice error: {exc}")
            if voice == DEFAULT_VOICE:
                return None
            try:
                print(f"[SpeechService] Falling back to {DEFAULT_VOICE} for text={text}")
                return await self._synthesize_full_with_voice(text, DEFAULT_VOICE)
            except Exception as fallback_exc:
                print(f"[SpeechService] Edge-TTS fallback voice error: {fallback_exc}")
                return None


speech_service = SpeechService()
