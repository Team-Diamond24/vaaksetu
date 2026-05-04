# VaakSetu Refactoring Context & Requirements

## Project Overview
VaakSetu is a real-time AI-assisted emergency call system for the 1092 helpline in Karnataka, India. It handles multilingual calls (Kannada, Hindi, English) with dialect awareness, acoustic intelligence, and human-in-the-loop capabilities.

## Current Architecture

### Backend (Python/FastAPI)
- **Real-time WebSocket** audio streaming
- **Groq Whisper** for speech-to-text (16kHz PCM → text)
- **Groq LLM** for reasoning
- **Edge-TTS** for multilingual text-to-speech
- **SQLite** for analytics persistence

### Frontend (React/TypeScript)
- AudioWorklet-based real-time capture
- WebSocket client with streaming TTS playback
- Supervisor dashboard with live monitoring

### Key Services
1. **transcription_service.py** - Energy-based VAD + Groq Whisper STT
2. **reasoning_service.py** - LLM-based triage analysis
3. **speech_service.py** - Edge-TTS multilingual synthesis
4. **acoustic_service.py** - Real-time DSP (RMS, ZCR, distress scoring)
5. **cultural_service.py** - Dialect-aware RAG with 25+ regional slang terms
6. **call_service.py** - State machine for call lifecycle
7. **analytics_service.py** - Post-call performance reports

### Current Call States
- **LISTENING** - AI actively listening, will do full triage
- **VERIFYING** - AI restated issue, waiting for confirmation
- **CONFIRMED** - User confirmed, dispatching help
- **ESCALATED** - Human operator takeover

### Current Issues Fixed
1. ✅ WebSocket ECONNABORTED errors (Vite proxy config)
2. ✅ Aggressive barge-in logic (refined detection)
3. ✅ Missing greeting message (added multilingual greeting)
4. ✅ VAD threshold too low (increased from 1000 to 2500)
5. ✅ Auto-mute on empty transcripts (removed resilience takeover)

## REQUIRED REFACTORING

### 1. Enforce Strict Call Flow
**New State Machine:** GREETING → LISTENING → VERIFYING → ASSURANCE → ESCALATED

**State Definitions:**
- **GREETING** - Hardcoded TTS (NO LLM): "Namaskara, welcome to the 1092 Helpline. Are you facing a medical, fire, or police emergency?"
- **LISTENING** - LLM extracts intent, urgency, location, creates restatement, sets needs_verification=true
- **VERIFYING** - System asks Yes/No confirmation
- **ASSURANCE** - On "Yes", LLM generates brief assurance: "Help is on the way to [location]. Stay on the line."
- **ESCALATED** - Human operator takeover

**Files to modify:**
- `backend/app/services/call_service.py` - Add GREETING and ASSURANCE states
- `backend/app/main.py` - Update WebSocket handler for new flow
- `frontend/src/types/ws-messages.ts` - Add new states to CallState type

### 2. Complaint Logging
**New Feature:** Save confirmed complaints to JSON file

**Implementation:**
- Create `backend/app/data/complaints.json`
- Add method in `call_service.py`: `log_complaint(session_id, data)`
- Trigger on state transition: VERIFYING → ASSURANCE (user said "Yes")

**Complaint Record Schema:**
```json
{
  "session_id": "uuid",
  "timestamp": "ISO 8601",
  "location": "extracted by LLM",
  "complaint_text": "final restatement",
  "intent": "Medical|Fire|Crime",
  "urgency": 1-5,
  "distress_level": 1-5,
  "language": "en|hi|kn",
  "acoustic_data": {
    "environment": "quiet|moderate|noisy|chaotic",
    "loudness": "whisper|normal|loud|shouting"
  }
}
```

### 3. System Prompt Optimization
**Current:** Verbose multi-paragraph prompts
**Target:** Ultra-compact, token-efficient prompts

**Example Optimized Prompt:**
```
Role: 1092 emergency triage AI.
Extract: intent (Medical/Fire/Crime/Inquiry), urgency (1-5), location, restatement (1 sentence in caller's language).
Output: STRICT JSON, no markdown.
Context: [cultural_slang_if_detected] [acoustic: distress=X, env=Y]
```

## Current File Structure
```
vaaksetu/
├── backend/
│   ├── app/
│   │   ├── services/
│   │   │   ├── reasoning_service.py      ← REFACTOR
│   │   │   ├── analytics_service.py      ← REFACTOR
│   │   │   ├── call_service.py           ← UPDATE (add states)
│   │   │   ├── transcription_service.py  ← KEEP AS IS
│   │   │   ├── speech_service.py         ← KEEP AS IS
│   │   │   ├── acoustic_service.py       ← KEEP AS IS
│   │   │   └── cultural_service.py       ← KEEP AS IS
│   │   ├── data/
│   │   │   ├── cultural_slang.json       ← KEEP AS IS
│   │   │   └── complaints.json           ← CREATE NEW
│   │   ├── config.py                     ← UPDATE
│   │   ├── main.py                       ← UPDATE (call flow)
│   │   └── models.py                     ← UPDATE (add states)
│   ├── .env                              ← UPDATE
│   └── requirements.txt                  ← VERIFY
└── frontend/
    └── src/
        └── types/
            └── ws-messages.ts            ← UPDATE (add states)
```

## API Keys Required
- ✅ **GROQ_API_KEY** - Already configured (Whisper STT + LLM reasoning)

## Existing Features to Preserve
1. ✅ Dialect-aware RAG (cultural_service.py)
2. ✅ Acoustic intelligence (acoustic_service.py)
3. ✅ Energy-based VAD (transcription_service.py)
4. ✅ Multilingual TTS (speech_service.py)
5. ✅ Human takeover (TOGGLE_TAKEOVER)
6. ✅ Barge-in detection
7. ✅ WebSocket streaming
8. ✅ Post-call analytics

## Testing Checklist After Refactoring
- [ ] Greeting plays on call start (hardcoded, no LLM)
- [ ] LLM extracts location from transcript
- [ ] Confirmation flow works (Yes/No detection)
- [ ] Assurance message includes location
- [ ] Complaint logged to complaints.json on confirmation
- [ ] All existing features still work
- [ ] No markdown in LLM responses
- [ ] State transitions: GREETING → LISTENING → VERIFYING → ASSURANCE

## Priority Order
1. **HIGH** - Update call_service.py with new states (GREETING, ASSURANCE)
2. **HIGH** - Implement complaint logging
3. **MEDIUM** - Update main.py WebSocket handler for new flow
4. **MEDIUM** - Optimize system prompts for token efficiency
5. **LOW** - Update frontend types for new states

## Notes
- Current VAD threshold: 2500 (works well, don't change)
- Current Groq model: whisper-large-v3 (keep as is)
- Current TTS: Edge-TTS (free, keep as is)
- Database: SQLite (keep as is)
- WebSocket endpoint: /ws/call (keep as is)

## Success Criteria
- ✅ Groq LLM reasoning working
- ✅ Complaint logging functional
- ✅ New call flow enforced
- ✅ All existing features preserved
- ✅ No regression in accuracy
