from __future__ import annotations

import json
import re
from typing import Any, Optional


def extract_json_array(text: str) -> list[dict]:
    candidates = _extract_json_blocks(text)
    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
        if isinstance(candidate, dict) and any(isinstance(v, list) for v in candidate.values()):
            for v in candidate.values():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                    return v
    return []


def extract_json_object(text: str) -> dict:
    candidates = _extract_json_blocks(text)
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return {}


def _extract_json_blocks(text: str) -> list[Any]:
    results = []

    fenced = re.findall(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    for block in fenced:
        parsed = _try_parse_json(block.strip())
        if parsed is not None:
            results.append(parsed)

    if results:
        return results

    parsed = _try_parse_json(text.strip())
    if parsed is not None:
        results.append(parsed)

    return results


def _try_parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass
        cleaned = _repair_json(candidate)
        if cleaned is not None:
            try:
                return json.loads(cleaned)
            except (json.JSONDecodeError, ValueError):
                pass

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass
        cleaned = _repair_json(candidate)
        if cleaned is not None:
            try:
                return json.loads(cleaned)
            except (json.JSONDecodeError, ValueError):
                pass

    return None


def _repair_json(text: str) -> Optional[str]:
    if not text:
        return None
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
    fixed = _fix_json_string_values(text)
    if fixed is not None:
        return fixed
    text = re.sub(r"(?<!\\)'", '"', text)
    text = re.sub(r'\\(?!["\\/bfnrtu])', "", text)
    return text


def _fix_json_string_values(text: str) -> Optional[str]:
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            j = i + 1
            while j < len(text):
                if text[j] == "\\" and j + 1 < len(text):
                    j += 2
                    continue
                if text[j] == '"':
                    raw = text[i + 1 : j]
                    escaped = (
                        raw.replace("\\", "\\\\")
                        .replace('"', '\\"')
                        .replace("\n", "\\n")
                        .replace("\r", "\\r")
                        .replace("\t", "\\t")
                    )
                    result.append('"')
                    result.append(escaped)
                    result.append('"')
                    i = j + 1
                    break
                j += 1
            else:
                result.append(ch)
                i += 1
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def normalize_severity(severity: str) -> str:
    severity = severity.lower().strip()
    mapping = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
        "minor": "low",
        "major": "high",
        "blocker": "critical",
    }
    return mapping.get(severity, "medium")


def truncate_text(text: str, max_length: int = 500) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
