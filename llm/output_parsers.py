from __future__ import annotations

from typing import Any

from utils.json_utils import parse_json


def expect_json(text: str) -> dict[str, Any]:
    data = parse_json(text)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object from model output")
    return data
