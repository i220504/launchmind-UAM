# LaunchMind Multi-Agent Startup Launch System

This project is a production-style Python implementation of the LaunchMind assignment using:

- CrewAI for agent reasoning workflows
- Provider-configurable LLMs across the agent system
- Redis pub/sub for inter-agent messaging
- Real GitHub API integration for issue, branch, commit, PR, and inline review comments
- Real Slack API integration for launch notifications
- Real email sending via SendGrid or SMTP
- JSONL logs, message traceability, retries, and CEO-visible failure escalation

The project supports multiple providers, including OpenAI, OpenRouter-compatible models, and Gemini for engineer-specific generation paths.

## Public Repository

- Repository: [launchmind-UAM](https://github.com/i220504/launchmind-UAM)
- Latest Engineer PR proof: [Pull Request #36](https://github.com/i220504/launchmind-UAM/pull/36)
- Latest Engineer issue proof: [Issue #35](https://github.com/i220504/launchmind-UAM/issues/35)

## Project Overview

At runtime, the user provides a startup idea. The CEO agent decomposes the idea into structured work, coordinates Product, Engineer, Marketing, and QA agents through Redis pub/sub, reviews their outputs with LLM reasoning, triggers revision loops where needed, and posts a final summary to Slack.

Every inter-agent message uses this exact schema:

```json
{
  "message_id": "uuid-string",
  "from_agent": "ceo|product|engineer|marketing|qa",
  "to_agent": "ceo|product|engineer|marketing|qa",
  "message_type": "task|result|revision_request|confirmation|error",
  "payload": {},
  "timestamp": "ISO-8601 string",
  "parent_message_id": "uuid-string or null"
}
```

## Marks-Maximization Strategy

- Use all required agents: CEO, Product, Engineer, Marketing, QA.
- Make the CEO a real LLM-based orchestrator instead of a fixed script.
- Use real external APIs instead of mocked services.
- Preserve complete message history and JSONL audit logs for demo traceability.
- Demonstrate multiple revision loops: CEO review loops and QA-enforced rework loops.
- Show real GitHub issue, branch, commit, PR, inline comments, Slack messages, and email delivery.
- Keep the implementation modular and demo-friendly, with visible logs and persisted artifacts.

## Bonus Points Strategy

Implemented bonus-aligned items:

- QA agent: yes
- Redis pub/sub message bus: yes
- Graceful failure handling with retries and escalation: yes
- Multiple feedback loops: yes
- Full traceability and logging: yes
- Different LLM providers: yes

## Startup Idea

The current demo startup is a negotiation-as-a-service product. It helps people negotiate higher salaries, lower car prices, and better service-contract terms by generating negotiation strategy, counter-offers, follow-ups, and persuasive outreach on the user's behalf.

The product is intentionally concrete: it has a clear target user, a high-value outcome, and obvious reasons why someone would pay for it. That makes it a strong fit for the Product, Engineer, Marketing, and QA agents in this assignment.

## Recommended Demo Startup Idea

Use this:

`Negotiation-as-a-Service AI that negotiates salaries, car prices, and service contracts on your behalf by drafting counter-offers, follow-ups, and negotiation strategy.`

Why this works well:

- Easy to explain in under a minute
- Strong product, marketing, and landing-page outputs
- Looks impressive live because the value proposition is immediate and high-stakes
- Naturally creates persuasive copy, CTA sections, and clear user personas
- Naturally fits GitHub, Slack, and email demo steps

## Architecture

```text
User CLI
  -> Startup Runner
    -> CEO Agent
      -> Redis Pub/Sub
        -> Product Agent
        -> Engineer Agent -> GitHub API
        -> Marketing Agent -> Slack API + Email API
        -> QA Agent -> GitHub PR Inline Comments

All messages -> JSONL Message Store
All events -> Audit Log
All artifacts -> outputs/artifacts/
```

Agent communication summary:

- CEO -> Product: startup idea decomposition and structured product task
- Product -> CEO: product specification result
- CEO -> Engineer: approved engineering task and revision requests
- CEO -> Marketing: approved marketing task and revision requests
- Engineer -> CEO: landing page, GitHub issue, and PR result
- Marketing -> CEO: tagline, launch copy, email, and Slack result
- CEO -> QA: consolidated review task after engineer and marketing complete
- QA -> CEO: pass/fail review report and revision triggers
- CEO -> Slack: final workflow summary

## Repository Structure

```text
launchmind-project/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── main.py
├── config.py
├── utils/
├── messaging/
├── llm/
├── integrations/
├── agents/
├── runtime/
└── outputs/
    ├── logs/
    └── artifacts/
```

## Agent Responsibilities

- CEO: decomposes the idea, assigns work, reviews outputs, decides revisions, escalates failures, posts final Slack summary.
- Product: creates a structured product specification and shares it downstream.
- Engineer: generates `index.html`, creates GitHub issue and branch, commits the file, opens the PR.
- Marketing: generates launch copy, sends the real email, posts a real Slack launch message.
- QA: reviews engineer and marketing outputs, posts at least two inline PR comments, forces revisions when quality is weak.

## Redis Message Flow

1. CEO publishes a `task` to `product`.
2. Product returns a `result` to `ceo` and shares confirmations downstream.
3. CEO publishes `task` messages to `engineer` and `marketing`.
4. Engineer and Marketing return `result` messages to `ceo`.
5. CEO reviews both; if acceptable, CEO publishes a `task` to `qa`.
6. QA returns a `result` to `ceo`.
7. If QA fails either artifact, CEO publishes `revision_request` messages and the cycle repeats.
8. CEO posts the final Slack summary and writes the final artifact bundle.

## Setup

### 1. Install Python dependencies

```bash
cd /Users/osman/Documents/Documents/UNI/AGENTIC/A3/LauchMind/launchmind-project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 0. Clone the repository

```bash
git clone https://github.com/i220504/launchmind-UAM.git
cd launchmind-UAM
```

### 2. Start Redis

With Homebrew:

```bash
brew install redis
brew services start redis
redis-cli ping
```

With Docker:

```bash
docker run --name launchmind-redis -p 6379:6379 redis:7
```

### 3. Configure GitHub

1. Create a fine-grained personal access token with repository contents, pull requests, and issues permissions.
2. Set `GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_TOKEN`.
3. Ensure the target repo already exists and the default branch matches `GITHUB_DEFAULT_BASE_BRANCH`.

### 4. Configure Slack

1. Create a Slack app.
2. Enable bot scopes: `chat:write`.
3. Install the app to your workspace.
4. Invite the bot to your launches channel.
5. Set `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID`.

### 5. Configure Email

SendGrid option:

1. Create a SendGrid API key with Mail Send permission.
2. Verify the sender identity.
3. Set `SENDGRID_API_KEY`, `EMAIL_FROM`, `EMAIL_TO`.

SMTP option:

1. Use Gmail app password or another SMTP provider.
2. Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`.

### 6. Configure LLM Provider

OpenAI path:

1. Set `LLM_PROVIDER=openai`
2. Set `OPENAI_API_KEY`
3. Optionally change `OPENAI_MODEL`

OpenRouter path for free local testing:

1. Set `LLM_PROVIDER=openrouter`
2. Set `OPENROUTER_API_KEY`
3. Optionally change `OPENROUTER_MODEL` such as `openrouter/free`

Gemini path, currently used for the engineer provider override:

1. Set `ENGINEER_LLM_PROVIDER=gemini`
2. Set `GEMINI_API_KEY`
3. Optionally change `GEMINI_MODEL`

### 7. Create your `.env`

```bash
cp .env.example .env
```

Fill in all values before running.

## How To Run

```bash
python3 main.py --idea "Negotiation-as-a-Service AI that negotiates salaries, car prices, and service contracts on your behalf by drafting counter-offers, follow-ups, and negotiation strategy."
```

## External Platforms And What The Agents Do On Each

- GitHub
  - Engineer creates the issue, branch, commit, and pull request
  - QA posts inline PR review comments
- Slack
  - Marketing posts the launch message
  - CEO posts the final summary
- Email
  - Marketing sends the cold outreach email to the configured inbox
- Redis
  - All agents exchange structured JSON messages through Redis pub/sub channels
- OpenAI / Gemini / OpenRouter-compatible APIs
  - Agents use LLM reasoning for planning, generation, review, and revision decisions

## Slack Proof

- Slack workspace invite link: add your shareable workspace or channel invite link before submission if you want a direct public link here
- Alternative proof path: include screenshots of the Slack bot messages in the repository and link them here if you do not want to expose the invite publicly
- Current implementation proof file: [`integrations/slack_client.py`](./integrations/slack_client.py)

## GitHub PR Proof

- Engineer-created pull request: [https://github.com/i220504/launchmind-UAM/pull/36](https://github.com/i220504/launchmind-UAM/pull/36)

## Demo Frontend

To make the live demo easier, use the Streamlit demo console:

```bash
streamlit run demo_app.py
```

What the demo frontend shows:

- startup idea input and run controls
- live runtime logs
- live message history
- final summary card
- product, engineer, marketing, and QA artifacts
- landing page preview inside the browser
- GitHub PR / issue links
- evaluator-facing rubric checklist

This makes it much easier to show the entire assignment flow from one screen instead of switching manually between terminal, files, and artifacts.

## Demo Flow For 8 To 10 Minutes

1. Show the `.env` variables are externalized.
2. Start Redis and explain Redis pub/sub channels.
3. Run `python3 main.py --idea "..."`
4. Keep the terminal visible so the evaluator sees agent logs.
5. Open the GitHub repo and show the new issue.
6. Show the new branch and `index.html` commit.
7. Open the pull request.
8. Show QA inline comments inside the PR.
9. Show the Slack launches channel with the marketing message and CEO final summary.
10. Show the email inbox with the generated outreach email.
11. Open `outputs/logs/message_history.jsonl` and `outputs/artifacts/final_summary.json`.

## Failure Handling

Handled failure scenarios:

- LLM timeout, malformed output, or rate limiting: retry, then provider-aware fallback handling, then escalate to CEO.
- Redis connection issue: ping check and retry-wrapped publish.
- GitHub API failure: retries, then agent sends `error` message to CEO.
- Slack API failure: retries, then escalate. Final CEO Slack failure is recorded without deadlocking the run.
- Email sending failure: retries, then escalate.
- QA or CEO revision loops exceeding limit: CEO finalizes with visible error context.

## Logs And Artifacts

- `outputs/logs/runtime.log`: human-readable runtime logs
- `outputs/logs/audit.jsonl`: audit trail of events
- `outputs/logs/message_history.jsonl`: full message history
- `outputs/artifacts/*.json`: plan, reviews, QA report, final summary
- `outputs/artifacts/index.html`: generated landing page

## Demo Recording Advice

- Keep terminal, Slack, GitHub, and email tabs pre-opened.
- Start with the startup idea and architecture slide.
- Record the full run once with valid credentials so every integration succeeds.
- Zoom in enough that terminal logs and PR comments are readable.
- End by showing `message_history.jsonl` and `final_summary.json` so the evaluator sees traceability.

## Rubric Checklist

- Python implementation: complete
- CrewAI multi-agent framework: complete
- Multi-provider LLM support: complete
- Redis pub/sub: complete
- Structured JSON inter-agent messages: complete
- CEO dynamic orchestration with LLM: complete
- Product, Engineer, Marketing, QA agents: complete
- Real GitHub issue, branch, commit, PR, inline comments: complete
- Real Slack launch message: complete
- Real email sending: complete
- Multiple revision loops: complete
- Graceful failure handling with retries and escalation: complete
- Full logs and traceability: complete
- Environment-variable based secrets: complete

## Notes

- Before the demo, do one dry run with your actual credentials to confirm GitHub repo permissions, Slack bot membership, and email sender verification.
