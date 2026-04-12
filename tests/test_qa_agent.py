from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agents.qa_agent import QAAgent


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


class QAAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.agent = QAAgent(
            "qa",
            llm_client=None,
            bus=_DummyBus(),
            store=_DummyStore(),
            artifacts_dir=Path(self.tempdir.name),
            github_client=_DummyGitHub(),
        )
        self.product_spec = {
            "landing_page_requirements": [
                "Visual demo of the dashboard showing the prediction and offer generation.",
                "Testimonials or case studies from early users/partners.",
                "Call-to-action buttons for demo signups and newsletter subscriptions.",
                "Frequently asked questions section addressing common concerns.",
            ],
            "marketing_hooks": [
                "Reduce food waste with predictive discounts.",
                "Recover revenue before closing time.",
            ],
            "value_proposition": "Predict spoilage and create pickup offers for nearby diners.",
        }
        self.engineer_result = {
            "html": """
                <section>dashboard</section>
                <section>testimonials</section>
                <section>frequently asked questions</section>
                <section>newsletter</section>
                <a class='cta-button'>Book a demo</a>
            """,
        }
        self.marketing_result = {
            "tagline": "Waste into revenue",
            "short_description": "Predict spoilage, create discounts, and recover revenue before closing.",
        }

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_softener_removes_invented_engineer_requirements(self) -> None:
        report = {
            "overall_status": "fail",
            "engineer_review": {
                "status": "fail",
                "issues": [
                    "The HTML needs a product video demo.",
                    "The testimonials should link back to real case studies.",
                ],
                "inline_comments": ["a", "b"],
            },
            "marketing_review": {"status": "pass", "issues": []},
            "summary": "bad",
        }
        softened = self.agent._soften_report(self.product_spec, self.engineer_result, self.marketing_result, report)
        self.assertEqual(softened["engineer_review"]["status"], "pass")
        self.assertEqual(softened["overall_status"], "pass")

    def test_softener_keeps_real_marketing_issue_when_copy_is_generic(self) -> None:
        report = {
            "overall_status": "fail",
            "engineer_review": {"status": "pass", "issues": [], "inline_comments": ["a", "b"]},
            "marketing_review": {"status": "fail", "issues": ["The marketing copy is too generic and does not differentiate the product."]},
            "summary": "bad",
        }
        generic_marketing = {
            "tagline": "Great startup launch tool",
            "short_description": "A good platform for users.",
        }
        softened = self.agent._soften_report(self.product_spec, self.engineer_result, generic_marketing, report)
        self.assertEqual(softened["marketing_review"]["status"], "fail")
        self.assertEqual(softened["overall_status"], "fail")

    def test_softener_passes_single_minor_engineer_issue(self) -> None:
        report = {
            "overall_status": "fail",
            "engineer_review": {
                "status": "fail",
                "issues": ["Call-to-action wording could be stronger."],
                "inline_comments": ["a", "b"],
            },
            "marketing_review": {"status": "pass", "issues": []},
            "summary": "needs polish",
        }
        softened = self.agent._soften_report(self.product_spec, self.engineer_result, self.marketing_result, report)
        self.assertEqual(softened["engineer_review"]["status"], "pass")
        self.assertEqual(softened["overall_status"], "pass")


if __name__ == "__main__":
    unittest.main()
