import type { CallMetadata } from "./call-metadata";

export interface ReasoningOutput {
  restatement: string;
  location: string | null;
  intent: string;
  urgency_level: number;
  sentiment: string;
  needs_verification: boolean;
  language_code: string;
}

export type CallState =
  | "GREETING"
  | "LISTENING"
  | "VERIFYING"
  | "ASSURANCE"
  | "ESCALATED";

export interface AcousticData {
  distress_level: number;
  environment: "quiet" | "moderate" | "noisy" | "chaotic";
  is_high_distress: boolean;
  loudness: "whisper" | "normal" | "loud" | "shouting";
  rms: number;
  zcr: number;
}

export interface PerformanceReport {
  understanding_score: number;
  cultural_accuracy: number;
  bottleneck_detected: string;
  coaching_tip: string;
}

export type ClientMessage =
  | { type: "start_call"; session_id: string }
  | { type: "end_call"; session_id: string }
  | { type: "audio_chunk"; data: string; session_id: string }
  | { type: "TOGGLE_TAKEOVER"; session_id: string };

export type ServerMessage =
  | { type: "audio_playback"; data: string }
  | { type: "audio_chunk"; data: string }
  | { type: "audio_done" }
  | { type: "interrupt" }
  | { type: "metadata"; data: CallMetadata }
  | { type: "transcript"; text: string; is_final: boolean }
  | { type: "reasoning_update"; data: ReasoningOutput }
  | { type: "call_summary"; data: PerformanceReport }
  | { type: "acoustic_update"; data: AcousticData }
  | { type: "state_change"; state: CallState; session_id: string }
  | { type: "error"; message: string };
