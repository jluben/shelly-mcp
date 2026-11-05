"""Parse RPC params from MCP tool arguments (forgiving JSON)."""

from __future__ import annotations

import json
import re


def parse_params(params_json: str | None) -> dict | None:
    if params_json is None:
        return None
    raw = str(params_json).strip()
    if not raw:
        return None
    raw = _strip_markdown_fence(raw)
    data = _load_json_lenient(raw)
    if data is None:
        return None
    if isinstance(data, str):
        data = _load_json_lenient(data.strip())
    if not isinstance(data, dict):
        raise ValueError(
            "params_json must be a JSON object, e.g. {\"id\": 0, \"on\": false}"
        )
    return data


def _strip_markdown_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 2 and lines[-1].strip().startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return text


def _load_json_lenient(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Common model mistake: Python-style True/False/None
    normalized = re.sub(r"\bTrue\b", "true", raw)
    normalized = re.sub(r"\bFalse\b", "false", normalized)
    normalized = re.sub(r"\bNone\b", "null", normalized)
    try:
        return json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid params_json: {exc.msg}") from exc
