from __future__ import annotations

import json
from typing import Any


def ceo_decomposition_prompt(startup_idea: str) -> str:
    return f"""
You are the CEO agent for a LaunchMind multi-agent system.
Decompose the startup idea into a tightly scoped execution plan.

Startup idea:
{startup_idea}

Return strict JSON with this shape:
{{
  "startup_name": "string",
  "north_star": "string",
  "product_task": {{
    "objective": "string",
    "success_criteria": ["string"],
    "constraints": ["string"]
  }},
  "engineer_task": {{
    "objective": "string",
    "deliverables": ["string"],
    "design_direction": ["string"]
  }},
  "marketing_task": {{
    "objective": "string",
    "deliverables": ["string"],
    "tone": ["string"]
  }},
  "qa_task": {{
    "objective": "string",
    "review_focus": ["string"]
  }}
}}

Rules:
- Ensure each task is concrete and testable.
- No markdown, no commentary, JSON only.
""".strip()


def ceo_review_prompt(startup_idea: str, artifact_type: str, artifact: dict[str, Any], qa_context: dict[str, Any] | None = None) -> str:
    qa_blob = json.dumps(qa_context or {}, indent=2)
    artifact_blob = json.dumps(artifact, indent=2)
    return f"""
You are the CEO agent reviewing a {artifact_type} artifact for a startup launch workflow.

Startup idea:
{startup_idea}

Artifact:
{artifact_blob}

QA context:
{qa_blob}

Return strict JSON:
{{
  "decision": "approve" | "revise",
  "score": 1-10,
  "strengths": ["string"],
  "issues": ["string"],
  "revision_instructions": ["string"]
}}

Rules:
- Approve only if the artifact is specific, coherent, and launch-ready.
- If you request revision, instructions must be concrete and directly actionable.
- Evaluate clarity, consistency, startup relevance, and demo value.
- For `product_spec`, approve if it is sufficiently actionable for engineering and marketing even if minor copy polish is still possible.
- Do not request revision for `product_spec` over small wording improvements alone.
- For `product_spec`, only request revision if a required section is missing, internally inconsistent, too vague for downstream execution, or badly misaligned with the startup idea.
- JSON only.
""".strip()


def product_prompt(startup_idea: str, ceo_task: dict[str, Any]) -> str:
    task_blob = json.dumps(ceo_task, indent=2)
    return f"""
You are the Product Agent in a multi-agent startup launch system.
Create a product specification for this startup idea:

{startup_idea}

CEO task:
{task_blob}

Return strict JSON:
{{
  "startup_name": "string",
  "value_proposition": "string",
  "personas": [
    {{
      "name": "string",
      "pain_points": ["string"],
      "desired_outcomes": ["string"]
    }}
  ],
  "features": [
    {{
      "name": "string",
      "description": "string",
      "priority": "high|medium|low"
    }}
  ],
  "user_stories": ["string"],
  "landing_page_requirements": ["string"],
  "marketing_hooks": ["string"]
}}

Validation rules:
- Tie every section directly to the startup idea.
- Features must be realistic for a launch landing page demo.
- Personas must be distinct.
- User stories must follow the format "As a ..., I want ..., so that ...".
- Each user story should be concrete and, where natural, include an observable outcome such as speed, clarity, validation, signups, or investor readiness.
- Landing page requirements must be implementation-ready and should explicitly mention the most important sections needed for the demo.
- Marketing hooks must sound believable and specific rather than hype-heavy.
- JSON only.
""".strip()


def engineer_design_brief_prompt(startup_idea: str, product_spec: dict[str, Any], task_payload: dict[str, Any]) -> str:
    return f"""
You are the Engineer Agent.
Your first job is to create a sharp design brief for a launch landing page before any HTML is written.

Startup idea:
{startup_idea}

Product spec:
{json.dumps(product_spec, indent=2)}

CEO or revision task:
{json.dumps(task_payload, indent=2)}

Return strict JSON:
{{
  "headline": "string",
  "subheadline": "string",
  "cta_text": "string",
  "page_goal": "string",
  "audience_focus": ["string"],
  "section_plan": [
    {{
      "id": "hero|features|demo|testimonials|pricing|faq|newsletter|personas|cta",
      "purpose": "string",
      "must_include": ["string"]
    }}
  ],
  "feature_bullets": ["string"],
  "testimonials": [
    {{
      "name": "string",
      "quote": "string"
    }}
  ],
  "visual_requirements": ["string"]
}}

Validation rules:
- Create an implementation-ready design brief, not HTML.
- The section plan must reflect the product spec and include every required landing page requirement.
- The brief must be concrete enough that another engineer could build the page from it.
- Headline must communicate the value proposition clearly.
- CTA text should feel specific and conversion-oriented.
- Testimonials should sound relevant to the domain and believable for a demo.
- JSON only.
""".strip()


def engineer_visual_direction_prompt(
    startup_idea: str,
    product_spec: dict[str, Any],
    task_payload: dict[str, Any],
    design_brief: dict[str, Any],
) -> str:
    return f"""
You are the Engineer Agent deciding the visual direction for a launch landing page.

Startup idea:
{startup_idea}

Product spec:
{json.dumps(product_spec, indent=2)}

Creative task payload:
{json.dumps(task_payload, indent=2)}

Design brief:
{json.dumps(design_brief, indent=2)}

Return strict JSON:
{{
  "design_style": "string",
  "layout_strategy": "string",
  "palette": {{
    "background": "hex",
    "surface": "hex",
    "primary": "hex",
    "secondary": "hex",
    "accent": "hex",
    "text": "hex",
    "muted_text": "hex"
  }},
  "typography": {{
    "display_family": "string",
    "body_family": "string",
    "font_import_url": "string"
  }},
  "imagery_plan": {{
    "hero_visual": "string",
    "demo_visual": "string",
    "icon_style": "string"
  }},
  "ui_motifs": ["string"],
  "animation_notes": ["string"]
}}

Validation rules:
- Make the visual direction feel premium and domain-aware.
- The direction must be distinct on each run and should use the provided creative direction instead of repeating a stock template.
- Use professional typography and avoid plain default font stacks.
- Plan visuals that can be built self-contained in HTML/CSS/SVG without relying on broken external assets.
- JSON only.
""".strip()


def engineer_github_prompt(startup_idea: str, product_spec: dict[str, Any], design_brief: dict[str, Any]) -> str:
    return f"""
You are the Engineer Agent preparing GitHub artifacts for a startup landing-page implementation.

Startup idea:
{startup_idea}

Product spec:
{json.dumps(product_spec, indent=2)}

Design brief:
{json.dumps(design_brief, indent=2)}

Return strict JSON:
{{
  "issue_title": "string",
  "issue_body": "string",
  "commit_message": "string",
  "pr_title": "string",
  "pr_body": "string"
}}

Rules:
- Set the GitHub issue title exactly to `Initial landing page`.
- The issue body must describe what the first landing page includes and why it matches the product spec.
- The commit message should be short, professional, and specific to the landing-page implementation.
- The pull request title and body must be professional and startup-specific.
- The pull request body should summarize what was built, what the page includes, and what QA/review should focus on.
- JSON only.
""".strip()


def engineer_prompt(startup_idea: str, product_spec: dict[str, Any], task_payload: dict[str, Any]) -> str:
    return f"""
You are the Engineer Agent. Build a polished single-file landing page in HTML with embedded CSS.

Startup idea:
{startup_idea}

Product spec:
{json.dumps(product_spec, indent=2)}

CEO or revision task:
{json.dumps(task_payload, indent=2)}

Return strict JSON:
{{
  "headline": "string",
  "subheadline": "string",
  "cta_text": "string",
  "feature_bullets": ["string"],
  "visual_concept": "string",
  "testimonials": [
    {{
      "name": "string",
      "quote": "string"
    }}
  ],
  "html": "full HTML document string"
}}

Validation rules:
- The HTML must be complete and directly runnable as index.html.
- Include a headline, subheadline, feature section, CTA button, responsive layout, and professional CSS styling.
- Reflect the product spec faithfully and cover its required landing-page sections.
- If the spec requires demo/mockup, FAQ, testimonials, pricing/ROI, newsletter/waitlist, or trust/privacy sections, include them clearly.
- Use professional typography and intentional visual design.
- Prefer self-contained visuals such as inline SVG, CSS artwork, or compact data-URI assets.
- Never use placeholder assets or fake URLs such as example.com or placeholder.com.
- Keep the HTML efficient enough for API generation: target roughly 160 to 280 lines and avoid unnecessary repetition.
- The result must feel premium, readable, and specific to the startup idea, not generic.
- JSON only.
""".strip()


def engineer_render_prompt(
    startup_idea: str,
    product_spec: dict[str, Any],
    task_payload: dict[str, Any],
    design_brief: dict[str, Any],
    visual_direction: dict[str, Any],
) -> str:
    return f"""
You are the Engineer Agent. Build a polished single-file landing page in HTML with embedded CSS.

Startup idea:
{startup_idea}

Product spec:
{json.dumps(product_spec, indent=2)}

Creative task payload:
{json.dumps(task_payload, indent=2)}

Design brief:
{json.dumps(design_brief, indent=2)}

Visual direction:
{json.dumps(visual_direction, indent=2)}

Return strict JSON:
{{
  "headline": "string",
  "subheadline": "string",
  "cta_text": "string",
  "feature_bullets": ["string"],
  "visual_concept": "string",
  "testimonials": [
    {{
      "name": "string",
      "quote": "string"
    }}
  ],
  "html": "full HTML document string"
}}

Validation rules:
- The HTML must be complete and directly runnable as index.html.
- Use the design brief and visual direction faithfully. Do not ignore them.
- Keep the HTML efficient enough for API generation: target roughly 160 to 280 lines, avoid unnecessary repetition, and do not generate overly long boilerplate.
- Include: headline, subheadline, feature section, testimonials or social-proof section, CTA button, visual styling, and responsive layout.
- If requested in the product spec, include a dashboard/demo mockup section, FAQ section, newsletter/demo signup capture section, pricing/ROI section, and any other explicitly requested sections.
- Always include a visible demo section or product mockup section.
- Always include at least one meaningful visual element such as a hero image, domain-relevant image, or inline SVG illustration.
- Always use professional typography. Import or define a polished font pairing and avoid plain default browser typography.
- Never use placeholder assets or fake URLs such as `example.com`, `placeholder.com`, or empty image sources.
- Prefer self-contained visuals: compact inline SVG illustrations, CSS artwork, or small data-URI visuals created inside the document.
- Avoid default-looking typography like plain Arial-only styling.
- The page should look premium, intentional, and visually rich rather than generic.
- The page must feel fresh on every run. Do not reuse the same layout, section wording, spacing rhythm, or visual treatment.
- Use the provided creative direction in the task payload to vary visual style, hierarchy, and section ordering.
- Use compact inline SVG illustrations, gradient shapes, badges, icon chips, and domain-relevant visual motifs inside the HTML itself.
- Do not rely on the same stock structure each time. Generate a new composition that is still professional and readable.
- Do not use JavaScript frameworks.
- HTML must reflect the product spec and any revision instructions.
- The headline must explicitly communicate the value proposition, not just speed or urgency.
- If the product spec asks for testimonials or social proof, the HTML must contain a visible testimonials or social-proof section.
- Use semantic sections where reasonable and make the CTA specific and persuasive.
- Use domain-relevant visual elements. Example: restaurants can have meal cards, table-service motifs, kitchen/dashboard mockups, offer chips, etc.
- Prefer inline SVG and CSS shapes over external dependencies so the file stays self-contained.
- Keep SVG markup concise. Do not generate giant repeated path data or oversized demo illustrations.
- Before finalizing, self-check that every landing page requirement in the product spec appears in the HTML.
- JSON only.
""".strip()


def engineer_repair_prompt(
    startup_idea: str,
    product_spec: dict[str, Any],
    task_payload: dict[str, Any],
    design_brief: dict[str, Any],
    visual_direction: dict[str, Any],
    current_result: dict[str, Any],
    missing_requirements: list[str],
) -> str:
    return f"""
You are the Engineer Agent repairing a landing page HTML draft.

Startup idea:
{startup_idea}

Product spec:
{json.dumps(product_spec, indent=2)}

Task payload:
{json.dumps(task_payload, indent=2)}

Design brief:
{json.dumps(design_brief, indent=2)}

Visual direction:
{json.dumps(visual_direction, indent=2)}

Current engineer draft:
{json.dumps(current_result, indent=2)}

Missing or weak requirements:
{json.dumps(missing_requirements, indent=2)}

Return strict JSON with the same shape:
{{
  "headline": "string",
  "subheadline": "string",
  "cta_text": "string",
  "feature_bullets": ["string"],
  "visual_concept": "string",
  "testimonials": [
    {{
      "name": "string",
      "quote": "string"
    }}
  ],
  "html": "full HTML document string"
}}

Rules:
- Keep the page visually premium and domain-specific.
- Preserve the strongest ideas from the design brief and visual direction while fixing the weak spots.
- Fix every missing requirement explicitly.
- Ensure the repaired HTML includes professional typography, meaningful visuals, and a visible demo section.
- Remove placeholder URLs and replace them with self-contained visuals or real renderable image sources.
- Do not return partial HTML.
- Use a visibly different, intentional layout if the previous one felt too generic.
- JSON only.
""".strip()


def marketing_prompt(startup_idea: str, product_spec: dict[str, Any], task_payload: dict[str, Any]) -> str:
    return f"""
You are the Marketing Agent. Create sharp launch messaging for this startup.

Startup idea:
{startup_idea}

Product spec:
{json.dumps(product_spec, indent=2)}

CEO or revision task:
{json.dumps(task_payload, indent=2)}

Return strict JSON:
{{
  "tagline": "under 10 words",
  "short_description": "string",
  "cold_outreach_email": {{
    "subject": "string",
    "body": "string"
  }},
  "social_posts": {{
    "x": ["string", "string", "string"],
    "linkedin": ["string", "string", "string"],
    "instagram": ["string", "string", "string"]
  }},
  "slack_summary": "string"
}}

Validation rules:
- Tagline must be fewer than 10 words.
- Tagline must be distinct from the headline and should not simply repeat the same promise.
- The short description must sound launch-ready, not generic.
- Social posts must not all repeat the same angle.
- Email must be specific and credible.
- Do not use placeholder tokens such as `{{{{first_name}}}}`, `{{link}}`, `{{city}}`, or bracketed dummy text.
- Write the cold outreach email as a natural, ready-to-send message for one clear audience from the product spec.
- End the cold outreach email with one concrete CTA in plain language such as replying to the email, joining the beta, or requesting a walkthrough.
- Avoid over-precise claims unless they are framed as configurable or pilot-dependent.
- Keep the tone confident, concise, and tailored to the actual buyer persona in the product spec.
- Before finalizing, self-check that the tagline, short description, and email each emphasize different aspects of the value proposition.
- JSON only.
""".strip()


def marketing_repair_prompt(startup_idea: str, product_spec: dict[str, Any], draft_output: dict[str, Any]) -> str:
    return f"""
You are the Marketing Agent doing a repair pass on your own draft.
Your job is to keep what is strong, fix what is misaligned, and return a final launch-ready marketing package.

Startup idea:
{startup_idea}

Product spec:
{json.dumps(product_spec, indent=2)}

Current draft:
{json.dumps(draft_output, indent=2)}

Return strict JSON:
{{
  "tagline": "under 10 words",
  "short_description": "string",
  "cold_outreach_email": {{
    "subject": "string",
    "body": "string"
  }},
  "social_posts": {{
    "x": ["string", "string", "string"],
    "linkedin": ["string", "string", "string"],
    "instagram": ["string", "string", "string"]
  }},
  "slack_summary": "string"
}}

Repair rules:
- The final copy must match the actual startup idea and product spec exactly.
- Remove any unrelated domain leakage or stale phrases from another startup.
- Pick one primary audience for the cold outreach email and write only for that audience.
- Keep the copy specific, credible, and demo-ready.
- Do not use placeholder tokens such as `{{{{first_name}}}}`, `{{link}}`, `{{city}}`, or bracketed dummy text.
- Do not mention features, industries, or personas that are not present in the startup idea or product spec.
- Keep the CTA concrete and singular in plain language.
- JSON only.
""".strip()


def qa_prompt(startup_idea: str, product_spec: dict[str, Any], engineer_result: dict[str, Any], marketing_result: dict[str, Any], task_payload: dict[str, Any]) -> str:
    return f"""
You are the QA and Reviewer Agent.
Review the engineer and marketing outputs against the product specification.

Startup idea:
{startup_idea}

Product spec:
{json.dumps(product_spec, indent=2)}

Engineer artifact:
{json.dumps(engineer_result, indent=2)}

Marketing artifact:
{json.dumps(marketing_result, indent=2)}

Review task:
{json.dumps(task_payload, indent=2)}

Return strict JSON:
{{
  "overall_status": "pass" | "fail",
  "engineer_review": {{
    "status": "pass" | "fail",
    "issues": ["string"],
    "inline_comments": ["string", "string"]
  }},
  "marketing_review": {{
    "status": "pass" | "fail",
    "issues": ["string"]
  }},
  "summary": "string"
}}

Validation rules:
- Be pragmatic and assignment-oriented rather than perfectionist.
- Only fail engineering if a clearly required section or capability from the product spec is genuinely missing or badly misaligned.
- Only fail marketing if the copy materially contradicts the value proposition, misses the target user, or is too generic to demo credibly.
- Do not invent requirements that are not explicitly present in the product spec.
- Do not require videos, real customer links, live case-study URLs, production analytics, or external assets unless the product spec explicitly asks for them.
- If the output is usable and launch-ready with only polish suggestions remaining, mark it as pass and put the polish points in the issues/comments.
- Always provide at least two concise inline HTML review comments.
- JSON only.
""".strip()
