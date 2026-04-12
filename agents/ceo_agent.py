from __future__ import annotations

import threading
from typing import Any

from config import settings
from llm.prompts import ceo_decomposition_prompt, ceo_review_prompt

from agents.base_agent import BaseAgent
from integrations.slack_client import SlackClient
from messaging.message_schema import AgentMessage


class CEOAgent(BaseAgent):
    def __init__(self, *args, slack_client: SlackClient, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.slack_client = slack_client
        self.completed = threading.Event()
        self.state.update(
            {
                "startup_idea": "",
                "plan": None,
                "product_spec": None,
                "engineer_result": None,
                "marketing_result": None,
                "qa_report": None,
                "errors": [],
                "review_counts": {"product": 0, "engineer": 0, "marketing": 0, "qa": 0},
                "qa_requested": False,
                "awaiting_revisions": set(),
                "final_summary": None,
            }
        )

    def _record_failure_and_finalize(self, failed_agent: str, error: str) -> None:
        self.state["errors"].append({"failed_agent": failed_agent, "error": error})
        self._finalize(status="failed")

    def start_workflow(self, startup_idea: str) -> None:
        self.state["startup_idea"] = startup_idea
        plan = self.llm_client.run_json_task(
            role="CEO Orchestrator",
            goal="Break the startup idea into executable work and supervise quality.",
            backstory="You think like a startup CEO coordinating product, engineering, marketing, and QA under demo pressure.",
            prompt=ceo_decomposition_prompt(startup_idea),
        )
        self.state["plan"] = plan
        self.write_json_artifact("ceo_plan.json", plan)
        self.send_message(
            "product",
            "task",
            {
                "startup_idea": startup_idea,
                "task": plan["product_task"],
                "north_star": plan["north_star"],
            },
        )

    def handle_message(self, message: AgentMessage) -> None:
        if message.message_type == "error":
            self.state["errors"].append(message.payload)
            self.logger.error("CEO escalation received: %s", message.payload)
            failed_agent = message.payload.get("failed_agent")
            if failed_agent in {"engineer", "product"} and not self.completed.is_set():
                self._finalize(status="failed")
                return
            if len(self.state["errors"]) >= 3 and not self.completed.is_set():
                self._finalize(status="failed")
            return

        if message.from_agent == "product" and "product_spec" in message.payload:
            self._handle_product_result(message)
            return
        if message.from_agent == "engineer" and "engineer_result" in message.payload:
            self._handle_engineer_result(message)
            return
        if message.from_agent == "marketing" and "marketing_result" in message.payload:
            self._handle_marketing_result(message)
            return
        if message.from_agent == "qa" and "qa_report" in message.payload:
            self._handle_qa_result(message)

    def _review_artifact(self, artifact_type: str, artifact: dict[str, Any], qa_context: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return self.llm_client.run_json_task(
                role="CEO Reviewer",
                goal="Review output quality and decide whether revision is required.",
                backstory="You hold the bar for coherence, execution quality, and launch readiness.",
                prompt=ceo_review_prompt(self.state["startup_idea"], artifact_type, artifact, qa_context),
            )
        except Exception as exc:  # noqa: BLE001
            if not self._is_rate_limit_error(exc):
                raise
            self.logger.warning("CEO reviewer hit rate limit for %s, using heuristic fallback review: %s", artifact_type, exc)
            return self._fallback_review(artifact_type, artifact, qa_context)

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        blob = str(exc).lower()
        return "429" in blob or "rate limit" in blob or "ratelimit" in blob

    def _fallback_review(self, artifact_type: str, artifact: dict[str, Any], qa_context: dict[str, Any] | None = None) -> dict[str, Any]:
        if artifact_type == "product_spec":
            decision = "approve" if self._is_actionable_product_spec(artifact) else "revise"
            return {
                "decision": decision,
                "score": 8 if decision == "approve" else 5,
                "strengths": ["Fallback review used because the LLM reviewer was temporarily rate-limited."],
                "issues": [] if decision == "approve" else ["Product spec needs more concrete structure before downstream handoff."],
                "revision_instructions": [] if decision == "approve" else ["Add clearer personas, features, and landing-page requirements."],
            }
        if artifact_type == "marketing_output":
            decision = "approve" if self._is_actionable_marketing_output(artifact) else "revise"
            return {
                "decision": decision,
                "score": 7 if decision == "approve" else 5,
                "strengths": ["Fallback review used because the LLM reviewer was temporarily rate-limited."],
                "issues": [] if decision == "approve" else ["Marketing output is not complete enough to send forward safely."],
                "revision_instructions": [] if decision == "approve" else ["Tighten the email CTA and ensure all social channels are present."],
            }
        if artifact_type == "engineer_output":
            html = str(artifact.get("html", "")).lower()
            decision = "approve" if html and "<html" in html and "<section" in html else "revise"
            return {
                "decision": decision,
                "score": 7 if decision == "approve" else 5,
                "strengths": ["Fallback review used because the LLM reviewer was temporarily rate-limited."],
                "issues": [] if decision == "approve" else ["Landing page HTML is incomplete and needs a stronger section structure."],
                "revision_instructions": [] if decision == "approve" else ["Return complete HTML with clearer section structure and CTA."],
            }
        report = qa_context or {}
        decision = "approve" if report.get("overall_status") == "pass" else "revise"
        return {
            "decision": decision,
            "score": 7 if decision == "approve" else 5,
            "strengths": ["Fallback review used because the LLM reviewer was temporarily rate-limited."],
            "issues": [] if decision == "approve" else ["QA reported unresolved issues that still need attention."],
            "revision_instructions": [] if decision == "approve" else ["Address the remaining QA findings and resubmit."],
        }

    def _handle_product_result(self, message: AgentMessage) -> None:
        product_spec = message.payload["product_spec"]
        review = self._review_artifact("product_spec", product_spec)
        force_feedback_loop = self._should_force_product_feedback_loop()
        if force_feedback_loop:
            review = self._build_forced_product_revision_review(review)
        if not force_feedback_loop and review.get("decision") == "revise" and self._should_accept_product_spec(product_spec, review):
            review = {
                **review,
                "decision": "approve",
                "issues": [
                    "Accepted as actionable for downstream engineering and marketing. Remaining notes are advanced product polish rather than blocking launch-spec gaps."
                ],
                "revision_instructions": [],
            }
        self.write_json_artifact("ceo_product_review.json", review)
        if review["decision"] == "revise" and self.state["review_counts"]["product"] < settings.max_revisions:
            self.state["review_counts"]["product"] += 1
            self.state["awaiting_revisions"].add("product")
            self.send_message(
                "product",
                "revision_request",
                {
                    "startup_idea": self.state["startup_idea"],
                    "task": {
                        **self.state["plan"]["product_task"],
                        "revision_instructions": review["revision_instructions"],
                    },
                },
                parent_message_id=message.message_id,
            )
            return
        if review["decision"] == "revise":
            self._record_failure_and_finalize("product", "Product output still required revision after max revision attempts.")
            return

        self.state["awaiting_revisions"].discard("product")
        self.state["product_spec"] = product_spec
        self.logger.info("CEO approved product spec and is dispatching engineer and marketing in parallel")
        self.send_message(
            "engineer",
            "task",
            {
                "startup_idea": self.state["startup_idea"],
                "product_spec": self.state["product_spec"],
                "task": self.state["plan"]["engineer_task"],
            },
            parent_message_id=message.message_id,
        )
        self.send_message(
            "marketing",
            "task",
            {
                "startup_idea": self.state["startup_idea"],
                "product_spec": self.state["product_spec"],
                "task": self.state["plan"]["marketing_task"],
            },
            parent_message_id=message.message_id,
        )

    def _should_force_product_feedback_loop(self) -> bool:
        return self.state["review_counts"]["product"] < 2

    def _build_forced_product_revision_review(self, review: dict[str, Any]) -> dict[str, Any]:
        existing_instructions = [str(item).strip() for item in review.get("revision_instructions", []) if str(item).strip()]
        forced_instructions = [
            "Sharpen the value proposition so it is more concrete and easier for downstream engineering and marketing to execute.",
            "Tighten personas, feature framing, and user stories so the spec feels more launch-ready and specific.",
            "Refine landing-page requirements and marketing hooks so the startup positioning is clearer and more polished.",
        ]
        merged_instructions = existing_instructions + [item for item in forced_instructions if item not in existing_instructions]
        return {
            **review,
            "decision": "revise",
            "issues": [
                "CEO is enforcing an intentional product refinement loop before downstream handoff."
            ],
            "revision_instructions": merged_instructions,
            "forced_feedback_loop": True,
        }

    def _should_accept_product_spec(self, product_spec: dict[str, Any], review: dict[str, Any]) -> bool:
        if not self._is_actionable_product_spec(product_spec):
            return False
        score = int(review.get("score", 0) or 0)
        if score < 7:
            return False
        issues = [str(item).lower() for item in review.get("issues", [])]
        truly_blocking_markers = [
            "missing required section",
            "required section is missing",
            "badly misaligned with the startup idea",
            "too vague for downstream execution",
            "not actionable",
            "invalid json",
            "missing personas",
            "missing features",
            "missing user stories",
            "missing landing page requirements",
        ]
        if any(marker in issue for issue in issues for marker in truly_blocking_markers):
            return False
        advanced_scope_markers = [
            "underspecified",
            "ambiguous",
            "scope",
            "placeholder strategy",
            "testable",
            "schema",
            "validation",
            "sla",
            "timezone",
            "state machine",
            "option sets",
            "intake",
            "traceability",
            "investor pack",
            "channel bundle",
            "manual intervention",
        ]
        if score >= 8 and all(any(marker in issue for marker in advanced_scope_markers) for issue in issues):
            return True
        return True

    def _is_actionable_product_spec(self, product_spec: dict[str, Any]) -> bool:
        startup_name = str(product_spec.get("startup_name", "")).strip()
        value_proposition = str(product_spec.get("value_proposition", "")).strip()
        personas = product_spec.get("personas", [])
        features = product_spec.get("features", [])
        user_stories = product_spec.get("user_stories", [])
        landing_page_requirements = product_spec.get("landing_page_requirements", [])
        marketing_hooks = product_spec.get("marketing_hooks", [])

        if len(startup_name) < 3 or len(value_proposition) < 30:
            return False
        if len(personas) < 1 or len(features) < 3 or len(user_stories) < 3 or len(landing_page_requirements) < 5 or len(marketing_hooks) < 3:
            return False

        if not all(
            str(persona.get("name", "")).strip()
            and len(persona.get("pain_points", [])) >= 2
            and len(persona.get("desired_outcomes", [])) >= 2
            for persona in personas
        ):
            return False

        if not all(
            str(feature.get("name", "")).strip()
            and str(feature.get("description", "")).strip()
            and str(feature.get("priority", "")).strip() in {"high", "medium", "low"}
            for feature in features
        ):
            return False

        if not all(
            isinstance(story, str)
            and (story.lower().startswith("as a ") or story.lower().startswith("as an "))
            for story in user_stories
        ):
            return False

        return True

    def _handle_engineer_result(self, message: AgentMessage) -> None:
        review = self._review_artifact("engineer_output", message.payload["engineer_result"])
        self.write_json_artifact("ceo_engineer_review.json", review)
        if review["decision"] == "revise" and self.state["review_counts"]["engineer"] < settings.max_revisions:
            self.state["review_counts"]["engineer"] += 1
            self.state["awaiting_revisions"].add("engineer")
            self.send_message(
                "engineer",
                "revision_request",
                {
                    "startup_idea": self.state["startup_idea"],
                    "product_spec": self.state["product_spec"],
                    "task": {
                        **self.state["plan"]["engineer_task"],
                        "revision_instructions": review["revision_instructions"],
                    },
                },
                parent_message_id=message.message_id,
            )
            return
        if review["decision"] == "revise":
            self._record_failure_and_finalize("engineer", "Engineer output still required revision after max revision attempts.")
            return
        self.state["awaiting_revisions"].discard("engineer")
        self.state["engineer_result"] = message.payload["engineer_result"]
        self._maybe_request_qa()

    def _handle_marketing_result(self, message: AgentMessage) -> None:
        marketing_result = message.payload["marketing_result"]
        review = self._review_artifact("marketing_output", marketing_result)
        if review.get("decision") == "revise" and self._should_accept_marketing_output(marketing_result, review):
            review = {
                **review,
                "decision": "approve",
                "issues": [
                    "Accepted as launch-ready marketing output. Remaining notes are consistency improvements rather than blocking messaging flaws."
                ],
                "revision_instructions": [],
            }
        self.write_json_artifact("ceo_marketing_review.json", review)
        if review["decision"] == "revise" and self.state["review_counts"]["marketing"] < settings.max_revisions:
            self.state["review_counts"]["marketing"] += 1
            self.state["awaiting_revisions"].add("marketing")
            self.send_message(
                "marketing",
                "revision_request",
                {
                    "startup_idea": self.state["startup_idea"],
                    "product_spec": self.state["product_spec"],
                    "task": {
                        **self.state["plan"]["marketing_task"],
                        "revision_instructions": review["revision_instructions"],
                    },
                },
                parent_message_id=message.message_id,
            )
            return
        if review["decision"] == "revise":
            self._record_failure_and_finalize("marketing", "Marketing output still required revision after max revision attempts.")
            return
        self.state["awaiting_revisions"].discard("marketing")
        self.state["marketing_result"] = marketing_result
        self._maybe_request_qa()

    def _should_accept_marketing_output(self, marketing_result: dict[str, Any], review: dict[str, Any]) -> bool:
        if not self._is_actionable_marketing_output(marketing_result):
            return False
        score = int(review.get("score", 0) or 0)
        if score < 7:
            return False
        blocking_markers = [
            "completely mismatched",
            "completely misaligned",
            "critical alignment failure",
            "wrong domain",
            "unrelated to",
            "restaurant",
            "food waste",
            "pos integration",
            "wrong persona",
            "missing cta",
            "no cta",
            "not launch-ready",
        ]
        issue_blob = " ".join(review.get("issues", [])).lower()
        return not any(marker in issue_blob for marker in blocking_markers)

    def _is_actionable_marketing_output(self, marketing_result: dict[str, Any]) -> bool:
        tagline = str(marketing_result.get("tagline", "")).strip()
        short_description = str(marketing_result.get("short_description", "")).strip()
        email = marketing_result.get("cold_outreach_email", {})
        subject = str(email.get("subject", "")).strip()
        body = str(email.get("body", "")).strip()
        social_posts = marketing_result.get("social_posts", {})

        if not tagline or len(tagline.split()) > 10:
            return False
        if len(short_description) < 80:
            return False
        if not subject or not body:
            return False
        body_lower = body.lower()
        if not any(
            phrase in body_lower
            for phrase in ["demo", "walkthrough", "reply to this email", "reply here", "join the beta", "try it", "get started"]
        ):
            return False
        if "{" in subject and "{{first_name}}" not in subject:
            return False
        for channel in ("x", "linkedin", "instagram"):
            posts = social_posts.get(channel, [])
            if len(posts) < 3 or not all(str(post).strip() for post in posts):
                return False
        return True

    def _maybe_request_qa(self) -> None:
        if self.state["qa_requested"]:
            return
        if self.state["awaiting_revisions"]:
            return
        if not self.state["product_spec"] or not self.state["engineer_result"] or not self.state["marketing_result"]:
            return
        self.state["qa_requested"] = True
        self.send_message(
            "qa",
            "task",
            {
                "startup_idea": self.state["startup_idea"],
                "product_spec": self.state["product_spec"],
                "engineer_result": self.state["engineer_result"],
                "marketing_result": self.state["marketing_result"],
                "task": self.state["plan"]["qa_task"],
            },
        )

    def _handle_qa_result(self, message: AgentMessage) -> None:
        report = message.payload["qa_report"]
        self.state["qa_report"] = report
        if report["overall_status"] == "fail" and self.state["review_counts"]["qa"] < settings.max_revisions:
            self.state["review_counts"]["qa"] += 1
            self.state["qa_requested"] = False
            if report["engineer_review"]["status"] == "fail":
                self.state["awaiting_revisions"].add("engineer")
                self.send_message(
                    "engineer",
                    "revision_request",
                    {
                        "startup_idea": self.state["startup_idea"],
                        "product_spec": self.state["product_spec"],
                        "task": {
                            **self.state["plan"]["engineer_task"],
                            "revision_instructions": report["engineer_review"]["issues"],
                        },
                    },
                    parent_message_id=message.message_id,
                )
            if report["marketing_review"]["status"] == "fail":
                self.state["awaiting_revisions"].add("marketing")
                self.send_message(
                    "marketing",
                    "revision_request",
                    {
                        "startup_idea": self.state["startup_idea"],
                        "product_spec": self.state["product_spec"],
                        "task": {
                            **self.state["plan"]["marketing_task"],
                            "revision_instructions": report["marketing_review"]["issues"],
                        },
                    },
                    parent_message_id=message.message_id,
                )
            return
        if report["overall_status"] == "fail":
            self._record_failure_and_finalize("qa", "QA still reported fail after max revision attempts.")
            return

        self._finalize(status="success")

    def _finalize(self, *, status: str) -> None:
        if self.completed.is_set():
            return
        summary = {
            "status": status,
            "startup_name": (self.state["product_spec"] or {}).get("startup_name", "Unknown Startup"),
            "north_star": (self.state["plan"] or {}).get("north_star", ""),
            "product_spec_ready": self.state["product_spec"] is not None,
            "engineer_pr_url": (self.state["engineer_result"] or {}).get("pr_url"),
            "engineer_issue_url": (self.state["engineer_result"] or {}).get("issue_url"),
            "marketing_tagline": (self.state["marketing_result"] or {}).get("tagline"),
            "qa_status": (self.state["qa_report"] or {}).get("overall_status"),
            "errors": self.state["errors"],
        }
        summary_text = (
            f"*Status:* {status}\n"
            f"*Startup:* {summary['startup_name']}\n"
            f"*North star:* {summary['north_star']}\n"
            f"*QA:* {summary['qa_status']}\n"
            f"*PR:* {summary['engineer_pr_url'] or 'not created'}\n"
            f"*Issue:* {summary['engineer_issue_url'] or 'not created'}"
        )
        try:
            self.slack_client.post_launch_message(
                startup_name=summary["startup_name"],
                summary=summary_text,
                pr_url=summary["engineer_pr_url"],
                issue_url=summary["engineer_issue_url"],
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Final Slack summary failed: %s", exc)
            summary["errors"].append({"failed_agent": "ceo", "error": f"Final Slack summary failed: {exc}"})
        self.state["final_summary"] = summary
        self.write_json_artifact("final_summary.json", summary)
        self.completed.set()
