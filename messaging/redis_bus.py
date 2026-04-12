from __future__ import annotations

import json
import threading
from collections.abc import Callable

import redis

from config import settings
from messaging.message_schema import AgentMessage
from utils.logger import get_logger
from utils.retry import retry_call


class RedisBus:
    def __init__(self, channel_prefix: str | None = None) -> None:
        self.logger = get_logger("redis_bus")
        self.client = redis.from_url(settings.redis_url, decode_responses=True)
        self.channel_prefix = channel_prefix or settings.redis_channel_prefix
        self._threads: list[threading.Thread] = []

    def ping(self) -> None:
        retry_call(lambda: self.client.ping(), retry_on=(redis.RedisError,))
        self.logger.info("Redis connection established")

    def _channel(self, agent_name: str) -> str:
        return f"{self.channel_prefix}:{agent_name}"

    def publish(self, message: AgentMessage) -> None:
        channel = self._channel(message.to_agent)

        def _do_publish() -> int:
            return self.client.publish(channel, message.model_dump_json())

        retry_call(_do_publish, retry_on=(redis.RedisError,))
        self.logger.info(
            "Published message %s from=%s to=%s type=%s",
            message.message_id,
            message.from_agent,
            message.to_agent,
            message.message_type,
        )

    def subscribe(self, agent_name: str, handler: Callable[[AgentMessage], None]) -> None:
        def _listener() -> None:
            pubsub = self.client.pubsub(ignore_subscribe_messages=True)
            channel = self._channel(agent_name)
            pubsub.subscribe(channel)
            self.logger.info("Subscribed %s to %s", agent_name, channel)
            for event in pubsub.listen():
                try:
                    payload = event["data"]
                    if isinstance(payload, bytes):
                        payload = payload.decode("utf-8")
                    message = AgentMessage.model_validate(json.loads(payload))
                    handler(message)
                except Exception as exc:  # noqa: BLE001
                    self.logger.exception("Subscriber error for %s: %s", agent_name, exc)

        thread = threading.Thread(target=_listener, name=f"redis-{agent_name}", daemon=True)
        thread.start()
        self._threads.append(thread)
