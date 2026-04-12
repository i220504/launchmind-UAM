from __future__ import annotations

from llm.prompts import product_prompt

from agents.base_agent import BaseAgent
from messaging.message_schema import AgentMessage


class ProductAgent(BaseAgent):
    def handle_message(self, message: AgentMessage) -> None:
        if message.message_type not in {"task", "revision_request"}:
            return
        startup_idea = message.payload["startup_idea"]
        ceo_task = message.payload["task"]
        spec = self.llm_client.run_json_task(
            role="Product Strategist",
            goal="Produce a concrete product specification aligned to the startup idea.",
            backstory="You are a sharp zero-to-one product thinker who turns vague ideas into crisp launch plans.",
            prompt=product_prompt(startup_idea, ceo_task),
        )
        self.write_json_artifact("product_spec.json", spec)
        self.send_message("ceo", "result", {"product_spec": spec}, parent_message_id=message.message_id)
