from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel

import structlog

logger = structlog.get_logger("complexity_router")


class ComplexityLevel(str, Enum):
    MINOR = "minor"
    STANDARD = "standard"
    MAJOR = "major"


class ComplexityResult(BaseModel):
    level: ComplexityLevel
    score: int
    reasoning: str
    profile: str
    estimated_latency_seconds: int


_COMPLEXITY_PROMPT = """Analyze this document and assess its complexity for a document quality review pipeline.

Rate complexity from 1-10:
- 1-3 (Minor): Small changes, typo fixes, config tweaks, simple UI updates. No architectural impact.
- 4-6 (Standard): Feature additions, moderate refactors, new endpoints. Some architectural consideration needed.
- 7-10 (Major): Architecture changes, migrations, breaking changes, multi-service impacts. Full deep analysis required.

Document type: {doc_type}

Document content:
{content}

Respond in this exact JSON format:
{{"score": <1-10>, "reasoning": "<one sentence explanation>", "level": "<minor|standard|major>"}}

Only output the JSON, nothing else."""


def route_complexity(
    client,
    content: str,
    doc_type: str,
) -> ComplexityResult:
    prompt = _COMPLEXITY_PROMPT.format(
        doc_type=doc_type,
        content=content[:8000],
    )

    model = client.resolve_model("critic_a")
    response = client.chat_completion(
        model=model,
        messages=[
            {"role": "system", "content": "You are a document complexity assessor. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=256,
        stage="complexity_router",
    )

    raw = response.get("content", "").strip()
    logger.info("complexity_router_raw", raw=raw[:200])

    try:
        import json

        text = raw
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        parsed = json.loads(text)

        score = max(1, min(10, int(parsed.get("score", 5))))
        level_str = parsed.get("level", "standard").lower()
        reasoning = parsed.get("reasoning", "")

        from app.config import load_pipeline_profile_config

        profile_config = load_pipeline_profile_config()
        router_config = profile_config.get("complexity_router", {})
        thresholds = router_config.get("thresholds", {})
        mapping = router_config.get("profile_mapping", {})

        if level_str == "minor" or score <= thresholds.get("minor_change", 3):
            level = ComplexityLevel.MINOR
        elif level_str == "major" or score >= thresholds.get("major_change", 7):
            level = ComplexityLevel.MAJOR
        else:
            level = ComplexityLevel.STANDARD

        profile = mapping.get(level.value, "standard")
        profiles = profile_config.get("profiles", {})
        est_latency = profiles.get(profile, {}).get("estimated_latency_seconds", 300)

        result = ComplexityResult(
            level=level,
            score=score,
            reasoning=reasoning,
            profile=profile,
            estimated_latency_seconds=est_latency,
        )
        logger.info(
            "complexity_routed",
            score=score,
            level=level.value,
            profile=profile,
            reasoning=reasoning,
        )
        return result

    except Exception as e:
        logger.warning("complexity_router_parse_failed", error=str(e), fallback="standard")
        return ComplexityResult(
            level=ComplexityLevel.STANDARD,
            score=5,
            reasoning=f"Fallback due to parse error: {e}",
            profile="standard",
            estimated_latency_seconds=240,
        )
