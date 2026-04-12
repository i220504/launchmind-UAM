from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agents.marketing_agent import MarketingAgent


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
    def post_launch_message(self, **_kwargs) -> dict:
        return {"channel": "demo", "ts": "1"}


class _DummyEmail:
    def send_email(self, **_kwargs) -> dict:
        return {"provider": "smtp", "status": "sent"}


class MarketingAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.agent = MarketingAgent(
            "marketing",
            llm_client=None,
            bus=_DummyBus(),
            store=_DummyStore(),
            artifacts_dir=Path(self.tempdir.name),
            slack_client=_DummySlack(),
            email_client=_DummyEmail(),
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_generic_fallback_stays_startup_specific_without_restaurant_leak(self) -> None:
        product_spec = {
            "startup_name": "WrenchPilot",
            "value_proposition": "Get a clear remote assessment and book a vetted mechanic in minutes.",
            "personas": [{"name": "Busy commuter with an urgent issue", "pain_points": ["Car trouble"], "desired_outcomes": ["Fast booking"]}],
        }
        result = {
            "tagline": "",
            "short_description": "",
            "cold_outreach_email": {"subject": "", "body": ""},
            "social_posts": {"x": ["a", "b", "c"], "linkedin": ["a", "b", "c"], "instagram": ["a", "b", "c"]},
            "slack_summary": "",
        }
        polished, generation_mode = self.agent._finalize_marketing_output(product_spec, result, repaired_with_llm=False)
        blob = " ".join(
            [
                polished["short_description"],
                polished["cold_outreach_email"]["subject"],
                polished["cold_outreach_email"]["body"],
                polished["slack_summary"],
            ]
        ).lower()
        self.assertEqual(generation_mode, "fallback")
        for banned in ["restaurant", "food waste", "pickup offers", "pos integration", "surplus", "spoilage", "unsold meals"]:
            self.assertNotIn(banned, blob)
        self.assertIn("mechanic", blob)

    def test_normalization_removes_placeholder_tokens(self) -> None:
        product_spec = {
            "startup_name": "StudySourced",
            "value_proposition": "Turn class materials into cited explanations and practice questions.",
            "personas": [{"name": "Overloaded First-Year Student", "pain_points": ["Too much to study"], "desired_outcomes": ["Clearer review"]}],
        }
        result = {
            "tagline": "Study help with citations from your materials.",
            "short_description": "Upload notes and slides, then get a clear study pack in {city}.",
            "cold_outreach_email": {
                "subject": "{{first_name}}, study help grounded in your own notes",
                "body": "Hi {{first_name}},\n\nStudySourced helps students turn notes into a study pack.\n\nSee the demo here: {{calendly_link}}",
            },
            "social_posts": {"x": ["Try it in {city}"], "linkedin": ["Reply for details at {link}"], "instagram": ["Join via {beta_link}"]},
            "slack_summary": "StudySourced is launching in {city}.",
        }
        polished, generation_mode = self.agent._finalize_marketing_output(product_spec, result, repaired_with_llm=False)
        blob = " ".join(
            [
                polished["short_description"],
                polished["cold_outreach_email"]["subject"],
                polished["cold_outreach_email"]["body"],
                polished["slack_summary"],
                *polished["social_posts"]["x"],
                *polished["social_posts"]["linkedin"],
                *polished["social_posts"]["instagram"],
            ]
        )
        self.assertEqual(generation_mode, "llm_plus_normalization")
        for banned in ["{{first_name}}", "{{calendly_link}}", "{city}", "{link}", "{beta_link}"]:
            self.assertNotIn(banned, blob)

    def test_clean_llm_output_stays_llm_mode(self) -> None:
        product_spec = {
            "startup_name": "StudySourced",
            "value_proposition": "Turn class materials into cited explanations and practice questions.",
            "personas": [{"name": "Overloaded First-Year Student", "pain_points": ["Too much to study"], "desired_outcomes": ["Clearer review"]}],
        }
        result = {
            "tagline": "Study help you can trust.",
            "short_description": "StudySourced turns class notes and slides into cited explanations, practice questions, and clearer study sessions without generic AI guesswork.",
            "cold_outreach_email": {
                "subject": "A simpler way to study from your own notes",
                "body": "Hi,\n\nStudySourced turns class notes and slides into cited explanations and practice questions students can trust.\n\nReply to this email if you want a quick walkthrough.",
            },
            "social_posts": {"x": ["a", "b", "c"], "linkedin": ["a", "b", "c"], "instagram": ["a", "b", "c"]},
            "slack_summary": "StudySourced turns class notes and slides into cited explanations and practice questions students can trust.",
        }
        polished, generation_mode = self.agent._finalize_marketing_output(product_spec, result, repaired_with_llm=False)
        self.assertEqual(generation_mode, "llm")
        self.assertEqual(polished["short_description"], result["short_description"])


if __name__ == "__main__":
    unittest.main()
