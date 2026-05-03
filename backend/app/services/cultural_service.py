"""
Cultural Context Service — Kannada dialect & regional slang intelligence.

Provides a JSON-based lookup table of regional dialect variations across
Karnataka's major dialect zones (North Karnataka / Uttara Kannada,
Old Mysore / South Karnataka, Coastal Karnataka, Hyderabad-Karnataka)
and emergency-specific slang terms.

Usage:
    from app.services.cultural_service import cultural_context_service

    ctx = cultural_context_service.get_context(transcript)
    # ctx.context_string  → ready-to-inject prompt fragment
    # ctx.matched_terms   → list of matched slang entries
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data path
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_SLANG_FILE = _DATA_DIR / "cultural_slang.json"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@dataclass
class SlangEntry:
    """A single slang / dialect mapping."""

    term: str                    # the colloquial / dialectal term
    canonical: str               # standard Kannada / English equivalent
    definition: str              # plain English explanation
    region: str                  # dialect zone (e.g. "North Karnataka")
    domain: str                  # emergency domain: medical | fire | crime | general
    urgency_hint: int | None = None  # optional urgency bump (1-5)


@dataclass
class CulturalContext:
    """Result returned by the service for a given transcript."""

    matched_terms: list[SlangEntry] = field(default_factory=list)
    context_string: str = ""


# ---------------------------------------------------------------------------
# Default slang corpus (embedded fallback — overridden by JSON file)
# ---------------------------------------------------------------------------
_DEFAULT_CORPUS: list[dict] = [
    # ── North Karnataka (Uttara Kannada / Dharwad / Belgaum) ──────────────
    {
        "term": "ಉಸಿರಾಡಕ್ಕಾಗವಲ್ದು",
        "canonical": "ಉಸಿರಾಡಲು ಆಗುತ್ತಿಲ್ಲ",
        "definition": "Cannot breathe — severe respiratory distress. "
                      "North Karnataka dialect omits the standard auxiliary verb form.",
        "region": "North Karnataka",
        "domain": "medical",
        "urgency_hint": 5,
    },
    {
        "term": "ರೊಕ್ಕ",
        "canonical": "ಹಣ / ದುಡ್ಡು",
        "definition": "Money — in crime contexts may indicate robbery or extortion.",
        "region": "North Karnataka",
        "domain": "crime",
        "urgency_hint": None,
    },
    {
        "term": "ಹೊಟ್ಟಿ ಬಾಕ ಬಂದೈತಿ",
        "canonical": "ಹೊಟ್ಟೆ ತುಂಬಾ ನೋಯುತ್ತಿದೆ",
        "definition": "Severe stomach pain — 'baak' is a North Karnataka intensifier "
                      "implying acute distress, not mild discomfort.",
        "region": "North Karnataka",
        "domain": "medical",
        "urgency_hint": 3,
    },
    {
        "term": "ರಗಡ",
        "canonical": "ಜಗಳ / ಹೊಡೆದಾಟ",
        "definition": "A violent fight or brawl — implies active physical altercation.",
        "region": "North Karnataka",
        "domain": "crime",
        "urgency_hint": 4,
    },
    {
        "term": "ಬೆಂಕಿ ಹಚ್ಚಾರ",
        "canonical": "ಬೆಂಕಿ ಹಚ್ಚಿದ್ದಾರೆ",
        "definition": "Someone set fire — implies deliberate arson, "
                      "North Karnataka past-tense marker '-aar'.",
        "region": "North Karnataka",
        "domain": "fire",
        "urgency_hint": 5,
    },
    {
        "term": "ಹಿಡ್ಕೊಂಡ್ ಹೋಗ್ಯಾರ",
        "canonical": "ಹಿಡಿದುಕೊಂಡು ಹೋಗಿದ್ದಾರೆ",
        "definition": "They have taken someone away (abduction/kidnapping). "
                      "Contracted verb form typical of Dharwad-Belgaum belt.",
        "region": "North Karnataka",
        "domain": "crime",
        "urgency_hint": 5,
    },
    {
        "term": "ಗಾಡಿ ಬಿದ್ದೈತಿ",
        "canonical": "ವಾಹನ ಅಪಘಾತವಾಗಿದೆ",
        "definition": "Vehicle has crashed / accident. 'Gaadi biddaiti' is North Karnataka "
                      "dialect for a road accident.",
        "region": "North Karnataka",
        "domain": "medical",
        "urgency_hint": 4,
    },

    # ── Old Mysore / South Karnataka ─────────────────────────────────────
    {
        "term": "ಉಸ್ರು ಬರ್ತಿಲ್ಲ",
        "canonical": "ಉಸಿರು ಬರುತ್ತಿಲ್ಲ",
        "definition": "Cannot breathe — Old Mysore dialect. Vowel shift from "
                      "'usiru' to 'usru', 'bartilla' negative form.",
        "region": "Old Mysore",
        "domain": "medical",
        "urgency_hint": 5,
    },
    {
        "term": "ಎದಿ ನೋವು",
        "canonical": "ಎದೆ ನೋವು",
        "definition": "Chest pain. 'Edi' is the Mysore-region pronunciation of 'ede' (chest).",
        "region": "Old Mysore",
        "domain": "medical",
        "urgency_hint": 4,
    },
    {
        "term": "ಹೊಡ್ತಾ ಇದಾರೆ",
        "canonical": "ಹೊಡೆಯುತ್ತಿದ್ದಾರೆ",
        "definition": "They are beating (someone) — ongoing physical assault.",
        "region": "Old Mysore",
        "domain": "crime",
        "urgency_hint": 4,
    },
    {
        "term": "ಕಳ್ಳ ಬಂದವ್ನೆ",
        "canonical": "ಕಳ್ಳ ಬಂದಿದ್ದಾನೆ",
        "definition": "A thief has come / intruder present — active burglary in progress.",
        "region": "Old Mysore",
        "domain": "crime",
        "urgency_hint": 4,
    },
    {
        "term": "ತಲಿ ತಿರ್ಗತೈತೆ",
        "canonical": "ತಲೆ ತಿರುಗುತ್ತಿದೆ",
        "definition": "Severe dizziness / vertigo — may indicate stroke, "
                      "low BP, or head injury. Mysore pronunciation of 'tale'→'tali'.",
        "region": "Old Mysore",
        "domain": "medical",
        "urgency_hint": 3,
    },

    # ── Coastal Karnataka (Mangalore / Udupi) ────────────────────────────
    {
        "term": "ಜ್ವರ ಬೈಂದು",
        "canonical": "ಜ್ವರ ಬಂದಿದೆ",
        "definition": "Has fever. Coastal dialect uses 'baindu' (Tulu-influenced past tense).",
        "region": "Coastal Karnataka",
        "domain": "medical",
        "urgency_hint": 2,
    },
    {
        "term": "ನೀರ್ ಬಂದ್ಹೋಯ್ದು",
        "canonical": "ನೀರು ಬಂದು ಹೋಗಿದೆ",
        "definition": "Flooding — water has come in. Coastal contraction "
                      "'bandhoydu' implies sudden flooding.",
        "region": "Coastal Karnataka",
        "domain": "fire",  # floods often routed through fire/rescue
        "urgency_hint": 4,
    },

    # ── Hyderabad-Karnataka (Kalaburagi / Raichur / Bidar) ───────────────
    {
        "term": "ಖೂನ ಆಗೈತಿ",
        "canonical": "ಕೊಲೆ ಆಗಿದೆ",
        "definition": "A murder has happened. 'Khoona' is the Urdu-influenced "
                      "Hyderabad-Karnataka term for murder/homicide.",
        "region": "Hyderabad-Karnataka",
        "domain": "crime",
        "urgency_hint": 5,
    },
    {
        "term": "ದವಾಖಾನಿ",
        "canonical": "ಆಸ್ಪತ್ರೆ",
        "definition": "Hospital — Urdu-influenced word 'dawakhani' used across "
                      "Hyderabad-Karnataka instead of standard 'aaspatre'.",
        "region": "Hyderabad-Karnataka",
        "domain": "medical",
        "urgency_hint": None,
    },
    {
        "term": "ಹೊಡ್ದಾರ ಸಾಹೇಬ",
        "canonical": "ಹೊಡೆದಿದ್ದಾರೆ ಸರ್",
        "definition": "Someone has been beaten — 'Saheb' is the honorific "
                      "for authority figures in Hyderabad-Karnataka dialect.",
        "region": "Hyderabad-Karnataka",
        "domain": "crime",
        "urgency_hint": 3,
    },

    # ── Hindi slang (callers who code-switch) ────────────────────────────
    {
        "term": "सांस नहीं आ रही",
        "canonical": "सांस लेने में कठिनाई",
        "definition": "Cannot breathe — Hindi. Critical respiratory distress.",
        "region": "Hindi-speaking",
        "domain": "medical",
        "urgency_hint": 5,
    },
    {
        "term": "मार रहे हैं",
        "canonical": "मारपीट हो रही है",
        "definition": "They are beating (someone) — active assault in Hindi.",
        "region": "Hindi-speaking",
        "domain": "crime",
        "urgency_hint": 4,
    },
    {
        "term": "आग लगी है",
        "canonical": "अग्निकांड",
        "definition": "Fire has started — active fire in Hindi.",
        "region": "Hindi-speaking",
        "domain": "fire",
        "urgency_hint": 5,
    },
    {
        "term": "चोर आया है",
        "canonical": "चोरी हो रही है",
        "definition": "A thief has come — active burglary/intrusion.",
        "region": "Hindi-speaking",
        "domain": "crime",
        "urgency_hint": 4,
    },

    # ── English colloquial ───────────────────────────────────────────────
    {
        "term": "gas leak",
        "canonical": "LPG / gas cylinder leakage",
        "definition": "Domestic gas leak — fire & explosion risk.",
        "region": "English-speaking",
        "domain": "fire",
        "urgency_hint": 5,
    },
    {
        "term": "chain snatching",
        "canonical": "robbery / theft of jewellery",
        "definition": "Street robbery targeting necklaces/chains — common urban crime term.",
        "region": "English-speaking",
        "domain": "crime",
        "urgency_hint": 3,
    },
    {
        "term": "eve teasing",
        "canonical": "sexual harassment",
        "definition": "South Asian colloquial term for sexual harassment in public spaces.",
        "region": "English-speaking",
        "domain": "crime",
        "urgency_hint": 3,
    },
]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class CulturalContextService:
    """
    Loads regional slang entries and provides transcript → context mapping.

    On init, tries to load from ``app/data/cultural_slang.json``.
    Falls back to the embedded ``_DEFAULT_CORPUS`` if the file is missing.
    """

    def __init__(self) -> None:
        self._entries: list[SlangEntry] = []
        self._load_corpus()

    # -- loading -------------------------------------------------------------

    def _load_corpus(self) -> None:
        """Load from JSON file, fall back to embedded default."""
        raw: list[dict] = []
        if _SLANG_FILE.exists():
            try:
                raw = json.loads(_SLANG_FILE.read_text(encoding="utf-8"))
                print(f"[CulturalContext] Loaded {len(raw)} entries from {_SLANG_FILE}")
            except Exception as exc:
                print(f"[CulturalContext] JSON load failed ({exc}), using defaults")
                raw = _DEFAULT_CORPUS
        else:
            raw = _DEFAULT_CORPUS
            # Persist the defaults so they can be edited later
            self._persist_defaults()

        self._entries = [SlangEntry(**e) for e in raw]

    def _persist_defaults(self) -> None:
        """Write the embedded corpus to disk so operators can edit it."""
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            _SLANG_FILE.write_text(
                json.dumps(_DEFAULT_CORPUS, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[CulturalContext] Persisted default corpus to {_SLANG_FILE}")
        except Exception as exc:
            print(f"[CulturalContext] Could not persist defaults: {exc}")

    # -- public API ----------------------------------------------------------

    def reload(self) -> None:
        """Hot-reload the corpus from disk (e.g. after an admin edit)."""
        self._entries.clear()
        self._load_corpus()

    def get_context(self, transcript: str) -> CulturalContext:
        """
        Scan *transcript* for known regional / slang terms and build a
        'Linguistic Context' string ready for injection into the LLM prompt.

        Returns a ``CulturalContext`` with the matches and the assembled string.
        """
        if not transcript:
            return CulturalContext()

        matched: list[SlangEntry] = []
        text_lower = transcript.lower()

        for entry in self._entries:
            # Case-insensitive substring match for Latin-script terms;
            # exact substring for Devanagari / Kannada script (already
            # case-insensitive by nature).
            term = entry.term
            if _is_latin(term):
                if term.lower() in text_lower:
                    matched.append(entry)
            else:
                if term in transcript:
                    matched.append(entry)

        if not matched:
            return CulturalContext()

        # De-duplicate (a term may appear multiple times in the transcript)
        seen: set[str] = set()
        unique: list[SlangEntry] = []
        for m in matched:
            if m.term not in seen:
                seen.add(m.term)
                unique.append(m)

        context_lines = [
            "## Linguistic Context (auto-detected regional markers)"
        ]
        for entry in unique:
            line = (
                f"- The caller used the regional term \"{entry.term}\" "
                f"({entry.region}), which is the dialectal form of "
                f"\"{entry.canonical}\". In this region it implies: "
                f"{entry.definition}"
            )
            if entry.urgency_hint:
                line += f" [suggested urgency ≥ {entry.urgency_hint}]"
            context_lines.append(line)

        context_lines.append(
            "\nAdjust your restatement to reflect these regional nuances. "
            "Mirror the caller's dialectal tone to build trust — do NOT "
            "over-formalize into textbook Kannada / Hindi."
        )

        return CulturalContext(
            matched_terms=unique,
            context_string="\n".join(context_lines),
        )

    @property
    def entry_count(self) -> int:
        """Number of loaded slang entries."""
        return len(self._entries)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_latin(text: str) -> bool:
    """Return True if the first alphabetic char is Latin-script."""
    for ch in text:
        if ch.isalpha():
            return ch.isascii()
    return True


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
cultural_context_service = CulturalContextService()
