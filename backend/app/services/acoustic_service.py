"""
Acoustic Intelligence service — real-time audio feature extraction.

Analyzes raw Int16 PCM chunks (16 kHz mono) to detect:
  - Loudness (RMS energy) — shouting vs. whispering
  - Pitch proxy (Zero Crossing Rate) — high pitch ≈ distress
  - Background noise level — chaotic vs. calm environment
  - Distress scoring — composite 1-5 scale

All analysis runs in-memory on raw PCM bytes. No external libraries required.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from collections import deque


# ---------------------------------------------------------------------------
# Constants & thresholds
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16_000          # Hz
SAMPLE_WIDTH = 2              # bytes (Int16)

# RMS thresholds (Int16 range: -32768 to +32767)
RMS_WHISPER = 300             # below → very quiet / whispering
RMS_NORMAL = 800              # normal conversational level
RMS_LOUD = 2000               # raised voice
RMS_SHOUTING = 4000           # shouting / screaming

# Zero Crossing Rate thresholds (crossings per second)
ZCR_LOW = 500                 # low pitch / calm
ZCR_NORMAL = 1500             # normal speech
ZCR_HIGH = 3000               # high pitch / stressed
ZCR_VERY_HIGH = 5000          # extreme distress / shrieking

# Background noise: rolling window of silence-segment energy
NOISE_BASELINE_QUIET = 200    # very quiet room
NOISE_BASELINE_MODERATE = 500 # moderate ambient
NOISE_BASELINE_CHAOTIC = 1000 # traffic / crowd / sirens

# How many recent silence chunks to keep for noise estimation
NOISE_WINDOW_SIZE = 20


# ---------------------------------------------------------------------------
# Analysis result
# ---------------------------------------------------------------------------
@dataclass
class AcousticSnapshot:
    """Result of analyzing a single audio chunk."""
    rms: float = 0.0                      # Root Mean Square energy
    zcr: float = 0.0                      # Zero Crossing Rate (crossings/sec)
    is_high_distress: bool = False         # loudness + pitch combined flag
    distress_level: int = 1               # 1 (calm) – 5 (extreme distress)
    environment: str = "quiet"            # quiet | moderate | chaotic
    noise_floor: float = 0.0             # estimated background noise energy
    loudness_label: str = "normal"        # whisper | normal | loud | shouting


# ---------------------------------------------------------------------------
# Per-session acoustic state
# ---------------------------------------------------------------------------
@dataclass
class _SessionAcoustics:
    """Rolling state for one session's acoustic analysis."""
    silence_energies: deque = field(
        default_factory=lambda: deque(maxlen=NOISE_WINDOW_SIZE)
    )
    recent_rms: deque = field(
        default_factory=lambda: deque(maxlen=10)
    )
    recent_zcr: deque = field(
        default_factory=lambda: deque(maxlen=10)
    )
    peak_rms: float = 0.0
    peak_zcr: float = 0.0
    chunk_count: int = 0


# ---------------------------------------------------------------------------
# DSP helpers (pure Python — no numpy/scipy needed)
# ---------------------------------------------------------------------------
def _compute_rms(pcm_bytes: bytes) -> float:
    """Compute RMS energy of signed-16-bit PCM samples."""
    n_samples = len(pcm_bytes) // SAMPLE_WIDTH
    if n_samples == 0:
        return 0.0
    samples = struct.unpack(f"<{n_samples}h", pcm_bytes)
    sum_sq = sum(s * s for s in samples)
    return math.sqrt(sum_sq / n_samples)


def _compute_zcr(pcm_bytes: bytes) -> float:
    """
    Compute Zero Crossing Rate — number of sign changes per second.
    Higher ZCR often correlates with higher pitch / fricatives / distress.
    """
    n_samples = len(pcm_bytes) // SAMPLE_WIDTH
    if n_samples < 2:
        return 0.0
    samples = struct.unpack(f"<{n_samples}h", pcm_bytes)
    crossings = 0
    for i in range(1, n_samples):
        if (samples[i] >= 0) != (samples[i - 1] >= 0):
            crossings += 1

    # Duration of this chunk in seconds
    duration_s = n_samples / SAMPLE_RATE
    return crossings / duration_s if duration_s > 0 else 0.0


def _classify_loudness(rms: float) -> str:
    """Map RMS to a human-readable loudness label."""
    if rms < RMS_WHISPER:
        return "whisper"
    elif rms < RMS_LOUD:
        return "normal"
    elif rms < RMS_SHOUTING:
        return "loud"
    else:
        return "shouting"


def _classify_environment(noise_floor: float) -> str:
    """Classify ambient noise level."""
    if noise_floor < NOISE_BASELINE_QUIET:
        return "quiet"
    elif noise_floor < NOISE_BASELINE_MODERATE:
        return "moderate"
    elif noise_floor < NOISE_BASELINE_CHAOTIC:
        return "noisy"
    else:
        return "chaotic"


def _compute_distress_level(rms: float, zcr: float, noise_floor: float) -> int:
    """
    Composite distress score from 1 (calm) to 5 (extreme).
    Factors in loudness, pitch proxy, and environment noise.
    """
    score = 0.0

    # Loudness contribution (0–2 points)
    if rms >= RMS_SHOUTING:
        score += 2.0
    elif rms >= RMS_LOUD:
        score += 1.2
    elif rms >= RMS_NORMAL:
        score += 0.5

    # Pitch/ZCR contribution (0–2 points)
    if zcr >= ZCR_VERY_HIGH:
        score += 2.0
    elif zcr >= ZCR_HIGH:
        score += 1.2
    elif zcr >= ZCR_NORMAL:
        score += 0.4

    # Environment contribution (0–1 point)
    if noise_floor >= NOISE_BASELINE_CHAOTIC:
        score += 1.0
    elif noise_floor >= NOISE_BASELINE_MODERATE:
        score += 0.5

    # Map 0–5 float → 1–5 int
    level = max(1, min(5, round(score) + 1))
    return level


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class AcousticService:
    """
    Analyzes raw PCM audio chunks for situational awareness.

    Usage::

        snapshot = acoustic_service.analyze_chunk(session_id, pcm_bytes, is_speech)
        # snapshot.distress_level → 1-5
        # snapshot.environment   → "quiet" | "moderate" | "noisy" | "chaotic"
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _SessionAcoustics] = {}

    def start_session(self, session_id: str) -> None:
        """Initialize acoustic state for a new session."""
        self._sessions[session_id] = _SessionAcoustics()

    def end_session(self, session_id: str) -> None:
        """Clean up session acoustic state."""
        self._sessions.pop(session_id, None)

    def analyze_chunk(
        self,
        session_id: str,
        pcm_bytes: bytes,
        is_speech: bool,
    ) -> AcousticSnapshot:
        """
        Analyze a single PCM chunk and return an ``AcousticSnapshot``.

        Args:
            session_id: Active session identifier.
            pcm_bytes: Raw Int16 PCM audio bytes (16 kHz mono).
            is_speech: Whether the VAD classified this chunk as speech.
        """
        state = self._sessions.get(session_id)
        if state is None:
            self.start_session(session_id)
            state = self._sessions[session_id]

        state.chunk_count += 1

        # Core metrics
        rms = _compute_rms(pcm_bytes)
        zcr = _compute_zcr(pcm_bytes)

        # Track peaks
        state.peak_rms = max(state.peak_rms, rms)
        state.peak_zcr = max(state.peak_zcr, zcr)

        # Rolling averages
        state.recent_rms.append(rms)
        state.recent_zcr.append(zcr)

        # Background noise estimation: use silence segments
        if not is_speech:
            state.silence_energies.append(rms)

        # Compute noise floor from rolling silence window
        noise_floor = 0.0
        if state.silence_energies:
            noise_floor = sum(state.silence_energies) / len(state.silence_energies)

        # Smoothed values for distress (rolling average)
        avg_rms = sum(state.recent_rms) / len(state.recent_rms)
        avg_zcr = sum(state.recent_zcr) / len(state.recent_zcr)

        # Classify
        loudness_label = _classify_loudness(avg_rms)
        environment = _classify_environment(noise_floor)
        distress_level = _compute_distress_level(avg_rms, avg_zcr, noise_floor)
        is_high_distress = (avg_rms > RMS_LOUD and avg_zcr > ZCR_HIGH)

        return AcousticSnapshot(
            rms=round(rms, 1),
            zcr=round(zcr, 1),
            is_high_distress=is_high_distress,
            distress_level=distress_level,
            environment=environment,
            noise_floor=round(noise_floor, 1),
            loudness_label=loudness_label,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
acoustic_service = AcousticService()
