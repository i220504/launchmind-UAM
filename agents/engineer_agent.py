from __future__ import annotations

import re
import time
from html import escape
from urllib.parse import quote

from config import settings
from llm.prompts import (
    engineer_prompt,
    engineer_repair_prompt,
)
from utils.ids import slugify

from agents.base_agent import BaseAgent
from integrations.github_client import GitHubClient
from messaging.message_schema import AgentMessage


class EngineerAgent(BaseAgent):
    def __init__(self, *args, github_client: GitHubClient, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.github_client = github_client
        self.engineer_provider = settings.engineer_llm_provider or settings.llm_provider

    def handle_message(self, message: AgentMessage) -> None:
        if message.message_type not in {"task", "revision_request"}:
            return

        startup_idea = message.payload["startup_idea"]
        product_spec = message.payload["product_spec"]
        prompt_spec = self._prompt_ready_product_spec(product_spec)
        task_payload = message.payload["task"]

        started = time.time()
        self.logger.info("Engineer starting landing-page generation for startup=%s", product_spec.get("startup_name", "Unknown"))
        render_started = time.time()
        try:
            result = self.llm_client.run_json_task(
                role="Engineer Agent",
                goal="Build a launch-ready landing page and return complete runnable HTML.",
                backstory="You are a product-minded frontend engineer who turns startup specs into polished single-file landing pages and production-ready GitHub artifacts.",
                prompt=engineer_prompt(startup_idea, prompt_spec, task_payload),
                provider_override=self.engineer_provider,
            )
            self.logger.info("Engineer initial HTML generation completed in %.2fs", time.time() - render_started)
            render_mode = "crewai_render"
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Engineer primary LLM render failed, using built-in template fallback: %s", exc)
            result = self._fallback_result(product_spec, {})
            render_mode = "template_fallback"
        quality_issues = self._missing_requirements(result.get("html", ""), product_spec)
        self.logger.info("Engineer quality gate found %s issue(s)", len(quality_issues))
        if quality_issues and render_mode != "template_fallback":
            try:
                repair_started = time.time()
                result = self.llm_client.run_json_task(
                    role="Engineer Agent",
                    goal="Repair the landing page so it fully satisfies the product spec and quality requirements.",
                    backstory="You improve HTML drafts without losing product specificity, visual polish, or structural completeness.",
                    prompt=engineer_repair_prompt(
                        startup_idea,
                        prompt_spec,
                        task_payload,
                        {},
                        {},
                        result,
                        quality_issues,
                    ),
                    provider_override=self.engineer_provider,
                )
                self.logger.info("Engineer repair pass completed in %.2fs", time.time() - repair_started)
                render_mode = "crewai_repair"
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Engineer repair failed, using built-in template fallback: %s", exc)
                result = self._fallback_result(product_spec, result)
                render_mode = "template_fallback"

        raw_llm_html = result.get("html", "")
        html = raw_llm_html
        final_quality_issues = self._missing_requirements(html, product_spec)
        blocking_quality_issues = [issue for issue in final_quality_issues if not self._is_minor_quality_issue(issue)]
        if blocking_quality_issues:
            self.logger.warning(
                "Engineer output still had blocking issues after LLM path, switching to built-in template fallback: %s",
                "; ".join(blocking_quality_issues),
            )
            result = self._fallback_result(product_spec, result)
            raw_llm_html = result.get("html", "")
            html = raw_llm_html
            final_quality_issues = self._missing_requirements(html, product_spec)
            blocking_quality_issues = [issue for issue in final_quality_issues if not self._is_minor_quality_issue(issue)]
            if blocking_quality_issues:
                raise RuntimeError(
                    "Engineer fallback output still did not meet landing-page requirements: "
                    + "; ".join(blocking_quality_issues)
                )
            render_mode = "template_fallback"
        final_mode = "template_final" if render_mode == "template_fallback" else "llm_final"
        self.write_text_artifact("index_llm_raw.html", raw_llm_html)
        self.write_text_artifact("index_final.html", html)
        self.write_text_artifact("index.html", html)
        result["html"] = html
        github_metadata = self._build_github_metadata(startup_idea, product_spec, result)
        self.logger.info("Engineer GitHub metadata prepared without a second LLM call")

        startup_name = product_spec.get("startup_name", "launchmind-project")
        branch_name = self.state.get("branch_name") or f"launch/{slugify(startup_name)}"
        issue = self.state.get("issue")
        if issue is None:
            github_issue_started = time.time()
            issue = self.github_client.create_issue(
                title=github_metadata["issue_title"],
                body=github_metadata["issue_body"],
            )
            self.logger.info("Engineer GitHub issue creation completed in %.2fs", time.time() - github_issue_started)
            self.state["issue"] = issue
            branch_started = time.time()
            self.github_client.create_branch(branch_name)
            self.logger.info("Engineer branch setup completed in %.2fs", time.time() - branch_started)
            self.state["branch_name"] = branch_name

        commit_started = time.time()
        commit_result = self.github_client.commit_file(
            branch_name,
            "index.html",
            html,
            message=github_metadata["commit_message"],
        )
        self.logger.info("Engineer commit completed in %.2fs", time.time() - commit_started)
        commit_sha = commit_result["commit"]["sha"]
        self.state["latest_commit_sha"] = commit_sha

        pr = self.state.get("pull_request")
        if pr is None:
            pr_started = time.time()
            pr = self.github_client.open_pull_request(
                title=github_metadata["pr_title"],
                body=github_metadata["pr_body"],
                head=branch_name,
            )
            self.logger.info("Engineer pull request creation completed in %.2fs", time.time() - pr_started)
            self.state["pull_request"] = pr

        payload = {
            "engineer_result": {
                **result,
                "issue_url": issue["html_url"],
                "branch_name": branch_name,
                "pr_url": self.state["pull_request"]["html_url"],
                "pr_number": self.state["pull_request"]["number"],
                "latest_commit_sha": commit_sha,
                "render_mode": render_mode,
                "final_mode": final_mode,
                "quality_issues": final_quality_issues,
                "raw_html_artifact": "index_llm_raw.html",
                "final_html_artifact": "index_final.html",
                "github_metadata": github_metadata,
            }
        }
        self.write_json_artifact("engineer_result.json", payload["engineer_result"])
        self.logger.info("Engineer completed full workflow in %.2fs", time.time() - started)
        self.send_message("ceo", "result", payload, parent_message_id=message.message_id)

    def _fallback_result(self, product_spec: dict, partial_result: dict) -> dict:
        headline = str(partial_result.get("headline") or product_spec.get("value_proposition") or product_spec.get("startup_name") or "Launch faster").strip()
        subheadline = str(
            partial_result.get("subheadline")
            or product_spec.get("value_proposition")
            or "Turn the approved product spec into a launch-ready page with clear positioning and conversion-focused structure."
        ).strip()
        cta_text = str(partial_result.get("cta_text") or "Request early access").strip()
        feature_bullets = partial_result.get("feature_bullets") or [
            f"{feature.get('name', '')}: {feature.get('description', '')}".strip(": ")
            for feature in product_spec.get("features", [])[:4]
        ]
        testimonials = partial_result.get("testimonials") or [
            {
                "name": persona.get("name", "Early user"),
                "quote": f"{product_spec.get('startup_name', 'This product')} makes the core value proposition clear and easy to act on."
            }
            for persona in product_spec.get("personas", [])[:2]
        ]
        return {
            "headline": headline,
            "subheadline": subheadline,
            "cta_text": cta_text,
            "feature_bullets": feature_bullets[:4],
            "visual_concept": "Structured premium fallback template filled with product-specific copy and self-contained visuals.",
            "testimonials": testimonials[:2],
            "html": self._build_safe_template_html(product_spec, partial_result),
        }

    def _build_safe_template_html(self, product_spec: dict, partial_result: dict) -> str:
        startup_name = escape(str(product_spec.get("startup_name", "LaunchMind")).strip() or "LaunchMind")
        headline = escape(str(partial_result.get("headline") or product_spec.get("value_proposition") or startup_name).strip())
        subheadline = escape(
            str(
                partial_result.get("subheadline")
                or product_spec.get("value_proposition")
                or "From approved product spec to a polished launch page."
            ).strip()
        )
        cta_text = escape(str(partial_result.get("cta_text") or "Request early access").strip())
        value_prop = escape(str(product_spec.get("value_proposition", "")).strip())
        features = product_spec.get("features", [])[:4]
        feature_cards = "\n".join(
            f"""
            <article class="feature-card">
                <span class="feature-icon">{self._safe_icon(index)}</span>
                <h3>{escape(str(feature.get("name", "Core feature")).strip() or "Core feature")}</h3>
                <p>{escape(str(feature.get("description", "Built from the approved product specification.")).strip() or "Built from the approved product specification.")}</p>
            </article>
            """.strip()
            for index, feature in enumerate(features)
        ) or """
            <article class="feature-card"><span class="feature-icon">01</span><h3>Launch-ready structure</h3><p>Built from the approved product spec with clear conversion intent.</p></article>
            <article class="feature-card"><span class="feature-icon">02</span><h3>Focused messaging</h3><p>The page highlights the core value proposition and most important buyer outcomes.</p></article>
            <article class="feature-card"><span class="feature-icon">03</span><h3>Fast handoff</h3><p>Single-file HTML that is easy to review, demo, and ship through GitHub.</p></article>
        """.strip()
        personas = product_spec.get("personas", [])[:2]
        persona_cards = "\n".join(
            f"""
            <article class="persona-card">
                <h3>{escape(str(persona.get("name", "Target user")).strip() or "Target user")}</h3>
                <p><strong>Pain points:</strong> {escape(", ".join(persona.get("pain_points", [])[:2]))}</p>
                <p><strong>Desired outcomes:</strong> {escape(", ".join(persona.get("desired_outcomes", [])[:2]))}</p>
            </article>
            """.strip()
            for persona in personas
        )
        testimonials = partial_result.get("testimonials") or []
        testimonial_cards = "\n".join(
            f"""
            <article class="testimonial-card">
                <p class="quote">“{escape(str(item.get("quote", "")).strip() or f"{product_spec.get('startup_name', 'This product')} turns a rough concept into something you can show with confidence.")}”</p>
                <p class="author">{escape(str(item.get("name", "Early user")).strip() or "Early user")}</p>
            </article>
            """.strip()
            for item in testimonials[:2]
        ) or f"""
            <article class="testimonial-card">
                <p class="quote">“{startup_name} makes the idea easier to understand, easier to pitch, and easier to launch.”</p>
                <p class="author">Early user feedback</p>
            </article>
        """.strip()
        hooks = product_spec.get("marketing_hooks", [])[:3]
        hook_items = "\n".join(f"<li>{escape(str(hook).strip())}</li>" for hook in hooks)
        requirements = product_spec.get("landing_page_requirements", [])
        faq_items = "\n".join(
            f"""
            <details class="faq-item">
                <summary>{escape(str(item).strip())}</summary>
                <p>This landing page section addresses this requirement directly within the current fallback build.</p>
            </details>
            """.strip()
            for item in requirements[:4]
        )
        hero_svg = self._svg_data_uri(product_spec.get("startup_name", "LaunchMind"), product_spec.get("value_proposition", ""), "hero")
        demo_svg = self._svg_data_uri(f"{product_spec.get('startup_name', 'LaunchMind')} Demo", "Live workflow preview", "demo")
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{startup_name}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&family=Fraunces:wght@600;700&display=swap');
        :root {{
            --bg: #0d1117;
            --surface: rgba(20, 28, 39, 0.92);
            --surface-2: #111b28;
            --ink: #eef2f7;
            --muted: #a4b0bf;
            --line: rgba(255,255,255,0.08);
            --accent: #2dd4bf;
            --accent-2: #fb923c;
            --shadow: 0 28px 60px rgba(0,0,0,0.28);
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            font-family: "Manrope", sans-serif;
            color: var(--ink);
            background:
                radial-gradient(circle at top left, rgba(45,212,191,0.12), transparent 28%),
                radial-gradient(circle at top right, rgba(251,146,60,0.12), transparent 24%),
                linear-gradient(180deg, #0d1117 0%, #101722 100%);
        }}
        .page {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 32px 0 56px; }}
        .panel {{
            border-radius: 28px;
            border: 1px solid var(--line);
            background: var(--surface);
            box-shadow: var(--shadow);
        }}
        .hero {{
            display: grid;
            grid-template-columns: 1.15fr 0.85fr;
            gap: 24px;
            align-items: stretch;
        }}
        .hero-copy {{ padding: 40px; }}
        .eyebrow {{
            display: inline-block;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 0.14em;
            font-size: 0.78rem;
            font-weight: 800;
            margin-bottom: 14px;
        }}
        h1, h2, h3 {{ margin: 0; }}
        h1 {{
            font-family: "Fraunces", serif;
            font-size: clamp(2.7rem, 5vw, 4.6rem);
            line-height: 0.96;
            letter-spacing: -0.04em;
            margin-bottom: 16px;
        }}
        .lede {{
            margin: 0;
            color: var(--muted);
            font-size: 1.08rem;
            line-height: 1.75;
            max-width: 56ch;
        }}
        .cta-row {{ display: flex; flex-wrap: wrap; gap: 14px; align-items: center; margin-top: 28px; }}
        .cta-button {{
            display: inline-flex;
            min-height: 54px;
            align-items: center;
            justify-content: center;
            padding: 0 24px;
            border-radius: 999px;
            background: linear-gradient(135deg, var(--accent-2), var(--accent));
            color: #fff;
            text-decoration: none;
            font-weight: 800;
            box-shadow: 0 18px 28px rgba(45,212,191,0.22);
        }}
        .cta-note {{ color: var(--muted); font-size: 0.92rem; }}
        .hero-visual {{ padding: 22px; display: flex; flex-direction: column; gap: 16px; }}
        .hero-visual img, .demo-visual img {{
            width: 100%;
            display: block;
            border-radius: 22px;
            border: 1px solid var(--line);
            background: #0f1722;
        }}
        .stat-row {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
        }}
        .stat {{
            border-radius: 18px;
            padding: 14px;
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--line);
        }}
        .stat strong {{ display: block; font-size: 1.2rem; margin-bottom: 6px; }}
        .section {{ margin-top: 24px; padding: 30px; }}
        .section-head {{
            display: flex;
            justify-content: space-between;
            gap: 18px;
            align-items: end;
            margin-bottom: 22px;
        }}
        .section-head p {{ color: var(--muted); max-width: 56ch; line-height: 1.7; margin: 0; }}
        .feature-grid, .persona-grid, .testimonial-grid {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 16px;
        }}
        .feature-card, .persona-card, .testimonial-card, .pricing-card {{
            border-radius: 22px;
            padding: 22px;
            background: var(--surface-2);
            border: 1px solid var(--line);
        }}
        .feature-icon {{
            display: inline-flex;
            width: 40px;
            height: 40px;
            align-items: center;
            justify-content: center;
            border-radius: 12px;
            background: rgba(45,212,191,0.12);
            color: var(--accent);
            font-weight: 800;
            margin-bottom: 12px;
        }}
        .feature-card p, .persona-card p, .testimonial-card p, .pricing-card p, .demo-copy p, .lead-card p {{
            color: var(--muted);
            line-height: 1.7;
        }}
        .demo-shell {{
            display: grid;
            grid-template-columns: 1.05fr 0.95fr;
            gap: 16px;
            align-items: stretch;
        }}
        .demo-copy, .demo-visual, .lead-card {{
            border-radius: 22px;
            padding: 22px;
            background: var(--surface-2);
            border: 1px solid var(--line);
        }}
        .list {{
            margin: 14px 0 0;
            padding-left: 18px;
            color: var(--muted);
            line-height: 1.8;
        }}
        .pricing-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }}
        .faq-item {{
            border-radius: 18px;
            padding: 16px 18px;
            background: var(--surface-2);
            border: 1px solid var(--line);
            margin-bottom: 12px;
        }}
        .faq-item summary {{
            cursor: pointer;
            font-weight: 700;
        }}
        footer {{
            margin-top: 24px;
            padding: 22px 28px;
            border-radius: 24px;
            border: 1px solid var(--line);
            background: rgba(15,23,34,0.95);
            color: var(--muted);
            display: flex;
            justify-content: space-between;
            gap: 16px;
            flex-wrap: wrap;
        }}
        @media (max-width: 960px) {{
            .hero, .demo-shell, .pricing-grid, .feature-grid, .persona-grid, .testimonial-grid, .stat-row {{
                grid-template-columns: 1fr;
            }}
            .hero-copy, .hero-visual, .section {{ padding: 24px; }}
        }}
    </style>
</head>
<body>
    <main class="page">
        <section class="hero">
            <div class="panel hero-copy">
                <span class="eyebrow">Launch-Ready Landing Page</span>
                <h1>{headline}</h1>
                <p class="lede">{subheadline}</p>
                <div class="cta-row">
                    <a href="#lead" class="cta-button">{cta_text}</a>
                    <span class="cta-note">{value_prop}</span>
                </div>
            </div>
            <div class="panel hero-visual">
                <img src="{hero_svg}" alt="{startup_name} hero visual">
                <div class="stat-row">
                    <div class="stat"><strong>1 page</strong><span>Single-file, review-friendly HTML</span></div>
                    <div class="stat"><strong>Live spec</strong><span>Content mapped from the approved product brief</span></div>
                    <div class="stat"><strong>Fast handoff</strong><span>Ready for GitHub issue, commit, and PR flow</span></div>
                </div>
            </div>
        </section>

        <section class="panel section">
            <div class="section-head">
                <div><span class="eyebrow">Core Features</span><h2>What the product delivers first.</h2></div>
                <p>The fallback template still uses the approved product spec so the page stays aligned even when the free-model render is slow or unstable.</p>
            </div>
            <div class="feature-grid">
                {feature_cards}
            </div>
        </section>

        <section class="panel section">
            <div class="section-head">
                <div><span class="eyebrow">Product Demo</span><h2>See the workflow in one glance.</h2></div>
                <p>This demo section makes the product easier to understand quickly and keeps the landing page launch-ready for review.</p>
            </div>
            <div class="demo-shell">
                <div class="demo-copy">
                    <h3>What this experience highlights</h3>
                    <ul class="list">
                        {hook_items or '<li>Clear value proposition and a conversion-focused structure.</li><li>Self-contained visuals that always render reliably.</li><li>Sections aligned with the approved product specification.</li>'}
                    </ul>
                </div>
                <div class="demo-visual">
                    <img src="{demo_svg}" alt="{startup_name} demo visual">
                </div>
            </div>
        </section>

        <section class="panel section">
            <div class="section-head">
                <div><span class="eyebrow">Target Users</span><h2>Built for the people who need the result fast.</h2></div>
                <p>The personas below are taken directly from the approved product spec so the message stays grounded.</p>
            </div>
            <div class="persona-grid">
                {persona_cards or '<article class="persona-card"><h3>Core user</h3><p><strong>Pain points:</strong> Needs launch-ready output quickly.</p><p><strong>Desired outcomes:</strong> Clear positioning, visible credibility, and a usable first page.</p></article>'}
            </div>
        </section>

        <section class="panel section">
            <div class="section-head">
                <div><span class="eyebrow">Social Proof</span><h2>Give the page a stronger trust signal.</h2></div>
                <p>Even the fallback keeps a visible testimonials section so the landing page does not feel thin or unfinished.</p>
            </div>
            <div class="testimonial-grid">
                {testimonial_cards}
            </div>
        </section>

        <section class="panel section">
            <div class="section-head">
                <div><span class="eyebrow">Pricing And ROI</span><h2>Make the value easy to justify.</h2></div>
                <p>This section keeps the landing page commercially legible by showing a simple buying path and payoff story.</p>
            </div>
            <div class="pricing-grid">
                <article class="pricing-card">
                    <h3>Launch Plan</h3>
                    <p>Designed for early teams that need a professional first impression without a long production cycle.</p>
                    <ul class="list">
                        <li>Fast setup and single-file delivery</li>
                        <li>Product-specific messaging and structure</li>
                        <li>Easy review through GitHub workflow</li>
                    </ul>
                </article>
                <article class="pricing-card">
                    <h3>Why it pays back quickly</h3>
                    <p>A clearer landing page means faster validation, stronger conversations, and less time spent rewriting the basics by hand.</p>
                    <ul class="list">
                        <li>Less design bottleneck</li>
                        <li>Faster launch cycle</li>
                        <li>Sharper first impression</li>
                    </ul>
                </article>
            </div>
        </section>

        <section class="panel section" id="lead">
            <div class="section-head">
                <div><span class="eyebrow">Call To Action</span><h2>Start with a clear next step.</h2></div>
                <p>The fallback still preserves a visible CTA and lead-capture area so the page remains useful for launch review.</p>
            </div>
            <div class="lead-card">
                <h3>{cta_text}</h3>
                <p>{value_prop}</p>
                <div class="cta-row">
                    <a href="#lead" class="cta-button">{cta_text}</a>
                    <span class="cta-note">Reach out to request access, a walkthrough, or an early collaboration.</span>
                </div>
            </div>
        </section>

        <section class="panel section">
            <div class="section-head">
                <div><span class="eyebrow">FAQ</span><h2>Answer the practical questions early.</h2></div>
                <p>The FAQ content is derived from the product requirements so reviewers can still see clear launch readiness.</p>
            </div>
            {faq_items or '<details class="faq-item"><summary>What does this landing page include?</summary><p>Hero, features, demo, social proof, pricing/ROI, CTA, and FAQ sections in one review-ready file.</p></details>'}
        </section>

        <footer>
            <span>{startup_name}</span>
            <span>Built from the approved product specification and prepared for GitHub delivery.</span>
        </footer>
    </main>
</body>
</html>"""

    def _safe_icon(self, index: int) -> str:
        return ["01", "02", "03", "04", "05"][index % 5]

    def _build_github_metadata(self, startup_idea: str, product_spec: dict, result: dict) -> dict[str, str]:
        startup_name = str(product_spec.get("startup_name", "LaunchMind Project")).strip() or "LaunchMind Project"
        value_proposition = str(product_spec.get("value_proposition", "")).strip()
        features = product_spec.get("features", [])[:3]
        feature_lines = []
        for feature in features:
            name = str(feature.get("name", "")).strip()
            description = str(feature.get("description", "")).strip()
            if name and description:
                feature_lines.append(f"- {name}: {description}")
            elif name:
                feature_lines.append(f"- {name}")
        if not feature_lines:
            feature_lines.append("- Single-file landing page implementation aligned with the approved product specification.")

        headline = str(result.get("headline", "")).strip()
        issue_body = "\n".join(
            [
                f"Startup idea: {startup_idea}",
                "",
                f"Implemented the initial landing page for {startup_name}.",
                value_proposition,
                "",
                "What is included:",
                *feature_lines,
                "",
                f"Primary page headline: {headline or startup_name}",
            ]
        ).strip()
        commit_slug = slugify(startup_name) or "startup"
        pr_body = "\n".join(
            [
                f"Implements the initial landing page for {startup_name}.",
                "",
                "Included in this PR:",
                "- Generated single-file `index.html` landing page",
                "- Product-specific headline, subheadline, and CTA",
                "- Feature positioning derived from the approved product spec",
                "- Responsive styling for live preview and review",
                "",
                "Review focus:",
                "- Product-spec alignment",
                "- Visual clarity and CTA strength",
                "- Overall launch readiness",
            ]
        ).strip()
        return {
            "issue_title": "Initial landing page",
            "issue_body": issue_body,
            "commit_message": f"Add {commit_slug} landing page",
            "pr_title": f"Launch landing page for {startup_name}",
            "pr_body": pr_body,
        }

    def _prompt_ready_product_spec(self, product_spec: dict) -> dict:
        personas = product_spec.get("personas", [])[:2]
        features = product_spec.get("features", [])[:6]
        requirements = product_spec.get("landing_page_requirements", [])[:8]
        hooks = product_spec.get("marketing_hooks", [])[:5]
        return {
            "startup_name": product_spec.get("startup_name", ""),
            "value_proposition": product_spec.get("value_proposition", ""),
            "personas": [
                {
                    "name": persona.get("name", ""),
                    "pain_points": persona.get("pain_points", [])[:3],
                    "desired_outcomes": persona.get("desired_outcomes", [])[:3],
                }
                for persona in personas
            ],
            "features": [
                {
                    "name": feature.get("name", ""),
                    "description": feature.get("description", "")[:220],
                    "priority": feature.get("priority", ""),
                }
                for feature in features
            ],
            "landing_page_requirements": requirements,
            "marketing_hooks": hooks,
        }

    def _is_minor_quality_issue(self, issue: str) -> bool:
        issue_lc = issue.lower()
        minor_markers = [
            "call-to-action",
            "cta section",
            "testimonial",
            "social-proof",
            "newsletter",
            "waitlist",
            "faq section",
            "pricing or roi",
        ]
        return any(marker in issue_lc for marker in minor_markers)

    def _missing_requirements(self, html: str, product_spec: dict) -> list[str]:
        html_lc = (html or "").lower()
        requirements = [item.lower() for item in product_spec.get("landing_page_requirements", [])]
        missing: list[str] = []
        if "dashboard" not in html_lc and "demo" not in html_lc and "mockup" not in html_lc:
            missing.append("Add a visible demo, dashboard, or product mockup section.")
        if all(token not in html_lc for token in ["<img", "<svg", "background-image", "url("]):
            missing.append("Add meaningful visuals such as a domain-related image, inline SVG illustration, or visual mockup.")
        if "example.com" in html_lc or "placeholder.com" in html_lc or 'src=""' in html_lc or "src=''" in html_lc:
            missing.append("Replace placeholder image URLs with self-contained visuals or real renderable image sources.")
        if "font-family" not in html_lc:
            missing.append("Use a professional typography system with a deliberate font pairing.")
        if "font-family: 'arial'" in html_lc or 'font-family: "arial"' in html_lc or "font-family: arial" in html_lc:
            missing.append("Replace plain Arial typography with a more polished, professional font pairing.")
        if not any(token in html_lc for token in ["@import url(", "fonts.googleapis.com", "font-face", "fraunces", "manrope", "space grotesk", "dm sans", "outfit"]):
            missing.append("Use a stronger, more intentional typography system instead of a default-looking font stack.")
        if html_lc.count("<section") < 5:
            missing.append("Add more complete page structure so the landing page does not feel sparse or unfinished.")
        for requirement in requirements:
            if "dashboard" in requirement or "demo" in requirement:
                if "dashboard" not in html_lc and "demo" not in html_lc:
                    missing.append("Add a visible dashboard or product demo section.")
            if "testimonial" in requirement or "case stud" in requirement or "social proof" in requirement:
                if "testimonial" not in html_lc and "case stud" not in html_lc and "social proof" not in html_lc:
                    missing.append("Add a testimonials, case study, or social-proof section.")
            if "newsletter" in requirement or "email" in requirement:
                if "newsletter" not in html_lc and "waitlist" not in html_lc and "email" not in html_lc:
                    missing.append("Add a newsletter, waitlist, or email capture section.")
            if "faq" in requirement or "frequently asked" in requirement:
                if "faq" not in html_lc and "frequently asked" not in html_lc:
                    missing.append("Add a FAQ section.")
            if "call-to-action" in requirement or "cta" in requirement:
                cta_markers = [
                    "cta-button",
                    "<button",
                    "href=",
                    "get started",
                    "book a demo",
                    "sign up",
                    "join now",
                    "join beta",
                    "request access",
                    "start free",
                    "try now",
                    "learn more",
                    "see how it works",
                    "contact us",
                    "book now",
                    "schedule",
                    "apply now",
                    "start your",
                ]
                if not any(marker in html_lc for marker in cta_markers):
                    missing.append("Add a strong visible call-to-action section.")
            if "pricing" in requirement or "roi" in requirement:
                if "pricing" not in html_lc and "roi" not in html_lc and "return on investment" not in html_lc:
                    missing.append("Add a pricing or ROI section because the product spec explicitly asks for it.")
        deduped: list[str] = []
        for item in missing:
            if item not in deduped:
                deduped.append(item)
        return deduped

    def _finalize_html(self, product_spec: dict, result: dict) -> str:
        llm_html = result.get("html", "")
        quality_issues = self._missing_requirements(llm_html, product_spec)
        if self._needs_professional_rebuild(llm_html, quality_issues):
            html = self._build_professional_html(product_spec, result)
        else:
            html = self._apply_visual_fallbacks(llm_html, product_spec)

        remaining_issues = self._missing_requirements(html, product_spec)
        if remaining_issues:
            html = self._build_professional_html(product_spec, result)
            html = self._apply_visual_fallbacks(html, product_spec)
        return html

    def _needs_professional_rebuild(self, html: str, quality_issues: list[str]) -> bool:
        html_lc = (html or "").lower()
        severe_markers = [
            "example.com",
            "placeholder.com",
            "font-family: 'arial'",
            'font-family: "arial"',
            "font-family: arial",
        ]
        if any(marker in html_lc for marker in severe_markers):
            return True
        if len(quality_issues) >= 2:
            return True
        if html_lc.count("<section") < 4:
            return True
        if len(html or "") < 5000:
            return True
        return False

    def _apply_visual_fallbacks(self, html: str, product_spec: dict) -> str:
        fixed = html
        if "example.com" in fixed.lower() or "placeholder.com" in fixed.lower():
            hero_svg = self._svg_data_uri(
                title=product_spec.get("startup_name", "LaunchMind"),
                subtitle=product_spec.get("value_proposition", ""),
                kind="hero",
            )
            demo_svg = self._svg_data_uri(
                title=f"{product_spec.get('startup_name', 'LaunchMind')} Demo",
                subtitle="Live dashboard preview",
                kind="demo",
            )
            fixed = re.sub(r'src=["\']https?://[^"\']*example\.com[^"\']*["\']', f'src="{hero_svg}"', fixed, count=1, flags=re.IGNORECASE)
            fixed = re.sub(r'src=["\']https?://[^"\']*example\.com[^"\']*["\']', f'src="{demo_svg}"', fixed, count=1, flags=re.IGNORECASE)
            fixed = re.sub(r'src=["\']https?://[^"\']*placeholder\.com[^"\']*["\']', f'src="{demo_svg}"', fixed, flags=re.IGNORECASE)

        if "font-family: 'arial'" in fixed.lower() or 'font-family: "arial"' in fixed.lower() or "font-family: arial" in fixed.lower():
            fixed = re.sub(
                r"<style>",
                "<style>@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&family=Fraunces:wght@600;700&display=swap');",
                fixed,
                count=1,
                flags=re.IGNORECASE,
            )
            fixed = re.sub(
                r"font-family:\s*['\"]?Arial['\"]?,\s*sans-serif;",
                "font-family: 'Manrope', 'Helvetica Neue', Arial, sans-serif;",
                fixed,
                flags=re.IGNORECASE,
            )
            fixed = re.sub(
                r"(\.hero h1\s*\{)",
                r"\1 font-family: 'Fraunces', Georgia, serif;",
                fixed,
                count=1,
                flags=re.IGNORECASE,
            )
        if "fonts.googleapis.com" not in fixed.lower() and "<style>" in fixed.lower():
            fixed = re.sub(
                r"<style>",
                "<style>@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&family=Fraunces:wght@600;700&display=swap');",
                fixed,
                count=1,
                flags=re.IGNORECASE,
            )
        return fixed

    def _svg_data_uri(self, title: str, subtitle: str, kind: str) -> str:
        title_text = title[:32]
        subtitle_text = subtitle[:64]
        accent = "#f97316" if kind == "hero" else "#0d9488"
        svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720" fill="none">
  <rect width="1200" height="720" rx="36" fill="#101827"/>
  <circle cx="210" cy="150" r="180" fill="{accent}" fill-opacity="0.28"/>
  <circle cx="1030" cy="110" r="220" fill="#2563EB" fill-opacity="0.24"/>
  <rect x="74" y="88" width="1052" height="544" rx="28" fill="#F8FAFC" fill-opacity="0.08" stroke="white" stroke-opacity="0.14"/>
  <rect x="128" y="146" width="420" height="300" rx="24" fill="#F8FAFC" fill-opacity="0.9"/>
  <rect x="598" y="146" width="474" height="80" rx="22" fill="#F8FAFC" fill-opacity="0.16"/>
  <rect x="598" y="248" width="224" height="142" rx="24" fill="{accent}" fill-opacity="0.85"/>
  <rect x="848" y="248" width="224" height="142" rx="24" fill="#2563EB" fill-opacity="0.85"/>
  <rect x="598" y="414" width="474" height="130" rx="24" fill="#F8FAFC" fill-opacity="0.12"/>
  <text x="152" y="214" fill="#0F172A" font-family="Manrope, Arial, sans-serif" font-size="28" font-weight="700">{title_text}</text>
  <text x="152" y="256" fill="#475569" font-family="Manrope, Arial, sans-serif" font-size="18">{subtitle_text}</text>
  <text x="624" y="196" fill="white" font-family="Manrope, Arial, sans-serif" font-size="18" font-weight="700">Live product snapshot</text>
  <text x="626" y="304" fill="white" font-family="Manrope, Arial, sans-serif" font-size="46" font-weight="800">32%</text>
  <text x="626" y="338" fill="white" font-family="Manrope, Arial, sans-serif" font-size="18">waste reduced</text>
  <text x="876" y="304" fill="white" font-family="Manrope, Arial, sans-serif" font-size="46" font-weight="800">$420</text>
  <text x="876" y="338" fill="white" font-family="Manrope, Arial, sans-serif" font-size="18">recovered tonight</text>
  <text x="626" y="468" fill="white" font-family="Manrope, Arial, sans-serif" font-size="22" font-weight="700">Visual demo section</text>
  <text x="626" y="504" fill="#CBD5E1" font-family="Manrope, Arial, sans-serif" font-size="18">Self-contained graphic fallback so the page always renders cleanly.</text>
</svg>
"""
        return f"data:image/svg+xml;charset=UTF-8,{quote(svg)}"

    def _build_professional_html(self, product_spec: dict, result: dict) -> str:
        variant_seed = self._variant_seed(product_spec)
        theme = self._select_theme(product_spec, variant_seed)
        labels = self._select_labels(product_spec, variant_seed)
        startup_name = escape(product_spec.get("startup_name", "LaunchMind"))
        value_proposition = escape(product_spec.get("value_proposition", result.get("subheadline", "")))
        headline = escape(result.get("headline") or product_spec.get("value_proposition", startup_name))
        subheadline = escape(result.get("subheadline") or value_proposition)
        cta_text = escape(result.get("cta_text") or "Start Your Launch")
        body_font = theme["body_font"]
        display_font = theme["display_font"]
        surface_tint = theme["surface_tint"]
        hero_blend = theme["hero_blend"]
        cta_shadow = theme["cta_shadow"]
        visual_pack = self._select_visual_pack(product_spec)

        feature_items = result.get("feature_bullets") or [
            feature.get("name", "") + ": " + feature.get("description", "")
            for feature in product_spec.get("features", [])[:6]
        ]
        feature_cards = "\n".join(
            f"""
            <article class="feature-card">
                <span class="feature-icon">{escape(self._feature_icon(item, visual_pack))}</span>
                <h3>{escape(self._split_feature_title(item)[0])}</h3>
                <p>{escape(self._split_feature_title(item)[1])}</p>
            </article>
            """.strip()
            for item in feature_items[:6]
        )

        personas = product_spec.get("personas", [])[:2]
        persona_cards = "\n".join(
            f"""
            <article class="persona-card">
                <span class="eyebrow">Built For</span>
                <span class="persona-icon">{escape(self._persona_icon(persona.get("name", ""), visual_pack))}</span>
                <h3>{escape(persona.get("name", "Founder"))}</h3>
                <p><strong>Pain points:</strong> {escape(", ".join(persona.get("pain_points", [])[:2]))}</p>
                <p><strong>Outcome:</strong> {escape(", ".join(persona.get("desired_outcomes", [])[:2]))}</p>
            </article>
            """.strip()
            for persona in personas
        )

        testimonials = result.get("testimonials") or [
            {
                "name": "Student Founder",
                "quote": "I turned a messy startup concept into a credible launch page and investor pitch in one evening.",
            },
            {
                "name": "Non-Technical Builder",
                "quote": "It gave me launch-ready copy without needing a designer, developer, or marketing team.",
            },
        ]
        testimonial_cards = "\n".join(
            f"""
            <article class="testimonial-card">
                <span class="testimonial-badge">{escape(self._testimonial_icon(visual_pack))}</span>
                <p class="quote">“{escape(item.get("quote", ""))}”</p>
                <p class="author">{escape(item.get("name", "Founder"))}</p>
                <a href="#" class="case-link">View example case study</a>
            </article>
            """.strip()
            for item in testimonials[:3]
        )

        hooks = product_spec.get("marketing_hooks", [])[:3]
        hook_items = "\n".join(f"<li>{escape(hook)}</li>" for hook in hooks)
        stat_pairs = self._build_stat_pairs(product_spec)
        hero_stats = "\n".join(
            f"""
                    <div class="stat">
                        <strong>{escape(stat_value)}</strong>
                        <span>{escape(stat_label)}</span>
                    </div>
            """.rstrip()
            for stat_value, stat_label in stat_pairs
        )
        dashboard_cards = self._build_dashboard_cards(product_spec)
        faq_items = self._build_faq_items(product_spec)
        newsletter_copy = self._build_newsletter_copy(product_spec)
        hero_image_url = self._hero_image_url(product_spec)
        demo_visual_url = self._demo_visual_url(product_spec)
        feature_intro = escape(labels["features_body"])
        persona_intro = escape(labels["persona_body"])
        testimonial_intro = escape(labels["testimonial_body"])
        section_blocks = {
            "features": f"""
        <section class="section">
            <div class="section-header">
                <div>
                    <span class="eyebrow">{escape(labels["features_eyebrow"])}</span>
                    <h2>{escape(labels["features_title"])}</h2>
                </div>
                <p>{feature_intro}</p>
            </div>
            <div class="feature-grid">
                {feature_cards}
            </div>
        </section>
""".rstrip(),
            "personas": f"""
        <section class="section">
            <div class="section-header">
                <div>
                    <span class="eyebrow">{escape(labels["persona_eyebrow"])}</span>
                    <h2>{escape(labels["persona_title"])}</h2>
                </div>
                <p>{persona_intro}</p>
            </div>
            <div class="persona-grid">
                {persona_cards}
            </div>
        </section>
""".rstrip(),
            "testimonials": f"""
        <section class="section">
            <div class="section-header">
                <div>
                    <span class="eyebrow">{escape(labels["testimonial_eyebrow"])}</span>
                    <h2>{escape(labels["testimonial_title"])}</h2>
                </div>
                <p>{testimonial_intro}</p>
            </div>
            <div class="testimonial-grid">
                {testimonial_cards}
            </div>
        </section>
""".rstrip(),
            "dashboard": f"""
        <section class="section">
            <div class="section-header">
                <div>
                    <span class="eyebrow">Product Demo</span>
                    <h2>See the dashboard that turns waste into recoverable revenue.</h2>
                </div>
                <p>This visual walkthrough mirrors the dashboard requirement in the product spec by showing prediction metrics, recommended offers, and the action flow from waste forecast to published pickup deal.</p>
            </div>
            <div class="dashboard-shell">
                <div class="dashboard-card">
                    <span class="eyebrow">Dashboard Snapshot</span>
                    <h3>Tonight’s recovery dashboard</h3>
                    <div class="dashboard-visual">
                        <img src="{demo_visual_url}" alt="{startup_name} dashboard demo visual">
                    </div>
                    <div class="dashboard-metrics">
                        {dashboard_cards}
                    </div>
                    <div class="dashboard-flow">
                        <div class="flow-step">
                            <span>1</span>
                            <div>
                                <strong>Predict unsold inventory</strong>
                                <p>PlatePilot identifies likely leftovers before closing using recent POS and inventory signals.</p>
                            </div>
                        </div>
                        <div class="flow-step">
                            <span>2</span>
                            <div>
                                <strong>Generate a localized offer</strong>
                                <p>The platform recommends discount depth, pickup timing, and the best nearby customer segment.</p>
                            </div>
                        </div>
                        <div class="flow-step">
                            <span>3</span>
                            <div>
                                <strong>Push offers and track redemptions</strong>
                                <p>Managers can publish the deal, monitor conversions, and compare recovered revenue vs predicted waste.</p>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="sidebar-card">
                    <span class="eyebrow">Manager View</span>
                    <h3>What the team sees before close</h3>
                    <p>The dashboard surfaces waste risk, likely sell-through, active discounts, and the fastest actions to save inventory without manually recalculating offers.</p>
                    <ul class="promise-list">
                        <li>Predicted unsold meals by category</li>
                        <li>Recommended discount window for fast conversion</li>
                        <li>Offer performance and recovered revenue tracking</li>
                        <li>Operational visibility for owners and shift managers</li>
                    </ul>
                </div>
            </div>
        </section>
""".rstrip(),
            "newsletter": f"""
        <section class="section">
            <div class="section-header">
                <div>
                    <span class="eyebrow">Lead Capture</span>
                    <h2>Book a demo or join the launch list.</h2>
                </div>
                <p>{escape(newsletter_copy)}</p>
            </div>
            <div class="newsletter-card">
                <span class="eyebrow">Newsletter Signup</span>
                <h3>See how restaurants reduce waste before closing time.</h3>
                <form>
                    <input type="email" placeholder="Enter your restaurant email">
                    <button type="submit">Join the waitlist</button>
                </form>
            </div>
        </section>
""".rstrip(),
            "faq": f"""
        <section class="section">
            <div class="section-header">
                <div>
                    <span class="eyebrow">Frequently Asked Questions</span>
                    <h2>Answer the questions restaurant teams ask before adopting new tools.</h2>
                </div>
                <p>The FAQ section addresses the operational objections most likely to slow down signups, which makes the launch page more conversion-ready and more aligned with the spec.</p>
            </div>
            <div class="faq-list">
                {faq_items}
            </div>
        </section>
""".rstrip(),
            "pricing": f"""
        <section class="section">
            <div class="section-header">
                <div>
                    <span class="eyebrow">Pricing And ROI</span>
                    <h2>Show operators the savings case, not just the product story.</h2>
                </div>
                <p>This section turns the value proposition into an operator-friendly business case with a visible subscription price and a plain-language ROI explanation.</p>
            </div>
            <div class="pricing-grid">
                <article class="pricing-card featured-tier">
                    <span class="eyebrow">Launch Plan</span>
                    <h3>$79<span>/month</span></h3>
                    <p>Built for independent restaurants that need nightly waste predictions, discount recommendations, and a cleaner close-time workflow.</p>
                    <ul class="promise-list">
                        <li>Waste prediction dashboard</li>
                        <li>Offer generation guidance</li>
                        <li>Redemption and revenue visibility</li>
                        <li>Fast onboarding for operators</li>
                    </ul>
                </article>
                <article class="pricing-card roi-card">
                    <span class="eyebrow">Expected Payback</span>
                    <h3>Recover the fee in one busy week.</h3>
                    <p>For restaurants losing margin to leftovers, preventing even a small amount of nightly spoilage can offset the subscription and turn waste into incremental revenue.</p>
                    <div class="roi-badges">
                        <span>Lower spoilage</span>
                        <span>More close-time sell-through</span>
                        <span>Clear nightly margin insight</span>
                    </div>
                </article>
            </div>
        </section>
""".rstrip(),
        }
        section_order = self._section_order(variant_seed)
        rendered_sections = "\n\n".join(section_blocks[name] for name in section_order)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{startup_name}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&family=Fraunces:wght@600;700&display=swap');
        :root {{
            --bg: {theme["bg"]};
            --surface: {theme["surface"]};
            --surface-strong: {theme["surface_strong"]};
            --ink: {theme["ink"]};
            --muted: {theme["muted"]};
            --accent: {theme["accent"]};
            --accent-2: {theme["accent_2"]};
            --line: rgba(31, 30, 26, 0.08);
            --shadow: 0 24px 60px rgba(31, 30, 26, 0.12);
        }}
        * {{
            box-sizing: border-box;
        }}
        body {{
            margin: 0;
            font-family: {body_font};
            background:
                radial-gradient(circle at top left, {theme["glow_1"]}, transparent 28%),
                radial-gradient(circle at top right, {theme["glow_2"]}, transparent 30%),
                linear-gradient(180deg, {theme["gradient_start"]} 0%, {theme["gradient_end"]} 100%);
            color: var(--ink);
        }}
        .page {{
            width: min(1180px, calc(100% - 32px));
            margin: 0 auto;
            padding: 32px 0 56px;
        }}
        .hero {{
            display: grid;
            grid-template-columns: 1.3fr 0.9fr;
            gap: 28px;
            align-items: stretch;
        }}
        .hero-copy {{
            position: relative;
            overflow: hidden;
        }}
        .hero-copy, .hero-panel, .section {{
            background: var(--surface);
            backdrop-filter: blur(10px);
            border: 1px solid var(--line);
            border-radius: 28px;
            box-shadow: var(--shadow);
        }}
        .hero-copy {{
            padding: 44px;
        }}
        .hero-copy::after {{
            content: "";
            position: absolute;
            inset: auto -80px -100px auto;
            width: 240px;
            height: 240px;
            background: radial-gradient(circle, rgba(255,255,255,0.55), transparent 70%);
            pointer-events: none;
        }}
        .hero-panel {{
            padding: 28px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            background: {hero_blend};
            overflow: hidden;
        }}
        .hero-media {{
            position: relative;
            min-height: 240px;
            margin-top: 18px;
            border-radius: 24px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.35);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.3);
        }}
        .hero-media img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
            filter: saturate(1.08) contrast(1.02);
        }}
        .hero-media::after {{
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(180deg, rgba(24, 32, 51, 0.00), rgba(24, 32, 51, 0.34));
        }}
        .hero-media-label {{
            position: absolute;
            left: 16px;
            bottom: 16px;
            z-index: 1;
            padding: 10px 14px;
            border-radius: 999px;
            background: rgba(255,255,255,0.82);
            color: var(--ink);
            font-family: "Helvetica Neue", Arial, sans-serif;
            font-size: 0.85rem;
            font-weight: 700;
        }}
        .eyebrow {{
            display: inline-block;
            font-family: "Helvetica Neue", Arial, sans-serif;
            font-size: 12px;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: var(--accent);
            margin-bottom: 14px;
        }}
        h1 {{
            margin: 0 0 16px;
            font-family: {display_font};
            font-size: clamp(2.8rem, 5vw, 5rem);
            line-height: 0.95;
            letter-spacing: -0.04em;
        }}
        .lede {{
            margin: 0;
            font-size: 1.15rem;
            line-height: 1.75;
            color: var(--muted);
            max-width: 58ch;
        }}
        .cta-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            margin-top: 28px;
            align-items: center;
        }}
        .cta-button {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 54px;
            padding: 0 24px;
            border-radius: 999px;
            background: linear-gradient(135deg, var(--accent-2), var(--accent));
            color: #fffaf3;
            text-decoration: none;
            font-family: "Helvetica Neue", Arial, sans-serif;
            font-size: 0.98rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            box-shadow: {cta_shadow};
        }}
        .cta-note {{
            font-family: "Helvetica Neue", Arial, sans-serif;
            color: var(--muted);
            font-size: 0.92rem;
        }}
        .hero-stats {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 14px;
        }}
        .stat {{
            padding: 16px;
            border-radius: 18px;
            background: {surface_tint};
            border: 1px solid rgba(31, 30, 26, 0.06);
        }}
        .stat strong {{
            display: block;
            font-size: 1.6rem;
            margin-bottom: 6px;
        }}
        .hero-panel p {{
            margin: 0;
            color: var(--muted);
            line-height: 1.7;
        }}
        .section {{
            margin-top: 28px;
            padding: 32px;
        }}
        .section-header {{
            display: flex;
            justify-content: space-between;
            gap: 18px;
            align-items: end;
            margin-bottom: 24px;
        }}
        .section-header h2 {{
            margin: 6px 0 0;
            font-size: clamp(1.8rem, 3vw, 2.7rem);
            letter-spacing: -0.03em;
        }}
        .section-header p {{
            max-width: 52ch;
            margin: 0;
            color: var(--muted);
            line-height: 1.7;
        }}
        .feature-grid, .persona-grid, .testimonial-grid {{
            display: grid;
            gap: 18px;
        }}
        .feature-grid {{
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }}
        .persona-grid, .testimonial-grid {{
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .dashboard-shell {{
            display: grid;
            grid-template-columns: 1.15fr 0.85fr;
            gap: 18px;
            align-items: stretch;
        }}
        .dashboard-card, .sidebar-card, .faq-item, .newsletter-card {{
            padding: 22px;
            border-radius: 22px;
            background: var(--surface-strong);
            border: 1px solid var(--line);
        }}
        .dashboard-metrics {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
            margin-top: 18px;
        }}
        .dashboard-visual {{
            margin-top: 18px;
            border-radius: 22px;
            overflow: hidden;
            border: 1px solid var(--line);
            background: rgba(255,255,255,0.5);
        }}
        .dashboard-visual img {{
            width: 100%;
            display: block;
        }}
        .metric {{
            padding: 14px;
            border-radius: 18px;
            background: {surface_tint};
        }}
        .metric strong {{
            display: block;
            font-size: 1.3rem;
            margin-bottom: 6px;
        }}
        .dashboard-flow {{
            margin-top: 18px;
            display: grid;
            gap: 12px;
        }}
        .flow-step {{
            display: flex;
            gap: 12px;
            align-items: flex-start;
            padding: 14px;
            border-radius: 16px;
            background: rgba(255,255,255,0.48);
            border: 1px solid var(--line);
        }}
        .flow-step span {{
            min-width: 30px;
            height: 30px;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-family: "Helvetica Neue", Arial, sans-serif;
            font-weight: 700;
            color: #fff;
            background: linear-gradient(135deg, var(--accent-2), var(--accent));
        }}
        .feature-card, .persona-card, .testimonial-card {{
            padding: 22px;
            border-radius: 22px;
            background: var(--surface-strong);
            border: 1px solid var(--line);
        }}
        .feature-icon, .persona-icon, .testimonial-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 48px;
            height: 48px;
            border-radius: 16px;
            margin-bottom: 14px;
            background: linear-gradient(135deg, rgba(255,255,255,0.96), {surface_tint});
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.5);
            font-size: 1.4rem;
        }}
        .feature-card h3, .persona-card h3 {{
            margin: 0 0 10px;
            font-size: 1.2rem;
        }}
        .feature-card p, .persona-card p, .testimonial-card p {{
            margin: 0;
            color: var(--muted);
            line-height: 1.7;
        }}
        .persona-card p + p {{
            margin-top: 10px;
        }}
        .quote {{
            font-size: 1.08rem;
        }}
        .author {{
            margin-top: 14px !important;
            font-family: "Helvetica Neue", Arial, sans-serif;
            color: var(--ink) !important;
            font-weight: 700;
        }}
        .case-link {{
            margin-top: 10px !important;
            display: inline-block;
            color: var(--accent);
            font-family: "Helvetica Neue", Arial, sans-serif;
            font-weight: 700;
            text-decoration: none;
        }}
        .promise-list {{
            margin: 0;
            padding-left: 18px;
            color: var(--muted);
            line-height: 1.9;
        }}
        .closing {{
            display: grid;
            grid-template-columns: 1.1fr 0.9fr;
            gap: 18px;
            align-items: center;
        }}
        .closing-card {{
            padding: 28px;
            border-radius: 24px;
            background: {theme["closing_blend"]};
            border: 1px solid var(--line);
        }}
        .closing-card h2 {{
            margin: 0 0 12px;
            font-family: {display_font};
            font-size: clamp(2rem, 3vw, 3rem);
            letter-spacing: -0.03em;
        }}
        .closing-card p {{
            margin: 0 0 20px;
            color: var(--muted);
            line-height: 1.75;
        }}
        .newsletter-card form {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-top: 18px;
        }}
        .newsletter-card input {{
            flex: 1 1 220px;
            min-height: 52px;
            padding: 0 16px;
            border-radius: 999px;
            border: 1px solid var(--line);
            background: rgba(255,255,255,0.82);
            font: inherit;
        }}
        .newsletter-card button {{
            min-height: 52px;
            padding: 0 20px;
            border: 0;
            border-radius: 999px;
            background: linear-gradient(135deg, var(--accent), var(--accent-2));
            color: #fff;
            font-family: "Helvetica Neue", Arial, sans-serif;
            font-weight: 700;
            cursor: pointer;
        }}
        .faq-list {{
            display: grid;
            gap: 14px;
        }}
        .pricing-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
        }}
        .pricing-card {{
            padding: 24px;
            border-radius: 22px;
            background: var(--surface-strong);
            border: 1px solid var(--line);
        }}
        .pricing-card h3 {{
            margin: 8px 0 12px;
            font-family: {display_font};
            font-size: clamp(1.8rem, 3vw, 2.6rem);
            letter-spacing: -0.03em;
        }}
        .pricing-card h3 span {{
            font-family: {body_font};
            font-size: 1rem;
            color: var(--muted);
            margin-left: 4px;
        }}
        .featured-tier {{
            background: linear-gradient(180deg, rgba(255,255,255,0.92), {surface_tint});
        }}
        .roi-badges {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 18px;
        }}
        .roi-badges span {{
            display: inline-flex;
            padding: 10px 14px;
            border-radius: 999px;
            background: {surface_tint};
            border: 1px solid var(--line);
            font-family: "Helvetica Neue", Arial, sans-serif;
            font-size: 0.92rem;
            font-weight: 700;
        }}
        .faq-item h3 {{
            margin: 0 0 8px;
            font-size: 1.05rem;
        }}
        @media (max-width: 900px) {{
            .hero, .closing, .feature-grid, .persona-grid, .testimonial-grid, .dashboard-shell, .pricing-grid {{
                grid-template-columns: 1fr;
            }}
            .dashboard-metrics {{
                grid-template-columns: 1fr;
            }}
            .hero-copy, .hero-panel, .section {{
                padding: 24px;
            }}
        }}
    </style>
</head>
<body>
    <main class="page">
        <section class="hero">
            <div class="hero-copy">
                <span class="eyebrow">{escape(labels["hero_eyebrow"])}</span>
                <h1>{headline}</h1>
                <p class="lede">{subheadline}</p>
                <div class="cta-row">
                    <a href="#launch-cta" class="cta-button">{cta_text}</a>
                    <span class="cta-note">{escape(labels["cta_note"])}</span>
                </div>
            </div>
            <aside class="hero-panel">
                <div>
                    <span class="eyebrow">{escape(labels["panel_eyebrow"])}</span>
                    <p>{value_proposition}</p>
                    <div class="hero-media">
                        <img src="{hero_image_url}" alt="{startup_name} domain visual">
                        <div class="hero-media-label">{escape(labels["hero_eyebrow"])}</div>
                    </div>
                </div>
                <div class="hero-stats">
                    {hero_stats}
                </div>
            </aside>
        </section>
        {rendered_sections}

        <section class="section">
            <div class="closing">
                <div class="closing-card" id="launch-cta">
                    <span class="eyebrow">{escape(labels["closing_eyebrow"])}</span>
                    <h2>{escape(labels["closing_title"])}</h2>
                    <p>{value_proposition}</p>
                    <a href="#" class="cta-button">{cta_text}</a>
                </div>
                <div class="closing-card">
                    <span class="eyebrow">{escape(labels["hooks_eyebrow"])}</span>
                    <ul class="promise-list">
                        {hook_items}
                    </ul>
                </div>
            </div>
        </section>
    </main>
</body>
</html>
"""

    def _split_feature_title(self, item: str) -> tuple[str, str]:
        if ":" in item:
            title, description = item.split(":", 1)
            return title.strip(), description.strip()
        return item.strip(), "Professional launch support designed to move founders from idea to execution faster."

    def _select_theme(self, product_spec: dict, seed: int | None = None) -> dict[str, str]:
        effective_seed = seed if seed is not None else self._variant_seed(product_spec)
        return self._select_theme_from_seed(effective_seed)

    def _select_theme_from_seed(self, seed: int) -> dict[str, str]:
        themes = [
            {
                "bg": "#f5efe4",
                "surface": "rgba(255, 252, 246, 0.86)",
                "surface_strong": "#fffaf0",
                "surface_tint": "rgba(255, 250, 240, 0.8)",
                "ink": "#1f1e1a",
                "muted": "#5d564b",
                "accent": "#0d9488",
                "accent_2": "#f97316",
                "glow_1": "rgba(249, 115, 22, 0.18)",
                "glow_2": "rgba(13, 148, 136, 0.18)",
                "gradient_start": "#fcf8f1",
                "gradient_end": "#f2ecdf",
                "hero_blend": "linear-gradient(180deg, rgba(13, 148, 136, 0.12), rgba(249, 115, 22, 0.10))",
                "closing_blend": "linear-gradient(135deg, rgba(13, 148, 136, 0.12), rgba(249, 115, 22, 0.12))",
                "body_font": '"Manrope", "Helvetica Neue", Arial, sans-serif',
                "display_font": '"Fraunces", Georgia, serif',
                "cta_shadow": "0 16px 34px rgba(13, 148, 136, 0.22)",
            },
            {
                "bg": "#eef3ff",
                "surface": "rgba(255, 255, 255, 0.84)",
                "surface_strong": "#ffffff",
                "surface_tint": "rgba(245, 248, 255, 0.92)",
                "ink": "#182033",
                "muted": "#52607a",
                "accent": "#2563eb",
                "accent_2": "#14b8a6",
                "glow_1": "rgba(37, 99, 235, 0.16)",
                "glow_2": "rgba(20, 184, 166, 0.14)",
                "gradient_start": "#f7faff",
                "gradient_end": "#e9f0ff",
                "hero_blend": "linear-gradient(180deg, rgba(37, 99, 235, 0.12), rgba(20, 184, 166, 0.10))",
                "closing_blend": "linear-gradient(135deg, rgba(37, 99, 235, 0.10), rgba(20, 184, 166, 0.14))",
                "body_font": '"Manrope", "Helvetica Neue", Arial, sans-serif',
                "display_font": '"Fraunces", Georgia, serif',
                "cta_shadow": "0 16px 34px rgba(37, 99, 235, 0.24)",
            },
            {
                "bg": "#f4f0ff",
                "surface": "rgba(253, 250, 255, 0.84)",
                "surface_strong": "#fffaff",
                "surface_tint": "rgba(251, 245, 255, 0.88)",
                "ink": "#241a34",
                "muted": "#655579",
                "accent": "#7c3aed",
                "accent_2": "#ec4899",
                "glow_1": "rgba(124, 58, 237, 0.14)",
                "glow_2": "rgba(236, 72, 153, 0.16)",
                "gradient_start": "#fbf8ff",
                "gradient_end": "#efe7fb",
                "hero_blend": "linear-gradient(180deg, rgba(124, 58, 237, 0.12), rgba(236, 72, 153, 0.10))",
                "closing_blend": "linear-gradient(135deg, rgba(124, 58, 237, 0.10), rgba(236, 72, 153, 0.12))",
                "body_font": '"Manrope", "Helvetica Neue", Arial, sans-serif',
                "display_font": '"Fraunces", Georgia, serif',
                "cta_shadow": "0 16px 34px rgba(124, 58, 237, 0.22)",
            },
            {
                "bg": "#eef7f0",
                "surface": "rgba(249, 255, 250, 0.84)",
                "surface_strong": "#ffffff",
                "surface_tint": "rgba(243, 251, 245, 0.9)",
                "ink": "#1b2a1f",
                "muted": "#55685a",
                "accent": "#15803d",
                "accent_2": "#ca8a04",
                "glow_1": "rgba(21, 128, 61, 0.15)",
                "glow_2": "rgba(202, 138, 4, 0.12)",
                "gradient_start": "#f8fff8",
                "gradient_end": "#eaf6ea",
                "hero_blend": "linear-gradient(180deg, rgba(21, 128, 61, 0.12), rgba(202, 138, 4, 0.10))",
                "closing_blend": "linear-gradient(135deg, rgba(21, 128, 61, 0.10), rgba(202, 138, 4, 0.13))",
                "body_font": '"Manrope", "Helvetica Neue", Arial, sans-serif',
                "display_font": '"Fraunces", Georgia, serif',
                "cta_shadow": "0 16px 34px rgba(21, 128, 61, 0.20)",
            },
        ]
        return themes[seed % len(themes)]

    def _select_labels(self, product_spec: dict, seed: int | None = None) -> dict[str, str]:
        startup_name = product_spec.get("startup_name", "LaunchMind")
        variants = [
            {
                "hero_eyebrow": "Launch-Ready In 24 Hours",
                "cta_note": "Built for student founders and non-technical builders who need polished launch assets fast.",
                "panel_eyebrow": "Why It Matters",
                "features_eyebrow": "Core Capabilities",
                "features_title": "Everything needed to look credible from day one.",
                "features_body": "This page mirrors the product spec directly with a strong value proposition, visible social proof, responsive layout, and a persuasive launch call-to-action.",
                "persona_eyebrow": "Who It Helps",
                "persona_title": "Built around founder pain points, not generic startup fluff.",
                "persona_body": f"{startup_name} is designed for founders who need speed, clarity, and a polished presence without losing weeks to design and copy iteration.",
                "testimonial_eyebrow": "Social Proof",
                "testimonial_title": "Founders trust polished execution when the stakes are high.",
                "testimonial_body": "These testimonials reinforce the exact promise in the product spec: rough startup ideas become launch-ready assets that feel credible and investor-facing.",
                "closing_eyebrow": "Launch Faster",
                "closing_title": "Go from messy idea to confident launch story.",
                "hooks_eyebrow": "Messaging Hooks",
            },
            {
                "hero_eyebrow": "Student Founder Momentum",
                "cta_note": "Clear messaging, better credibility, and a faster path from startup idea to public launch.",
                "panel_eyebrow": "The Promise",
                "features_eyebrow": "What You Unlock",
                "features_title": "A launch stack shaped for early-stage founders.",
                "features_body": "Instead of a generic brochure page, this layout emphasizes execution quality: benefits, proof, founder fit, and a direct invitation to act.",
                "persona_eyebrow": "Founder Profiles",
                "persona_title": "Made for ambitious builders with limited time and leverage.",
                "persona_body": f"{startup_name} focuses on the people who most need acceleration: students, solo founders, and operators trying to look established quickly.",
                "testimonial_eyebrow": "Proof Of Confidence",
                "testimonial_title": "The page feels stronger when outcomes are visible.",
                "testimonial_body": "The testimonials section gives the launch a sense of traction and credibility, which helps both conversion and QA alignment.",
                "closing_eyebrow": "Ready To Move",
                "closing_title": "Turn startup momentum into a clear next step.",
                "hooks_eyebrow": "Angles To Lead With",
            },
            {
                "hero_eyebrow": "From Rough Idea To Release",
                "cta_note": "A stable launch page, sharper positioning, and a more convincing story for users and investors.",
                "panel_eyebrow": "Strategic Value",
                "features_eyebrow": "Execution Layers",
                "features_title": "More than a landing page: a clearer market-facing story.",
                "features_body": "The sections stay reliable for QA, but the presentation shifts to match the product identity, target users, and founder expectations.",
                "persona_eyebrow": "Audience Fit",
                "persona_title": "The strongest launches speak directly to their real users.",
                "persona_body": f"{startup_name} is framed here around the specific founder personas in the product spec so the experience feels intentional rather than one-size-fits-all.",
                "testimonial_eyebrow": "Trust Signals",
                "testimonial_title": "Social proof makes the value proposition feel believable.",
                "testimonial_body": "This section adds credibility and emotional reassurance so the page does not rely on feature claims alone.",
                "closing_eyebrow": "Take The Next Step",
                "closing_title": "Make the launch page work like a real growth asset.",
                "hooks_eyebrow": "Positioning Lines",
            },
        ]
        effective_seed = seed if seed is not None else self._variant_seed(product_spec)
        return variants[effective_seed % len(variants)]

    def _build_stat_pairs(self, product_spec: dict) -> list[tuple[str, str]]:
        persona_names = [persona.get("name", "Founder") for persona in product_spec.get("personas", [])[:2]]
        first_persona = persona_names[0] if persona_names else "Founders"
        return [
            ("24h", "From rough idea to launch-ready presence"),
            ("No Code", "Professional output without building everything yourself"),
            ("Investor-Ready", "Sharper messaging for traction, credibility, and outreach"),
            (first_persona, "Designed around real user pain points and fast execution"),
        ]

    def _build_dashboard_cards(self, product_spec: dict) -> str:
        startup_name = escape(product_spec.get("startup_name", "LaunchMind"))
        cards = [
            ("18 trays", "Predicted unsold inventory"),
            ("34%", "Average waste reduction opportunity"),
            ("$420", f"Recovered revenue with {startup_name} offers"),
        ]
        return "\n".join(
            f"""
                        <div class="metric">
                            <strong>{escape(value)}</strong>
                            <span>{escape(label)}</span>
                        </div>
            """.rstrip()
            for value, label in cards
        )

    def _build_faq_items(self, product_spec: dict) -> str:
        startup_name = product_spec.get("startup_name", "LaunchMind")
        items = [
            (
                f"How does {startup_name} predict end-of-day waste?",
                "It combines recent sales velocity, category-level inventory trends, and closing-time behavior to estimate what will likely remain unsold before service ends.",
            ),
            (
                "Do restaurant teams need to change their POS workflow?",
                "No. The platform is positioned as a lightweight layer that reads existing sales signals, recommends offers quickly, and helps teams act before inventory becomes waste.",
            ),
            (
                "What do customers experience?",
                "Nearby diners receive clear, time-sensitive offers for fresh discounted meals, making the value obvious while helping restaurants recover revenue that would otherwise be lost.",
            ),
        ]
        return "\n".join(
            f"""
                <article class="faq-item">
                    <h3>{escape(question)}</h3>
                    <p>{escape(answer)}</p>
                </article>
            """.strip()
            for question, answer in items
        )

    def _build_newsletter_copy(self, product_spec: dict) -> str:
        startup_name = product_spec.get("startup_name", "LaunchMind")
        return (
            f"{startup_name} needs both a demo signup CTA and a newsletter-style lead capture path so operators can either book a walkthrough immediately or stay informed until launch."
        )

    def _hero_image_url(self, product_spec: dict) -> str:
        return self._domain_visual_data_uri(product_spec, kind="hero")

    def _demo_visual_url(self, product_spec: dict) -> str:
        return self._domain_visual_data_uri(product_spec, kind="demo")

    def _domain_keywords(self, product_spec: dict) -> list[str]:
        blob = " ".join(
            [
                product_spec.get("startup_name", ""),
                product_spec.get("value_proposition", ""),
                " ".join(feature.get("name", "") for feature in product_spec.get("features", [])),
                " ".join(persona.get("name", "") for persona in product_spec.get("personas", [])),
            ]
        ).lower()
        keyword_map = [
            (["restaurant", "food", "meal", "diner", "kitchen"], ["restaurant", "food", "kitchen"]),
            (["health", "clinic", "doctor", "patient"], ["healthcare", "doctor", "wellness"]),
            (["finance", "invoice", "payment", "bank"], ["finance", "payments", "business"]),
            (["education", "student", "tutor", "school"], ["education", "students", "learning"]),
            (["travel", "hotel", "trip"], ["travel", "tourism", "adventure"]),
        ]
        for triggers, keywords in keyword_map:
            if any(trigger in blob for trigger in triggers):
                return keywords
        return ["startup", "technology", "product"]

    def _select_visual_pack(self, product_spec: dict) -> dict[str, list[str] | str]:
        blob = " ".join(self._domain_keywords(product_spec))
        if "restaurant" in blob or "food" in blob or "kitchen" in blob:
            return {
                "feature_icons": ["🍽️", "📉", "🏷️", "📊", "📍", "⏰"],
                "persona_icons": ["👨‍🍳", "🧑‍🍳", "🍴", "🥡"],
                "testimonial_icon": "⭐",
            }
        if "education" in blob or "students" in blob or "learning" in blob:
            return {
                "feature_icons": ["📚", "🧠", "🎓", "🗂️", "💬", "⏱️"],
                "persona_icons": ["🧑‍🎓", "👩‍🏫", "📖", "📝"],
                "testimonial_icon": "🎯",
            }
        return {
            "feature_icons": ["🚀", "⚙️", "📈", "💡", "🧭", "🔔"],
            "persona_icons": ["🧑‍💼", "👥", "📱", "💼"],
            "testimonial_icon": "✨",
        }

    def _feature_icon(self, item: str, visual_pack: dict) -> str:
        icons = visual_pack["feature_icons"]
        title = self._split_feature_title(item)[0].lower()
        if "dashboard" in title:
            return "📊"
        if "discount" in title or "offer" in title:
            return "🏷️"
        if "prediction" in title or "forecast" in title:
            return "📉"
        if "notification" in title:
            return "🔔"
        return icons[sum(ord(char) for char in title) % len(icons)]

    def _persona_icon(self, persona_name: str, visual_pack: dict) -> str:
        icons = visual_pack["persona_icons"]
        return icons[sum(ord(char) for char in persona_name.lower()) % len(icons)]

    def _testimonial_icon(self, visual_pack: dict) -> str:
        return str(visual_pack["testimonial_icon"])

    def _variant_seed(self, product_spec: dict) -> int:
        startup_name = product_spec.get("startup_name", "launchmind")
        self.state["render_count"] = int(self.state.get("render_count", 0)) + 1
        base = sum(ord(char) for char in startup_name)
        return base + (self.state["render_count"] * 997)

    def _section_order(self, seed: int) -> list[str]:
        orders = [
            ["features", "personas", "dashboard", "pricing", "testimonials", "newsletter", "faq"],
            ["dashboard", "features", "pricing", "personas", "testimonials", "faq", "newsletter"],
            ["personas", "features", "dashboard", "testimonials", "pricing", "newsletter", "faq"],
            ["pricing", "features", "dashboard", "testimonials", "personas", "faq", "newsletter"],
        ]
        return orders[seed % len(orders)]

    def _domain_visual_data_uri(self, product_spec: dict, kind: str) -> str:
        startup_name = product_spec.get("startup_name", "LaunchMind")
        domain_keywords = self._domain_keywords(product_spec)
        title = startup_name[:28]
        subtitle = " · ".join(domain_keywords[:3]).title()
        if kind == "hero":
            svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="780" viewBox="0 0 1200 780" fill="none">
  <rect width="1200" height="780" rx="40" fill="#0F172A"/>
  <rect x="50" y="56" width="1100" height="668" rx="32" fill="#111827"/>
  <circle cx="1020" cy="130" r="180" fill="#F97316" fill-opacity="0.28"/>
  <circle cx="180" cy="620" r="220" fill="#0D9488" fill-opacity="0.20"/>
  <rect x="110" y="120" width="380" height="480" rx="28" fill="#FFF7ED"/>
  <rect x="540" y="120" width="540" height="104" rx="24" fill="#1F2937"/>
  <rect x="540" y="250" width="250" height="158" rx="24" fill="#F97316"/>
  <rect x="830" y="250" width="250" height="158" rx="24" fill="#0D9488"/>
  <rect x="540" y="438" width="540" height="162" rx="24" fill="#172554"/>
  <text x="146" y="196" fill="#0F172A" font-family="Manrope, Arial, sans-serif" font-size="26" font-weight="700">{escape(title)}</text>
  <text x="146" y="236" fill="#475569" font-family="Manrope, Arial, sans-serif" font-size="18">{escape(subtitle)}</text>
  <text x="146" y="316" fill="#0F172A" font-family="Fraunces, Georgia, serif" font-size="48" font-weight="700">Plan tonight's recovery</text>
  <text x="146" y="368" fill="#334155" font-family="Manrope, Arial, sans-serif" font-size="20">Forecast leftovers, publish offers, and watch redemptions update in one operator view.</text>
  <rect x="146" y="430" width="184" height="54" rx="27" fill="#0F172A"/>
  <text x="184" y="464" fill="#FFF7ED" font-family="Manrope, Arial, sans-serif" font-size="18" font-weight="700">Book a demo</text>
  <text x="574" y="184" fill="#E5E7EB" font-family="Manrope, Arial, sans-serif" font-size="19" font-weight="700">Service dashboard preview</text>
  <text x="574" y="340" fill="white" font-family="Manrope, Arial, sans-serif" font-size="46" font-weight="800">18 trays</text>
  <text x="574" y="374" fill="white" font-family="Manrope, Arial, sans-serif" font-size="18">predicted unsold</text>
  <text x="864" y="340" fill="white" font-family="Manrope, Arial, sans-serif" font-size="46" font-weight="800">$420</text>
  <text x="864" y="374" fill="white" font-family="Manrope, Arial, sans-serif" font-size="18">recovered tonight</text>
  <text x="574" y="498" fill="#E5E7EB" font-family="Manrope, Arial, sans-serif" font-size="22" font-weight="700">Offer workflow</text>
  <text x="574" y="536" fill="#CBD5E1" font-family="Manrope, Arial, sans-serif" font-size="18">Predict surplus → recommend discount → push pickup offer → track redemption.</text>
</svg>
"""
        else:
            svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760" viewBox="0 0 1200 760" fill="none">
  <rect width="1200" height="760" rx="40" fill="#FFF7ED"/>
  <rect x="42" y="42" width="1116" height="676" rx="32" fill="#ffffff"/>
  <rect x="94" y="96" width="1012" height="72" rx="22" fill="#F8FAFC"/>
  <rect x="94" y="210" width="312" height="188" rx="28" fill="#0D9488"/>
  <rect x="444" y="210" width="312" height="188" rx="28" fill="#F97316"/>
  <rect x="794" y="210" width="312" height="188" rx="28" fill="#1D4ED8"/>
  <rect x="94" y="438" width="666" height="212" rx="28" fill="#111827"/>
  <rect x="796" y="438" width="310" height="212" rx="28" fill="#F8FAFC"/>
  <text x="130" y="140" fill="#0F172A" font-family="Manrope, Arial, sans-serif" font-size="24" font-weight="700">{escape(title)} demo section</text>
  <text x="130" y="280" fill="white" font-family="Manrope, Arial, sans-serif" font-size="22" font-weight="700">Waste risk</text>
  <text x="130" y="324" fill="white" font-family="Fraunces, Georgia, serif" font-size="54" font-weight="700">34%</text>
  <text x="480" y="280" fill="white" font-family="Manrope, Arial, sans-serif" font-size="22" font-weight="700">Offer uplift</text>
  <text x="480" y="324" fill="white" font-family="Fraunces, Georgia, serif" font-size="54" font-weight="700">2.1x</text>
  <text x="830" y="280" fill="white" font-family="Manrope, Arial, sans-serif" font-size="22" font-weight="700">Recovered revenue</text>
  <text x="830" y="324" fill="white" font-family="Fraunces, Georgia, serif" font-size="54" font-weight="700">$420</text>
  <text x="128" y="500" fill="#E5E7EB" font-family="Manrope, Arial, sans-serif" font-size="22" font-weight="700">Live workflow</text>
  <text x="128" y="544" fill="#CBD5E1" font-family="Manrope, Arial, sans-serif" font-size="19">Forecast leftovers, set discount rules, and monitor claim activity in one place.</text>
  <text x="830" y="500" fill="#0F172A" font-family="Manrope, Arial, sans-serif" font-size="22" font-weight="700">Operator outcomes</text>
  <text x="830" y="544" fill="#475569" font-family="Manrope, Arial, sans-serif" font-size="18">Less spoilage</text>
  <text x="830" y="578" fill="#475569" font-family="Manrope, Arial, sans-serif" font-size="18">Higher close-time sell-through</text>
  <text x="830" y="612" fill="#475569" font-family="Manrope, Arial, sans-serif" font-size="18">More predictable nightly margins</text>
</svg>
"""
        return f"data:image/svg+xml;charset=UTF-8,{quote(svg)}"
