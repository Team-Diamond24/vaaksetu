"""
Call session service — business logic for managing call metadata.
"""

import uuid

from app.models import CallMetadata


class CallService:
    """Handles call session lifecycle and metadata operations."""

    @staticmethod
    def create_session() -> CallMetadata:
        """Create a new call session with default metadata."""
        return CallMetadata(
            session_id=str(uuid.uuid4()),
            is_user_speaking=False,
            detected_sentiment="neutral",
            requires_confirmation=False,
        )

    @staticmethod
    def update_sentiment(
        metadata: CallMetadata, sentiment: str
    ) -> CallMetadata:
        """Return a new metadata instance with updated sentiment."""
        return metadata.model_copy(update={"detected_sentiment": sentiment})

    @staticmethod
    def toggle_speaking(
        metadata: CallMetadata, is_speaking: bool
    ) -> CallMetadata:
        """Return a new metadata instance with updated speaking state."""
        return metadata.model_copy(update={"is_user_speaking": is_speaking})


call_service = CallService()
