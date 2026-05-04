"""
Transcription service: energy-based VAD plus Groq Whisper STT.
"""

from __future__ import annotations

import base64
import io
import math
import struct
import wave
from dataclasses import dataclass, field
import logging

from groq import Groq

from app.config import settings

logger = logging.getLogger(__name__)


SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2
NUM_CHANNELS = 1
CHUNK_DURATION_MS = 250
SILENCE_THRESHOLD_MS = 800
ENERGY_THRESHOLD = settings.vad_energy_threshold
WHISPER_PROMPT = (
    "ನಮಸ್ಕಾರ ಸಹಾಯ, नमस्ते मदद चाहिए, emergency, police, fire, ambulance, "
    "accident, address, location."
)
HALLUCINATIONS = [
    "thank you",
    "thanks for watching",
    "subscribe",
    "amara.org",
    "fuck",
    "ai ai ai",
    "marching band",
]


@dataclass
class _SessionBuffer:
    chunks: list[bytes] = field(default_factory=list)
    silence_chunks: int = 0
    is_speaking: bool = False


@dataclass
class TranscriptionResult:
    text: str
    is_final: bool = True
    skipped: bool = False


def _rms_energy(pcm_bytes: bytes) -> float:
    n_samples = len(pcm_bytes) // SAMPLE_WIDTH
    if n_samples == 0:
        return 0.0
    samples = struct.unpack(f"<{n_samples}h", pcm_bytes)
    sum_sq = sum(sample * sample for sample in samples)
    return math.sqrt(sum_sq / n_samples)


def _is_speech(pcm_bytes: bytes) -> bool:
    return _rms_energy(pcm_bytes) > ENERGY_THRESHOLD


def _pcm_to_wav(pcm_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(NUM_CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _should_discard(text: str) -> bool:
    text_clean = text.lower().strip()
    if any(h in text_clean for h in HALLUCINATIONS) or len(text_clean) < 4:
        return True
    return False


class TranscriptionService:
    def __init__(self) -> None:
        self._client = Groq(api_key=settings.groq_api_key)
        self._sessions: dict[str, _SessionBuffer] = {}

    def start_session(self, session_id: str) -> None:
        self._sessions[session_id] = _SessionBuffer()

    def end_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def clear_buffer(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.chunks.clear()
            session.silence_chunks = 0
            session.is_speaking = False

    async def feed_chunk(
        self,
        session_id: str,
        b64_data: str,
    ) -> TranscriptionResult | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None

        pcm_bytes = base64.b64decode(b64_data)
        if _is_speech(pcm_bytes):
            session.chunks.append(pcm_bytes)
            session.silence_chunks = 0
            session.is_speaking = True
            return None

        if session.is_speaking:
            session.chunks.append(pcm_bytes)
            session.silence_chunks += 1
            if session.silence_chunks * CHUNK_DURATION_MS >= SILENCE_THRESHOLD_MS:
                return await self._flush(session)

        return None

    async def _flush(self, session: _SessionBuffer) -> TranscriptionResult | None:
        pcm_data = b"".join(session.chunks)
        session.chunks.clear()
        session.silence_chunks = 0
        session.is_speaking = False

        if len(pcm_data) < SAMPLE_RATE * SAMPLE_WIDTH * 0.3:
            return None

        wav_bytes = _pcm_to_wav(pcm_data)
        text = (await self._call_groq(wav_bytes)).strip()
        if _should_discard(text):
            return None
        return TranscriptionResult(text=text, is_final=True)

    async def _call_groq(self, wav_bytes: bytes) -> str:
        try:
            transcription = self._client.audio.transcriptions.create(
                file=("utterance.wav", wav_bytes),
                model="whisper-large-v3",
                prompt=WHISPER_PROMPT,
                response_format="text",
                temperature=0.0,
            )
            return str(transcription)
        except Exception as exc:
            logger.exception("[TranscriptionService] Groq API error")
            return ""


transcription_service = TranscriptionService()
