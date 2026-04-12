from __future__ import annotations

import os
import time
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.events.event_bus import crewai_event_bus
from openai import OpenAI

from config import settings
from llm.output_parsers import expect_json
from utils.logger import get_logger
from utils.retry import retry_call


class OpenAIClient:
    def __init__(self) -> None:
        self.logger = get_logger("openai_client")
        provider = settings.llm_provider
        if provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
            os.environ["OPENAI_API_KEY"] = settings.openai_api_key
            self.model = settings.openai_model
            self.client = OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
        elif provider == "openrouter":
            if not settings.openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")
            self.model = settings.openrouter_model
            self.client = OpenAI(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
                timeout=settings.openai_timeout_seconds,
            )
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

    def _provider_bundle(self, provider_override: str | None = None) -> tuple[str, str, OpenAI]:
        provider = (provider_override or settings.llm_provider or "openai").strip().lower()
        if provider == "openai":
            return (
                provider,
                settings.openai_model,
                OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds),
            )
        if provider == "openrouter":
            return (
                provider,
                settings.openrouter_model,
                OpenAI(
                    api_key=settings.openrouter_api_key,
                    base_url=settings.openrouter_base_url,
                    timeout=settings.openai_timeout_seconds,
                ),
            )
        if provider == "gemini":
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required when ENGINEER_LLM_PROVIDER=gemini")
            return (
                provider,
                settings.gemini_model,
                OpenAI(
                    api_key=settings.gemini_api_key,
                    base_url=settings.gemini_base_url,
                    timeout=settings.openai_timeout_seconds,
                ),
            )
        raise ValueError(f"Unsupported provider override: {provider}")

    def run_crewai_task(
        self,
        *,
        role: str,
        goal: str,
        backstory: str,
        prompt: str,
        expected_output: str = "Strict JSON object",
    ) -> str:
        def _run() -> str:
            self._ensure_crewai_event_bus_ready()
            started = time.time()
            agent = Agent(
                role=role,
                goal=goal,
                backstory=backstory,
                verbose=settings.crewai_verbose,
                allow_delegation=False,
                llm=self.model,
            )
            task = Task(description=prompt, expected_output=expected_output, agent=agent)
            crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=settings.crewai_verbose)
            result = crew.kickoff()
            self.logger.info("CrewAI task completed role=%s duration=%.2fs", role, time.time() - started)
            return str(result).strip()

        return retry_call(_run)

    def _ensure_crewai_event_bus_ready(self) -> None:
        shutting_down = getattr(crewai_event_bus, "_shutting_down", False)
        executor = getattr(crewai_event_bus, "_sync_executor", None)
        loop = getattr(crewai_event_bus, "_loop", None)
        executor_dead = bool(executor is not None and getattr(executor, "_shutdown", False))
        loop_dead = bool(loop is not None and loop.is_closed())
        if shutting_down or executor_dead or loop_dead:
            self.logger.warning(
                "Resetting CrewAI event bus (shutting_down=%s executor_dead=%s loop_dead=%s)",
                shutting_down,
                executor_dead,
                loop_dead,
            )
            crewai_event_bus._initialize()

    def run_json_task(
        self,
        *,
        role: str,
        goal: str,
        backstory: str,
        prompt: str,
        provider_override: str | None = None,
    ) -> dict[str, Any]:
        provider = (provider_override or settings.llm_provider or "openai").strip().lower()
        if provider in {"openrouter", "gemini"}:
            self.logger.info(
                "Using direct %s JSON completion for role=%s to avoid unstable CrewAI provider routing.",
                provider.capitalize(),
                role,
            )
            return self.direct_json_completion(prompt, provider_override=provider)
        try:
            raw = self.run_crewai_task(role=role, goal=goal, backstory=backstory, prompt=prompt)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("CrewAI task failed before parsing, retrying with direct OpenAI: %s", exc)
            return self.direct_json_completion(prompt, provider_override=provider)
        try:
            return expect_json(raw)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("CrewAI output parse failed, retrying with direct OpenAI: %s", exc)
            return self.direct_json_completion(prompt, provider_override=provider)

    def run_json_task_fast(
        self,
        *,
        prompt: str,
        attempts: int | None = None,
        timeout_seconds: int | None = None,
        max_output_tokens: int | None = None,
        provider_override: str | None = None,
    ) -> dict[str, Any]:
        return self.direct_json_completion(
            prompt,
            attempts=attempts,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
            provider_override=provider_override,
        )

    def direct_json_completion(
        self,
        prompt: str,
        attempts: int | None = None,
        timeout_seconds: int | None = None,
        max_output_tokens: int | None = None,
        provider_override: str | None = None,
    ) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            started = time.time()
            provider, model, client = self._provider_bundle(provider_override)
            if timeout_seconds is not None:
                if provider == "openrouter":
                    client = OpenAI(
                        api_key=settings.openrouter_api_key,
                        base_url=settings.openrouter_base_url,
                        timeout=timeout_seconds,
                    )
                elif provider == "gemini":
                    client = OpenAI(
                        api_key=settings.gemini_api_key,
                        base_url=settings.gemini_base_url,
                        timeout=timeout_seconds,
                    )
                else:
                    client = OpenAI(api_key=settings.openai_api_key, timeout=timeout_seconds)

            if provider == "gemini":
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Return valid JSON only. Do not include markdown or commentary."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_output_tokens,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or "{}"
                self.logger.info("Direct Gemini JSON completion finished duration=%.2fs", time.time() - started)
                return expect_json(content)

            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": "Return valid JSON only. Do not include markdown or commentary.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_output_tokens=max_output_tokens,
            )
            self.logger.info("Direct %s JSON completion finished duration=%.2fs", provider.capitalize(), time.time() - started)
            return expect_json(response.output_text)

        return retry_call(_run, attempts=attempts)
