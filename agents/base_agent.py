from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from messaging.message_schema import AgentMessage
from messaging.message_store import MessageStore
from messaging.redis_bus import RedisBus
from utils.logger import get_logger


class BaseAgent:
    def __init__(self, name: str, llm_client: Any, bus: RedisBus, store: MessageStore, artifacts_dir: Path) -> None:
        self.name = name
        self.llm_client = llm_client
        self.bus = bus
        self.store = store
        self.artifacts_dir = artifacts_dir
        self.logger = get_logger(f"agent.{name}")
        self.state: dict[str, Any] = {}

    def start(self) -> None:
        self.bus.subscribe(self.name, self._safe_handle_message)
        self.logger.info("%s agent started", self.name.upper())

    def _safe_handle_message(self, message: AgentMessage) -> None:
        self.logger.info(
            "Received message %s from=%s type=%s",
            message.message_id,
            message.from_agent,
            message.message_type,
        )
        self.store.append_event(
            "message_received",
            {"agent": self.name, "message_id": message.message_id, "from_agent": message.from_agent},
        )
        try:
            self.handle_message(message)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Unhandled error in %s: %s", self.name, exc)
            if self.name != "ceo":
                self.send_message(
                    "ceo",
                    "error",
                    {
                        "error": str(exc),
                        "failed_agent": self.name,
                        "original_message_id": message.message_id,
                    },
                    parent_message_id=message.message_id,
                )

    def handle_message(self, message: AgentMessage) -> None:
        raise NotImplementedError

    def send_message(
        self,
        to_agent: str,
        message_type: str,
        payload: dict[str, Any],
        *,
        parent_message_id: str | None = None,
    ) -> AgentMessage:
        message = AgentMessage(
            from_agent=self.name, to_agent=to_agent, message_type=message_type, payload=payload, parent_message_id=parent_message_id
        )
        self.store.append(message)
        self.bus.publish(message)
        return message

    def write_json_artifact(self, filename: str, payload: dict[str, Any]) -> Path:
        path = self.artifacts_dir / filename
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        return path

    def write_text_artifact(self, filename: str, content: str) -> Path:
        path = self.artifacts_dir / filename
        with path.open("w", encoding="utf-8") as handle:
            handle.write(content)
        return path
