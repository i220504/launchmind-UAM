from __future__ import annotations

from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import settings
from utils.logger import get_logger
from utils.retry import retry_call


class SlackClient:
    def __init__(self) -> None:
        self.logger = get_logger("slack_client")
        self.client = WebClient(token=settings.slack_bot_token)

    def validate(self) -> None:
        if not settings.slack_bot_token or not settings.slack_channel_id:
            raise ValueError("Slack environment variables are incomplete")
        retry_call(lambda: self.client.auth_test(), retry_on=(SlackApiError,))
        self.logger.info("Slack client validated")

    def post_launch_message(self, startup_name: str, summary: str, pr_url: str | None, issue_url: str | None) -> dict[str, Any]:
        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"LaunchMind: {startup_name}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": summary},
            },
        ]
        if pr_url or issue_url:
            links = []
            if issue_url:
                links.append(f"<{issue_url}|GitHub Issue>")
            if pr_url:
                links.append(f"<{pr_url}|Pull Request>")
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": " | ".join(links)}]})

        def _send() -> dict[str, Any]:
            response = self.client.chat_postMessage(channel=settings.slack_channel_id, text=summary, blocks=blocks)
            return dict(response.data)

        return retry_call(_send, retry_on=(SlackApiError,))
