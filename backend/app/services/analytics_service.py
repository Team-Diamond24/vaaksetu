"""
Post-call analytics service — generates coach-style performance reports.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from openai import AsyncOpenAI

from app.config import settings


class PerformanceReport(BaseModel):
    """Structured post-mortem report shown to the supervisor."""

    understanding_score: int = Field(
        ge=1,
        le=10,
        description="How well the AI/operator understood and resolved the issue.",
    )
    cultural_accuracy: int = Field(
        ge=1,
        le=10,
        description="How accurately regional language and dialect were interpreted.",
    )
    bottleneck_detected: str = Field(
        description="Main point where the caller became frustrated or progress stalled."
    )
    coaching_tip: str = Field(
        description="One sentence actionable coaching tip for the human operator."
    )


POST_MORTEM_PROMPT = """\
You are the VaakSetu Call Coach.

Given the full transcript timeline of a completed helpline call, output a strict JSON object:
- understanding_score (1-10)
- cultural_accuracy (1-10)
- bottleneck_detected (short phrase)
- coaching_tip (exactly one sentence)

Scoring guidance:
- understanding_score: quality of issue comprehension and resolution flow.
- cultural_accuracy: handling of multilingual / dialect cues with empathy and correctness.
- bottleneck_detected: where the conversation slowed, repeated, or confusion emerged.
- coaching_tip: specific operator action that would most improve next call.

Return only valid JSON matching the schema.
"""


class AnalyticsService:
    """Generates a post-call performance report via Gemini Flash."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
        )
        self._model = "google/gemini-2.5-flash"

    async def post_mortem(self, transcript_timeline: str) -> PerformanceReport | None:
        """Generate final performance report from full call transcript."""
        if not transcript_timeline.strip():
            return PerformanceReport(
                understanding_score=3,
                cultural_accuracy=3,
                bottleneck_detected="Insufficient speech captured",
                coaching_tip="Escalate to the operator sooner when no reliable transcript is available.",
            )

        try:
            response = await self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": POST_MORTEM_PROMPT},
                    {"role": "user", "content": f"Call transcript timeline:\n\n{transcript_timeline}"},
                ],
                response_format=PerformanceReport,
                temperature=0.2,
                max_tokens=300,
            )
            return response.choices[0].message.parsed
        except Exception as exc:
            print(f"[AnalyticsService] Post-mortem error: {exc}")
            return None


analytics_service = AnalyticsService()
