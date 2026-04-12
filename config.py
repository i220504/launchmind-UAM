from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    base_dir: Path = BASE_DIR
    outputs_dir: Path = BASE_DIR / "outputs"
    logs_dir: Path = BASE_DIR / "outputs" / "logs"
    artifacts_dir: Path = BASE_DIR / "outputs" / "artifacts"
    run_lock_path: Path = BASE_DIR / "outputs" / "run.lock"

    llm_provider: str = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_timeout_seconds: int = _get_int("OPENAI_TIMEOUT_SECONDS", 60)
    engineer_render_timeout_seconds: int = _get_int("ENGINEER_RENDER_TIMEOUT_SECONDS", 180)
    engineer_render_max_output_tokens: int = _get_int("ENGINEER_RENDER_MAX_OUTPUT_TOKENS", 9000)
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_base_url: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    engineer_llm_provider: str = os.getenv("ENGINEER_LLM_PROVIDER", "").strip().lower()

    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_channel_prefix: str = os.getenv("REDIS_CHANNEL_PREFIX", "launchmind")

    github_token: str = os.getenv("GITHUB_TOKEN", "")
    github_owner: str = os.getenv("GITHUB_OWNER", "")
    github_repo: str = os.getenv("GITHUB_REPO", "")
    github_default_base_branch: str = os.getenv("GITHUB_DEFAULT_BASE_BRANCH", "main")
    github_commit_author_name: str = os.getenv("GITHUB_COMMIT_AUTHOR_NAME", "EngineerAgent")
    github_commit_author_email: str = os.getenv("GITHUB_COMMIT_AUTHOR_EMAIL", "agent@launchmind.ai")

    slack_bot_token: str = os.getenv("SLACK_BOT_TOKEN", "")
    slack_channel_id: str = os.getenv("SLACK_CHANNEL_ID", "")

    sendgrid_api_key: str = os.getenv("SENDGRID_API_KEY", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    email_to: str = os.getenv("EMAIL_TO", "")

    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = _get_int("SMTP_PORT", 587)
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_use_tls: bool = _get_bool("SMTP_USE_TLS", True)

    demo_startup_idea: str = os.getenv(
        "DEMO_STARTUP_IDEA",
        "Negotiation-as-a-Service AI that negotiates salaries, car prices, and service contracts on your behalf by drafting counter-offers, follow-ups, and negotiation strategy.",
    )
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    max_revisions: int = _get_int("MAX_REVISIONS", 2)
    workflow_timeout_seconds: int = _get_int("WORKFLOW_TIMEOUT_SECONDS", 1800)
    retry_attempts: int = _get_int("RETRY_ATTEMPTS", 3)
    retry_backoff_seconds: int = _get_int("RETRY_BACKOFF_SECONDS", 2)
    crewai_verbose: bool = _get_bool("CREWAI_VERBOSE", True)


settings = Settings()
settings.logs_dir.mkdir(parents=True, exist_ok=True)
settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
