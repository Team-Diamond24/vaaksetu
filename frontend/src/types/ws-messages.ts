import type { CallMetadata } from "./call-metadata";

/**
 * Structured analysis returned by the VaakSetu Intelligence Layer (Gemini).
 * Mirrors: backend/app/services/reasoning_service.py → ReasoningOutput
 */
export interface ReasoningOutput {
  /** 1-sentence confirmation in the caller's language */
  restatement: string;
  /** Medical | Fire | Crime | Inquiry */
  intent: string;
  /** 1 (low) – 5 (life-threatening) */
  urgency_level: number;
  /** positive | negative | neutral | fearful | angry | distressed */
  sentiment: string;
  /** true if the transcript is ambiguous or high-stakes */
  needs_verification: boolean;
  /** ISO 639-1 code (en, hi, kn, …) */
  language_code: string;
}

/** Call lifecycle state — mirrors backend CallState enum */
export type CallState = "LISTENING" | "VERIFYING" | "CONFIRMED" | "ESCALATED";

/** Real-time acoustic analysis data from the backend */
export interface AcousticData {
  distress_level: number;
  environment: "quiet" | "moderate" | "noisy" | "chaotic";
  is_high_distress: boolean;
  loudness: "whisper" | "normal" | "loud" | "shouting";
  rms: number;
  zcr: number;
}

/* ---------- client → server ---------- */
export type ClientMessage =
  | { type: "start_call"; session_id: string }
  | { type: "end_call"; session_id: string }
  | { type: "audio_chunk"; data: string; session_id: string }
  | { type: "TOGGLE_TAKEOVER"; session_id: string };

/* ---------- server → client ---------- */
export type ServerMessage =
  | { type: "audio_playback"; data: string }
  | { type: "audio_chunk"; data: string }
  | { type: "audio_done" }
  | { type: "interrupt" }
  | { type: "metadata"; data: CallMetadata }
  | { type: "transcript"; text: string; is_final: boolean }
  | { type: "reasoning_update"; data: ReasoningOutput }
  | { type: "acoustic_update"; data: AcousticData }
  | { type: "state_change"; state: CallState; session_id: string }
  | { type: "error"; message: string };
