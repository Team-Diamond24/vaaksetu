"""
Post-call analytics service powered by Groq.
"""

from __future__ import annotations

import asyncio
import json

from groq import Groq
from pydantic import BaseModel, Field

from app.config import settings


POST_MORTEM_MODEL = "llama-3.1-8b-instant"
POST_MORTEM_PROMPT = (
    "1092 QA. Score understanding(1-10), cultural_accuracy(1-10), "
    "name the main bottleneck, give one coaching sentence. Output JSON only."
)


class PerformanceReport(BaseModel):
    understanding_score: int = Field(ge=1, le=10)
    cultural_accuracy: int = Field(ge=1, le=10)
    bottleneck_detected: str
    coaching_tip: str


def _normalize_report_payload(payload: dict) -> dict:
    understanding = payload.get("understanding_score", payload.get("score", 3))
    cultural = payload.get("cultural_accuracy", payload.get("culture_score", 3))
    bottleneck = payload.get(
        "bottleneck_detected",
        payload.get("bottleneck", payload.get("issue", "Unknown bottleneck")),
    )
    coaching = payload.get(
        "coaching_tip",
        payload.get("tip", payload.get("advice", "Escalate sooner when the call stalls.")),
    )

    return {
        "understanding_score": max(1, min(10, int(understanding))),
        "cultural_accuracy": max(1, min(10, int(cultural))),
        "bottleneck_detected": str(bottleneck),
        "coaching_tip": str(coaching),
    }


class AnalyticsService:
    """Generates a post-call report with Groq JSON mode."""

    def __init__(self) -> None:
        self._client = Groq(api_key=settings.groq_api_key)

    def _post_mortem_sync(self, transcript_timeline: str) -> PerformanceReport:
        response = self._client.chat.completions.create(
            model=POST_MORTEM_MODEL,
            messages=[
                {"role": "system", "content": POST_MORTEM_PROMPT},
                {"role": "user", "content": transcript_timeline},
            ],
            temperature=0.2,
            max_tokens=220,
            response_format={"type": "json_object"},
        )
        content = (response.choices[0].message.content or "").strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        raw_payload = json.loads(content.strip())
        return PerformanceReport.model_validate(_normalize_report_payload(raw_payload))

    async def post_mortem(self, transcript_timeline: str) -> PerformanceReport | None:
        if not transcript_timeline.strip():
            return PerformanceReport(
                understanding_score=3,
                cultural_accuracy=3,
                bottleneck_detected="Insufficient speech captured",
                coaching_tip="Escalate to the operator sooner when no reliable transcript is available.",
            )

        try:
            return await asyncio.to_thread(self._post_mortem_sync, transcript_timeline)
        except Exception as exc:
            print(f"[AnalyticsService] Post-mortem error: {exc}")
            return None


analytics_service = AnalyticsService()
