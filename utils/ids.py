from __future__ import annotations

import re
import uuid


def new_uuid() -> str:
    return str(uuid.uuid4())


def slugify(value: str, max_length: int = 48) -> str:
    lowered = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return (lowered or "launchmind")[:max_length].strip("-")
