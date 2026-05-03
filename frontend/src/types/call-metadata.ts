/**
 * CallMetadata — shared interface for call session metadata.
 *
 * Keep in sync with the backend Pydantic model:
 *   backend/app/models.py → CallMetadata
 */
export interface CallMetadata {
  /** Unique identifier for the call session */
  session_id: string;

  /** Whether the user is currently speaking */
  is_user_speaking: boolean;

  /** Detected sentiment of the current speaker */
  detected_sentiment: string;

  /** Whether the current action requires user confirmation */
  requires_confirmation: boolean;

  /** Acoustic distress level: 1 (calm) – 5 (extreme distress) */
  distress_level: number;

  /** Acoustic environment classification */
  environment: "quiet" | "moderate" | "noisy" | "chaotic";
}
