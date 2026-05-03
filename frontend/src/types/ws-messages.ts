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

/* ---------- client → server ---------- */
export type ClientMessage =
  | { type: "start_call"; session_id: string }
  | { type: "end_call"; session_id: string }
  | { type: "audio_chunk"; data: string; session_id: string };

/* ---------- server → client ---------- */
export type ServerMessage =
  | { type: "audio_playback"; data: string }
  | { type: "interrupt" }
  | { type: "metadata"; data: CallMetadata }
  | { type: "transcript"; text: string; is_final: boolean }
  | { type: "reasoning_update"; data: ReasoningOutput }
  | { type: "error"; message: string };
