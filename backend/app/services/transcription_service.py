"""
Transcription service — energy-based VAD + Groq Whisper STT.

Pipeline:
  1. Receive Base64-encoded Int16 PCM chunks (16 kHz, mono, 250 ms each).
  2. Compute RMS energy per chunk; classify as speech or silence.
  3. Buffer speech chunks.  Once silence exceeds 500 ms, flush the buffer.
  4. Convert buffered PCM → WAV in-memory, send to Groq whisper-large-v3.
  5. Return transcribed text.
"""

from __future__ import annotations

import base64
import io
import math
import struct
import wave
from dataclasses import dataclass, field

from groq import Groq

from app.config import settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16_000          # Hz  — matches the frontend AudioWorklet
SAMPLE_WIDTH = 2              # bytes (Int16)
NUM_CHANNELS = 1              # mono
CHUNK_DURATION_MS = 250       # each chunk the frontend sends
SILENCE_THRESHOLD_MS = 500    # flush after this much consecutive silence
SAMPLES_PER_CHUNK = SAMPLE_RATE * CHUNK_DURATION_MS // 1000  # 4 000

# Energy threshold — Int16 RMS below this is treated as silence.
# Tuned for typical close-talk microphones; adjust if needed.
ENERGY_THRESHOLD = settings.vad_energy_threshold

# Groq Whisper prompt for multilingual code-switching
WHISPER_PROMPT = (
    "This is a multilingual conversation with frequent code-switching "
    "between Kannada, Hindi, and English. The speaker may switch languages "
    "mid-sentence. Transcribe exactly as spoken, preserving the original "
    "language of each word or phrase. Use Devanagari script for Hindi, "
    "Kannada script for Kannada, and Latin script for English."
)


# ---------------------------------------------------------------------------
# Per-session speech buffer
# ---------------------------------------------------------------------------
@dataclass
class _SessionBuffer:
    """Accumulates PCM bytes for one active session."""

    chunks: list[bytes] = field(default_factory=list)
    silence_chunks: int = 0          # consecutive silent chunks
    is_speaking: bool = False        # has speech started in current utterance?
    total_chunks_fed: int = 0


# ---------------------------------------------------------------------------
# VAD helpers
# ---------------------------------------------------------------------------
def _rms_energy(pcm_bytes: bytes) -> float:
    """Compute RMS energy of signed-16-bit PCM samples."""
    n_samples = len(pcm_bytes) // SAMPLE_WIDTH
    if n_samples == 0:
        return 0.0
    samples = struct.unpack(f"<{n_samples}h", pcm_bytes)
    sum_sq = sum(s * s for s in samples)
    return math.sqrt(sum_sq / n_samples)


def _is_speech(pcm_bytes: bytes) -> bool:
    """Return True if the chunk's energy exceeds the silence threshold."""
    return _rms_energy(pcm_bytes) > ENERGY_THRESHOLD


# ---------------------------------------------------------------------------
# WAV builder
# ---------------------------------------------------------------------------
def _pcm_to_wav(pcm_bytes: bytes) -> bytes:
    """Wrap raw PCM bytes in a WAV container (in-memory)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(NUM_CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class TranscriptionService:
    """
    Manages per-session audio buffering, VAD, and Groq Whisper transcription.

    Usage from the WebSocket handler:

        result = await transcription_service.feed_chunk(session_id, b64_data)
        if result is not None:
            # result.text contains the transcript
            ...
    """

    def __init__(self) -> None:
        self._client = Groq(api_key=settings.groq_api_key)
        self._sessions: dict[str, _SessionBuffer] = {}

    # -- session lifecycle ---------------------------------------------------

    def start_session(self, session_id: str) -> None:
        """Register a new session buffer."""
        self._sessions[session_id] = _SessionBuffer()

    def end_session(self, session_id: str) -> None:
        """Remove a session buffer and free memory."""
        self._sessions.pop(session_id, None)

    def clear_buffer(self, session_id: str) -> None:
        """Clear accumulated audio to prevent processing old trailing noise."""
        buf = self._sessions.get(session_id)
        if buf:
            buf.chunks.clear()
            buf.silence_chunks = 0
            buf.is_speaking = False

    # -- main entry point ----------------------------------------------------

    async def feed_chunk(
        self, session_id: str, b64_data: str
    ) -> TranscriptionResult | None:
        """
        Feed a single Base64-encoded Int16 PCM chunk.

        Returns a ``TranscriptionResult`` when an utterance boundary is
        detected (silence > 500 ms after speech), or ``None`` while still
        buffering.
        """
        buf = self._sessions.get(session_id)
        if buf is None:
            return None

        pcm_bytes = base64.b64decode(b64_data)
        buf.total_chunks_fed += 1
        speech = _is_speech(pcm_bytes)

        if speech:
            buf.chunks.append(pcm_bytes)
            buf.silence_chunks = 0
            buf.is_speaking = True
            return None

        # Silence frame
        if buf.is_speaking:
            # Still include a small amount of trailing silence for context
            buf.chunks.append(pcm_bytes)
            buf.silence_chunks += 1

            silence_ms = buf.silence_chunks * CHUNK_DURATION_MS
            if silence_ms >= SILENCE_THRESHOLD_MS:
                # End-of-utterance detected — flush and transcribe
                return await self._flush(buf)

        return None

    # -- internal ------------------------------------------------------------

    async def _flush(self, buf: _SessionBuffer) -> TranscriptionResult:
        """Concatenate buffered chunks, transcribe via Groq, and reset."""
        pcm_data = b"".join(buf.chunks)

        # Reset the buffer for the next utterance
        buf.chunks.clear()
        buf.silence_chunks = 0
        buf.is_speaking = False

        if len(pcm_data) < SAMPLE_RATE * SAMPLE_WIDTH * 0.3:
            # Less than ~300 ms of audio — too short, skip
            return TranscriptionResult(text="", is_final=True, skipped=True)

        wav_data = _pcm_to_wav(pcm_data)
        text = await self._call_groq(wav_data)
        return TranscriptionResult(text=text.strip(), is_final=True)

    async def _call_groq(self, wav_bytes: bytes) -> str:
        """Send WAV audio to Groq whisper-large-v3 and return the text."""
        try:
            transcription = self._client.audio.transcriptions.create(
                file=("utterance.wav", wav_bytes),
                model="whisper-large-v3",
                prompt=WHISPER_PROMPT,
                response_format="text",
                temperature=0.0,
            )
            # response_format="text" returns the plain string directly
            return str(transcription)
        except Exception as exc:
            print(f"[TranscriptionService] Groq API error: {exc}")
            return ""


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------
@dataclass
class TranscriptionResult:
    text: str
    is_final: bool = True
    skipped: bool = False


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
transcription_service = TranscriptionService()
