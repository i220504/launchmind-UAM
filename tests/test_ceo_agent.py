from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agents.ceo_agent import CEOAgent
from messaging.message_schema import AgentMessage


class _DummyBus:
    def subscribe(self, *_args, **_kwargs) -> None:
        return None

    def publish(self, *_args, **_kwargs) -> None:
        return None


class _DummyStore:
    def append(self, *_args, **_kwargs) -> None:
        return None

    def append_event(self, *_args, **_kwargs) -> None:
        return None


class _DummySlack:
    def post_launch_message(self, **_kwargs) -> None:
        return None


class CEOAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.agent = CEOAgent(
            "ceo",
            llm_client=None,
            bus=_DummyBus(),
            store=_DummyStore(),
            artifacts_dir=Path(self.tempdir.name),
            slack_client=_DummySlack(),
        )
        self.spec = {
            "startup_name": "PlatePilot",
            "value_proposition": "Reduce restaurant food waste by predicting same-day surplus and converting it into pickup revenue with minimal staff effort.",
            "personas": [
                {
                    "name": "Restaurant Owner",
                    "pain_points": ["Food waste", "Low margin nights"],
                    "desired_outcomes": ["Recover revenue", "Reduce spoilage"],
                }
            ],
            "features": [
                {"name": "Waste Prediction", "description": "Forecast likely leftovers before close.", "priority": "high"},
                {"name": "Offer Builder", "description": "Create discounted pickup offers fast.", "priority": "high"},
                {"name": "Operator Dashboard", "description": "Track waste risk and recovered revenue.", "priority": "medium"},
            ],
            "user_stories": [
                "As a restaurant owner, I want to predict nightly waste, so that I can recover revenue.",
                "As a manager, I want a fast approval flow, so that closing stays simple.",
                "As a customer, I want clear pickup offers, so that I can buy with confidence.",
            ],
            "landing_page_requirements": [
                "Hero section with value proposition.",
                "Problem and solution section.",
                "Demo section.",
                "Pricing and ROI section.",
                "Lead capture section.",
            ],
            "marketing_hooks": [
                "Reduce waste without adding work.",
                "Turn leftovers into revenue.",
                "Give operators a simple close-time playbook.",
            ],
        }

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_actionable_product_spec_returns_true(self) -> None:
        self.assertTrue(self.agent._is_actionable_product_spec(self.spec))

    def test_actionable_product_spec_accepts_as_an_user_stories(self) -> None:
        spec = {
            **self.spec,
            "startup_name": "WrenchNow",
            "value_proposition": "Get real-time help from a vetted mechanic online with a written diagnosis summary, estimate, and booking flow.",
            "user_stories": [
                "As a driver, I want a quick remote diagnosis, so that I know what to do next.",
                "As an admin, I want to pause intake when capacity is exceeded, so that SLA promises stay realistic.",
                "As a mechanic, I want structured intake details, so that I can respond faster.",
            ],
        }
        self.assertTrue(self.agent._is_actionable_product_spec(spec))

    def test_accepts_high_scoring_actionable_spec_with_non_blocking_review(self) -> None:
        review = {
            "decision": "revise",
            "score": 8,
            "issues": [
                "Prediction algorithm detail could be more explicit for future implementation phases.",
                "Support tooling could be described more fully.",
            ],
            "revision_instructions": ["Add more detail."],
        }
        self.assertTrue(self.agent._should_accept_product_spec(self.spec, review))

    def test_accepts_high_scoring_spec_with_advanced_scope_issues(self) -> None:
        review = {
            "decision": "revise",
            "score": 8,
            "issues": [
                "Channel bundle spec is internally inconsistent because it says 3 channels but lists 4.",
                "Claim traceability requirement is likely underspecified as written.",
                "SLA local-time handling is ambiguous.",
            ],
            "revision_instructions": ["Tighten the spec."],
        }
        self.assertTrue(self.agent._should_accept_product_spec(self.spec, review))

    def test_rejects_truly_incomplete_spec(self) -> None:
        incomplete = {
            "startup_name": "PP",
            "value_proposition": "Too short.",
            "personas": [],
            "features": [],
            "user_stories": [],
            "landing_page_requirements": [],
            "marketing_hooks": [],
        }
        self.assertFalse(self.agent._is_actionable_product_spec(incomplete))

    def test_actionable_marketing_output_returns_true(self) -> None:
        marketing_result = {
            "tagline": "Sell the surplus. Skip the scramble.",
            "short_description": "PlatePilot helps small restaurants reduce nightly food waste by predicting surplus and turning it into same-day pickup revenue without requiring POS integration.",
            "cold_outreach_email": {
                "subject": "{{first_name}}, reduce nightly waste without POS integration",
                "body": "Hi {{first_name}},\n\nAt {{restaurant_name}}, PlatePilot helps operators forecast surplus, publish pickup offers with conservative caps, and recover margin before close.\n\nBook a quick walkthrough here: {{calendly_link}}",
            },
            "social_posts": {
                "x": ["Post one", "Post two", "Post three"],
                "linkedin": ["Post one", "Post two", "Post three"],
                "instagram": ["Post one", "Post two", "Post three"],
            },
        }
        self.assertTrue(self.agent._is_actionable_marketing_output(marketing_result))

    def test_accepts_high_scoring_actionable_marketing_with_non_blocking_review(self) -> None:
        marketing_result = {
            "tagline": "Sell the surplus. Skip the scramble.",
            "short_description": "PlatePilot helps small restaurants reduce nightly food waste by predicting surplus and turning it into same-day pickup revenue without requiring POS integration.",
            "cold_outreach_email": {
                "subject": "{{first_name}}, reduce nightly waste without POS integration",
                "body": "Hi {{first_name}},\n\nAt {{restaurant_name}}, PlatePilot helps operators forecast surplus, publish pickup offers with conservative caps, and recover margin before close.\n\nBook a quick walkthrough here: {{calendly_link}}",
            },
            "social_posts": {
                "x": ["Post one", "Post two", "Post three"],
                "linkedin": ["Post one", "Post two", "Post three"],
                "instagram": ["Post one", "Post two", "Post three"],
            },
        }
        review = {
            "decision": "revise",
            "score": 7,
            "issues": [
                "CTA formatting could be more consistent across channels.",
                "One placeholder should be standardized.",
            ],
            "revision_instructions": ["Tighten consistency."],
        }
        self.assertTrue(self.agent._should_accept_marketing_output(marketing_result, review))

    def test_accepts_score_seven_marketing_when_issues_are_non_blocking(self) -> None:
        marketing_result = {
            "tagline": "60-second audience quality snapshot",
            "short_description": "InstaAudit helps teams review public Instagram accounts with a fast scorecard, clear confidence level, and a simple summary they can share internally.",
            "cold_outreach_email": {
                "subject": "A faster way to vet public Instagram accounts",
                "body": "Hi there,\n\nInstaAudit gives teams a fast scorecard, confidence signal, and plain-language summary for public Instagram accounts.\n\nReply to this email if you want a quick walkthrough.",
            },
            "social_posts": {
                "x": ["Post one", "Post two", "Post three"],
                "linkedin": ["Post one", "Post two", "Post three"],
                "instagram": ["Post one", "Post two", "Post three"],
            },
        }
        review = {
            "decision": "revise",
            "score": 7,
            "issues": [
                "Terminology and claims risk could be softened with a clearer disclaimer.",
                "The social posts could use a more explicit CTA and a tighter ICP callout.",
                "Brand naming collision risk is worth reviewing before launch.",
            ],
            "revision_instructions": ["Tighten positioning and disclaimers."],
        }
        self.assertTrue(self.agent._should_accept_marketing_output(marketing_result, review))

    def test_product_phase_forces_two_revision_loops_before_approval(self) -> None:
        self.agent.state["startup_idea"] = "AI concierge for student founders"
        self.agent.state["plan"] = {
            "product_task": {"goal": "Create product spec"},
            "engineer_task": {"goal": "Build landing page"},
            "marketing_task": {"goal": "Create launch copy"},
        }
        sent_messages: list[tuple[str, str, dict, str | None]] = []

        def _capture_send(to_agent: str, message_type: str, payload: dict, parent_message_id: str | None = None) -> None:
            sent_messages.append((to_agent, message_type, payload, parent_message_id))

        self.agent.send_message = _capture_send  # type: ignore[method-assign]
        self.agent._review_artifact = lambda *_args, **_kwargs: {  # type: ignore[method-assign]
            "decision": "approve",
            "score": 9,
            "issues": [],
            "revision_instructions": [],
        }

        first_message = AgentMessage(
            message_id="msg-1",
            from_agent="product",
            to_agent="ceo",
            message_type="result",
            payload={"product_spec": self.spec},
            timestamp="2026-04-12T12:00:00Z",
            parent_message_id=None,
        )
        second_message = AgentMessage(
            message_id="msg-2",
            from_agent="product",
            to_agent="ceo",
            message_type="result",
            payload={"product_spec": self.spec},
            timestamp="2026-04-12T12:01:00Z",
            parent_message_id=None,
        )
        third_message = AgentMessage(
            message_id="msg-3",
            from_agent="product",
            to_agent="ceo",
            message_type="result",
            payload={"product_spec": self.spec},
            timestamp="2026-04-12T12:02:00Z",
            parent_message_id=None,
        )

        self.agent._handle_product_result(first_message)
        self.assertEqual(self.agent.state["review_counts"]["product"], 1)
        self.assertEqual(sent_messages[-1][0], "product")
        self.assertEqual(sent_messages[-1][1], "revision_request")

        self.agent._handle_product_result(second_message)
        self.assertEqual(self.agent.state["review_counts"]["product"], 2)
        self.assertEqual(sent_messages[-1][0], "product")
        self.assertEqual(sent_messages[-1][1], "revision_request")

        self.agent._handle_product_result(third_message)
        self.assertEqual(self.agent.state["review_counts"]["product"], 2)
        self.assertEqual(sent_messages[-2][0], "engineer")
        self.assertEqual(sent_messages[-2][1], "task")
        self.assertEqual(sent_messages[-1][0], "marketing")
        self.assertEqual(sent_messages[-1][1], "task")
        self.assertEqual(self.agent.state["product_spec"], self.spec)

    def test_forced_product_loop_overrides_reviseable_approval_logic(self) -> None:
        self.agent.state["startup_idea"] = "Mechanic online diagnosis"
        self.agent.state["plan"] = {
            "product_task": {"goal": "Create product spec"},
            "engineer_task": {"goal": "Build landing page"},
            "marketing_task": {"goal": "Create launch copy"},
        }
        sent_messages: list[tuple[str, str, dict, str | None]] = []

        def _capture_send(to_agent: str, message_type: str, payload: dict, parent_message_id: str | None = None) -> None:
            sent_messages.append((to_agent, message_type, payload, parent_message_id))

        self.agent.send_message = _capture_send  # type: ignore[method-assign]
        self.agent._review_artifact = lambda *_args, **_kwargs: {  # type: ignore[method-assign]
            "decision": "revise",
            "score": 9,
            "issues": ["Minor polish note."],
            "revision_instructions": ["Tighten wording."],
        }

        message = AgentMessage(
            message_id="msg-force-1",
            from_agent="product",
            to_agent="ceo",
            message_type="result",
            payload={"product_spec": self.spec},
            timestamp="2026-04-12T12:03:00Z",
            parent_message_id=None,
        )

        self.agent._handle_product_result(message)
        self.assertEqual(self.agent.state["review_counts"]["product"], 1)
        self.assertEqual(sent_messages[-1][0], "product")
        self.assertEqual(sent_messages[-1][1], "revision_request")
        revision_instructions = sent_messages[-1][2]["task"]["revision_instructions"]
        self.assertIn("Tighten wording.", revision_instructions)
        self.assertTrue(
            any("Sharpen the value proposition" in instruction for instruction in revision_instructions)
        )


if __name__ == "__main__":
    unittest.main()
