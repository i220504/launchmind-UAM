from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from utils.ids import new_uuid
from utils.time_utils import utc_now_iso


AgentName = Literal["ceo", "product", "engineer", "marketing", "qa"]
MessageType = Literal["task", "result", "revision_request", "confirmation", "error"]


class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=new_uuid)
    from_agent: AgentName
    to_agent: AgentName
    message_type: MessageType
    payload: dict[str, Any]
    timestamp: str = Field(default_factory=utc_now_iso)
    parent_message_id: str | None = None

