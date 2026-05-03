"""
Shared Pydantic models — keep in sync with frontend TypeScript interfaces.
See: frontend/src/types/call-metadata.ts
"""

from pydantic import BaseModel, Field


class CallMetadata(BaseModel):
    """
    Metadata for an active call session.

    Mirrors the frontend TypeScript interface:
      frontend/src/types/call-metadata.ts → CallMetadata
    """

    session_id: str = Field(
        ...,
        description="Unique identifier for the call session",
    )
    is_user_speaking: bool = Field(
        default=False,
        description="Whether the user is currently speaking",
    )
    detected_sentiment: str = Field(
        default="neutral",
        description="Detected sentiment of the current speaker (e.g. 'positive', 'negative', 'neutral')",
    )
    requires_confirmation: bool = Field(
        default=False,
        description="Whether the current action requires user confirmation",
    )
    distress_level: int = Field(
        default=1,
        ge=1, le=5,
        description="Acoustic distress level: 1 (calm) – 5 (extreme distress)",
    )
    environment: str = Field(
        default="quiet",
        description="Acoustic environment: quiet | moderate | noisy | chaotic",
    )
