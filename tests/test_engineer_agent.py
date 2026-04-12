from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agents.engineer_agent import EngineerAgent


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


class _DummyGitHub:
    pass


class EngineerAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.agent = EngineerAgent(
            "engineer",
            llm_client=None,
            bus=_DummyBus(),
            store=_DummyStore(),
            artifacts_dir=Path(self.tempdir.name),
            github_client=_DummyGitHub(),
        )
        self.product_spec = {
            "startup_name": "PlatePilot",
            "value_proposition": "Predict end-of-day spoilage and generate discounts for nearby diners.",
            "personas": [
                {
                    "name": "Restaurant Owner",
                    "pain_points": ["Food waste", "Low last-minute traffic"],
                    "desired_outcomes": ["Recover revenue", "Reduce spoilage"],
                }
            ],
            "landing_page_requirements": [
                "Visual demo of the dashboard showing the prediction and offer generation.",
                "Testimonials or case studies from early users/partners.",
                "Call-to-action buttons for demo signups and newsletter subscriptions.",
                "Frequently asked questions section addressing common concerns.",
                "A section outlining the pricing model and potential ROI for restaurant owners.",
            ],
        }

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_prompt_ready_product_spec_is_compact_and_actionable(self) -> None:
        compact = self.agent._prompt_ready_product_spec(self.product_spec)
        self.assertEqual(compact["startup_name"], "PlatePilot")
        self.assertLessEqual(len(compact["personas"]), 2)
        self.assertLessEqual(len(compact["landing_page_requirements"]), 8)

    def test_missing_requirements_detects_absent_sections(self) -> None:
        html = "<html><body><h1>Hello</h1></body></html>"
        missing = self.agent._missing_requirements(html, self.product_spec)
        self.assertTrue(any("dashboard" in item.lower() for item in missing))
        self.assertTrue(any("newsletter" in item.lower() or "waitlist" in item.lower() for item in missing))
        self.assertTrue(any("faq" in item.lower() for item in missing))

    def test_missing_requirements_accepts_present_sections(self) -> None:
        html = """
        <style>@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;700&display=swap'); body { font-family: 'Manrope', sans-serif; } .hero { background-image: url('data:image/svg+xml;base64,abc'); }</style>
        <section>dashboard demo</section>
        <section>testimonials</section>
        <section>newsletter waitlist email capture</section>
        <section>frequently asked questions</section>
        <section>pricing roi return on investment</section>
        <img src="data:image/svg+xml;base64,abc" alt="hero">
        <a>Book a demo</a>
        """
        missing = self.agent._missing_requirements(html, self.product_spec)
        self.assertEqual(missing, [])

    def test_needs_professional_rebuild_for_placeholder_html(self) -> None:
        html = """
        <html>
            <head><style>body { font-family: Arial, sans-serif; }</style></head>
            <body>
                <section><img src="https://example.com/hero.jpg"></section>
                <section>demo</section>
            </body>
        </html>
        """
        issues = self.agent._missing_requirements(html, self.product_spec)
        self.assertTrue(self.agent._needs_professional_rebuild(html, issues))

    def test_minor_quality_issue_is_tolerated(self) -> None:
        self.assertTrue(self.agent._is_minor_quality_issue("Add a strong visible call-to-action section."))
        self.assertFalse(self.agent._is_minor_quality_issue("Replace placeholder image URLs with self-contained visuals or real renderable image sources."))

    def test_build_github_metadata_is_deterministic_and_complete(self) -> None:
        metadata = self.agent._build_github_metadata(
            "AI concierge for student founders",
            {
                **self.product_spec,
                "features": [
                    {"name": "Idea Validation", "description": "Turns vague startup ideas into structured launch plans."},
                    {"name": "Landing Page Builder", "description": "Creates a polished page from the approved product spec."},
                ],
            },
            {"headline": "Launch startup ideas in one day"},
        )
        self.assertEqual(metadata["issue_title"], "Initial landing page")
        self.assertIn("PlatePilot", metadata["pr_title"])
        self.assertIn("Launch startup ideas in one day", metadata["issue_body"])
        self.assertTrue(metadata["commit_message"].startswith("Add "))

    def test_fallback_template_html_uses_spec_content(self) -> None:
        html = self.agent._build_safe_template_html(
            {
                **self.product_spec,
                "startup_name": "LaunchMate AI",
                "value_proposition": "Turn startup ideas into launch-ready pages faster.",
                "features": [
                    {"name": "Landing Page Builder", "description": "Creates a polished first page."},
                    {"name": "Launch Copy", "description": "Generates sharp messaging for the startup."},
                ],
            },
            {"headline": "Launch startup ideas in one day", "cta_text": "Request early access"},
        )
        self.assertIn("LaunchMate AI", html)
        self.assertIn("Launch startup ideas in one day", html)
        self.assertIn("Landing Page Builder", html)
        self.assertIn("Request early access", html)
        self.assertNotIn("example.com", html)


if __name__ == "__main__":
    unittest.main()
