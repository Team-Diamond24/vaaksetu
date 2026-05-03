import type { CallMetadata } from "./call-metadata";

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
  | { type: "error"; message: string };
