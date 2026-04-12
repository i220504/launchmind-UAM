from __future__ import annotations

import json
from typing import Any


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


def parse_json(text: str) -> dict[str, Any]:
    return json.loads(strip_code_fences(text))


def dump_json(data: Any, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(data, indent=2, ensure_ascii=False)
    return json.dumps(data, ensure_ascii=False)
