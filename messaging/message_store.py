from __future__ import annotations

from pathlib import Path
from typing import Any

from messaging.message_schema import AgentMessage
from utils.logger import audit_logger


class MessageStore:
    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def append(self, message: AgentMessage) -> None:
        audit_logger.write({"event_type": "message", "message": message.model_dump()})
        with self.filepath.open("a", encoding="utf-8") as handle:
            handle.write(message.model_dump_json() + "\n")

    def append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"event_type": event_type, "payload": payload}
        audit_logger.write(event)
        with self.filepath.open("a", encoding="utf-8") as handle:
            import json

            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
