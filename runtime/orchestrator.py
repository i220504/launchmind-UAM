from __future__ import annotations

import time
from uuid import uuid4

from config import settings

from agents.ceo_agent import CEOAgent
from agents.engineer_agent import EngineerAgent
from agents.marketing_agent import MarketingAgent
from agents.product_agent import ProductAgent
from agents.qa_agent import QAAgent
from integrations.email_client import EmailClient
from integrations.github_client import GitHubClient
from integrations.slack_client import SlackClient
from llm.openai_client import OpenAIClient
from messaging.message_store import MessageStore
from messaging.redis_bus import RedisBus
from utils.logger import get_logger


class LaunchMindOrchestrator:
    def __init__(self) -> None:
        self.logger = get_logger("orchestrator")
        self.run_id = uuid4().hex[:8]
        self.store = MessageStore(settings.logs_dir / "message_history.jsonl")
        self.channel_prefix = f"{settings.redis_channel_prefix}:{self.run_id}"
        self.bus = RedisBus(channel_prefix=self.channel_prefix)
        self.llm_client = OpenAIClient()
        self.github_client = GitHubClient()
        self.slack_client = SlackClient()
        self.email_client = EmailClient()

        self.ceo = CEOAgent(
            "ceo",
            self.llm_client,
            self.bus,
            self.store,
            settings.artifacts_dir,
            slack_client=self.slack_client,
        )
        self.product = ProductAgent("product", self.llm_client, self.bus, self.store, settings.artifacts_dir)
        self.engineer = EngineerAgent(
            "engineer",
            self.llm_client,
            self.bus,
            self.store,
            settings.artifacts_dir,
            github_client=self.github_client,
        )
        self.marketing = MarketingAgent(
            "marketing",
            self.llm_client,
            self.bus,
            self.store,
            settings.artifacts_dir,
            slack_client=self.slack_client,
            email_client=self.email_client,
        )
        self.qa = QAAgent(
            "qa",
            self.llm_client,
            self.bus,
            self.store,
            settings.artifacts_dir,
            github_client=self.github_client,
        )

    def validate_integrations(self) -> None:
        self.logger.info("Using Redis channel prefix %s", self.channel_prefix)
        self.bus.ping()
        self.github_client.validate()
        self.slack_client.validate()
        self.email_client.validate()
        self.logger.info("All external integrations validated")

    def start_agents(self) -> None:
        for agent in (self.ceo, self.product, self.engineer, self.marketing, self.qa):
            agent.start()
        time.sleep(1.0)
        self.logger.info("All agents subscribed and ready")
