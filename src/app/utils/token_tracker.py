from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

import structlog

logger = structlog.get_logger("token_tracker")


class TokenUsageRecord:
    __slots__ = ("stage", "model", "prompt_tokens", "completion_tokens", "total_tokens", "duration_ms")

    def __init__(
        self,
        stage: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        duration_ms: float,
    ):
        self.stage = stage
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.duration_ms = duration_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": round(self.duration_ms),
        }


class TokenTracker:
    def __init__(self):
        self._records: list[TokenUsageRecord] = []
        self._lock = threading.Lock()

    def record(
        self,
        stage: str,
        model: str,
        usage: dict[str, Any],
        duration_ms: float,
    ) -> None:
        rec = TokenUsageRecord(
            stage=stage or "unknown",
            model=model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            duration_ms=duration_ms,
        )
        with self._lock:
            self._records.append(rec)
        logger.debug(
            "token_recorded",
            stage=rec.stage,
            model=rec.model,
            total_tokens=rec.total_tokens,
        )

    @property
    def total_tokens(self) -> int:
        with self._lock:
            return sum(r.total_tokens for r in self._records)

    @property
    def total_prompt_tokens(self) -> int:
        with self._lock:
            return sum(r.prompt_tokens for r in self._records)

    @property
    def total_completion_tokens(self) -> int:
        with self._lock:
            return sum(r.completion_tokens for r in self._records)

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._records)

        by_model: dict[str, dict[str, int]] = defaultdict(
            lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0, "duration_ms": 0}
        )
        by_stage: dict[str, dict[str, int]] = defaultdict(
            lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0, "duration_ms": 0}
        )

        for r in records:
            by_model[r.model]["prompt_tokens"] += r.prompt_tokens
            by_model[r.model]["completion_tokens"] += r.completion_tokens
            by_model[r.model]["total_tokens"] += r.total_tokens
            by_model[r.model]["calls"] += 1
            by_model[r.model]["duration_ms"] += round(r.duration_ms)

            by_stage[r.stage]["prompt_tokens"] += r.prompt_tokens
            by_stage[r.stage]["completion_tokens"] += r.completion_tokens
            by_stage[r.stage]["total_tokens"] += r.total_tokens
            by_stage[r.stage]["calls"] += 1
            by_stage[r.stage]["duration_ms"] += round(r.duration_ms)

        return {
            "total_tokens": sum(r.total_tokens for r in records),
            "total_prompt_tokens": sum(r.prompt_tokens for r in records),
            "total_completion_tokens": sum(r.completion_tokens for r in records),
            "total_calls": len(records),
            "total_duration_ms": sum(round(r.duration_ms) for r in records),
            "by_model": dict(by_model),
            "by_stage": dict(by_stage),
            "calls": [r.to_dict() for r in records],
        }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
