from __future__ import annotations

from llm.prompts import marketing_prompt, marketing_repair_prompt

from agents.base_agent import BaseAgent
from integrations.email_client import EmailClient
from integrations.slack_client import SlackClient
from messaging.message_schema import AgentMessage


class MarketingAgent(BaseAgent):
    def __init__(self, *args, slack_client: SlackClient, email_client: EmailClient, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.slack_client = slack_client
        self.email_client = email_client

    def handle_message(self, message: AgentMessage) -> None:
        if message.message_type not in {"task", "revision_request"}:
            return

        startup_idea = message.payload["startup_idea"]
        product_spec = message.payload["product_spec"]
        task_payload = message.payload["task"]
        startup_name = product_spec.get("startup_name", "LaunchMind Startup")

        draft = self.llm_client.run_json_task(
            role="Growth Marketer",
            goal="Craft launch messaging that feels sharp, specific, and ready to send.",
            backstory="You have strong product-marketing judgment and write concise copy that stays tightly aligned to the actual startup.",
            prompt=marketing_prompt(startup_idea, product_spec, task_payload),
        )
        repaired, repaired_with_llm = self._repair_marketing_output(startup_idea, product_spec, draft)
        result, generation_mode = self._finalize_marketing_output(product_spec, repaired, repaired_with_llm=repaired_with_llm)

        email_result = self.email_client.send_email(
            subject=result["cold_outreach_email"]["subject"],
            body=result["cold_outreach_email"]["body"],
        )
        slack_result = self.slack_client.post_launch_message(
            startup_name=startup_name,
            summary=result["slack_summary"],
            pr_url=None,
            issue_url=None,
        )

        marketing_payload = {
            **result,
            "generation_mode": generation_mode,
            "email_delivery": email_result,
            "slack_delivery": {"channel": slack_result.get("channel"), "ts": slack_result.get("ts")},
        }
        self.write_json_artifact("marketing_result.json", marketing_payload)
        self.send_message("ceo", "result", {"marketing_result": marketing_payload}, parent_message_id=message.message_id)

    def _repair_marketing_output(self, startup_idea: str, product_spec: dict, draft: dict) -> tuple[dict, bool]:
        if self.llm_client is None:
            return draft, False
        repaired = self.llm_client.run_json_task_fast(
            prompt=marketing_repair_prompt(startup_idea, product_spec, draft),
            attempts=1,
        )
        return repaired, repaired != draft

    def _finalize_marketing_output(self, product_spec: dict, result: dict, *, repaired_with_llm: bool) -> tuple[dict, str]:
        startup_name = str(product_spec.get("startup_name", "LaunchMind Startup")).strip() or "LaunchMind Startup"
        value_prop = str(product_spec.get("value_proposition", "")).strip()
        target_persona = self._target_persona(product_spec)
        used_fallback = False
        used_cleanup = False

        tagline = str(result.get("tagline", "")).strip()
        if not tagline or len(tagline.split()) > 10:
            result["tagline"] = self._fallback_tagline(startup_name)
            used_fallback = True

        short_description = str(result.get("short_description", "")).strip()
        if not short_description or len(short_description) < 60:
            result["short_description"] = self._fallback_short_description(startup_name, value_prop, target_persona)
            used_fallback = True
        else:
            cleaned_description = self._strip_placeholder_tokens(short_description)
            if cleaned_description != short_description:
                result["short_description"] = cleaned_description
                used_cleanup = True

        email = result.get("cold_outreach_email", {}) or {}
        subject = str(email.get("subject", "")).strip()
        body = str(email.get("body", "")).strip()
        if not subject or not body:
            result["cold_outreach_email"] = self._fallback_email(startup_name, value_prop, target_persona)
            used_fallback = True
        else:
            cleaned_subject = self._strip_placeholder_tokens(subject)
            cleaned_body = self._normalize_email_body(body)
            if cleaned_subject != subject or cleaned_body != body:
                used_cleanup = True
            result["cold_outreach_email"] = {"subject": cleaned_subject, "body": cleaned_body}

        social_posts = result.get("social_posts", {}) or {}
        normalized_social_posts = self._normalize_social_posts(social_posts)
        if normalized_social_posts != social_posts:
            used_cleanup = True
        result["social_posts"] = normalized_social_posts

        slack_summary = str(result.get("slack_summary", "")).strip()
        if not slack_summary:
            result["slack_summary"] = self._fallback_slack_summary(startup_name, value_prop)
            used_fallback = True
        else:
            cleaned_summary = self._strip_placeholder_tokens(slack_summary)
            if cleaned_summary != slack_summary:
                result["slack_summary"] = cleaned_summary
                used_cleanup = True

        if used_fallback:
            generation_mode = "fallback"
        elif repaired_with_llm and used_cleanup:
            generation_mode = "llm_repair_plus_normalization"
        elif repaired_with_llm:
            generation_mode = "llm_repair"
        elif used_cleanup:
            generation_mode = "llm_plus_normalization"
        else:
            generation_mode = "llm"
        return result, generation_mode

    def _target_persona(self, product_spec: dict) -> str:
        personas = product_spec.get("personas", [])
        if personas:
            return str(personas[0].get("name", "target users")).strip() or "target users"
        return "target users"

    def _fallback_tagline(self, startup_name: str) -> str:
        if len(startup_name.split()) <= 3:
            return f"{startup_name}, with clearer next steps."
        return "Clear next steps, faster."

    def _fallback_short_description(self, startup_name: str, value_prop: str, target_persona: str) -> str:
        if value_prop:
            return f"{startup_name} helps {target_persona.lower()} {value_prop[0].lower() + value_prop[1:]}"
        return f"{startup_name} gives {target_persona.lower()} a faster, clearer path from first problem to a useful next step."

    def _fallback_email(self, startup_name: str, value_prop: str, target_persona: str) -> dict:
        body = (
            f"Hi,\n\n{startup_name} is built for {target_persona.lower()} who want a faster path from first question to a clear next step.\n\n"
            f"{value_prop or 'It turns a messy starting point into a more useful, trustworthy workflow.'}\n\n"
            "If you'd like to see the workflow live or join the pilot, reply to this email and we can share the next steps.\n\n"
            "Best,\nLaunchMind Team"
        )
        return {
            "subject": f"A quicker way to try {startup_name}",
            "body": body,
        }

    def _fallback_slack_summary(self, startup_name: str, value_prop: str) -> str:
        if value_prop:
            return f"{startup_name}: {value_prop}"
        return f"{startup_name} is ready with launch messaging, social copy, and outreach email."

    def _normalize_email_body(self, body: str) -> str:
        normalized = self._strip_placeholder_tokens(body)
        if "reply to this email" not in normalized.lower() and "book a quick walkthrough" not in normalized.lower():
            normalized = normalized.rstrip() + "\n\nReply to this email if you want a quick walkthrough."
        return normalized

    def _normalize_social_posts(self, posts: dict) -> dict:
        normalized = {"x": [], "linkedin": [], "instagram": []}
        for channel in normalized:
            items = list(posts.get(channel, []))[:3]
            cleaned_items: list[str] = []
            for item in items:
                cleaned = self._strip_placeholder_tokens(str(item)).strip()
                if cleaned:
                    cleaned_items.append(cleaned)
            normalized[channel] = cleaned_items
        return normalized

    def _strip_placeholder_tokens(self, text: str) -> str:
        cleaned = str(text)
        replacements = {
            "{{first_name}}": "there",
            "{{restaurant_name}}": "your business",
            "{{calendly_link}}": "reply to this email",
            "{{city}}": "your city",
            "{city}": "your city",
            "{link}": "reply for details",
            "{beta_link}": "reply for beta access",
            "[Metro]": "your area",
            "[Your Metro]": "your area",
            "[Founder Name]": "there",
            "[Restaurant Name]": "your business",
        }
        for old, new in replacements.items():
            cleaned = cleaned.replace(old, new)
        return cleaned
